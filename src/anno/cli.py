"""Public JSON CLI. Parsing, business logic and renderers share one validator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from . import __version__
from .core.errors import AnnoError
from .core.project import (
    GEOMETRY_ISSUES,
    RESOURCES,
    VISION_ISSUES,
    atomic_json,
    confined,
    empty_record,
    images,
    label_for,
    load_config,
    load_manifest,
    relative_image,
    timestamp,
    validate_schema,
)
from .core.storage import commit_labels, project_lock, repair
from .core.validator import dataset_fingerprint, validate_project_readiness, validate_request, verification_id
from .core.yolo_io import serialize_labels
from .init import initialize
from .presentation import configure_help, render_text
from .renderers.grid import grid, select
from .renderers.visualizer import overview, preview
from .review.reviewer import audit_one, merge_issue


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(*args, **kwargs)
        self.add_argument(
            "--format",
            choices=("json", "text"),
            default=argparse.SUPPRESS,
            help="Output format: json for scripts (default), text for people; accepted at any command level",
        )

    def error(self, message):
        raise AnnoError(message, "INVALID_ARGUMENT")


def build_parser():
    parser = Parser(prog="anno", description="Validated YOLO labeling and explicit review (POSIX).")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create missing project files without overwriting existing files")
    init.add_argument(
        "--force", action="store_true", help="Compatibility option; existing files are still preserved"
    )
    commands.add_parser("doctor", help="Validate project readiness")
    commands.add_parser("repair", help="Replay an interrupted label/state transaction")
    commands.add_parser("capabilities", help="Print versioned command/options/schema contract")
    schema = commands.add_parser("schema", help="Print an installed JSON schema")
    schema.add_argument("name", help="Schema filename, e.g. manifest.v1.json")
    review = commands.add_parser("review").add_subparsers(dest="review_command", required=True)
    audit = review.add_parser("audit")
    audit.add_argument("--iou-threshold", type=float)
    audit.add_argument("--min-size", type=int)
    audit.add_argument("--contained-threshold", type=float)
    audit.add_argument("--max-aspect-ratio", type=float)
    review.add_parser("next")
    review.add_parser("status")
    for name in ("overview", "sheet"):
        sub = review.add_parser(name, help="Render indexed class overlay; does not approve")
        sub.add_argument("image_path")
        sub.add_argument("--max-size", type=int, default=1024)
    inspect = review.add_parser("inspect")
    inspect.add_argument("image_path")
    inspect.add_argument("--index", type=int, required=True)
    inspect.add_argument("--margin", type=float, default=0.20)
    mark = review.add_parser("mark")
    mark.add_argument("image_path")
    group = mark.add_mutually_exclusive_group(required=True)
    group.add_argument("--issue", choices=sorted(VISION_ISSUES))
    group.add_argument("--verdict", choices=["approved"])
    mark.add_argument("--message")
    mark.add_argument("--box-index", type=int)
    mark.add_argument("--notes")
    label = commands.add_parser("label").add_subparsers(dest="label_command", required=True)
    label.add_parser("next")
    label.add_parser("status")
    sub = label.add_parser("grid")
    sub.add_argument("image_path")
    sub.add_argument("--cells")
    sub = label.add_parser("overview")
    sub.add_argument("image_path")
    sub.add_argument("--max-size", type=int, default=1024)
    for name in ("select", "visual"):
        sub = label.add_parser(name)
        sub.add_argument("image_path")
        sub.add_argument("--cells", required=True)
        sub.add_argument("--margin", type=float, default=0.20)
    sub = label.add_parser("verify")
    sub.add_argument("image_path")
    sub.add_argument("--class", dest="class_id", type=int, required=True)
    sub.add_argument("--cells", required=True)
    bbox = label.add_parser("bbox").add_subparsers(dest="action", required=True)
    for action in ("add", "update", "delete", "list", "empty"):
        sub = bbox.add_parser(action)
        sub.add_argument("image_path")
        if action in ("update", "delete"):
            sub.add_argument("--index", type=int, required=True)
        if action in ("add", "update"):
            sub.add_argument("--class", dest="class_id", type=int, required=True)
            sub.add_argument("--cells", required=True)
            sub.add_argument("--verification-id", required=True)
    configure_help(parser)
    return parser


def render(root, args, request):
    name = getattr(args, "review_command", None) or args.label_command
    with Image.open(request.image) as source:
        image = source.convert("RGB")
    extra = {}
    if name in ("overview", "sheet"):
        result, counts = overview(image, request.boxes, request.classes, args.max_size)
        extra = {
            "boxes": len(request.boxes),
            "class_counts": counts,
            "label_missing": not request.label.exists(),
        }
    elif name == "inspect":
        result, crop = preview(image, request.boxes[args.index]["xyxy"], args.margin)
        extra = {"box_index": args.index, "crop": list(crop)}
    elif name == "grid":
        result, extra = grid(image, args.cells)
    elif name == "select":
        result, extra = select(image, args.cells, args.margin)
    elif name == "visual":
        result, crop = preview(image, request.box, args.margin)
        extra = {"crop": list(crop), "xyxy": list(request.box)}
    else:
        raise AnnoError("Unknown renderer")
    filename = f"inspect_{args.index}.png" if name == "inspect" else f"{args.command}_{name}.png"
    # Full relative image filename avoids collisions between dotted stems/folders.
    out = confined(root / ".anno/tmp" / request.key / filename, root)
    out.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile

    fd, temp = tempfile.mkstemp(dir=out.parent, suffix=".png")
    os.close(fd)
    try:
        result.save(temp, format="PNG")
        os.replace(temp, out)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {
        "image_path": "dataset/images/" + request.key,
        "artifact_path": out.relative_to(root).as_posix(),
        **extra,
    }


def audit(root, args):
    config = load_config(root)
    for attr, key in (
        ("iou_threshold", "iou_threshold"),
        ("min_size", "min_box_edge_px"),
        ("contained_threshold", "contained_ratio_threshold"),
        ("max_aspect_ratio", "max_aspect_ratio"),
    ):
        value = getattr(args, attr)
        if value is not None:
            config["review"]["audit"][key] = value
    # jsonschema alone accepts infinity as a number; enforce JSON-finite values.
    try:
        json.dumps(config, allow_nan=False)
    except ValueError:
        raise AnnoError("Audit thresholds must be finite")
    validate_schema(config, "audit_config.v1.json")
    manifest = load_manifest(root)
    failures = []
    scanned = flagged = 0
    for pic in images(root):
        key = relative_image(pic, root)
        try:
            req = validate_request(
                root,
                SimpleNamespace(image_path=str(pic), label_command="verify-audit"),
                check_collision=False,
            )
            before = dataset_fingerprint(req)
            issues = audit_one(pic, req.label, req.classes, config, size=(req.width, req.height))
            if before != dataset_fingerprint(req):
                raise AnnoError("Image or label changed during audit", "CONCURRENT_CHANGE")
            record = manifest.setdefault(key, empty_record())
            for issue in VISION_ISSUES:
                issues[issue] = record["issues"][issue]
            if record["status"] == "approved" and record.get("audit_fingerprint") != before:
                record["status"] = "modified"
            record["issues"] = issues
            if any(value is not None for value in issues.values()):
                record["status"] = "flagged"
            elif record["status"] in ("flagged", "modified"):
                record["status"] = "modified"
            record["audit_at"] = record["updated_at"] = timestamp()
            record["audit_fingerprint"] = before
            record["audit_config"] = config
            scanned += 1
            flagged += record["status"] == "flagged"
        except (ValueError, OSError) as error:
            failures.append(
                {
                    "image_path": "dataset/images/" + key,
                    "code": getattr(error, "code", "INVALID_IMAGE"),
                    "message": str(error),
                }
            )
    if failures:
        raise AnnoError(
            "Audit input errors; no manifest or labels were changed",
            "AUDIT_INPUT_ERROR",
            {"failures": failures},
        )
    atomic_json(root / ".anno/manifest.json", manifest)
    return {
        "effective_config": config["review"]["audit"],
        "scanned_images": scanned,
        "flagged_images": flagged,
    }


def queue_or_status(root, args):
    manifest = load_manifest(root)
    pics = images(root)
    records = [
        (relative_image(pic, root), pic, manifest.get(relative_image(pic, root), empty_record()))
        for pic in pics
    ]
    if args.command == "review":
        if args.review_command == "status":
            counts = {s: 0 for s in ("unreviewed", "flagged", "modified", "approved")}
            for _, _, record in records:
                counts[record["status"]] += 1
            total = len(pics)
            reviewed = total - counts["unreviewed"]
            return {
                "total_images": total,
                "reviewed": reviewed,
                "unreviewed": counts["unreviewed"],
                "progress": f"{100 * reviewed / total:.1f}%" if total else "0.0%",
                "by_status": {k: v for k, v in counts.items() if k != "unreviewed"},
            }
        priority = {"flagged": 0, "modified": 1, "unreviewed": 2}
        todo = sorted((priority[r["status"]], key, r) for key, pic, r in records if r["status"] in priority)
        if not todo:
            return {"image_path": None, "done": True}
        _, key, record = todo[0]
        return {
            "image_path": "dataset/images/" + key,
            "review_status": record["status"],
            "issues": record["issues"],
            "done": False,
        }
    if args.label_command == "status":
        count = sum(label_for(root, pic).exists() for pic in pics)
        return {
            "total_images": len(pics),
            "labeled": count,
            "unlabeled": len(pics) - count,
            "progress": f"{100 * count / len(pics):.1f}%" if pics else "0.0%",
        }
    todo = []
    for key, pic, record in records:
        if record["status"] == "flagged":
            todo.append((0, key, "fix_issues", record["issues"]))
        elif record["status"] != "modified" and not label_for(root, pic).exists():
            todo.append((1, key, "new_label", None))
    if not todo:
        return {"image_path": None, "task": None, "issues": None, "done": True}
    _, key, task, issues = min(todo)
    return {"image_path": "dataset/images/" + key, "task": task, "issues": issues, "done": False}


def mark(root, args, req):
    manifest = load_manifest(root)
    record = manifest.setdefault(req.key, empty_record())
    if args.issue:
        if args.notes is not None:
            raise AnnoError("--notes requires --verdict approved")
        merge_issue(record, args.issue, args.message.strip(), args.box_index)
    else:
        if args.box_index is not None or args.message is not None:
            raise AnnoError("--box-index and --message require --issue")
        if not req.label.exists():
            raise AnnoError("Cannot approve a missing label", "MISSING_LABEL")
        if not record.get("audit_at") or record.get("audit_fingerprint") != dataset_fingerprint(req):
            raise AnnoError(
                "Run review audit after the latest image, label, class or config change", "STALE_AUDIT"
            )
        if any(record["issues"][kind] is not None for kind in GEOMETRY_ISSUES):
            raise AnnoError("Cannot approve while geometry issues remain", "OPEN_GEOMETRY_ISSUES")
        record.setdefault("history", []).append(
            {"issues": record["issues"], "closed_at": timestamp(), "notes": args.notes}
        )
        record["issues"] = empty_record()["issues"]
        record["status"] = "approved"
        record["verdict"] = {"value": "approved", "notes": args.notes, "updated_at": timestamp()}
    record["updated_at"] = timestamp()
    atomic_json(root / ".anno/manifest.json", manifest)
    return {"image_path": "dataset/images/" + req.key, "review_status": record["status"], "done": False}


def bbox(root, args, req):
    if args.action == "list":
        return {
            "boxes": [
                {
                    "index": b["index"],
                    "class_id": b["class_id"],
                    "class_name": req.classes[b["class_id"]],
                    "xyxy": b["xyxy"],
                }
                for b in req.boxes
            ]
        }
    manifest = load_manifest(root)  # Validate state before touching labels.
    rows = [(b["class_id"], *b["norm"]) for b in req.boxes]
    if args.action == "empty":
        if rows:
            raise AnnoError(
                "bbox empty refuses to overwrite nonempty labels; delete reviewed boxes explicitly"
            )
    elif args.action == "delete":
        rows.pop(args.index)
    else:
        if args.verification_id != verification_id(req, args.class_id):
            raise AnnoError(
                "Verification does not match current image, label, class and box; rerun verify",
                "VERIFICATION_MISMATCH",
            )
        x1, y1, x2, y2 = req.box
        row = (
            args.class_id,
            (x1 + x2) / (2 * req.width),
            (y1 + y2) / (2 * req.height),
            (x2 - x1) / req.width,
            (y2 - y1) / req.height,
        )
        if args.action == "update":
            rows[args.index] = row
        else:
            rows.append(row)
    record = manifest.setdefault(req.key, empty_record())
    record["status"] = "modified" if record["status"] in ("flagged", "modified", "approved") else "unreviewed"
    record.pop("audit_at", None)
    record.pop("audit_fingerprint", None)
    record["updated_at"] = timestamp()
    commit_labels(root, req.label, serialize_labels(rows), manifest)
    return {"image_path": "dataset/images/" + req.key, "box_count": len(rows), "written": True}


def dispatch(root, args):
    if args.command == "init":
        return initialize(root)
    if args.command == "capabilities":
        return json.loads((RESOURCES / "contract.json").read_text())
    if args.command == "schema":
        if Path(args.name).name != args.name or not (RESOURCES / "schemas" / args.name).is_file():
            raise AnnoError("Unknown schema name")
        return {"schema": json.loads((RESOURCES / "schemas" / args.name).read_text())}
    if args.command == "repair":
        return repair(root)
    subcommand = getattr(args, "review_command", None) or getattr(args, "label_command", None)
    writes = subcommand in ("audit", "mark") or subcommand == "bbox" and args.action != "list"
    with project_lock(root, write=writes):
        if args.command == "doctor":
            result = validate_project_readiness(root)
            if not result["ready"]:
                raise AnnoError("Project is not ready", "INVALID_PROJECT", result)
            return result
        if subcommand == "audit":
            return audit(root, args)
        if subcommand in ("next", "status"):
            return queue_or_status(root, args)
        req = validate_request(root, args)
        if subcommand == "verify":
            return {
                "image_path": "dataset/images/" + req.key,
                "verification_id": verification_id(req, args.class_id),
                "box": list(req.box),
            }
        if subcommand == "mark":
            return mark(root, args, req)
        if subcommand == "bbox":
            return bbox(root, args, req)
        return render(root, args, req)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    output_format = "json"
    args = None
    try:
        # Read presentation independently so even argument errors use the requested format.
        presentation = Parser(add_help=False)
        output_format = getattr(presentation.parse_known_args(argv)[0], "format", "json")
        args = build_parser().parse_args(argv)
        output_format = getattr(args, "format", "json")
        result = {"ok": True, "status": "success", **dispatch(Path.cwd().resolve(), args)}
        code = 0
    except AnnoError as error:
        result = {
            "ok": False,
            "status": "error",
            "error": {"code": error.code, "message": str(error), "details": error.details},
        }
        code = 1
    except (OSError, ValueError, TypeError) as error:
        result = {"ok": False, "status": "error", "error": {"code": "INVALID_PROJECT", "message": str(error)}}
        code = 1
    if output_format == "text":
        print(render_text(result, args), file=sys.stderr if code else sys.stdout)
    else:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
