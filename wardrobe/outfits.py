from __future__ import annotations

import itertools
import json
import sqlite3
import uuid
from datetime import datetime

from .catalog import items
from .db import connect, list_outfits, insert_outfit, insert_outfit_feedback

NEUTRALS = {
    "black", "white", "off-white", "cream", "beige", "stone", "gray", "grey", "charcoal",
    "navy", "dark navy", "blue-gray", "khaki", "taupe", "brown", "dark indigo", "indigo"
}
COOL = {"blue", "light blue", "navy", "dark navy", "green", "teal", "gray", "grey", "blue-gray", "indigo", "dark indigo"}
WARM = {"cream", "beige", "stone", "khaki", "taupe", "brown", "tan", "salmon pink", "pink", "burgundy", "maroon", "olive", "olive green"}
PATTERN_TAGS = {"striped", "vertical-stripes", "pinstripe", "plaid", "patterned", "graphic-patches", "geometric", "dotted-pattern"}
SMART_TAGS = {"shirt", "button-up", "collared", "blazer", "loafers", "dress", "chinos", "trousers"}
CASUAL_TAGS = {"hoodie", "sneakers", "jeans", "fleece", "cargo-trousers", "t-shirt", "tee", "shorts"}
LIGHT_TAGS = {"linen", "lightweight", "short-sleeve"}
WARM_TAGS = {"knit", "sweater", "fleece", "puffer-jacket", "down-jacket", "coat", "wool"}


def _norm_list(values: list[str] | None) -> set[str]:
    return {str(v).strip().lower() for v in values or [] if str(v).strip()}


def item_profile(item: dict) -> dict:
    tags = _norm_list(item.get("tags"))
    colors = _norm_list(item.get("colors"))
    text = " ".join([item.get("category") or "", item.get("subcategory") or "", item.get("notes") or "", " ".join(tags), " ".join(colors)]).lower()
    pattern_strength = "statement" if len(tags & PATTERN_TAGS) >= 2 or "graphic" in text else "subtle" if tags & PATTERN_TAGS else "solid"
    formality_score = len(tags & SMART_TAGS) - len(tags & CASUAL_TAGS)
    formality = "smart-casual" if formality_score >= 1 else "casual"
    if "blazer" in text or "dress trousers" in text:
        formality = "formal"
    weight = "light" if tags & LIGHT_TAGS else "warm" if tags & WARM_TAGS else "mid"
    return {"tags": tags, "colors": colors, "pattern_strength": pattern_strength, "formality": formality, "weight": weight}


def _color_temp(colors: set[str]) -> str:
    if colors and colors <= NEUTRALS:
        return "neutral"
    warm = bool(colors & WARM)
    cool = bool(colors & COOL)
    if warm and cool:
        return "mixed"
    if warm:
        return "warm"
    if cool:
        return "cool"
    return "neutral"


def score_outfit(parts: list[dict], occasion: str = "casual", weather: str = "mild", vibe: str = "balanced") -> tuple[int, list[str]]:
    profiles = [item_profile(p) for p in parts]
    tags = set().union(*(p["tags"] for p in profiles)) if profiles else set()
    colors = set().union(*(p["colors"] for p in profiles)) if profiles else set()
    patterns = [p for p in profiles if p["pattern_strength"] != "solid"]
    score = 50
    reasons: list[str] = []

    if len(parts) >= 2:
        score += 12
        reasons.append("complete base outfit")
    if any(i["category"] == "shoes" for i in parts):
        score += 7
        reasons.append("includes shoes")
    if any(i["category"] == "outerwear" for i in parts):
        if weather in {"cold", "rainy"}:
            score += 8
            reasons.append("outerwear fits weather")
        elif weather == "hot":
            score -= 7
            reasons.append("outerwear may be too warm")

    neutral_count = len(colors & NEUTRALS)
    color_temp = _color_temp(colors)
    if neutral_count >= max(1, len(colors) - 1):
        score += 14
        reasons.append("mostly neutral palette")
    elif color_temp in {"warm", "cool"}:
        score += 9
        reasons.append(f"cohesive {color_temp} colors")
    elif color_temp == "mixed":
        score -= 2
        reasons.append("mixed warm/cool palette")
    if len(colors) > 5:
        score -= 6
        reasons.append("many colors competing")

    if len(patterns) == 0:
        score += 7
        reasons.append("clean solid base")
    elif len(patterns) == 1:
        score += 10
        reasons.append("one pattern as focal point")
    else:
        score -= 10
        reasons.append("multiple patterns may clash")

    if occasion in {"work", "dinner", "date", "smart"}:
        smart = sum(1 for p in profiles if p["formality"] in {"smart-casual", "formal"})
        casual = sum(1 for p in profiles if p["formality"] == "casual")
        score += smart * 5 - casual * 2
        if smart:
            reasons.append("leans smart-casual")
    elif occasion in {"casual", "travel", "weekend"}:
        score += 3
        reasons.append("easy casual balance")

    if weather == "hot":
        light = sum(1 for p in profiles if p["weight"] == "light")
        warm = sum(1 for p in profiles if p["weight"] == "warm")
        score += light * 5 - warm * 8
        if light:
            reasons.append("light fabrics for heat")
    elif weather == "cold":
        warm = sum(1 for p in profiles if p["weight"] == "warm")
        score += warm * 6
        if warm:
            reasons.append("warm layers included")

    if vibe == "minimal" and len(patterns) == 0 and neutral_count >= 2:
        score += 8
        reasons.append("minimal neutral look")
    if vibe == "statement" and patterns:
        score += 6
        reasons.append("has a statement piece")

    return max(0, min(100, score)), reasons[:5]


def _parts_with_target(candidates: list[list[dict]], target_item: dict | None) -> list[list[dict]]:
    if not target_item:
        return candidates
    target_id = target_item["id"]
    if target_item["category"] in {"tops", "bottoms", "shoes", "outerwear"}:
        return [parts for parts in candidates if any(item["id"] == target_id for item in parts)]
    return [parts + [target_item] for parts in candidates if not any(item["id"] == target_id for item in parts)]


def suggest_outfits(
    occasion: str = "casual",
    weather: str = "mild",
    vibe: str = "balanced",
    limit: int = 12,
    item_id: str | None = None,
) -> list[dict]:
    rows = items()
    target_item = next((row for row in rows if row["id"] == item_id), None) if item_id else None
    if item_id and not target_item:
        raise ValueError(f"No item found with id {item_id}")

    tops = [i for i in rows if i["category"] == "tops"]
    bottoms = [i for i in rows if i["category"] == "bottoms"]
    shoes = [i for i in rows if i["category"] == "shoes"]
    outerwear = [i for i in rows if i["category"] == "outerwear"]

    if target_item:
        if target_item["category"] == "tops":
            tops = [target_item]
        elif target_item["category"] == "bottoms":
            bottoms = [target_item]
        elif target_item["category"] == "shoes":
            shoes = [target_item]
        elif target_item["category"] == "outerwear":
            outerwear = [target_item]

    candidates: list[list[dict]] = []
    for top, bottom in itertools.product(tops, bottoms):
        candidates.append([top, bottom])
        for shoe in shoes[:12]:
            candidates.append([top, bottom, shoe])
        if weather in {"cold", "rainy", "mild"} or (target_item and target_item["category"] == "outerwear"):
            for layer in outerwear[:10]:
                candidates.append([top, bottom, layer])
                for shoe in shoes[:8]:
                    candidates.append([top, bottom, layer, shoe])

    candidates = _parts_with_target(candidates, target_item)

    seen: set[tuple[str, ...]] = set()
    scored = []
    for parts in candidates:
        key = tuple(sorted(p["id"] for p in parts))
        if key in seen:
            continue
        seen.add(key)
        score, reasons = score_outfit(parts, occasion=occasion, weather=weather, vibe=vibe)
        scored.append({
            "id": "suggestion_" + "_".join(p["id"].replace("item_", "")[:4] for p in parts),
            "score": score,
            "reasons": reasons,
            "items": parts,
            "occasion": occasion,
            "weather": weather,
            "vibe": vibe,
            "remix_item_id": item_id,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

def saved_outfits() -> list[dict]:
    rows = items()
    by_id = {row["id"]: row for row in rows}
    out = []
    with connect() as con:
        for outfit in list_outfits(con):
            item_ids = outfit.pop("item_ids")
            outfit["items"] = [by_id[i] for i in item_ids if i in by_id]
            out.append(outfit)
    return out


def save_outfit(item_ids: list[str], name: str | None = None, occasion: str = "casual", weather: str = "mild", vibe: str = "balanced", notes: str | None = None) -> dict:
    rows = items()
    by_id = {row["id"]: row for row in rows}
    parts = [by_id[i] for i in item_ids if i in by_id]
    if len(parts) < 2:
        raise ValueError("Outfit needs at least two known items")
    score, reasons = score_outfit(parts, occasion=occasion, weather=weather, vibe=vibe)
    outfit = {
        "id": f"outfit_{uuid.uuid4().hex[:12]}",
        "name": name or _auto_name(parts),
        "occasion": occasion,
        "weather": weather,
        "vibe": vibe,
        "score": score,
        "reasons": reasons,
        "item_ids": [p["id"] for p in parts],
        "notes": notes,
    }
    with connect() as con:
        insert_outfit(con, outfit)
    return {**outfit, "items": parts}


def rate_outfit(outfit_id: str, rating: int, reason: str | None = None) -> dict:
    with connect() as con:
        insert_outfit_feedback(con, outfit_id, rating, reason)
    return {"ok": True, "outfit_id": outfit_id, "rating": rating, "reason": reason}


def _auto_name(parts: list[dict]) -> str:
    bits = []
    for item in parts[:3]:
        colors = item.get("colors") or []
        sub = item.get("subcategory") or item.get("category") or "piece"
        bits.append(" ".join([*(colors[:1]), sub]).strip())
    return " + ".join(bits).title()
