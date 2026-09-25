"""Build outbound protocol messages shared by all device transports."""

from protocol.messages import PROTOCOL_VERSION


def state_message(session, revision: int) -> dict:
    return {
        "version": PROTOCOL_VERSION,
        "type": "cc.state",
        "revision": revision,
        "cc_code": session.cc_code,
        "state": session.state.value,
        "summary": session.summary,
        "priority": session.priority.value,
        "ts": int(session.updated_at),
    }


def snapshot_message(snapshot) -> dict:
    return {
        "version": PROTOCOL_VERSION,
        "type": "cc.snapshot",
        "revision": snapshot.revision,
        "sessions": [_session_payload(session) for session in snapshot.sessions],
    }


def _session_payload(session) -> dict:
    return {
        "cc_code": session.cc_code,
        "state": session.state.value,
        "summary": session.summary,
        "priority": session.priority.value,
        "ts": int(session.updated_at),
    }
