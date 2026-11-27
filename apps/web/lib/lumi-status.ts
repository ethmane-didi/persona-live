import { ConnectionState } from "livekit-client";
import type { AgentState } from "@livekit/components-react";

/** What the in-room UI shows. */
export type LumiStatus =
  | "connecting" // joining the LiveKit room
  | "waiting" // in the room, but no agent has joined (agent offline / pod stopped)
  | "getting-ready" // agent joined and is loading the persona into PersonaPlex
  | "live" // talking
  | "reconnecting" // network blip; LiveKit is reconnecting
  | "disconnected";

const LIVE_AGENT_STATES: ReadonlySet<AgentState> = new Set(["listening", "thinking", "speaking"]);

/**
 * Room connection + agent presence/state -> one UI status.
 * The agent (server/agent/main.py) sets its state to "initializing" while it
 * connects to PersonaPlex, then "listening" once the conversation is live.
 */
export function getLumiStatus(
  connection: ConnectionState,
  agentPresent: boolean,
  agentState: AgentState,
): LumiStatus {
  switch (connection) {
    case ConnectionState.Connecting:
      return "connecting";
    case ConnectionState.Reconnecting:
    case ConnectionState.SignalReconnecting:
      return "reconnecting";
    case ConnectionState.Disconnected:
      return "disconnected";
    case ConnectionState.Connected:
      if (!agentPresent) return "waiting";
      return LIVE_AGENT_STATES.has(agentState) ? "live" : "getting-ready";
    default:
      return "connecting";
  }
}

export const STATUS_LABEL: Record<LumiStatus, string> = {
  connecting: "Connecting",
  waiting: "Waiting for Lumi",
  "getting-ready": "Lumi is getting ready",
  live: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Disconnected",
};
