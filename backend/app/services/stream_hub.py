import asyncio
from collections import deque
from time import monotonic

from fastapi import WebSocket

from app.config import settings


class RateLimiter:
    def __init__(self, max_fps: float) -> None:
        self.max_fps = max_fps
        self.window = deque()

    def allow(self) -> bool:
        now = monotonic()
        cutoff = now - 1.0
        while self.window and self.window[0] < cutoff:
            self.window.popleft()

        if len(self.window) >= self.max_fps:
            return False

        self.window.append(now)
        return True


class StreamHub:
    def __init__(self) -> None:
        self.output_clients: set[WebSocket] = set()
        self.frame_queue: asyncio.Queue[bytes | str] = asyncio.Queue(maxsize=4)
        self.input_limiters: dict[WebSocket, RateLimiter] = {}

    async def add_output_client(self, ws: WebSocket) -> None:
        self.output_clients.add(ws)

    async def remove_output_client(self, ws: WebSocket) -> None:
        self.output_clients.discard(ws)

    def register_input(self, ws: WebSocket) -> None:
        self.input_limiters[ws] = RateLimiter(settings.max_fps_per_client)

    def unregister_input(self, ws: WebSocket) -> None:
        self.input_limiters.pop(ws, None)

    async def push_frame(self, ws: WebSocket, payload: bytes | str) -> bool:
        limiter = self.input_limiters.get(ws)
        if limiter is None or not limiter.allow():
            return False

        if self.frame_queue.full():
            try:
                _ = self.frame_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        await self.frame_queue.put(payload)
        return True

    async def pop_frame(self) -> bytes | str:
        return await self.frame_queue.get()

    async def broadcast_json(self, payload: dict) -> None:
        dead_clients: list[WebSocket] = []
        for ws in self.output_clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_clients.append(ws)

        for ws in dead_clients:
            self.output_clients.discard(ws)


hub = StreamHub()
