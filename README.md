# AudioExtract

Ứng dụng desktop Windows chuyển lời nói trong video/audio thành transcript (TXT, SRT, VTT, JSON).
Chạy hoàn toàn trên máy bằng [faster-whisper](https://github.com/SYSTRAN/faster-whisper), không cần API key, không upload video.

- Giao diện tiếng Việt, hỗ trợ nhiều ngôn ngữ hoặc tự nhận diện.
- Chạy bằng NVIDIA GPU (CUDA, FP16) hoặc CPU (INT8).
- Video dài nhiều giờ được xử lý từng khúc 2 phút nên không tốn nhiều RAM/VRAM.
- Có kèm **AudioExtract Queue**: nhập danh sách video và xử lý lần lượt (FIFO).

## Cài đặt

Yêu cầu: Windows 10/11, [Python 3.10+ 64-bit](https://www.python.org/downloads/). Không cần cài FFmpeg hay CUDA toolkit.

```powershell
git clone https://github.com/SkipClassGoGym/AudioExtract.git
cd AudioExtract
setup.bat
```

`setup.bat` tạo `.venv` và cài thư viện, kể cả runtime CUDA cho GPU.

## Chạy

| Cách | Lệnh |
| --- | --- |
| Giao diện chính | Mở `Start AudioExtract.vbs` |
| Hàng đợi nhiều video | Mở `Start AudioExtract Queue.vbs` |
| Dòng lệnh | `.venv\Scripts\python.exe main.py --input "video.mp4" --language vi --model small --format srt` |

Cách dùng: chọn video → chọn ngôn ngữ, model, thiết bị → **Trích xuất transcript** → **Xuất tệp**.

Lần đầu dùng một model, app cần Internet để tải model về `%LOCALAPPDATA%\AudioExtract\models`.
Sau đó có thể bật **Chỉ dùng model đã tải (offline)**.

## Chọn model theo VRAM

| VRAM GPU | Model khuyến nghị | Ghi chú |
| --- | --- | --- |
| Không có NVIDIA GPU | `small` (CPU) | `base` nếu máy yếu; `medium` chính xác hơn nhưng chậm |
| 2–4 GB | `small` | `medium` có thể thiếu VRAM |
| 6 GB | `medium` hoặc `turbo` | |
| 8 GB trở lên | **`turbo`** | Gần bằng large-v3, nhanh hơn nhiều |
| 10–12 GB trở lên | **`large-v3`** | Chính xác nhất, nhất là tiếng Việt |

Mức VRAM trong bảng là ước tính. Nếu báo thiếu VRAM, hãy đóng các app đang dùng GPU hoặc hạ một bậc model.
Với tiếng Việt, nên chọn rõ **Tiếng Việt** thay vì để tự nhận diện.

## Build EXE (tùy chọn)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -Gpu      # dist\AudioExtractGPU\
powershell -ExecutionPolicy Bypass -File scripts\build.ps1           # bản CPU
powershell -ExecutionPolicy Bypass -File scripts\build_queue.ps1     # dist\AudioExtractQueue\
```

Khi chép sang máy khác, chép **cả thư mục** trong `dist\`, không chỉ riêng tệp EXE.

## Kiểm tra

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

Hướng dẫn chi tiết cho app hàng đợi: [mini_app/README.md](mini_app/README.md).
