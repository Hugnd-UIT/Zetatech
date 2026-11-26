import asyncio
from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: int):
        await websocket.accept()
        async with self.lock:
            if session_id not in self.active_connections:
                self.active_connections[session_id] = []
            self.active_connections[session_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, session_id: int):
        async with self.lock:
            if session_id in self.active_connections:
                if websocket in self.active_connections[session_id]:
                    self.active_connections[session_id].remove(websocket)
                if not self.active_connections[session_id]:
                    del self.active_connections[session_id]

    async def send_to_session(self, session_id: int, message: dict):
        targets = []
        async with self.lock:
            if session_id in self.active_connections:
                targets = list(self.active_connections[session_id])

        failed: List[WebSocket] = []
        for conn in targets:
            try:
                await conn.send_json(message)
            except Exception:
                failed.append(conn)

        if not failed:
            return

        async with self.lock:
            items = self.active_connections.get(session_id)
            if not items:
                return
            for conn in failed:
                if conn in items:
                    items.remove(conn)
            if not items:
                del self.active_connections[session_id]


manager = ConnectionManager()
