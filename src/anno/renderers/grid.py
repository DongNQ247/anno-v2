"""Render labels in the same global coordinate system used by bbox math."""

import math
from fractions import Fraction

from PIL import Image, ImageDraw, ImageFont

from ..core.coords import cells_bounds, name, selected_cells
from ..core.errors import AnnoError
from .visualizer import crop_bounds


def _local_render(image, expression, margin, scale, subdivide):
    if str(scale) not in ("auto", "1", "2", "3", "4"):
        raise AnnoError("--scale must be auto or an integer from 1 to 4")
    parents = selected_cells(expression)
    crop = crop_bounds(cells_bounds(expression, *image.size), image.size, margin)
    native_size = [crop[2] - crop[0], crop[3] - crop[1]]
    depth = max(d for _, _, d in parents) + 1
    subcell = [image.width / 8**depth, image.height / 8**depth]
    minimum = min(subcell)
    required = math.ceil(28 / minimum) if minimum else None
    details = {
        "native_crop_size": native_size,
        "native_subcell_size": subcell,
        "native_subcell_min_edge": minimum,
        "required_scale": required,
        "max_scale": 4,
        "parent_cell_count": len(parents),
        "subcell_count": len(parents) * 64,
        "recommended_max_parent_cells": 8,
        "suggested_cells": "select a smaller local edge region; use a coarser cell level if subcells are too small",
    }
    if subdivide and len(parents) > 8:
        raise AnnoError("Subgrid region is too broad; select a smaller local edge region", details=details)
    if scale == "auto" and (required is None or required > 4):
        raise AnnoError("Local cells need more than max_scale; use a coarser cell level", details=details)
    factor = max(1, required) if scale == "auto" else int(scale)
    cells = (
        [(x * 8 + i, y * 8 + j, d + 1) for x, y, d in parents for j in range(8) for i in range(8)]
        if subdivide
        else parents
    )
    result = image.crop(crop)
    if factor > 1:
        result = result.resize(tuple(edge * factor for edge in native_size), Image.Resampling.LANCZOS)
    try:
        labels, geometry = draw_cells(result, cells, image.size, crop[:2], (factor, factor))
    except AnnoError as exc:
        raise AnnoError(str(exc), details=details) from exc
    metadata = {
        "cell_labels": labels,
        "cells": geometry,
        "crop": list(crop),
        "native_crop_size": native_size,
        "scale": factor,
        "render_size": list(result.size),
        "readable_labels": True,
    }
    if subdivide:
        metadata.update(
            subcell_size=[edge * factor for edge in subcell],
            parent_cell_count=len(parents),
            subcell_count=len(cells),
            recommended_max_parent_cells=8,
        )
    return result, metadata


def _find_font(text, max_w, max_h):
    for size in range(12, 5, -1):
        candidate = ImageFont.load_default(size=size)
        if candidate.getlength(text) <= max_w and candidate.getbbox(text)[3] <= max_h:
            return candidate
    return None


def draw_cells(image, cells, original_size, origin=(0, 0), scale=(1, 1)):
    draw = ImageDraw.Draw(image)
    width, height = original_size
    labels = []
    cell_geometry = []

    layout = []
    can_fit_full = True
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
        labels.append(label)
        cell_geometry.append(
            {
                "id": label,
                "xyxy": [math.floor(x1), math.floor(y1), math.ceil(x2), math.ceil(y2)],
            }
        )

        font = _find_font(label, rect[2] - rect[0] - 4, rect[3] - rect[1] - 4)
        if font is None:
            can_fit_full = False
        layout.append((x, y, depth, rect, label, font))

    if can_fit_full:
        for x, y, depth, rect, label, font in layout:
            draw.rectangle(rect, outline="#00ffff", width=1)
            draw.text(
                (rect[0] + 2, rect[1] + 2),
                label,
                fill="yellow",
                font=font,
                stroke_width=1,
                stroke_fill="black",
            )
        return labels, cell_geometry

    min_x = min(c[0] for c in cells)
    min_y = min(c[1] for c in cells)

    for x, y, depth, rect, label, _ in layout:
        draw.rectangle(rect, outline="#00ffff", width=1)
        max_w = rect[2] - rect[0] - 4
        max_h = rect[3] - rect[1] - 4
        parts = label.split("-")

        is_top = y == min_y
        is_left = x == min_x

        if not (is_top or is_left):
            continue

        col_full = f"{parts[0][0]}{parts[-1][0]}" if (x % 8 == 0 and len(parts) > 1) else parts[-1][0]
        col_short = parts[-1][0]
        row_full = f"{parts[0][1]}{parts[-1][1]}" if (y % 8 == 0 and len(parts) > 1) else parts[-1][1]
        row_short = parts[-1][1]

        if is_top and is_left:
            combo = f"{col_short}/{row_short}"
            combo_font = _find_font(combo, max_w, max_h)
            if combo_font:
                draw.text(
                    (rect[0] + 2, rect[1] + 2),
                    combo,
                    fill="yellow",
                    font=combo_font,
                    stroke_width=1,
                    stroke_fill="black",
                )
            else:
                col_font = _find_font(col_short, max_w, max_h)
                row_font = _find_font(row_short, max_w, max_h)
                if col_font is None or row_font is None:
                    raise AnnoError(
                        "Grid cells cannot fit readable coordinate labels; use a coarser grid or visual"
                    )
                draw.text(
                    (rect[0] + 2, rect[1] + 2),
                    col_short,
                    fill="yellow",
                    font=col_font,
                    stroke_width=1,
                    stroke_fill="black",
                )
                rw = row_font.getlength(row_short)
                draw.text(
                    (max(rect[0] + 2, rect[2] - rw - 2), rect[1] + 2),
                    row_short,
                    fill="yellow",
                    font=row_font,
                    stroke_width=1,
                    stroke_fill="black",
                )
        elif is_top:
            font = _find_font(col_full, max_w, max_h)
            text = col_full
            if font is None:
                font = _find_font(col_short, max_w, max_h)
                text = col_short
            if font is None:
                raise AnnoError(
                    "Grid cells cannot fit readable coordinate labels; use a coarser grid or visual"
                )
            draw.text(
                (rect[0] + 2, rect[1] + 2),
                text,
                fill="yellow",
                font=font,
                stroke_width=1,
                stroke_fill="black",
            )
        elif is_left:
            font = _find_font(row_full, max_w, max_h)
            text = row_full
            if font is None:
                font = _find_font(row_short, max_w, max_h)
                text = row_short
            if font is None:
                raise AnnoError(
                    "Grid cells cannot fit readable coordinate labels; use a coarser grid or visual"
                )
            draw.text(
                (rect[0] + 2, rect[1] + 2),
                text,
                fill="yellow",
                font=font,
                stroke_width=1,
                stroke_fill="black",
            )

    return labels, cell_geometry


def grid(image, expression=None, scale="auto"):
    if expression is None:
        if scale != "auto":
            raise AnnoError("--scale requires --cells for label grid")
        result = image.copy()
        result.thumbnail((1024, 1024))
        labels, cells_geo = draw_cells(
            result,
            [(x, y, 1) for y in range(8) for x in range(8)],
            image.size,
            scale=(result.width / image.width, result.height / image.height),
        )
        return result, {"cell_labels": labels, "cells": cells_geo}
    return _local_render(image, expression, 0, scale, True)


def select(image, expression, margin, scale="auto"):
    return _local_render(image, expression, margin, scale, False)
