"""Transcription and subtitle export, independent of the desktop UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile
import traceback
from typing import Callable

from .gpu import prepare_gpu_runtime
from .audio import audio_duration, stream_audio_chunks


MODELS = ("tiny", "base", "small", "medium", "large-v3", "turbo")
LANGUAGES = {
    "Tự nhận diện": None,
    "Tiếng Việt": "vi",
    "English": "en",
    "日本語": "ja",
    "中文": "zh",
    "한국어": "ko",
    "Français": "fr",
    "Deutsch": "de",
    "Español": "es",
    "ไทย": "th",
    "Bahasa Indonesia": "id",
    "Русский": "ru",
}
MEDIA_EXTENSIONS = (
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv",
    ".mpeg", ".mpg", ".ts", ".m2ts", ".mp3", ".wav", ".m4a", ".flac",
    ".ogg", ".aac", ".opus", ".wma",
)


def data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    return base / "AudioExtract"


@dataclass(frozen=True)
class Options:
    source: str
    model: str = "small"
    language: str | None = None
    device: str = "cuda"
    offline: bool = False


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str

    def __post_init__(self):
        if not (math.isfinite(self.start) and math.isfinite(self.end)):
            raise ValueError("Mốc thời gian phải là số hữu hạn.")
        if self.start < 0 or self.end < self.start:
            raise ValueError("Mốc thời gian không hợp lệ.")


def timestamp(seconds: float, separator: str = ".") -> str:
    total = max(0, round(seconds * 1000))
    hours, remainder = divmod(total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def plain_text(segments: list[Segment]) -> str:
    return "\n".join(s.text.strip() for s in segments if s.text.strip())


def render_export(segments: list[Segment], fmt: str, metadata: dict | None = None) -> str:
    fmt = fmt.lower().lstrip(".")
    if fmt == "txt":
        return plain_text(segments) + ("\n" if segments else "")
    if fmt == "json":
        return json.dumps(
            {"metadata": metadata or {}, "segments": [asdict(s) for s in segments]},
            ensure_ascii=False, indent=2,
        ) + "\n"
    if fmt not in {"srt", "vtt"}:
        raise ValueError(f"Định dạng không được hỗ trợ: {fmt}")
    separator = "," if fmt == "srt" else "."
    cues = []
    for i, segment in enumerate(segments, 1):
        # Blank lines terminate cues. Keep each recognized segment in one cue.
        text = " ".join(segment.text.split())
        if fmt == "vtt":
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Rounded timestamps must retain a positive cue duration.
        start_ms = round(segment.start * 1000)
        end_ms = max(start_ms + 1, round(segment.end * 1000))
        timing = f"{timestamp(start_ms / 1000, separator)} --> {timestamp(end_ms / 1000, separator)}"
        cues.append(f"{i}\n{timing}\n{text}\n")
    return ("WEBVTT\n\n" if fmt == "vtt" else "") + "\n".join(cues)


def save_export(path: str | Path, segments: list[Segment], fmt: str,
                metadata: dict | None = None, source: str | Path | None = None) -> None:
    target = Path(path).expanduser().resolve()
    if source and target == Path(source).expanduser().resolve():
        raise ValueError("Hãy chọn tên khác để không ghi đè video gốc.")
    if source and target.exists() and Path(source).exists():
        if os.path.samefile(target, source):
            raise ValueError("Không thể ghi đè video gốc.")
    content = render_export(segments, fmt, metadata)
    # Atomic replacement prevents a failed write from destroying an existing export.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def validate_source(source: str) -> Path:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError("Không tìm thấy video. Hãy chọn một tệp có trên máy.")
    if path.stat().st_size == 0:
        raise ValueError("Tệp đang trống. Hãy chọn video có âm thanh.")
    return path


def transcribe(options: Options, emit: Callable[[dict], None]) -> None:
    source = validate_source(options.source)
    if options.model not in MODELS:
        raise ValueError("Model không được hỗ trợ.")
    if options.device not in {"cpu", "cuda"}:
        raise ValueError("Thiết bị không được hỗ trợ.")
    # These flags affect only this worker process. No audio is sent to a server.
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    if options.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    emit({"type": "status", "text": "Đang kiểm tra tệp video…"})
    duration = audio_duration(source)
    metadata = {
        "source": str(source), "model": options.model, "device": options.device,
        "compute_type": "float16" if options.device == "cuda" else "int8",
        "language": options.language or "auto", "language_probability": 0.0,
        "duration": duration, "complete": False, "chunk_seconds": 120,
    }
    emit({"type": "metadata", "data": metadata.copy()})
    emit({"type": "status", "text": "Đang nạp model; lần đầu có thể cần tải xuống…"})
    if options.device == "cuda":
        prepare_gpu_runtime()
    from faster_whisper import WhisperModel

    model = WhisperModel(
        options.model, device=options.device,
        compute_type="int8" if options.device == "cpu" else "float16",
        cpu_threads=min(8, max(1, (os.cpu_count() or 2) - 1)),
        download_root=str(data_dir() / "models"),
        local_files_only=options.offline,
    )
    device_label = "NVIDIA GPU (FP16)" if options.device == "cuda" else "CPU (INT8)"
    language = options.language
    decoded_end = 0.0

    def reading(position):
        total = timestamp(duration).split(".")[0] if duration else "?"
        emit({"type": "status", "text": f"Đang đọc âm thanh: {timestamp(position).split('.')[0]} / {total} (từng đoạn tối đa 2 phút)…"})

    for number, chunk in enumerate(stream_audio_chunks(source, reading=reading), 1):
        emit({"type": "status", "text": (
            f"Đang nhận dạng đoạn {number}: {timestamp(chunk.start).split('.')[0]}"
            f" → {timestamp(chunk.end).split('.')[0]} trên {device_label}…"
        )})
        # Passing only this small float32 array prevents faster-whisper from
        # allocating a multi-hour spectrogram/FFT (several GB of float64 arrays).
        segments, info = model.transcribe(
            chunk.samples, language=language, task="transcribe", beam_size=5,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        for segment in segments:
            if not segment.text.strip():
                continue
            start = min(chunk.end, chunk.start + max(0, segment.start))
            end = min(chunk.end, max(start, chunk.start + segment.end))
            emit({"type": "segment", "data": asdict(Segment(start, end, segment.text.strip())),
                  "progress": min(99, 100 * end / max(duration, chunk.end, 0.001))})
            # Do not lock automatic language detection to a silent first chunk.
            if language is None:
                language = info.language
                metadata.update(language=info.language, language_probability=info.language_probability)
                emit({"type": "metadata", "data": metadata.copy()})
        decoded_end = chunk.end
        emit({"type": "progress", "progress": min(99, 100 * chunk.end / max(duration, chunk.end, 0.001))})
        del segments, info, chunk
    metadata.update(duration=decoded_end, complete=True)
    emit({"type": "metadata", "data": metadata.copy()})
    emit({"type": "done"})


def friendly_error(error: Exception, offline: bool = False) -> str:
    detail = str(error)
    lower = detail.lower()
    if isinstance(error, MemoryError) or "unable to allocate" in lower:
        return "Không đủ RAM để chuẩn bị âm thanh. Hãy dùng bản mới xử lý từng đoạn ngắn và đóng ứng dụng nặng khác.\n\n" + detail
    if "out of memory" in lower or "cuda_error_out_of_memory" in lower:
        return "GPU không đủ VRAM cho model này. Hãy chọn model small hoặc base, rồi thử lại.\n\n" + detail
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "Thiếu thư viện chạy ứng dụng. Hãy chạy setup.bat hoặc dùng bản AudioExtract.exe.\n\n" + detail
    if any(word in lower for word in ("cuda", "cudnn", "cublas")):
        return "Không khởi tạo được NVIDIA GPU. Hãy chọn CPU và thử lại.\n\n" + detail
    if "audio" in lower and any(word in lower for word in ("stream", "empty", "track")):
        return "Video không có luồng âm thanh đọc được. Hãy chọn video khác.\n\n" + detail
    if offline and any(word in lower for word in ("cache", "offline", "local", "snapshot")):
        return "Model chưa được tải đầy đủ. Bỏ chọn chế độ offline, kết nối Internet rồi thử lại.\n\n" + detail
    if any(word in lower for word in ("connection", "network", "https", "download", "huggingface", "timed out")):
        return "Không tải được model. Kiểm tra Internet rồi thử lại; phần đã tải sẽ được dùng tiếp khi có thể.\n\n" + detail
    if any(word in lower for word in ("invalid data", "invaliddataerror", "permission denied")):
        return "Không đọc được tệp. Kiểm tra tệp video và quyền truy cập.\n\n" + detail
    return detail or type(error).__name__


def worker(options: Options, events) -> None:
    """Spawned process entry point; can be terminated without freezing Tk."""
    try:
        transcribe(options, events.put)
    except Exception as error:
        try:
            directory = data_dir()
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / "errors.log").open("a", encoding="utf-8") as log:
                traceback.print_exc(file=log)
        except OSError:
            pass
        events.put({"type": "error", "text": friendly_error(error, options.offline)})
    finally:
        # Flush the feeder before a normal exit; the UI drains it while waiting.
        events.close()
        events.join_thread()
