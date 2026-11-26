# persona-live

A real-time AI video persona you talk to in the browser. Open the page, allow the mic,
and have a live spoken conversation with **Lumi**, an animated 3D character who listens
and speaks at the same time (full-duplex). Inspired by Nuance Labs' Emma, built only on
free, open-source software. The only cost is rented GPU time.

> Lumi is an AI and always says so. She never claims to be human.

## Architecture

```
Browser (Next.js)  ⇄  LiveKit room (WebRTC)  ⇄  GPU server (Python)
  - mic in                                        ├─ PersonaPlex  (full-duplex speech-to-speech, voice + persona)
  - persona audio out                             ├─ Audio2Face-3D (audio → facial blendshapes + emotion)
  - 3D face (three.js) driven by blendshapes      └─ LiveKit agent (joins room, routes audio + blendshape data)
```

| Piece | What it does | License |
|---|---|---|
| [PersonaPlex](https://github.com/NVIDIA/PersonaPlex) | Voice brain: full-duplex speech-to-speech | MIT code + NVIDIA Open Model License |
| [Audio2Face-3D](https://huggingface.co/nvidia/Audio2Face-3D-v3.0) | Turns audio into facial blendshapes (not video) | NVIDIA Open Model License |
| LiveKit + LiveKit Agents | WebRTC transport between browser and GPU | Apache 2.0 |
| Next.js, three.js, Tailwind | Frontend | MIT |
| Supabase | Auth, session logs, minute caps (phase 4) | Apache 2.0 |

## Build order

One phase at a time. Don't start the next until the current one works.

- [ ] **Phase 1: Voice only.** PersonaPlex on a rented GPU, talking with the role prompt from `prompts/persona.md`.
- [ ] **Phase 2: Browser voice.** LiveKit agent wraps PersonaPlex; the Next.js page streams the mic and plays the reply. Barge-in works.
- [ ] **Phase 3: Face.** Audio2Face-3D blendshapes over the LiveKit data channel drive a three.js head, under 100 ms of drift.
- [ ] **Phase 4: Product shell.** Supabase login, minutes cap per user, session logging, landing page.

## Local vs GPU

| Runs locally (Mac) | Runs on the GPU server (RunPod) |
|---|---|
| Next.js frontend only | PersonaPlex, Audio2Face-3D, LiveKit agent |

**Never download model weights or run GPU code locally.** Point the local frontend at the
remote LiveKit server and agent.

## Repo layout

```
persona-live/
├── prompts/persona.md        # character role prompt, loaded at runtime
├── docs/RESEARCH.md          # background research and model choices
├── apps/web/                 # Next.js frontend
└── server/
    ├── agent/                # LiveKit agent (Python)
    ├── personaplex/          # model wrapper + voice samples
    ├── audio2face/           # blendshape service
    └── scripts/              # GPU server setup (runpod-setup.sh)
```

## Setup

1. Copy `.env.example` to `.env` and fill in the values. Copy the frontend values into `apps/web/.env.local`.
2. Commands (filled in as each phase lands):
   - Frontend: `cd apps/web && npm run dev`
   - Agent (GPU server): `cd server/agent && python main.py dev`
   - GPU setup (GPU server): `bash server/scripts/runpod-setup.sh`

## Rules

- Secrets live in `.env` / `.env.local`, never committed.
- Check a model's license before adding it. Commercial use must be allowed.
- Never clone a real person's face or voice without written consent. Use original or licensed assets only.

## More

- [docs/RESEARCH.md](docs/RESEARCH.md): why this stack, GPU options, alternatives
- [prompts/persona.md](prompts/persona.md): Lumi's runtime prompt and character sheet
