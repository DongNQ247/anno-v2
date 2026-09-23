import json

import pytest


def state(root):
    return json.loads((root / ".anno/manifest.json").read_text())


@pytest.mark.parametrize(
    "size,label,kind,expected",
    [
        ((1000, 100), "0 .5 .5 .5 .1", "extreme_aspect_ratio", True),
        ((1000, 100), "0 .5 .5 .2 .1", "extreme_aspect_ratio", False),
        ((1000, 100), "0 .5 .5 .201 .1", "extreme_aspect_ratio", True),
        ((100, 100), "0 .5 .5 .05 .1", "tiny_box", False),
        ((100, 100), "0 .5 .5 .049 .1", "tiny_box", True),
        ((100, 100), "0 .05 .5 .1 .1", "out_of_bounds", False),
        ((100, 100), "0 .049 .5 .1 .1", "out_of_bounds", True),
        ((100, 100), "0 .5 .5 .5 .5\n1 .5 .5 .5 .5", "high_iou", True),
        ((100, 100), "0 .5 .5 .5 .5\n1 .5 .5 .1 .1", "contained_box", True),
    ],
)
def test_geometry(project, size, label, kind, expected):
    root, run, image = project
    image(size=size, labels=label + "\n")
    run("review", "audit")
    assert (state(root)["one.png"]["issues"][kind] is not None) == expected


@pytest.mark.parametrize(
    "label", [None, "bad label", "9 .5 .5 .1 .1", "0 nan .5 .1 .1", "0 .5 .5 -1 .1", "0 .5 .5 0 .1"]
)
def test_bad_labels_abort_without_manifest_change(project, label):
    root, run, image = project
    image(labels=label)
    before = (root / ".anno/manifest.json").read_bytes()
    result = run("review", "audit", ok=False)
    assert result["error"]["code"] == "AUDIT_INPUT_ERROR"
    assert result["error"]["details"]["failures"][0]["image_path"] == "dataset/images/one.png"
    assert (root / ".anno/manifest.json").read_bytes() == before


def test_bad_image(project):
    root, run, image = project
    path = image()
    (root / path).write_bytes(b"not an image")
    assert run("review", "audit", ok=False)["error"]["details"]["failures"]


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.update(schema_version=True),
        lambda c: c.update(extra=1),
        lambda c: c["review"]["audit"].update(iou_threshold=0),
        lambda c: c["review"]["audit"].update(min_box_edge_px=1.5),
        lambda c: c["review"]["audit"]["checks"].update(high_iou=1),
        lambda c: c.update(review=[]),
        lambda c: c["review"]["audit"].update(iou_threshold=1.01),
    ],
)
def test_invalid_config(project, change):
    root, run, image = project
    image()
    path = root / ".anno/config/config.json"
    config = json.loads(path.read_text())
    change(config)
    path.write_text(json.dumps(config))
    before = (root / ".anno/manifest.json").read_bytes()
    run("review", "audit", ok=False)
    run("doctor", ok=False)
    assert (root / ".anno/manifest.json").read_bytes() == before


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1", "1.01"])
def test_invalid_override(project, value):
    _, run, image = project
    image()
    run("review", "audit", "--iou-threshold", value, ok=False)


def test_override_and_repeat_preserve_visual_findings(project):
    root, run, image = project
    path = image(labels="0 .5 .5 .005 .005\n")
    run("review", "mark", path, "--issue", "missing_object", "--message", "person absent")
    config = (root / ".anno/config/config.json").read_bytes()
    run("review", "audit", "--min-size", "1")
    assert state(root)["one.png"]["issues"]["tiny_box"] is None
    assert state(root)["one.png"]["issues"]["missing_object"]["message"] == "person absent"
    run("review", "audit")
    assert state(root)["one.png"]["issues"]["tiny_box"] is not None
    assert (root / ".anno/config/config.json").read_bytes() == config


def test_audit_does_not_clamp_labels(project):
    root, run, image = project
    image(labels="0 -.1 .5 .5 .5\n")
    label = root / "dataset/labels/one.txt"
    before = label.read_bytes()
    run("review", "audit")
    assert label.read_bytes() == before


@pytest.mark.parametrize(
    "ratio,kind,expected",
    [
        (0.8, "high_iou", True),
        (0.799, "high_iou", False),
        (0.999, "contained_box", True),
        (0.998, "contained_box", False),
    ],
)
def test_pair_thresholds(project, ratio, kind, expected):
    root, run, image = project
    if kind == "high_iou":
        # A contained rectangle has IoU equal to its width ratio.
        labels = f"0 .5 .5 1 1\n1 .5 .5 {ratio} 1\n"
    else:
        # Equal unit boxes translated horizontally: intersection/smaller area = ratio.
        labels = f"0 .5 .5 1 1\n1 {1.5 - ratio} .5 1 1\n"
    image(size=(1000, 1000), labels=labels)
    run("review", "audit")
    assert (state(root)["one.png"]["issues"][kind] is not None) == expected


def test_disabled_checks(project):
    root, run, image = project
    image(labels="0 .5 .5 .001 .001\n")
    config = root / ".anno/config/config.json"
    data = json.loads(config.read_text())
    data["review"]["audit"]["checks"]["tiny_box"] = False
    config.write_text(json.dumps(data))
    result = run("review", "audit")
    assert result["flagged_images"] == 0
    assert result["effective_config"]["checks"]["tiny_box"] is False


def test_derived_overflow_rejected(project):
    _, run, image = project
    image(labels="0 1e308 .5 .5 .5\n")
    result = run("review", "audit", ok=False)
    assert result["error"]["details"]["failures"][0]["code"] == "INVALID_LABEL"
