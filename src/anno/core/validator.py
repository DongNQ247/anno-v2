"""Shared request and readiness guards."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import classes
from .coords import cells_bounds
from .errors import AnnoError
from .project import confined, images, label_for, load_config, load_manifest, relative_image
from .yolo_io import read_labels


@dataclass
class ImageRequest:
    image: Path
    key: str
    label: Path
    width: int
    height: int
    classes: dict
    boxes: list
    box: tuple | None = None


def image_size(path):
    try:
        with Image.open(path) as image:
            image.load()
            return image.size
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise AnnoError(f"Unreadable image {path.name}: {error}", "INVALID_IMAGE") from error


def validate_request(root, args, *, check_collision=True):
    raw = Path(args.image_path)
    path = confined(raw if raw.is_absolute() else root / raw, root)
    key = relative_image(path, root)
    if not path.is_file():
        raise AnnoError(f"Image not found: {key}", "INVALID_IMAGE")
    # Catch same-stem image ambiguity before any label mutation.
    for candidate in path.parent.iterdir() if check_collision else ():
        from .project import IMAGE_EXTENSIONS

        if candidate != path and candidate.stem == path.stem and candidate.suffix.lower() in IMAGE_EXTENSIONS:
            raise AnnoError(f"Images share label stem: {path.stem}", "INVALID_PROJECT")
    width, height = image_size(path)
    mapping = classes(root)
    label = label_for(root, path)
    command = getattr(args, "label_command", None) or getattr(args, "review_command", None)
    action = getattr(args, "action", None)
    # Drawing grids/preview must remain usable for repairing malformed labels.
    needs_labels = command in {"bbox", "overview", "inspect", "sheet", "mark"}
    allow_missing = command in {"overview", "mark"} or action in {"add", "empty"}
    boxes = read_labels(label, width, height, set(mapping), allow_missing) if needs_labels else []
    request = ImageRequest(path, key, label, width, height, mapping, boxes)
    if hasattr(args, "margin") and (not math.isfinite(args.margin) or args.margin < 0):
        raise AnnoError("--margin must be finite and nonnegative")
    if hasattr(args, "max_size") and args.max_size < 1:
        raise AnnoError("--max-size must be positive")
    if getattr(args, "cells", None) is not None:
        request.box = cells_bounds(args.cells, width, height)
    if command == "verify" or action in {"add", "update"}:
        if args.class_id not in mapping:
            raise AnnoError(f"Unknown class id {args.class_id}")
        if request.box is None:
            raise AnnoError("--cells is required")
        x1, y1, x2, y2 = request.box
        if not 0 <= x1 < x2 <= width or not 0 <= y1 < y2 <= height:
            raise AnnoError("Box must have positive area within the image")
    index = getattr(args, "index", None)
    if index is None:
        index = getattr(args, "box_index", None)
    if index is not None and not 0 <= index < len(boxes):
        raise AnnoError(f"Box index outside 0..{len(boxes) - 1}")
    if command == "mark" and args.issue and not (args.message and args.message.strip()):
        raise AnnoError("--message must be nonempty with --issue")
    return request


def fingerprint(path):
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dataset_fingerprint(request):
    return {
        "image": fingerprint(request.image),
        "label": fingerprint(request.label),
        "config": fingerprint(
            request.image.parents[len(Path(request.key).parts) + 1] / ".anno/config/config.json"
        ),
        "classes": hashlib.sha256(json.dumps(request.classes, sort_keys=True).encode()).hexdigest(),
    }


def verification_id(request, class_id):
    value = {
        "path": str(request.image),
        "content": dataset_fingerprint(request),
        "class": class_id,
        "box": request.box,
        "size": [request.width, request.height],
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate_project_readiness(root):
    errors = []
    warnings = []
    mapping = {}
    pics = []
    for check in (lambda: load_config(root), lambda: load_manifest(root)):
        try:
            check()
        except (ValueError, OSError) as error:
            errors.append(str(error))
    try:
        mapping = classes(root)
    except (ValueError, OSError) as error:
        errors.append(str(error))
    try:
        guide = confined(root / "label.md", root)
        text = guide.read_text(encoding="utf-8").strip() if guide.is_file() else ""
        if not text or "Describe each class" in text:
            errors.append("label.md is missing, empty or still a template")
        pics = images(root)
        if not pics:
            errors.append("dataset/images contains no supported images")
    except (ValueError, OSError) as error:
        errors.append(str(error))
    compiled = False
    for skill in ("anno-align", "anno-workflow", "anno-review", "anno-class"):
        path = confined(root / ".anno/skills" / skill / "SKILL.md", root)
        text = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        if not text:
            errors.append(f"Missing or empty skill: {skill}")
        if skill == "anno-class":
            compiled = bool(text) and "generated from `label.md`" not in text
            if not compiled:
                warnings.append("anno-class is not compiled; complete anno-align before labeling")
    return {
        "ready": not errors,
        "images_count": len(pics),
        "classes_count": len(mapping),
        "class_compiled": compiled,
        "model_assisted": False,
        "errors": errors,
        "warnings": warnings,
    }
