"""Verify the real GPU queue UI, then prepare a fixture for the frozen mini app."""

from pathlib import Path
import shutil
import sys
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mini_app.gui import QueueApplication
from mini_app.queueing import QueueStore


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    project = Path(__file__).resolve().parents[1]
    directory = project / ".test-artifacts" / ("queue-smoke-" + str(time.time_ns()))
    directory.mkdir(parents=True)
    source = project / ".test-artifacts" / "video-local.mp4"
    first = directory / "02 - Bài học.mp4"
    second = directory / "01 - Bài học.mp4"
    shutil.copyfile(source, first)
    shutil.copyfile(source, second)
    list_file = directory / "videos.txt"
    list_file.write_text(f'{first.name}\nmissing.mp4\n{second.name}\n', encoding="utf-8-sig")
    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda cls, error, tb: errors.append(str(error))
    app = QueueApplication(root, QueueStore(directory / "queue.json"))
    app.result_dir.set(str(directory / "result"))
    app.model.set("small")
    app.language.set("English")
    app.offline.set(True)
    try:
        with patch("mini_app.gui.filedialog.askopenfilename", return_value=str(list_file)), \
             patch("mini_app.gui.messagebox.showerror", side_effect=lambda *args, **kwargs: errors.append(str(args))):
            app._import()
            assert app.busy, "Import should automatically start the queue"
            root.update()
            assert [Path(j.source).name for j in app.store.snapshot()] == [first.name, "missing.mp4", second.name]
            app._start()
            deadline = time.monotonic() + 150
            while app.busy or app.runner.running:
                root.update()
                if time.monotonic() > deadline:
                    raise AssertionError("Real GPU queue timed out")
                time.sleep(0.02)
            root.update()
            assert not errors, errors
            jobs = app.store.snapshot()
            assert [j.state for j in jobs] == ["done", "failed", "done"], jobs
            for job in (jobs[0], jobs[2]):
                assert [Path(p).name for p in job.outputs] == [Path(job.source).stem + ".txt", Path(job.source).stem + ".srt"]
                text = Path(job.outputs[0]).read_text(encoding="utf-8").lower()
                assert "local video transcription test" in text, text
            log = app.log.get("1.0", "end")
            assert log.index(first.name) < log.index(second.name)
            restored = QueueStore(directory / "queue.json").snapshot()
            assert [j.state for j in restored] == ["done", "failed", "done"]
            root.geometry("970x690")
            root.deiconify()
            root.update()
            assert app.start_button.winfo_rooty() + app.start_button.winfo_height() < root.winfo_rooty() + root.winfo_height()
            (project / ".test-artifacts" / "queue-smoke-path.txt").write_text(str(directory), encoding="utf-8")
            (directory / "one-video.txt").write_text(first.name + "\n", encoding="utf-8")
            print("PASS: real Small/GPU FIFO -> two transcripts, error continuation, names, persistence, minimum-size UI")
            print(f"Artifacts: {directory}")
    finally:
        if app.runner.running:
            app.runner.cancel_current()
            app.runner.thread.join(timeout=20)
        root.destroy()


if __name__ == "__main__":
    main()
