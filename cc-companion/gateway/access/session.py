"""Protocol for outbound device communication."""

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class DeviceSession(Protocol):
    """An authenticated device's outbound channel (gateway -> device)."""

    @property
    def device_id(self) -> str:
        ...

    @property
    def capabilities(self) -> frozenset:
        ...

    async def send(self, message: Dict[str, Any]) -> None:
        """Push a JSON message to the device."""
        ...

    async def close(self) -> None:
        """Close the device connection."""
        ...
