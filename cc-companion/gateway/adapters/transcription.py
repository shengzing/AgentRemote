"""Transcription adapter boundary; cloud credentials remain outside the device."""

from domain.audio import AudioValidationError


class UnconfiguredTranscriber:
    """Safe default until an operator explicitly configures a Whisper adapter."""

    def transcribe(self, pcm, audio_format):
        raise AudioValidationError("TRANSCRIPTION_NOT_CONFIGURED")
