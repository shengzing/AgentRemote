"""Composition root for the LAN gateway's current M1 HTTP surface."""

import logging
import os
import secrets
import time
from pathlib import Path

from aiohttp import web

from access import DeviceAccessLayer
from adapters.hooks import HookService
from adapters.http import HOOK_SERVICE_KEY, configure_routes as configure_http_routes
from adapters.pairing import PairingService, PairingStore
from adapters.realtime_ws import ACCESS_LAYER_KEY, configure_routes as configure_realtime_routes
from adapters.tmux import TmuxInjector
from config import GatewayConfig
from domain.registry import SessionRegistry


CONFIG_KEY = web.AppKey("config", GatewayConfig)


def create_app(config: GatewayConfig = None, pairing_service=None, tmux_injector=None, recording_service=None) -> web.Application:
    config = config or GatewayConfig.from_environment()
    registry = SessionRegistry(
        max_sessions=config.max_sessions,
        expiry_seconds=config.session_expiry_seconds,
        pinned_codes=set(config.tmux_targets.keys()),
    )

    app = web.Application()

    pairing_service = pairing_service or PairingService(
        PairingStore(Path(config.pairing_store)),
        pairing_code=config.pairing_code or _new_pairing_code(),
        expires_after_seconds=config.pairing_expiry_seconds,
    )
    tmux_injector = tmux_injector or TmuxInjector(config.tmux_targets)
    access_layer = DeviceAccessLayer(
        pairing=pairing_service,
        registry=registry,
        tmux=tmux_injector,
        require_pairing=config.require_pairing,
    )

    def publish(session, revision):
        # Hook processing is synchronous; schedule the async fan-out on its request loop.
        __import__("asyncio").get_running_loop().create_task(
            access_layer.broadcast_state(session, revision)
        )

    app[CONFIG_KEY] = config
    app[HOOK_SERVICE_KEY] = HookService(registry, on_session_updated=publish)
    app[ACCESS_LAYER_KEY] = access_layer
    configure_http_routes(app)
    configure_realtime_routes(app)
    return app


def _new_pairing_code() -> str:
    return "{0:06d}".format(secrets.randbelow(1000000))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = GatewayConfig.from_environment()
    pairing_code = config.pairing_code or _new_pairing_code()
    app = create_app(config)
    if config.require_pairing:
        logging.getLogger(__name__).info("Companion pairing code: %s", pairing_code)
    else:
        logging.getLogger(__name__).info("Pairing disabled: devices auto-register on connect")
    web.run_app(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
