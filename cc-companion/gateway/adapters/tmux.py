"""Safe, literal tmux text injection."""

import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional


class InjectError(str, Enum):
    EMPTY_TEXT = "EMPTY_TEXT"
    TARGET_UNREACHABLE = "TARGET_UNREACHABLE"
    INJECTION_FAILED = "INJECTION_FAILED"


@dataclass(frozen=True)
class InjectResult:
    ok: bool
    text: str
    warning: Optional[str] = None
    error: Optional[InjectError] = None


class TmuxInjector:
    def __init__(self, targets: Dict[int, str], runner: Callable = subprocess.run, timeout: float = 3.0):
        self._targets = dict(targets)
        self._runner = runner
        self._timeout = timeout

    def inject(self, cc_code: int, text: str) -> InjectResult:
        target = self._targets.get(cc_code)
        if not target:
            return InjectResult(False, "", error=InjectError.TARGET_UNREACHABLE)

        line, warning = _first_line(text)
        if not line:
            return InjectResult(False, "", error=InjectError.EMPTY_TEXT)

        try:
            literal_result = self._run(["tmux", "send-keys", "-t", target, "-l", "--", line])
            if literal_result.returncode != 0:
                return InjectResult(False, line, warning=warning, error=InjectError.TARGET_UNREACHABLE)
            enter_result = self._run(["tmux", "send-keys", "-t", target, "Enter"])
            if enter_result.returncode != 0:
                return InjectResult(False, line, warning=warning, error=InjectError.INJECTION_FAILED)
        except (OSError, subprocess.TimeoutExpired):
            return InjectResult(False, line, warning=warning, error=InjectError.TARGET_UNREACHABLE)

        return InjectResult(True, line, warning=warning)

    def _run(self, args):
        return self._runner(
            args,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )


def _first_line(text: str):
    if not isinstance(text, str):
        return "", None
    lines = text.splitlines()
    line = lines[0].strip() if lines else ""
    warning = "MULTILINE_TRUNCATED" if len(lines) > 1 else None
    return line, warning
