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
        assert im.size == (400, 400)
        assert im.getpixel((25, 150)) != (255, 255, 255)
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

