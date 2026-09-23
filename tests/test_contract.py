import json
import subprocess
import sys
from pathlib import Path

import pytest

from anno.cli import build_parser
from anno.core.project import RESOURCES


def test_capabilities_and_schema(project):
    root, run, image = project
    result = run("capabilities")
    for command, spec in result["command_details"].items():
        assert command in result["commands"]
        assert (root / ".anno/schemas" / spec["response_schema"]).is_file()
    run("schema", "manifest.v1.json")
    run("schema", "../config.json", ok=False)
    image()
    assert run("doctor")["ready"]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["bad"],
        ["review", "inspect", "x", "--index", "abc"],
        ["label", "verify", "x", "--class", "0", "--box", "1", "2", "3", "4"],
        ["review", "mark", "x", "--issue", "bad"],
    ],
)
def test_parser_errors_are_json(project, args):
    _, run, _ = project
    assert run(*args, ok=False)["error"]["code"] == "INVALID_ARGUMENT"


def test_doctor_error_schema_and_optional_model(project):
    root, run, image = project
    image()
    assert run("doctor")["model_assisted"] is False
    (root / "dataset/data.yaml").write_text("names: {}")
    result = run("doctor", ok=False)
    assert result["error"]["details"]["ready"] is False


def test_init_preserves_every_existing_file(project):
    root, run, image = project
    image()
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    run("init", "--force")
    assert all(p.read_bytes() == content for p, content in before.items())


def test_packaged_schema_copies():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "schemas").glob("*.json"):
        assert path.read_bytes() == (RESOURCES / "schemas" / path.name).read_bytes()


def test_parser_matches_contract():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "tools/generate_contract.py"
    spec = importlib.util.spec_from_file_location("contract_generator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = json.loads((RESOURCES / "contract.json").read_text())
    assert module.commands(build_parser()) == contract["command_details"]


def test_entrypoint(project):
    root, _, image = project
    image()
    result = subprocess.run(
        [sys.executable, "-m", "anno.cli", "doctor"], cwd=root, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ready"]
