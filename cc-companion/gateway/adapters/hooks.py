"""Transport-independent Hook service used by the future HTTP adapter."""

import time
from typing import Any, Dict, Optional

from domain.normalizer import normalize_hook_payload
from domain.registry import SessionRegistry


class HookService:
    def __init__(self, registry: SessionRegistry, on_session_updated=None):
        self.registry = registry
        self._on_session_updated = on_session_updated

    def accept(self, payload: Dict[str, Any], now: Optional[float] = None):
        event = normalize_hook_payload(payload, time.time() if now is None else now)
        session = self.registry.apply(event)
        if self._on_session_updated:
            self._on_session_updated(session, self.registry.snapshot(now=session.updated_at).revision)
        return session
