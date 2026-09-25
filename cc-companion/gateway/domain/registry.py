"""In-memory authoritative state for active Claude Code sessions."""

from typing import Dict

from .models import NormalizedEvent, Session, Snapshot


class SessionLimitError(RuntimeError):
    """No code remains for a newly observed Claude Code session."""


class SessionRegistry:
    def __init__(self, max_sessions: int = 8, expiry_seconds: float = 1800.0):
        if max_sessions < 1:
            raise ValueError("max_sessions must be positive")
        self._max_sessions = max_sessions
        self._expiry_seconds = expiry_seconds
        self._sessions: Dict[str, Session] = {}
        self._revision = 0

    def apply(self, event: NormalizedEvent) -> Session:
        current = self._sessions.get(event.session_id)
        cc_code = current.cc_code if current else self._allocate_code()
        session = Session(
            session_id=event.session_id,
            cc_code=cc_code,
            state=event.state,
            summary=event.summary,
            priority=event.priority,
            cwd=event.cwd,
            updated_at=event.ts,
        )
        self._sessions[event.session_id] = session
        self._revision += 1
        return session

    def expire(self, now: float) -> int:
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.updated_at >= self._expiry_seconds
        ]
        for session_id in expired_ids:
            del self._sessions[session_id]
        if expired_ids:
            self._revision += 1
        return len(expired_ids)

    def snapshot(self, now: float) -> Snapshot:
        self.expire(now)
        ordered = tuple(sorted(self._sessions.values(), key=lambda session: session.cc_code))
        return Snapshot(revision=self._revision, sessions=ordered)

    def has_cc_code(self, cc_code: int, now: float) -> bool:
        self.expire(now)
        return any(session.cc_code == cc_code for session in self._sessions.values())

    def _allocate_code(self) -> int:
        used = {session.cc_code for session in self._sessions.values()}
        for code in range(1, self._max_sessions + 1):
            if code not in used:
                return code
        raise SessionLimitError("Maximum active Claude Code sessions reached")
