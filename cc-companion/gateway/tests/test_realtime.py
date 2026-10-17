import json
import tempfile
import unittest
from pathlib import Path

from aiohttp import WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from adapters.pairing import PairingService, PairingStore
from adapters.tmux import TmuxInjector
from app import create_app
from config import GatewayConfig


class RealtimeAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = create_app(
            GatewayConfig(tmux_targets={1: "cc1"}),
            pairing_service=PairingService(
                PairingStore(Path(self.temporary_directory.name) / "pairings.json"),
                pairing_code="123456",
            ),
        )
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary_directory.cleanup()

    async def test_pair_hello_receives_snapshot_then_hook_delta(self):
        websocket = await self.client.ws_connect("/ws")
        await websocket.send_json(
            {"version": 1, "type": "pair.complete", "device_id": "stick-s3-01", "code": "123456"}
        )
        paired = await websocket.receive_json()
        self.assertEqual(paired["type"], "pair.complete")
        self.assertTrue(paired["ok"])

        await websocket.send_json(
            {
                "version": 1,
                "type": "device.hello",
                "device_id": "stick-s3-01",
                "token": paired["token"],
            }
        )
        self.assertEqual((await websocket.receive_json())["type"], "device.ready")
        snapshot = await websocket.receive_json()
        self.assertEqual(
            snapshot, {"version": 1, "type": "cc.snapshot", "revision": 0, "sessions": []}
        )

        hook = await self.client.post(
            "/hook",
            json={
                "session_id": "session-one",
                "hook_event_name": "Notification",
                "message": "Waiting for your permission",
            },
        )
        self.assertEqual(hook.status, 202)
        delta = await websocket.receive_json()
        self.assertEqual(delta["type"], "cc.state")
        self.assertEqual(delta["cc_code"], 1)
        self.assertEqual(delta["state"], "AWAITING_CONFIRMATION")
        self.assertEqual(delta["revision"], 1)

    async def test_invalid_token_receives_no_snapshot(self):
        websocket = await self.client.ws_connect("/ws")
        await websocket.send_json(
            {"version": 1, "type": "device.hello", "device_id": "stick-s3-01", "token": "bad-token"}
        )
        error = await websocket.receive_json()

        self.assertEqual(error, {"version": 1, "type": "device.error", "error": "UNAUTHORIZED"})
        closed = await websocket.receive()
        self.assertEqual(closed.type, WSMsgType.CLOSE)

    async def test_authenticated_device_receives_pong(self):
        websocket = await self._authenticated_socket()

        await websocket.send_json({"version": 1, "type": "ping"})

        self.assertEqual(await websocket.receive_json(), {"version": 1, "type": "pong"})

    async def _authenticated_socket(self):
        websocket = await self.client.ws_connect("/ws")
        await websocket.send_json(
            {"version": 1, "type": "pair.complete", "device_id": "stick-s3-02", "code": "123456"}
        )
        paired = await websocket.receive_json()
        await websocket.send_json(
            {
                "version": 1,
                "type": "device.hello",
                "device_id": "stick-s3-02",
                "token": paired["token"],
            }
        )
        await websocket.receive_json()
        await websocket.receive_json()
        return websocket


if __name__ == "__main__":
    unittest.main()
