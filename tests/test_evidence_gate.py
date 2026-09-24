"""Acceptance tests for evidence-gated coordinate depth."""

from PIL import Image


def test_level_1_allowed_without_subgrid(project):
    """Candidate using level 1 does not require opening a subgrid."""
    _, run, image = project
    path = image("img.png")
    run("label", "grid", path)
    res = run("label", "verify", path, "--class", "0", "--cells", "A1")
    assert res["coordinate_level"] == 1
    assert res["parent_cells"] == []
    assert res["evidence_id"] == "level_1_root"


def test_depth_rejection_without_parent_evidence(project):
    """A1 is valid, but A1-a1 is rejected when parent A1 subgrid was never opened."""
    _, run, image = project
    path = image("img.png")
    run("label", "grid", path)
    res = run("label", "verify", path, "--class", "0", "--cells", "A1-a1", ok=False)
    assert res["error"]["code"] == "INVALID_ARGUMENT"
    assert res["error"]["details"]["reason"] == "COORDINATE_EVIDENCE_REQUIRED"
    assert res["error"]["details"]["coordinate_level"] == 2
    assert "A1" in res["error"]["details"]["missing_parents"]
    assert "suggested_recovery" in res["error"]
    assert "anno label grid" in res["error"]["suggested_recovery"]


def test_subgrid_opens_child_evidence(project):
    """Opening subgrid for B3 allows B3-a2, but C4-a2 is rejected."""
    _, run, image = project
    path = image("img.png")
    run("label", "grid", path, "--cells", "B3")
    res_b3 = run("label", "verify", path, "--class", "0", "--cells", "B3-a2")
    assert res_b3["coordinate_level"] == 2
    assert res_b3["parent_cells"] == ["B3"]
    assert "evidence_id" in res_b3

    res_c4 = run("label", "verify", path, "--class", "0", "--cells", "C4-a2", ok=False)
    assert res_c4["error"]["code"] == "INVALID_ARGUMENT"
    assert res_c4["error"]["details"]["reason"] == "COORDINATE_EVIDENCE_REQUIRED"
    assert "C4" in res_c4["error"]["details"]["missing_parents"]


def test_hierarchical_chain_level_3(project):
    """Opening B3 and then B3-a2 allows B3-a2-a1; B3-a3-a1 remains rejected."""
    _, run, image = project
    path = image("img.png", size=(4096, 4096))
    run("label", "grid", path, "--cells", "B3")
    run("label", "grid", path, "--cells", "B3-a2")

    res = run("label", "verify", path, "--class", "0", "--cells", "B3-a2-a1")
    assert res["coordinate_level"] == 3
    assert res["parent_cells"] == ["B3", "B3-a2"]

    rejected = run("label", "verify", path, "--class", "0", "--cells", "B3-a3-a1", ok=False)
    assert rejected["error"]["code"] == "INVALID_ARGUMENT"
    assert rejected["error"]["details"]["reason"] == "COORDINATE_EVIDENCE_REQUIRED"
    assert "B3-a3" in rejected["error"]["details"]["missing_parents"]


def test_cross_image_evidence_isolation(project):
    """Evidence for image A cannot be used to verify or mutate image B."""
    _, run, image = project
    a = image("a.png")
    b = image("b.png")

    run("label", "grid", a, "--cells", "B3")
    # Verify B3-a2 succeeds on a.png
    assert run("label", "verify", a, "--class", "0", "--cells", "B3-a2")["ok"]

    # Verify B3-a2 on b.png must fail
    res = run("label", "verify", b, "--class", "0", "--cells", "B3-a2", ok=False)
    assert res["error"]["code"] == "INVALID_ARGUMENT"
    assert res["error"]["details"]["reason"] == "COORDINATE_EVIDENCE_REQUIRED"


def test_bbox_add_and_update_rejection_leaves_state_clean(project):
    """Bbox add and update enforce evidence gates; rejection does not modify labels or manifest."""
    root, run, image = project
    path = image("img.png", labels=None)
    manifest_before = (root / ".anno/manifest.json").read_bytes()
    label_path = root / "dataset/labels/img.txt"

    # Direct add with depth 2 without evidence must fail
    run(
        "label",
        "bbox",
        "add",
        path,
        "--class",
        "0",
        "--cells",
        "B3-a2",
        "--verification-id",
        "dummy_token",
        ok=False,
    )
    assert not label_path.exists()
    assert (root / ".anno/manifest.json").read_bytes() == manifest_before

    # Now open B3 evidence, verify, and add
    run("label", "grid", path, "--cells", "B3")
    ver = run("label", "verify", path, "--class", "0", "--cells", "B3-a2")
    token = ver["verification_id"]

    res_add = run(
        "label",
        "bbox",
        "add",
        path,
        "--class",
        "0",
        "--cells",
        "B3-a2",
        "--verification-id",
        token,
    )
    assert res_add["written"]
    assert res_add["box_count"] == 1
    assert label_path.exists()
    label_content = label_path.read_text()

    # Now try update with un-evidenced depth 2 cell (C4-a2)
    run(
        "label",
        "bbox",
        "update",
        path,
        "--index",
        "0",
        "--class",
        "0",
        "--cells",
        "C4-a2",
        "--verification-id",
        token,
        ok=False,
    )
    # Label content must be unchanged
    assert label_path.read_text() == label_content

    # Now verify with valid evidenced cell and update successfully
    ver_update = run("label", "verify", path, "--class", "0", "--cells", "B3-a3")
    res_update = run(
        "label",
        "bbox",
        "update",
        path,
        "--index",
        "0",
        "--class",
        "0",
        "--cells",
        "B3-a3",
        "--verification-id",
        ver_update["verification_id"],
    )
    assert res_update["written"]
    assert label_path.read_text() != label_content


def test_evidence_invalidated_when_image_changes(project):
    """Modifying the image file invalidates previously gathered evidence."""
    root, run, image = project
    path = image("img.png")
    run("label", "grid", path, "--cells", "B3")
    assert run("label", "verify", path, "--class", "0", "--cells", "B3-a2")["ok"]

    # Modify image pixels
    img_file = root / path
    Image.new("RGB", (800, 800), "black").save(img_file)

    # Now B3-a2 should fail because image fingerprint changed
    res = run("label", "verify", path, "--class", "0", "--cells", "B3-a2", ok=False)
    assert res["error"]["code"] == "INVALID_ARGUMENT"
    assert res["error"]["details"]["reason"] == "COORDINATE_EVIDENCE_REQUIRED"
