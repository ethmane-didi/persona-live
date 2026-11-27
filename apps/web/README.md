# apps/web: Next.js frontend

The page the user opens. Click **Talk to Lumi**, allow the mic, and you join a LiveKit
room where the agent (`server/agent`) brings Lumi in. Phase 3 adds her 3D face.

- **Stack:** Next.js 16 (App Router), TypeScript (strict), Tailwind 4, `@livekit/components-react`
- **Runs locally.** This is the only part of the project that runs on the Mac.

## Run

```bash
cd apps/web
cp .env.local.example .env.local   # then fill in your LiveKit Cloud URL, API key and secret
npm install                        # first time only
npm run dev                        # http://localhost:3000
```

Type check: `npm run typecheck`.

Without the GPU pod you can still join: the page shows **Waiting for Lumi**, and after
15 s a hint that her agent is offline. With the pod running (`server/agent/README.md`)
she joins the room, the status turns **Live**, and her words appear as captions.

## How it fits together

| File | What it does |
|---|---|
| `app/api/token/route.ts` | `POST /api/token`: creates a short-lived (15 min) LiveKit token for a fresh room. Reads the secret from `.env.local` on the server; it never reaches the browser |
| `components/TalkToLumi.tsx` | The button, the token fetch, joining the room with the mic on (echo cancellation on), playing Lumi's audio |
| `components/LumiSession.tsx` | In-room UI: status, Lumi's voice visualizer, live captions, mute and leave |
| `lib/lumi-status.ts` | Turns room connection + agent state into one status: Connecting → Waiting for Lumi → Lumi is getting ready → Live |

The agent joins every new room automatically (LiveKit "automatic dispatch"), so the
token doesn't need to name it.

⚠️ `/api/token` has no login yet, so anyone who can reach it can start a conversation
on your GPU. Keep it on localhost until Phase 4 adds Supabase auth and a minutes cap.
