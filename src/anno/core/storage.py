"""POSIX project locking and replayable label/manifest transactions."""

import fcntl
from contextlib import contextmanager

from .errors import AnnoError
from .project import atomic_json, atomic_text, confined, strict_json, validate_schema


@contextmanager
def project_lock(root, write=False):
    lock = confined(root / ".anno/project.lock", root)
    if not lock.exists():
        raise AnnoError("Missing project lock; run anno init to complete setup", "INVALID_PROJECT")
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        try:
            pending = confined(root / ".anno/transaction.json", root)
            if pending.exists():
                raise AnnoError(
                    "Interrupted transaction; run anno repair to recover before continuing",
                    "RECOVERY_REQUIRED",
                )
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def apply_transaction(root, transaction):
    validate_schema(transaction["manifest"], "manifest.v1.json")
    label = confined(root / transaction["label_path"], root)
    try:
        label.relative_to(root / "dataset/labels")
    except ValueError:
        raise AnnoError("Invalid transaction label path", "RECOVERY_REQUIRED")
    if label.suffix != ".txt" or not isinstance(transaction["label_content"], str):
        raise AnnoError("Invalid transaction label content", "RECOVERY_REQUIRED")
    atomic_text(label, transaction["label_content"])
    atomic_json(confined(root / ".anno/manifest.json", root), transaction["manifest"])


def commit_labels(root, label, content, manifest):
    pending = confined(root / ".anno/transaction.json", root)
    transaction = {
        "label_path": label.relative_to(root).as_posix(),
        "label_content": content,
        "manifest": manifest,
    }
    validate_schema(manifest, "manifest.v1.json")
    atomic_json(pending, transaction)
    apply_transaction(root, transaction)
    pending.unlink()


def repair(root):
    lock = confined(root / ".anno/project.lock", root)
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        pending = confined(root / ".anno/transaction.json", root)
        if not pending.exists():
            return {"recovered": False}
        transaction = strict_json(pending)
        if not isinstance(transaction, dict) or set(transaction) != {
            "label_path",
            "label_content",
            "manifest",
        }:
            raise AnnoError("Invalid recovery journal; restore from backup", "RECOVERY_REQUIRED")
        apply_transaction(root, transaction)
        pending.unlink()
        return {"recovered": True}
