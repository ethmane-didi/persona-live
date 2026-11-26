# server/agent: LiveKit agent

Joins each new LiveKit room, waits for the user, and bridges their audio to
PersonaPlex running on the same pod:

```
browser mic ──WebRTC──▶ LiveKit Cloud ──▶ agent ──ws://127.0.0.1:8998──▶ moshi.server (PersonaPlex)
browser speaker ◀──────  LiveKit Cloud ◀── agent ◀── Lumi's voice (+ captions) ──┘
```

1. Your mic (resampled by LiveKit to 24 kHz mono) is encoded to Ogg-Opus and streamed to PersonaPlex.
2. Lumi's voice comes back as Ogg-Opus, is decoded, and published as an audio track.
3. Her words come back as text and are published as live captions (LiveKit transcription streams).
4. (Phase 3) her audio also goes through Audio2Face, with blendshapes on the data channel.

There's **no turn-taking or voice-activity detection** in the agent. PersonaPlex is
full-duplex: it hears you while it talks and handles interruptions (barge-in) itself.
That's also why the agent doesn't use LiveKit's `AgentSession`, which is built around
speech-to-text → LLM → text-to-speech turns.

| File | What it does |
|---|---|
| `main.py` | The LiveKit side: joins the room, moves audio between LiveKit and the backend, publishes captions |
| `personaplex_client.py` | The PersonaPlex WebSocket protocol (handshake, Ogg-Opus audio, text) |
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
pick the project, connect). The agent joins automatically. Use headphones.

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
