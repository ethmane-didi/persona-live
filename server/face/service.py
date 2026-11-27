"""Face service: a localhost WebSocket that turns Lumi's audio into lip-synced video.

The LiveKit agent connects to ws://127.0.0.1:8999/stream, then:

  server -> agent  text   {"type": "ready", "width": W, "height": H, "fps": 25, "format": "I420"}
  agent  -> server binary Lumi's audio: int16 little-endian PCM, mono, 24 kHz, any chunk size.
                          Send it continuously (silence too): frame i is lined up
                          with audio time i * 40 ms since the first sample.
  server -> agent  binary 4-byte little-endian frame index + one I420 frame (W*H*3/2 bytes)

Frames come out in order, in batches (default 5 = 200 ms), each one roughly
280 ms after its audio arrived (the batch + MuseTalk's 80 ms look-ahead + compute).
The agent holds the audio back by the same amount so lips and voice stay in sync.

One conversation at a time, like moshi.server. Runs in MuseTalk's venv:
    python service.py --avatar lumi
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from aiohttp import WSMsgType, web

MUSETALK_DIR = Path(os.getenv("MUSETALK_DIR", "/workspace/MuseTalk"))
# MuseTalk's loaders use relative paths ("models/sd-vae", ...), so run from its checkout.
sys.path.insert(0, str(MUSETALK_DIR))
os.chdir(MUSETALK_DIR)

from musetalk_stream import FPS, MuseTalkStreamer  # noqa: E402

logger = logging.getLogger("face-service")


class FaceService:
    def __init__(self, streamer: MuseTalkStreamer, batch_frames: int) -> None:
        self.streamer = streamer
        self.batch_frames = batch_frames
        self.lock = asyncio.Lock()
        # One worker thread: render() calls must not overlap, and keeping the GPU
        # work off the event loop lets audio keep arriving while a batch renders.
        self.executor = ThreadPoolExecutor(max_workers=1)

    async def handle_stream(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=0)
        await ws.prepare(request)
        if self.lock.locked():
            logger.info("another conversation is using the face; waiting")
        async with self.lock:
            await self._run(ws)
        return ws

    async def _run(self, ws: web.WebSocketResponse) -> None:
        s = self.streamer
        s.reset()
        await ws.send_str(
            json.dumps({"type": "ready", "width": s.width, "height": s.height, "fps": FPS, "format": "I420"})
        )
        logger.info("conversation started (%dx%d @ %d fps)", s.width, s.height, FPS)
        loop = asyncio.get_running_loop()
        closed = asyncio.Event()
        stats = {"frames": 0, "render_s": 0.0, "audio_s": 0.0}

        async def receive_audio() -> None:
            try:
                async for msg in ws:
                    if msg.type == WSMsgType.BINARY:
                        pcm = np.frombuffer(msg.data, dtype="<i2").astype(np.float32) / 32768.0
                        s.push_audio(pcm)
                        stats["audio_s"] += len(pcm) / 24_000
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                        break
            finally:
                closed.set()

        async def render_frames() -> None:
            while not closed.is_set():
                if s.ready_frames() < self.batch_frames:
                    await asyncio.sleep(0.005)
                    continue
                t0 = time.perf_counter()
                frames = await loop.run_in_executor(self.executor, s.render, self.batch_frames)
                stats["render_s"] += time.perf_counter() - t0
                for index, data in frames:
                    if ws.closed:
                        return
                    await ws.send_bytes(struct.pack("<I", index) + data)
                stats["frames"] += len(frames)

        async def log_stats() -> None:
            # Real-time needs render time per frame under 40 ms (1000 ms / 25 fps).
            while not closed.is_set():
                await asyncio.sleep(10)
                if stats["frames"]:
                    per_frame_ms = 1000 * stats["render_s"] / stats["frames"]
                    logger.info(
                        "frames %d, audio %.1f s, render %.1f ms/frame (%.1fx real time)",
                        stats["frames"], stats["audio_s"], per_frame_ms, 40.0 / per_frame_ms,
                    )

        tasks = [asyncio.create_task(t()) for t in (receive_audio, render_frames, log_stats)]
        await closed.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("conversation ended after %d frames", stats["frames"])


def main() -> None:
    parser = argparse.ArgumentParser(description="MuseTalk face service for the LiveKit agent")
    parser.add_argument("--avatar", default=os.getenv("FACE_AVATAR", "lumi"),
                        help="avatar id prepared under MuseTalk's results/v15/avatars/ (default: lumi)")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: localhost only)")
    parser.add_argument("--port", type=int, default=8999)
    parser.add_argument("--batch-frames", type=int, default=5,
                        help="frames per render batch; bigger = more efficient, more delay (default 5 = 200 ms)")
    parser.add_argument("--output-height", type=int, default=720, help="downscale frames to this height")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    avatar_dir = MUSETALK_DIR / "results" / "v15" / "avatars" / args.avatar
    logger.info("loading MuseTalk and avatar %s", avatar_dir)
    streamer = MuseTalkStreamer(avatar_dir, output_height=args.output_height)
    logger.info("warming up")
    streamer.warmup()

    service = FaceService(streamer, args.batch_frames)
    app = web.Application()
    app.router.add_get("/stream", service.handle_stream)
    logger.info("face service ready on ws://%s:%d/stream", args.host, args.port)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
