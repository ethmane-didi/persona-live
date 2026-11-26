"""Check the PersonaPlex connection without LiveKit (run on the GPU pod).

Uses the same PersonaPlexSession as the agent: connects to moshi.server, sends a
recorded question (or silence) in real time, and reports what comes back.

    python check_personaplex.py                                  # 8 s of silence
    python check_personaplex.py --wav /workspace/personaplex/assets/test/input_assistant.wav
    python check_personaplex.py --wav ... --out /workspace/agent_check.wav   # save Lumi's reply

Passes when the handshake arrives and Lumi's audio comes back at about real-time speed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from personaplex_client import PersonaPlexSession
from voice_backend import SAMPLE_RATE, AudioOut, Pcm, TextOut

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "server" / "personaplex"))
from runtime_prompt import load_runtime_prompt  # noqa: E402

CHUNK_S = 0.08  # one PersonaPlex frame (80 ms)


def read_wav_24k_mono(path: Path) -> Pcm:
    """Read a 16-bit PCM WAV and convert it to 24 kHz mono float32."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise SystemExit(f"{path}: only 16-bit PCM WAV is supported")
        rate, channels = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:  # simple linear resample; fine for a connectivity check
        n_out = int(len(data) * SAMPLE_RATE / rate)
        data = np.interp(np.linspace(0, len(data) - 1, n_out), np.arange(len(data)), data).astype(np.float32)
    return data


def write_wav(path: Path, pcm: Pcm) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((np.clip(pcm, -1, 1) * 32767).astype(np.int16).tobytes())


async def run(args: argparse.Namespace) -> int:
    ws_url = os.getenv("PERSONAPLEX_WS_URL", "ws://127.0.0.1:8998/api/chat")
    voice_name = os.getenv("PERSONAPLEX_VOICE", "NATF2.pt")
    prompt = load_runtime_prompt(REPO_ROOT / os.getenv("PERSONA_PROMPT_PATH", "prompts/persona.md"))
    audio_in = read_wav_24k_mono(Path(args.wav)) if args.wav else np.zeros(int(8 * SAMPLE_RATE), np.float32)
    # A few seconds of silence after the question so Lumi has time to answer.
    audio_in = np.concatenate([audio_in, np.zeros(int(args.tail * SAMPLE_RATE), np.float32)])

    print(f"PersonaPlex: {ws_url}  voice: {voice_name}")
    print(f"Prompt: {prompt[:90]}...")
    session = PersonaPlexSession(ws_url, prompt, voice_name)
    t0 = time.monotonic()
    await session.start()
    print(f"Handshake after {time.monotonic() - t0:.1f} s")

    out_chunks: list[Pcm] = []
    text: list[str] = []

    async def send() -> None:
        step = int(CHUNK_S * SAMPLE_RATE)
        start = time.monotonic()
        for i in range(0, len(audio_in), step):
            await session.push_audio(audio_in[i : i + step])
            # pace like a real mic: never send ahead of the wall clock
            await asyncio.sleep(max(0.0, start + (i + step) / SAMPLE_RATE - time.monotonic()))
        await asyncio.sleep(1.0)  # let the last replies arrive
        await session.aclose()

    async def receive() -> None:
        async for event in session.events():
            if isinstance(event, AudioOut):
                out_chunks.append(event.pcm)
            elif isinstance(event, TextOut):
                text.append(event.text)

    t1 = time.monotonic()
    await asyncio.gather(send(), receive())
    sent_s = len(audio_in) / SAMPLE_RATE
    out = np.concatenate(out_chunks) if out_chunks else np.zeros(0, np.float32)
    got_s = len(out) / SAMPLE_RATE
    ratio = got_s / sent_s if sent_s else 0.0

    print(f"Sent {sent_s:.1f} s of audio in {time.monotonic() - t1:.1f} s, got {got_s:.1f} s back ({ratio:.0%})")
    print(f"Lumi said: {''.join(text).strip() or '(no words)'}")
    if args.out and got_s > 0:
        write_wav(Path(args.out), out)
        print(f"Saved her audio to {args.out}")

    # The model makes one 80 ms frame per 80 ms of input, minus a little at start/end.
    if ratio >= 0.85:
        print("PASS: handshake OK and audio comes back at real-time speed.")
        return 0
    print("FAIL: too little audio came back. The GPU may be too slow, or the stream broke (check the moshi.server log).")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wav", help="16-bit WAV to send as the user's voice (default: 8 s of silence)")
    parser.add_argument("--tail", type=float, default=4.0, help="seconds of silence after the WAV (default 4)")
    parser.add_argument("--out", help="save Lumi's audio to this WAV file")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
