"""Non-destructive scaffold installation."""

import fcntl
from pathlib import Path

from .core.errors import AnnoError
from .core.project import RESOURCES, atomic_json, atomic_text, confined


def initialize(root):
    created, conflicts = [], []
    directories = [
        "dataset/images",
        "dataset/labels",
        ".anno/tmp",
        "examples/images",
        "examples/labels",
        "models",
        ".anno/skills",
        ".anno/schemas",
    ]
    files = [
        (root / "AGENTS.md", RESOURCES / "AGENTS.md"),
        (root / "label.md", RESOURCES / "label.md"),
        (root / "dataset/data.yaml", RESOURCES / "data.yaml"),
        (root / ".anno/config/config.json", RESOURCES / "config.json"),
        (root / ".anno/skills/anno-class/SKILL.md", RESOURCES / "anno-class.SKILL.md.template"),
    ]
    for path in (Path(__file__).parent / "skills").glob("*/SKILL.md"):
        files.append((root / ".anno/skills" / path.parent.name / path.name, path))
    for path in (RESOURCES / "schemas").glob("*.json"):
        files.append((root / ".anno/schemas" / path.name, path))
    files.append((root / ".anno/contract.json", RESOURCES / "contract.json"))
    for path in (
        [root / d for d in directories]
        + [p for p, s in files]
        + [root / ".anno/manifest.json", root / ".anno/project.lock"]
    ):
        confined(path, root)
    state = root / ".anno"
    state.mkdir(parents=True, exist_ok=True)
    with (state / "project.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (state / "transaction.json").exists():
            raise AnnoError("Pending transaction; run anno repair", "RECOVERY_REQUIRED")
        for relative in directories:
            path = root / relative
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created.append(relative)
            elif not path.is_dir():
                raise AnnoError(f"Expected directory: {relative}", "INVALID_PROJECT")
        for target, source in files:
            if target.exists():
                conflicts.append(target.relative_to(root).as_posix())
            else:
                atomic_text(target, source.read_text(encoding="utf-8"))
                created.append(target.relative_to(root).as_posix())
        if not (state / "manifest.json").exists():
            atomic_json(state / "manifest.json", {})
            created.append(".anno/manifest.json")
    return {
        "created": created,
        "conflicts": conflicts,
        "message": "Existing files are preserved. Back up and migrate listed conflicts explicitly."
        if conflicts
        else "Project scaffold created.",
    }
