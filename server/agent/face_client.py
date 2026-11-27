"""Client for the face service (server/face/service.py): Lumi's audio in, video frames out.

Protocol (localhost WebSocket):
  server -> us  text   {"type": "ready", "width", "height", "fps", "format": "I420"}
  us -> server  binary int16 little-endian PCM, mono, 24 kHz (send continuously, silence too)
  server -> us  binary 4-byte little-endian frame index + I420 frame bytes
Frame i lines up with audio time i / fps since the first sample we sent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass

import aiohttp
import numpy as np

from voice_backend import Pcm

logger = logging.getLogger("face-client")


class FaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaceFormat:
    width: int
    height: int
    fps: int


class FaceStream:
    def __init__(self, ws_url: str, ready_timeout_s: float = 10.0) -> None:
        self._ws_url = ws_url
        self._ready_timeout_s = ready_timeout_s
        self._http: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self.format: FaceFormat | None = None

    async def start(self) -> FaceFormat:
        self._http = aiohttp.ClientSession()
        try:
            self._ws = await self._http.ws_connect(self._ws_url, max_msg_size=0)
            msg = await asyncio.wait_for(self._ws.receive(), timeout=self._ready_timeout_s)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            await self.aclose()
            raise FaceError(f"face service at {self._ws_url} isn't available ({e!r})") from e
        if msg.type != aiohttp.WSMsgType.TEXT:
            await self.aclose()
            raise FaceError(f"face service sent {msg.type.name} instead of its ready message")
        info = json.loads(msg.data)
        if info.get("format") != "I420":
            await self.aclose()
            raise FaceError(f"unsupported frame format {info.get('format')!r}")
        self.format = FaceFormat(width=int(info["width"]), height=int(info["height"]), fps=int(info["fps"]))
        logger.info("face service ready: %dx%d @ %d fps", self.format.width, self.format.height, self.format.fps)
        return self.format

    async def push_audio(self, pcm: Pcm) -> None:
        if self._ws is None or self._ws.closed:
            raise FaceError("face service connection is closed")
        samples = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype("<i2")
        await self._ws.send_bytes(samples.tobytes())

    async def frames(self) -> AsyncIterator[tuple[int, bytes]]:
        if self._ws is None:
            raise FaceError("start() must be called first")
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.BINARY and len(msg.data) > 4:
                (index,) = struct.unpack_from("<I", msg.data)
                yield index, msg.data[4:]
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                break
        raise FaceError("face service closed the connection")

    async def aclose(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._http is not None and not self._http.closed:
            await self._http.close()
        self._ws = None
        self._http = None
