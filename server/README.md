# server: GPU-side code (Python)

Everything here runs on a rented NVIDIA GPU (RunPod), **never on the local Mac**.

| Folder | What | Phase |
|---|---|---|
| `scripts/` | One-shot setup for a fresh GPU box | 1 |
| `personaplex/` | PersonaPlex model wrapper + voice samples | 1 |
| `agent/` | LiveKit agent that joins the room and routes audio/video | 2, 3 |
| `face/` | MuseTalk face service: Lumi's audio → lip-synced photoreal video | 3 |
| `vision/` | Describes one frame of the user's camera for Lumi's prompt | 3 |

Python code uses type hints. Secrets come from `.env` (see root `.env.example`).
