"""Exact hierarchical 8x8 coordinates, independent of rendering."""

import math
import re
from fractions import Fraction

from .errors import AnnoError

CELL = re.compile(r"([A-Ha-h])([1-8])\Z")


def point(text):
    parts = text.strip().split("-")
    x = y = 0
    for depth, part in enumerate(parts):
        match = CELL.fullmatch(part)
        if not match or (depth == 0) != part[0].isupper():
            raise AnnoError(f"Invalid cell: {text}; use A1..H8 then lowercase subcells")
        x = x * 8 + ord(part[0].upper()) - ord("A")
        y = y * 8 + int(part[1]) - 1
    return x, y, len(parts)


def name(x, y, depth):
    parts = []
    for level in range(depth):
        divisor = 8 ** (depth - level - 1)
        parts.append(f"{chr((65 if level == 0 else 97) + x // divisor % 8)}{y // divisor % 8 + 1}")
    return "-".join(parts)


def ranges(expression):
    if not isinstance(expression, str) or not expression.strip():
        raise AnnoError("--cells cannot be empty")
    result = []
    for item in expression.split(","):
        ends = item.strip().split(":")
        if len(ends) not in (1, 2):
            raise AnnoError(f"Invalid cell range: {item}")
        x, y, depth = point(ends[0])
        X, Y, end_depth = point(ends[-1])
        if depth != end_depth or X < x or Y < y:
            raise AnnoError("Range endpoints must have equal depth and run from top-left to bottom-right")
        result.append((x, y, X + 1, Y + 1, depth))
    return result


def cells_bounds(expression, width, height):
    rectangles = ranges(expression)
    x1 = min(Fraction(x, 8**d) for x, y, X, Y, d in rectangles)
    y1 = min(Fraction(y, 8**d) for x, y, X, Y, d in rectangles)
    x2 = max(Fraction(X, 8**d) for x, y, X, Y, d in rectangles)
    y2 = max(Fraction(Y, 8**d) for x, y, X, Y, d in rectangles)
    return math.floor(x1 * width), math.floor(y1 * height), math.ceil(x2 * width), math.ceil(y2 * height)


def selected_cells(expression, limit=4096):
    """Enumerate only for render; bbox math has no enumeration/depth limit."""
    rectangles = ranges(expression)
    if sum((X - x) * (Y - y) for x, y, X, Y, d in rectangles) > limit:
        raise AnnoError(f"Render selection exceeds {limit} cells; select a smaller region")
    return sorted({(x, y, d) for a, b, A, B, d in rectangles for y in range(b, B) for x in range(a, A)})
