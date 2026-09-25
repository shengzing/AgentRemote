import tempfile
import unittest
from pathlib import Path

from adapters.pairing import PairingService, PairingStore


class PairingServiceTests(unittest.TestCase):
    def test_correct_code_issues_token_that_survives_service_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "pairings.json"
            service = PairingService(PairingStore(store_path), pairing_code="123456", now=lambda: 10.0)

            token = service.complete("stick-s3-01", "123456")

            self.assertIsNotNone(token)
            self.assertTrue(service.verify("stick-s3-01", token))
            restarted = PairingService(PairingStore(store_path), pairing_code="654321", now=lambda: 10.0)
            self.assertTrue(restarted.verify("stick-s3-01", token))
            self.assertNotIn(token, store_path.read_text(encoding="utf-8"))

    def test_wrong_or_expired_code_never_issues_a_token(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [10.0]
            service = PairingService(
                PairingStore(Path(directory) / "pairings.json"),
                pairing_code="123456",
                expires_after_seconds=5.0,
                now=lambda: now[0],
            )

            self.assertIsNone(service.complete("stick-s3-01", "000000"))
            now[0] = 16.0
            self.assertIsNone(service.complete("stick-s3-01", "123456"))
