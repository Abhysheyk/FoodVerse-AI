from fastapi import APIRouter

from app.api.v1 import auth, dashboard, history, media, system, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(media.router)
api_router.include_router(history.router)
