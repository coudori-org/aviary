"""Health and readiness probes for the agent runtime."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_ready = False
_manager = None  # SessionManager reference, set during lifespan


def set_ready(ready: bool = True):
    global _ready
    _ready = ready


def set_manager(mgr):
    global _manager
    _manager = mgr


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    if not _ready:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    if _manager and not _manager.has_capacity:
        return JSONResponse(
            {"status": "at_capacity", "active": _manager.active_count},
            status_code=503,
        )
    return {"status": "ready", "active": _manager.active_count if _manager else 0}
