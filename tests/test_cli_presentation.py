"""Exercise presentation at the CLI boundary while retaining the JSON contract."""

import json
import subprocess
import sys

import pytest

from anno.cli import build_parser, main


@pytest.mark.parametrize(
    "args",
    [
        ["--format", "text", "label", "status"],
        ["label", "--format", "text", "status"],
        ["label", "status", "--format=text"],
    ],
)
def test_text_format_at_each_level(project, capsys, args):
    _, _, image = project
    image()
    image("missing.png", labels=None)
    assert main(args) == 0
    captured = capsys.readouterr()
    assert "Total images: 2" in captured.out
    assert "Labeled: 1" in captured.out
    assert "Progress: 50.0%" in captured.out
    assert captured.err == ""


def test_json_explicit_and_default_match(project, capsys):
    _, _, image = project
    image()
    assert main(["doctor"]) == 0
    default = json.loads(capsys.readouterr().out)
    assert main(["--format", "text", "doctor", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == default


@pytest.mark.parametrize(
    "args",
    [
        ["--format", "text", "unknown"],
        ["review", "inspect", "x", "--index", "abc", "--format", "text"],
        ["--format", "text"],
    ],
)
def test_text_argument_errors_go_to_stderr(capsys, args):
    assert main(args) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error [INVALID_ARGUMENT]" in captured.err
    assert "--help" in captured.err


def test_doctor_errors_are_not_hidden(project, capsys):
    root, _, _ = project
    (root / "dataset/data.yaml").write_text("names: {}")
    assert main(["doctor", "--format", "text"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "Error [INVALID_PROJECT]" in captured.err
    assert "Errors:" in captured.err
    assert "class" in captured.err.lower()


def test_review_progress_is_not_approval(project, capsys):
    _, run, image = project
    image(labels="0 0.5 0.5 0.001 0.001\n")
    run("review", "audit")
    assert main(["review", "status", "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "Flagged: 1" in output
    assert "Approved: 0" in output
    assert "Progress (review activity, not approval): 100.0%" in output


def test_next_hint_quotes_paths_and_does_not_write_state(project, capsys):
    root, _, image = project
    image("my photo's.png", labels=None)
    before = (root / ".anno/manifest.json").read_bytes()
    assert main(["label", "next", "--format", "text"]) == 0
    output = capsys.readouterr().out
    import shlex

    hint = output.split("Next: ", 1)[1].strip()
    assert shlex.split(hint) == ["anno", "label", "grid", "dataset/images/my photo's.png", "--format", "text"]
    assert (root / ".anno/manifest.json").read_bytes() == before


def test_empty_queue_and_render_artifact(project, capsys):
    _, _, image = project
    path = image()
    assert main(["label", "next", "--format", "text"]) == 0
    assert "pending review" in capsys.readouterr().out
    assert main(["review", "overview", path, "--format", "text"]) == 0
    assert "Artifact path: .anno/tmp/one.png/review_overview.png" in capsys.readouterr().out


def test_all_command_help_has_examples_and_argument_descriptions():
    import argparse

    def check(parser):
        assert "Examples" in parser.format_help()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    check(child)
            else:
                assert action.help, (parser.prog, action.dest)

    check(build_parser())


def test_text_entrypoint_and_audit_failure_details(project):
    root, _, image = project
    image("first.png", labels=None)
    image("second.png", labels=None)
    before = (root / ".anno/manifest.json").read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "anno.cli", "review", "audit", "--format", "text"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "AUDIT_INPUT_ERROR" in result.stderr
    assert "dataset/images/first.png" in result.stderr
    assert "dataset/images/second.png" in result.stderr
    assert (root / ".anno/manifest.json").read_bytes() == before


def test_text_format_at_bbox_depth(project, capsys):
    _, _, image = project
    path = image(labels="0 0.5 0.5 0.25 0.25\n")
    assert main(["label", "bbox", "list", path, "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "Index: 0" in output
    assert "Class name: car" in output
