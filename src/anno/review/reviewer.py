import math

from PIL import Image

from ..core.project import ISSUES
from ..core.yolo_io import read_labels


def audit_one(p, lbl, class_map, cfg, size=None):
    if size is None:
        with Image.open(p) as im:
            im.load()
            size = im.size
    w, h = size
    boxes = read_labels(lbl, w, h, set(class_map))
    a = cfg["review"]["audit"]
    checks = a["checks"]
    issues = {k: None for k in sorted(ISSUES)}

    def add(k, indices, msg, **extra):
        issues[k] = {"box_indices": indices, "message": msg, **extra}

    bxs = [b["xyxy"] for b in boxes]
    if checks["out_of_bounds"]:
        bad = [
            b["index"]
            for b in boxes
            if any(not math.isfinite(x) for x in b["xyxy"])
            or b["xyxy"][0] < 0
            or b["xyxy"][1] < 0
            or b["xyxy"][2] > w
            or b["xyxy"][3] > h
            or any(x < 0 or x > 1 for x in b["norm"])
        ]
        if bad:
            add(
                "out_of_bounds",
                bad,
                "Label coordinates extend beyond the image or normalized range",
                boxes=[
                    {"index": boxes[i]["index"], "xyxy": boxes[i]["xyxy"], "normalized": boxes[i]["norm"]}
                    for i in bad
                ],
            )
    if checks["tiny_box"]:
        bad = [
            b["index"]
            for b in boxes
            if b["norm"][2] * w < a["min_box_edge_px"] or b["norm"][3] * h < a["min_box_edge_px"]
        ]
        if bad:
            add("tiny_box", bad, f"Box edge is below {a['min_box_edge_px']} px")
    if checks["extreme_aspect_ratio"]:
        bad = [
            b["index"]
            for b in boxes
            if min(b["norm"][2:]) > 0
            and max(b["norm"][2] * w, b["norm"][3] * h) / min(b["norm"][2] * w, b["norm"][3] * h)
            > a["max_aspect_ratio"]
        ]
        if bad:
            add("extreme_aspect_ratio", bad, f"Aspect ratio exceeds {a['max_aspect_ratio']}")
    if checks["high_iou"] or checks["contained_box"]:
        ious = []
        contained = []
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                x1, y1, x2, y2 = bxs[i]
                X1, Y1, X2, Y2 = bxs[j]
                inter = max(0, min(x2, X2) - max(x1, X1)) * max(0, min(y2, Y2) - max(y1, Y1))
                ar1 = max(0, x2 - x1) * max(0, y2 - y1)
                ar2 = max(0, X2 - X1) * max(0, Y2 - Y1)
                union = ar1 + ar2 - inter
                iou = inter / union if union else 0
                if iou >= a["iou_threshold"]:
                    ious.append([i, j, round(iou, 4)])
                if min(ar1, ar2) > 0 and inter / min(ar1, ar2) >= a["contained_ratio_threshold"]:
                    contained.append([i, j])
        if checks["high_iou"] and ious:
            add("high_iou", sorted({i for pair in ious for i in pair[:2]}), "High IoU box pairs", pairs=ious)
        if checks["contained_box"] and contained:
            add(
                "contained_box",
                sorted({i for pair in contained for i in pair}),
                "One box is nearly contained in another",
                pairs=contained,
            )
    return issues


def merge_issue(record, kind, message, index=None):
    finding = {"message": message}
    if index is not None:
        finding["box_indices"] = [index]
    previous = record["issues"].get(kind)
    findings = list(previous.get("findings", [previous])) if previous else []
    if finding not in findings:
        findings.append(finding)
    record["issues"][kind] = {
        "message": "\n".join(item["message"] for item in findings),
        "box_indices": sorted({i for item in findings for i in item.get("box_indices", [])}),
        "findings": findings,
    }
    record["status"] = "flagged"
