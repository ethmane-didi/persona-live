# apps/web: Next.js frontend

The page the user opens. Joins the LiveKit room, streams the mic, plays Lumi's voice,
and renders her 3D face from blendshape data.

- **Stack:** Next.js (App Router), TypeScript (strict), Tailwind, `@livekit/components-react`, three.js / @react-three/fiber
- **Phases:** 2 (browser voice), 3 (3D face), 4 (Supabase login, landing page)
- **Runs locally.** This is the only part of the project that runs on the Mac.
- **Env:** copy the `NEXT_PUBLIC_*` values from the root `.env.example` into `.env.local`.

Run (once scaffolded in phase 2): `npm run dev`
