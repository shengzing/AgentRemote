"""aiohttp adapter for receiving Claude Code Hook events."""

import logging
from pathlib import Path

from aiohttp import web

from adapters.hooks import HookService
from domain.normalizer import HookValidationError
from domain.registry import SessionLimitError


LOGGER = logging.getLogger(__name__)
HOOK_SERVICE_KEY = web.AppKey("hook_service", HookService)


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def simulator(request: web.Request) -> web.FileResponse:
    simulator_root = Path(__file__).resolve().parent.parent / "simulator"
    return web.FileResponse(simulator_root / "index.html")


async def simulator_asset(request: web.Request) -> web.FileResponse:
    asset_name = request.match_info["asset"]
    if asset_name not in {"simulator.css", "simulator.js"}:
        raise web.HTTPNotFound()
    simulator_root = Path(__file__).resolve().parent.parent / "simulator"
    return web.FileResponse(simulator_root / asset_name)


async def voice_terminal(request: web.Request) -> web.FileResponse:
    terminal_root = Path(__file__).resolve().parent.parent / "voice-terminal"
    return web.FileResponse(terminal_root / "index.html")


async def voice_terminal_asset(request: web.Request) -> web.FileResponse:
    asset_name = request.match_info["asset"]
    if asset_name not in {"terminal.css", "terminal.js"}:
        raise web.HTTPNotFound()
    terminal_root = Path(__file__).resolve().parent.parent / "voice-terminal"
    return web.FileResponse(terminal_root / asset_name)


async def m5_simulator(request: web.Request) -> web.FileResponse:
    simulator_root = Path(__file__).resolve().parent.parent / "m5-simulator"
    return web.FileResponse(simulator_root / "index.html")


async def m5_simulator_asset(request: web.Request) -> web.FileResponse:
    asset_name = request.match_info["asset"]
    if asset_name not in {"m5.css", "m5.js"}:
        raise web.HTTPNotFound()
    simulator_root = Path(__file__).resolve().parent.parent / "m5-simulator"
    return web.FileResponse(simulator_root / asset_name)


async def receive_hook(request: web.Request) -> web.Response:
    service = request.app[HOOK_SERVICE_KEY]
    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "INVALID_JSON"}, status=400)

    try:
        session = service.accept(payload)
    except HookValidationError as error:
        LOGGER.warning("Rejected malformed Hook request: %s", error)
        return web.json_response({"error": "INVALID_HOOK"}, status=400)
    except SessionLimitError:
        LOGGER.warning("Rejected Hook because the active session limit was reached")
        return web.json_response({"error": "SESSION_LIMIT_REACHED"}, status=429)

    revision = service.registry.snapshot(now=session.updated_at).revision
    return web.json_response(
        {
            "accepted": True,
            "cc_code": session.cc_code,
            "state": session.state.value,
            "revision": revision,
        },
        status=202,
    )


def configure_routes(app: web.Application) -> None:
    app.router.add_get("/health", health)
    app.router.add_post("/hook", receive_hook)
    app.router.add_get("/simulator", simulator)
    app.router.add_get("/simulator/{asset}", simulator_asset)
    app.router.add_get("/terminal", voice_terminal)
    app.router.add_get("/terminal/{asset}", voice_terminal_asset)
    app.router.add_get("/m5", m5_simulator)
    app.router.add_get("/m5/{asset}", m5_simulator_asset)
