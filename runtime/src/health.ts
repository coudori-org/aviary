/**
 * Liveness / readiness probes.
 *
 * Readiness only reports whether the server has finished booting — it does
 * NOT gate on session count. KEDA handles scale-up based on session load;
 * there's no hard per-pod cap.
 */

import { Router, type Request, type Response } from "express";

let _ready = false;

export function setReady(ready = true): void {
  _ready = ready;
}

export const healthRouter = Router();

healthRouter.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

healthRouter.get("/ready", (_req: Request, res: Response) => {
  if (!_ready) {
    res.status(503).json({ status: "not_ready" });
    return;
  }
  res.json({ status: "ready" });
});
