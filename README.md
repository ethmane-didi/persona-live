# persona-live

A real-time AI video persona you talk to in the browser. Open the page, allow the mic
(and, if you like, the camera), and have a live video call with **Lumi**, a photoreal
persona who listens and speaks at the same time (full-duplex). Inspired by Nuance Labs'
Emma, built only on free, open-source software. The only cost is rented GPU time.

> Lumi is an AI and always says so. She never claims to be human. Her face is an
> original or licensed likeness with a signed release, never a real person without
> written consent.

## Architecture

```text
Browser (Next.js)  ⇄  LiveKit room (WebRTC)  ⇄  GPU server (Python)
  - mic + camera in                               ├─ PersonaPlex  (full-duplex speech-to-speech, voice + persona)
  - persona audio + video out                     ├─ MuseTalk 1.5 (persona audio → lip-synced photoreal video)
  - video-call UI, captions                       ├─ vision model (describes the user's camera once, at the start)
                                                  └─ LiveKit agent (joins room, routes audio/video, keeps lips in sync)
```

| Piece | What it does | License |
|---|---|---|
| [PersonaPlex](https://github.com/NVIDIA/PersonaPlex) | Voice brain: full-duplex speech-to-speech | MIT code + NVIDIA Open Model License |
| [MuseTalk 1.5](https://github.com/TMElyralab/MuseTalk) | Lip-syncs a looping video of Lumi to her voice, live | MIT code; weights "available for any purpose, even commercially" (see open items) |
| [SmolVLM2-2.2B](https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct) | Describes one camera frame for Lumi's prompt | Apache 2.0 |
| LiveKit + LiveKit Agents | WebRTC transport between browser and GPU | Apache 2.0 |
| Next.js, Tailwind | Frontend | MIT |
| Supabase | Auth, session logs, minute caps (phase 4) | Apache 2.0 |

**What "she sees you" means today:** PersonaPlex is audio-only and takes text only once,
as the role prompt at the start. So Lumi sees one moment (when you join) and can refer
to it. She can't notice changes later in the call. Continuous vision needs a different
model and is deferred.

## Build order

One phase at a time. Don't start the next until the current one works.

- [x] **Phase 1: Voice only.** PersonaPlex on a rented GPU, talking with the role prompt from `prompts/persona.md`.
- [ ] **Phase 2: Browser voice.** LiveKit agent wraps PersonaPlex; the Next.js page streams the mic and plays the reply. Barge-in works. (Page done; end-to-end test with the pod pending.)
- [ ] **Phase 3: Face + camera.** MuseTalk video of Lumi in sync with her voice (under 100 ms of drift); camera on/off on the page; the agent describes your camera at the start.
- [ ] **Phase 4: Product shell.** Supabase login, minutes cap per user, session logging, landing page.

## Open items before any commercial launch

- [ ] **S3FD face detector license.** MuseTalk's face detection comes from [face-alignment](https://github.com/1adrianb/face-alignment); its weights download from `adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth`. Check the weights' license (and the training data's terms).
- [ ] **Face-parsing (BiSeNet) model license.** MuseTalk downloads `79999_iter.pth` from a Google Drive link (the face-parsing.PyTorch model) plus torchvision's ResNet-18. Check the weights' license and the training data's terms.
- [ ] **MuseTalk's other parts**, per its own license note: whisper-tiny (Apache 2.0), sd-vae-ft-mse (MIT), DWPose (Apache 2.0). Verified on Hugging Face; re-check at launch.
- [ ] **livekit-local-inference**, pulled in by livekit-agents: "Apache-2.0 AND LicenseRef-LiveKit-Model". We use none of its models; review the terms anyway.
- [ ] **Lumi's likeness:** signed release covering AI/synthetic use, commercial use and modification.
- [ ] **Data disclosure:** the page says sessions may be logged (LiveKit agent observability). Replace with a real privacy policy, and update the text if observability is turned off.

## Local vs GPU

| Runs locally (Mac) | Runs on the GPU server (RunPod) |
|---|---|
| Next.js frontend only (Node; no Python) | PersonaPlex, MuseTalk face service, vision service, LiveKit agent |

**Never download model weights or run GPU code locally.** Point the local frontend at
LiveKit Cloud; the agent on the pod joins the same rooms.

## Repo layout

```text
persona-live/
├── prompts/persona.md        # character role prompt, loaded at runtime
├── docs/RESEARCH.md          # background research and model choices
├── apps/web/                 # Next.js frontend (video-call page)
└── server/
    ├── agent/                # LiveKit agent (Python)
    ├── personaplex/          # voice model notes + runtime prompt loader
    ├── face/                 # MuseTalk streaming face service
    ├── vision/               # camera-frame describer
    └── scripts/              # GPU server setup scripts
```

## Setup

1. Copy `.env.example` to `.env` and fill in the values. For the frontend, copy `apps/web/.env.local.example` to `apps/web/.env.local`.
2. Commands:
   - Frontend: `cd apps/web && npm run dev`
   - GPU setup (GPU server): `bash server/scripts/runpod-setup.sh`, then `agent-setup.sh`, `face-setup.sh`, `vision-setup.sh`
   - Services (GPU server): see `server/agent/README.md` for the full start order

## Rules

- Secrets live in `.env` / `.env.local`, never committed.
- Check a model's license before adding it. Commercial use must be allowed.
- Never clone a real person's face or voice without written consent. Use original or licensed assets only.
- Tell users truthfully what happens to their camera and voice.

## More

- [docs/RESEARCH.md](docs/RESEARCH.md): why this stack, GPU options, alternatives
- [prompts/persona.md](prompts/persona.md): Lumi's runtime prompt and character sheet
