import unittest

from domain.models import CcState, NormalizedEvent, Priority
from domain.registry import SessionLimitError, SessionRegistry


def event(session_id, state=CcState.WORKING, ts=0.0, summary="Working"):
    return NormalizedEvent(
        session_id=session_id,
        state=state,
        summary=summary,
        priority=Priority.NORMAL,
        cwd="/project",
        ts=ts,
        source_event="PostToolUse",
    )


class SessionRegistryTests(unittest.TestCase):
    def test_session_code_is_stable_and_snapshot_revision_advances(self):
        registry = SessionRegistry(max_sessions=2, expiry_seconds=60)

        first = registry.apply(event("one", ts=10.0))
        updated = registry.apply(event("one", state=CcState.DONE, ts=11.0))
        second = registry.apply(event("two", ts=12.0))

        self.assertEqual(first.cc_code, 1)
        self.assertEqual(updated.cc_code, 1)
        self.assertEqual(updated.state, CcState.DONE)
        self.assertEqual(second.cc_code, 2)
        snapshot = registry.snapshot(now=12.0)
        self.assertEqual(snapshot.revision, 3)
        self.assertEqual([item.cc_code for item in snapshot.sessions], [1, 2])

    def test_expired_code_is_reclaimed(self):
        registry = SessionRegistry(max_sessions=2, expiry_seconds=10)
        registry.apply(event("one", ts=0.0))
        registry.expire(now=10.0)

        replacement = registry.apply(event("two", ts=10.0))

        self.assertEqual(replacement.cc_code, 1)

    def test_full_registry_rejects_new_session_without_overwriting_existing(self):
        registry = SessionRegistry(max_sessions=1, expiry_seconds=60)
        registry.apply(event("one", ts=0.0))

        with self.assertRaises(SessionLimitError):
            registry.apply(event("two", ts=1.0))

        snapshot = registry.snapshot(now=1.0)
        self.assertEqual([item.session_id for item in snapshot.sessions], ["one"])

    def test_active_code_check_rejects_expired_sessions(self):
        registry = SessionRegistry(max_sessions=2, expiry_seconds=10)
        registry.apply(event("one", ts=0.0))

        self.assertTrue(registry.has_cc_code(1, now=9.0))
        self.assertFalse(registry.has_cc_code(1, now=10.0))


if __name__ == "__main__":
    unittest.main()
