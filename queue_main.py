"""Entry point of the independent lightweight FIFO mini app."""

import argparse
from pathlib import Path
import queue
import sys
import uuid

from mini_app.queueing import Backend, QueueRunner, QueueStore, RunSettings, default_backend, import_list, project_root


def main():
    parser = argparse.ArgumentParser(description="AudioExtract Queue — FIFO video transcription")
    parser.add_argument("--batch", type=Path, help="Run a TXT/CSV/JSON list without opening the GUI")
    parser.add_argument("--result", type=Path, help="Output folder (default: project/result)")
    parser.add_argument("--backend", help="AudioExtract main.py or EXE")
    parser.add_argument("--model", default="small", choices=("tiny", "base", "small", "medium", "large-v3", "turbo"))
    parser.add_argument("--language", default="auto")
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--formats", default="txt,srt", choices=("txt", "txt,srt", "txt,srt,json", "txt_time", "txt,txt_time"))
    args = parser.parse_args()
    if args.batch is None:
        from mini_app.gui import launch
        launch()
        return 0
    runner = None
    try:
        sources = import_list(args.batch)
        if not sources:
            raise ValueError("Danh sách không có video.")
        result = (args.result or project_root() / "result").resolve()
        backend = Backend.from_path(args.backend or default_backend())
        state = result / "_queue_runs" / uuid.uuid4().hex / "queue.json"
        store = QueueStore(state)
        store.add(sources)
        events = queue.Queue()
        runner = QueueRunner(store, events)
        runner.start(RunSettings(backend, str(result), args.model, args.language, args.device,
                                 args.offline, tuple(args.formats.split(","))))
        finished = False
        while not finished:
            event = events.get()
            finished = event["type"] == "finished"
            if event["type"] in {"log", "status"} and sys.stdout is not None:
                print(event["text"], flush=True)
        runner.thread.join()
        return 0 if all(j.state == "done" for j in store.snapshot()) else 1
    except KeyboardInterrupt:
        if runner:
            runner.cancel_current()
            runner.thread.join(timeout=20)
        return 130
    except Exception as error:
        if sys.stderr is not None:
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
