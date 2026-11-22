import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest

from mini_app.queueing import Backend, QueueRunner, QueueStore, RunSettings, export_result, import_list, parse_list


DOCUMENT = {"metadata": {"complete": True},
            "segments": [{"start": 0.5, "end": 2.5, "text": "Xin chào Việt Nam!"}]}


class ListAndOutputTests(unittest.TestCase):
    def test_text_import_preserves_fifo_duplicates_quotes_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = parse_list('# comment\n"Bài 02.mp4"\nBài 01.mp4\nBài 02.mp4\n', root)
            self.assertEqual(result, [str(root / name) for name in ("Bài 02.mp4", "Bài 01.mp4", "Bài 02.mp4")])

    def test_utf8_bom_csv_uses_path_column_without_reordering(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "videos.csv"
            source.write_text('title,path\nSecond,"sub/02, demo.mp4"\nFirst,01.mp4\n', encoding="utf-8-sig")
            self.assertEqual(import_list(source), [str(source.parent / "sub" / "02, demo.mp4"), str(source.parent / "01.mp4")])

    def test_json_objects_and_bad_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(parse_list('{"videos":[{"path":"B.mp4"},"A.mp4"]}', root, "json"),
                             [str(root / "B.mp4"), str(root / "A.mp4")])
            with self.assertRaises(ValueError):
                parse_list('[{"title":"missing path"}]', root, "json")
            with self.assertRaises(ValueError):
                parse_list('https://example.com/video.mp4', root)

    def test_outputs_keep_video_name_and_never_overwrite_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = export_result(DOCUMENT, root / "Bài học.mp4", root / "result", ("txt", "srt"))
            original = Path(first[0]).read_bytes()
            second = export_result(DOCUMENT, root / "another" / "Bài học.mkv", root / "result", ("txt", "srt"))
            self.assertEqual([Path(p).name for p in first], ["Bài học.txt", "Bài học.srt"])
            self.assertEqual([Path(p).name for p in second], ["Bài học__2.txt", "Bài học__2.srt"])
            self.assertEqual(Path(first[0]).read_bytes(), original)
            self.assertIn("00:00:00,500 --> 00:00:02,500", Path(first[1]).read_text(encoding="utf-8"))

    def test_incomplete_result_produces_no_final_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = {**DOCUMENT, "metadata": {"complete": False}}
            with self.assertRaises(ValueError):
                export_result(document, root / "video.mp4", root / "result", ("txt",))
            self.assertFalse((root / "result").exists())

    def test_reload_recovers_interrupted_job_and_keeps_done_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            store = QueueStore(path)
            store.add(["first.mp4", "second.mp4"])
            first = store.claim_next()
            store.update(first.id, state="done", outputs=["first.txt"])
            store.claim_next()
            loaded = QueueStore(path).snapshot()
            self.assertEqual([j.state for j in loaded], ["done", "pending"])
            self.assertEqual(loaded[0].outputs, ["first.txt"])


FAKE_BACKEND = '''
import argparse, json, time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--input'); p.add_argument('--output')
args,_=p.parse_known_args()
source=Path(args.input)
with (source.parent/'execution.log').open('a',encoding='utf-8') as log:
    log.write(source.name+'\\n')
if source.name.startswith('slow'):
    time.sleep(15)
if source.name.startswith('bad'):
    print('Invalid audio fixture',flush=True)
    raise SystemExit(1)
print('75% — segment',flush=True)
Path(args.output).write_text(json.dumps({'metadata':{'complete':True},'segments':[{'start':0,'end':1,'text':source.stem}]}),encoding='utf-8')
'''


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        backend = self.root / "backend.py"
        backend.write_text(FAKE_BACKEND, encoding="utf-8")
        self.store = QueueStore(self.root / "queue.json")
        self.events = queue.Queue()
        self.runner = QueueRunner(self.store, self.events)
        self.settings = RunSettings(Backend(str(backend), (sys.executable, str(backend))),
                                    str(self.root / "result"), device="cpu")

    def tearDown(self):
        if self.runner.running:
            self.runner.cancel_current()
            self.runner.thread.join(timeout=20)
        self.temporary.cleanup()

    def add(self, *names):
        for name in names:
            (self.root / name).write_bytes(b"fixture")
        self.store.add([str(self.root / name) for name in names])

    def wait(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                self.fail("Timed out waiting for queue")
            time.sleep(0.02)

    def test_real_processes_run_fifo_continue_after_error_and_export_names(self):
        self.add("02.mp4", "bad.mp4", "01.mp4")
        self.runner.start(self.settings)
        self.runner.thread.join(timeout=15)
        self.assertFalse(self.runner.running)
        self.assertEqual((self.root / "execution.log").read_text(encoding="utf-8").splitlines(),
                         ["02.mp4", "bad.mp4", "01.mp4"])
        jobs = self.store.snapshot()
        self.assertEqual([j.state for j in jobs], ["done", "failed", "done"])
        self.assertIn("Invalid audio", jobs[1].error)
        self.assertEqual((self.root / "result" / "02.txt").read_text(encoding="utf-8"), "02\n")
        self.assertTrue((self.root / "result" / "01.srt").exists())

    def test_pause_finishes_current_video_without_starting_next(self):
        self.add("slow.mp4", "next.mp4")
        # Slow fixture is shortened to keep this regression fast.
        script = Path(self.settings.backend.path)
        script.write_text(FAKE_BACKEND.replace("time.sleep(15)", "time.sleep(0.5)"), encoding="utf-8")
        self.runner.start(self.settings)
        self.wait(lambda: (self.root / "execution.log").exists())
        self.runner.pause_after_current()
        self.runner.thread.join(timeout=10)
        self.assertEqual([j.state for j in self.store.snapshot()], ["done", "pending"])
        self.assertEqual((self.root / "execution.log").read_text().splitlines(), ["slow.mp4"])

    def test_new_items_added_during_run_stay_at_tail_of_fifo(self):
        self.add("slow.mp4", "second.mp4")
        script = Path(self.settings.backend.path)
        script.write_text(FAKE_BACKEND.replace("time.sleep(15)", "time.sleep(0.5)"), encoding="utf-8")
        self.runner.start(self.settings)
        self.wait(lambda: (self.root / "execution.log").exists())
        self.add("third.mp4")
        self.runner.thread.join(timeout=10)
        self.assertEqual((self.root / "execution.log").read_text().splitlines(),
                         ["slow.mp4", "second.mp4", "third.mp4"])
        self.assertEqual([j.state for j in self.store.snapshot()], ["done", "done", "done"])

    def test_cancel_terminates_current_without_export_and_preserves_pending(self):
        self.add("slow.mp4", "next.mp4")
        self.runner.start(self.settings)
        self.wait(lambda: (self.root / "execution.log").exists())
        self.runner.cancel_current()
        self.runner.thread.join(timeout=15)
        self.assertFalse(self.runner.running)
        self.assertIsNone(self.runner.process)
        self.assertEqual([j.state for j in self.store.snapshot()], ["cancelled", "pending"])
        self.assertFalse((self.root / "result" / "slow.txt").exists())
        self.store.retry({self.store.snapshot()[0].id})
        self.assertEqual([j.state for j in self.store.snapshot()], ["pending", "pending"])


if __name__ == "__main__":
    unittest.main()
