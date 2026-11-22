"""Verify packaged mini app invokes both source and EXE AudioExtract backends."""

import json
from pathlib import Path
import subprocess
import sys


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    directory = Path((root / ".test-artifacts" / "queue-smoke-path.txt").read_text(encoding="utf-8").strip())
    exe = root / "dist" / "AudioExtractQueue" / "AudioExtractQueue.exe"
    for kind, backend in (("source", root / "main.py"),
                          ("exe", root / "dist" / "AudioExtractGPU-v2" / "AudioExtractGPU-v2.exe")):
        result = directory / ("frozen-" + kind)
        completed = subprocess.run([
            str(exe), "--batch", str(directory / "one-video.txt"), "--result", str(result),
            "--backend", str(backend), "--model", "small", "--language", "en", "--device", "cuda", "--offline",
        ], timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        manifests = list((result / "_queue_runs").glob("*/queue.json"))
        assert manifests, f"No run manifest for {kind}, exit={completed.returncode}"
        manifest = json.loads(manifests[-1].read_text(encoding="utf-8"))
        assert completed.returncode == 0, manifest
        assert manifest["jobs"][0]["state"] == "done", manifest
        target = result / "02 - Bài học.txt"
        assert "local video transcription test" in target.read_text(encoding="utf-8").lower()
        assert (result / "02 - Bài học.srt").is_file()
        print(f"PASS: packaged mini app -> AudioExtract {kind} backend -> GPU/offline -> named TXT + SRT", flush=True)


if __name__ == "__main__":
    main()
