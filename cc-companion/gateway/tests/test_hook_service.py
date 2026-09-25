import unittest

from adapters.hooks import HookService
from domain.models import CcState
from domain.registry import SessionRegistry


class HookServiceTests(unittest.TestCase):
    def test_valid_hook_updates_registry(self):
        service = HookService(SessionRegistry())

        session = service.accept(
            {
                "session_id": "abc",
                "hook_event_name": "Notification",
                "message": "Waiting for your permission",
            },
            now=123.0,
        )

        self.assertEqual(session.cc_code, 1)
        self.assertEqual(session.state, CcState.AWAITING_CONFIRMATION)
        self.assertEqual(service.registry.snapshot(now=123.0).revision, 1)


if __name__ == "__main__":
    unittest.main()
