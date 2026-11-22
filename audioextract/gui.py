"""Vietnamese desktop interface. All Tk operations stay on the main thread."""

from __future__ import annotations

import ctypes
import multiprocessing as mp
import os
from pathlib import Path
import queue
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .engine import (
    LANGUAGES, MEDIA_EXTENSIONS, MODELS, Options, Segment,
    plain_text, save_export, timestamp, validate_source, worker,
)


BG = "#f3f5f7"
WHITE = "#ffffff"
INK = "#172b35"
MUTED = "#667984"
GREEN = "#087f6b"
LINE = "#dce5e9"


class Application:
    def __init__(self, root: tk.Tk):
        self.root = root
        name = "AudioExtract GPU" if getattr(sys, "frozen", False) and "GPU" in Path(sys.executable).stem else "AudioExtract"
        self.root.title(f"{name} — Video thành văn bản")
        self.root.geometry("1120x790")
        self.root.minsize(930, 700)
        self.root.configure(bg=BG)
        self.context = mp.get_context("spawn")
        self.process = None
        self.events = None
        self.segments: list[Segment] = []
        self.metadata = {}
        self.result_source = ""
        self.started = 0.0
        self.busy = False
        self.partial = False
        self.search_after = None
        self.path = tk.StringVar()
        self.model = tk.StringVar(value="small")
        self.language = tk.StringVar(value="Tự nhận diện")
        self.device = tk.StringVar(value="NVIDIA GPU (CUDA)")
        self.offline = tk.BooleanVar(value=False)
        self.show_timestamps = tk.BooleanVar(value=True)
        self.search = tk.StringVar()
        self.status = tk.StringVar(value="Sẵn sàng. Chọn một video để bắt đầu.")
        self.stats = tk.StringVar(value="Chưa có transcript")
        self.elapsed = tk.StringVar(value="")
        self.matches = tk.StringVar(value="")
        self.file_info = tk.StringVar(value="MP4, MKV, MOV, AVI, WebM và các tệp âm thanh")
        self.preview_title = tk.StringVar(value="Transcript của bạn")
        self._styles()
        self._build()
        self._placeholder()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<Control-o>", lambda _: self._choose())
        self.root.bind("<Control-s>", lambda _: self._export())
        self.root.bind("<Control-Shift-C>", lambda _: self._copy())
        self.search.trace_add("write", self._schedule_search)
        self.path.trace_add("write", self._path_changed)
        self.root.after(120, self._poll)

    def _styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=WHITE)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=WHITE)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("CardMuted.TLabel", background=WHITE, foreground=MUTED)
        style.configure("Heading.TLabel", font=("Segoe UI Semibold", 23))
        style.configure("Section.TLabel", background=WHITE, font=("Segoe UI Semibold", 11))
        style.configure("TButton", font=("Segoe UI", 10), padding=(13, 9),
                        background=WHITE, foreground=INK, bordercolor=LINE)
        style.map("TButton", background=[("active", "#e9f1ef")],
                  foreground=[("disabled", "#97a4ac")])
        style.configure("Accent.TButton", background=GREEN, foreground=WHITE, borderwidth=0)
        style.map("Accent.TButton", background=[("disabled", "#c7d7d3"), ("active", "#066857")],
                  foreground=[("disabled", "#6b817b")])
        style.configure("TEntry", padding=8, fieldbackground=WHITE, bordercolor=LINE)
        style.configure("TCombobox", padding=8, fieldbackground=WHITE, bordercolor=LINE)
        style.map("TCombobox", fieldbackground=[("readonly", WHITE)],
                  selectbackground=[("readonly", WHITE)], selectforeground=[("readonly", INK)])
        style.configure("TCheckbutton", background=WHITE, foreground=INK, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", WHITE)])
        style.configure("Horizontal.TProgressbar", background=GREEN, troughcolor=LINE,
                        borderwidth=0, lightcolor=GREEN, darkcolor=GREEN)
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

    def _build(self):
        shell = ttk.Frame(self.root, padding=(28, 20, 28, 18))
        shell.pack(fill="both", expand=True)
        top = ttk.Frame(shell)
        top.pack(fill="x")
        ttk.Label(top, text="◈  AudioExtract", font=("Segoe UI Semibold", 16)).pack(side="left")
        tk.Label(top, text="  XỬ LÝ TRÊN MÁY  ", bg="#deeee8", fg=GREEN,
                 font=("Segoe UI Semibold", 9), padx=7, pady=5).pack(side="right")
        ttk.Label(shell, text="Biến lời nói thành văn bản.", style="Heading.TLabel").pack(
            anchor="w", pady=(20, 5))
        ttk.Label(shell, text="Chọn video, trích xuất lời nói và lưu transcript theo cách bạn cần.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 22))
        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        sidepanel = ttk.Frame(body, style="Card.TFrame", width=282)
        sidepanel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        sidepanel.grid_propagate(False)
        sidepanel.rowconfigure(0, weight=1)
        sidepanel.columnconfigure(0, weight=1)
        canvas = tk.Canvas(sidepanel, bg=WHITE, highlightthickness=0, width=260)
        canvas.grid(row=0, column=0, sticky="nsew")
        settings_scroll = ttk.Scrollbar(sidepanel, orient="vertical", command=canvas.yview)
        settings_scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=settings_scroll.set)
        sidebar = ttk.Frame(canvas, style="Card.TFrame", padding=(20, 20, 12, 8))
        sidebar_window = canvas.create_window(0, 0, window=sidebar, anchor="nw")
        sidebar.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(sidebar_window, width=event.width))

        def scroll_settings(event):
            inside = (sidepanel.winfo_rootx() <= event.x_root < sidepanel.winfo_rootx() + sidepanel.winfo_width()
                      and canvas.winfo_rooty() <= event.y_root < canvas.winfo_rooty() + canvas.winfo_height())
            if inside:
                canvas.yview_scroll(-int(event.delta / 120), "units")

        self.root.bind("<MouseWheel>", scroll_settings, add="+")
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text="01   Chọn nguồn", style="Section.TLabel").grid(sticky="w")
        self.choose_button = ttk.Button(sidebar, text="+  Chọn video / audio", command=self._choose)
        self.choose_button.grid(sticky="ew", pady=(12, 8))
        self.path_entry = ttk.Entry(sidebar, textvariable=self.path, font=("Segoe UI", 9))
        self.path_entry.grid(sticky="ew")
        ttk.Label(sidebar, textvariable=self.file_info, style="CardMuted.TLabel",
                  wraplength=220, font=("Segoe UI", 9)).grid(sticky="w", pady=(8, 22))
        ttk.Label(sidebar, text="02   Nhận dạng lời nói", style="Section.TLabel").grid(sticky="w")
        ttk.Label(sidebar, text="Ngôn ngữ trong video", style="CardMuted.TLabel").grid(
            sticky="w", pady=(14, 5))
        self.language_combo = ttk.Combobox(sidebar, textvariable=self.language,
                                           values=list(LANGUAGES), state="readonly")
        self.language_combo.grid(sticky="ew")
        ttk.Label(sidebar, text="Model nhận dạng", style="CardMuted.TLabel").grid(sticky="w", pady=(14, 5))
        self.model_combo = ttk.Combobox(sidebar, textvariable=self.model, values=MODELS, state="readonly")
        self.model_combo.grid(sticky="ew")
        self.model_note = ttk.Label(sidebar, text="small: cân bằng tốc độ và độ chính xác.",
                                    style="CardMuted.TLabel", wraplength=220, font=("Segoe UI", 9))
        self.model_note.grid(sticky="w", pady=(6, 0))
        self.model_combo.bind("<<ComboboxSelected>>", self._model_changed)
        ttk.Label(sidebar, text="Thiết bị xử lý", style="CardMuted.TLabel").grid(sticky="w", pady=(14, 5))
        self.device_combo = ttk.Combobox(sidebar, textvariable=self.device, state="readonly",
                                         values=("NVIDIA GPU (CUDA)", "CPU (phù hợp mọi máy)"))
        self.device_combo.grid(sticky="ew")
        self.offline_check = ttk.Checkbutton(sidebar, text="Chỉ dùng model đã tải (offline)", variable=self.offline)
        self.offline_check.grid(sticky="w", pady=(14, 0))
        # Keep the primary controls visible even on small screens or high DPI.
        actions = ttk.Frame(sidepanel, style="Card.TFrame", padding=(20, 8, 20, 16))
        actions.grid(row=1, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self.start_button = ttk.Button(actions, text="Trích xuất transcript  →", style="Accent.TButton", command=self._start)
        self.start_button.grid(sticky="ew", pady=(0, 8))
        self.stop_button = ttk.Button(actions, text="Dừng xử lý", command=self._stop, state="disabled")
        self.stop_button.grid(sticky="ew")
        ttk.Label(actions, text="Lần đầu dùng mỗi model cần Internet để tải.\nVideo và âm thanh được xử lý trên máy.",
                  style="CardMuted.TLabel", wraplength=240, font=("Segoe UI", 8)).grid(sticky="w", pady=(14, 0))

        preview = ttk.Frame(body, style="Card.TFrame", padding=20)
        preview.grid(row=0, column=1, sticky="nsew")
        preview.rowconfigure(2, weight=1)
        preview.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(preview, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Label(toolbar, textvariable=self.preview_title, style="Section.TLabel").pack(side="left")
        self.export_button = ttk.Button(toolbar, text="Xuất tệp ↓", command=self._export, state="disabled")
        self.export_button.pack(side="right")
        self.copy_button = ttk.Button(toolbar, text="Sao chép", command=self._copy, state="disabled")
        self.copy_button.pack(side="right", padx=(6, 8))
        filterbar = ttk.Frame(preview, style="Card.TFrame")
        filterbar.grid(row=1, column=0, sticky="ew", pady=(16, 12))
        self.search_entry = ttk.Entry(filterbar, textvariable=self.search, width=20)
        ttk.Label(filterbar, text="Tìm", style="CardMuted.TLabel").pack(side="left", padx=(0, 8))
        self.search_entry.pack(side="left", fill="x", expand=True)
        ttk.Label(filterbar, textvariable=self.matches, style="CardMuted.TLabel").pack(side="left", padx=8)
        ttk.Checkbutton(filterbar, text="Mốc thời gian", variable=self.show_timestamps,
                        command=self._render).pack(side="right")
        text_frame = ttk.Frame(preview, style="Card.TFrame")
        text_frame.grid(row=2, column=0, sticky="nsew")
        self.text = tk.Text(text_frame, wrap="word", bg=WHITE, fg=INK, bd=0,
                            highlightthickness=0, padx=2, pady=8, spacing1=5, spacing3=8,
                            font=("Segoe UI", 11), selectbackground="#bce7db", relief="flat",
                            cursor="xterm", state="disabled", width=30)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("time", foreground=GREEN, font=("Consolas", 9))
        self.text.tag_configure("placeholder", foreground=MUTED, spacing1=20, spacing3=12)
        self.text.tag_configure("match", background="#ffec99", foreground=INK)
        ttk.Label(preview, textvariable=self.stats, style="CardMuted.TLabel", font=("Segoe UI", 9)).grid(
            row=3, column=0, sticky="w", pady=(12, 0))
        footer = ttk.Frame(shell)
        footer.pack(fill="x", pady=(16, 0))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=820).pack(side="left")
        ttk.Label(footer, textvariable=self.elapsed, style="Muted.TLabel").pack(side="right")
        self.progress = ttk.Progressbar(shell, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(9, 0))
        self.settings = [self.choose_button, self.path_entry, self.offline_check]
        self.combos = [self.language_combo, self.model_combo, self.device_combo]

    def _placeholder(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "Lời nói trong video,\nđược lưu thành từng dòng.\n\n", "placeholder")
        self.text.insert("end", "1. Chọn video hoặc tệp âm thanh trên máy.\n"
                         "2. Chọn ngôn ngữ và model phù hợp.\n"
                         "3. Nhấn Trích xuất transcript.\n\n"
                         "Kết quả sẽ xuất hiện tại đây trong lúc xử lý.\n"
                         "Bạn có thể lưu văn bản TXT, phụ đề SRT / VTT hoặc JSON.", "placeholder")
        self.text.configure(state="disabled")

    def _choose(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(
            parent=self.root, title="Chọn video hoặc âm thanh",
            filetypes=[("Video và âm thanh", " ".join("*" + e for e in MEDIA_EXTENSIONS)),
                       ("Tất cả tệp", "*.*")],
        )
        if path:
            self.path.set(path)
            self.path_entry.xview_moveto(1)

    def _path_changed(self, *_):
        try:
            path = Path(self.path.get().strip().strip('"'))
            if path.is_file():
                self.file_info.set(f"{path.name}\n{path.stat().st_size / (1024 * 1024):,.1f} MB")
            else:
                self.file_info.set("Chọn tệp hoặc dán đường dẫn đầy đủ.")
        except (OSError, ValueError):
            self.file_info.set("Đường dẫn không hợp lệ.")

    def _model_changed(self, _=None):
        notes = {
            "tiny": "tiny: tải nhẹ, chạy nhanh; độ chính xác thấp hơn.",
            "base": "base: nhẹ, phù hợp kiểm tra nhanh.",
            "small": "small: cân bằng tốc độ và độ chính xác.",
            "medium": "medium: chính xác hơn, xử lý CPU lâu hơn.",
            "large-v3": "large-v3: model lớn, cần nhiều RAM và thời gian.",
            "turbo": "turbo: model lớn, ưu tiên GPU nếu có CUDA.",
        }
        self.model_note.configure(text=notes[self.model.get()])

    def _set_busy(self, busy: bool):
        self.busy = busy
        for widget in self.settings:
            widget.configure(state="disabled" if busy else "normal")
        for widget in self.combos:
            widget.configure(state="disabled" if busy else "readonly")
        self.start_button.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state="normal" if busy else "disabled")

    def _start(self):
        if self.busy:
            return
        try:
            source = validate_source(self.path.get().strip().strip('"'))
        except (ValueError, OSError) as error:
            messagebox.showerror("Chưa chọn được video", str(error), parent=self.root)
            return
        if self.segments and not messagebox.askyesno(
            "Tạo transcript mới", "Kết quả đang xem sẽ được thay bằng transcript mới. Tiếp tục?", parent=self.root,
        ):
            return
        self.segments.clear()
        self.metadata.clear()
        self.partial = False
        self.result_source = str(source)
        self.preview_title.set("Transcript")
        self.stats.set(f"{source.name} · Đang chuẩn bị")
        self.copy_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.started = time.monotonic()
        self.status.set("Đang khởi tạo bộ nhận dạng…")
        self._set_busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        options = Options(str(source), self.model.get(), LANGUAGES[self.language.get()],
                          "cuda" if self.device.get().startswith("NVIDIA") else "cpu", self.offline.get())
        try:
            self.events = self.context.Queue()
            self.process = self.context.Process(target=worker, args=(options, self.events), daemon=True)
            self.process.start()
        except Exception as error:
            self._finish("Không khởi tạo được tiến trình xử lý.")
            messagebox.showerror("Lỗi khởi tạo", str(error), parent=self.root)

    def _append(self, segment: Segment):
        follow = self.text.yview()[1] >= 0.98
        self.text.configure(state="normal")
        if self.show_timestamps.get():
            self.text.insert("end", f"{timestamp(segment.start)}  →  {timestamp(segment.end)}\n", "time")
        self.text.insert("end", segment.text + "\n\n")
        self.text.configure(state="disabled")
        if follow:
            self.text.see("end")

    def _render(self):
        if not self.segments:
            if not self.busy:
                self._placeholder()
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        for segment in self.segments:
            self._append(segment)
        self.text.yview_moveto(0)
        self._highlight()

    def _update_stats(self):
        language = self.metadata.get("language", "…")
        duration = timestamp(self.metadata.get("duration", 0)).split(".")[0]
        suffix = " · Kết quả một phần" if self.partial else ""
        device = "GPU/FP16" if self.metadata.get("device") == "cuda" else "CPU/INT8"
        self.stats.set(f"{len(self.segments)} đoạn · {language} · {duration} · {device}{suffix}")

    def _poll(self):
        if self.busy:
            elapsed = int(time.monotonic() - self.started)
            self.elapsed.set(f"Đã chạy {elapsed // 60:02d}:{elapsed % 60:02d}")
        # Limit per tick so long transcripts never starve the Tk event loop.
        if self.events is not None:
            drained = False
            for _ in range(150):
                try:
                    event = self.events.get_nowait()
                except (queue.Empty, ValueError, OSError):
                    drained = True
                    break
                self._handle_event(event)
                if not self.busy:
                    break
            if drained and self.busy and self.process is not None and not self.process.is_alive():
                # A clean worker flushes its queue before exiting; only consider an
                # unexpected exit once all remaining queued events have been drained.
                self.partial = bool(self.segments)
                self._finish("Tiến trình dừng đột ngột. Thử CPU hoặc model nhỏ hơn.")
        self.root.after(120, self._poll)

    def _handle_event(self, event):
        kind = event["type"]
        if kind == "status":
            self.status.set(event["text"])
            if self.busy:
                self.stats.set(event["text"])
        elif kind == "progress":
            self.progress["value"] = event["progress"]
        elif kind == "metadata":
            self.metadata.update(event["data"])
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self._update_stats()
        elif kind == "segment":
            segment = Segment(**event["data"])
            self.segments.append(segment)
            self._append(segment)
            self.progress["value"] = event["progress"]
            self.copy_button.configure(state="normal")
            self._update_stats()
        elif kind == "done":
            self.metadata["complete"] = True
            self._finish("Hoàn tất. Transcript đã sẵn sàng để sao chép hoặc xuất tệp.", complete=True)
            if not self.segments:
                self.status.set("Không tìm thấy lời nói. Thử chọn đúng ngôn ngữ hoặc model lớn hơn.")
        elif kind == "error":
            self.partial = bool(self.segments)
            self._finish("Xử lý gặp lỗi. Bạn có thể xuất các đoạn đã nhận dạng.")
            messagebox.showerror("Không thể trích xuất", event["text"], parent=self.root)

    def _cleanup(self):
        if self.process is not None:
            if self.process.pid is not None:
                self.process.join(timeout=0.2)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=1)
                self.process.close()
            self.process = None
        if self.events is not None:
            self.events.close()
            self.events = None

    def _finish(self, message: str, complete: bool = False):
        self._cleanup()
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100 if complete else 0)
        self._set_busy(False)
        self.status.set(message)
        self.copy_button.configure(state="normal" if self.segments else "disabled")
        self.export_button.configure(state="normal" if self.segments else "disabled")
        self._update_stats()
        self._highlight()

    def _stop(self):
        if not self.busy:
            return
        self.partial = True
        self.metadata["complete"] = False
        self._finish("Đã dừng. Bạn có thể xuất các đoạn đã nhận dạng hoặc chạy lại.")

    def _copy(self):
        if self.segments:
            self.root.clipboard_clear()
            self.root.clipboard_append(plain_text(self.segments))
            if not self.busy:
                self.status.set("Đã sao chép văn bản vào clipboard.")

    def _export(self):
        if not self.segments or self.busy:
            return
        suffix = "_partial" if self.partial else ""
        selected_type = tk.StringVar(value="Văn bản TXT")
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Xuất transcript", defaultextension=".txt",
            initialdir=str(Path(self.result_source).parent),
            initialfile=Path(self.result_source).stem + suffix,
            typevariable=selected_type,
            filetypes=[("Văn bản TXT", "*.txt"), ("Phụ đề SRT", "*.srt"),
                       ("Phụ đề WebVTT", "*.vtt"), ("Dữ liệu JSON", "*.json")],
        )
        if not path:
            return
        fmt = Path(path).suffix.lower().lstrip(".")
        if fmt not in {"txt", "srt", "vtt", "json"}:
            messagebox.showerror("Định dạng tệp", "Hãy dùng đuôi .txt, .srt, .vtt hoặc .json.", parent=self.root)
            return
        try:
            save_export(path, self.segments, fmt, self.metadata, self.result_source)
        except (OSError, ValueError) as error:
            messagebox.showerror("Không lưu được tệp", str(error), parent=self.root)
        else:
            self.status.set(f"Đã lưu: {path}")

    def _schedule_search(self, *_):
        if self.search_after:
            self.root.after_cancel(self.search_after)
        self.search_after = self.root.after(200, self._highlight)

    def _highlight(self):
        self.search_after = None
        self.text.tag_remove("match", "1.0", "end")
        query = self.search.get().strip()
        if not query or not self.segments:
            self.matches.set("")
            return
        index, count = "1.0", 0
        while True:
            index = self.text.search(query, index, stopindex="end", nocase=True, exact=True)
            if not index:
                break
            end = f"{index}+{len(query)}c"
            self.text.tag_add("match", index, end)
            index = end
            count += 1
        self.matches.set(f"{count} kết quả")

    def _close(self):
        if self.busy and not messagebox.askyesno(
            "Thoát AudioExtract", "Đang xử lý video. Dừng và thoát ứng dụng?", parent=self.root,
        ):
            return
        self._cleanup()
        self.root.destroy()


def launch():
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    Application(root)
    root.mainloop()
