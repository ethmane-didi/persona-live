# server: GPU-side code (Python)

Everything here runs on a rented NVIDIA GPU (RunPod), **never on the local Mac**.

| Folder | What | Phase |
|---|---|---|
| `scripts/` | One-shot setup for a fresh GPU box | 1 |
| `personaplex/` | PersonaPlex model wrapper + voice samples | 1 |
| `agent/` | LiveKit agent that joins the room and routes audio/data | 2 |
| `audio2face/` | Audio → facial blendshapes service | 3 |

Python code uses type hints. Secrets come from `.env` (see root `.env.example`).
