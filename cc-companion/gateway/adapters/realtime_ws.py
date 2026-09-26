"""Thin WebSocket adapter: transport I/O only, all logic in DeviceAccessLayer."""

import logging

from aiohttp import WSMsgType, web

from domain.audio import AudioFormat
from protocol.messages import PROTOCOL_VERSION, ProtocolError, decode_client_message
from access import CAPABILITY_DISPLAY, DEFAULT_CAPABILITIES, DeviceAccessLayer, DeviceSession


LOGGER = logging.getLogger(__name__)
ACCESS_LAYER_KEY = web.AppKey("access_layer", DeviceAccessLayer)


class _WsSession:
    """WebSocket implementation of DeviceSession."""

    def __init__(self, websocket: web.WebSocketResponse):
        self._ws = websocket
        self._device_id = ""
        self._capabilities = DEFAULT_CAPABILITIES

    def init(self, device_id: str, capabilities: frozenset):
        self._device_id = device_id
        self._capabilities = capabilities

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def capabilities(self) -> frozenset:
        return self._capabilities

    async def send(self, message: dict) -> None:
        if not self._ws.closed:
            await self._ws.send_json(message)

    async def close(self) -> None:
        if not self._ws.closed:
            await self._ws.close()


async def websocket_handler(request: web.Request) -> web.StreamResponse:
    websocket = web.WebSocketResponse(heartbeat=30.0)
    await websocket.prepare(request)
    access: DeviceAccessLayer = request.app[ACCESS_LAYER_KEY]
    session = _WsSession(websocket)
    active_recording_id = None
    active_recording_seq = 0

    LOGGER.info("WebSocket connected from %s", request.remote)

    try:
        async for incoming in websocket:
            if incoming.type in {WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR}:
                break

            if incoming.type == WSMsgType.BINARY:
                if active_recording_id and session.device_id:
                    error = access.append_audio(
                        session.device_id, active_recording_id,
                        active_recording_seq, bytes(incoming.data),
                    )
                    if error:
                        await _send_transcript_error(websocket, active_recording_id, error)
                        access.cancel_audio(session.device_id, active_recording_id)
                        active_recording_id = None
                    else:
                        active_recording_seq += 1
                continue

            if incoming.type != WSMsgType.TEXT:
                await _send_error(websocket, "INVALID_MESSAGE")
                continue

            try:
                message = decode_client_message(incoming.json())
            except (ProtocolError, ValueError):
                await _send_error(websocket, "INVALID_MESSAGE")
                continue

            message_type = message["type"]

            if message_type == "pair.complete":
                token = access.pair(message["device_id"], message["code"])
                if token is None:
                    await _send_error(websocket, "PAIRING_FAILED")
                else:
                    await websocket.send_json({
                        "version": PROTOCOL_VERSION,
                        "type": "pair.complete",
                        "ok": True,
                        "token": token,
                    })
                continue

            if message_type == "device.hello":
                session.init(message["device_id"], message["capabilities"])
                if access.connect(session, message.get("token", "")):
                    await session.send(_device_ready_message(session.capabilities))
                else:
                    await _send_error(websocket, "UNAUTHORIZED")
                if CAPABILITY_DISPLAY in session.capabilities:
                    await access.push_snapshot(session.device_id)
                continue

            if not session.device_id or not access.is_online(session.device_id):
                await _send_error(websocket, "UNAUTHORIZED")
                await websocket.close()
                break

            if message_type == "ping":
                await websocket.send_json({"version": PROTOCOL_VERSION, "type": "pong"})
            elif message_type == "cc.select":
                access.select_target(session.device_id, message["cc_code"])
            elif message_type == "message.send":
                ack = access.submit_text(session.device_id, message["cc_code"], message["text"])
                await session.send(ack)
            elif message_type == "audio.start":
                if active_recording_id is not None:
                    await _send_error(websocket, "INVALID_AUDIO")
                    continue
                audio_format = AudioFormat(
                    message["sample_rate"],
                    message["sample_width_bits"],
                    message["channels"],
                )
                ok = access.begin_audio(
                    session.device_id, message["recording_id"],
                    message["cc_code"], audio_format,
                )
                if ok:
                    active_recording_id = message["recording_id"]
                    active_recording_seq = 0
                    await websocket.send_json({
                        "version": PROTOCOL_VERSION,
                        "type": "audio.ready",
                        "recording_id": active_recording_id,
                    })
                else:
                    await _send_transcript_error(websocket, message["recording_id"], "AUDIO_START_FAILED")
            elif message_type == "audio.end":
                if message["recording_id"] != active_recording_id:
                    await _send_error(websocket, "INVALID_AUDIO")
                    continue
                recording_id = active_recording_id
                active_recording_id = None
                result = access.finish_audio(session.device_id, recording_id)
                if result.get("ok"):
                    await websocket.send_json({
                        "version": PROTOCOL_VERSION,
                        "type": "transcript.result",
                        "recording_id": recording_id,
                        "ok": True,
                        "text": result["text"],
                    })
                else:
                    await _send_transcript_error(websocket, recording_id, result.get("error", "TRANSCRIPTION_FAILED"))
            else:
                await _send_error(websocket, "INVALID_MESSAGE")

    finally:
        if session.device_id:
            access.disconnect(session.device_id)

    return websocket


def _device_ready_message(capabilities: frozenset) -> dict:
    return {
        "version": PROTOCOL_VERSION,
        "type": "device.ready",
        "capabilities": sorted(capabilities),
    }


async def _send_error(websocket: web.WebSocketResponse, error: str) -> None:
    await websocket.send_json({"version": PROTOCOL_VERSION, "type": "device.error", "error": error})


async def _send_transcript_error(websocket: web.WebSocketResponse, recording_id: str, error: str) -> None:
    await websocket.send_json({
        "version": PROTOCOL_VERSION,
        "type": "transcript.result",
        "recording_id": recording_id,
        "ok": False,
        "error": error,
    })


def configure_routes(app: web.Application) -> None:
    app.router.add_get("/ws", websocket_handler)
