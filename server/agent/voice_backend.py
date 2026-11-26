"""The interface every voice backend implements.

The LiveKit agent (main.py) only deals in raw PCM audio and text. A backend turns
the user's audio into the persona's audio. Today that's PersonaPlex
(personaplex_client.py). If PersonaPlex is ever blocked, the fallback pipeline
(faster-whisper -> Ollama -> Kokoro) can implement this same interface and
main.py won't change.

Audio format everywhere in this interface: mono float32 numpy arrays in [-1, 1]
at `SAMPLE_RATE` (24 kHz, PersonaPlex's native rate).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, Union

import numpy as np
import numpy.typing as npt

SAMPLE_RATE = 24_000

Pcm = npt.NDArray[np.float32]


@dataclass(frozen=True)
class AudioOut:
    """A chunk of the persona's voice."""

    pcm: Pcm


@dataclass(frozen=True)
class TextOut:
    """A piece of the text the persona is saying (a word or part of a word)."""

    text: str


BackendEvent = Union[AudioOut, TextOut]


class VoiceSession(Protocol):
    """One live conversation with the persona."""

    async def start(self) -> None:
        """Connect and get ready. Returns once the backend can take audio."""
        ...

    async def push_audio(self, pcm: Pcm) -> None:
        """Send the next chunk of the user's mic audio. Call it continuously,
        including during silence: a full-duplex model needs a steady stream."""
        ...

    def events(self) -> AsyncIterator[BackendEvent]:
        """Persona audio and text, in the order the backend produces them.
        Ends when the session closes."""
        ...

    async def aclose(self) -> None:
        """End the conversation and free the backend (PersonaPlex serves one at a time)."""
        ...
