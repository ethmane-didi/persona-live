"""LiveKit agent: bridges a LiveKit room to PersonaPlex, MuseTalk and a vision model.

    browser mic ──WebRTC──▶ LiveKit ──▶ agent ──ws://127.0.0.1:8998──▶ moshi.server (PersonaPlex)
    browser camera ───────▶ LiveKit ──▶ agent ──http://127.0.0.1:8997──▶ vision service (once, at the start)
    browser ◀── Lumi's voice + video ── agent ◀──ws://127.0.0.1:8999──── face service (MuseTalk)

It joins each new room and waits for the user. If their camera is on, it grabs one
frame and asks the vision service to describe it; that sentence is added to the
runtime prompt from prompts/persona.md. Then it opens one PersonaPlex conversation
and streams audio both ways at the same time. It does no turn-taking or
voice-activity detection: PersonaPlex is full-duplex and handles interruptions
(barge-in) inside the model.

Lumi's voice also goes to the face service, which returns lip-synced video. The
voice is held back until its video frame exists, so they stay in sync. Every
GPU service is optional: without the face service she's voice-only, without the
vision service she can't see the user.

Run on the GPU pod (see server/agent/README.md):
    python main.py dev
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli
from livekit.agents.types import (
    ATTRIBUTE_AGENT_STATE,
    ATTRIBUTE_TRANSCRIPTION_FINAL,
    ATTRIBUTE_TRANSCRIPTION_SEGMENT_ID,
    ATTRIBUTE_TRANSCRIPTION_TRACK_ID,
    TOPIC_TRANSCRIPTION,
)

from face_client import FaceError, FaceStream
from output import AudioOutput, VideoOutput
from personaplex_client import PersonaPlexError, PersonaPlexSession
from vision_client import capture_camera_frame, describe_frame, prompt_with_vision
from voice_backend import SAMPLE_RATE, AudioOut, Pcm, TextOut, VoiceSession

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")  # LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET + the settings below

# Reuse the Phase 1 prompt loader so the agent and the offline test send the same prompt.
sys.path.insert(0, str(REPO_ROOT / "server" / "personaplex"))
from runtime_prompt import load_runtime_prompt  # noqa: E402

PERSONAPLEX_WS_URL = os.getenv("PERSONAPLEX_WS_URL", "ws://127.0.0.1:8998/api/chat")
PERSONAPLEX_VOICE = os.getenv("PERSONAPLEX_VOICE", "NATF2.pt")  # "Natural female 2" preset
PERSONA_PROMPT_PATH = REPO_ROOT / os.getenv("PERSONA_PROMPT_PATH", "prompts/persona.md")
# Optional GPU services on the same pod. Set to an empty string to turn one off.
FACE_WS_URL = os.getenv("FACE_WS_URL", "ws://127.0.0.1:8999/stream")
VISION_URL = os.getenv("VISION_URL", "http://127.0.0.1:8997/describe")
# How long to wait for a camera frame when the user joins (camera off = no frames).
CAMERA_WAIT_S = 3.0

# If the mic sends nothing for this long (user muted, network blip), feed the model
# silence. PersonaPlex only moves forward when it receives audio, so without this
# Lumi would freeze mid-sentence whenever the user mutes.
MIC_GAP_FILL_S = 0.2
# How much of Lumi's voice LiveKit may buffer before playback. Small = interruptions
# take effect quickly; too small = choppy audio on hiccups.
OUTPUT_QUEUE_MS = 400
# Lumi's captions: a pause this long in her text ends one caption segment.
CAPTION_PAUSE_S = 1.0

logger = logging.getLogger("persona-agent")
server = AgentServer()


def frame_to_pcm(frame: rtc.AudioFrame) -> Pcm:
    """LiveKit int16 frame -> float32 in [-1, 1]."""
    return np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0


async def see_user(user: rtc.RemoteParticipant) -> tuple[str | None, bool]:
    """One camera frame -> (description or None, whether the camera was on)."""
    cameras = [
        pub for pub in user.track_publications.values() if pub.source == rtc.TrackSource.SOURCE_CAMERA
    ]
    if not cameras:
        logger.info("the user's camera is off")
        return None, False
    if not VISION_URL:
        return None, True
    frame = await capture_camera_frame(user, wait_s=CAMERA_WAIT_S)
    # One frame is all we use, so stop receiving their video for the rest of the call.
    for pub in cameras:
        pub.set_subscribed(False)
    if frame is None:
        logger.info("the user's camera is on, but no frame arrived in time")
        return None, True
    description = await describe_frame(frame, VISION_URL)
    logger.info("Lumi sees: %s", description or "(vision service unavailable)")
    return description, True


class CaptionStreamer:
    """Publishes Lumi's words as LiveKit transcription text streams, the format the
    Agents Playground and @livekit/components-react show as live captions.
    PersonaPlex sends no end-of-turn signal, so a pause in her text ends a segment."""

    def __init__(self, participant: rtc.LocalParticipant, track_sid: str) -> None:
        self._participant = participant
        self._track_sid = track_sid
        self._writer: rtc.TextStreamWriter | None = None
        self._close_timer: asyncio.TimerHandle | None = None

    async def add(self, text: str) -> None:
        try:
            if self._writer is None:
                self._writer = await self._participant.stream_text(
                    topic=TOPIC_TRANSCRIPTION,
                    attributes={
                        ATTRIBUTE_TRANSCRIPTION_FINAL: "false",
                        ATTRIBUTE_TRANSCRIPTION_TRACK_ID: self._track_sid,
                        ATTRIBUTE_TRANSCRIPTION_SEGMENT_ID: f"lumi_{uuid.uuid4().hex[:12]}",
                    },
                )
            await self._writer.write(text)
        except Exception as e:  # captions are nice-to-have; never let them break the audio
            logger.warning("couldn't publish caption: %s", e)
            return
        if self._close_timer is not None:
            self._close_timer.cancel()
        self._close_timer = asyncio.get_running_loop().call_later(
            CAPTION_PAUSE_S, lambda: asyncio.create_task(self.flush())
        )

    async def flush(self) -> None:
        writer, self._writer = self._writer, None
        if writer is None:
            return
        try:
            await writer.aclose(
                attributes={
                    ATTRIBUTE_TRANSCRIPTION_FINAL: "true",
                    ATTRIBUTE_TRANSCRIPTION_TRACK_ID: self._track_sid,
                }
            )
        except Exception as e:
            logger.warning("couldn't close caption stream: %s", e)


async def set_agent_state(ctx: JobContext, state: str) -> None:
    """Shown by the Playground / LiveKit UI components ("initializing", "listening", ...)."""
    await ctx.room.local_participant.set_attributes({ATTRIBUTE_AGENT_STATE: state})


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    # Audio and video: the user's camera feeds the "describe you at the start" step.
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
    await set_agent_state(ctx, "initializing")
    user = await ctx.wait_for_participant()
    logger.info("room %s: user %s joined", ctx.room.name, user.identity)

    description, camera_on = await see_user(user)
    text_prompt = prompt_with_vision(load_runtime_prompt(PERSONA_PROMPT_PATH), description, camera_on)
    voice: VoiceSession = PersonaPlexSession(PERSONAPLEX_WS_URL, text_prompt, PERSONAPLEX_VOICE)
    # Always release PersonaPlex when the job ends: it serves one conversation at a time.
    ctx.add_shutdown_callback(voice.aclose)

    @ctx.room.on("participant_disconnected")
    def _on_left(participant: rtc.RemoteParticipant) -> None:
        if participant.identity == user.identity:
            logger.info("user left, ending the conversation")
            ctx.shutdown("user left")

    # Lumi's voice goes out as an audio track at PersonaPlex's native 24 kHz;
    # LiveKit resamples for the browser.
    source = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=OUTPUT_QUEUE_MS)
    track = rtc.LocalAudioTrack.create_audio_track("lumi-voice", source)
    publication = await ctx.room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )
    captions = CaptionStreamer(ctx.room.local_participant, publication.sid)

    try:
        await voice.start()
    except PersonaPlexError as e:
        logger.error("%s", e)
        ctx.shutdown(f"PersonaPlex unavailable: {e}")
        return

    # Lumi's face, if the face service is running; otherwise she's voice-only.
    output: AudioOutput | VideoOutput = AudioOutput(source)
    if FACE_WS_URL:
        face = FaceStream(FACE_WS_URL)
        try:
            fmt = await face.start()
            video_source = rtc.VideoSource(fmt.width, fmt.height)
            video_track = rtc.LocalVideoTrack.create_video_track("lumi-face", video_source)
            video_pub = await ctx.room.local_participant.publish_track(
                video_track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
            )

            async def drop_video() -> None:
                # The page falls back to its voice-only tile when the track goes away.
                await ctx.room.local_participant.unpublish_track(video_pub.sid)

            output = VideoOutput(face, source, video_source, on_failure=drop_video)
            ctx.add_shutdown_callback(output.aclose)
        except FaceError as e:
            logger.warning("%s; Lumi is voice-only this time", e)
    await set_agent_state(ctx, "listening")

    # The user's mic, resampled by LiveKit to 24 kHz mono.
    mic = rtc.AudioStream.from_participant(
        participant=user,
        track_source=rtc.TrackSource.SOURCE_MICROPHONE,
        sample_rate=SAMPLE_RATE,
        num_channels=1,
    )
    mic_queue: asyncio.Queue[Pcm] = asyncio.Queue()
    stats = {"mic_s": 0.0, "fill_s": 0.0, "out_s": 0.0}

    async def read_mic() -> None:
        async for event in mic:
            mic_queue.put_nowait(frame_to_pcm(event.frame))

    async def send_mic() -> None:
        silence = np.zeros(int(SAMPLE_RATE * MIC_GAP_FILL_S), dtype=np.float32)
        while True:
            try:
                pcm = await asyncio.wait_for(mic_queue.get(), timeout=MIC_GAP_FILL_S)
                stats["mic_s"] += pcm.shape[-1] / SAMPLE_RATE
            except asyncio.TimeoutError:
                pcm = silence
                stats["fill_s"] += MIC_GAP_FILL_S
            await voice.push_audio(pcm)

    async def play_persona() -> None:
        async for event in voice.events():
            if isinstance(event, AudioOut):
                stats["out_s"] += event.pcm.shape[-1] / SAMPLE_RATE
                await output.push(event.pcm)
            elif isinstance(event, TextOut):
                await captions.add(event.text)
        await captions.flush()

    async def log_stats() -> None:
        # Every 10 s: audio sent vs received. They should grow at the same rate;
        # if "lumi" falls behind "mic", the GPU isn't keeping up with real time.
        # "face delay" is how long her voice is held back for the video (0 when voice-only).
        while True:
            await asyncio.sleep(10)
            logger.info(
                "audio so far: mic %.1f s (+%.1f s silence fill), lumi %.1f s, "
                "playback queue %.0f ms, face delay %.0f ms",
                stats["mic_s"], stats["fill_s"], stats["out_s"],
                source.queued_duration * 1000, output.delay_s() * 1000,
            )

    tasks = [asyncio.create_task(t()) for t in (read_mic, send_mic, play_persona, output.run, log_stats)]
    try:
        # play_persona ends when PersonaPlex closes the connection; any task
        # failing also ends the conversation.
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task.exception() is not None:
                logger.error("conversation task failed", exc_info=task.exception())
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await mic.aclose()
        ctx.shutdown("conversation ended")


if __name__ == "__main__":
    cli.run_app(server)
