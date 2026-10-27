from fastapi import APIRouter

from app.api.v1 import (
    auth,
    dashboard,
    food,
    freshness,
    history,
    meals,
    media,
    nutrition,
    system,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(media.router)
api_router.include_router(history.router)
api_router.include_router(food.router)
api_router.include_router(freshness.router)
api_router.include_router(nutrition.router)
api_router.include_router(meals.router)
