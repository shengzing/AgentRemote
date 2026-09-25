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
from domain.audio import RecordingService


class RecordingRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)

        class Result:
            returncode = 0

        return Result()


class StaticTranscriber:
    def __init__(self):
        self.calls = []

    def transcribe(self, pcm, audio_format):
        self.calls.append((pcm, audio_format))
        return "Allow this command"


class RealtimeAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.runner = RecordingRunner()
        self.transcriber = StaticTranscriber()
        self.app = create_app(
            GatewayConfig(tmux_targets={1: "cc1"}),
            pairing_service=PairingService(
                PairingStore(Path(self.temporary_directory.name) / "pairings.json"),
                pairing_code="123456",
            ),
            tmux_injector=TmuxInjector({1: "cc1"}, runner=self.runner),
            recording_service=RecordingService(self.transcriber),
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
        self.assertEqual(snapshot, {"version": 1, "type": "cc.snapshot", "revision": 0, "sessions": []})

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

    async def test_send_injects_active_target_and_returns_ack(self):
        hook = await self.client.post(
            "/hook",
            json={
                "session_id": "session-one",
                "hook_event_name": "UserPromptSubmit",
                "message": "Work",
            },
        )
        self.assertEqual(hook.status, 202)

        websocket = await self._authenticated_socket()
        await websocket.send_json({"version": 1, "type": "message.send", "cc_code": 1, "text": "continue\nignored"})
        acknowledgement = await websocket.receive_json()

        self.assertEqual(acknowledgement["type"], "message.ack")
        self.assertTrue(acknowledgement["ok"])
        self.assertEqual(acknowledgement["text"], "continue")
        self.assertEqual(acknowledgement["warning"], "MULTILINE_TRUNCATED")
        self.assertEqual(
            self.runner.calls,
            [
                ["tmux", "send-keys", "-t", "cc1", "-l", "--", "continue"],
                ["tmux", "send-keys", "-t", "cc1", "Enter"],
            ],
        )

    async def test_send_to_a_code_without_a_live_session_does_not_invoke_tmux(self):
        websocket = await self._authenticated_socket()
        await websocket.send_json({"version": 1, "type": "message.send", "cc_code": 1, "text": "continue"})

        acknowledgement = await websocket.receive_json()

        self.assertEqual(acknowledgement["type"], "message.ack")
        self.assertFalse(acknowledgement["ok"])
        self.assertEqual(acknowledgement["error"], "TARGET_UNREACHABLE")
        self.assertEqual(self.runner.calls, [])

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

    async def test_audio_binary_chunks_return_a_transcript_for_an_active_cc(self):
        hook = await self.client.post(
            "/hook",
            json={
                "session_id": "session-one",
                "hook_event_name": "UserPromptSubmit",
                "message": "Work",
            },
        )
        self.assertEqual(hook.status, 202)
        websocket = await self._authenticated_socket()

        await websocket.send_json(
            {
                "version": 1,
                "type": "audio.start",
                "recording_id": "recording-1",
                "cc_code": 1,
                "sample_rate": 16000,
                "sample_width_bits": 16,
                "channels": 1,
            }
        )
        self.assertEqual(await websocket.receive_json(), {"version": 1, "type": "audio.ready", "recording_id": "recording-1"})
        await websocket.send_bytes(b"\x00" * 16000)
        await websocket.send_json({"version": 1, "type": "audio.end", "recording_id": "recording-1"})

        result = await websocket.receive_json()
        self.assertEqual(
            result,
            {
                "version": 1,
                "type": "transcript.result",
                "recording_id": "recording-1",
                "cc_code": 1,
                "ok": True,
                "text": "Allow this command",
            },
        )
        self.assertEqual(len(self.transcriber.calls), 1)

    async def test_audio_for_inactive_cc_is_rejected_without_starting_a_recording(self):
        websocket = await self._authenticated_socket()
        await websocket.send_json(
            {
                "version": 1,
                "type": "audio.start",
                "recording_id": "recording-inactive",
                "cc_code": 1,
                "sample_rate": 16000,
                "sample_width_bits": 16,
                "channels": 1,
            }
        )

        self.assertEqual(
            await websocket.receive_json(),
            {"version": 1, "type": "device.error", "error": "TARGET_UNREACHABLE"},
        )
        self.assertEqual(self.transcriber.calls, [])

    async def test_unconfigured_transcription_returns_a_recoverable_error(self):
        app = create_app(
            GatewayConfig(tmux_targets={1: "cc1"}),
            pairing_service=PairingService(
                PairingStore(Path(self.temporary_directory.name) / "unconfigured-pairings.json"),
                pairing_code="123456",
            ),
        )
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        try:
            hook = await client.post(
                "/hook",
                json={"session_id": "session-one", "hook_event_name": "UserPromptSubmit", "message": "Work"},
            )
            self.assertEqual(hook.status, 202)
            websocket = await client.ws_connect("/ws")
            await websocket.send_json(
                {"version": 1, "type": "pair.complete", "device_id": "stick-s3-03", "code": "123456"}
            )
            paired = await websocket.receive_json()
            await websocket.send_json(
                {"version": 1, "type": "device.hello", "device_id": "stick-s3-03", "token": paired["token"]}
            )
            await websocket.receive_json()
            await websocket.receive_json()
            await websocket.send_json(
                {
                    "version": 1,
                    "type": "audio.start",
                    "recording_id": "recording-unconfigured",
                    "cc_code": 1,
                    "sample_rate": 16000,
                    "sample_width_bits": 16,
                    "channels": 1,
                }
            )
            await websocket.receive_json()
            await websocket.send_bytes(b"\x00" * 16000)
            await websocket.send_json(
                {"version": 1, "type": "audio.end", "recording_id": "recording-unconfigured"}
            )
            self.assertEqual(
                await websocket.receive_json(),
                {
                    "version": 1,
                    "type": "transcript.result",
                    "recording_id": "recording-unconfigured",
                    "ok": False,
                    "error": "TRANSCRIPTION_NOT_CONFIGURED",
                },
            )
        finally:
            await client.close()

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
