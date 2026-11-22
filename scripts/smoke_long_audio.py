"""Regression: stream a synthetic 3-hour file with bounded Python/NumPy allocations."""

from pathlib import Path
import sys
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audioextract.audio import SAMPLE_RATE, audio_duration, stream_audio_chunks


def main():
    import av
    import numpy as np

    directory = Path(__file__).resolve().parents[1] / ".test-artifacts"
    directory.mkdir(exist_ok=True)
    source = directory / "three-hours.flac"
    seconds = 3 * 3600
    if not source.exists():
        with av.open(str(source), "w") as output:
            stream = output.add_stream("flac", rate=SAMPLE_RATE)
            stream.layout = "mono"
            zeros = np.zeros((1, SAMPLE_RATE), dtype=np.int16)
            for second in range(seconds):
                frame = av.AudioFrame.from_ndarray(zeros, format="s16", layout="mono")
                frame.sample_rate = SAMPLE_RATE
                frame.pts = second * SAMPLE_RATE
                for packet in stream.encode(frame):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
    assert abs(audio_duration(source) - seconds) < 0.01
    tracemalloc.start()
    total, largest, count = 0, 0, 0
    for chunk in stream_audio_chunks(source):
        total += len(chunk.samples)
        largest = max(largest, len(chunk.samples))
        count += 1
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert total == seconds * SAMPLE_RATE, total
    assert largest <= 120 * SAMPLE_RATE, largest
    assert peak < 80 * 1024 * 1024, peak
    print(f"PASS: 3 hours streamed in {count} chunks; largest {largest / SAMPLE_RATE:.2f}s; peak tracked allocations {peak / 1024**2:.1f} MiB")


if __name__ == "__main__":
    main()
