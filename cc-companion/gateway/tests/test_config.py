import os
import unittest
from unittest.mock import patch

from config import ConfigError, GatewayConfig, parse_tmux_targets


class GatewayConfigTests(unittest.TestCase):
    def test_parses_numbered_tmux_targets(self):
        self.assertEqual(parse_tmux_targets("1=cc1, 2=project:0.1"), {1: "cc1", 2: "project:0.1"})

    def test_rejects_invalid_or_duplicate_target_codes(self):
        with self.assertRaises(ConfigError):
            parse_tmux_targets("1=cc1,1=cc2")
        with self.assertRaises(ConfigError):
            parse_tmux_targets("bad")

    def test_rejects_a_session_limit_that_exceeds_the_protocol_limit(self):
        with patch.dict(os.environ, {"CC_COMPANION_MAX_SESSIONS": "9"}, clear=True):
            with self.assertRaises(ConfigError):
                GatewayConfig.from_environment()

    def test_environment_uses_safe_local_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = GatewayConfig.from_environment()

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 7421)
        self.assertEqual(config.tmux_targets, {})
        self.assertEqual(config.pairing_store, ".cc-companion-pairings.json")
        self.assertIsNone(config.pairing_code)

    def test_environment_reads_pairing_settings(self):
        with patch.dict(
            os.environ,
            {
                "CC_COMPANION_PAIRING_STORE": "/tmp/pairings.json",
                "CC_COMPANION_PAIRING_CODE": "123456",
            },
            clear=True,
        ):
            config = GatewayConfig.from_environment()

        self.assertEqual(config.pairing_store, "/tmp/pairings.json")
        self.assertEqual(config.pairing_code, "123456")


if __name__ == "__main__":
    unittest.main()
