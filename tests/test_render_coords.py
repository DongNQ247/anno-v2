import pytest
from PIL import Image

from anno.core.coords import cells_bounds


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("A1", (0, 0, 100, 100)),
        ("H8", (700, 700, 800, 800)),
        ("A1:B2", (0, 0, 200, 200)),
        ("A1-h8:B2-a1", (87, 87, 113, 113)),
        ("A1-a1, B2-c4", (0, 0, 138, 150)),
        ("A1-a1:A1-a4, B2-c4", (0, 0, 138, 150)),
    ],
)
def test_cells(expr, expected):
    assert cells_bounds(expr, 800, 800) == expected


@pytest.mark.parametrize("expr", ["", "a1", "A1-A1", "I1", "A0", "A1:B2:C3", "B2:A1", "A1,,B2", "A1:B2-a1"])
def test_invalid_cells(expr):
    with pytest.raises(ValueError):
        cells_bounds(expr, 800, 800)


def test_recursive_math_has_no_fixed_depth():
    assert cells_bounds("A1" + "-a1" * 100, 800, 800) == (0, 0, 1, 1)


def test_render_geometry_and_readonly(project):
    root, run, image = project
    path = image(size=(1600, 1600), labels="0 .5 .5 .25 .25\n")
    before = {
        p: p.read_bytes()
        for p in (root / ".anno/manifest.json", root / "dataset/labels/one.txt", root / path)
    }
    result = run("label", "grid", path)
    assert result["cell_labels"][0] == "A1"
    assert result["image_size"] == [1600, 1600]
    assert result["cells"][0]["id"] == "A1"
    assert result["cells"][0]["xyxy"] == [0, 0, 200, 200]
    with Image.open(root / result["artifact_path"]) as im:
        assert im.size == (1024, 1024)
    result = run("label", "grid", path, "--cells", "A1:B2")
    assert len(result["cell_labels"]) == 256
    assert "A1-h8" in result["cell_labels"] and "B2-a1" in result["cell_labels"]
    assert result["image_size"] == [1600, 1600]
    assert len(result["cells"]) == 256
    assert result["cells"][0]["id"] == result["cell_labels"][0]
    with Image.open(root / result["artifact_path"]) as im:
        assert im.size == (800, 800)
        assert im.getpixel((0, 0)) != (255, 255, 255)
    result = run("label", "select", path, "--cells", "A1:B2", "--margin", "0")
    assert set(result["cell_labels"]) == {"A1", "A2", "B1", "B2"}
    assert result["image_size"] == [1600, 1600]
    assert len(result["cells"]) == 4
    result = run("label", "visual", path, "--cells", "C3:D4", "--margin", "0")
    with Image.open(root / result["artifact_path"]) as im:
        assert im.size == (400, 400)
        assert im.getpixel((0, 0)) == (255, 0, 0)
    result = run("review", "inspect", path, "--index", "0")
    assert result["crop"] == [520, 520, 1080, 1080]
    with Image.open(root / result["artifact_path"]) as im:
        assert im.size == (560, 560)
        assert im.getpixel((80, 80)) == (255, 0, 0)
    for group, command in [("review", "overview"), ("review", "sheet"), ("label", "overview")]:
        result = run(group, command, path)
        assert result["class_counts"] == {"0 (car)": 1}
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.parametrize("margin", ["-1", "nan", "inf"])
def test_invalid_margin(project, margin):
    _, run, image = project
    path = image(labels="0 .5 .5 .2 .2\n")
    run("review", "inspect", path, "--index", "0", "--margin", margin, ok=False)
    run("label", "select", path, "--cells", "A1", "--margin", margin, ok=False)


def test_render_does_not_collide(project):
    _, run, image = project
    a = image("a/one.png")
    b = image("b/one.png")
    assert run("label", "grid", a)["artifact_path"] != run("label", "grid", b)["artifact_path"]


def test_subpixel_render_fails_clearly(project):
    _, run, image = project
    path = image(size=(64, 64))
    run("label", "grid", path, "--cells", "A1-a1", ok=False)


def test_small_grid_renders_edge_labels(project):
    _, run, image = project
    path = image(size=(800, 800))
    # In 800x800 image, cell A1 is 100x100. Subcells are ~12x12px, too small for full labels but fit edge labels.
    result = run("label", "grid", path, "--cells", "A1")
    assert len(result["cell_labels"]) == 64
    assert result["crop"] == [0, 0, 100, 100]


def test_small_crop_auto_upscales_with_aspect_ratio(project):
    root, run, image = project
    # Image 1600x800 (2:1 aspect ratio). Cell A1 is 200x100.
    path = image(size=(1600, 800))
    result = run("label", "grid", path, "--cells", "A1")
    assert result["crop"] == [0, 0, 200, 100]
    assert result["image_size"] == [1600, 800]
    with Image.open(root / result["artifact_path"]) as im:
        assert im.size == (600, 300)

    # Scale depends on cell size, independent of range and margin.
    sel = run("label", "select", path, "--cells", "A1:B1", "--margin", "0")
    assert sel["crop"] == [0, 0, 400, 100]
    with Image.open(root / sel["artifact_path"]) as im:
        assert im.size == (1200, 300)


@pytest.mark.parametrize("command", ["grid", "select"])
@pytest.mark.parametrize("scale", ["auto", "1", "3", "4"])
def test_local_scale_metadata(project, command, scale):
    root, run, image = project
    path = image(size=(720, 1280))
    result = run("label", command, path, "--cells", "G4", "--scale", scale)
    factor = 3 if scale == "auto" else int(scale)
    native = [90, 160] if command == "grid" else [126, 224]
    assert result["native_crop_size"] == native
    assert result["scale"] == factor
    assert result["render_size"] == [n * factor for n in native]
    assert result["readable_labels"] is True
    with Image.open(root / result["artifact_path"]) as rendered:
        assert list(rendered.size) == result["render_size"]
    if command == "grid":
        assert result["subcell_size"] == [11.25 * factor, 20 * factor]
        assert result["cells"][0] == {"id": "G4-a1", "xyxy": [540, 480, 552, 500]}
    else:
        assert result["crop"] == [522, 448, 648, 672]
        assert result["cells"] == [{"id": "G4", "xyxy": [540, 480, 630, 640]}]


def test_subgrid_guardrails(project):
    _, run, image = project
    path = image(size=(720, 1280))
    for scale in ("auto", "4"):
        failure = run("label", "grid", path, "--cells", "A3:H8", "--scale", scale, ok=False)
        details = failure["error"]["details"]
        assert details["parent_cell_count"] == 48
        assert details["subcell_count"] == 3072
        assert details["recommended_max_parent_cells"] == 8
        assert "smaller local edge" in details["suggested_cells"]
    path = image(size=(800, 400))
    failure = run("label", "grid", path, "--cells", "A3:C4", ok=False)
    details = failure["error"]["details"]
    assert details["native_crop_size"] == [300, 100]
    assert details["native_subcell_min_edge"] == 6.25
    assert details["required_scale"] == 5
    assert details["max_scale"] == 4


@pytest.mark.parametrize("scale", ["0", "5", "-1", "1.5", "nan"])
def test_invalid_scale(project, scale):
    _, run, image = project
    path = image()
    for command in ("grid", "select"):
        run("label", command, path, "--cells", "A1", "--scale", scale, ok=False)


def test_scale_requires_local_grid(project):
    _, run, image = project
    run("label", "grid", image(), "--scale", "3", ok=False)


def test_default_scale_and_guard_boundary(project):
    _, run, image = project
    path = image(size=(720, 1280))
    for command in ("grid", "select"):
        assert run("label", command, path, "--cells", "G4")["scale"] == 3
    result = run("label", "grid", path, "--cells", "A3:C4")
    assert result["parent_cell_count"] == 6
    assert result["subcell_count"] == 384
    assert run("label", "grid", path, "--cells", "A1:H1")["parent_cell_count"] == 8
    run("label", "grid", path, "--cells", "A1:C3", ok=False)
