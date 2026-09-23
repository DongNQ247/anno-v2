"""Project paths, strict state/config loading and durable atomic writes."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import AnnoError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VISION_ISSUES = {"missing_object", "class_mismatch", "tightness_error", "occlusion_violation", "ghost_object"}
GEOMETRY_ISSUES = {"high_iou", "tiny_box", "contained_box", "extreme_aspect_ratio", "out_of_bounds"}
ISSUES = GEOMETRY_ISSUES | VISION_ISSUES
RESOURCES = Path(__file__).resolve().parents[1] / "templates"
DEFAULT_CONFIG = json.loads((RESOURCES / "config.json").read_text())


def confined(path, root):
    """Reject symlinks in managed paths, including symlinked roots."""
    root = root.resolve()
    path = Path(os.path.abspath(path))
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise AnnoError(f"Path must be inside {root}", "PATH_OUTSIDE_ROOT")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise AnnoError(f"Symlinks are not allowed in managed paths: {relative}", "PATH_OUTSIDE_ROOT")
    return path


def atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def project_paths(root):
    root = root.resolve()
    paths = {
        "root": root,
        "images": root / "dataset/images",
        "labels": root / "dataset/labels",
        "manifest": root / ".anno/manifest.json",
        "config": root / ".anno/config/config.json",
        "tmp": root / ".anno/tmp",
    }
    for path in paths.values():
        confined(path, root)
    return paths


def images(root):
    image_root = project_paths(root)["images"]
    if not image_root.is_dir():
        raise AnnoError("Missing dataset/images; run anno init", "INVALID_PROJECT")
    found = []
    labels = set()
    for path in sorted(image_root.rglob("*")):
        confined(path, root)
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            key = path.relative_to(image_root).with_suffix(".txt").as_posix()
            if key in labels:
                raise AnnoError(f"Images share the same label path: {key}", "INVALID_PROJECT")
            labels.add(key)
            found.append(path)
    return found


def relative_image(path, root):
    path = confined(path, root)
    try:
        return path.relative_to(project_paths(root)["images"]).as_posix()
    except ValueError:
        raise AnnoError("image_path must be inside dataset/images", "PATH_OUTSIDE_ROOT")


def label_for(root, image):
    return confined(
        project_paths(root)["labels"] / Path(relative_image(image, root)).with_suffix(".txt"), root
    )


def strict_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AnnoError(f"Duplicate JSON key: {key}", "INVALID_PROJECT")
            result[key] = value
        return result

    def reject(value):
        raise AnnoError(f"Non-finite JSON value: {value}", "INVALID_PROJECT")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            reject(value)
        return number

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=reject,
        parse_float=finite_float,
    )


def validate_schema(data, schema_name):
    schema = json.loads((RESOURCES / "schemas" / schema_name).read_text())
    error = next(Draft202012Validator(schema).iter_errors(data), None)
    if error:
        location = ".".join(map(str, error.absolute_path))
        raise AnnoError(f"{schema_name} at {location or '<root>'}: {error.message}", "INVALID_PROJECT")


def load_manifest(root):
    path = project_paths(root)["manifest"]
    if not path.is_file():
        raise AnnoError("Missing manifest; run anno init", "INVALID_PROJECT")
    data = strict_json(path)
    validate_schema(data, "manifest.v1.json")
    for key in data:
        if Path(key).is_absolute() or ".." in Path(key).parts:
            raise AnnoError("Invalid manifest image key", "INVALID_PROJECT")
    return data


def load_config(root):
    path = project_paths(root)["config"]
    if not path.is_file():
        raise AnnoError("Missing audit config; run anno init", "INVALID_PROJECT")
    config = strict_json(path)
    validate_schema(config, "audit_config.v1.json")
    return config


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def empty_record():
    return {"status": "unreviewed", "issues": {k: None for k in sorted(ISSUES)}, "updated_at": timestamp()}
