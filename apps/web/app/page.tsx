import { TalkToLumi } from "@/components/TalkToLumi";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-xl flex-col items-center justify-center gap-10 px-6 py-16">
      <header className="space-y-3 text-center">
        <h1 className="text-4xl font-semibold tracking-tight">Lumi</h1>
        <p className="text-neutral-400">
          A live voice conversation with an AI companion. She listens while she talks, so you can
          interrupt her any time.
        </p>
      </header>

      <TalkToLumi />

      <footer className="text-center text-xs text-neutral-500">
        Lumi is an AI, not a person. Use headphones so she doesn&apos;t hear herself.
      </footer>
    </main>
  );
}
