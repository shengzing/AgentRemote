"""Translate verified Claude Code Hook payloads into domain events."""

from typing import Any, Dict

from .models import CcState, NormalizedEvent, Priority


class HookValidationError(ValueError):
    """A Hook request does not contain the minimum safe contract."""


_EVENT_STATES = {
    "UserPromptSubmit": CcState.WORKING,
    "PreToolUse": CcState.WORKING,
    "PostToolUse": CcState.WORKING,
    "SubagentStop": CcState.DONE,
}


def normalize_hook_payload(payload: Dict[str, Any], now: float) -> NormalizedEvent:
    """Normalize a Hook payload without reading the transcript or executing tools."""
    if not isinstance(payload, dict):
        raise HookValidationError("Hook payload must be a JSON object")

    session_id = _required_string(payload, "session_id")
    hook_event_name = _required_string(payload, "hook_event_name")
    message = _optional_string(payload.get("message"))
    cwd = _optional_string(payload.get("cwd"))

    state, priority = _classify(hook_event_name, message)
    return NormalizedEvent(
        session_id=session_id,
        state=state,
        summary=_summary(message or hook_event_name),
        priority=priority,
        cwd=cwd,
        ts=now,
        source_event=hook_event_name,
    )


def _classify(hook_event_name: str, message: str):
    if hook_event_name == "Notification":
        lowered = message.lower()
        if "permission" in lowered or "allow" in lowered or "confirm" in lowered:
            return CcState.AWAITING_CONFIRMATION, Priority.HIGH
        return CcState.AWAITING_INPUT, Priority.HIGH
    if hook_event_name == "Stop":
        lowered = message.lower()
        if any(word in lowered for word in ("error", "failed", "exception", "failure")):
            return CcState.ERROR, Priority.NORMAL
        return CcState.DONE, Priority.NORMAL
    try:
        return _EVENT_STATES[hook_event_name], Priority.NORMAL
    except KeyError as error:
        raise HookValidationError("Unsupported hook event: {0}".format(hook_event_name)) from error


def _required_string(payload: Dict[str, Any], key: str) -> str:
    value = _optional_string(payload.get(key))
    if not value:
        raise HookValidationError("Missing or invalid {0}".format(key))
    return value


def _optional_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _summary(value: str, limit: int = 80) -> str:
    normalized = " ".join(value.split())
    return normalized[:limit]
