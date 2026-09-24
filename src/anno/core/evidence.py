"""Evidence-gated coordinate depth management."""

import hashlib
import json
from pathlib import Path

from .coords import name, selected_cells
from .errors import AnnoError
from .project import atomic_json, confined, timestamp


def parse_cell_parents(expression: str) -> tuple[int, list[str]]:
    """Parse a cell expression and return (max_depth, required_parent_cells).

    - Level 1 cells (e.g. A1, B2) have depth 1 and require no parents ([]).
    - Level 2 cells (e.g. B3-a2) have depth 2 and require parent ["B3"].
    - Level 3 cells (e.g. B3-a2-a1) have depth 3 and require parents ["B3", "B3-a2"].
    """
    if not isinstance(expression, str) or not expression.strip():
        raise AnnoError("--cells cannot be empty")
    max_depth = 1
    required_parents = set()
    for item in expression.split(","):
        for end in item.strip().split(":"):
            cell = end.strip()
            if not cell:
                continue
            parts = cell.split("-")
            depth = len(parts)
            max_depth = max(max_depth, depth)
            for k in range(1, depth):
                required_parents.add("-".join(parts[:k]))
    return max_depth, sorted(required_parents, key=lambda s: (len(s.split("-")), s))


def evidence_file(root: Path, key: str) -> Path:
    return confined(root / ".anno/tmp" / key / "evidence.json", root)


def load_evidence_context(root: Path, req) -> dict:
    """Load valid evidence context for the given image request.

    Invalidates if the image content, classes, or config file has changed,
    or if the artifact files no longer exist on disk.
    """
    path = evidence_file(root, req.key)
    if not path.is_file():
        return {"opened_parents": {}, "records": []}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"opened_parents": {}, "records": []}

    stored_fp = data.get("fingerprint", {})
    from .validator import fingerprint

    current_image_fp = fingerprint(req.image)
    if stored_fp.get("image") != current_image_fp:
        return {"opened_parents": {}, "records": []}

    config_path = req.image.parents[len(Path(req.key).parts) + 1] / ".anno/config/config.json"
    if stored_fp.get("config") != fingerprint(config_path):
        return {"opened_parents": {}, "records": []}

    classes_hash = hashlib.sha256(json.dumps(req.classes, sort_keys=True).encode()).hexdigest()
    if stored_fp.get("classes") != classes_hash:
        return {"opened_parents": {}, "records": []}

    # Verify that artifacts on disk still exist
    valid_parents = {}
    for parent, info in data.get("opened_parents", {}).items():
        art = root / info.get("artifact_path", "")
        if art.is_file():
            valid_parents[parent] = info

    data["opened_parents"] = valid_parents
    return data


def save_evidence_context(root: Path, req, command: str, expression: str | None, artifact_path: str) -> dict:
    """Record that an artifact has been created and opened, granting evidence for subcells."""
    path = evidence_file(root, req.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_evidence_context(root, req)
    from .validator import fingerprint

    config_path = req.image.parents[len(Path(req.key).parts) + 1] / ".anno/config/config.json"
    data["image_path"] = "dataset/images/" + req.key
    data["fingerprint"] = {
        "image": fingerprint(req.image),
        "config": fingerprint(config_path),
        "classes": hashlib.sha256(json.dumps(req.classes, sort_keys=True).encode()).hexdigest(),
    }
    opened = data.setdefault("opened_parents", {})

    evidence_id = hashlib.sha256(f"{req.key}:{command}:{expression}:{timestamp()}".encode()).hexdigest()

    parent_cells = []
    if command == "grid":
        if expression is None:
            coordinate_level = 1
            opened[""] = {
                "level": 1,
                "command": command,
                "artifact_path": artifact_path,
                "evidence_id": evidence_id,
                "timestamp": timestamp(),
            }
        else:
            parents = selected_cells(expression, limit=64)
            coordinate_level = max(d + 1 for x, y, d in parents)
            for x, y, d in parents:
                p_name = name(x, y, d)
                parent_cells.append(p_name)
                opened[p_name] = {
                    "level": d + 1,
                    "command": command,
                    "artifact_path": artifact_path,
                    "evidence_id": evidence_id,
                    "timestamp": timestamp(),
                }
    elif command == "select":
        cells = selected_cells(expression)
        coordinate_level = max(d for x, y, d in cells)
        for x, y, d in cells:
            c_name = name(x, y, d)
            parent_cells.append(c_name)
            opened[c_name] = {
                "level": d,
                "command": command,
                "artifact_path": artifact_path,
                "evidence_id": evidence_id,
                "timestamp": timestamp(),
            }
    else:
        coordinate_level = 1

    data.setdefault("records", []).append(
        {
            "evidence_id": evidence_id,
            "command": command,
            "expression": expression,
            "coordinate_level": coordinate_level,
            "parent_cells": parent_cells,
            "artifact_path": artifact_path,
            "timestamp": timestamp(),
        }
    )

    atomic_json(path, data)
    return {
        "evidence_id": evidence_id,
        "coordinate_level": coordinate_level,
        "parent_cells": parent_cells,
    }


def check_coordinate_evidence(root: Path, req, expression: str) -> tuple[int, list[str], str]:
    """Validate that the expression's coordinate depth is backed by artifact evidence.

    Returns (coordinate_level, parent_cells, evidence_id).
    Raises AnnoError if evidence is missing.
    """
    max_depth, required_parents = parse_cell_parents(expression)
    if max_depth <= 1 or not required_parents:
        return 1, [], "level_1_root"

    data = load_evidence_context(root, req)
    opened = data.get("opened_parents", {})

    missing = [p for p in required_parents if p not in opened]
    if missing:
        raise AnnoError(
            f"Coordinate '{expression}' at level {max_depth} requires artifact evidence for parent '{missing[0]}'",
            "INVALID_ARGUMENT",
            {
                "reason": "COORDINATE_EVIDENCE_REQUIRED",
                "coordinate_level": max_depth,
                "required_parents": required_parents,
                "missing_parents": missing,
                "image_path": "dataset/images/" + req.key,
            },
        )

    evidence_id = opened[required_parents[-1]].get("evidence_id", "evidence_verified")
    return max_depth, required_parents, evidence_id
