import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Talk to Lumi",
  description: "A live voice conversation with Lumi, an AI companion.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // suppressHydrationWarning: browser extensions (e.g. Scribe's recorder) add
    // attributes like data-scribe-recorder-ready to <html>/<body> before React loads,
    // which React reports as a hydration mismatch. This only ignores attribute
    // differences on these two tags, not in the page content.
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-dvh bg-neutral-950 text-neutral-100 antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
