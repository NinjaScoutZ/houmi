import asyncio
import unittest

from app.ws_manager import ConnectionManager


class _FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.messages.append(data)


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_thread_broadcast_returns_to_application_loop(self):
        manager = ConnectionManager()
        socket = _FakeWebSocket()
        await manager.connect("project", socket)

        await asyncio.to_thread(
            manager.broadcast_sync,
            "project",
            {"type": "mask_progress", "status": "success"},
        )
        for _ in range(20):
            if socket.messages:
                break
            await asyncio.sleep(0.01)

        self.assertTrue(socket.accepted)
        self.assertEqual(
            socket.messages,
            [{"type": "mask_progress", "status": "success"}],
        )


if __name__ == "__main__":
    unittest.main()
