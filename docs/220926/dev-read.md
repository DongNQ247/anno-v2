# Đặc tả kỹ thuật Anno 2.0

Cập nhật 23/09/2026. Tài liệu này được đồng bộ với [hợp đồng chuẩn tắc](implementation-contract.md), [contract CLI](../../TOOL_CONTRACT.md) và [trạng thái kiểm chứng](../plan.md). Khi cần tên field/option chính xác, dùng `anno capabilities` và `anno schema <name>`; ví dụ JSON cũ đã được thay bằng schema của từng lệnh.

## 1. Phạm vi và kiến trúc

Package `anno`, source `src/anno/`, entrypoint `anno`, Python >= 3.10 trên POSIX. Linux là nền tảng kiểm thử hiện tại.

- `cli.py`: parser, dispatcher và điều phối nghiệp vụ.
- `init.py`: tạo scaffold không ghi đè.
- `core/validator.py`: request guard và `validate_project_readiness()`.
- `core/config.py`: đọc class mapping; ID liên tục từ 0, tên không rỗng/không trùng.
- `core/project.py`: đường dẫn, schema config/manifest và ghi file atomic.
- `core/storage.py`: project lock, journal giao dịch nhãn/manifest, recovery.
- `core/coords.py`: toán tọa độ phân cấp bằng phân số chính xác.
- `core/yolo_io.py`: đọc YOLO nghiêm ngặt và serialization giữ độ chính xác.
- `renderers/`: render lưới, crop và overlay, không sửa trạng thái.
- `review/reviewer.py`: audit hình học và gộp issue thị giác.
- `skills/`, `templates/`: skills, config và toàn bộ schema/contract được đóng gói.

`infer` là tính năng đích chưa bật: cần chốt runtime, weights, mapping class, confidence, dependency, chính sách không ghi đè và kiểm thử trước khi triển khai. Không có shim `a4od` chạy song song.

## 2. Đường dẫn và tính toàn vẹn

Project chạy từ root; ảnh ở `dataset/images/`, label YOLO tương ứng ở `dataset/labels/`, class ở `dataset/data.yaml`, hướng dẫn ở `label.md`. Manifest `.anno/manifest.json` dùng key tương đối với image root, ví dụ `camera/001.jpg`. Ngưỡng nằm ở `.anno/config/config.json`.

Không cho phép symlink trong đường dẫn do công cụ quản lý hoặc hai ảnh có chung đường dẫn label sau khi đổi extension. Artifact ở `.anno/tmp/<relative-image-filename>/`, ví dụ `.anno/tmp/camera/001.jpg/review_overview.png`; giữ extension để tránh xung đột tên. Có thể xóa artifact khi không có lệnh render đang chạy.

Agent không tự đọc/sửa manifest hoặc sửa nhãn: lấy issue qua queue, nhãn qua bbox list, cập nhật qua CLI. Developer/test được đọc trạng thái để kiểm chứng implementation.

## 3. Tọa độ phân cấp và render

Mỗi cấp là lưới 8×8. Cấp đầu `A1..H8`; cấp sau `a1..h8`. Parser hỗ trợ ô đơn, range cùng độ sâu, danh sách và tổ hợp:

```text
A1
A1-a1-a1
A1:B2
A1-a2:C3-c4
A1-h8:B2-a1
A1-a1:A1-a4, B2-c4
```

Range so sánh vị trí toàn cục, không so sánh riêng ký tự từng cấp. Box là hình chữ nhật bao nhỏ nhất, làm tròn x1/y1 xuống và x2/y2 lên theo pixel. Toán bbox không giới hạn cố định số cấp. Render từ chối ô nhỏ hơn một pixel nguồn hoặc không đủ chỗ cho tên tọa độ; giới hạn 4096 ô mỗi lần, hoặc 64 ô cha khi chia tiếp, để tránh tạo artifact không đọc được hoặc mở rộng tổ hợp quá lớn.

| Lệnh | Hành vi |
| --- | --- |
| `label grid IMAGE` | Toàn cảnh tối đa 1024px, lưới cấp 1 có tên ô. |
| `label grid IMAGE --cells CELLS` | Crop native và chia 8×8 trong từng ô cha được chọn; tên ô khớp parser. |
| `label select IMAGE --cells CELLS [--margin .20]` | Crop native, giữ đường biên và tên các ô được chọn ở cấp hiện tại, không chia cấp mới. |
| `label visual IMAGE --cells CELLS [--margin .20]` | Crop native có margin, chỉ vẽ candidate bbox trên ảnh sạch. |
| `label overview IMAGE [--max-size 1024]` | Box, index, tên class và thống kê class. Thiếu label được trả tường minh bằng `label_missing`. |
| `review overview IMAGE [--max-size 1024]` | Overlay như trên, không sửa manifest. |
| `review sheet IMAGE [--max-size 1024]` | Alias quan sát toàn cảnh có index; không duyệt. |
| `review inspect IMAGE --index N [--margin .20]` | Crop native quanh một box, có viền box; trả index và crop bounds. |

Margin phải hữu hạn, không âm, mở rộng từng phía theo kích thước box và giới hạn ở biên ảnh. Index 0-based; index sai bị từ chối trước khi render/mutation.

## 4. Ghi nhãn và verification

```bash
anno label verify dataset/images/001.jpg --class 0 --cells A1:B2
anno label bbox add dataset/images/001.jpg --class 0 --cells A1:B2 --verification-id TOKEN
anno label bbox update dataset/images/001.jpg --index 0 --class 1 --cells A1:B2 --verification-id TOKEN
anno label bbox delete dataset/images/001.jpg --index 0
anno label bbox list dataset/images/001.jpg
anno label bbox empty dataset/images/negative.jpg
```

`TOKEN` phải lấy từ verify cho đúng class/cells và nội dung hiện tại. Token được ràng buộc ảnh, label, class mapping, config và pixel box. Sau mỗi mutation cần verify lại. `empty` chỉ dùng sau khi xác nhận không có object; không xóa nhãn đang chứa box.

Bbox mutation kiểm tra manifest trước khi ghi, giữ issue mở để tái kiểm, hủy audit cũ. Ảnh flagged/modified/approved chuyển modified; ảnh mới vẫn unreviewed.

## 5. Audit: 10 tiêu chí, hai tầng

| Issue | Quy tắc |
| --- | --- |
| `high_iou` | IoU >= .80, bất kể class; trả cặp index và IoU. |
| `tiny_box` | Một cạnh pixel < 5. |
| `contained_box` | Giao / diện tích box nhỏ >= .999. |
| `extreme_aspect_ratio` | max(pixel width / height, height / width) > 20. |
| `out_of_bounds` | Tọa độ chuẩn hóa ngoài [0,1] hoặc box vượt ảnh. |
| `missing_object` | Agent phát hiện object bị bỏ sót qua overview. |
| `class_mismatch` | Agent phát hiện class sai. |
| `tightness_error` | Agent kiểm tra viền box qua inspect. |
| `occlusion_violation` | Agent đối chiếu quy tắc che khuất trong label.md. |
| `ghost_object` | Agent xác minh nhãn nhầm nền/bóng/đốm sáng. |

Năm tiêu chí đầu là cảnh báo hình học, không phải khẳng định nhãn sai; audit không clamp, sửa hoặc xóa label. Năm tiêu chí sau cần đánh giá thị giác.

Config mặc định được tạo bởi init; schema `audit_config.v1.json` kiểm tra cấu trúc đầy đủ, khóa lạ, phiên bản, boolean và miền ngưỡng. Config thiếu/sai là lỗi, không fallback. `review audit` nhận override `--iou-threshold`, `--min-size`, `--contained-threshold`, `--max-aspect-ratio`; override không sửa config. Kết quả trả `effective_config`.

Ảnh lỗi, label sai định dạng/class hoặc thiếu label được báo trong `AUDIT_INPUT_ERROR`, gồm danh sách ảnh và nguyên nhân. Audit đó không cập nhật manifest. Nhãn rỗng hợp lệ; label thiếu chưa được coi là ảnh âm tính. Các số YOLO phải hữu hạn, width/height dương; tọa độ vượt biên được giữ để audit.

## 6. Trạng thái và queue

Bốn trạng thái: unreviewed, flagged, modified, approved. Ảnh mới được coi là unreviewed trong bộ nhớ khi đọc queue/status; chỉ lệnh ghi trạng thái mới lưu record. Queue/status không ghi cache.

Audit thay thế issue hình học, giữ nguyên issue thị giác. Có issue mở thì flagged; sạch trên ảnh từng flagged/modified thì modified, không tự duyệt. Thay đổi nội dung so với audit của ảnh approved làm mất hiệu lực duyệt khi audit lại.

`review next`: flagged → modified → unreviewed, rồi thứ tự path ổn định. `label next`: flagged trước, rồi ảnh thiếu label và không ở trạng thái modified. Nhãn rỗng không được chọn như ảnh mới. Queue không claim ảnh; người điều phối nhiều Agent phải tự phân việc. Khi hết việc trả `done: true, image_path: null`.

`review mark --issue TYPE --message TEXT [--box-index N]` tích lũy findings cùng loại, không ghi đè findings khác và không lặp exact duplicate. Index ghi nhận là index tại thời điểm quan sát; sau delete cần xem lại bbox list.

`review mark --verdict approved [--notes TEXT]` yêu cầu audit còn khớp ảnh/label/classes/config, không còn geometry issue, và người gọi đã kiểm tra thị giác. Khi duyệt, issue được chuyển vào history với notes/timestamp. Lệnh không tự đo chất lượng đánh giá của Agent.

## 7. Init, doctor, skills và recovery

`init [--force]` tạo file thiếu, skills, schemas, config, manifest, project lock và thư mục dữ liệu. Không ghi đè file đã tồn tại; trả conflicts và hướng dẫn backup/di trú.

`doctor` kiểm tra config, manifest, data.yaml, label.md, các skills và image root. Thiếu model không phải lỗi. `class_compiled: false` là warning cho bước alignment; phải hoàn thành alignment trước khi gán nhãn. `model_assisted` hiện false vì infer chưa bật. Lỗi readiness nằm trong `error.details`, theo envelope lỗi chung.

Bốn skills: anno-align làm rõ quy tắc với người dùng và biên dịch anno-class; anno-class chứa quy tắc đã chốt; anno-workflow hướng dẫn progressive zoom/verify/mutation; anno-review hướng dẫn audit/kiểm tra thị giác/duyệt. Ảnh examples dùng để trao đổi trực quan; CLI dataset không chấp nhận đường dẫn ngoài image root. Muốn dùng CLI với examples, tạo project mẫu riêng, đưa bản sao examples vào dataset của project đó.

Mutations dùng exclusive project lock; readers dùng shared lock để đọc snapshot. Nhãn và manifest được commit qua journal durable, fsync và atomic replace. Khi tiến trình dừng giữa giao dịch, lệnh sau báo `RECOVERY_REQUIRED`; chạy `anno repair` để replay dưới lock. Không xóa journal hay sửa label trong khi đang recovery. Bảo đảm này áp dụng các tiến trình CLI hợp tác trên filesystem POSIX cục bộ; chưa chứng nhận NFS hoặc sửa file bằng công cụ ngoài.

## 8. Nghiệm thu

Test phải bao phủ ngưỡng biên, malformed files, root containment, state/queue, verify binding, schema, render không sửa cache, ghi đồng thời và replay sau crash. Wheel/sdist phải chứa skills, templates, schema và contract; chạy entrypoint từ package đã cài ngoài checkout. Kết quả cụ thể và giới hạn được ghi ở [plan](../plan.md).
