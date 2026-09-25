import unittest

from protocol.messages import ProtocolError, decode_client_message


class ProtocolMessageTests(unittest.TestCase):
    def test_valid_send_message_is_normalized(self):
        message = decode_client_message(
            {
                "version": 1,
                "type": "message.send",
                "cc_code": 2,
                "text": "continue",
            }
        )

        self.assertEqual(message["cc_code"], 2)

    def test_unknown_version_and_invalid_cc_code_are_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_client_message({"version": 2, "type": "ping"})
        with self.assertRaises(ProtocolError):
            decode_client_message(
                {"version": 1, "type": "message.send", "cc_code": 9, "text": "go"}
            )

    def test_pairing_and_authenticated_hello_are_validated(self):
        pairing = decode_client_message(
            {"version": 1, "type": "pair.complete", "device_id": "stick-s3-01", "code": "123456"}
        )
        hello = decode_client_message(
            {"version": 1, "type": "device.hello", "device_id": "stick-s3-01", "token": "token"}
        )

        self.assertEqual(pairing["device_id"], "stick-s3-01")
        self.assertEqual(hello["type"], "device.hello")
        with self.assertRaises(ProtocolError):
            decode_client_message(
                {"version": 1, "type": "pair.complete", "device_id": "stick", "code": "123"}
            )

    def test_audio_start_and_end_messages_validate_the_fixed_mvp_format(self):
        start = decode_client_message(
            {
                "version": 1,
                "type": "audio.start",
                "recording_id": "recording-1",
                "cc_code": 2,
                "sample_rate": 16000,
                "sample_width_bits": 16,
                "channels": 1,
            }
        )
        end = decode_client_message({"version": 1, "type": "audio.end", "recording_id": "recording-1"})

        self.assertEqual(start["sample_rate"], 16000)
        self.assertEqual(end["recording_id"], "recording-1")
        with self.assertRaises(ProtocolError):
            decode_client_message(
                {
                    "version": 1,
                    "type": "audio.start",
                    "recording_id": "recording-1",
                    "cc_code": 2,
                    "sample_rate": 8000,
                    "sample_width_bits": 16,
                    "channels": 1,
                }
            )

    def test_hello_without_capabilities_gets_default(self):
        payload = decode_client_message(
            {"version": 1, "type": "device.hello", "device_id": "dev-1", "token": "t"}
        )
        self.assertEqual(payload["capabilities"], frozenset({"input", "display"}))

    def test_hello_with_input_only_capabilities(self):
        payload = decode_client_message(
            {
                "version": 1,
                "type": "device.hello",
                "device_id": "cli-1",
                "token": "t",
                "capabilities": ["input"],
            }
        )
        self.assertEqual(payload["capabilities"], frozenset({"input"}))

    def test_hello_with_full_capabilities(self):
        payload = decode_client_message(
            {
                "version": 1,
                "type": "device.hello",
                "device_id": "m5-1",
                "token": "t",
                "capabilities": ["input", "display", "audio", "select"],
            }
        )
        self.assertEqual(
            payload["capabilities"],
            frozenset({"input", "display", "audio", "select"}),
        )

    def test_hello_with_invalid_capabilities_is_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_client_message(
                {
                    "version": 1,
                    "type": "device.hello",
                    "device_id": "dev",
                    "token": "t",
                    "capabilities": ["input", "telepathy"],
                }
            )

    def test_hello_with_non_list_capabilities_is_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_client_message(
                {
                    "version": 1,
                    "type": "device.hello",
                    "device_id": "dev",
                    "token": "t",
                    "capabilities": "input",
                }
            )

    def test_cc_select_valid_message(self):
        payload = decode_client_message(
            {"version": 1, "type": "cc.select", "cc_code": 3}
        )
        self.assertEqual(payload["type"], "cc.select")
        self.assertEqual(payload["cc_code"], 3)

    def test_cc_select_invalid_cc_code_is_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_client_message({"version": 1, "type": "cc.select", "cc_code": 9})

    def test_cc_select_missing_cc_code_is_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_client_message({"version": 1, "type": "cc.select"})


if __name__ == "__main__":
    unittest.main()
