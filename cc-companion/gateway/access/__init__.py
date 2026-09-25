"""Device access layer: transport-independent pairing, session, and action routing."""

from .capabilities import (
    CAPABILITY_AUDIO,
    CAPABILITY_DISPLAY,
    CAPABILITY_INPUT,
    CAPABILITY_SELECT,
    DEFAULT_CAPABILITIES,
)
from .layer import DeviceAccessLayer
from .session import DeviceSession

__all__ = [
    "CAPABILITY_AUDIO",
    "CAPABILITY_DISPLAY",
    "CAPABILITY_INPUT",
    "CAPABILITY_SELECT",
    "DEFAULT_CAPABILITIES",
    "DeviceAccessLayer",
    "DeviceSession",
]
