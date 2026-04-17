/**
 * Dedicated proxy for the workflow-builder AI assistant endpoint.
 *
 * The default Next.js `rewrites` path pipes through undici with a ~60s
 * idle timeout, which kills the connection well before this endpoint
 * finishes (3 sequential LLM calls = ~2-3 min). This route handler
 * replaces the rewrite for this specific path and uses an AbortSignal
 * that tolerates the full latency budget.
 */

import { NextRequest } from "next/server";

const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const ASSISTANT_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes — 3 stages × 5 min API timeout

export const maxDuration = 600;

async function proxy(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const url = `${API_URL}/api/workflows/${id}/assistant`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");

  const body = req.method === "POST" ? await req.text() : undefined;

  const res = await fetch(url, {
    method: req.method,
    headers,
    body,
    signal: AbortSignal.timeout(ASSISTANT_TIMEOUT_MS),
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

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  return proxy(req, ctx);
}
