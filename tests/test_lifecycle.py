import json

import pytest


def add(run, path, cells="A1:B2", action="add", index=None):
    token = run("label", "verify", path, "--class", "0", "--cells", cells)["verification_id"]
    args = ["label", "bbox", action, path, "--class", "0", "--cells", cells, "--verification-id", token]
    if index is not None:
        args += ["--index", str(index)]
    return run(*args)


def test_full_lifecycle(project):
    root, run, image = project
    path = image(labels=None)
    assert run("label", "next")["task"] == "new_label"
    add(run, path)
    run("review", "audit")
    run("review", "mark", path, "--verdict", "approved", "--notes", "Visually verified")
    assert run("review", "next")["done"]
    run("review", "mark", path, "--issue", "tightness_error", "--box-index", "0", "--message", "left edge")
    run("review", "mark", path, "--issue", "tightness_error", "--box-index", "0", "--message", "right edge")
    findings = run("label", "next")["issues"]["tightness_error"]["findings"]
    assert len(findings) == 2
    add(run, path, "A1:C2", action="update", index=0)
    assert run("review", "next")["review_status"] == "modified"
    assert run("label", "next")["done"]
    run("review", "mark", path, "--verdict", "approved", ok=False)
    run("review", "audit")
    run("review", "mark", path, "--verdict", "approved")
    assert run("review", "next")["done"]
    state = json.loads((root / ".anno/manifest.json").read_text())["one.png"]
    assert all(value is None for value in state["issues"].values())
    assert state["history"][-1]["issues"]["tightness_error"]["findings"] == findings


def test_priority_order_and_readonly_queue(project):
    root, run, image = project
    a = image("a.png")
    b = image("b.png")
    c = image("c.png")
    run("review", "audit")
    run("review", "mark", b, "--verdict", "approved")
    add(run, b)
    run("review", "mark", c, "--issue", "missing_object", "--message", "missing person")
    before = (root / ".anno/manifest.json").read_bytes()
    assert run("review", "next")["image_path"] == c
    assert run("label", "next")["image_path"] == c
    run("review", "status")
    run("label", "status")
    assert (root / ".anno/manifest.json").read_bytes() == before
    run("review", "audit")
    run("review", "mark", c, "--verdict", "approved")
    assert run("review", "next")["image_path"] == b
    run("review", "mark", b, "--verdict", "approved")
    assert run("review", "next")["image_path"] == a


def test_empty_negative_and_delete(project):
    _, run, image = project
    path = image(labels=None)
    run("label", "bbox", "empty", path)
    assert run("label", "next")["done"]
    add(run, path)
    run("label", "bbox", "empty", path, ok=False)
    run("label", "bbox", "delete", path, "--index", "0")
    assert run("label", "bbox", "list", path)["boxes"] == []
    run("review", "audit")
    run("review", "mark", path, "--verdict", "approved")


@pytest.mark.parametrize("target", ["image", "label", "config", "classes"])
def test_stale_audit_refused(project, target):
    root, run, image = project
    path = image()
    run("review", "audit")
    locations = {
        "image": root / path,
        "label": root / "dataset/labels/one.txt",
        "config": root / ".anno/config/config.json",
        "classes": root / "dataset/data.yaml",
    }
    if target == "image":
        from PIL import Image

        Image.new("RGB", (800, 800), "black").save(locations[target])
    else:
        with locations[target].open("a") as stream:
            stream.write("\n" if target != "classes" else "\n# changed\n")
    # Class comments do not change semantic mapping.
    if target == "classes":
        locations[target].write_text("names: [truck, person]\n")
    assert run("review", "mark", path, "--verdict", "approved", ok=False)["error"]["code"] == "STALE_AUDIT"


def test_verification_binding(project):
    _root, run, image = project
    a = image("a.png")
    b = image("b.png")
    token = run("label", "verify", a, "--class", "0", "--cells", "A1:B2")["verification_id"]
    for path, cid, cells in [(b, "0", "A1:B2"), (a, "1", "A1:B2"), (a, "0", "B2:C3")]:
        assert (
            run(
                "label",
                "bbox",
                "add",
                path,
                "--class",
                cid,
                "--cells",
                cells,
                "--verification-id",
                token,
                ok=False,
            )["error"]["code"]
            == "VERIFICATION_MISMATCH"
        )
    add(run, a)
    run("label", "bbox", "add", a, "--class", "0", "--cells", "A1:B2", "--verification-id", token, ok=False)


def test_missing_label_cannot_approve(project):
    _, run, image = project
    path = image(labels=None)
    run("review", "mark", path, "--verdict", "approved", ok=False)


def test_geometry_blocks_approval(project):
    _, run, image = project
    path = image(labels="0 .5 .5 .001 .001\n")
    run("review", "audit")
    assert (
        run("review", "mark", path, "--verdict", "approved", ok=False)["error"]["code"]
        == "OPEN_GEOMETRY_ISSUES"
    )
