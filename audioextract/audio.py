"""Decode a bounded amount of audio at a time, even for multi-hour videos."""

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable


SAMPLE_RATE = 16000
CHUNK_SECONDS = 120


@dataclass(frozen=True)
class AudioChunk:
    start: float
    samples: Any

    @property
    def end(self) -> float:
        return self.start + len(self.samples) / SAMPLE_RATE


def audio_duration(source: str | Path) -> float:
    import av

    with av.open(str(source), metadata_errors="ignore") as media:
        if not media.streams.audio:
            raise ValueError("Video không có luồng âm thanh. Hãy chọn video có lời nói.")
        stream = media.streams.audio[0]
        if stream.duration is not None and stream.time_base is not None:
            return max(0.0, float(stream.duration * stream.time_base))
        return max(0.0, float(media.duration / av.time_base)) if media.duration else 0.0


def _quiet_boundary(samples, sample_rate: int) -> int:
    """Prefer a quiet point in the last 3 seconds; do not omit/duplicate samples."""
    import numpy as np

    if len(samples) < 10 * sample_rate:
        return len(samples)
    window = sample_rate // 50
    tail_start = len(samples) - 3 * sample_rate
    tail = samples[tail_start:]
    blocks = tail[:len(tail) // window * window].reshape(-1, window)
    energy = np.mean(blocks * blocks, axis=1)
    quietest = int(np.argmin(energy))
    if energy[quietest] < 0.0001:
        return tail_start + (quietest + 1) * window
    return len(samples)


def stream_audio_chunks(source: str | Path, chunk_seconds: float = CHUNK_SECONDS,
                        reading: Callable[[float], None] | None = None):
    import av
    import numpy as np

    capacity = int(chunk_seconds * SAMPLE_RATE)
    if capacity < 1:
        raise ValueError("Độ dài đoạn âm thanh phải lớn hơn 0.")
    buffer = np.empty(capacity, dtype=np.float32)
    filled = 0
    offset = 0
    last_notification = 0.0
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)

    def frames(media):
        for frame in media.decode(audio=0):
            # Use the same continuous audio timeline as faster-whisper's decoder.
            frame.pts = None
            yield from resampler.resample(frame)
        yield from resampler.resample(None)

    with av.open(str(source), metadata_errors="ignore") as media:
        if not media.streams.audio:
            raise ValueError("Video không có luồng âm thanh.")
        for frame in frames(media):
            samples = frame.to_ndarray().reshape(-1)
            position = 0
            while position < len(samples):
                count = min(capacity - filled, len(samples) - position)
                buffer[filled:filled + count] = samples[position:position + count]
                filled += count
                position += count
                now = time.monotonic()
                if reading and now - last_notification >= 1:
                    reading((offset + filled) / SAMPLE_RATE)
                    last_notification = now
                if filled == capacity:
                    boundary = _quiet_boundary(buffer, SAMPLE_RATE)
                    yield AudioChunk(offset / SAMPLE_RATE, buffer[:boundary].copy())
                    remaining = filled - boundary
                    if remaining:
                        buffer[:remaining] = buffer[boundary:filled].copy()
                    offset += boundary
                    filled = remaining
        if filled:
            yield AudioChunk(offset / SAMPLE_RATE, buffer[:filled].copy())
