"""Combined router for all admin HTML pages."""

from fastapi import APIRouter

from app.routers.pages.agents import router as agents_router
from app.routers.pages.mcp import router as mcp_router
from app.routers.pages.users import router as users_router

router = APIRouter()
router.include_router(agents_router)
router.include_router(mcp_router)
router.include_router(users_router)
