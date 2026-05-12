from __future__ import annotations

import shutil
import uuid
from pathlib import Path
import numpy as np
from .config import IMAGE_DIR, EMBEDDING_DIR, CATEGORIES
from .db import connect, insert_item, list_items, update_item_metadata
from .vision import load_image, dominant_colors, visual_tags, image_embedding

def infer_category(filename: str, user_category: str | None = None) -> tuple[str, str | None]:
    if user_category:
        user_category = user_category.lower().strip()
        if user_category in CATEGORIES:
            return user_category, None
        for cat, subs in CATEGORIES.items():
            if user_category in subs:
                return cat, user_category
        return user_category, None
    lower = filename.lower()
    for cat, subs in CATEGORIES.items():
        for sub in subs:
            if sub in lower:
                return cat, sub
    return "unknown", None

def add_item(image_path: str | Path, category: str | None = None, notes: str | None = None) -> dict:
    src = Path(image_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    img = load_image(src)
    cat, subcat = infer_category(src.name, category)
    item_id = f"item_{uuid.uuid4().hex[:12]}"
    dest_dir = IMAGE_DIR / cat
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower() or ".jpg"
    dest = dest_dir / f"{item_id}{ext}"
    shutil.copy2(src, dest)

    emb = image_embedding(img)
    emb_path = EMBEDDING_DIR / f"{item_id}.npy"
    np.save(emb_path, emb)

    item = {
        "id": item_id,
        "original_filename": src.name,
        "image_path": str(dest),
        "embedding_path": str(emb_path),
        "category": cat,
        "subcategory": subcat,
        "colors": dominant_colors(img),
        "tags": visual_tags(img),
        "notes": notes,
    }
    with connect() as con:
        insert_item(con, item)
    return item

def items(category: str | None = None) -> list[dict]:
    with connect() as con:
        return list_items(con, category)


def update_item(item_id: str, **changes) -> dict:
    with connect() as con:
        return update_item_metadata(con, item_id, changes)

def similar(image_path: str | Path | None = None, item_id: str | None = None, limit: int = 5) -> list[dict]:
    rows = items()
    if not rows:
        return []
    if item_id:
        base = next((r for r in rows if r["id"] == item_id), None)
        if not base:
            raise ValueError(f"No item found with id {item_id}")
        query = np.load(base["embedding_path"])
        exclude = item_id
    elif image_path:
        query = image_embedding(load_image(Path(image_path).expanduser().resolve()))
        exclude = None
    else:
        raise ValueError("Provide image_path or item_id")
    scored = []
    for r in rows:
        if r["id"] == exclude:
            continue
        vec = np.load(r["embedding_path"])
        score = float(np.dot(query, vec) / ((np.linalg.norm(query) * np.linalg.norm(vec)) or 1.0))
        scored.append({**r, "score": score})
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:limit]
