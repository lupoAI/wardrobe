from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageStat

from .catalog import items
from .config import EMBEDDING_DIR, THUMBNAIL_DIR, THUMBNAIL_META_DIR
from .vision import image_embedding, load_image

DESCRIBE_PROMPT = (
    "Briefly describe this clothing item for a game thumbnail prompt. "
    "Focus on garment type, color, silhouette, material texture, and distinctive visible details. "
    "One concise sentence."
)

MODEL = "google/gemini-3.1-flash-image-preview"


def build_thumbnail_prompt(description: str, item_type: str = "item") -> str:
    return f"""Using the reference garment, create a clean standalone game inventory thumbnail asset of the same {item_type}.

Garment requirements: {description} Preserve the real reference garment's color, material, proportions, neckline/waist/opening shape, sleeve/leg/strap shape, hem/sole/edge details, texture, and any distinctive construction details visible in the photo.

Composition: ONLY the item, front-facing or at the clearest catalog angle for this item type, centered, floating neatly like a character-dressing closet item icon. No human, mannequin, hanger, labels, logos, text, buttons/zippers/patterns unless they are actually present in the reference, extra clothes, accessories, border, frame, card, checkerboard, UI elements, or decorative background.

Style: high-quality stylized-realistic fashion game asset, crisp readable silhouette at small size, soft studio lighting, gentle shadow/ambient occlusion. Background should be plain transparent if possible; otherwise plain warm off-white with no border or pattern."""


def _run_json(cmd: list[str], timeout: int) -> dict:
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Expected JSON from command: {' '.join(cmd)}\n{proc.stdout}") from e


def describe_item(image_path: str | Path, timeout: int = 90) -> str:
    data = _run_json(
        [
            "openclaw",
            "infer",
            "image",
            "describe",
            "--file",
            str(image_path),
            "--prompt",
            DESCRIBE_PROMPT,
            "--json",
            "--timeout-ms",
            str(timeout * 1000),
        ],
        timeout=timeout + 10,
    )
    outputs = data.get("outputs") or []
    if not outputs or not outputs[0].get("text"):
        raise RuntimeError(f"No description returned for {image_path}: {data}")
    return outputs[0]["text"].strip()


def ensure_embedding(item: dict, force: bool = False) -> str:
    emb_path = Path(item["embedding_path"])
    if emb_path.exists() and not force:
        return str(emb_path)
    emb_path.parent.mkdir(parents=True, exist_ok=True)
    img = load_image(Path(item["image_path"]))
    np.save(emb_path, image_embedding(img))
    return str(emb_path)


def infer_item_type(item: dict) -> str:
    sub = item.get("subcategory")
    tags = item.get("tags") or []
    if sub:
        return sub
    for tag in tags:
        if isinstance(tag, str) and tag not in {"solid", "striped", "lightweight", "textured-fabric"}:
            return tag.replace("-", " ")
    return item.get("category") or "item"


def thumbnail_path_for(item_id: str) -> Path:
    return THUMBNAIL_DIR / f"{item_id}.png"


def legacy_thumbnail_path_for(item_id: str) -> Path:
    return THUMBNAIL_DIR / f"{item_id}.jpg"


def metadata_path_for(item_id: str) -> Path:
    return THUMBNAIL_META_DIR / f"{item_id}.json"



def remove_plain_background(src: str | Path, dest: str | Path, *, size: int = 1024) -> dict:
    """Remove a mostly plain generated thumbnail background and save RGBA PNG.

    The Gemini image model currently ignores transparent-background hints for this
    route, but our prompt asks for a plain warm off-white background. This uses a
    conservative edge-connected background mask so similarly colored details inside
    the garment are not removed unless connected to the image edge.
    """
    target_size = size
    img = Image.open(src).convert("RGB")
    w, h = img.size
    px = img.load()

    sample_points = []
    band = max(4, min(w, h) // 24)
    for x in range(w):
        for y in list(range(band)) + list(range(h - band, h)):
            sample_points.append(px[x, y])
    for y in range(h):
        for x in list(range(band)) + list(range(w - band, w)):
            sample_points.append(px[x, y])

    # Median-ish background color from border pixels.
    channels = list(zip(*sample_points))
    bg = tuple(int(sorted(c)[len(c) // 2]) for c in channels)

    def dist(c):
        return sum((int(c[i]) - bg[i]) ** 2 for i in range(3)) ** 0.5

    border_dists = sorted(dist(c) for c in sample_points)
    # Adaptive but conservative threshold; generated backgrounds are usually flat.
    threshold = max(28, min(72, border_dists[int(len(border_dists) * 0.85)] + 12))

    visited = bytearray(w * h)
    bgmask = bytearray(w * h)
    stack = []
    for x in range(w):
        stack.append((x, 0)); stack.append((x, h - 1))
    for y in range(h):
        stack.append((0, y)); stack.append((w - 1, y))

    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        idx = y * w + x
        if visited[idx]:
            continue
        visited[idx] = 1
        if dist(px[x, y]) > threshold:
            continue
        bgmask[idx] = 255
        stack.append((x + 1, y)); stack.append((x - 1, y)); stack.append((x, y + 1)); stack.append((x, y - 1))

    mask = Image.frombytes("L", (w, h), bytes(bgmask))
    # Grow then feather the removed area slightly to avoid halos.
    mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    alpha = ImageChops.invert(mask)

    rgba = img.convert("RGBA")
    rgba.putalpha(alpha)

    # Crop to visible object with padding, then paste into square transparent canvas.
    bbox = alpha.point(lambda a: 255 if a > 12 else 0).getbbox()
    if bbox:
        pad = int(min(w, h) * 0.06)
        left = max(0, bbox[0] - pad); top = max(0, bbox[1] - pad)
        right = min(w, bbox[2] + pad); bottom = min(h, bbox[3] + pad)
        rgba = rgba.crop((left, top, right, bottom))
    canvas_size = max(rgba.size)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
    canvas.alpha_composite(rgba, ((canvas_size - rgba.width) // 2, (canvas_size - rgba.height) // 2))
    rgba = canvas.resize((target_size, target_size), Image.Resampling.LANCZOS)

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    rgba.save(dest, "PNG")
    alpha_stat = ImageStat.Stat(rgba.getchannel("A"))
    transparent_ratio = 1.0 - (alpha_stat.mean[0] / 255.0)
    return {
        "source_path": str(src),
        "output_path": str(dest),
        "source_size": [w, h],
        "output_size": list(rgba.size),
        "background_color": list(bg),
        "threshold": round(float(threshold), 2),
        "transparent_ratio": round(float(transparent_ratio), 4),
        "bbox": list(bbox) if bbox else None,
    }


def _read_metadata(item_id: str) -> dict:
    path = metadata_path_for(item_id)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def thumbnail_status(item: dict) -> dict:
    """Return thumbnail/cutout availability without making model calls."""
    item_id = item["id"]
    png = thumbnail_path_for(item_id)
    legacy = legacy_thumbnail_path_for(item_id)
    raw = THUMBNAIL_META_DIR / f"{item_id}.raw.jpg"
    meta = _read_metadata(item_id)
    if png.is_file():
        state = "clean"
        thumbnail_path = str(png)
    elif legacy.is_file():
        state = "legacy-jpg"
        thumbnail_path = str(legacy)
    else:
        state = "missing"
        thumbnail_path = None
    return {
        "id": item_id,
        "state": state,
        "has_clean_thumbnail": png.is_file(),
        "has_legacy_thumbnail": legacy.is_file(),
        "has_raw_thumbnail": raw.is_file(),
        "thumbnail_path": thumbnail_path,
        "metadata_path": str(metadata_path_for(item_id)) if metadata_path_for(item_id).is_file() else None,
        "background_removed": bool(meta.get("background_removed")) if meta else png.is_file(),
        "format": meta.get("format") or ("png" if png.is_file() else "jpg" if legacy.is_file() else None),
        "generated_at": meta.get("generated_at"),
        "cleaned_at": meta.get("cleaned_at"),
        "source_path": meta.get("source_path") or meta.get("raw_thumbnail_path") or meta.get("legacy_thumbnail_path"),
    }


def _best_clean_source(item: dict) -> Path:
    item_id = item["id"]
    candidates = [
        THUMBNAIL_META_DIR / f"{item_id}.raw.jpg",
        legacy_thumbnail_path_for(item_id),
        Path(item["image_path"]),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No source image found for {item_id}")


def clean_thumbnail(item: dict, *, source: str | Path | None = None, force: bool = False, size: int = 1024) -> dict:
    """Create/refresh a transparent PNG cutout from an existing image source.

    This is intentionally model-free: it reuses the generated raw thumbnail when
    available, falls back to legacy JPG thumbnails, and finally tries the original
    catalog photo. It is useful for repairing old assets or building clean
    thumbnails in environments where image generation is unavailable.
    """
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_META_DIR.mkdir(parents=True, exist_ok=True)
    item_id = item["id"]
    out = thumbnail_path_for(item_id)
    meta_out = metadata_path_for(item_id)
    if out.exists() and not force:
        return {**thumbnail_status(item), "skipped": True, "reason": "clean_thumbnail_exists"}

    src = Path(source) if source is not None else _best_clean_source(item)
    cleanup = remove_plain_background(src, out, size=size)
    meta = _read_metadata(item_id)
    meta.update(
        {
            "id": item_id,
            "category": item.get("category"),
            "subcategory": item.get("subcategory"),
            "image_path": str(item.get("image_path")),
            "thumbnail_path": str(out),
            "source_path": str(src),
            "background_removed": True,
            "format": "png",
            "cleaned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cleanup": cleanup,
        }
    )
    meta_out.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return {**meta, "skipped": False}


def generate_thumbnail(item: dict, *, force: bool = False, timeout: int = 180) -> dict:
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_META_DIR.mkdir(parents=True, exist_ok=True)

    item_id = item["id"]
    src = Path(item["image_path"])
    out = thumbnail_path_for(item_id)
    legacy_out = legacy_thumbnail_path_for(item_id)
    raw_out = THUMBNAIL_META_DIR / f"{item_id}.raw.jpg"
    meta_out = metadata_path_for(item_id)

    embedding_path = ensure_embedding(item)
    if out.exists() and meta_out.exists() and not force:
        meta = json.loads(meta_out.read_text())
        return {**meta, "skipped": True, "reason": "thumbnail_exists"}
    if legacy_out.exists() and not out.exists() and not force:
        remove_plain_background(legacy_out, out)
        if meta_out.exists():
            meta = json.loads(meta_out.read_text())
        else:
            meta = {"id": item_id, "image_path": str(src), "embedding_path": embedding_path}
        meta.update({"thumbnail_path": str(out), "legacy_thumbnail_path": str(legacy_out), "background_removed": True, "format": "png"})
        meta_out.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        return {**meta, "skipped": True, "reason": "converted_legacy_jpg"}

    description = describe_item(src)
    item_type = infer_item_type(item)
    prompt = build_thumbnail_prompt(description, item_type=item_type)

    started = time.time()
    data = _run_json(
        [
            "openclaw",
            "infer",
            "image",
            "edit",
            "--file",
            str(src),
            "--prompt",
            prompt,
            "--model",
            MODEL,
            "--aspect-ratio",
            "1:1",
            "--resolution",
            "1K",
            "--output",
            str(raw_out),
            "--json",
            "--timeout-ms",
            str(timeout * 1000),
        ],
        timeout=timeout + 30,
    )
    elapsed = round(time.time() - started, 2)
    outputs = data.get("outputs") or []
    generated_path = Path(outputs[0].get("path", raw_out)) if outputs else raw_out
    if not outputs or not generated_path.exists():
        raise RuntimeError(f"No thumbnail output for {item_id}: {data}")
    remove_plain_background(generated_path, out)

    meta = {
        "id": item_id,
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "image_path": str(src),
        "embedding_path": embedding_path,
        "thumbnail_path": str(out),
        "description": description,
        "prompt": prompt,
        "model": MODEL,
        "elapsed_seconds": elapsed,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_thumbnail_path": str(generated_path),
        "background_removed": True,
        "format": "png",
        "provider_output": outputs[0],
    }
    meta_out.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return meta


def thumbnail_statuses(*, category: str | None = None, limit: int | None = None) -> list[dict]:
    rows = items(category)
    if limit is not None:
        rows = rows[:limit]
    return [thumbnail_status(item) for item in rows]


def clean_all_thumbnails(*, category: str | None = None, limit: int | None = None, force: bool = False, size: int = 1024) -> list[dict]:
    THUMBNAIL_META_DIR.mkdir(parents=True, exist_ok=True)
    rows = items(category)
    if limit is not None:
        rows = rows[:limit]
    results = []
    for idx, item in enumerate(rows, start=1):
        try:
            result = clean_thumbnail(item, force=force, size=size)
            status = "skipped" if result.get("skipped") else "cleaned"
            print(json.dumps({"index": idx, "total": len(rows), "id": item["id"], "status": status, "thumbnail_path": result.get("thumbnail_path")}), flush=True)
            results.append(result)
        except Exception as e:
            err = {"id": item.get("id"), "error": str(e), "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            print(json.dumps({"index": idx, "total": len(rows), "id": item.get("id"), "status": "error", "error": str(e)}), flush=True)
            (THUMBNAIL_META_DIR / f"{item.get('id', 'unknown')}.error.json").write_text(json.dumps(err, indent=2))
            results.append(err)
    manifest = THUMBNAIL_META_DIR / "clean-manifest.json"
    manifest.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    return results


def generate_all_thumbnails(*, category: str | None = None, limit: int | None = None, force: bool = False) -> list[dict]:
    THUMBNAIL_META_DIR.mkdir(parents=True, exist_ok=True)
    rows = items(category)
    if limit is not None:
        rows = rows[:limit]
    results = []
    for idx, item in enumerate(rows, start=1):
        try:
            result = generate_thumbnail(item, force=force)
            status = "skipped" if result.get("skipped") else "generated"
            print(json.dumps({"index": idx, "total": len(rows), "id": item["id"], "status": status, "thumbnail_path": result.get("thumbnail_path")}), flush=True)
            results.append(result)
        except Exception as e:
            err = {"id": item.get("id"), "error": str(e), "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            print(json.dumps({"index": idx, "total": len(rows), "id": item.get("id"), "status": "error", "error": str(e)}), flush=True)
            (THUMBNAIL_META_DIR / f"{item.get('id', 'unknown')}.error.json").write_text(json.dumps(err, indent=2))
            results.append(err)
    manifest = THUMBNAIL_META_DIR / "manifest.json"
    manifest.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    return results
