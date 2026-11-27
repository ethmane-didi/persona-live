"""'Describe you at the start': one camera frame -> one sentence for Lumi's role prompt.

PersonaPlex only takes text once, as the role prompt when the conversation
starts. So the agent grabs a frame from the user's camera as they join, asks the
vision service (server/vision/service.py) to describe it, and adds that line to
the prompt. Lumi can't notice changes later in the call; the prompt says so.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
from livekit import rtc

logger = logging.getLogger("vision-client")

# The first frames from a camera that just turned on are often dark while
# auto-exposure settles, so keep reading for a moment and use the latest one.
SETTLE_S = 0.8


async def capture_camera_frame(participant: rtc.RemoteParticipant, wait_s: float = 3.0) -> rtc.VideoFrame | None:
    """One RGB24 frame from the participant's camera, or None if it's off / doesn't arrive in time."""
    stream = rtc.VideoStream.from_participant(
        participant=participant,
        track_source=rtc.TrackSource.SOURCE_CAMERA,
        format=rtc.VideoBufferType.RGB24,
    )
    latest: rtc.VideoFrame | None = None

    async def read() -> None:
        nonlocal latest
        first_at: float | None = None
        async for event in stream:
            latest = event.frame
            first_at = first_at or time.monotonic()
            if time.monotonic() - first_at >= SETTLE_S:
                return

    try:
        await asyncio.wait_for(read(), timeout=wait_s + SETTLE_S)
    except asyncio.TimeoutError:
        pass  # camera off (no frames), or still settling: use whatever arrived
    finally:
        await stream.aclose()
    return latest


async def describe_frame(frame: rtc.VideoFrame, url: str, timeout_s: float = 8.0) -> str | None:
    """Ask the vision service for a one-sentence description. None if it's unavailable."""
    if frame.type != rtc.VideoBufferType.RGB24:
        frame = frame.convert(rtc.VideoBufferType.RGB24)
    params = {"width": str(frame.width), "height": str(frame.height)}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as http:
            async with http.post(url, params=params, data=bytes(frame.data)) as res:
                body = await res.json()
                if res.status != 200:
                    logger.warning("vision service error %d: %s", res.status, body)
                    return None
                description = str(body.get("description", "")).strip()
                return description or None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        logger.warning("vision service at %s unavailable: %r", url, e)
        return None


def prompt_with_vision(base_prompt: str, description: str | None, camera_on: bool) -> str:
    """Add what Lumi saw (or that she can't see) to the role prompt. Kept short:
    PersonaPlex was trained on short prompts."""
    if description:
        return (
            f"{base_prompt} When the call started you saw the person through their camera: {description} "
            "That was one moment only; you can't see what they do now, so never pretend to."
        )
    if camera_on:
        return f"{base_prompt} The person's camera is on, but you can't see the picture."
    return f"{base_prompt} You can't see the person: their camera is off."
