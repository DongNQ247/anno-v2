# Hợp đồng triển khai Anno 2.0

**Ngày:** 22/09/2026  
**Trạng thái:** Bổ sung chuẩn tắc cho đặc tả mục tiêu  
**Liên quan:** [dev-read.md](dev-read.md), [user-read.md](user-read.md), `TOOL_CONTRACT.md`

Tài liệu này bổ sung các quyết định và tiêu chí nghiệm thu còn thiếu trong hai hướng dẫn trên. `dev-read.md` và `user-read.md` mô tả **hành vi mục tiêu của Anno 2.0**. Repo A4OD hiện tại là nền mã nguồn cần được chuyển đổi; khi khác nhau, không dùng hành vi A4OD cũ để thay thế yêu cầu của Anno 2.0. Trong quá trình triển khai, cập nhật CLI, contract, schema và hướng dẫn cùng một nhịp để không công bố tính năng chưa có.

## 1. Phạm vi và tương thích

1. Sản phẩm đích là package `anno`, CLI `anno`, source tree `src/anno/`, dữ liệu ảnh ở `dataset/images/`, nhãn ở `dataset/labels/`, trạng thái nội bộ ở `.anno/`, cấu hình project ở `.anno/config/config.json` và artifact tạm ở `.anno/tmp/`.
2. Chuyển mã A4OD sang kiến trúc đích theo roadmap trong `dev-read.md`; không duy trì hai bộ implementation song song. Trong thời gian chuyển đổi có thể giữ `a4od` làm shim tương thích, nhưng shim phải gọi cùng CLI engine và có ma trận lệnh tương thích được ghi trong README/contract.
3. Mọi lệnh, option, JSON output, mã lỗi và đường dẫn mặc định phải được công bố trong contract máy đọc được và schema trước khi phát hành package.
4. Giữ nguyên nguyên tắc không cho Agent sửa trực tiếp file nhãn. Mọi mutation phải qua validator tập trung; yêu cầu verification-id là quyết định của Anno 2.0 contract và phải được áp dụng nhất quán cho bbox add/update.

## 2. Mô hình trạng thái review

Mỗi ảnh có đúng một trạng thái: `unreviewed`, `flagged`, `modified`, hoặc `approved`. Record được lưu trong `.anno/manifest.json`, dùng khóa là đường dẫn ảnh tương đối với image root đã cấu hình. Manifest lưu trạng thái, issue đang mở và dấu thời gian; các ngưỡng audit nằm riêng trong `.anno/config/config.json`.

| Trạng thái hiện tại | Sự kiện | Trạng thái kế tiếp | Quy tắc |
| --- | --- | --- | --- |
| Chưa có record | Ảnh xuất hiện trong image root | `unreviewed` | Khởi tạo trong bộ nhớ khi audit/status/queue gặp ảnh; chỉ lệnh ghi trạng thái mới lưu record. |
| Bất kỳ trạng thái nào | Audit phát hiện issue hình học | `flagged` | Lưu issue hiện hành; audit sạch không tự xóa issue thị giác. |
| `unreviewed` | Bắt đầu review | `unreviewed` | Chọn ảnh vào queue không đồng nghĩa đã duyệt. |
| `unreviewed` hoặc `modified` | Agent ghi nhận issue | `flagged` | Gộp issue vào record; không xóa issue khác còn mở. |
| `flagged` | Có bbox add/update/delete thành công | `modified` | Giữ issue làm lịch sử chờ tái kiểm; không xem là đã khắc phục. |
| `modified` | Audit sạch; Agent hoàn tất kiểm tra thị giác và xác nhận các issue cũ đã được xử lý | `approved` | Chỉ `review mark approved` mới xác nhận duyệt và đóng issue đang mở. |
| `approved` | Audit mới phát hiện issue hoặc Agent ghi nhận issue | `flagged` | Duyệt cũ mất hiệu lực khi nhãn/đánh giá thay đổi. |
| `approved` | Bbox bị sửa | `modified` | Yêu cầu kiểm duyệt lại. |

`approved` **không** được đặt bởi lệnh render (`review sheet`, `label-overlay` hay overview tương đương). Lệnh render chỉ tạo artifact. Việc duyệt phải là thao tác tường minh, sau khi Agent hoàn thành các bước kiểm tra. `review mark approved` là thao tác đóng toàn bộ issue đang mở của ảnh; chỉ được gọi sau khi audit sạch và Agent đã xác minh bằng hình ảnh rằng các issue cũ đã được khắc phục. Lệnh lưu verdict/notes và dấu thời gian để truy vết. Nếu audit còn issue hình học thì từ chối duyệt và giữ `flagged`.

### Hàng đợi

- `review next` chọn `flagged` trước, sau đó `modified`, rồi `unreviewed`; trong cùng nhóm chọn theo thứ tự đường dẫn tương đối ổn định.
- `review next` chỉ đọc trạng thái và trả về một ảnh; không tự đổi trạng thái, không claim/lock ảnh.
- Đầu ra khi còn việc: `{"ok":true,"status":"success","image_path":"...","review_status":"flagged","done":false}`. Khi hết việc: `{"ok":true,"status":"success","image_path":null,"done":true}`.
- `label next` ưu tiên ảnh `flagged`, sau đó ảnh chưa có file nhãn; không chọn `modified` như ảnh mới. Ảnh `modified` phải quay lại `review next`. File nhãn rỗng là nhãn hợp lệ biểu thị ảnh không có object, không phải ảnh chưa xử lý.

## 3. Audit hình học

Audit chỉ phát hiện và ghi cảnh báo; **không sửa hoặc clamp nhãn tự động**. Đây là kiểm tra rủi ro, không phải phán quyết rằng box sai. Các ngưỡng mặc định được lưu trong `.anno/config/config.json`, schema tại `schemas/audit_config.v1.json`, và giá trị hiệu lực phải xuất hiện trong JSON kết quả. Ưu tiên áp dụng: default ứng dụng < project config < option CLI cho lần chạy hiện tại.

| Mã issue | Quy tắc mặc định | Ghi chú |
| --- | --- | --- |
| `high_iou` | IoU `>= 0.80` giữa hai box cùng ảnh | Báo cặp index và IoU. Cảnh báo bất kể class; không tự xóa. |
| `tiny_box` | Chiều rộng hoặc chiều cao pixel `< 5` | Kích thước tính trên tọa độ pixel sau khi đọc YOLO. |
| `contained_box` | Box nhỏ có ít nhất 99.9% diện tích nằm trong box lớn | Cảnh báo để người review xác minh quan hệ cha-con; không khẳng định là lỗi. |
| `extreme_aspect_ratio` | `max(w/h, h/w) > 20` | Áp dụng cho box có kích thước dương. |
| `out_of_bounds` | Tọa độ suy ra nằm ngoài ảnh hoặc giá trị YOLO chuẩn hóa ngoài `[0,1]` | Giữ nguyên dữ liệu gốc và báo tọa độ/index; không clamp. |

Audit phải chỉ rõ ảnh không đọc được, label sai định dạng, class id không hợp lệ và ảnh thiếu label theo chính sách hiện hành của repo. Không được âm thầm bỏ qua các lỗi đó. Khi chạy lại, audit thay thế tập **issue hình học do audit quản lý** bằng kết quả mới; issue thị giác (`missing_object`, `class_mismatch`, `tightness_error`, `occlusion_violation`, `ghost_object`) được giữ nguyên tới khi được đóng tường minh. Nếu không còn issue mở nhưng ảnh trước đó `flagged`/`modified`, trạng thái chuyển về `modified`, không tự duyệt.

## 4. Lệnh review

Các lệnh mục tiêu là `anno review audit`, `next`, `status`, `overview`, `inspect`, và `mark`. Dùng các quy ước sau cho mọi lệnh:

- Ảnh nhận vào phải nằm trong `dataset/images/`; nhãn tương ứng nằm trong `dataset/labels/`.
- Artifact ghi vào `.anno/tmp/<relative-image-filename>/` (giữ extension, xem bổ sung bên dưới) với tên cụ thể theo loại artifact. Không dùng một đường dẫn chung `overview.png`/`inspect.png` vì nhiều ảnh sẽ ghi đè nhau.
- Đầu ra thành công giữ `ok: true`, `status: "success"`; lỗi theo `schemas/error.v1.json`, exit code khác 0. Không trả lỗi dạng tự do riêng cho từng lệnh.
- `review inspect` nhận `--index` 0-based, từ chối index ngoài phạm vi và trả box index cùng crop path. Margin là số thực không âm, mặc định `0.20` mỗi phía so với kích thước box; crop được giới hạn ở biên ảnh.
- `review sheet` là công cụ quan sát; lệnh không đổi trạng thái review.
- `review mark --issue` thêm issue đang mở và đặt `flagged`; `review mark --verdict approved` đóng issue sau khi audit sạch và Agent hoàn tất kiểm tra. Lệnh render không tự duyệt.

## 5. Khởi tạo, doctor và infer

- `init` tạo cấu trúc Anno 2.0, bao gồm `dataset/images/`, `dataset/labels/`, `.anno/config/config.json`, manifest, artifact directory và skills. `--force` không được ghi đè dữ liệu hoặc hướng dẫn người dùng; chỉ tạo file thiếu, còn xung đột phải báo và hướng dẫn backup/di trú.
- `doctor` xác thực project config, `data.yaml`, guidelines, skills và image root. Model là tùy chọn; thiếu model không làm project labeling không sẵn sàng. Config audit sai schema là lỗi, không fallback im lặng.
- `infer` chỉ được bật khi runtime/backend, mapping class, quy tắc không ghi đè nhãn đã có, confidence, dependency và kiểm thử được đặc tả. Không công bố mức tiết kiệm token cụ thể nếu chưa đo.

## 6. Tiêu chí nghiệm thu

Một tính năng review chỉ được xem là triển khai xong khi:

1. Lệnh và option xuất hiện nhất quán trong `--help`, `TOOL_CONTRACT.md`, `.a4od/contract.yaml`, `capabilities` và schema versioned.
2. Có kiểm thử tự động cho ngưỡng biên, ảnh/label lỗi, đường dẫn ngoài root, trạng thái/queue, ghi cache, và việc chạy lặp lại không làm mất issue ngoài phạm vi audit.
3. Lệnh render không sửa label/cache; lệnh mark không sửa label; bbox mutation tiếp tục đi qua validator và `verify` hiện hành.
4. Queue kết thúc đúng khi hết việc, không bỏ qua `flagged`/`modified`, và thứ tự chọn ảnh ổn định.
5. User Guide chỉ mô tả luồng đã chạy được bằng CLI trong repo. Build/package install, nếu thay đổi packaging, có kiểm tra cài đặt và gọi entrypoint sau cài đặt.
6. Báo cáo kết quả phân biệt rõ kiểm thử code/CLI với đánh giá chất lượng nhãn thực tế; không tuyên bố độ chính xác hoặc mức tiết kiệm nếu chưa đo.

## 7. Trình tự triển khai đề xuất

Trạng thái thực hiện hiện tại được theo dõi tại [docs/plan.md](../plan.md); không coi các lệnh chưa được liệt kê trong phạm vi đã làm là tính năng phát hành.

1. Chốt schema config, manifest, error và command outputs cho Anno 2.0.
2. Tạo package `src/anno/` và console entrypoint `anno`; xác định shim tương thích A4OD và ma trận hành vi.
3. Chuyển core labeling, validator tập trung, renderers, review engine, init/doctor và Skills theo `dev-read.md`.
4. Đồng bộ CLI help, machine-readable capabilities, schemas, contract và user guide.
5. Thêm kiểm thử hồi quy và nghiệm thu theo mục 6 trước khi phát hành.

## 8. Bổ sung vận hành đã chốt ngày 23/09/2026

Bổ sung UI/UX CLI: mặc định và `--format json` giữ nguyên JSON/schema/exit code hiện hành. Mọi lệnh hỗ trợ `--format text` ở các cấp parser để hiển thị kết quả dễ đọc; lỗi text ra stderr với đủ mã và chi tiết, exit code 1. Giá trị format sai trả lỗi JSON. Option lặp dùng giá trị cuối; `schema`/`capabilities` ở chế độ text là JSON thụt dòng. Đây là ngoại lệ hiển thị tường minh cho quy tắc JSON bên dưới; không thay đổi validator, mutation hay ý nghĩa trạng thái.

- `anno-contract.yaml` và contract đóng gói được sinh từ parser; `anno capabilities` trả cùng inventory và toàn bộ option. Schema từng response nằm trong `schemas/`, package và project sau init; `anno schema NAME` đọc schema của phiên bản đang chạy. `--help`/`--version` là ngoại lệ văn bản; lỗi đối số cũng phải là JSON.
- Artifact giữ toàn bộ relative filename, ví dụ `.anno/tmp/camera/001.jpg/inspect_0.png`; mục đích là tránh va chạm giữa stem, extension và thư mục. `review sheet IMAGE` là alias overview quan sát có index.
- Missing label là lỗi input audit; file rỗng là negative hợp lệ. `label bbox empty IMAGE` tạo negative tường minh và từ chối nhãn có box. Audit gom lỗi input và không commit bất kỳ manifest nào nếu có lỗi; không tự tạo dữ liệu thay thế.
- Issue cùng loại chứa danh sách `findings`; thêm finding không xóa finding trước, exact duplicate được gộp. Index trong finding là index khi quan sát; sau khi xóa box phải lấy lại index hiện tại.
- Verification ràng buộc cả nội dung nhãn/config/classes, ngoài ảnh/class/box; cần verify lại sau mutation. Audit lưu fingerprint và cấu hình hiệu lực; approval từ chối fingerprint đã thay đổi, lưu history của issue được đóng. Agent vẫn chịu trách nhiệm xác minh thị giác.
- Guard tập trung chặn đường dẫn ngoài root, symlink và ảnh dùng chung label path. Hệ tọa độ bbox dùng phân số; render từ chối ô subpixel hoặc không đủ chỗ cho tên tọa độ, giới hạn 4096 ô hoặc 64 ô cha khi chia lưới. Đây là giới hạn render, không giới hạn độ sâu parser.
- Linux/POSIX: khóa project bảo vệ cập nhật của các tiến trình CLI; queue không claim ảnh. Giao dịch nhãn/manifest có journal; khi bị ngắt, mọi thao tác project từ chối cho đến khi `anno repair` hoàn tất replay. Không chứng nhận network filesystem hoặc tác nhân ghi trực tiếp ngoài CLI.
- `doctor` thất bại theo error envelope, readiness ở `error.details`. Chưa compile anno-class là warning để alignment có thể chạy trước labeling. Thiếu các skill bắt buộc là lỗi.
- Không phát hành infer hay shim a4od khi chưa có contract/backend/test đầy đủ.
