#!/usr/bin/env python3
"""Forward one Claude Code Hook JSON object to a local Companion gateway."""

import json
import os
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    gateway_url = os.environ.get("CC_COMPANION_HOOK_URL", "http://127.0.0.1:7421/hook")
    data = json.dumps(payload).encode("utf-8")
    request = Request(gateway_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=1.0):
            pass
    except (URLError, OSError):
        # A Hook must never hold up Claude Code when the local gateway is down.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
