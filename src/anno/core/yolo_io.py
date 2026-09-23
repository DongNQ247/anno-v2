"""Strict YOLO reader; preserve out-of-bounds coordinates for audit."""

import math

from .errors import AnnoError


def read_labels(path, width, height, class_ids, missing_ok=False):
    if not path.exists():
        if missing_ok:
            return []
        raise AnnoError(
            f"Missing label: {path.name}; use bbox empty for confirmed negative images", "MISSING_LABEL"
        )
    boxes = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        try:
            if len(parts) != 5:
                raise ValueError("expected class_id xc yc width height")
            cid = int(parts[0])
            xc, yc, w, h = map(float, parts[1:])
            if cid not in class_ids:
                raise ValueError(f"unknown class id {cid}")
            if not all(math.isfinite(v) for v in (xc, yc, w, h)) or w <= 0 or h <= 0:
                raise ValueError("coordinates must be finite and dimensions positive")
        except ValueError as error:
            raise AnnoError(f"{path.name}:{line_number}: {error}", "INVALID_LABEL") from error
        derived = [(xc - w / 2) * width, (yc - h / 2) * height, (xc + w / 2) * width, (yc + h / 2) * height]
        if not all(math.isfinite(value) for value in derived):
            raise AnnoError(f"{path.name}:{line_number}: coordinate overflow", "INVALID_LABEL")
        boxes.append(
            {
                "index": len(boxes),
                "class_id": cid,
                "norm": [xc, yc, w, h],
                "xyxy": [
                    (xc - w / 2) * width,
                    (yc - h / 2) * height,
                    (xc + w / 2) * width,
                    (yc + h / 2) * height,
                ],
            }
        )
    return boxes


def serialize_labels(rows):
    # Round-trip precision keeps untouched boxes unchanged numerically.
    return "".join(f"{cid} " + " ".join(format(v, ".17g") for v in values) + "\n" for cid, *values in rows)
