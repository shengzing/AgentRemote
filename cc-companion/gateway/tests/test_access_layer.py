"""Pure-logic unit tests for DeviceAccessLayer (no aiohttp dependency)."""

import tempfile
import unittest
import time
from pathlib import Path

from access import CAPABILITY_DISPLAY, DeviceAccessLayer
from adapters.pairing import PairingService, PairingStore
from adapters.tmux import InjectError, InjectResult, TmuxInjector
from domain.audio import AudioFormat, RecordingService
from domain.models import CcState, Priority, Session
from domain.registry import SessionRegistry


class FakeDeviceSession:
    def __init__(self, device_id, capabilities):
        self._device_id = device_id
        self._capabilities = capabilities
        self.sent_messages = []
        self.closed = False

    @property
    def device_id(self):
        return self._device_id

    @property
    def capabilities(self):
        return self._capabilities

    async def send(self, message):
        self.sent_messages.append(message)

    async def close(self):
        self.closed = True


class FakeTranscriber:
    def transcribe(self, pcm, audio_format):
        return "Allow this command"


class DeviceAccessLayerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pairing = PairingService(
            PairingStore(Path(self.temp_dir.name) / "pairings.json"),
            pairing_code="123456",
        )
        self.registry = SessionRegistry(max_sessions=8)
        self.tmux = TmuxInjector({1: "cc1"}, runner=_fake_tmux_runner)
        self.recording = RecordingService(FakeTranscriber())
        self.access = DeviceAccessLayer(
            pairing=self.pairing,
            registry=self.registry,
            tmux=self.tmux,
            recording=self.recording,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _pair_and_connect(self, device_id="dev-1", capabilities=frozenset({"input", "display"})):
        token = self.access.pair(device_id, "123456")
        self.assertIsNotNone(token)
        session = FakeDeviceSession(device_id, capabilities)
        ok = self.access.connect(session, token)
        self.assertTrue(ok)
        return session

    async def test_pair_and_connect_success(self):
        session = self._pair_and_connect()
        self.assertTrue(self.access.is_online("dev-1"))
        self.assertEqual(self.access.online_device_ids(), frozenset({"dev-1"}))

    async def test_connect_with_wrong_token_fails(self):
        token = self.access.pair("dev-1", "123456")
        session = FakeDeviceSession("dev-1", frozenset({"input"}))
        ok = self.access.connect(session, "wrong-token")
        self.assertFalse(ok)
        self.assertFalse(self.access.is_online("dev-1"))

    async def test_display_device_gets_snapshot(self):
        session = self._pair_and_connect("dev-display")
        await self.access.push_snapshot("dev-display")
        self.assertEqual(len(session.sent_messages), 1)
        self.assertEqual(session.sent_messages[0]["type"], "cc.snapshot")

    async def test_input_only_device_gets_no_snapshot(self):
        session = self._pair_and_connect("dev-input", capabilities=frozenset({"input"}))
        await self.access.push_snapshot("dev-input")
        self.assertEqual(len(session.sent_messages), 0)

    async def test_broadcast_state_filters_display(self):
        display_session = self._pair_and_connect("dev-display")
        input_session = self._pair_and_connect("dev-input", capabilities=frozenset({"input"}))
        cc_session = Session(
            session_id="s1", cc_code=1, state=CcState.WORKING,
            summary="working", priority=Priority.NORMAL,
            cwd="/tmp", updated_at=1000.0,
        )
        await self.access.broadcast_state(cc_session, 1)
        self.assertEqual(len(display_session.sent_messages), 1)
        self.assertEqual(display_session.sent_messages[0]["type"], "cc.state")
        self.assertEqual(len(input_session.sent_messages), 0)

    async def test_submit_text_ok(self):
        self._pair_and_connect()
        self.registry.apply(_make_event("s1", 1))
        ack = self.access.submit_text("dev-1", 1, "allow")
        self.assertTrue(ack["ok"])
        self.assertEqual(ack["text"], "allow")
        self.assertEqual(ack["cc_code"], 1)

    async def test_submit_text_target_unreachable(self):
        self._pair_and_connect()
        ack = self.access.submit_text("dev-1", 5, "allow")
        self.assertFalse(ack["ok"])
        self.assertEqual(ack["error"], "TARGET_UNREACHABLE")

    async def test_submit_text_multiline_truncated(self):
        self._pair_and_connect()
        self.registry.apply(_make_event("s1", 1))
        ack = self.access.submit_text("dev-1", 1, "first line\nsecond line")
        self.assertTrue(ack["ok"])
        self.assertEqual(ack["text"], "first line")
        self.assertEqual(ack["warning"], "MULTILINE_TRUNCATED")

    async def test_disconnect_cleans_up(self):
        self._pair_and_connect()
        self.access.disconnect("dev-1")
        self.assertFalse(self.access.is_online("dev-1"))

    async def test_disconnect_cancels_active_recording(self):
        session = self._pair_and_connect()
        self.registry.apply(_make_event("s1", 1))
        fmt = AudioFormat(sample_rate=16000, sample_width_bits=16, channels=1)
        ok = self.access.begin_audio("dev-1", "rec-1", 1, fmt)
        self.assertTrue(ok)
        self.access.disconnect("dev-1")
        result = self.access.finish_audio("dev-1", "rec-1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "RECORDING_NOT_ACTIVE")

    async def test_begin_append_finish_audio(self):
        self._pair_and_connect()
        self.registry.apply(_make_event("s1", 1))
        fmt = AudioFormat(sample_rate=16000, sample_width_bits=16, channels=1)
        ok = self.access.begin_audio("dev-1", "rec-1", 1, fmt)
        self.assertTrue(ok)
        pcm = b"\x00" * 16000  # 0.5 seconds of silence
        err = self.access.append_audio("dev-1", "rec-1", 0, pcm)
        self.assertIsNone(err)
        result = self.access.finish_audio("dev-1", "rec-1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "Allow this command")

    async def test_append_audio_wrong_device_rejected(self):
        self._pair_and_connect("dev-a")
        self._pair_and_connect("dev-b")
        self.registry.apply(_make_event("s1", 1))
        fmt = AudioFormat(sample_rate=16000, sample_width_bits=16, channels=1)
        self.access.begin_audio("dev-a", "rec-a", 1, fmt)
        err = self.access.append_audio("dev-b", "rec-a", 0, b"\x00" * 100)
        self.assertEqual(err, "RECORDING_NOT_ACTIVE")

    async def test_multi_device_concurrent(self):
        session_a = self._pair_and_connect("dev-a")
        session_b = self._pair_and_connect("dev-b")
        self.registry.apply(_make_event("s1", 1))
        ack_a = self.access.submit_text("dev-a", 1, "hello")
        ack_b = self.access.submit_text("dev-b", 1, "world")
        self.assertTrue(ack_a["ok"])
        self.assertTrue(ack_b["ok"])


def _fake_tmux_runner(args, **kwargs):
    class Result:
        returncode = 0
    return Result()


def _make_event(session_id, cc_code):
    from domain.models import NormalizedEvent
    return NormalizedEvent(
        session_id=session_id,
        state=CcState.WORKING,
        summary="working",
        priority=Priority.NORMAL,
        cwd="/tmp",
        ts=time.time(),
        source_event="UserPromptSubmit",
    )


if __name__ == "__main__":
    unittest.main()
