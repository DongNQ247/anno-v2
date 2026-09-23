"""Regenerate packaged and repository contracts from the actual CLI parser."""

import argparse
import json
from pathlib import Path

import yaml

from anno import __version__
from anno.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


def commands(parser, prefix=""):
    children = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    if children:
        result = {}
        for name, child in children.choices.items():
            result.update(commands(child, (prefix + " " + name).strip()))
        return result
    options = []
    for action in parser._actions:
        if action.dest == "help":
            continue
        options.append(
            {
                "name": action.option_strings[-1] if action.option_strings else action.dest,
                "required": action.required,
                "type": "boolean"
                if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction))
                else action.type.__name__
                if action.type
                else "string",
                "default": "json" if action.dest == "format" else action.default,
                **({"choices": list(action.choices)} if action.choices else {}),
            }
        )
    return {
        prefix: {
            "arguments": options,
            "response_schema": prefix.replace(" ", "_") + ".v1.json",
            "exclusive_groups": [
                {
                    "required": group.required,
                    "arguments": [action.option_strings[-1] for action in group._group_actions],
                }
                for group in parser._mutually_exclusive_groups
            ],
        }
    }


def generate():
    inventory = commands(build_parser())
    contract = {
        "api_version": "1",
        "version": __version__,
        "commands": list(inventory),
        "command_details": inventory,
        "schemas": {p.stem: p.name for p in sorted((ROOT / "schemas").glob("*.json"))},
        "paths": {
            "images": "dataset/images",
            "labels": "dataset/labels",
            "manifest": ".anno/manifest.json",
            "config": ".anno/config/config.json",
            "artifacts": ".anno/tmp/<relative-image-filename>/",
            "schemas": ".anno/schemas",
            "transaction": ".anno/transaction.json",
        },
        "mutation_rules": {
            "bbox_add_requires_verification_id": True,
            "bbox_update_requires_verification_id": True,
            "render_commands_change_review_state": False,
            "concurrency": "POSIX advisory project lock",
            "recovery": "anno repair",
            "negative_images": "anno label bbox empty IMAGE",
        },
        "errors": [
            "INVALID_ARGUMENT",
            "INVALID_REQUEST",
            "INVALID_PROJECT",
            "PATH_OUTSIDE_ROOT",
            "INVALID_IMAGE",
            "MISSING_LABEL",
            "INVALID_LABEL",
            "AUDIT_INPUT_ERROR",
            "STALE_AUDIT",
            "OPEN_GEOMETRY_ISSUES",
            "VERIFICATION_MISMATCH",
            "CONCURRENT_CHANGE",
            "RECOVERY_REQUIRED",
        ],
        "unsupported": ["label infer", "a4od entrypoint"],
        "platforms": ["POSIX (Linux tested)"],
    }
    common = {"ok": {"const": True}, "status": {"const": "success"}}
    shapes = {
        "init": {
            "created": {"type": "array", "items": {"type": "string"}},
            "conflicts": {"type": "array", "items": {"type": "string"}},
            "message": {"type": "string"},
        },
        "doctor": {
            "ready": {"const": True},
            "images_count": {"type": "integer", "minimum": 0},
            "classes_count": {"type": "integer", "minimum": 1},
            "class_compiled": {"type": "boolean"},
            "model_assisted": {"const": False},
            "errors": {"type": "array"},
            "warnings": {"type": "array"},
        },
        "repair": {"recovered": {"type": "boolean"}},
        "schema": {"schema": {"type": "object"}},
        "capabilities": {
            k: {"type": "array" if isinstance(v, list) else "object" if isinstance(v, dict) else "string"}
            for k, v in contract.items()
        },
        "review audit": {
            "effective_config": {"type": "object"},
            "scanned_images": {"type": "integer", "minimum": 0},
            "flagged_images": {"type": "integer", "minimum": 0},
        },
        "review status": {
            "total_images": {"type": "integer", "minimum": 0},
            "reviewed": {"type": "integer", "minimum": 0},
            "unreviewed": {"type": "integer", "minimum": 0},
            "progress": {"type": "string"},
            "by_status": {"type": "object"},
        },
        "label status": {
            "total_images": {"type": "integer", "minimum": 0},
            "labeled": {"type": "integer", "minimum": 0},
            "unlabeled": {"type": "integer", "minimum": 0},
            "progress": {"type": "string"},
        },
        "review mark": {
            "image_path": {"type": "string"},
            "review_status": {"enum": ["flagged", "approved"]},
            "done": {"const": False},
        },
        "label verify": {
            "image_path": {"type": "string"},
            "verification_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "box": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "integer"}},
        },
        "label bbox list": {
            "boxes": {
                "type": "array",
                "items": {"type": "object", "required": ["index", "class_id", "class_name", "xyxy"]},
            }
        },
    }
    for command in inventory:
        properties = shapes.get(command)
        if properties is None:
            if command.endswith("next"):
                properties = {"image_path": {"type": ["string", "null"]}, "done": {"type": "boolean"}}
                if command.startswith("label"):
                    properties.update(
                        task={"enum": ["fix_issues", "new_label", None]}, issues={"type": ["object", "null"]}
                    )
            elif command.startswith("label bbox"):
                properties = {
                    "image_path": {"type": "string"},
                    "box_count": {"type": "integer", "minimum": 0},
                    "written": {"const": True},
                }
            else:
                properties = {"image_path": {"type": "string"}, "artifact_path": {"type": "string"}}
                if command.endswith(("overview", "sheet")):
                    properties.update(
                        boxes={"type": "integer", "minimum": 0},
                        class_counts={"type": "object"},
                        label_missing={"type": "boolean"},
                    )
                if command.endswith("inspect"):
                    properties.update(
                        box_index={"type": "integer", "minimum": 0},
                        crop={"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "integer"}},
                    )
                if command.endswith(("grid", "select")):
                    properties.update(cell_labels={"type": "array", "items": {"type": "string"}})
                if command.endswith("visual"):
                    properties.update(
                        crop={"type": "array", "minItems": 4, "maxItems": 4},
                        xyxy={"type": "array", "minItems": 4, "maxItems": 4},
                    )
        filename = inventory[command]["response_schema"]
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "anno://schemas/" + filename,
            "type": "object",
            "required": list(common) + list(properties),
            "properties": {**common, **properties},
            "additionalProperties": False,
        }
        if command.endswith("next"):
            if command.startswith("review"):
                schema["properties"].update(
                    review_status={"enum": ["flagged", "modified", "unreviewed"]}, issues={"type": "object"}
                )
            schema["allOf"] = [
                {
                    "if": {"properties": {"done": {"const": True}}},
                    "then": {"properties": {"image_path": {"type": "null"}}},
                    "else": {"properties": {"image_path": {"type": "string"}}},
                }
            ]
        if command.endswith("grid"):
            schema["properties"]["crop"] = {"type": "array", "minItems": 4, "maxItems": 4}
        if command.endswith("select"):
            schema["properties"]["crop"] = {"type": "array", "minItems": 4, "maxItems": 4}
            schema["required"].append("crop")
        (ROOT / "schemas" / filename).write_text(json.dumps(schema, indent=2) + "\n")
    contract["schemas"] = {p.stem: p.name for p in sorted((ROOT / "schemas").glob("*.json"))}
    (ROOT / "src/anno/templates/contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    (ROOT / "anno-contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False))
    for path in (ROOT / "schemas").glob("*.json"):
        (ROOT / "src/anno/templates/schemas" / path.name).write_text(path.read_text())


if __name__ == "__main__":
    generate()
