import { randomUUID } from "node:crypto";
import { AccessToken } from "livekit-server-sdk";
import type { ConnectionDetails, TokenError } from "@/lib/connection-details";

// Creates a LiveKit access token on the server. The API secret is read from
// apps/web/.env.local (no NEXT_PUBLIC_ prefix), so it never reaches the browser;
// the browser only gets a short-lived token for one room.
//
// No login yet: anyone who can reach this route can get a token. Fine on
// localhost; Phase 4 puts it behind Supabase auth and a minutes cap. Don't
// deploy it publicly before then.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TOKEN_TTL = "15m";
const REQUIRED_ENV = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"] as const;

function readEnv(): { url: string; apiKey: string; apiSecret: string } | { missing: string[] } {
  const missing = REQUIRED_ENV.filter((name) => {
    const value = process.env[name];
    return !value || value.includes("your-");
  });
  if (missing.length > 0) return { missing };
  return {
    url: process.env.LIVEKIT_URL as string,
    apiKey: process.env.LIVEKIT_API_KEY as string,
    apiSecret: process.env.LIVEKIT_API_SECRET as string,
  };
}

export async function POST(): Promise<Response> {
  const env = readEnv();
  if ("missing" in env) {
    const body: TokenError = {
      error: `LiveKit isn't configured. Set ${env.missing.join(", ")} in apps/web/.env.local (see .env.local.example), then restart npm run dev.`,
    };
    return Response.json(body, { status: 500 });
  }

  // A fresh room per conversation. The LiveKit agent uses automatic dispatch,
  // so it joins every new room in the project on its own.
  const roomName = `lumi-${randomUUID()}`;
  const identity = `user-${randomUUID().slice(0, 8)}`;

  const token = new AccessToken(env.apiKey, env.apiSecret, {
    identity,
    name: "You",
    ttl: TOKEN_TTL,
  });
  token.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  const body: ConnectionDetails = {
    serverUrl: env.url,
    roomName,
    participantToken: await token.toJwt(),
  };
  return Response.json(body, { headers: { "Cache-Control": "no-store" } });
}
