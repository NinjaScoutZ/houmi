"""
WebSocket Connection Manager for Houmi Pipeline.
Manages per-project WebSocket connections and broadcasts
real-time progress events during pipeline processing.
"""
import logging
import asyncio
from fastapi import WebSocket

logger = logging.getLogger("houmi-ws")


class ConnectionManager:
    """Manages WebSocket connections per project for real-time progress updates."""

    def __init__(self):
        # project_id → list of active WebSocket connections
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, project_id: str, websocket: WebSocket):
        """Accept and register a new WebSocket connection for a project."""
        self._loop = asyncio.get_running_loop()
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info(f"WebSocket connected: project={project_id} (total: {len(self.active_connections[project_id])})")

    def disconnect(self, project_id: str, websocket: WebSocket):
        """Remove a disconnected WebSocket from the registry."""
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info(f"WebSocket disconnected: project={project_id}")

    async def send_progress(self, project_id: str, data: dict):
        """Broadcast a progress event to all connections watching a project."""
        if project_id not in self.active_connections:
            return

        dead_connections = []
        for ws in self.active_connections[project_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(project_id, ws)

    async def broadcast_global(self, data: dict):
        """Broadcast an event to all connected clients across all projects."""
        for project_id in list(self.active_connections.keys()):
            await self.send_progress(project_id, data)

    def broadcast_sync(self, project_id: str, data: dict):
        """
        Thread-safe synchronous wrapper for send_progress.
        Used from background threads (batch processing, training).
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.debug("WS broadcast skipped because no application loop is registered")
            return
        try:
            if loop is asyncio.get_running_loop():
                loop.create_task(self.send_progress(project_id, data))
            else:
                asyncio.run_coroutine_threadsafe(self.send_progress(project_id, data), loop)
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(self.send_progress(project_id, data), loop)

    def broadcast_global_sync(self, data: dict):
        """
        Thread-safe synchronous wrapper for broadcast_global.
        Used from background threads for global events like training updates.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.debug("WS global broadcast skipped because no application loop is registered")
            return
        try:
            if loop is asyncio.get_running_loop():
                loop.create_task(self.broadcast_global(data))
            else:
                asyncio.run_coroutine_threadsafe(self.broadcast_global(data), loop)
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(self.broadcast_global(data), loop)


# Global singleton
ws_manager = ConnectionManager()
