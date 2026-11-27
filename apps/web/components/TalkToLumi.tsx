"use client";

import { useCallback, useRef, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer, StartAudio } from "@livekit/components-react";
import { DisconnectReason, MediaDeviceFailure } from "livekit-client";
import type { ConnectionDetails, TokenError } from "@/lib/connection-details";
import { LumiSession } from "./LumiSession";

type Phase =
  | { kind: "idle" }
  | { kind: "fetching-token" }
  | { kind: "in-room"; details: ConnectionDetails }
  | { kind: "error"; message: string };

// Browser audio processing for the mic. Echo cancellation matters most:
// PersonaPlex hears you while it talks, so without it Lumi hears herself.
const MIC_OPTIONS = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };

function micFailureMessage(failure?: MediaDeviceFailure): string {
  switch (failure) {
    case MediaDeviceFailure.PermissionDenied:
      return "Microphone access was blocked. Allow the mic for this site in your browser settings, then try again.";
    case MediaDeviceFailure.NotFound:
      return "No microphone found. Plug one in and try again.";
    case MediaDeviceFailure.DeviceInUse:
      return "Your microphone is being used by another app. Close it and try again.";
    default:
      return "Couldn't start your microphone.";
  }
}

export function TalkToLumi() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [micError, setMicError] = useState<string | null>(null);
  // Set when the user clicks Leave, so that disconnect isn't shown as an error.
  const leavingRef = useRef(false);

  const start = useCallback(async () => {
    leavingRef.current = false;
    setMicError(null);
    setPhase({ kind: "fetching-token" });
    try {
      const res = await fetch("/api/token", { method: "POST" });
      const body: unknown = await res.json();
      if (!res.ok) {
        const message = (body as Partial<TokenError>).error ?? `Token request failed (HTTP ${res.status}).`;
        setPhase({ kind: "error", message });
        return;
      }
      setPhase({ kind: "in-room", details: body as ConnectionDetails });
    } catch {
      setPhase({ kind: "error", message: "Couldn't reach /api/token. Is `npm run dev` still running?" });
    }
  }, []);

  const leave = useCallback(() => {
    leavingRef.current = true;
    setPhase({ kind: "idle" });
  }, []);

  const onDisconnected = useCallback((reason?: DisconnectReason) => {
    if (leavingRef.current || reason === DisconnectReason.CLIENT_INITIATED) {
      setPhase({ kind: "idle" });
      return;
    }
    setPhase({
      kind: "error",
      message: `Disconnected from LiveKit${reason !== undefined ? ` (${DisconnectReason[reason]})` : ""}.`,
    });
  }, []);

  const onError = useCallback((error: Error) => {
    setPhase({ kind: "error", message: `LiveKit error: ${error.message}` });
  }, []);

  if (phase.kind === "in-room") {
    return (
      <LiveKitRoom
        serverUrl={phase.details.serverUrl}
        token={phase.details.participantToken}
        connect
        audio={MIC_OPTIONS}
        video={false}
        onDisconnected={onDisconnected}
        onError={onError}
        onMediaDeviceFailure={(failure) => setMicError(micFailureMessage(failure))}
        className="w-full"
      >
        <LumiSession micError={micError} onLeave={leave} />
        {/* Plays Lumi's audio track. */}
        <RoomAudioRenderer />
        {/* Shown only if the browser blocked autoplay. */}
        <StartAudio
          label="Click to hear Lumi"
          className="mx-auto mt-4 block rounded-full bg-amber-500 px-5 py-2 text-sm font-medium text-neutral-950"
        />
      </LiveKitRoom>
    );
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      {phase.kind === "error" && (
        <p role="alert" className="w-full rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {phase.message}
        </p>
      )}
      <button
        type="button"
        onClick={start}
        disabled={phase.kind === "fetching-token"}
        className="rounded-full bg-violet-500 px-8 py-4 text-lg font-medium text-white shadow-lg shadow-violet-500/20 transition hover:bg-violet-400 disabled:cursor-wait disabled:opacity-60"
      >
        {phase.kind === "fetching-token" ? "Connecting…" : phase.kind === "error" ? "Try again" : "Talk to Lumi"}
      </button>
    </div>
  );
}
