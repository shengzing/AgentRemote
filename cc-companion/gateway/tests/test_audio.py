import unittest

from domain.audio import AudioFormat, AudioValidationError, RecordingService


class RecordingTranscriber:
    def __init__(self, response="Allow this command"):
        self.response = response
        self.calls = []

    def transcribe(self, pcm, audio_format):
        self.calls.append((pcm, audio_format))
        return self.response


class RecordingServiceTests(unittest.TestCase):
    def setUp(self):
        self.transcriber = RecordingTranscriber()
        self.service = RecordingService(self.transcriber)
        self.format = AudioFormat(sample_rate=16000, sample_width_bits=16, channels=1)

    def test_valid_half_second_recording_is_transcribed_once(self):
        self.service.begin("recording-1", 2, self.format)
        self.service.append("recording-1", 0, b"\x00" * 8000)
        self.service.append("recording-1", 1, b"\x01" * 8000)

        transcript = self.service.finish("recording-1")

        self.assertEqual(transcript, "Allow this command")
        self.assertEqual(len(self.transcriber.calls), 1)
        self.assertEqual(len(self.transcriber.calls[0][0]), 16000)
        self.assertEqual(self.service.active_count, 0)

    def test_rejects_invalid_format_out_of_order_or_oversize_audio(self):
        with self.assertRaises(AudioValidationError):
            self.service.begin("wrong-format", 1, AudioFormat(8000, 16, 1))

        self.service.begin("recording-2", 1, self.format)
        with self.assertRaises(AudioValidationError):
            self.service.append("recording-2", 1, b"\x00")
        with self.assertRaises(AudioValidationError):
            self.service.append("recording-2", 0, b"\x00" * (480000 + 1))

    def test_short_recording_is_rejected_without_calling_transcriber(self):
        self.service.begin("recording-3", 1, self.format)
        self.service.append("recording-3", 0, b"\x00" * 15998)

        with self.assertRaises(AudioValidationError):
            self.service.finish("recording-3")

        self.assertEqual(self.transcriber.calls, [])

    def test_blank_transcription_is_reported_as_failure(self):
        service = RecordingService(RecordingTranscriber(response="  "))
        service.begin("recording-4", 1, self.format)
        service.append("recording-4", 0, b"\x00" * 16000)

        with self.assertRaises(AudioValidationError):
            service.finish("recording-4")

    def test_cancel_discards_an_incomplete_recording(self):
        self.service.begin("recording-5", 1, self.format)
        self.service.append("recording-5", 0, b"\x00" * 100)

        self.service.cancel("recording-5")

        self.assertEqual(self.service.active_count, 0)
        with self.assertRaises(AudioValidationError):
            self.service.finish("recording-5")


if __name__ == "__main__":
    unittest.main()
