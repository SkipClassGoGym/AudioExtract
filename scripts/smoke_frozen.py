"""Verify the packaged EXE can run a real spawned transcription worker."""

import multiprocessing as mp
from pathlib import Path
import queue
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audioextract.engine import Options, worker


def main():
    root = Path(__file__).resolve().parents[1]
    gpu = "--gpu" in sys.argv
    model = "medium" if "--medium" in sys.argv else "small"
    name = "AudioExtractGPU" if gpu else "AudioExtract"
    if "--v2" in sys.argv:
        name += "-v2"
    exe = root / "dist" / name / (name + ".exe")
    assert exe.exists()
    # Simulate the same Windows spawn command line used by the frozen GUI.
    sys.frozen = True
    mp.set_executable(str(exe))
    context = mp.get_context("spawn")
    events = context.Queue()
    fixture = "chunk-boundaries.wav" if "--long" in sys.argv else "video-local.mp4"
    process = context.Process(target=worker, args=(
        Options(str(root / ".test-artifacts" / fixture), model, "en", "cuda" if gpu else "cpu", True), events,
    ))
    process.start()
    deadline = time.monotonic() + 120
    segments = []
    timings = []
    done = False
    metadata = {}
    try:
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=1)
            except queue.Empty:
                if not process.is_alive():
                    break
                continue
            if event["type"] == "error":
                raise AssertionError(event["text"])
            if event["type"] == "segment":
                segments.append(event["data"]["text"])
                timings.append(event["data"])
            if event["type"] == "metadata":
                metadata.update(event["data"])
            if event["type"] == "done":
                done = True
                break
        assert done, f"Worker did not complete (exit={process.exitcode})"
        assert "local video transcription test" in " ".join(segments).lower(), segments
        assert metadata.get("device") == ("cuda" if gpu else "cpu"), metadata
        assert metadata.get("model") == model, metadata
        if "--long" in sys.argv:
            assert " ".join(segments).lower().count("local video transcription test") == 3, segments
            assert abs(metadata["duration"] - 250) < 0.1, metadata
            assert timings[-1]["end"] > 240, timings
            assert all(a["end"] <= b["start"] + 0.01 for a, b in zip(timings, timings[1:])), timings
        print(f"PASS: packaged EXE + {model} + spawned {metadata['device']}/offline worker -> {len(segments)} segments")
    finally:
        process.join(timeout=3)
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
        process.close()
        events.close()


if __name__ == "__main__":
    main()
