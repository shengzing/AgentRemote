"""Transport-independent device access layer."""

import asyncio
import logging
import time
from typing import Dict, Optional

from adapters.pairing import PairingService
from adapters.tmux import InjectError, InjectResult, TmuxInjector
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
        require_pairing: bool = False,
    ):
        self._pairing = pairing
        self._registry = registry
        self._tmux = tmux
        self._require_pairing = require_pairing
        self._sessions: Dict[str, DeviceSession] = {}

    # -- Lifecycle --

    def pair(self, device_id: str, code: str) -> Optional[str]:
        """Exchange a pairing code for a token. Returns None on failure."""
        return self._pairing.complete(device_id, code)

    def connect(self, session: DeviceSession, token: str) -> bool:
        """Authenticate and register a session. Does not push snapshot."""
        if self._require_pairing and not self._pairing.verify(session.device_id, token):
            return False
        self._sessions[session.device_id] = session
        return True

    def disconnect(self, device_id: str) -> None:
        """Unregister a device session."""
        self._sessions.pop(device_id, None)
        LOGGER.info("Device disconnected: %s", device_id)

    def is_online(self, device_id: str) -> bool:
        return device_id in self._sessions

    def registry_has_cc_code(self, cc_code: int) -> bool:
        return self._registry.has_cc_code(cc_code, now=time.time())

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
