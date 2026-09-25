"""Validate the small v1 device-to-gateway JSON surface."""

from typing import Any, Dict


DEFAULT_CAPABILITIES = frozenset({"input", "display"})
VALID_CAPABILITIES = frozenset({"input", "display", "audio", "select"})


PROTOCOL_VERSION = 1
MAX_CC_CODE = 8


class ProtocolError(ValueError):
    """A device message is not valid for the negotiated protocol version."""


def decode_client_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProtocolError("Message must be an object")
    if payload.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("Unsupported protocol version")
    message_type = payload.get("type")
    if message_type == "ping":
        return {"version": PROTOCOL_VERSION, "type": "ping"}
    if message_type == "pair.complete":
        return {
            "version": PROTOCOL_VERSION,
            "type": "pair.complete",
            "device_id": _device_id(payload.get("device_id")),
            "code": _pairing_code(payload.get("code")),
        }
    if message_type == "device.hello":
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise ProtocolError("token must be a non-empty string")
        capabilities = _capabilities(payload.get("capabilities"))
        return {
            "version": PROTOCOL_VERSION,
            "type": "device.hello",
            "device_id": _device_id(payload.get("device_id")),
            "token": token,
            "capabilities": capabilities,
        }
    if message_type == "cc.select":
        cc_code = payload.get("cc_code")
        if not isinstance(cc_code, int) or not 1 <= cc_code <= MAX_CC_CODE:
            raise ProtocolError("cc_code must be between 1 and 8")
        return {
            "version": PROTOCOL_VERSION,
            "type": "cc.select",
            "cc_code": cc_code,
        }
    if message_type == "audio.start":
        recording_id = _recording_id(payload.get("recording_id"))
        cc_code = payload.get("cc_code")
        if not isinstance(cc_code, int) or not 1 <= cc_code <= MAX_CC_CODE:
            raise ProtocolError("cc_code must be between 1 and 8")
        if (
            payload.get("sample_rate") != 16000
            or payload.get("sample_width_bits") != 16
            or payload.get("channels") != 1
        ):
            raise ProtocolError("audio must be 16-kHz, 16-bit mono PCM")
        return {
            "version": PROTOCOL_VERSION,
            "type": "audio.start",
            "recording_id": recording_id,
            "cc_code": cc_code,
            "sample_rate": 16000,
            "sample_width_bits": 16,
            "channels": 1,
        }
    if message_type == "audio.end":
        return {"version": PROTOCOL_VERSION, "type": "audio.end", "recording_id": _recording_id(payload.get("recording_id"))}
    if message_type == "message.send":
        cc_code = payload.get("cc_code")
        text = payload.get("text")
        if not isinstance(cc_code, int) or not 1 <= cc_code <= MAX_CC_CODE:
            raise ProtocolError("cc_code must be between 1 and 8")
        if not isinstance(text, str):
            raise ProtocolError("text must be a string")
        return {
            "version": PROTOCOL_VERSION,
            "type": "message.send",
            "cc_code": cc_code,
            "text": text,
        }
    raise ProtocolError("Unsupported message type")


def _device_id(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or value.strip() != value:
        raise ProtocolError("device_id must be a non-empty identifier")
    return value


def _pairing_code(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 6 or not value.isdigit():
        raise ProtocolError("code must contain six digits")
    return value


def _recording_id(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or value.strip() != value:
        raise ProtocolError("recording_id must be a non-empty identifier")
    return value


def _capabilities(value: Any) -> frozenset:
    if value is None:
        return DEFAULT_CAPABILITIES
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item in VALID_CAPABILITIES for item in value
    ):
        raise ProtocolError("capabilities must be a list of valid capability names")
    return frozenset(value) if value else DEFAULT_CAPABILITIES
