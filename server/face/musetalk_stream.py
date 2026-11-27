"""Streaming MuseTalk: Lumi's audio in (24 kHz), lip-synced video frames out (25 fps).

MuseTalk's own `scripts/realtime_inference.py` renders a whole audio clip at once.
This class does the same per-frame work on a live audio stream:

  1. Keep a rolling buffer of the last few seconds of audio.
  2. When enough audio has arrived for the next batch of frames, run Whisper's
     encoder over the buffer (MuseTalk's audio features, 50 per second).
  3. Each video frame i (40 ms) uses a window of 10 features starting 4 features
     (80 ms) before it, exactly like MuseTalk's `get_whisper_chunk` with its
     default padding of 2 frames on each side. So frame i can only be drawn once
     audio up to 80 ms past its end has arrived.
  4. UNet + VAE decoder redraw the mouth area; it's pasted back onto the matching
     frame of the prepared avatar video (the idle loop).

Face detection and face parsing happen once, in MuseTalk's avatar preparation
step, not here. That's what makes it real-time.

Runs on the GPU pod inside MuseTalk's own venv (see server/face/README.md).
"""

from __future__ import annotations

import glob
import math
import os
import pickle
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import librosa
import numpy as np
import torch
from einops import rearrange
from transformers import AutoFeatureExtractor, WhisperModel

# MuseTalk modules; service.py puts the MuseTalk checkout on sys.path and makes
# it the working directory (its loaders use paths like "models/sd-vae").
from musetalk.utils.blending import get_image_blending
from musetalk.utils.utils import load_all_model

FPS = 25
IN_RATE = 24_000  # PersonaPlex's rate; the agent forwards her audio unchanged
WHISPER_RATE = 16_000
FEATURES_PER_S = 50  # Whisper encoder output rate
FEATS_PER_FRAME = FEATURES_PER_S // FPS  # 2
PAD_FRAMES_LEFT = 2  # MuseTalk's audio_padding_length_left default
PAD_FRAMES_RIGHT = 2  # MuseTalk's audio_padding_length_right default
WINDOW_FEATS = 2 * (PAD_FRAMES_LEFT + PAD_FRAMES_RIGHT + 1)  # 10 features per frame
LEFT_FEATS = FEATS_PER_FRAME * PAD_FRAMES_LEFT  # 4: window starts 80 ms before the frame
SAMPLES_PER_FEATURE = IN_RATE // FEATURES_PER_S  # 480
CONTEXT_FEATS = int(4.0 * FEATURES_PER_S)  # 4 s of past audio as Whisper context


@dataclass
class Avatar:
    """The materials MuseTalk's preparation step writes to results/v15/avatars/<id>/."""

    frames: list[np.ndarray]  # BGR full frames of the idle loop (forward + reversed)
    coords: list[tuple[int, int, int, int]]  # face box per frame
    latents: list[torch.Tensor]  # VAE latents of each face crop
    masks: list[np.ndarray]  # blending masks
    mask_boxes: list[tuple[int, int, int, int]]


def _sorted_images(folder: Path) -> list[np.ndarray]:
    paths = glob.glob(str(folder / "*.png"))
    paths.sort(key=lambda p: int(Path(p).stem))
    images = [cv2.imread(p) for p in paths]
    if not images or any(img is None for img in images):
        raise RuntimeError(f"Couldn't read the avatar images in {folder}")
    return images  # type: ignore[return-value]


def load_avatar(avatar_dir: Path, device: torch.device) -> Avatar:
    if not (avatar_dir / "latents.pt").exists():
        raise FileNotFoundError(
            f"No prepared avatar at {avatar_dir}. Run the preparation step first (server/face/README.md)."
        )
    with open(avatar_dir / "coords.pkl", "rb") as f:
        coords = pickle.load(f)
    with open(avatar_dir / "mask_coords.pkl", "rb") as f:
        mask_boxes = pickle.load(f)
    return Avatar(
        frames=_sorted_images(avatar_dir / "full_imgs"),
        coords=coords,
        latents=torch.load(avatar_dir / "latents.pt", map_location=device),
        masks=_sorted_images(avatar_dir / "mask"),
        mask_boxes=mask_boxes,
    )


class MuseTalkStreamer:
    def __init__(
        self,
        avatar_dir: Path,
        device: str = "cuda",
        output_height: int | None = 720,
    ) -> None:
        self.device = torch.device(device)
        vae, unet, pe = load_all_model(
            unet_model_path=os.path.join("models", "musetalkV15", "unet.pth"),
            vae_type="sd-vae",
            unet_config=os.path.join("models", "musetalkV15", "musetalk.json"),
            device=self.device,
        )
        # fp16 everywhere, as in MuseTalk's realtime script.
        self.pe = pe.half().to(self.device)
        vae.vae = vae.vae.half().to(self.device)
        unet.model = unet.model.half().to(self.device)
        self.vae, self.unet = vae, unet
        self.dtype = unet.model.dtype
        self.timesteps = torch.tensor([0], device=self.device)

        self.feature_extractor = AutoFeatureExtractor.from_pretrained(os.path.join("models", "whisper"))
        self.whisper = WhisperModel.from_pretrained(os.path.join("models", "whisper"))
        self.whisper = self.whisper.to(device=self.device, dtype=self.dtype).eval()
        self.whisper.requires_grad_(False)

        self.avatar = load_avatar(avatar_dir, self.device)
        src_h, src_w = self.avatar.frames[0].shape[:2]
        if output_height and output_height < src_h:
            scale = output_height / src_h
            self.width, self.height = int(src_w * scale), output_height
        else:
            self.width, self.height = src_w, src_h
        # I420 needs even dimensions.
        self.width -= self.width % 2
        self.height -= self.height % 2

        self._lock = threading.Lock()  # push_audio runs on the event loop, render in a worker thread
        self.reset()

    # ---------- stream state ----------

    def reset(self) -> None:
        """Start a new conversation: frame 0 lines up with the first audio sample pushed."""
        with self._lock:
            self._pending: list[np.ndarray] = []
            self._audio = np.zeros(0, dtype=np.float32)  # rolling 24 kHz buffer
            self._audio_start = 0  # global sample index of _audio[0]
            self._received = 0  # total samples pushed
            self._next_frame = 0  # next frame index to render

    def push_audio(self, pcm: np.ndarray) -> None:
        """Lumi's audio, mono float32 in [-1, 1] at 24 kHz, in any chunk size."""
        with self._lock:
            self._pending.append(pcm.astype(np.float32, copy=False))
            self._received += len(pcm)

    def ready_frames(self) -> int:
        """How many new frames have all the audio they need."""
        with self._lock:
            return self._ready_locked()

    def _ready_locked(self) -> int:
        # Frame i needs features up to (exclusive) 2i - 4 + 10 = 2i + 6.
        available_feats = self._received // SAMPLES_PER_FEATURE
        last_renderable = (available_feats - (WINDOW_FEATS - LEFT_FEATS)) // FEATS_PER_FRAME
        return max(0, last_renderable + 1 - self._next_frame)

    # ---------- rendering (call from one worker thread) ----------

    @torch.no_grad()
    def render(self, max_frames: int) -> list[tuple[int, bytes]]:
        """Render up to max_frames ready frames. Returns (frame_index, I420 bytes) pairs."""
        with self._lock:
            n = min(self._ready_locked(), max_frames)
            if n == 0:
                return []
            if self._pending:
                self._audio = np.concatenate([self._audio, *self._pending])
                self._pending = []
            first = self._next_frame
            last = first + n - 1
            feat_lo = FEATS_PER_FRAME * first - LEFT_FEATS
            feat_hi = FEATS_PER_FRAME * last - LEFT_FEATS + WINDOW_FEATS
            min_feat = math.ceil(self._audio_start / SAMPLES_PER_FEATURE)
            win_feat0 = max(0, feat_lo - CONTEXT_FEATS, min_feat)
            lo = win_feat0 * SAMPLES_PER_FEATURE - self._audio_start
            hi = feat_hi * SAMPLES_PER_FEATURE - self._audio_start
            clip = self._audio[lo:hi].copy()

        feats = self._whisper_features(clip)  # [1, T, layers, 384], T at 50/s from win_feat0
        prompts = []
        for i in range(first, last + 1):
            g0 = FEATS_PER_FRAME * i - LEFT_FEATS
            window = torch.zeros(
                (WINDOW_FEATS, feats.shape[2], feats.shape[3]), device=self.device, dtype=feats.dtype
            )
            for k in range(WINDOW_FEATS):
                local = g0 + k - win_feat0
                if g0 + k >= 0 and 0 <= local < feats.shape[1]:
                    window[k] = feats[0, local]
            prompts.append(window)
        whisper_batch = rearrange(torch.stack(prompts), "b c h w -> b (c h) w")

        n_lat = len(self.avatar.latents)
        latent_batch = torch.cat([self.avatar.latents[i % n_lat] for i in range(first, last + 1)], dim=0)
        latent_batch = latent_batch.to(device=self.device, dtype=self.unet.model.dtype)
        audio_feature_batch = self.pe(whisper_batch)
        pred = self.unet.model(latent_batch, self.timesteps, encoder_hidden_states=audio_feature_batch).sample
        faces = self.vae.decode_latents(pred.to(device=self.device, dtype=self.vae.vae.dtype))  # BGR uint8

        out = [(i, self._compose(i, face)) for i, face in zip(range(first, last + 1), faces)]

        with self._lock:
            self._next_frame = last + 1
            # Drop audio that no future frame (or its Whisper context) needs.
            keep_from = max(
                self._audio_start,
                (FEATS_PER_FRAME * self._next_frame - LEFT_FEATS - CONTEXT_FEATS) * SAMPLES_PER_FEATURE,
            )
            drop = keep_from - self._audio_start
            if drop > 0:
                self._audio = self._audio[drop:]
                self._audio_start = keep_from
        return out

    def _whisper_features(self, clip_24k: np.ndarray) -> torch.Tensor:
        audio_16k = librosa.resample(clip_24k, orig_sr=IN_RATE, target_sr=WHISPER_RATE)
        mel = self.feature_extractor(audio_16k, return_tensors="pt", sampling_rate=WHISPER_RATE).input_features
        mel = mel.to(device=self.device, dtype=self.dtype)
        hidden = self.whisper.encoder(mel, output_hidden_states=True).hidden_states
        return torch.stack(hidden, dim=2)

    def _compose(self, i: int, face: np.ndarray) -> bytes:
        """Paste the generated mouth area onto idle-loop frame i, as MuseTalk's process_frames does."""
        a = self.avatar
        frame = a.frames[i % len(a.frames)].copy()
        x1, y1, x2, y2 = a.coords[i % len(a.coords)]
        if x2 > x1 and y2 > y1:  # (0, 0, 0, 0) marks frames where no face was found
            face = cv2.resize(face.astype(np.uint8), (x2 - x1, y2 - y1))
            frame = get_image_blending(
                frame, face, (x1, y1, x2, y2), a.masks[i % len(a.masks)], a.mask_boxes[i % len(a.mask_boxes)]
            )
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420).tobytes()

    def warmup(self) -> None:
        """Run one batch on silence so the first real frames aren't slowed by CUDA setup."""
        self.reset()
        self.push_audio(np.zeros(IN_RATE, dtype=np.float32))
        self.render(5)
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        self.reset()
