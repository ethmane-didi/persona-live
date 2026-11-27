"use client";

import { useEffect, useState } from "react";
import {
  BarVisualizer,
  VideoTrack,
  useConnectionState,
  useLocalParticipant,
  useRoomContext,
  useTranscriptions,
  useVoiceAssistant,
  type TrackReference,
} from "@livekit/components-react";
import { Track, VideoPresets, type VideoCaptureOptions } from "livekit-client";
import { DATA_DISCLOSURE } from "@/lib/disclosure";
import { getLumiStatus, STATUS_LABEL, type LumiStatus } from "@/lib/lumi-status";
import { DemoVideo } from "./DemoVideo";

/** After this long in "waiting", explain that the agent is probably offline. */
const AGENT_OFFLINE_HINT_MS = 15_000;
/** How many of Lumi's recent caption segments to show. */
const CAPTION_SEGMENTS = 3;
/** 960x540 is plenty for the agent's vision model and keeps upload bandwidth low. */
const CAMERA_OPTIONS: VideoCaptureOptions = {
  resolution: VideoPresets.h540.resolution,
  facingMode: "user",
};

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

function cameraErrorMessage(error: unknown): string {
  const name = error instanceof Error ? error.name : "";
  switch (name) {
    case "NotAllowedError":
      return "Camera access was blocked. Allow the camera for this site in your browser settings, then try again.";
    case "NotFoundError":
      return "No camera found.";
    case "NotReadableError":
      return "Your camera is being used by another app. Close it and try again.";
    default:
      return `Couldn't start your camera${error instanceof Error ? `: ${error.message}` : "."}`;
  }
}

type Props = {
  micError: string | null;
  onLeave: () => void;
};

export function LumiSession({ micError, onLeave }: Props) {
  const room = useRoomContext();
  const connection = useConnectionState();
  const { agent, state: agentState, audioTrack, videoTrack: lumiVideo } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled, cameraTrack } = useLocalParticipant();
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

  const [demoVideo, setDemoVideo] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [cameraBusy, setCameraBusy] = useState(false);

  const selfView: TrackReference | undefined =
    isCameraEnabled && cameraTrack
      ? { participant: localParticipant, publication: cameraTrack, source: Track.Source.Camera }
      : undefined;

  const toggleMic = () => {
    void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
  };

  const toggleCamera = async () => {
    setCameraBusy(true);
    setCameraError(null);
    try {
      await localParticipant.setCameraEnabled(!isCameraEnabled, isCameraEnabled ? undefined : CAMERA_OPTIONS);
    } catch (error) {
      setCameraError(cameraErrorMessage(error));
    } finally {
      setCameraBusy(false);
    }
  };

  const leave = () => {
    onLeave(); // flag first, so the disconnect isn't reported as an error
    void room.disconnect();
  };

  return (
    <section className="flex w-full flex-col items-center gap-5">
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
          <p className="max-w-md text-xs text-neutral-500">
            Still no Lumi after {AGENT_OFFLINE_HINT_MS / 1000} s, so her agent is probably offline. Start it on the
            GPU pod (<code className="text-neutral-400">python main.py dev</code>) and she&apos;ll join this room.
          </p>
        )}
      </div>

      {/* The call: Lumi large, you small in the corner. */}
      <div className="relative aspect-video w-full overflow-hidden rounded-2xl border border-white/10 bg-black">
        {lumiVideo ? (
          <VideoTrack trackRef={lumiVideo} className="h-full w-full object-cover" />
        ) : demoVideo ? (
          <DemoVideo className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-4">
            <p className="text-sm text-neutral-500">
              {agent ? "Lumi (audio only: her face isn't running yet)" : "Lumi isn't here yet"}
            </p>
            <BarVisualizer
              state={agentState}
              trackRef={audioTrack}
              barCount={7}
              className="h-16 w-48"
              aria-label="Lumi's voice level"
            />
          </div>
        )}

        <span className="absolute bottom-3 left-3 rounded-md bg-black/60 px-2 py-1 text-xs text-neutral-200">
          Lumi · AI
        </span>

        {selfView && (
          <div className="absolute right-3 bottom-3 aspect-video w-1/4 min-w-28 overflow-hidden rounded-lg border border-white/20 bg-neutral-900 shadow-lg">
            {/* Mirrored, like every video-call self-view. Lumi receives it unmirrored. */}
            <VideoTrack trackRef={selfView} className="h-full w-full -scale-x-100 object-cover" />
          </div>
        )}
      </div>

      <div className="min-h-14 w-full text-center text-lg leading-relaxed text-neutral-200" aria-live="polite">
        {captions.length > 0 ? (
          captions.map((c) => <p key={c.streamInfo.id}>{c.text}</p>)
        ) : (
          <p className="text-sm text-neutral-600">{status === "live" ? "Lumi's words will show up here." : ""}</p>
        )}
      </div>

      {(micError || cameraError) && (
        <div className="w-full space-y-2">
          {[micError, cameraError].filter(Boolean).map((message) => (
            <p
              key={message}
              role="alert"
              className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
            >
              {message}
            </p>
          ))}
        </div>
      )}

      <div className="flex flex-wrap justify-center gap-3">
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
          onClick={toggleCamera}
          disabled={cameraBusy}
          aria-pressed={isCameraEnabled}
          className={`rounded-full px-5 py-2 text-sm font-medium transition disabled:cursor-wait disabled:opacity-60 ${
            isCameraEnabled
              ? "bg-violet-500/25 text-violet-100 hover:bg-violet-500/35"
              : "bg-white/10 text-neutral-100 hover:bg-white/15"
          }`}
        >
          {cameraBusy ? "Camera…" : isCameraEnabled ? "Turn camera off" : "Turn camera on"}
        </button>
        {!lumiVideo && (
          <button
            type="button"
            onClick={() => setDemoVideo((on) => !on)}
            aria-pressed={demoVideo}
            className="rounded-full bg-white/5 px-5 py-2 text-sm text-neutral-400 transition hover:bg-white/10"
          >
            {demoVideo ? "Hide demo video" : "Demo video"}
          </button>
        )}
        <button
          type="button"
          onClick={leave}
          className="rounded-full bg-white/10 px-5 py-2 text-sm font-medium text-neutral-100 transition hover:bg-red-500/30"
        >
          Leave
        </button>
      </div>

      <p className="max-w-md text-center text-xs text-neutral-500">{DATA_DISCLOSURE}</p>
    </section>
  );
}
