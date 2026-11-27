import { TalkToLumi } from "@/components/TalkToLumi";
import { AI_DISCLOSURE, DATA_DISCLOSURE } from "@/lib/disclosure";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col items-center justify-center gap-10 px-6 py-16">
      <header className="space-y-3 text-center">
        <h1 className="text-4xl font-semibold tracking-tight">Lumi</h1>
        <p className="text-neutral-400">
          A live video call with an AI companion. She listens while she talks, so you can interrupt her
          any time. Turn your camera on if you&apos;d like her to see you.
        </p>
      </header>

      <TalkToLumi />

      <footer className="space-y-1 text-center text-xs text-neutral-500">
        <p>{AI_DISCLOSURE} Use headphones so she doesn&apos;t hear herself.</p>
        <p>{DATA_DISCLOSURE}</p>
      </footer>
    </main>
  );
}
