import subprocess
import unittest

from adapters.tmux import InjectError, TmuxInjector


class RecordingRunner:
    def __init__(self, return_codes=None):
        self.calls = []
        self.return_codes = iter(return_codes or [])

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return_code = next(self.return_codes, 0)
        return subprocess.CompletedProcess(args, return_code, stdout="", stderr="not found")


class TmuxInjectorTests(unittest.TestCase):
    def test_injection_uses_literal_text_and_never_invokes_a_shell(self):
        runner = RecordingRunner()
        injector = TmuxInjector({1: "cc1"}, runner=runner)

        result = injector.inject(1, "allow; rm -rf /\nsecond line")

        self.assertTrue(result.ok)
        self.assertEqual(result.text, "allow; rm -rf /")
        self.assertEqual(result.warning, "MULTILINE_TRUNCATED")
        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ["tmux", "send-keys", "-t", "cc1", "-l", "--", "allow; rm -rf /"],
                ["tmux", "send-keys", "-t", "cc1", "Enter"],
            ],
        )
        self.assertTrue(all(call[1]["shell"] is False for call in runner.calls))

    def test_missing_target_does_not_run_tmux(self):
        runner = RecordingRunner()
        injector = TmuxInjector({}, runner=runner)

        result = injector.inject(1, "continue")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, InjectError.TARGET_UNREACHABLE)
        self.assertEqual(runner.calls, [])

    def test_tmux_failure_returns_reachable_error_without_throwing(self):
        runner = RecordingRunner(return_codes=[1])
        injector = TmuxInjector({1: "missing"}, runner=runner)

        result = injector.inject(1, "continue")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, InjectError.TARGET_UNREACHABLE)

    def test_empty_input_is_rejected_without_running_tmux(self):
        runner = RecordingRunner()
        injector = TmuxInjector({1: "cc1"}, runner=runner)

        result = injector.inject(1, "  \n")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, InjectError.EMPTY_TEXT)
        self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
