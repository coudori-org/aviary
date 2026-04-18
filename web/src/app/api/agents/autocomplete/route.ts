/**
 * Dedicated proxy for the agent auto-complete endpoint.
 *
 * The default Next.js `rewrites` path pipes through undici with a ~60s
 * idle timeout, which kills the connection well before this endpoint
 * finishes (3 sequential LLM calls). This route handler replaces the
 * rewrite for this specific path and uses an AbortSignal that tolerates
 * the full latency budget.
 */

import { NextRequest } from "next/server";

const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const AUTOCOMPLETE_TIMEOUT_MS = 10 * 60 * 1000;

export const maxDuration = 600;

export async function POST(req: NextRequest) {
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");

  const body = await req.text();

  const res = await fetch(`${API_URL}/api/agents/autocomplete`, {
    method: "POST",
    headers,
    body,
    signal: AbortSignal.timeout(AUTOCOMPLETE_TIMEOUT_MS),
    // @ts-expect-error — Node fetch accepts `duplex` for streaming bodies
    duplex: "half",
  });

  const respHeaders = new Headers(res.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("transfer-encoding");

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: respHeaders,
  });
}
