import math
from collections import Counter

from PIL import ImageDraw, ImageFont

from ..core.errors import AnnoError


def font():
    # Pillow's bundled scalable font avoids host-font dependencies.
    return ImageFont.load_default(size=12)


def crop_bounds(box, size, margin):
    x1, y1, x2, y2 = box
    width, height = size
    dx, dy = (x2 - x1) * margin, (y2 - y1) * margin
    # Clamp before integer conversion, including very large finite margins.
    crop = (
        math.floor(max(0, x1 - dx)),
        math.floor(max(0, y1 - dy)),
        math.ceil(min(width, x2 + dx)),
        math.ceil(min(height, y2 + dy)),
    )
    if crop[2] <= crop[0] or crop[3] <= crop[1]:
        raise AnnoError("Box has no visible intersection with the image")
    return crop


def preview(image, box, margin):
    crop = crop_bounds(box, image.size, margin)
    result = image.crop(crop)
    x1, y1, x2, y2 = box
    ImageDraw.Draw(result).rectangle(
        (x1 - crop[0], y1 - crop[1], x2 - crop[0], y2 - crop[1]), outline="red", width=2
    )
    return result, crop


def overview(image, boxes, mapping, max_size=1024):
    width, height = image.size
    result = image.copy()
    result.thumbnail((max_size, max_size))
    draw = ImageDraw.Draw(result)
    for box in boxes:
        x1, y1, x2, y2 = box["xyxy"]
        rect = (
            x1 * result.width / width,
            y1 * result.height / height,
            x2 * result.width / width,
            y2 * result.height / height,
        )
        draw.rectangle(rect, outline="red", width=2)
        draw.text(
            (max(0, rect[0]), max(0, rect[1])),
            f"#{box['index']} {mapping[box['class_id']]}",
            fill="yellow",
            stroke_width=1,
            stroke_fill="black",
            font=font(),
        )
    counts = dict(Counter(f"{b['class_id']} ({mapping[b['class_id']]})" for b in boxes))
    return result, counts
