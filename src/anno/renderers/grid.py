"""Render labels in the same global coordinate system used by bbox math."""

from fractions import Fraction

from PIL import ImageDraw, ImageFont

from ..core.coords import cells_bounds, name, selected_cells
from ..core.errors import AnnoError
from .visualizer import crop_bounds


def draw_cells(image, cells, original_size, origin=(0, 0), scale=(1, 1)):
    draw = ImageDraw.Draw(image)
    width, height = original_size
    labels = []
    for x, y, depth in cells:
        denominator = 8**depth
        x1 = float(Fraction(x * width, denominator))
        y1 = float(Fraction(y * height, denominator))
        x2 = float(Fraction((x + 1) * width, denominator))
        y2 = float(Fraction((y + 1) * height, denominator))
        if x2 - x1 < 1 or y2 - y1 < 1:
            raise AnnoError("Grid cells are smaller than one source pixel; use a coarser selection")
        rect = (
            (x1 - origin[0]) * scale[0],
            (y1 - origin[1]) * scale[1],
            (x2 - origin[0]) * scale[0],
            (y2 - origin[1]) * scale[1],
        )
        label = name(x, y, depth)
        selected_font = None
        for size in range(12, 5, -1):
            candidate = ImageFont.load_default(size=size)
            if (
                candidate.getlength(label) <= rect[2] - rect[0] - 4
                and candidate.getbbox(label)[3] <= rect[3] - rect[1] - 4
            ):
                selected_font = candidate
                break
        if selected_font is None:
            raise AnnoError("Grid cells cannot fit readable coordinate labels; use a coarser grid or visual")
        draw.rectangle(rect, outline="#00ffff", width=1)
        draw.text(
            (rect[0] + 2, rect[1] + 2),
            label,
            fill="yellow",
            font=selected_font,
            stroke_width=1,
            stroke_fill="black",
        )
        labels.append(label)
    return labels


def grid(image, expression=None):
    if expression is None:
        result = image.copy()
        result.thumbnail((1024, 1024))
        labels = draw_cells(
            result,
            [(x, y, 1) for y in range(8) for x in range(8)],
            image.size,
            scale=(result.width / image.width, result.height / image.height),
        )
        return result, {"cell_labels": labels}
    parents = selected_cells(expression, limit=64)
    cells = [(x * 8 + i, y * 8 + j, d + 1) for x, y, d in parents for j in range(8) for i in range(8)]
    crop = cells_bounds(expression, *image.size)
    result = image.crop(crop)
    labels = draw_cells(result, cells, image.size, crop[:2])
    return result, {"cell_labels": labels, "crop": list(crop)}


def select(image, expression, margin):
    cells = selected_cells(expression)
    crop = crop_bounds(cells_bounds(expression, *image.size), image.size, margin)
    result = image.crop(crop)
    labels = draw_cells(result, cells, image.size, crop[:2])
    return result, {"cell_labels": labels, "crop": list(crop)}
