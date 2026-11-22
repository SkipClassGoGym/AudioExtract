"""Persistent FIFO queue that invokes AudioExtract as a background process."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import csv
import io
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import uuid


HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
PATH_COLUMNS = {"path", "video", "file", "filepath", "video_path", "source", "đường dẫn", "duong_dan"}


def project_root() -> Path:
    location = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__)
    for parent in location.parents:
        if (parent / "main.py").is_file() and (parent / "audioextract").is_dir():
            return parent
    return location.parent


def app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "AudioExtractQueue"


def _resolve_paths(values, base: Path) -> list[str]:
    paths = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Mỗi phần tử trong danh sách phải là một đường dẫn video.")
        value = value.strip()
        if not value or value.startswith("#"):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if re.match(r"^[a-z]+://", value, re.IGNORECASE):
            raise ValueError("Ứng dụng nhận video local. Hãy dùng đường dẫn tệp trên máy thay cho URL.")
        path = Path(os.path.expandvars(value)).expanduser()
        paths.append(str((base / path if not path.is_absolute() else path).resolve()))
    return paths


def parse_list(text: str, base: Path, kind: str = "txt") -> list[str]:
    """Preserve row order and duplicates; relative paths use the list's folder."""
    if kind == "json":
        values = json.loads(text)
        if isinstance(values, dict):
            values = values.get("videos", values.get("files"))
        if not isinstance(values, list):
            raise ValueError("JSON cần là danh sách đường dẫn hoặc đối tượng có thuộc tính videos/files.")
        normalized = []
        for value in values:
            if isinstance(value, dict):
                value = next((value[k] for k in ("path", "video", "file", "source") if k in value), None)
            normalized.append(value)
        return _resolve_paths(normalized, base)
    if kind == "csv":
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = [row for row in csv.reader(io.StringIO(text), dialect) if row and any(c.strip() for c in row)]
        if not rows:
            return []
        header = [c.strip().lower() for c in rows[0]]
        column = next((i for i, name in enumerate(header) if name in PATH_COLUMNS), None)
        if column is not None:
            rows = rows[1:]
        else:
            column = 0
        if any(len(row) <= column for row in rows):
            raise ValueError("Một dòng CSV bị thiếu cột đường dẫn video.")
        return _resolve_paths([row[column] for row in rows], base)
    return _resolve_paths(text.splitlines(), base)


def import_list(path: str | Path) -> list[str]:
    source = Path(path).resolve()
    kind = source.suffix.lower().lstrip(".")
    if kind not in {"txt", "csv", "json"}:
        raise ValueError("Hãy chọn danh sách TXT, CSV hoặc JSON.")
    return parse_list(source.read_text(encoding="utf-8-sig"), source.parent, kind)


@dataclass
class Job:
    source: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = "pending"
    progress: float = 0
    outputs: list[str] = field(default_factory=list)
    error: str = ""


class QueueStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.jobs: list[Job] = []
        self.settings: dict = {}
        if path.exists():
            document = json.loads(path.read_text(encoding="utf-8"))
            self.settings = document.get("settings", {})
            self.jobs = [Job(**row) for row in document.get("jobs", [])]
            for job in self.jobs:
                if job.state == "running":
                    job.state, job.progress = "pending", 0
                    job.error = "Phiên trước bị gián đoạn; sẽ xử lý lại video này từ đầu."

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                                 delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump({"settings": self.settings, "jobs": [asdict(j) for j in self.jobs]},
                              stream, ensure_ascii=False, indent=2)
                os.replace(temporary, self.path)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()

    def snapshot(self) -> list[Job]:
        with self.lock:
            return [Job(**asdict(job)) for job in self.jobs]

    def add(self, sources: list[str]):
        with self.lock:
            self.jobs.extend(Job(source=source) for source in sources)
            self.save()

    def claim_next(self) -> Job | None:
        with self.lock:
            for job in self.jobs:
                if job.state == "pending":
                    job.state, job.progress, job.error = "running", 0, ""
                    self.save()
                    return Job(**asdict(job))
        return None

    def update(self, job_id: str, persist: bool = True, **changes):
        with self.lock:
            job = next(job for job in self.jobs if job.id == job_id)
            for key, value in changes.items():
                setattr(job, key, value)
            if persist:
                self.save()

    def remove(self, ids: set[str]):
        with self.lock:
            self.jobs = [j for j in self.jobs if j.id not in ids or j.state == "running"]
            self.save()

    def retry(self, ids: set[str]):
        with self.lock:
            for job in self.jobs:
                if job.id in ids and job.state in {"failed", "cancelled"}:
                    job.state, job.progress, job.error = "pending", 0, ""
            self.save()


@dataclass(frozen=True)
class Backend:
    path: str
    command: tuple[str, ...]

    @classmethod
    def from_path(cls, path: str | Path):
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise ValueError("Không tìm thấy AudioExtract. Hãy chọn main.py hoặc AudioExtract.exe.")
        if source.suffix.lower() == ".py":
            interpreter = source.parent / ".venv" / "Scripts" / "python.exe"
            if os.name != "nt":
                interpreter = source.parent / ".venv" / "bin" / "python"
            if not interpreter.is_file():
                raise ValueError("Không tìm thấy Python trong .venv của AudioExtract. Hãy chọn bản EXE hoặc chạy setup.bat.")
            return cls(str(source), (str(interpreter), str(source)))
        if source.suffix.lower() == ".exe":
            return cls(str(source), (str(source),))
        raise ValueError("Hãy chọn main.py hoặc tệp EXE của AudioExtract.")


def default_backend() -> str:
    root = project_root()
    main = root / "main.py"
    if main.is_file() and (root / ".venv" / "Scripts" / "python.exe").exists():
        return str(main)
    for name in ("AudioExtractGPU-v2", "AudioExtractGPU", "AudioExtract"):
        exe = root / "dist" / name / (name + ".exe")
        if exe.exists():
            return str(exe)
    return ""


@dataclass(frozen=True)
class RunSettings:
    backend: Backend
    result_dir: str
    model: str = "small"
    language: str = "auto"
    device: str = "cuda"
    offline: bool = True
    formats: tuple[str, ...] = ("txt", "srt")


def _timestamp(seconds: float) -> str:
    total = max(0, round(seconds * 1000))
    hours, rest = divmod(total, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def export_result(document: dict, source: Path, directory: Path, formats: tuple[str, ...]) -> list[str]:
    """Write named results without ever replacing an existing result or source."""
    if document.get("metadata", {}).get("complete") is not True:
        raise ValueError("AudioExtract chưa hoàn tất transcript; không xuất kết quả dở dang.")
    segments = document.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Kết quả của AudioExtract không có danh sách transcript hợp lệ.")
    texts, timed_texts, cues = [], [], []
    for index, segment in enumerate(segments, 1):
        start, end, text = segment["start"], segment["end"], segment["text"]
        if not (isinstance(start, (int, float)) and isinstance(end, (int, float))
                and math.isfinite(start) and math.isfinite(end) and 0 <= start <= end and isinstance(text, str)):
            raise ValueError("Kết quả có mốc thời gian hoặc nội dung không hợp lệ.")
        texts.append(text.strip())
        timed_texts.append(f"[{_timestamp(start).split(',')[0]}] {' '.join(text.split())}")
        end = max(round(start * 1000) + 1, round(end * 1000)) / 1000
        cues.append(f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{' '.join(text.split())}\n")
    contents = {"txt": "\n".join(texts) + ("\n" if texts else ""),
                "txt_time": "\n".join(timed_texts) + ("\n" if timed_texts else ""),
                "srt": "\n".join(cues),
                "json": json.dumps(document, ensure_ascii=False, indent=2) + "\n"}
    if not formats or any(fmt not in contents for fmt in formats) or len(set(formats)) != len(formats):
        raise ValueError("Định dạng xuất không hợp lệ.")
    endings = [("_timestamp.txt" if "txt" in formats else ".txt") if fmt == "txt_time"
               else "." + fmt for fmt in formats]
    directory.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while True:
        stem = source.stem if suffix == 1 else f"{source.stem}__{suffix}"
        targets = [directory / (stem + ending) for ending in endings]
        if any(path.exists() for path in targets):
            suffix += 1
            continue
        created = []
        try:
            for target, fmt in zip(targets, formats):
                # Exclusive creation also protects files created after the check.
                with target.open("x", encoding="utf-8", newline="\n") as output:
                    created.append(target)
                    output.write(contents[fmt])
            return [str(path.resolve()) for path in targets]
        except FileExistsError:
            for target in created:
                target.unlink(missing_ok=True)
            suffix += 1
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise


class QueueRunner:
    def __init__(self, store: QueueStore, events: queue.Queue):
        self.store = store
        self.events = events
        self.thread: threading.Thread | None = None
        self.halt = threading.Event()
        self.cancel = threading.Event()
        self.process: subprocess.Popen | None = None
        self.process_lock = threading.Lock()

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, settings: RunSettings):
        if self.running:
            return
        self.halt.clear()
        self.cancel.clear()
        self.thread = threading.Thread(target=self._run, args=(settings,), daemon=True)
        self.thread.start()

    def pause_after_current(self):
        self.halt.set()

    def cancel_current(self):
        self.halt.set()
        self.cancel.set()
        threading.Thread(target=self._kill, daemon=True).start()

    def _kill(self):
        with self.process_lock:
            process = self.process
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            try:
                result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                        creationflags=HIDDEN, capture_output=True, timeout=10, check=False)
                if result.returncode and process.poll() is None:
                    process.kill()
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.kill()
        else:
            process.terminate()

    def _emit(self, kind: str, **data):
        self.events.put({"type": kind, **data})

    def _run(self, settings: RunSettings):
        try:
            while not self.halt.is_set():
                job = self.store.claim_next()
                if job is None:
                    break
                self._emit("changed")
                try:
                    source = Path(job.source)
                    if not source.is_file() or source.stat().st_size == 0:
                        raise ValueError("Tệp video không tồn tại hoặc đang trống.")
                    self._execute(job, settings)
                except Exception as error:
                    state = "cancelled" if self.cancel.is_set() else "failed"
                    self.store.update(job.id, state=state, error=str(error))
                    self._emit("log", text=f"{Path(job.source).name}: {error}")
                self._emit("changed")
        except Exception as error:
            self._emit("log", text=f"Lỗi hàng đợi: {error}")
        finally:
            self._emit("finished")

    def _execute(self, job: Job, settings: RunSettings):
        tail = deque(maxlen=16)
        logs = self.store.path.parent / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="AudioExtractQueue-") as temporary:
            output_json = Path(temporary) / "transcript.json"
            arguments = [*settings.backend.command, "--input", job.source, "--output", str(output_json),
                         "--format", "json", "--model", settings.model, "--language", settings.language,
                         "--device", settings.device]
            if settings.offline:
                arguments.append("--offline")
            environment = os.environ.copy()
            environment["PYTHONUTF8"] = "1"
            environment["PYTHONIOENCODING"] = "utf-8"
            environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            self._emit("started", id=job.id, source=job.source)
            with (logs / (job.id + ".log")).open("w", encoding="utf-8") as log:
                with self.process_lock:
                    if self.cancel.is_set():
                        raise RuntimeError("Đã dừng theo yêu cầu.")
                    self.process = subprocess.Popen(
                        arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                        creationflags=HIDDEN, env=environment, cwd=str(Path(settings.backend.path).parent),
                    )
                    process = self.process
                try:
                    for line in process.stdout:
                        line = line.strip()
                        if not line:
                            continue
                        log.write(line + "\n")
                        log.flush()
                        tail.append(line)
                        match = re.match(r"^(\d{1,3})%", line)
                        if match:
                            progress = min(99, int(match.group(1)))
                            self.store.update(job.id, persist=False, progress=progress)
                            self._emit("progress", id=job.id, progress=progress)
                        else:
                            self._emit("status", text=line)
                    return_code = process.wait()
                finally:
                    if process.poll() is None:
                        self._kill()
                        process.wait(timeout=15)
                    process.stdout.close()
                    with self.process_lock:
                        self.process = None
            if self.cancel.is_set():
                raise RuntimeError("Đã dừng video. Có thể chọn Chạy lại để xử lý video này từ đầu.")
            if return_code != 0 or not output_json.is_file():
                detail = "\n".join(tail)[-2200:]
                raise RuntimeError(detail or f"AudioExtract kết thúc với mã {return_code}. Hãy kiểm tra model, GPU và video đầu vào.")
            document = json.loads(output_json.read_text(encoding="utf-8-sig"))
            outputs = export_result(document, Path(job.source), Path(settings.result_dir), settings.formats)
            self.store.update(job.id, state="done", progress=100, outputs=outputs, error="")
            self._emit("log", text=f"Đã lưu: {', '.join(outputs)}")
