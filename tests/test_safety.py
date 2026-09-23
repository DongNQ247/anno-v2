import json
import subprocess
import sys

import pytest

from anno.core import storage


def test_outside_and_symlink_images(project, tmp_path_factory):
    root, run, _image = project
    outside = tmp_path_factory.mktemp("outside") / "outside.png"
    from PIL import Image

    Image.new("RGB", (100, 100)).save(outside)
    run("label", "grid", str(outside), ok=False)
    (root / "dataset/images/link.png").symlink_to(outside)
    run("label", "grid", "dataset/images/link.png", ok=False)
    run("review", "audit", ok=False)


def test_symlink_label_and_artifact_refused(project, tmp_path_factory):
    root, run, image = project
    path = image(labels=None)
    outside = tmp_path_factory.mktemp("outside")
    target = outside / "label.txt"
    target.write_text("")
    (root / "dataset/labels/one.txt").symlink_to(target)
    run("label", "bbox", "empty", path, ok=False)
    assert target.read_text() == ""
    (root / ".anno/tmp/one.png").symlink_to(outside, target_is_directory=True)
    run("label", "grid", path, ok=False)


def test_corrupt_manifest_never_mutates_label(project):
    root, run, image = project
    path = image(labels="0 .5 .5 .2 .2\n")
    label = root / "dataset/labels/one.txt"
    before = label.read_bytes()
    (root / ".anno/manifest.json").write_text("{bad")
    run("label", "bbox", "delete", path, "--index", "0", ok=False)
    assert label.read_bytes() == before


def test_interrupted_write_replay(project, monkeypatch):
    root, run, image = project
    path = image(labels=None)
    token = run("label", "verify", path, "--class", "0", "--cells", "A1:B2")["verification_id"]
    original = storage.atomic_json

    def fail_manifest(file, data):
        if file.name == "manifest.json":
            raise OSError("simulated disk failure")
        return original(file, data)

    with monkeypatch.context() as patch:
        patch.setattr(storage, "atomic_json", fail_manifest)
        run(
            "label",
            "bbox",
            "add",
            path,
            "--class",
            "0",
            "--cells",
            "A1:B2",
            "--verification-id",
            token,
            ok=False,
        )
    assert (root / ".anno/transaction.json").exists()
    assert run("label", "next", ok=False)["error"]["code"] == "RECOVERY_REQUIRED"
    assert run("repair")["recovered"]
    assert not run("repair")["recovered"]
    assert len(run("label", "bbox", "list", path)["boxes"]) == 1
    run("review", "audit")


def test_concurrent_marks_preserve_findings(project):
    root, run, image = project
    path = image()
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "anno.cli",
                "review",
                "mark",
                path,
                "--issue",
                "missing_object",
                "--message",
                f"finding {i}",
            ],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(8)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)
    findings = run("label", "next")["issues"]["missing_object"]["findings"]
    assert len(findings) == 8


def test_real_process_crash_recovery(project):
    root, run, image = project
    path = image(labels=None)
    code = """
from pathlib import Path
from anno.core import storage
from anno.core.project import empty_record
from anno.core.storage import project_lock
import os
root=Path.cwd()
original=storage.atomic_json
def crash(path,data):
    if path.name=='manifest.json': os._exit(91)
    original(path,data)
storage.atomic_json=crash
with project_lock(root,write=True):
    storage.commit_labels(root,root/'dataset/labels/one.txt','0 .5 .5 .2 .2\\n',{'one.png':empty_record()})
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=root, timeout=30, check=False)
    assert result.returncode == 91
    run("review", "next", ok=False)
    assert run("repair")["recovered"]
    assert len(run("label", "bbox", "list", path)["boxes"]) == 1


@pytest.mark.parametrize(
    "names",
    [
        "names: {0: car, 0: truck}",
        "names: {-1: car}",
        "names: {1: car}",
        "names: [null]",
        "names: [car, car]",
        "names: {true: car}",
        "names: [car]\nnc: 2",
    ],
)
def test_bad_class_mapping(project, names):
    root, run, image = project
    image()
    (root / "dataset/data.yaml").write_text(names)
    run("doctor", ok=False)


def test_same_stem_images_refused(project):
    _, run, image = project
    image("one.png")
    path = image("one.jpg")
    run("label", "next", ok=False)
    run("label", "bbox", "empty", path, ok=False)


def test_missing_manifest_not_silently_replaced(project):
    root, run, image = project
    path = image(labels="0 .5 .5 .2 .2\n")
    (root / ".anno/manifest.json").unlink()
    run("label", "bbox", "delete", path, "--index", "0", ok=False)


@pytest.mark.parametrize("content", ["names: [", "names: !unknown {}", "names:\n  - x\n y: z"])
def test_malformed_yaml_json_errors(project, content):
    root, run, image = project
    image()
    (root / "dataset/data.yaml").write_text(content)
    run("doctor", ok=False)
    run("review", "audit", ok=False)


def test_concurrent_add_uses_fresh_verification(project):
    root, run, image = project
    path = image(labels=None)
    token = run("label", "verify", path, "--class", "0", "--cells", "A1:B2")["verification_id"]
    args = [
        sys.executable,
        "-m",
        "anno.cli",
        "label",
        "bbox",
        "add",
        path,
        "--class",
        "0",
        "--cells",
        "A1:B2",
        "--verification-id",
        token,
    ]
    processes = [
        subprocess.Popen(args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert not stderr
        results.append((process.returncode, json.loads(stdout)))
    assert sorted(code for code, _ in results) == [0, 1]
    assert len(run("label", "bbox", "list", path)["boxes"]) == 1


def test_json_numeric_overflow_rejected(project):
    root, run, image = project
    image()
    config = root / ".anno/config/config.json"
    config.write_text(config.read_text().replace("20.0", "1e309"))
    run("doctor", ok=False)


def test_nested_image_fingerprint(project):
    root, run, image = project
    path = image("a/b/c.png")
    run("review", "audit")
    config = root / ".anno/config/config.json"
    config.write_text(config.read_text() + "\n")
    assert run("review", "mark", path, "--verdict", "approved", ok=False)["error"]["code"] == "STALE_AUDIT"
