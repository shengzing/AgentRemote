import unittest

from domain.normalizer import HookValidationError, normalize_hook_payload
from domain.models import CcState, Priority


class HookNormalizerTests(unittest.TestCase):
    def test_notification_permission_becomes_high_priority_confirmation(self):
        event = normalize_hook_payload(
            {
                "session_id": "session-1",
                "hook_event_name": "Notification",
                "cwd": "/work/project",
                "message": "Claude is waiting for your permission to use Bash: rm",
            },
            now=100.0,
        )

        self.assertEqual(event.state, CcState.AWAITING_CONFIRMATION)
        self.assertEqual(event.priority, Priority.HIGH)
        self.assertEqual(event.session_id, "session-1")
        self.assertEqual(event.ts, 100.0)

    def test_user_prompt_submit_becomes_working(self):
        event = normalize_hook_payload(
            {
                "session_id": "session-2",
                "hook_event_name": "UserPromptSubmit",
                "message": "Continue the refactor",
            },
            now=100.0,
        )

        self.assertEqual(event.state, CcState.WORKING)
        self.assertEqual(event.priority, Priority.NORMAL)

    def test_stop_with_error_language_becomes_error(self):
        event = normalize_hook_payload(
            {
                "session_id": "session-3",
                "hook_event_name": "Stop",
                "message": "Tests failed with an exception",
            },
            now=100.0,
        )

        self.assertEqual(event.state, CcState.ERROR)

    def test_invalid_payload_is_rejected(self):
        with self.assertRaises(HookValidationError):
            normalize_hook_payload({"hook_event_name": "Stop"}, now=100.0)


if __name__ == "__main__":
    unittest.main()
