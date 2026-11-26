"""Talks to a running PersonaPlex server (`python -m moshi.server`) over its WebSocket.

This is the same protocol NVIDIA's browser UI uses (moshi/server.py, handle_chat):

  1. Open ws://<host>:8998/api/chat?text_prompt=...&voice_prompt=NATF2.pt
  2. The server feeds the voice + text prompt through the model, then sends b"\\x00"
     (the handshake). Don't send audio before it arrives.
  3. From then on both sides stream at the same time (full-duplex). Binary messages,
     first byte = kind:
        0x01 + Ogg-Opus pages, 24 kHz mono  (both directions: user mic in, persona voice out)
        0x02 + UTF-8 text piece             (server -> us: what the persona is saying)
     There's no turn-taking message. Barge-in happens inside the model: it hears
     the user while it talks and decides to stop.

The server handles one conversation at a time (an asyncio.Lock). A second
connection waits until the first one closes, so always call aclose().
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import aiohttp
import numpy as np
import sphn

from voice_backend import SAMPLE_RATE, AudioOut, BackendEvent, Pcm, TextOut

logger = logging.getLogger("personaplex-client")

KIND_HANDSHAKE = 0x00
KIND_AUDIO = 0x01
KIND_TEXT = 0x02


class PersonaPlexError(RuntimeError):
    pass


class PersonaPlexSession:
    """One conversation with PersonaPlex. Implements voice_backend.VoiceSession."""

    def __init__(
        self,
        ws_url: str,
        text_prompt: str,
        voice_prompt: str,
        handshake_timeout_s: float = 90.0,
    ) -> None:
        self._ws_url = ws_url
        self._text_prompt = text_prompt
        self._voice_prompt = voice_prompt
        self._handshake_timeout_s = handshake_timeout_s
        self._http: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        # Ogg-Opus encoder for the user's mic and decoder for the persona's voice.
        # sphn is the same library the server uses, so the formats match exactly.
        self._encoder = sphn.OpusStreamWriter(SAMPLE_RATE)
        self._decoder = sphn.OpusStreamReader(SAMPLE_RATE)

    async def start(self) -> None:
        self._http = aiohttp.ClientSession()
        params = {"text_prompt": self._text_prompt, "voice_prompt": self._voice_prompt}
        try:
            self._ws = await self._http.ws_connect(self._ws_url, params=params, autoping=True)
        except aiohttp.ClientError as e:
            await self.aclose()
            raise PersonaPlexError(
                f"Can't reach PersonaPlex at {self._ws_url} ({e}). Is `python -m moshi.server` running?"
            ) from e

        logger.info("connected to PersonaPlex, waiting for it to process the prompts")
        try:
            msg = await asyncio.wait_for(self._ws.receive(), timeout=self._handshake_timeout_s)
        except asyncio.TimeoutError as e:
            await self.aclose()
            raise PersonaPlexError(
                f"No handshake from PersonaPlex after {self._handshake_timeout_s:.0f} s. "
                "It may be busy with another conversation (it serves one at a time)."
            ) from e

        if msg.type != aiohttp.WSMsgType.BINARY or msg.data[:1] != bytes([KIND_HANDSHAKE]):
            await self.aclose()
            # The server closes the socket without a handshake when, for example,
            # the voice file doesn't exist in its voice folder.
            raise PersonaPlexError(
                f"PersonaPlex closed the connection instead of handshaking (got {msg.type.name}). "
                f"Check the server log; is voice_prompt '{self._voice_prompt}' a valid voice file?"
            )
        logger.info("PersonaPlex handshake received; conversation is live")

    async def push_audio(self, pcm: Pcm) -> None:
        if self._ws is None or self._ws.closed:
            return
        self._encoder.append_pcm(np.ascontiguousarray(pcm, dtype=np.float32))
        pages = self._encoder.read_bytes()
        if pages:
            await self._ws.send_bytes(bytes([KIND_AUDIO]) + pages)

    async def events(self) -> AsyncIterator[BackendEvent]:
        if self._ws is None:
            raise PersonaPlexError("start() must be called first")
        async for msg in self._ws:
            if msg.type != aiohttp.WSMsgType.BINARY:
                if msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break
                continue
            data: bytes = msg.data
            if not data:
                continue
            kind, payload = data[0], data[1:]
            if kind == KIND_AUDIO:
                self._decoder.append_bytes(payload)
                pcm = self._decoder.read_pcm()
                if pcm.shape[-1] > 0:
                    yield AudioOut(pcm=pcm.astype(np.float32, copy=False))
            elif kind == KIND_TEXT:
                yield TextOut(text=payload.decode("utf-8", errors="replace"))
            else:
                logger.debug("ignoring message kind %d from PersonaPlex", kind)
        logger.info("PersonaPlex connection closed")

    async def aclose(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._http is not None and not self._http.closed:
            await self._http.close()
        self._ws = None
        self._http = None
