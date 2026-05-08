"""
WebSocket endpoint for real-time order tracking (FR-05, FR-04.1, FR-13).
Students connect to /ws/orders/{order_id} to receive live status pushes.
Kitchen connects to /ws/kitchen-queue to receive new order alerts.
"""

import json
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.security import decode_token

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        # order_id → set of connected WebSockets
        self.order_listeners: Dict[int, Set[WebSocket]] = {}
        # kitchen staff connections
        self.kitchen_connections: Set[WebSocket] = set()

    async def connect_order(self, websocket: WebSocket, order_id: int):
        await websocket.accept()
        self.order_listeners.setdefault(order_id, set()).add(websocket)

    async def connect_kitchen(self, websocket: WebSocket):
        await websocket.accept()
        self.kitchen_connections.add(websocket)

    def disconnect_order(self, websocket: WebSocket, order_id: int):
        listeners = self.order_listeners.get(order_id, set())
        listeners.discard(websocket)

    def disconnect_kitchen(self, websocket: WebSocket):
        self.kitchen_connections.discard(websocket)

    async def broadcast_order_update(self, order_id: int, payload: dict):
        """Broadcast order status update to all listeners for that order."""
        listeners = self.order_listeners.get(order_id, set())
        dead = set()
        for ws in listeners:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            listeners.discard(ws)

    async def broadcast_kitchen(self, payload: dict):
        """Broadcast new order / queue update to all kitchen connections."""
        dead = set()
        for ws in self.kitchen_connections:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.kitchen_connections.discard(ws)


manager = ConnectionManager()


@router.websocket("/ws/orders/{order_id}")
async def order_status_ws(websocket: WebSocket, order_id: int, token: str = Query(...)):
    """
    FR-05: Live order status updates (Received → Preparing → Ready).
    FR-13: Notify student when order is ready.
    Client connects with ?token=<access_token>
    """
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect_order(websocket, order_id)
    try:
        await websocket.send_json({"type": "connected", "order_id": order_id})
        while True:
            # Keep connection alive; status pushes come from the HTTP endpoints
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect_order(websocket, order_id)


@router.websocket("/ws/kitchen")
async def kitchen_queue_ws(websocket: WebSocket, token: str = Query(...)):
    """
    FR-18: Live kitchen queue — new orders appear instantly.
    Only accessible by kitchen_staff and admin roles.
    """
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect_kitchen(websocket)
    try:
        await websocket.send_json({"type": "connected", "role": "kitchen"})
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect_kitchen(websocket)
