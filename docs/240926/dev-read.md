# Đặc tả kỹ thuật Anno 2.0

Cập nhật 24/09/2026. Tài liệu này kế thừa và nêu rõ các thay đổi, bổ sung kỹ thuật so với bản [22/09/2026](../220926/dev-read.md). Mọi cập nhật đã được đồng bộ với [hợp đồng CLI](../../TOOL_CONTRACT.md), [schema JSON](../../schemas/) và bộ kiểm thử hồi quy tại `tests/`.

---

## Tóm tắt các thay đổi lớn so với bản 22/09/2026

| Khu vực | Thay đổi chính | Lợi ích cho Agent & Developer |
| --- | --- | --- |
| **Evidence Gate** | Thêm module `core/evidence.py`, kiểm soát cấp độ tọa độ subcell theo artifact cha thực tế. | Ngăn chặn agent suy đoán (hallucinate) hoặc tự gán tọa độ subcell khi chưa mở lưới cha. |
| **JSON Response** | Bổ sung `cells[].xyxy`, `image_size`, `candidate`, `box`, `label_path`, `reason`, `suggested_recovery`. | Agent không cần tự tính toán pixel từ text, phân biệt rõ trạng thái queue và nhận hướng xử lý lỗi lập tức. |
| **Grid Rendering** | Hỗ trợ nhãn mép (edge labels) khi ô chật và auto-scaling giữ tỷ lệ khung hình (`--scale`). | Tránh vỡ chữ / crash khi crop nhỏ; VLM nhận artifact độ phân giải cao và sắc nét. |
| **Scaffold Init** | `anno init` tự động sinh file `AGENTS.md` tại root project. | Chuẩn hóa điểm vào cho AI coding agents, trỏ đúng các skill và quy ước nhãn. |
| **Contract Gen** | `tools/generate_contract.py` sinh đồng bộ toàn bộ schema và hợp đồng. | Loại bỏ hoàn toàn nguy cơ schema drift trong CI/CD. |

---

## 1. Phạm vi và kiến trúc

Package `anno`, source `src/anno/`, entrypoint `anno`, Python >= 3.10 trên POSIX.

Cấu trúc module hiện tại:
- `cli.py`: parser, dispatcher, error handler mở rộng với `suggested_recovery`.
- `init.py`: tạo scaffold không ghi đè, bổ sung `AGENTS.md` vào danh sách file khởi tạo.
- `core/evidence.py` *(Mới)*: quản lý evidence context, kiểm tra bằng chứng phân cấp tọa độ, sinh và xác thực `evidence_id`.
- `core/validator.py`: request guard, kiểm tra geometry, fingerprint ảnh/config/classes.
- `core/config.py`: đọc class mapping; ID liên tục từ 0, tên không rỗng/không trùng.
- `core/project.py`: đường dẫn, schema config/manifest và ghi file atomic.
- `core/storage.py`: project lock, journal giao dịch nhãn/manifest, recovery.
- `core/coords.py`: toán tọa độ phân cấp 8×8 bằng phân số chính xác.
- `core/yolo_io.py`: đọc YOLO nghiêm ngặt và serialization giữ độ chính xác.
- `renderers/grid.py`: render lưới toàn cảnh, crop cục bộ, scaling 2-mode (full label hoặc edge label).
- `renderers/visualizer.py`: overlay hộp và preview box.
- `review/reviewer.py`: audit hình học và gộp issue thị giác.
- `skills/`, `templates/`: skills (đã bổ sung 6 quy tắc evidence-gate), config và schema được đóng gói.

---

## 2. Đường dẫn, tính toàn vẹn và Evidence Context

- Cấu trúc thư mục dữ liệu giữ nguyên: `dataset/images/`, `dataset/labels/`, `dataset/data.yaml`, `label.md`.
- **Evidence Context** lưu theo từng ảnh tại `.anno/tmp/<relative-image-filename>/evidence.json`.
- **Cơ chế vô hiệu hóa (Invalidation):** Evidence context tự động mất hiệu lực khi:
  - Hash nội dung ảnh thay đổi (`fingerprint(request.image)`).
  - File cấu hình `.anno/config/config.json` hoặc class mapping trong `data.yaml` thay đổi.
  - File artifact `.png` tương ứng bị xóa khỏi đĩa.
- Evidence của ảnh này tuyệt đối không thể sử dụng cho ảnh khác hoặc phiên bản ảnh cũ.

---

## 3. Tọa độ phân cấp, render và Local Scaling

### 3.1. Hai chế độ hiển thị nhãn tọa độ (Edge Label Fallback)
Khi các ô lưới quá hẹp để hiển thị đầy đủ chuỗi nhãn phân cấp (ví dụ `A1-a1` trong ô nhỏ):
1. **Full-fit mode:** Ưu tiên hiển thị đầy đủ nhãn trong từng ô nếu font chữ size 6..12 vừa vặn.
2. **Edge-label mode:** Nếu không vừa, tool tự động chuyển sang hiển thị nhãn cột ở mép trên (top edge), nhãn hàng ở mép trái (left edge), và ô góc kết hợp `col/row`. Không crash với lỗi `Grid cells cannot fit readable coordinate labels` trừ khi ô nhỏ hơn 1 pixel nguồn.

### 3.2. Local Scaling và Tùy chọn `--scale`
Các lệnh `label grid IMAGE --cells CELLS` và `label select IMAGE --cells CELLS` hỗ trợ tham số `--scale {auto,1,2,3,4}` (mặc định: `auto`):
- `auto`: Tự động tính toán hệ số phóng đại nguyên (tối đa 4×) sao cho mỗi ô con đạt tối thiểu 28 px, giữ nguyên tỷ lệ khung hình (aspect ratio).
- Dùng nội suy `Image.Resampling.LANCZOS` để phóng đại crop, sau đó vẽ lưới tọa độ sắc nét lên ảnh phóng đại.
- **Bảo toàn tọa độ số học:** Mọi trường `crop`, `cells[].xyxy`, `image_size` trong JSON response **luôn ở hệ tọa độ pixel gốc**, không bị ảnh hưởng bởi tỷ lệ render.
- **Metadata trả về:** Bổ sung `scale`, `native_crop_size`, `render_size`, `subcell_size`, `readable_labels`, `parent_cell_count`, `subcell_count`.

---

## 4. Evidence-Gated Coordinate Depth & Workflow

### 4.1. Quy tắc cấp bậc bằng chứng
1. **Lưới cấp 1 (`A1`..`H8`):** Được cấp bằng chứng bởi lưới toàn ảnh (`label grid IMAGE`). Tọa độ cấp 1 luôn hợp lệ, không bắt buộc phải mở subgrid.
2. **Lưới cấp 2 (ví dụ `B3-a2`):** Chỉ hợp lệ khi parent `B3` đã được mở bằng artifact `label grid IMAGE --cells B3` hoặc `label select`.
3. **Lưới cấp sâu hơn (ví dụ `B3-a2-a1`):** Yêu cầu toàn bộ chuỗi parent tiền nhiệm (`B3` và `B3-a2`) đều đã có trong evidence context của đúng ảnh.
4. **Cách ly hoàn toàn:** Không được dùng subcell rời rạc không có parent, không tự quy đổi dời gốc về `A1`, và không dùng evidence của ảnh khác.

### 4.2. Điểm kiểm soát (Enforcement Gates)
Evidence gate được thực thi nghiêm ngặt tại:
- `label grid IMAGE --cells CELLS`: Nếu `--cells` có depth > 1, kiểm tra parent của nó đã được mở chưa.
- `label select IMAGE --cells CELLS`: Kiểm tra parent của `--cells`.
- `label verify IMAGE --class C --cells CELLS`: Kiểm tra evidence trước khi cấp verification token.
- `label bbox add` / `label bbox update`: Kiểm tra evidence **trước khi** kiểm tra `verification-id` và trước khi ghi nhãn/manifest.

### 4.3. Xử lý khi vi phạm
- Khi thiếu bằng chứng, lệnh trả về lỗi JSON chuẩn:
  ```json
  {
    "ok": false,
    "status": "error",
    "error": {
      "code": "INVALID_ARGUMENT",
      "message": "Coordinate 'C4-a2' at level 2 requires artifact evidence for parent 'C4'",
      "details": {
        "reason": "COORDINATE_EVIDENCE_REQUIRED",
        "coordinate_level": 2,
        "required_parents": ["C4"],
        "missing_parents": ["C4"],
        "image_path": "dataset/images/001.jpg"
      },
      "suggested_recovery": "Run anno label grid dataset/images/001.jpg --cells C4 to open required parent evidence"
    }
  }
  ```
- **Bảo toàn trạng thái:** Nhãn và manifest không bị thay đổi khi kiểm tra thất bại.

---

## 5. Cải tiến JSON Responses cho Agent

### 5.1. Hình học Lưới (`label grid`, `label select`)
Trả về kích thước ảnh gốc và tọa độ pixel từng ô:
```json
{
  "image_path": "dataset/images/001.jpg",
  "image_size": [1600, 1200],
  "cell_labels": ["B3-a1", "B3-a2"],
  "cells": [
    {"id": "B3-a1", "xyxy": [200, 300, 225, 337]}
  ],
  "coordinate_level": 2,
  "parent_cells": ["B3"],
  "evidence_id": "sha256...",
  "artifact_path": ".anno/tmp/001.jpg/label_grid.png"
}
```

### 5.2. Phản hồi Verify (`label verify`)
Echo lại đối tượng candidate hoàn chỉnh kèm thông tin bằng chứng:
```json
{
  "image_path": "dataset/images/001.jpg",
  "verification_id": "sha256...",
  "box": [200, 300, 400, 600],
  "candidate": {
    "class_id": 0,
    "class_name": "car",
    "cells": "B3-a1:B3-d8",
    "xyxy": [200, 300, 400, 600]
  },
  "coordinate_level": 2,
  "parent_cells": ["B3"],
  "evidence_id": "sha256..."
}
```

### 5.3. Lý do hoàn thành Queue (`label next`, `review next`)
Bổ sung trường `reason` khi `done: true` để tránh hiểu lầm toàn bộ dataset đã hoàn tất đánh giá:
- `label next`: `{"done": true, "reason": "NO_FLAGGED_OR_UNLABELED", "task": null, "issues": null, "image_path": null}`
- `review next`: `{"done": true, "reason": "ALL_REVIEWED", "image_path": null}`

### 5.4. Phản hồi Mutation (`bbox add`, `bbox update`, `bbox delete`, `bbox empty`)
Echo `label_path` và đối tượng `box` vừa được ghi:
```json
{
  "image_path": "dataset/images/001.jpg",
  "label_path": "dataset/labels/001.txt",
  "box_count": 2,
  "written": true,
  "box": {
    "index": 1,
    "class_id": 0,
    "class_name": "car",
    "xyxy": [200.0, 300.0, 400.0, 600.0]
  }
}
```

### 5.5. Hướng dẫn phục hồi lỗi (`suggested_recovery`)
Mọi lỗi `AnnoError` khi trả ra JSON đều đi kèm trường `suggested_recovery` tương ứng với mã lỗi và ngữ cảnh, hỗ trợ agent tự động sửa sai mà không cần đoán message.

---

## 6. Audit và Workflow của Agent

### 6.1. Quy trình chuẩn cho Agent trong `anno-workflow`
```text
grid cấp hiện tại (toàn cảnh hoặc parent đã mở)
-> select vùng biên nếu cần quan sát
-> subgrid parent cụ thể nếu cần độ phân giải cao hơn
-> visual kiểm tra candidate box trên ảnh sạch
-> verify để lấy token và kiểm tra evidence gate
-> bbox add/update với verification token
```

### 6.2. Scaffold `AGENTS.md`
Lệnh `anno init` tự động tạo `AGENTS.md` với nội dung trỏ trực tiếp đến:
- `.anno/skills/anno-class/SKILL.md` (Quy tắc class đã chốt)
- `.anno/skills/anno-align/SKILL.md` (Quy trình alignment)
- `.anno/skills/anno-workflow/SKILL.md` (Workflow gán nhãn & evidence-gating)
- `.anno/skills/anno-review/SKILL.md` (Quy trình audit & review)
- `label.md` (Hướng dẫn quy ước gán nhãn đối tượng)

---

## 7. Nghiệm thu và Độ tương thích

- **Độ tương thích ngược:** 100% tương thích ngược với các project Anno cũ. Lệnh dùng cell cấp 1 không bị ảnh hưởng.
- **Contract Synchronization:** `tools/generate_contract.py` là single source of truth; chạy tự động trong CI để ngăn chặn mọi schema drift giữa repo và package template.
- **Bộ test kiểm chứng:** Hiện có **144 test cases** (tăng từ 115 test ở bản 22/09) bao phủ toàn diện:
  - 10 tiêu chí audit hình học và thị giác.
  - Giao dịch nhãn durable, concurrent locks, crash replay.
  - Edge coordinate labels và local crop scaling với LANCZOS.
  - 5 đề xuất cải tiến JSON output.
  - 7 acceptance tests kiểm tra evidence gate (cấp 1, cấp 2, cấp 3, cách ly ảnh, bảo toàn nhãn khi reject, vô hiệu hóa khi đổi ảnh).
