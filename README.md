# AudioExtract

Ứng dụng desktop Windows chuyển lời nói trong video/audio local thành transcript.
Giao diện tiếng Việt; nhận dạng bằng faster-whisper; không cần API key.

## Mở ứng dụng

Mở bản GPU đã sửa lỗi video dài tại **dist\AudioExtractGPU-v2\AudioExtractGPU-v2.exe**.
Bản này mặc định chọn **NVIDIA GPU (CUDA)** và model **small**;
các thư viện GPU nằm trong thư mục ứng dụng, không cần cài CUDA toolkit toàn hệ thống.
Bản CPU trước đó vẫn ở `dist\AudioExtract\AudioExtract.exe`.

Khi chuyển sang máy khác, sao chép **toàn bộ thư mục dist\AudioExtractGPU**,
bao gồm thư mục `_internal`; không chỉ sao chép riêng tệp EXE.

Nếu chạy từ mã nguồn:

1. Cài Python 64-bit từ 3.10 trở lên (bản này được kiểm tra trên Python 3.14).
2. Chạy `setup.bat` một lần để cài các thư viện vào `.venv`.
3. Mở `Start AudioExtract.vbs` để chạy không hiện cửa sổ terminal.
   Hoặc chạy `.venv\Scripts\python.exe main.py` để xem thông báo trong terminal.

## Cách dùng

1. Nhấn **Chọn video / audio**, hoặc dán đường dẫn tệp vào ô bên dưới.
2. Chọn **Tiếng Việt**, **English** hoặc **Tự nhận diện** theo lời nói trong video.
3. Để model **small** và thiết bị **NVIDIA GPU (CUDA)** khi bắt đầu.
   Nếu máy không có NVIDIA GPU, chuyển thiết bị sang **CPU**.
4. Nhấn **Trích xuất transcript**. Các đoạn lời nói xuất hiện dần kèm mốc thời gian.
5. Nhấn **Sao chép** hoặc **Xuất tệp**; chọn TXT, SRT, VTT hoặc JSON.

Các định dạng đầu vào gồm MP4, MKV, MOV, AVI, WebM và các định dạng audio thông dụng.
Tệp cần có luồng âm thanh mà PyAV đọc được. Ứng dụng nhận dạng lời nói;
không đọc chữ hiển thị trong khung hình và không tách tên từng người nói.

- **TXT:** văn bản thuần, mỗi đoạn một dòng.
- **SRT / VTT:** phụ đề có mốc thời gian của video gốc.
- **JSON:** các đoạn, mốc thời gian và thông tin nhận dạng; `complete: false` nếu dừng/lỗi.
- **Dừng xử lý:** dừng tiến trình; giữ các đoạn đã hiện để có thể xuất tệp với hậu tố `_partial`.
  Chạy lại sẽ xử lý từ đầu, không tiếp tục tại điểm đã dừng.
- **Tìm:** tô sáng từ/cụm từ trong transcript. Có thể bật/tắt hiển thị mốc thời gian.
- Phím tắt: `Ctrl+O` chọn tệp, `Ctrl+S` xuất tệp, `Ctrl+Shift+C` sao chép toàn bộ văn bản.

## Model, offline và phần cứng

Lần đầu sử dụng mỗi model, ứng dụng tải model từ Hugging Face. Sau đó chọn
**Chỉ dùng model đã tải (offline)** để ngăn truy cập mạng khi nhận dạng.
Video và âm thanh không được tải lên dịch vụ nhận dạng. Không dùng API trả phí.

Model và log lỗi được lưu ở `%LOCALAPPDATA%\AudioExtract`.
Model không được đóng gói trong EXE. Trên máy mới cần tải model một lần,
hoặc chép nguyên thư mục `models` vào cùng vị trí trong tài khoản mới.

| Model | Dùng khi |
| --- | --- |
| tiny / base | Cần kiểm tra nhanh, ưu tiên nhẹ |
| small | Cân bằng tốc độ và độ chính xác trên CPU |
| medium | Muốn nhận dạng kỹ hơn, chấp nhận xử lý lâu hơn |
| large-v3 / turbo | Máy nhiều RAM hoặc có NVIDIA GPU phù hợp |

CPU chạy INT8; NVIDIA GPU chạy FP16 và cần CUDA 12/cuDNN 9 tương thích.
Bản GPU đi kèm cuBLAS 12.3, cuDNN 9.1 và các runtime cần thiết, phù hợp driver của máy này.
Khi chạy từ mã nguồn, `setup.bat` cài thêm các gói trong `requirements-gpu.txt`.
Nếu gặp lỗi GPU, chọn CPU. Model `small` được ưu tiên cho RTX 3050 Ti Laptop 4 GB;
model lớn có thể thiếu VRAM. Thanh trạng thái transcript hiển thị `GPU/FP16` khi nhận dạng bằng GPU.
Không cần cài FFmpeg riêng vì PyAV kèm thư viện giải mã.
Video dài được đọc và nhận dạng lần lượt từng đoạn tối đa 2 phút, ưu tiên cắt ở điểm yên lặng.
Ứng dụng không tạo phổ âm thanh cho cả video 3 giờ cùng lúc, tránh cấp phát RAM nhiều GB.
Mốc thời gian phụ đề được cộng về đúng vị trí trong video gốc. Những từ nằm sát điểm chia
đoạn vẫn nên được rà soát. Thanh tiến độ chạy cả khi một đoạn không có lời nói.
Thanh tiến độ dựa trên mốc thời gian đã nhận dạng,
không phải ước tính chính xác thời gian chờ. Model được giải phóng sau mỗi lần chạy.

Chất lượng phụ thuộc tiếng ồn, người nói và model. Nếu video tiếng Việt nhận dạng sai,
chọn rõ **Tiếng Việt** và thử model lớn hơn. Kết quả nên được rà soát trước khi dùng làm phụ đề chính thức.

## Dòng lệnh

```powershell
.\.venv\Scripts\python.exe main.py --input "D:\Videos\bai-giang.mp4" --language vi --model small --format srt
.\.venv\Scripts\python.exe main.py --input "D:\Videos\bai-giang.mp4" --offline --output "D:\Videos\transcript.txt"
```

Không ghi đè tệp xuất sẵn có trừ khi truyền `--overwrite`. Không ghi đè video nguồn.
Chế độ dòng lệnh dùng bản Python; bản EXE đóng gói ưu tiên giao diện desktop.

## Kiểm tra và đóng gói lại

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -Gpu
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -Gpu -OutputName AudioExtractGPU-v2
```

Kết quả bản GPU: `dist\AudioExtractGPU\AudioExtractGPU.exe`.
Tham số `-Gpu` đóng gói cả DLL NVIDIA vào `_internal\nvidia`.
Kiểm tra nhận dạng GPU thực tế (cần video mẫu trong `.test-artifacts` và model small đã tải):

```powershell
.\.venv\Scripts\python.exe scripts\smoke_gui.py --gpu
.\.venv\Scripts\python.exe scripts\smoke_frozen.py --gpu
.\.venv\Scripts\python.exe scripts\smoke_frozen.py --gpu --medium
.\.venv\Scripts\python.exe scripts\smoke_frozen.py --gpu --medium --v2
.\.venv\Scripts\python.exe scripts\smoke_long_audio.py
```

`requirements-lock.txt` ghi lại phiên bản thư viện đã dùng để kiểm tra bản này.

Tài liệu thư viện: https://github.com/SYSTRAN/faster-whisper

## Mini app chạy danh sách FIFO

Mở `dist\AudioExtractQueue\AudioExtractQueue.exe` để nhập list TXT/CSV/JSON,
chọn nhiều video hoặc dán đường dẫn. App gọi AudioExtract ở chế độ nền,
xử lý lần lượt theo FIFO và lưu `result\<tên video>.txt` kèm SRT.
Tên trùng được thêm `__2`, `__3` để giữ kết quả cũ. Có dừng sau video hiện tại,
dừng ngay, chạy lại dòng lỗi và lưu/khôi phục hàng đợi.

Mặc định mini app dùng **small + GPU + offline**; có thể chọn medium trong giao diện.
Hướng dẫn đầy đủ: [mini_app/README.md](mini_app/README.md).
