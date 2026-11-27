# server/agent: LiveKit agent

Joins each new LiveKit room, waits for the user, and bridges them to the GPU services
running on the same pod:

```text
browser mic ────▶ LiveKit Cloud ──▶ agent ──ws://127.0.0.1:8998──▶ moshi.server (PersonaPlex)
browser camera ─▶ LiveKit Cloud ──▶ agent ──http://127.0.0.1:8997─▶ vision service (once, at the start)
browser ◀── Lumi's voice + video ── agent ◀──ws://127.0.0.1:8999─── face service (MuseTalk)
```

1. If your camera is on when you join, one frame is described by the vision service and the sentence is added to Lumi's role prompt. (She sees that one moment only; PersonaPlex takes text only at the start.)
2. Your mic (resampled by LiveKit to 24 kHz mono) is encoded to Ogg-Opus and streamed to PersonaPlex.
3. Lumi's voice comes back as Ogg-Opus and is decoded. It also goes to the face service, which returns one lip-synced video frame per 40 ms.
4. Her voice is held back until its frame exists, then voice and video are published together so they stay in sync (~0.3 s extra delay).
5. Her words are published as live captions (LiveKit transcription streams).

The face and vision services are optional: without the face service she's voice-only
(no extra delay); without the vision service she can't see you. Set `FACE_WS_URL` or
`VISION_URL` to an empty string to turn one off on purpose.

There's **no turn-taking or voice-activity detection** in the agent. PersonaPlex is
full-duplex: it hears you while it talks and handles interruptions (barge-in) itself.
That's also why the agent doesn't use LiveKit's `AgentSession`, which is built around
speech-to-text → LLM → text-to-speech turns.

| File | What it does |
|---|---|
| `main.py` | The LiveKit side: joins the room, the camera snapshot, moves audio between LiveKit and the backend, publishes captions |
| `personaplex_client.py` | The PersonaPlex WebSocket protocol (handshake, Ogg-Opus audio, text) |
| `output.py` | How Lumi leaves the agent: voice only, or voice + face video held in sync (falls back to voice only if the face service fails) |
| `face_client.py` | Client for the face service (`server/face/`) |
| `vision_client.py` | Grabs one camera frame, asks the vision service (`server/vision/`) to describe it, builds the prompt line |
| `voice_backend.py` | The interface a backend implements. The fallback pipeline (faster-whisper → Ollama → Kokoro) can plug in here without touching `main.py` |
| `check_personaplex.py` | Tests the PersonaPlex connection without LiveKit: sends a recorded question, prints what Lumi said, PASS/FAIL on real-time speed |
| `requirements.txt` | Agent dependencies (no torch; the model runs inside moshi.server) |

- **Persona:** the "Runtime prompt" section of `prompts/persona.md`, loaded with `server/personaplex/runtime_prompt.py`. A new conversation picks up edits; no restart needed.
- **Voice:** `PERSONAPLEX_VOICE` in `.env` (default `NATF2.pt`, "Natural female 2").
- **One conversation at a time:** moshi.server serves one connection at a time. A second room waits up to 90 s for the first to end, then gives up.

## Setup and run (on the GPU pod)

Needs Phase 1 working (`runpod-setup.sh`) and a LiveKit Cloud project.

```bash
cd /workspace/persona-live
bash server/scripts/agent-setup.sh        # agent venv at /root/venvs/agent; re-run after a pod restart
```

Put your LiveKit credentials in `/workspace/persona-live/.env`:
```
LIVEKIT_URL=wss://<your-project>.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
```

Terminal 1, PersonaPlex (`--static none` turns off NVIDIA's web UI; the agent is its client now):
```bash
source /workspace/personaplex.env
cd /workspace/personaplex && python -m moshi.server --port 8998 --static none
```

> ⚠️ moshi.server always listens on **all** interfaces: `server.py` never passes `--host`
> to `web.run_app`. So while port `8998` is exposed on the pod, anyone with the
> `https://<pod>-8998.proxy.runpod.net` URL can still open a conversation and block the
> agent (it serves one at a time). Once you no longer need NVIDIA's UI, remove `8998`
> from the pod's exposed ports (RunPod → pod → Edit). The agent reaches it on localhost
> either way.

Check the connection without LiveKit (any terminal, after moshi.server is up):
```bash
source /root/venvs/agent/bin/activate
cd /workspace/persona-live/server/agent
python check_personaplex.py --wav /workspace/personaplex/assets/test/input_assistant.wav --out /workspace/agent_check.wav
```

Terminal 2, the agent:
```bash
source /root/venvs/agent/bin/activate
cd /workspace/persona-live/server/agent && python main.py dev
```

Test it from the LiveKit **Agents Playground** (sign in with your LiveKit Cloud account,
pick the project, connect), or from the Next.js page (`apps/web`). The agent joins
automatically. Use headphones.

## Full Phase 3 start order (GPU session)

Each service in its own terminal (or tmux window), started in this order:

| # | Service | Commands | Ready when the log says |
|---|---|---|---|
| 1 | PersonaPlex | `source /workspace/personaplex.env && cd /workspace/personaplex && python -m moshi.server --port 8998 --static none` | the server is listening |
| 2 | Face | `source /workspace/face.env && cd /workspace/persona-live/server/face && python service.py --avatar lumi` | `face service ready` |
| 3 | Vision | `source /workspace/vision.env && cd /workspace/persona-live/server/vision && python service.py` | `vision service ready` |
| 4 | Agent | `source /root/venvs/agent/bin/activate && cd /workspace/persona-live/server/agent && python main.py dev` | registered with LiveKit |

First-time setup: `face-setup.sh` + `prepare_avatar.sh` (`server/face/README.md`) and
`vision-setup.sh` (`server/vision/README.md`). Give the next pod **50 GB of container
disk**: the three venvs (PersonaPlex, face, vision) need about 20 GB together.

**Status:** the Phase 3 agent code (`output.py`, `face_client.py`, `vision_client.py`
and the changes to `main.py`) is written but not yet run.

## Reading the logs

- `PersonaPlex handshake received; conversation is live`: the prompt was loaded and audio is flowing.
- Every 10 s: `audio so far: mic X s (+Y s silence fill), lumi Z s, playback queue N ms`.
  `mic` and `lumi` should grow at the same rate. If `lumi` falls behind, the GPU isn't
  keeping up with real time. `silence fill` grows while your mic is muted; that keeps
  Lumi from freezing mid-sentence.
- `Can't reach PersonaPlex at ws://127.0.0.1:8998/...`: moshi.server isn't running, or is on another port.
- `No handshake from PersonaPlex after 90 s`: another conversation is still connected
  (close the other tab/room), or the server is still loading.
- `PersonaPlex closed the connection instead of handshaking`: usually a wrong
  `PERSONAPLEX_VOICE`. Check the moshi.server terminal for the error.
- `Lumi sees: ...`: the camera description that went into her prompt.
  `no camera frame from the user (camera off)` means she was told she can't see you.
- `face service at ws://127.0.0.1:8999/stream isn't available ...; Lumi is voice-only this time`:
  the face service isn't running (or is busy with another conversation).
- The 10 s stats line ends with `face delay N ms`: how far her voice is held back for the
  video. Expect ~300 ms. If it keeps growing, the face can't keep real time (see `server/face/README.md`).
- `face service failed, continuing with voice only`: the face stream broke mid-call; her
  video track is removed and the page shows the voice-only tile.
