"""Human-facing help and output, independent of command behavior and JSON schemas."""

import argparse
import json
import shlex

COMMANDS = {
    "": (
        "Validated YOLO labeling and explicit review (POSIX).",
        (
            "anno init --format text\nanno doctor --format text\nanno label status --format text\n"
            "anno review audit --format text\nanno review status --format text"
        ),
    ),
    "init": (
        "Create missing project resources; preserve and list existing files.",
        "anno init --format text",
    ),
    "doctor": ("Check project readiness and report errors and warnings.", "anno doctor --format text"),
    "repair": ("Replay an interrupted transaction from its journal.", "anno repair --format text"),
    "capabilities": ("Print the installed command, option and schema contract.", "anno capabilities"),
    "schema": (
        "Print an installed JSON schema without requiring a project.",
        "anno schema review_next.v1.json",
    ),
    "review": (
        "Audit geometry, inspect images and explicitly record review decisions.",
        "anno review audit --format text\nanno review next --format text",
    ),
    "review audit": (
        "Audit geometry and update findings; does not approve or edit labels.",
        "anno review audit --min-size 10 --format text",
    ),
    "review next": (
        "Show the next flagged, modified or unreviewed image; does not reserve it.",
        "anno review next --format text",
    ),
    "review status": (
        "Show review states; reviewed includes flagged and modified images.",
        "anno review status --format text",
    ),
    "review overview": (
        "Render indexed boxes and class names; does not approve.",
        "anno review overview dataset/images/001.jpg --format text",
    ),
    "review sheet": (
        "Alias of review overview; does not approve.",
        "anno review sheet dataset/images/001.jpg --format text",
    ),
    "review inspect": (
        "Render a close-up of one box using its current zero-based index.",
        "anno review inspect dataset/images/001.jpg --index 0 --format text",
    ),
    "review mark": (
        "Record a visual issue, or approve after a current audit and visual inspection.",
        (
            "anno review mark dataset/images/001.jpg --issue tightness_error --message 'Check edges'\n"
            "anno review mark dataset/images/001.jpg --verdict approved --notes 'Visually checked'"
        ),
    ),
    "label": (
        "Find labeling work, inspect grids and edit verified bounding boxes.",
        "anno label next --format text\nanno label grid dataset/images/001.jpg --format text",
    ),
    "label next": (
        "Show a flagged image or an image without labels; does not reserve it.",
        "anno label next --format text",
    ),
    "label status": (
        "Count images with label files, including explicit empty labels.",
        "anno label status --format text",
    ),
    "label grid": (
        "Render a coordinate grid; --cells subdivides the selected parent cells.",
        "anno label grid dataset/images/001.jpg --cells A1:B2 --format text",
    ),
    "label overview": (
        "Render existing indexed boxes and class names.",
        "anno label overview dataset/images/001.jpg --format text",
    ),
    "label select": (
        "Crop selected cells with a grid at the current coordinate level.",
        "anno label select dataset/images/001.jpg --cells A1:B2 --format text",
    ),
    "label visual": (
        "Preview a candidate box before verification or writing.",
        "anno label visual dataset/images/001.jpg --cells A1-a1:B2-h8 --format text",
    ),
    "label verify": (
        "Validate a candidate and issue a token bound to current project content.",
        "anno label verify dataset/images/001.jpg --class 0 --cells A1:B2 --format text",
    ),
    "label bbox": (
        "List or edit boxes. Add/update requires a fresh verification token.",
        "anno label bbox list dataset/images/001.jpg --format text",
    ),
}
for action, description in {
    "add": "Append a verified box.",
    "update": "Replace a box at its current zero-based index using a fresh token.",
    "delete": "Delete a box; remaining indexes may shift.",
    "list": "List current box indexes, classes and pixel coordinates.",
    "empty": "Create an explicit negative label; refuses to overwrite nonempty labels.",
}.items():
    example = f"anno label bbox {action} dataset/images/001.jpg"
    if action in ("update", "delete"):
        example += " --index 0"
    if action in ("add", "update"):
        example += " --class 0 --cells A1:B2 --verification-id TOKEN"
    COMMANDS[f"label bbox {action}"] = (description, example + " --format text")

ARGUMENT_HELP = {
    "image_path": "Image path inside dataset/images/, relative to the project root or absolute",
    "index": "Current box index, starting at 0; obtain with label bbox list",
    "box_index": "Optional current box index, starting at 0",
    "class_id": "Class ID defined in dataset/data.yaml",
    "cells": "Cells or ranges, e.g. A1:B2 or A1-a1:B2-h8; comma-separated lists accepted",
    "verification_id": "Token from label verify; obtain a new token after each edit",
    "max_size": "Maximum preview dimension in pixels (default: 1024)",
    "margin": "Nonnegative padding on each side as a fraction of box size (default: 0.20)",
    "iou_threshold": "High-IoU threshold; uses project config if omitted",
    "min_size": "Minimum box edge in pixels; uses project config if omitted",
    "contained_threshold": "Containment ratio threshold; uses project config if omitted",
    "max_aspect_ratio": "Maximum box aspect ratio; uses project config if omitted",
    "issue": "Visual finding type; requires --message",
    "verdict": "Approve only after a current audit and completed visual inspection",
    "message": "Required nonempty description when using --issue",
    "notes": "Optional review notes for --verdict approved",
}


def configure_help(parser, command=""):
    description, example = COMMANDS[command]
    parser.description = description
    parser.epilog = "Examples (run from the dataset project root):\n  " + example.replace("\n", "\n  ")
    for action in parser._actions:
        if action.dest in ARGUMENT_HELP:
            action.help = ARGUMENT_HELP[action.dest]
        if isinstance(action, argparse._SubParsersAction):
            # Include commands originally declared without a help string.
            existing = {item.dest: item for item in action._choices_actions}
            for name, child in action.choices.items():
                path = f"{command} {name}".strip()
                if name in existing:
                    existing[name].help = COMMANDS[path][0]
                else:
                    action._choices_actions.append(action._ChoicesPseudoAction(name, [], COMMANDS[path][0]))
                configure_help(child, path)
            order = list(action.choices)
            action._choices_actions.sort(key=lambda item: order.index(item.dest))


def _details(value, indent=0):
    """Render every nested field so diagnostics and findings are never lost."""
    prefix = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            label = key.replace("_", " ").capitalize()
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}{label}:")
                lines.extend(_details(item, indent + 2))
            else:
                lines.append(f"{prefix}{label}: {_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(prefix + "-")
                lines.extend(_details(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_scalar(item)}")
        return lines
    return [prefix + _scalar(value)]


def _scalar(value):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None or value == [] or value == {}:
        return "none"
    return str(value)


def render_text(result, args=None):
    command = " ".join(
        str(getattr(args, key))
        for key in ("command", "review_command", "label_command", "action")
        if getattr(args, key, None)
    )
    if not result["ok"]:
        error = result["error"]
        lines = [f"Error [{error['code']}]: {error['message']}"]
        if error.get("details"):
            lines.extend(_details(error["details"], 2))
        hint = {
            "INVALID_ARGUMENT": "anno --help (or anno <command> --help)",
            "INVALID_PROJECT": "anno doctor --format text; inspect the reported project files",
            "RECOVERY_REQUIRED": "anno repair --format text",
            "STALE_AUDIT": "anno review audit --format text, then inspect the image before approval",
            "VERIFICATION_MISMATCH": "Run anno label verify again with the same image, class and cells",
            "AUDIT_INPUT_ERROR": "Fix the listed input errors, then rerun anno review audit --format text",
        }.get(error["code"])
        if hint:
            lines.extend(["", "Next: " + hint])
        return "\n".join(lines)
    # Schema and capabilities remain structured documents, pretty-printed for reading.
    if command in ("schema", "capabilities"):
        return json.dumps(result, ensure_ascii=False, indent=2)
    lines = [f"OK: anno {command}"]
    data = {key: value for key, value in result.items() if key not in ("ok", "status")}
    if command == "review status":
        data["reviewed (includes flagged and modified)"] = data.pop("reviewed")
        data["progress (review activity, not approval)"] = data.pop("progress")
    lines.extend(_details(data))
    hint = None
    if command == "init":
        hint = "Add images to dataset/images/, configure dataset/data.yaml and label.md, then run anno doctor --format text"
    elif command == "review audit":
        hint = "anno review next --format text; audit does not approve images"
    elif command == "repair":
        hint = "anno doctor --format text"
    elif command.endswith(" next"):
        if result["done"]:
            hint = (
                "No labeling work queued. Check anno review status --format text for pending review."
                if command == "label next"
                else "No images pending review."
            )
        else:
            image = shlex.quote(result["image_path"])
            next_command = (
                "review overview"
                if command == "review next" or result.get("task") == "fix_issues"
                else "label grid"
            )
            hint = f"anno {next_command} {image} --format text"
    elif "artifact_path" in result:
        hint = "Open the artifact shown above to inspect it. Rendering does not approve the image."
    elif command == "label verify":
        hint = "Pass the verification id to label bbox add/update using the same image, class and cells."
    if hint:
        lines.extend(["", "Next: " + hint])
    return "\n".join(lines)
