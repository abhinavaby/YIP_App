import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect


class LiveConnections:
    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        async with self._lock:
            self._sockets.add(socket)

    async def disconnect(self, socket: WebSocket) -> None:
        async with self._lock:
            self._sockets.discard(socket)

    async def publish(self, event: str, payload: dict) -> None:
        message = json.dumps({"event": event, "data": payload})
        async with self._lock:
            sockets = list(self._sockets)
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_text(message)
            except (WebSocketDisconnect, RuntimeError):
                stale.append(socket)
        for socket in stale:
            await self.disconnect(socket)


live_connections = LiveConnections()
