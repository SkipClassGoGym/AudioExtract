# AudioExtract Queue

Mini app riêng để nhập danh sách video local, gọi AudioExtract chạy nền từng video
theo FIFO và lưu transcript **ngôn ngữ gốc** vào thư mục `result`.

## Mở và sử dụng

Mở `dist\AudioExtractQueue\AudioExtractQueue.exe` hoặc `Start AudioExtract Queue.vbs`.

1. Chọn cấu hình và thư mục kết quả trước khi nhập. Mặc định: model **small**, **NVIDIA GPU**, nhận diện ngôn ngữ tự động,
   dùng model đã tải/offline, xuất **TXT + SRT**.
2. Nhấn **Nhập list & chạy**, **Chọn video & chạy** hoặc **Dán list & chạy**.
   Hàng đợi tự bắt đầu ngay sau khi nhập; nếu đang chạy thì video mới được thêm cuối hàng.
3. Thứ tự trong cột FIFO chính là thứ tự xử lý.
4. Chỉ chạy một video tại một thời điểm; khi xong sẽ tự
   lưu kết quả rồi chạy video tiếp theo. Nếu một video lỗi, ghi lại lỗi và tiếp tục dòng sau.
5. Kết quả mặc định ở `D:\AudioExtract\result`. Có thể chọn thư mục khác.

Nút **Chạy hàng đợi** dùng để tiếp tục sau khi dừng, mở lại app hoặc đưa dòng lỗi về Chờ.

Ví dụ `D:\Videos\Bài học 01.mp4` tạo `result\Bài học 01.txt` và `result\Bài học 01.srt`.
Nếu đã có kết quả cùng tên hoặc hai video ở các thư mục khác nhau có cùng tên,
app thêm `__2`, `__3`, ...; không ghi đè kết quả cũ. Chạy lại một video cũng tạo tên mới.

Double-click dòng đã hoàn tất để mở transcript TXT. **Mở result** mở thư mục kết quả.

Trong **Xuất tệp**, chọn **TXT có timestamp** để lưu một tệp `<tên video>.txt`,
mỗi dòng có thời điểm bắt đầu của đoạn lời nói trong video gốc:

```text
[00:00:10] Xin chào mọi người.
[01:12:35] Chúng ta tiếp tục phần tiếp theo.
```

Các lựa chọn TXT thường vẫn giữ nguyên. Dòng lệnh dùng `--formats txt_time`.

Để xuất **cả hai bản TXT trong cùng một lần nhận dạng**, chọn **TXT + TXT timestamp**:

- `<tên video>.txt`: văn bản thường.
- `<tên video>_timestamp.txt`: văn bản kèm `[HH:MM:SS]` ở đầu mỗi đoạn.

Dòng lệnh dùng `--formats txt,txt_time`. Khi tên bị trùng, cả cặp kết quả dùng cùng
hậu tố, ví dụ `Video__2.txt` và `Video__2_timestamp.txt`.

## Định dạng danh sách

TXT: UTF-8, mỗi dòng một đường dẫn. Dòng trống và dòng bắt đầu bằng `#` được bỏ qua.
Có thể dán đường dẫn có dấu cách hoặc dấu tiếng Việt, có/không có dấu ngoặc kép.

```text
D:\Videos\Bài học 01.mp4
D:\Videos\Bài học 02.mkv
```

CSV: cột `path`, `video`, `file`, `filepath`, `video_path`, `source`, `đường dẫn`
hoặc `duong_dan`; nếu không có header, dùng cột đầu tiên. Phân cách bằng dấu phẩy,
chấm phẩy hoặc tab. Đường dẫn có ký tự phân cách phải được đặt trong ngoặc kép.

JSON: danh sách chuỗi đường dẫn hoặc các đối tượng có thuộc tính `path`/`video`/`file`/`source`.
Cũng nhận đối tượng `{"videos": [...]}` hoặc `{"files": [...]}`.
Đường dẫn Windows trong JSON cần escape dấu gạch chéo, hoặc dùng `/`.

```json
["D:/Videos/Bài học 01.mp4", "D:/Videos/Bài học 02.mkv"]
```

Đường dẫn tương đối trong tệp list được tính từ **thư mục chứa list**.
Đường dẫn tương đối được dán trực tiếp được tính từ thư mục dự án AudioExtract.
App giữ nguyên thứ tự và cả các dòng trùng lặp. Không hỗ trợ URL tải video.

## Tạm dừng, lỗi và khôi phục

- **Dừng sau video hiện tại:** xử lý/lưu xong video đang chạy rồi dừng; danh sách chờ được giữ.
- **Dừng ngay:** kết thúc tiến trình AudioExtract do mini app khởi chạy; không lưu transcript
  dở dang của video đang chạy. Kết quả những video đã xong vẫn được giữ.
- **Chạy lại dòng lỗi:** chọn các dòng Lỗi/Đã dừng rồi nhấn nút để đưa chúng về trạng thái Chờ.
- **Xóa dòng chọn:** chỉ xóa khỏi danh sách, không xóa video hoặc kết quả. Không xóa dòng đang chạy.
- Danh sách và cấu hình được lưu ở `%LOCALAPPDATA%\AudioExtractQueue\queue.json`.
  Khi mở lại app, các video đã hoàn tất được giữ nguyên, video bị gián đoạn trở về Chờ.
  Cần nhấn Chạy hàng đợi để tiếp tục; video gián đoạn được xử lý lại từ đầu.
- Log chi tiết từng video ở `%LOCALAPPDATA%\AudioExtractQueue\logs`.

## Cách kết nối AudioExtract

Trên máy này, app mặc định gọi `.venv\Scripts\python.exe main.py --input ...`
ở chế độ nền, sử dụng bộ nhận dạng và cách chia đoạn tối đa 2 phút đã sửa cho video dài.
Không cần thao tác hay tự bấm nút trong giao diện AudioExtract.

Nút **Chọn ứng dụng** cũng nhận `AudioExtractGPU-v2.exe` và các EXE AudioExtract
có CLI `--input`, `--output`, `--format json`, `--model`, `--language`, `--device`, `--offline`.
Bản EXE cũ có thể không phát tiến độ ra console; khi đó mini app vẫn hiện video đang chạy
và thời gian chờ, rồi cập nhật khi tiến trình kết thúc.

Mini app không chứa model/CUDA. Khi chép sang máy khác, cần có AudioExtract phù hợp
và model ở máy đó, rồi chọn lại đường dẫn ứng dụng. Để chọn model chưa tải,
bỏ chọn **Model đã tải / offline** và dùng Internet.

Tránh chạy thêm tác vụ GPU khác của AudioExtract khi hàng đợi đang chạy nếu VRAM hạn chế.
Có thể chọn **medium** trong giao diện; model này cần nhiều RAM/VRAM hơn small.

## Đóng gói lại

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_queue.ps1
```

Mini app dùng thư viện chuẩn Python/Tkinter, không cần cài thêm thư viện AI.

Có thể chạy list từ dòng lệnh, không mở GUI:

```powershell
.\dist\AudioExtractQueue\AudioExtractQueue.exe --batch "D:\Videos\videos.txt" --result "D:\AudioExtract\result" --model medium --device cuda --offline
```

Lần chạy dòng lệnh lưu trạng thái và log riêng trong `result\_queue_runs`.
Mã thoát 0 khi tất cả video hoàn tất; mã 1 khi có lỗi trong danh sách.
