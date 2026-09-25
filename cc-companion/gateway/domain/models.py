"""Gateway domain values with no dependency on transport libraries."""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class CcState(str, Enum):
    WORKING = "WORKING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    AWAITING_INPUT = "AWAITING_INPUT"
    DONE = "DONE"
    ERROR = "ERROR"
    IDLE = "IDLE"


class Priority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"


@dataclass(frozen=True)
class NormalizedEvent:
    session_id: str
    state: CcState
    summary: str
    priority: Priority
    cwd: str
    ts: float
    source_event: str


@dataclass(frozen=True)
class Session:
    session_id: str
    cc_code: int
    state: CcState
    summary: str
    priority: Priority
    cwd: str
    updated_at: float


@dataclass(frozen=True)
class Snapshot:
    revision: int
    sessions: Tuple[Session, ...]
