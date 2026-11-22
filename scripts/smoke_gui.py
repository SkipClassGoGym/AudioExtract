"""Opt-in real CPU/offline GUI smoke check using the generated local MP4."""

import ctypes
import json
import multiprocessing as mp
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audioextract.engine import plain_text
from audioextract.gui import Application


def pump(root, predicate, timeout=120):
    deadline = time.monotonic() + timeout
    while not predicate():
        root.update()
        if time.monotonic() >= deadline:
            raise AssertionError("GUI check timed out")
        time.sleep(0.02)
    root.update()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    directory = Path(__file__).resolve().parents[1] / ".test-artifacts"
    errors = []
    root = tk.Tk()
    app = Application(root)
    root.update()
    root.report_callback_exception = lambda cls, error, tb: errors.append(str(error))
    try:
        with patch("audioextract.gui.messagebox.showerror", side_effect=lambda title, text, **_: errors.append(text)), \
             patch("audioextract.gui.messagebox.askyesno", return_value=True):
            app.path.set(str(directory / "video-local.mp4"))
            app.offline.set(True)
            app.language.set("English")
            app.device.set("NVIDIA GPU (CUDA)" if "--gpu" in sys.argv else "CPU (phù hợp mọi máy)")
            app._start()
            assert app.busy
            pump(root, lambda: not app.busy)
            assert not errors, errors
            assert app.metadata["complete"]
            text = plain_text(app.segments)
            assert "local video transcription test" in text.lower(), text
            assert "subtitles" in text.lower(), text
            app.search.set("video")
            pump(root, lambda: bool(app.matches.get()), timeout=3)
            assert app.text.tag_ranges("match")
            app.show_timestamps.set(False)
            app._render()
            assert not app.text.tag_ranges("time")
            app.show_timestamps.set(True)
            app._render()
            assert app.text.tag_ranges("time")
            app._copy()
            assert root.clipboard_get() == text
            for fmt in ("txt", "srt", "vtt", "json"):
                target = directory / ("Phụ đề tiếng Việt." + fmt)
                with patch("audioextract.gui.filedialog.asksaveasfilename", return_value=str(target)):
                    app._export()
                assert target.stat().st_size > 0
            assert not errors, errors
            # Leave coordinates for an optional screenshot of only this window.
            root.update()
            (directory / "gui-bounds.json").write_text(json.dumps({
                "x": root.winfo_rootx(), "y": root.winfo_rooty(),
                "width": root.winfo_width(), "height": root.winfo_height(),
            }), encoding="utf-8")
            print(f"PASS: real MP4 -> {app.metadata['device']}/offline -> GUI transcript -> clipboard and four exports", flush=True)
            if "--preview" in sys.argv:
                pump(root, lambda: (directory / "screenshot-done").exists(), timeout=60)
            app._start()
            root.update()
            app._stop()
            assert not app.busy and app.process is None and app.partial
            assert not mp.active_children(), mp.active_children()
            app.path.set(str(directory / "video-no-audio.mp4"))
            app._start()
            pump(root, lambda: not app.busy)
            assert errors and "âm thanh" in errors[-1], errors
            assert not app.metadata.get("complete", False)
            print("PASS: cancel cleans up worker; video without audio reports a clear error", flush=True)
    finally:
        app._cleanup()
        root.destroy()


if __name__ == "__main__":
    mp.freeze_support()
    main()
