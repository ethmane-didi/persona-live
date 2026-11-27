"use client";

import { useEffect, useState } from "react";
import {
  BarVisualizer,
  useConnectionState,
  useLocalParticipant,
  useRoomContext,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { getLumiStatus, STATUS_LABEL, type LumiStatus } from "@/lib/lumi-status";

/** After this long in "waiting", explain that the agent is probably offline. */
const AGENT_OFFLINE_HINT_MS = 15_000;
/** How many of Lumi's recent caption segments to show. */
const CAPTION_SEGMENTS = 3;

const STATUS_STYLE: Record<LumiStatus, string> = {
  connecting: "bg-sky-500/15 text-sky-300",
  waiting: "bg-amber-500/15 text-amber-300",
  "getting-ready": "bg-amber-500/15 text-amber-300",
  live: "bg-emerald-500/15 text-emerald-300",
  reconnecting: "bg-sky-500/15 text-sky-300",
  disconnected: "bg-red-500/15 text-red-300",
};

const STATUS_HELP: Record<LumiStatus, string> = {
  connecting: "Joining the room…",
  waiting: "You're in the room. Lumi will join as soon as her agent picks it up.",
  "getting-ready": "Lumi joined and is loading her persona. This takes a few seconds.",
  live: "Go ahead and talk. You can interrupt her any time.",
  reconnecting: "The connection dropped for a moment. Reconnecting…",
  disconnected: "The room closed.",
};

type Props = {
  micError: string | null;
  onLeave: () => void;
};

export function LumiSession({ micError, onLeave }: Props) {
  const room = useRoomContext();
  const connection = useConnectionState();
  const { agent, state: agentState, audioTrack } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const status = getLumiStatus(connection, agent !== undefined, agentState);

  // Lumi's captions: transcription streams published by the agent.
  const captions = useTranscriptions()
    .filter((t) => agent !== undefined && t.participantInfo.identity === agent.identity)
    .slice(-CAPTION_SEGMENTS);

  const [showOfflineHint, setShowOfflineHint] = useState(false);
  useEffect(() => {
    setShowOfflineHint(false);
    if (status !== "waiting") return;
    const timer = setTimeout(() => setShowOfflineHint(true), AGENT_OFFLINE_HINT_MS);
    return () => clearTimeout(timer);
  }, [status]);

  const toggleMic = () => {
    void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
  };

  const leave = () => {
    onLeave(); // flag first, so the disconnect isn't reported as an error
    void room.disconnect();
  };

  return (
    <section className="flex w-full flex-col items-center gap-6 rounded-3xl border border-white/10 bg-white/[0.03] p-8">
      <div className="flex flex-col items-center gap-2 text-center">
        <span
          role="status"
          className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${STATUS_STYLE[status]}`}
        >
          <span className="size-2 rounded-full bg-current" aria-hidden />
          {STATUS_LABEL[status]}
        </span>
        <p className="text-sm text-neutral-400">{STATUS_HELP[status]}</p>
        {status === "waiting" && showOfflineHint && (
          <p className="max-w-sm text-xs text-neutral-500">
            Still no Lumi after {AGENT_OFFLINE_HINT_MS / 1000} s, so her agent is probably offline. Start it on the
            GPU pod (<code className="text-neutral-400">python main.py dev</code>) and she&apos;ll join this room.
          </p>
        )}
      </div>

      <BarVisualizer
        state={agentState}
        trackRef={audioTrack}
        barCount={7}
        className="h-24 w-full max-w-xs"
        aria-label="Lumi's voice level"
      />

      <div className="min-h-16 w-full text-center text-lg leading-relaxed text-neutral-200" aria-live="polite">
        {captions.length > 0 ? (
          captions.map((c) => <p key={c.streamInfo.id}>{c.text}</p>)
        ) : (
          <p className="text-sm text-neutral-600">{status === "live" ? "Lumi's words will show up here." : ""}</p>
        )}
      </div>

      {micError && (
        <p role="alert" className="w-full rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {micError}
        </p>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={toggleMic}
          aria-pressed={isMicrophoneEnabled}
          className={`rounded-full px-5 py-2 text-sm font-medium transition ${
            isMicrophoneEnabled
              ? "bg-white/10 text-neutral-100 hover:bg-white/15"
              : "bg-red-500/20 text-red-200 hover:bg-red-500/30"
          }`}
        >
          {isMicrophoneEnabled ? "Mute mic" : "Unmute mic"}
        </button>
        <button
          type="button"
          onClick={leave}
          className="rounded-full bg-white/10 px-5 py-2 text-sm font-medium text-neutral-100 transition hover:bg-red-500/30"
        >
          Leave
        </button>
      </div>
    </section>
  );
}
