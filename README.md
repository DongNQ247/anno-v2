# Anno 2.0

Công cụ quản lý, audit chất lượng và kiểm duyệt tập dữ liệu YOLO (YOLO Dataset Management & Quality Audit).

* **Hệ điều hành:** Linux / POSIX
* **Yêu cầu:** Python >= 3.10

---

## 1. Cài đặt (Installation)

Cài đặt package `anno` qua `pip`:

```bash
# Tạo và kích hoạt môi trường ảo (khuyến nghị)
python3 -m venv .venv
source .venv/bin/activate

# Cài đặt trực tiếp từ GitHub
pip install git+https://github.com/DongNQ247/anno-v2.git
```

Kiểm tra cài đặt:
```bash
anno --version
```

---

## 2. Hướng dẫn sử dụng cho người dùng (User Guide)

Thêm `--format text` để đọc kết quả trực tiếp trên terminal: thông tin được chia dòng, lỗi có mã và hướng dẫn bước tiếp theo. Mặc định vẫn là JSON cho Agent/script; có thể chọn rõ bằng `--format json`.

```bash
anno doctor --format text
anno label status --format text
anno review status --format text
anno review audit --help
```

`--format` dùng được trước hoặc sau tên lệnh. Mỗi lệnh có `--help` giải thích đối số và ví dụ. Trong chế độ text, kết quả thành công ra stdout, lỗi ra stderr và exit code là 1. “Reviewed” gồm cả ảnh flagged/modified; xem `Approved` để biết số ảnh đã duyệt.

### Bước 1: Khởi tạo dự án dữ liệu
Di chuyển vào thư mục chứa dữ liệu và khởi tạo cấu trúc dự án:

```bash
cd /path/to/my-dataset
anno init
```

Lệnh `anno init` tạo ra cấu trúc thư mục chuẩn:
* `dataset/images/`: Đặt ảnh của bạn vào đây.
* `dataset/labels/`: Thư mục chứa các file nhãn YOLO tương ứng (`.txt`).
* `dataset/data.yaml`: Khai báo danh sách các nhãn (class names).
* `label.md`: Tài liệu mô tả quy tắc gán nhãn cho dự án.
* `.anno/`: Cấu hình nội bộ (audit thresholds, manifest trạng thái, lock file).

---

### Bước 2: Kiểm tra tính sẵn sàng của dự án (`anno doctor`)
Sau khi thêm ảnh và cập nhật `dataset/data.yaml` cùng `label.md`, chạy lệnh kiểm tra để đảm bảo cấu trúc và quy tắc không bị lỗi:

```bash
anno doctor
```
Lệnh sẽ xác thực tính hợp lệ của class mapping, tính toàn vẹn của dữ liệu và cảnh báo nếu có xung đột hoặc cấu hình thiếu sót.

---

### Bước 3: Theo dõi tiến độ gán nhãn & kiểm duyệt
Bạn có thể theo dõi tiến độ tổng thể của tập dữ liệu bất kỳ lúc nào:

```bash
# Xem tiến độ gán nhãn (số ảnh đã có nhãn vs chưa có nhãn)
anno label status

# Xem tiến độ kiểm duyệt chất lượng (tỷ lệ approved, flagged, modified, unreviewed)
anno review status
```

---

### Bước 4: Audit chất lượng hình học tập dữ liệu (`anno review audit`)
Quét tự động toàn bộ nhãn trong dataset để phát hiện các bất thường về hình học mà không làm thay đổi hay làm sai lệch nhãn gốc:

```bash
# Chạy audit với cấu hình mặc định của dự án
anno review audit

# Hoặc chỉ định tạm thời các ngưỡng kiểm tra cụ thể
anno review audit --iou-threshold 0.85 --min-size 10
```

Các tiêu chí hình học được kiểm tra tự động:
* `high_iou`: Hai bounding box chồng lấn lên nhau quá mức.
* `tiny_box`: Box có kích thước quá nhỏ (dưới ngưỡng pixel tối thiểu).
* `contained_box`: Một box nằm lọt hoàn toàn trong box khác.
* `extreme_aspect_ratio`: Box có tỷ lệ dài/rộng bất thường.
* `out_of_bounds`: Tọa độ nhãn vượt ra ngoài kích thước ảnh.

---

### Bước 5: Trực quan hóa và kiểm tra ảnh (`anno review overview`)
Render ảnh kèm khung bounding box, nhãn và thống kê phân bố class để kiểm tra trực quan bằng mắt:

```bash
anno review overview dataset/images/001.jpg
```
Kết quả trả về đường dẫn file ảnh preview trong `.anno/tmp/` để bạn mở và xem nhanh.

---

### Bước 6: Phục hồi khi bị gián đoạn (`anno repair`)
Nếu quá trình thao tác hoặc máy bị tắt đột ngột trong khi đang ghi dữ liệu, Anno sẽ bảo vệ dữ liệu và yêu cầu chạy phục hồi:

```bash
anno repair
```
Lệnh này sẽ replay lại transaction journal nguyên tử để đưa dataset về trạng thái nhất quán, an toàn.

---

## 3. Tài liệu tham khảo

* [Hướng dẫn sử dụng chi tiết](docs/220926/user-read.md) (`user-read.md`)
* [Đặc tả kỹ thuật hệ thống](docs/220926/dev-read.md) (`dev-read.md`)
* [Quy chuẩn an toàn và Tool Contract](TOOL_CONTRACT.md) (`TOOL_CONTRACT.md`)
* [Kế hoạch triển khai & nghiệm thu](docs/plan.md) (`docs/plan.md`)

---

## 4. Đóng góp & Báo lỗi
Mọi thắc mắc hoặc báo lỗi vui lòng mở issue tại [GitHub Issues](https://github.com/DongNQ247/anno-v2/issues).
