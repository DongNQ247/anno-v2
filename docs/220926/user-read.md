# Hướng dẫn sử dụng Anno 2.0

Anno hỗ trợ Agent gán nhãn YOLO bằng tọa độ lưới và kiểm duyệt tường minh. Chạy trên Linux/POSIX, Python >= 3.10. Chất lượng nhãn vẫn cần kiểm tra bằng hình ảnh và quy tắc của dự án; chưa có cam kết độ chính xác hay mức tiết kiệm token.

## 1. Cài đặt và khởi tạo

Tại repo công cụ:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
source .venv/bin/activate
```

Chuyển đến root của project dữ liệu rồi chạy:

```bash
anno init
```

Đặt ảnh vào `dataset/images/`; điền `dataset/data.yaml`, ví dụ `names: [car, pedestrian]`, và mô tả quy tắc trong `label.md`. Init tạo `.anno/config/config.json`, manifest, skills và schemas. `init --force` cũng không ghi đè dữ liệu/hướng dẫn cũ.

```bash
anno doctor
```

Nếu có lỗi, xem `error.details.errors`. Nếu `class_compiled` false, thực hiện skill `.anno/skills/anno-align/SKILL.md`: đọc hướng dẫn, hỏi lại các điểm mơ hồ, rồi tạo `.anno/skills/anno-class/SKILL.md` theo các quy tắc đã thống nhất. Thiếu model không ngăn gán nhãn; infer hiện chưa bật.

`examples/` là dữ liệu tham khảo trực quan. Nếu muốn render examples bằng CLI, tạo project mẫu riêng và đưa bản sao ảnh/nhãn vào `dataset/` của project đó; CLI không nhận ảnh ngoài image root.

## 2. Gán nhãn

```bash
anno label next
anno label grid dataset/images/001.jpg
anno label select dataset/images/001.jpg --cells A1:B2 --margin 0.20
anno label grid dataset/images/001.jpg --cells A1:B2
anno label visual dataset/images/001.jpg --cells A1-a1:B2-h8 --margin 0.20
anno label verify dataset/images/001.jpg --class 0 --cells A1-a1:B2-h8
```

Lấy `verification_id` từ kết quả verify, truyền vào lệnh ghi:

```bash
anno label bbox add dataset/images/001.jpg --class 0 --cells A1-a1:B2-h8 --verification-id TOKEN
```

Verify lại cho mỗi lần add/update. Update cần thêm `--index N`; delete chỉ cần index. Xem index hiện tại bằng `anno label bbox list IMAGE`. Sau khi đã xác nhận ảnh không có object, dùng `anno label bbox empty IMAGE`; công cụ không cho lệnh này xóa box đã có.

Lưới cấp đầu A1..H8, cấp sau a1..h8. `select` giữ cấp hiện tại; `grid --cells` chia từng ô cha sang cấp tiếp theo. Artifact trả qua `artifact_path`; box dùng hình chữ nhật bao nhỏ nhất của tập ô. Render từ chối các ô nhỏ hơn một pixel, không đủ chỗ cho tên tọa độ hoặc lựa chọn quá nhiều ô; chọn vùng hẹp hơn hoặc cấp thô hơn.

Nếu `label next` trả `task: fix_issues`, đọc `issues`, xem overview/inspect rồi sửa đầy đủ issue. Sau mutation ảnh chuyển modified và chờ review; không hiểu `label next` hết việc là dataset đã được duyệt.

## 3. Audit và duyệt

Sau khi ảnh đã có file label (kể cả file rỗng cho ảnh âm tính):

```bash
anno review audit
anno review next
anno review overview dataset/images/001.jpg
anno review inspect dataset/images/001.jpg --index 0 --margin 0.20
```

Audit báo rõ ảnh/label lỗi hoặc label thiếu, không sửa nhãn. Nếu có input lỗi, sửa nguồn dữ liệu/hoàn thành nhãn trước rồi chạy lại; lần audit lỗi không thay đổi manifest. Ngưỡng nằm trong `.anno/config/config.json`; có thể override cho một lần bằng các option trong `anno review audit --help`.

Agent kiểm tra overview và từng box, ghi findings:

```bash
anno review mark dataset/images/001.jpg --issue tightness_error --box-index 0 --message 'Mép dưới cắt vào bánh xe'
```

Năm mã thị giác: `missing_object`, `class_mismatch`, `tightness_error`, `occlusion_violation`, `ghost_object`. Findings cùng loại được giữ lại; sau delete cần xem index mới.

Sau khi sửa, audit lại và kiểm tra thị giác xong:

```bash
anno review audit
anno review mark dataset/images/001.jpg --verdict approved --notes 'Đã kiểm tra toàn cảnh và từng box'
```

Chỉ mark approved mới duyệt. Render không duyệt; audit sạch cũng không tự duyệt. Thay đổi ảnh/nhãn/classes/config sau audit khiến approval bị từ chối cho đến khi audit lại. Queue ưu tiên flagged, modified, unreviewed và không claim ảnh; cần phân công rõ khi nhiều Agent cùng làm.

## 4. Theo dõi và vận hành

Để đọc trực tiếp trên terminal, dùng `--format text` ở bất kỳ cấp lệnh nào:

```bash
anno init --format text
anno doctor --format text
anno label status --format text
anno review status --format text
anno review next --format text
```

Kết quả text hiển thị từng trường, đường dẫn artifact và gợi ý bước tiếp theo khi phù hợp. Lỗi được ghi vào stderr, giữ mã lỗi và toàn bộ chi tiết; exit code vẫn là 1. `review status` phân biệt tiến độ hoạt động review với số ảnh `approved`: flagged/modified cũng được tính vào reviewed.

Mặc định là JSON; Agent/script có thể ghi rõ `--format json`. Khi lặp `--format`, giá trị cuối cùng được dùng. Giá trị format không hợp lệ trả lỗi JSON. `capabilities` và `schema` trong chế độ text vẫn hiển thị JSON có thụt dòng để dễ đọc. Dùng `anno --help`, `anno review --help` hoặc `anno label bbox add --help` để xem mô tả và ví dụ theo từng cấp.

```bash
anno label status
anno review status
anno capabilities
anno schema review_next.v1.json
```

Giữ ảnh/nhãn/config/skills/manifest trong backup cùng nhau. Không sửa trực tiếp label hoặc manifest bằng Agent. Có thể xóa artifact `.anno/tmp/` khi không render.

Nếu công cụ báo `RECOVERY_REQUIRED` sau lần ghi bị ngắt:

```bash
anno repair
anno doctor
```

Repair hoàn tất lại giao dịch đã ghi journal; không xóa `.anno/transaction.json` bằng tay. Sau nâng cấp, `anno init` chỉ bổ sung file thiếu; những file có sẵn cần backup và di trú tường minh nếu khác contract mới.

Xem [kết quả kiểm chứng và giới hạn](../plan.md). Chưa chứng nhận Windows, network filesystem, tải dataset lớn hoặc chất lượng nhãn thị giác thực tế.
