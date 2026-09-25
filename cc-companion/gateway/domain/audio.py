"""Audio buffering rules kept separate from WebSocket and Whisper adapters."""

from dataclasses import dataclass
from typing import Dict, Protocol


MIN_DURATION_SECONDS = 0.5
MAX_DURATION_SECONDS = 15.0
MAX_PCM_BYTES = 480000  # 15 seconds * 16000 Hz * 2 bytes * 1 channel.


class AudioValidationError(ValueError):
    """A recording is malformed, incomplete, too short, or too large."""


@dataclass(frozen=True)
class AudioFormat:
    sample_rate: int
    sample_width_bits: int
    channels: int

    @property
    def bytes_per_second(self) -> int:
        return self.sample_rate * (self.sample_width_bits // 8) * self.channels

    def is_supported(self) -> bool:
        return self.sample_rate == 16000 and self.sample_width_bits == 16 and self.channels == 1


class Transcriber(Protocol):
    def transcribe(self, pcm: bytes, audio_format: AudioFormat) -> str:
        ...


@dataclass
class _Recording:
    cc_code: int
    audio_format: AudioFormat
    chunks: bytearray
    next_sequence: int


class RecordingService:
    def __init__(self, transcriber: Transcriber):
        self._transcriber = transcriber
        self._recordings: Dict[str, _Recording] = {}

    @property
    def active_count(self) -> int:
        return len(self._recordings)

    def begin(self, recording_id: str, cc_code: int, audio_format: AudioFormat) -> None:
        if not _valid_recording_id(recording_id) or not 1 <= cc_code <= 8:
            raise AudioValidationError("Invalid recording metadata")
        if not audio_format.is_supported():
            raise AudioValidationError("Only 16-kHz, 16-bit mono PCM is supported")
        if recording_id in self._recordings:
            raise AudioValidationError("Recording already exists")
        self._recordings[recording_id] = _Recording(cc_code, audio_format, bytearray(), 0)

    def append(self, recording_id: str, sequence: int, pcm: bytes) -> None:
        recording = self._recording(recording_id)
        if not isinstance(sequence, int) or sequence != recording.next_sequence:
            raise AudioValidationError("Audio chunks are out of order")
        if not isinstance(pcm, bytes) or not pcm:
            raise AudioValidationError("Audio chunk must contain bytes")
        if len(recording.chunks) + len(pcm) > MAX_PCM_BYTES:
            raise AudioValidationError("Recording exceeds 15-second limit")
        recording.chunks.extend(pcm)
        recording.next_sequence += 1

    def finish(self, recording_id: str) -> str:
        recording = self._recording(recording_id)
        try:
            minimum_bytes = int(recording.audio_format.bytes_per_second * MIN_DURATION_SECONDS)
            if len(recording.chunks) < minimum_bytes:
                raise AudioValidationError("Recording is shorter than 0.5 seconds")
            transcript = self._transcriber.transcribe(bytes(recording.chunks), recording.audio_format)
            if not isinstance(transcript, str) or not transcript.strip():
                raise AudioValidationError("Transcription returned no text")
            return transcript.strip()
        finally:
            del self._recordings[recording_id]

    def cancel(self, recording_id: str) -> None:
        if recording_id not in self._recordings:
            raise AudioValidationError("Unknown recording")
        del self._recordings[recording_id]

    def _recording(self, recording_id: str) -> _Recording:
        try:
            return self._recordings[recording_id]
        except KeyError as error:
            raise AudioValidationError("Unknown recording") from error


def _valid_recording_id(value) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 64 and value.strip() == value
