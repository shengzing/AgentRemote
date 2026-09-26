"""Transport-independent device access layer."""

import asyncio
import logging
import time
from typing import Dict, Optional

from adapters.pairing import PairingService
from adapters.tmux import InjectError, InjectResult, TmuxInjector
from domain.audio import AudioFormat, AudioValidationError, RecordingService
from domain.registry import SessionRegistry
from protocol.messages import PROTOCOL_VERSION

from .capabilities import CAPABILITY_DISPLAY
from .messages import snapshot_message, state_message
from .session import DeviceSession


LOGGER = logging.getLogger(__name__)


class DeviceAccessLayer:
    """The sole entry point for device adapters: pairing, actions, and state push."""

    def __init__(
        self,
        pairing: PairingService,
        registry: SessionRegistry,
        tmux: TmuxInjector,
        recording: RecordingService,
        require_pairing: bool = False,
    ):
        self._pairing = pairing
        self._registry = registry
        self._tmux = tmux
        self._recording = recording
        self._require_pairing = require_pairing
        self._sessions: Dict[str, DeviceSession] = {}
        self._active_recordings: Dict[str, str] = {}

    # -- Lifecycle --

    def pair(self, device_id: str, code: str) -> Optional[str]:
        """Exchange a pairing code for a token. Returns None on failure."""
        return self._pairing.complete(device_id, code)

    def auto_pair(self, device_id: str) -> str:
        """Auto-pair for personal use: generate and store a token for the device."""
        import secrets
        token = secrets.token_urlsafe(32)
        from adapters.pairing import _hash_token
        tokens = self._pairing._store.load()
        tokens[device_id] = _hash_token(token)
        self._pairing._store.save(tokens)
        return token

    def connect(self, session: DeviceSession, token: str) -> bool:
        """Authenticate and register a session. Does not push snapshot."""
        if self._require_pairing and not self._pairing.verify(session.device_id, token):
            return False
        self._sessions[session.device_id] = session
        return True

    def disconnect(self, device_id: str) -> None:
        """Clean up: cancel active recording and unregister session."""
        recording_id = self._active_recordings.pop(device_id, None)
        if recording_id is not None:
            self.cancel_audio(device_id, recording_id)
        self._sessions.pop(device_id, None)
        LOGGER.info("Device disconnected: %s", device_id)

    def is_online(self, device_id: str) -> bool:
        return device_id in self._sessions

    def online_device_ids(self) -> frozenset:
        return frozenset(self._sessions.keys())

    # -- Inbound actions (device -> gateway) --

    def select_target(self, device_id: str, cc_code: int) -> None:
        """Optional: record device's current target CC. v0.1 logs only."""
        LOGGER.info("Device %s selected CC %d", device_id, cc_code)

    def submit_text(self, device_id: str, cc_code: int, text: str) -> dict:
        """Submit text -> validate target -> tmux inject -> return ack dict."""
        if not self._registry.has_cc_code(cc_code, now=time.time()):
            result = InjectResult(ok=False, text="", error=InjectError.TARGET_UNREACHABLE)
        else:
            result = self._tmux.inject(cc_code, text)
        return self._build_ack(cc_code, result)

    def begin_audio(self, device_id: str, recording_id: str,
                    cc_code: int, audio_format: AudioFormat) -> bool:
        """Start a recording session. Returns False if device offline or already recording."""
        if device_id not in self._sessions:
            return False
        if device_id in self._active_recordings:
            return False
        try:
            self._recording.begin(recording_id, cc_code, audio_format)
            self._active_recordings[device_id] = recording_id
            return True
        except AudioValidationError:
            return False

    def append_audio(self, device_id: str, recording_id: str,
                     sequence: int, pcm: bytes) -> Optional[str]:
        """Append a PCM chunk. Returns error description or None."""
        if self._active_recordings.get(device_id) != recording_id:
            return "RECORDING_NOT_ACTIVE"
        try:
            self._recording.append(recording_id, sequence, pcm)
            return None
        except AudioValidationError as error:
            return str(error)

    def finish_audio(self, device_id: str, recording_id: str) -> dict:
        """Finish a recording -> transcribe -> return result dict."""
        if self._active_recordings.get(device_id) != recording_id:
            return {"ok": False, "error": "RECORDING_NOT_ACTIVE"}
        self._active_recordings.pop(device_id, None)
        try:
            transcript = self._recording.finish(recording_id)
            return {"ok": True, "text": transcript}
        except AudioValidationError as error:
            return {"ok": False, "error": str(error)}

    def cancel_audio(self, device_id: str, recording_id: str) -> None:
        """Cancel a recording."""
        if self._active_recordings.get(device_id) == recording_id:
            self._active_recordings.pop(device_id, None)
        try:
            self._recording.cancel(recording_id)
        except AudioValidationError:
            pass

    # -- Outbound push (gateway -> device, display-only) --

    async def broadcast_state(self, session, revision: int) -> None:
        """Push a state delta to all online display-capable devices."""
        message = state_message(session, revision)
        await self._fan_out(message, require_capability=CAPABILITY_DISPLAY)

    async def push_snapshot(self, device_id: str) -> None:
        """Push a full snapshot to one device (display-capable only)."""
        session = self._sessions.get(device_id)
        if session and CAPABILITY_DISPLAY in session.capabilities:
            snapshot = self._registry.snapshot(now=time.time())
            await session.send(snapshot_message(snapshot))

    async def send_error(self, device_id: str, error_code: str) -> None:
        """Push an error to a device."""
        session = self._sessions.get(device_id)
        if session:
            await session.send({
                "version": PROTOCOL_VERSION,
                "type": "device.error",
                "error": error_code,
            })

    # -- Internal --

    async def _fan_out(self, message: dict, require_capability: str) -> None:
        targets = [
            session for session in self._sessions.values()
            if require_capability in session.capabilities
        ]
        if not targets:
            return
        results = await asyncio.gather(
            *(session.send(message) for session in targets),
            return_exceptions=True,
        )
        if any(isinstance(result, Exception) for result in results):
            LOGGER.warning("A device failed to accept a state update")

    @staticmethod
    def _build_ack(cc_code: int, result: InjectResult) -> dict:
        ack = {
            "version": PROTOCOL_VERSION,
            "type": "message.ack",
            "cc_code": cc_code,
            "ok": result.ok,
            "text": result.text,
        }
        if result.warning:
            ack["warning"] = result.warning
        if result.error:
            ack["error"] = result.error.value
        return ack
