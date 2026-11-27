"""How Lumi's voice (and face) leave the agent.

AudioOutput: voice only, published as soon as it arrives (Phase 2 behaviour).

VideoOutput: voice + MuseTalk face. Her audio goes to the face service, which
returns one video frame per 40 ms of audio, ~0.3 s later. The audio is held back
until its frame exists, then each frame is published together with exactly its
40 ms of audio, so lips and voice stay in sync. The cost: everything Lumi says
(and her reaction to being interrupted) reaches the user that much later.

If the face service fails mid-call, VideoOutput falls back to voice only.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import numpy as np
from livekit import rtc

from face_client import FaceError, FaceStream
from voice_backend import SAMPLE_RATE, Pcm

logger = logging.getLogger("persona-output")


def pcm_to_frame(pcm: Pcm) -> rtc.AudioFrame:
    """float32 in [-1, 1] -> LiveKit int16 frame at 24 kHz mono."""
    samples = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16)
    return rtc.AudioFrame(
        data=samples.tobytes(),
        sample_rate=SAMPLE_RATE,
        num_channels=1,
        samples_per_channel=samples.shape[-1],
    )


class AudioOutput:
    def __init__(self, audio_source: rtc.AudioSource) -> None:
        self._source = audio_source

    async def push(self, pcm: Pcm) -> None:
        await self._source.capture_frame(pcm_to_frame(pcm))

    async def run(self) -> None:
        await asyncio.Event().wait()  # nothing to do in the background

    def delay_s(self) -> float:
        return 0.0


class VideoOutput:
    def __init__(
        self,
        face: FaceStream,
        audio_source: rtc.AudioSource,
        video_source: rtc.VideoSource,
        on_failure: Callable[[], Awaitable[None]],
    ) -> None:
        assert face.format is not None, "start the face stream first"
        self._face = face
        self._fmt = face.format
        self._audio_source = audio_source
        self._samples_per_frame = SAMPLE_RATE // self._fmt.fps  # 960 at 25 fps
        self._av = rtc.AVSynchronizer(
            audio_source=audio_source,
            video_source=video_source,
            video_fps=self._fmt.fps,
            video_queue_size_ms=200,
        )
        self._held = np.zeros(0, dtype=np.float32)  # audio waiting for its frame
        self._failed = False
        self._on_failure = on_failure

    async def push(self, pcm: Pcm) -> None:
        if self._failed:
            await self._audio_source.capture_frame(pcm_to_frame(pcm))
            return
        self._held = np.concatenate([self._held, pcm])
        try:
            await self._face.push_audio(pcm)
        except FaceError as e:
            await self._fail(e)

    async def run(self) -> None:
        expected = 0
        try:
            async for index, data in self._face.frames():
                if index != expected:
                    logger.warning("face frame %d arrived, expected %d", index, expected)
                expected = index + 1
                frame = rtc.VideoFrame(self._fmt.width, self._fmt.height, rtc.VideoBufferType.I420, data)
                chunk = self._held[: self._samples_per_frame]
                self._held = self._held[self._samples_per_frame :]
                if len(chunk) < self._samples_per_frame:  # shouldn't happen; keep timing anyway
                    chunk = np.pad(chunk, (0, self._samples_per_frame - len(chunk)))
                await self._av.push(frame)
                await self._av.push(pcm_to_frame(chunk))
        except FaceError as e:
            await self._fail(e)
        await asyncio.Event().wait()  # voice-only from here on; keep the task alive

    async def _fail(self, error: Exception) -> None:
        if self._failed:
            return
        self._failed = True
        logger.error("face service failed, continuing with voice only: %s", error)
        held, self._held = self._held, np.zeros(0, dtype=np.float32)
        if len(held):
            await self._audio_source.capture_frame(pcm_to_frame(held))
        await self._on_failure()

    def delay_s(self) -> float:
        """How far Lumi's published voice lags behind PersonaPlex right now."""
        return 0.0 if self._failed else len(self._held) / SAMPLE_RATE

    async def aclose(self) -> None:
        await self._av.aclose()
        await self._face.aclose()
