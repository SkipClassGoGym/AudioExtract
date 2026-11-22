"""Small Windows desktop controller for sequential local transcription."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .queueing import (
    Backend, QueueRunner, QueueStore, RunSettings, app_data, default_backend,
    import_list, parse_list, project_root,
)


STATES = {"pending": "Chờ", "running": "Đang chạy", "done": "Hoàn tất",
          "failed": "Lỗi", "cancelled": "Đã dừng"}
LANGUAGES = {"Tự nhận diện": "auto", "Tiếng Việt": "vi", "English": "en",
             "日本語": "ja", "中文": "zh", "한국어": "ko", "Français": "fr",
             "Deutsch": "de", "Español": "es", "ไทย": "th", "Indonesia": "id", "Русский": "ru"}
FORMATS = {"TXT + SRT": ("txt", "srt"), "Chỉ TXT": ("txt",),
           "TXT + SRT + JSON": ("txt", "srt", "json"),
           "TXT có timestamp": ("txt_time",),
           "TXT + TXT timestamp": ("txt", "txt_time")}


class QueueApplication:
    def __init__(self, root: tk.Tk, store: QueueStore | None = None):
        self.root = root
        root.title("AudioExtract Queue — Danh sách video FIFO")
        root.geometry("1140x800")
        root.minsize(970, 690)
        self.store = store or QueueStore(app_data() / "queue.json")
        self.events = queue.Queue()
        self.runner = QueueRunner(self.store, self.events)
        self.busy = False
        self.closing = False
        self.active_id = None
        self.started_at = 0.0
        self.current_progress = 0
        settings = self.store.settings
        self.backend = tk.StringVar(value=settings.get("backend") or default_backend())
        self.result_dir = tk.StringVar(value=settings.get("result_dir") or str(project_root() / "result"))
        self.model = tk.StringVar(value=settings.get("model", "small"))
        self.language = tk.StringVar(value=settings.get("language", "Tự nhận diện"))
        self.device = tk.StringVar(value=settings.get("device", "NVIDIA GPU"))
        self.offline = tk.BooleanVar(value=settings.get("offline", True))
        self.formats = tk.StringVar(value=settings.get("formats", "TXT + SRT"))
        self.status = tk.StringVar(value="Chọn cấu hình rồi nhập danh sách. App sẽ tự chạy từng video theo FIFO.")
        self.counts = tk.StringVar()
        self.elapsed = tk.StringVar()
        self.detail = tk.StringVar(value="Nhấp một dòng để xem đường dẫn, kết quả hoặc lỗi.")
        self._build()
        self._refresh()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(150, self._poll)

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f7")
        style.configure("TLabel", background="#f3f5f7", foreground="#172b35", font=("Segoe UI", 10))
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#087f6b", foreground="white")
        style.map("Accent.TButton", background=[("active", "#066857"), ("disabled", "#c7d7d3")])
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)
        style.configure("Treeview", rowheight=30, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), padding=6)
        style.configure("Horizontal.TProgressbar", background="#087f6b", troughcolor="#dce5e9")
        shell = ttk.Frame(self.root, padding=22)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(4, weight=1)
        ttk.Label(shell, text="AudioExtract  /  Hàng đợi video", font=("Segoe UI Semibold", 21)).grid(sticky="w")
        ttk.Label(shell, text="Nhập một danh sách. Tự trích transcript ngôn ngữ gốc theo FIFO và lưu theo tên video.",
                  foreground="#667984").grid(sticky="w", pady=(5, 15))

        config = ttk.Frame(shell)
        config.grid(row=2, column=0, sticky="ew")
        config.columnconfigure(1, weight=1)
        ttk.Label(config, text="AudioExtract").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.backend_entry = ttk.Entry(config, textvariable=self.backend)
        self.backend_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.backend_button = ttk.Button(config, text="Chọn ứng dụng", command=self._choose_backend)
        self.backend_button.grid(row=0, column=2, sticky="ew")
        ttk.Label(config, text="Lưu kết quả").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        self.result_entry = ttk.Entry(config, textvariable=self.result_dir)
        self.result_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self.result_button = ttk.Button(config, text="Chọn thư mục", command=self._choose_result)
        self.result_button.grid(row=1, column=2, sticky="ew")
        options = ttk.Frame(config)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(2, 12))
        self.combos = []
        for column, (label, variable, values, width) in enumerate([
            ("Model", self.model, ("tiny", "base", "small", "medium", "large-v3", "turbo"), 11),
            ("Ngôn ngữ", self.language, tuple(LANGUAGES), 17),
            ("Thiết bị", self.device, ("NVIDIA GPU", "CPU"), 13),
            ("Xuất tệp", self.formats, tuple(FORMATS), 19),
        ]):
            cell = ttk.Frame(options)
            cell.grid(row=0, column=column, sticky="w", padx=(0, 15))
            ttk.Label(cell, text=label, foreground="#667984").pack(anchor="w", pady=(0, 4))
            combo = ttk.Combobox(cell, textvariable=variable, values=values, state="readonly", width=width)
            combo.pack()
            self.combos.append(combo)
        self.offline_check = ttk.Checkbutton(options, text="Model đã tải / offline", variable=self.offline)
        self.offline_check.grid(row=0, column=4, sticky="s", pady=(0, 6))

        toolbar = ttk.Frame(shell)
        toolbar.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for label, command in [("+ Nhập list & chạy", self._import),
                               ("+ Chọn video & chạy", self._choose_videos), ("Dán list & chạy", self._paste),
                               ("Xóa dòng chọn", self._remove), ("Chạy lại dòng lỗi", self._retry)]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 7))
        table = ttk.Frame(shell)
        table.grid(row=4, column=0, sticky="nsew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("number", "video", "state", "progress", "output"),
                                 show="headings", selectmode="extended")
        for name, heading, width, stretch in [
            ("number", "FIFO", 45, False), ("video", "Video", 310, True),
            ("state", "Trạng thái", 110, False), ("progress", "Tiến độ", 80, False),
            ("output", "Tệp kết quả", 320, True),
        ]:
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, minwidth=width if not stretch else 140, stretch=stretch)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure("done", foreground="#087f6b")
        self.tree.tag_configure("failed", foreground="#b42318")
        self.tree.tag_configure("running", background="#e4f3ed")
        self.tree.bind("<<TreeviewSelect>>", self._selection)
        self.tree.bind("<Double-1>", self._open_selected)
        ttk.Label(shell, textvariable=self.detail, foreground="#667984", wraplength=1040,
                  font=("Segoe UI", 9)).grid(row=5, column=0, sticky="ew", pady=(8, 8))
        self.log = tk.Text(shell, height=4, wrap="word", font=("Consolas", 9),
                           bg="#fff", fg="#485e69", state="disabled", relief="flat", padx=8, pady=6)
        self.log.grid(row=6, column=0, sticky="ew")
        controls = ttk.Frame(shell)
        controls.grid(row=7, column=0, sticky="ew", pady=(14, 8))
        self.start_button = ttk.Button(controls, text="▶ Chạy hàng đợi", style="Accent.TButton", command=self._start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.pause_button = ttk.Button(controls, text="Dừng sau video hiện tại", command=self._pause, state="disabled")
        self.pause_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ttk.Button(controls, text="Dừng ngay", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left")
        ttk.Button(controls, text="Mở result ↗", command=self._open_result).pack(side="right")
        ttk.Label(controls, textvariable=self.elapsed, foreground="#667984").pack(side="right", padx=12)
        self.progress = ttk.Progressbar(shell, maximum=100)
        self.progress.grid(row=8, column=0, sticky="ew")
        ttk.Label(shell, textvariable=self.status, wraplength=1040).grid(row=9, column=0, sticky="ew", pady=(8, 3))
        ttk.Label(shell, textvariable=self.counts, foreground="#667984", font=("Segoe UI", 9)).grid(
            row=10, column=0, sticky="w")
        self.settings_widgets = [self.backend_entry, self.backend_button, self.result_entry,
                                 self.result_button, self.offline_check]

    def _choose_backend(self):
        path = filedialog.askopenfilename(title="Chọn AudioExtract", initialdir=str(project_root()),
                                          filetypes=[("AudioExtract", "*.exe *.py"), ("Tất cả", "*.*")])
        if path:
            self.backend.set(path)

    def _choose_result(self):
        path = filedialog.askdirectory(title="Thư mục lưu transcript", initialdir=str(project_root()))
        if path:
            self.result_dir.set(path)

    def _add(self, sources):
        if not sources:
            self.status.set("Danh sách không có đường dẫn video.")
            return
        self.store.add(sources)
        self._refresh()
        self._log(f"Đã thêm {len(sources)} video vào cuối hàng đợi.")
        if not self.busy and not self.runner.running:
            self._start()

    def _import(self):
        path = filedialog.askopenfilename(title="Nhập danh sách video theo đúng thứ tự",
                                          filetypes=[("Danh sách video", "*.txt *.csv *.json"), ("Tất cả", "*.*")])
        if path:
            try:
                self._add(import_list(path))
            except (OSError, ValueError, KeyError, TypeError) as error:
                messagebox.showerror("Không nhập được danh sách", str(error), parent=self.root)

    def _choose_videos(self):
        paths = filedialog.askopenfilenames(title="Thêm video vào cuối hàng đợi", filetypes=[
            ("Video / audio", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.wmv *.mp3 *.wav *.m4a *.flac *.ogg *.aac"),
            ("Tất cả", "*.*"),
        ])
        self._add(list(paths))

    def _paste(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Dán danh sách — mỗi dòng một đường dẫn video")
        dialog.geometry("760x420")
        dialog.transient(self.root)
        ttk.Label(dialog, text="Mỗi dòng một đường dẫn. Thứ tự các dòng chính là thứ tự xử lý FIFO.",
                  padding=12).pack(anchor="w")
        text = tk.Text(dialog, wrap="none", font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=12)

        def accept():
            try:
                sources = parse_list(text.get("1.0", "end"), project_root())
                self._add(sources)
            except (OSError, ValueError) as error:
                messagebox.showerror("Đường dẫn không hợp lệ", str(error), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(dialog, text="Thêm vào hàng đợi", command=accept, style="Accent.TButton").pack(
            anchor="e", padx=12, pady=12)
        text.focus_set()
        dialog.grab_set()

    def _remove(self):
        self.store.remove(set(self.tree.selection()))
        self._refresh()

    def _retry(self):
        self.store.retry(set(self.tree.selection()))
        self._refresh()

    def _selection(self, _=None):
        ids = self.tree.selection()
        if not ids:
            return
        job = next((j for j in self.store.snapshot() if j.id == ids[0]), None)
        if job:
            self.detail.set(job.source + ("  |  " + job.error if job.error else "")
                            + ("  |  " + ", ".join(job.outputs) if job.outputs else ""))

    def _refresh(self):
        jobs = self.store.snapshot()
        current = set(self.tree.get_children())
        wanted = {j.id for j in jobs}
        for item in current - wanted:
            self.tree.delete(item)
        for index, job in enumerate(jobs, 1):
            values = (index, Path(job.source).name, STATES.get(job.state, job.state),
                      f"{job.progress:.0f}%", ", ".join(Path(p).name for p in job.outputs))
            if job.id in current:
                self.tree.item(job.id, values=values, tags=(job.state,))
            else:
                self.tree.insert("", "end", iid=job.id, values=values, tags=(job.state,))
        counts = {state: sum(j.state == state for j in jobs) for state in STATES}
        self.counts.set(f"Tổng {len(jobs)}  ·  Chờ {counts['pending']}  ·  Đang chạy {counts['running']}"
                        f"  ·  Hoàn tất {counts['done']}  ·  Lỗi {counts['failed']}  ·  Đã dừng {counts['cancelled']}")

    def _set_busy(self, busy):
        self.busy = busy
        self.start_button.configure(state="disabled" if busy else "normal")
        self.pause_button.configure(state="normal" if busy else "disabled")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        for widget in self.settings_widgets:
            widget.configure(state="disabled" if busy else "normal")
        for widget in self.combos:
            widget.configure(state="disabled" if busy else "readonly")

    def _start(self):
        if self.busy or self.runner.running:
            return
        if not any(j.state == "pending" for j in self.store.snapshot()):
            self.status.set("Không có video đang chờ. Hãy thêm video hoặc chọn dòng lỗi rồi Chạy lại.")
            return
        try:
            if not self.result_dir.get().strip():
                raise ValueError("Hãy chọn thư mục lưu kết quả.")
            result = Path(self.result_dir.get()).expanduser().resolve()
            result.mkdir(parents=True, exist_ok=True)
            settings = RunSettings(Backend.from_path(self.backend.get()), str(result), self.model.get(),
                                   LANGUAGES[self.language.get()], "cuda" if self.device.get() == "NVIDIA GPU" else "cpu",
                                   self.offline.get(), FORMATS[self.formats.get()])
            self.store.settings = {"backend": self.backend.get(), "result_dir": str(result),
                                   "model": self.model.get(), "language": self.language.get(),
                                   "device": self.device.get(), "offline": self.offline.get(), "formats": self.formats.get()}
            self.store.save()
            self._set_busy(True)
            self.status.set("Đang khởi động AudioExtract…")
            self.runner.start(settings)
        except (OSError, ValueError, KeyError) as error:
            self._set_busy(False)
            messagebox.showerror("Chưa thể chạy hàng đợi", str(error), parent=self.root)

    def _pause(self):
        self.runner.pause_after_current()
        self.status.set("Sẽ dừng hàng đợi khi video hiện tại hoàn tất. Các video còn lại vẫn được giữ.")
        self.pause_button.configure(state="disabled")

    def _cancel(self):
        self.runner.cancel_current()
        self.status.set("Đang dừng video hiện tại… Danh sách chờ được giữ lại.")
        self.cancel_button.configure(state="disabled")

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 400:
            self.log.delete("1.0", "100.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll(self):
        refresh = False
        for _ in range(200):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event["type"]
            if kind == "started":
                self.active_id = event["id"]
                self.started_at = time.monotonic()
                self.current_progress = 0
                self.progress["value"] = 0
                self.status.set(f"Đang xử lý: {Path(event['source']).name}")
                self._log(f"Bắt đầu: {event['source']}")
                self.tree.see(event["id"])
            elif kind == "progress":
                self.current_progress = event["progress"]
                self.progress["value"] = self.current_progress
                refresh = True
            elif kind == "status":
                if not self.runner.halt.is_set():
                    self.status.set(event["text"])
            elif kind == "log":
                self._log(event["text"])
            elif kind == "changed":
                refresh = True
            elif kind == "finished":
                self._set_busy(False)
                self.active_id = None
                self.status.set("Đã dừng hàng đợi." if self.runner.halt.is_set()
                                else "Đã xử lý hết danh sách. Xem cột trạng thái và thư mục result.")
                refresh = True
                # Videos added after the runner saw an empty queue but before this event.
                if not self.runner.halt.is_set() and any(j.state == "pending" for j in self.store.snapshot()):
                    self.runner.thread.join(timeout=2)  # "finished" is emitted just before the thread exits
                    self._start()
        if refresh:
            self._refresh()
        if self.active_id:
            seconds = int(time.monotonic() - self.started_at)
            self.elapsed.set(f"Video hiện tại: {seconds // 60:02d}:{seconds % 60:02d}")
        if self.closing and not self.runner.running:
            self.root.destroy()
            return
        self.root.after(150, self._poll)

    def _open_result(self):
        try:
            path = Path(self.result_dir.get()).resolve()
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except OSError as error:
            messagebox.showerror("Không mở được thư mục", str(error), parent=self.root)

    def _open_selected(self, _=None):
        ids = self.tree.selection()
        job = next((j for j in self.store.snapshot() if ids and j.id == ids[0]), None)
        if job and job.outputs:
            try:
                os.startfile(job.outputs[0])
            except OSError as error:
                messagebox.showerror("Không mở được kết quả", str(error), parent=self.root)

    def _close(self):
        if self.runner.running:
            if not messagebox.askyesno("Đóng hàng đợi", "Dừng video đang chạy và thoát? Danh sách và kết quả đã hoàn tất sẽ được giữ.",
                                       parent=self.root):
                return
            self.closing = True
            self.runner.cancel_current()
            self.status.set("Đang dừng AudioExtract để thoát an toàn…")
            return
        self.store.save()
        self.root.destroy()


def launch():
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    try:
        QueueApplication(root)
    except (OSError, ValueError, TypeError) as error:
        messagebox.showerror("Không mở được hàng đợi", f"{error}\n\nDữ liệu hàng đợi: {app_data() / 'queue.json'}", parent=root)
        root.destroy()
        return
    root.mainloop()
