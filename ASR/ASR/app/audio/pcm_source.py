"""PCM capture parameters for Fun-ASR (16 kHz mono int16)."""

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


def frames_per_chunk(frame_ms: int) -> int:
    """Number of samples per channel for one chunk."""
    return max(1, int(SAMPLE_RATE * frame_ms / 1000))
