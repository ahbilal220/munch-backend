from fastapi import APIRouter
from app.api.v1.endpoints import auth, menu, orders, misc, ws

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(menu.router)
api_router.include_router(orders.router)
api_router.include_router(misc.router)
api_router.include_router(ws.router)
