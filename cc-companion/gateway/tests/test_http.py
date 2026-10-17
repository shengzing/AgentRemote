import unittest

from aiohttp.test_utils import TestClient, TestServer

from app import create_app
from config import GatewayConfig


class HookHttpAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = TestServer(create_app(GatewayConfig()))
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_hook_returns_state_and_stable_code(self):
        payload = {
            "session_id": "local-session",
            "hook_event_name": "Notification",
            "message": "Waiting for your permission",
        }

        first = await self.client.post("/hook", json=payload)
        first_body = await first.json()
        second = await self.client.post(
            "/hook",
            json={
                "session_id": "local-session",
                "hook_event_name": "Stop",
                "message": "Finished",
            },
        )
        second_body = await second.json()

        self.assertEqual(first.status, 202)
        self.assertEqual(first_body, {"accepted": True, "cc_code": 1, "state": "AWAITING_CONFIRMATION", "revision": 1})
        self.assertEqual(second.status, 202)
        self.assertEqual(second_body["cc_code"], 1)
        self.assertEqual(second_body["state"], "DONE")
        self.assertEqual(second_body["revision"], 2)

    async def test_invalid_json_and_invalid_payload_are_rejected(self):
        invalid_json = await self.client.post("/hook", data="not json", headers={"Content-Type": "application/json"})
        invalid_payload = await self.client.post("/hook", json={"hook_event_name": "Stop"})

        self.assertEqual(invalid_json.status, 400)
        self.assertEqual(await invalid_json.json(), {"error": "INVALID_JSON"})
        self.assertEqual(invalid_payload.status, 400)
        self.assertEqual(await invalid_payload.json(), {"error": "INVALID_HOOK"})

    async def test_terminal_page_is_served_from_the_gateway_origin(self):
        response = await self.client.get("/terminal")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/html")
        self.assertIn("Claude Code Terminal", await response.text())

    async def test_terminal_assets_are_served_from_the_gateway_origin(self):
        stylesheet = await self.client.get("/terminal/terminal.css")
        script = await self.client.get("/terminal/terminal.js")

        self.assertEqual(stylesheet.status, 200)
        self.assertIn("--bg", await stylesheet.text())
        self.assertEqual(script.status, 200)
        self.assertIn("new WebSocket", await script.text())


if __name__ == "__main__":
    unittest.main()
