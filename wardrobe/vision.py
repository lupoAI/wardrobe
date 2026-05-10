from __future__ import annotations

import colorsys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageStat

COLOR_NAMES = [
    ("black", (20, 20, 20)), ("white", (240, 240, 240)), ("gray", (128, 128, 128)),
    ("red", (190, 40, 40)), ("burgundy", (120, 25, 70)), ("orange", (220, 120, 35)),
    ("yellow", (225, 205, 55)), ("green", (45, 140, 75)), ("blue", (55, 100, 190)),
    ("purple", (125, 70, 170)), ("pink", (220, 115, 160)), ("brown", (115, 75, 45)),
    ("beige", (200, 175, 135)),
]

def load_image(path: Path, size: int = 384) -> Image.Image:
    img = Image.open(path).convert("RGB")
    img = ImageOps.exif_transpose(img)
    img.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return canvas

def nearest_color_name(rgb: tuple[int, int, int]) -> str:
    arr = np.array(COLOR_NAMES, dtype=object)
    names = [x[0] for x in COLOR_NAMES]
    vals = np.array([x[1] for x in COLOR_NAMES], dtype=np.float32)
    dists = np.linalg.norm(vals - np.array(rgb, dtype=np.float32), axis=1)
    return names[int(np.argmin(dists))]

def dominant_colors(img: Image.Image, count: int = 3) -> list[str]:
    small = img.resize((128, 128))
    arr = np.asarray(small).astype(np.uint8)
    # Prefer likely garment pixels over bright bedding/walls. This is intentionally
    # simple: keep central, reasonably saturated/non-white pixels when possible.
    h, w, _ = arr.shape
    yy, xx = np.mgrid[:h, :w]
    central = (xx > w * 0.12) & (xx < w * 0.88) & (yy > h * 0.10) & (yy < h * 0.92)
    flat = arr.reshape(-1, 3)
    hsv = np.array([colorsys.rgb_to_hsv(*(px / 255.0)) for px in flat], dtype=np.float32).reshape(h, w, 3)
    saturated = hsv[:, :, 1] > 0.20
    not_bright_bg = hsv[:, :, 2] < 0.92
    mask = central & (saturated | not_bright_bg)
    if mask.sum() > 250:
        arr = arr[mask].reshape(-1, 1, 3)
        sample = Image.fromarray(arr.astype(np.uint8), "RGB").resize((96, 96))
    else:
        sample = small.resize((96, 96))
    # quantize produces stable practical color buckets without sklearn.
    q = sample.quantize(colors=8, method=Image.Quantize.MEDIANCUT).convert("RGB")
    colors = q.getcolors(maxcolors=96 * 96) or []
    colors.sort(reverse=True, key=lambda x: x[0])
    names = []
    for _, rgb in colors:
        name = nearest_color_name(rgb)
        if name not in names:
            names.append(name)
        if len(names) >= count:
            break
    return names

def visual_tags(img: Image.Image) -> list[str]:
    arr = np.asarray(img).astype(np.float32) / 255.0
    gray = np.mean(arr, axis=2)
    contrast = float(gray.std())
    # crude but useful texture/pattern hints
    dx = np.abs(np.diff(gray, axis=1)).mean()
    dy = np.abs(np.diff(gray, axis=0)).mean()
    tags = []
    if contrast < 0.12:
        tags.append("solid")
    elif max(dx, dy) > 0.08:
        tags.append("patterned")
    if dy > dx * 1.35:
        tags.append("vertical-detail")
    if dx > dy * 1.35:
        tags.append("horizontal-detail")
    return tags

def image_embedding(img: Image.Image) -> np.ndarray:
    """Deterministic local visual embedding: color histograms + texture statistics.

    This is not as semantically rich as CLIP, but it works offline today and is
    enough for similarity by color/texture. The interface can later be swapped
    for CLIP/OpenAI embeddings without changing the database shape.
    """
    arr = np.asarray(img).astype(np.float32) / 255.0
    feats = []
    # RGB histograms
    for c in range(3):
        hist, _ = np.histogram(arr[:, :, c], bins=32, range=(0, 1), density=True)
        feats.extend(hist.tolist())
    # HSV histograms
    flat = arr.reshape(-1, 3)
    hsv = np.array([colorsys.rgb_to_hsv(*px) for px in flat], dtype=np.float32)
    for c, bins in [(0, 36), (1, 16), (2, 16)]:
        hist, _ = np.histogram(hsv[:, c], bins=bins, range=(0, 1), density=True)
        feats.extend(hist.tolist())
    gray = arr.mean(axis=2)
    feats.extend([
        float(gray.mean()), float(gray.std()),
        float(np.abs(np.diff(gray, axis=1)).mean()),
        float(np.abs(np.diff(gray, axis=0)).mean()),
    ])
    vec = np.asarray(feats, dtype=np.float32)
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec
