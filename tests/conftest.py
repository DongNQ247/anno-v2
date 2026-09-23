import json
from pathlib import Path

import pytest
from jsonschema import validate
from PIL import Image

from anno.cli import main
from anno.core.project import RESOURCES


@pytest.fixture
def project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def run(*args, ok=True):
        code = main(list(args))
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert (code == 0) == ok, data
        if ok:
            command = " ".join(
                args[:3]
                if args[:2] == ("label", "bbox")
                else args[:2]
                if args[0] in ("label", "review")
                else args[:1]
            )
            schema = RESOURCES / "schemas" / (command.replace(" ", "_") + ".v1.json")
        else:
            schema = RESOURCES / "schemas/error.v1.json"
        validate(data, json.loads(schema.read_text()))
        return data

    run("init")
    (tmp_path / "dataset/data.yaml").write_text("names: [car, person]\n")
    (tmp_path / "label.md").write_text("Label visible cars and people; boxes follow visible boundaries.")
    (tmp_path / ".anno/skills/anno-class/SKILL.md").write_text(
        "# Classes\n0: car; 1: person. Use visible extents."
    )

    def image(name="one.png", size=(800, 800), labels=""):
        path = tmp_path / "dataset/images" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, "white").save(path)
        if labels is not None:
            label = tmp_path / "dataset/labels" / Path(name).with_suffix(".txt")
            label.parent.mkdir(parents=True, exist_ok=True)
            label.write_text(labels)
        return "dataset/images/" + name

    return tmp_path, run, image
