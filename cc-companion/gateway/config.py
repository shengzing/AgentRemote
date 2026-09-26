"""Runtime configuration loaded from explicit environment variables."""

import os
from dataclasses import dataclass
from typing import Dict, Optional


class ConfigError(ValueError):
    """An operator-provided configuration value is invalid."""


@dataclass(frozen=True)
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 7421
    max_sessions: int = 8
    session_expiry_seconds: float = 1800.0
    tmux_targets: Dict[int, str] = None
    pairing_store: str = ".cc-companion-pairings.json"
    pairing_code: Optional[str] = None
    pairing_expiry_seconds: float = 600.0
    require_pairing: bool = False

    def __post_init__(self):
        if not 1 <= self.max_sessions <= 8:
            raise ConfigError("max_sessions must be between 1 and 8")
        if not 1 <= self.port <= 65535:
            raise ConfigError("port must be between 1 and 65535")
        if not isinstance(self.pairing_store, str) or not self.pairing_store.strip():
            raise ConfigError("pairing_store must be a non-empty path")
        if self.pairing_code is not None and (
            not isinstance(self.pairing_code, str)
            or len(self.pairing_code) != 6
            or not self.pairing_code.isdigit()
        ):
            raise ConfigError("pairing_code must contain exactly six digits")
        if self.pairing_expiry_seconds <= 0:
            raise ConfigError("pairing_expiry_seconds must be positive")
        if not isinstance(self.require_pairing, bool):
            raise ConfigError("require_pairing must be a boolean")
        object.__setattr__(self, "tmux_targets", dict(self.tmux_targets or {}))

    @classmethod
    def from_environment(cls):
        return cls(
            host=os.environ.get("CC_COMPANION_HOST", "127.0.0.1"),
            port=_positive_int(os.environ.get("CC_COMPANION_PORT", "7421"), "CC_COMPANION_PORT"),
            max_sessions=_positive_int(
                os.environ.get("CC_COMPANION_MAX_SESSIONS", "8"), "CC_COMPANION_MAX_SESSIONS"
            ),
            session_expiry_seconds=_positive_float(
                os.environ.get("CC_COMPANION_SESSION_EXPIRY", "1800"), "CC_COMPANION_SESSION_EXPIRY"
            ),
            tmux_targets=parse_tmux_targets(os.environ.get("CC_COMPANION_TMUX_TARGETS", "")),
            pairing_store=os.environ.get("CC_COMPANION_PAIRING_STORE", ".cc-companion-pairings.json"),
            pairing_code=os.environ.get("CC_COMPANION_PAIRING_CODE") or None,
            pairing_expiry_seconds=_positive_float(
                os.environ.get("CC_COMPANION_PAIRING_EXPIRY", "600"),
                "CC_COMPANION_PAIRING_EXPIRY",
            ),
            require_pairing=os.environ.get("CC_COMPANION_REQUIRE_PAIRING", "false").lower() in ("true", "1", "yes"),
        )


def parse_tmux_targets(value: str) -> Dict[int, str]:
    """Parse `1=cc1,2=cc2` without accepting arbitrary shell syntax."""
    targets = {}
    if not value.strip():
        return targets
    for part in value.split(","):
        code_text, separator, target = part.partition("=")
        if not separator or not target.strip():
            raise ConfigError("CC_COMPANION_TMUX_TARGETS must use code=target pairs")
        code = _positive_int(code_text.strip(), "tmux target code")
        if code > 8 or code in targets:
            raise ConfigError("tmux target codes must be unique and between 1 and 8")
        targets[code] = target.strip()
    return targets


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigError("{0} must be an integer".format(name)) from error
    if parsed < 1:
        raise ConfigError("{0} must be positive".format(name))
    return parsed


def _positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigError("{0} must be a number".format(name)) from error
    if parsed <= 0:
        raise ConfigError("{0} must be positive".format(name))
    return parsed
