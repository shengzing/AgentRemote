"""Pairing-code verification and durable hashes for trusted devices."""

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Callable, Dict, Optional


class PairingStore:
    """Small local store that contains hashes only, never reusable tokens."""

    def __init__(self, path: Path):
        self._path = Path(path)

    def load(self) -> Dict[str, str]:
        try:
            content = self._path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {device_id: token_hash for device_id, token_hash in data.items() if _valid_entry(device_id, token_hash)}

    def save(self, values: Dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_name(self._path.name + ".tmp")
        temporary_path.write_text(json.dumps(values, sort_keys=True), encoding="utf-8")
        os.replace(str(temporary_path), str(self._path))


class PairingService:
    def __init__(
        self,
        store: PairingStore,
        pairing_code: str,
        expires_after_seconds: float = 600.0,
        now: Callable[[], float] = time.time,
    ):
        if not _valid_code(pairing_code):
            raise ValueError("pairing_code must contain exactly six digits")
        self._store = store
        self._pairing_code = pairing_code
        self._expires_at = now() + expires_after_seconds
        self._now = now

    @property
    def pairing_code(self) -> str:
        """Current short-lived code; show it only on the local gateway console."""
        return self._pairing_code

    def complete(self, device_id: str, code: str) -> Optional[str]:
        if not _valid_device_id(device_id) or not _valid_code(code):
            return None
        if self._now() > self._expires_at or not hmac.compare_digest(code, self._pairing_code):
            return None
        token = secrets.token_urlsafe(32)
        tokens = self._store.load()
        tokens[device_id] = _hash_token(token)
        self._store.save(tokens)
        return token

    def verify(self, device_id: str, token: str) -> bool:
        if not _valid_device_id(device_id) or not isinstance(token, str) or not token:
            return False
        expected = self._store.load().get(device_id)
        if expected is None:
            return False
        return hmac.compare_digest(expected, _hash_token(token))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _valid_code(value) -> bool:
    return isinstance(value, str) and len(value) == 6 and value.isdigit()


def _valid_device_id(value) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 64 and value.strip() == value


def _valid_entry(device_id, token_hash) -> bool:
    return _valid_device_id(device_id) and isinstance(token_hash, str) and len(token_hash) == 64
