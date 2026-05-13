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


def suggest_outfits(occasion: str = "casual", weather: str = "mild", vibe: str = "balanced", limit: int = 12) -> list[dict]:
    rows = items()
    tops = [i for i in rows if i["category"] == "tops"]
    bottoms = [i for i in rows if i["category"] == "bottoms"]
    shoes = [i for i in rows if i["category"] == "shoes"]
    outerwear = [i for i in rows if i["category"] == "outerwear"]

    candidates: list[list[dict]] = []
    for top, bottom in itertools.product(tops, bottoms):
        candidates.append([top, bottom])
        for shoe in shoes[:12]:
            candidates.append([top, bottom, shoe])
        if weather in {"cold", "rainy", "mild"}:
            for layer in outerwear[:10]:
                candidates.append([top, bottom, layer])
                for shoe in shoes[:8]:
                    candidates.append([top, bottom, layer, shoe])

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
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def _weather_from_context(weather: str = "mild", location: str = "") -> str:
    requested = str(weather or "").strip().lower()
    if requested in {"hot", "cold", "rainy", "mild"}:
        return requested
    text = f"{requested} {location}".lower()
    if any(word in text for word in ["rain", "wet", "storm", "drizzle", "seattle", "london"]):
        return "rainy"
    if any(word in text for word in ["hot", "warm", "summer", "beach", "desert", "miami", "dubai", "la ", "los angeles"]):
        return "hot"
    if any(word in text for word in ["cold", "cool", "winter", "snow", "ski", "iceland", "oslo", "nyc winter"]):
        return "cold"
    return "mild"


def _style_context(style: str = "balanced", constraints: list[str] | None = None) -> tuple[str, str, set[str]]:
    text = " ".join([style or "", *(constraints or [])]).lower()
    vibe = "minimal" if "minimal" in text or "neutral" in text else "statement" if "statement" in text or "bold" in text else "balanced"
    occasion = "work" if any(w in text for w in ["work", "business", "office", "conference"]) else "dinner" if "dinner" in text else "travel"
    ignored = {"minimal", "neutral", "statement", "bold", "balanced", "travel", "capsule", "outfit", "style", "work", "business", "office", "conference", "dinner"}
    terms = {w.strip(" ,.;:/") for w in text.replace("-", " ").split() if len(w.strip(" ,.;:/")) >= 3 and w.strip(" ,.;:/") not in ignored}
    return occasion, vibe, terms


def _item_text(item: dict) -> str:
    return " ".join([
        item.get("id", ""), item.get("category", ""), item.get("subcategory", ""), item.get("notes", ""),
        " ".join(item.get("tags") or []), " ".join(item.get("colors") or []),
    ]).lower()


def _travel_item_score(item: dict, weather: str, style_terms: set[str]) -> int:
    profile = item_profile(item)
    tags = profile["tags"]
    text = _item_text(item)
    score = 0
    if profile["colors"] & NEUTRALS:
        score += 4
    if profile["pattern_strength"] == "solid":
        score += 3
    if weather == "hot" and profile["weight"] == "light":
        score += 8
    if weather == "hot" and profile["weight"] == "warm":
        score -= 10
    if weather == "cold" and profile["weight"] == "warm":
        score += 8
    if weather == "rainy" and any(w in text for w in ["rain", "waterproof", "coat", "jacket", "boots"]):
        score += 7
    if tags & {"linen", "lightweight", "sneakers", "chinos", "jeans", "shirt", "t-shirt", "tee"}:
        score += 2
    score += sum(5 for term in style_terms if term in text)
    return score


def _capsule_targets(days: int, weather: str, available: dict[str, list[dict]]) -> dict[str, int]:
    targets = {
        "tops": min(len(available.get("tops", [])), max(1, min(days, 5))),
        "bottoms": min(len(available.get("bottoms", [])), max(1, min(3, (days + 1) // 2))),
        "shoes": min(len(available.get("shoes", [])), 2 if days >= 4 else 1),
        "outerwear": 0,
        "accessories": min(len(available.get("accessories", [])), 2 if days >= 5 else 1),
    }
    if weather in {"cold", "rainy"}:
        targets["outerwear"] = min(len(available.get("outerwear", [])), 2 if days >= 5 else 1)
    elif weather == "mild":
        targets["outerwear"] = min(len(available.get("outerwear", [])), 1)
    return targets


def _rank_items_for_capsule(rows: list[dict], weather: str, style_terms: set[str], top_outfits: list[dict]) -> dict[str, list[dict]]:
    outfit_weight: dict[str, int] = {}
    for rank, outfit in enumerate(top_outfits[:80]):
        weight = max(1, 80 - rank) + int(outfit.get("score", 0))
        for item in outfit.get("items", []):
            outfit_weight[item["id"]] = outfit_weight.get(item["id"], 0) + weight
    ranked: dict[str, list[dict]] = {}
    for item in rows:
        score = outfit_weight.get(item["id"], 0) + _travel_item_score(item, weather, style_terms)
        ranked.setdefault(item["category"], []).append({**item, "capsule_score": score})
    for cat in ranked:
        ranked[cat].sort(key=lambda i: (-i["capsule_score"], i.get("category", ""), i.get("subcategory") or "", i["id"]))
    return ranked


def generate_capsule(
    trip_duration: int | str = 3,
    location: str = "",
    weather: str = "mild",
    style: str = "balanced",
    constraints: list[str] | None = None,
    limit: int | str | None = None,
) -> dict:
    """Build a deterministic travel capsule and day-by-day outfit plan from catalog data."""
    days = max(1, min(30, int(trip_duration or 3)))
    requested_days = max(1, min(days, int(limit or days)))
    norm_weather = _weather_from_context(weather, location)
    occasion, vibe, style_terms = _style_context(style, constraints)
    rows = items()
    available: dict[str, list[dict]] = {}
    for row in rows:
        available.setdefault(row["category"], []).append(row)

    suggestions = suggest_outfits(occasion=occasion, weather=norm_weather, vibe=vibe, limit=240)
    ranked = _rank_items_for_capsule(rows, norm_weather, style_terms, suggestions)
    targets = _capsule_targets(days, norm_weather, available)
    capsule_items: list[dict] = []
    for category in ["tops", "bottoms", "shoes", "outerwear", "accessories"]:
        capsule_items.extend(ranked.get(category, [])[:targets.get(category, 0)])
    capsule_ids = {item["id"] for item in capsule_items}

    day_candidates = [
        outfit for outfit in suggestions
        if outfit.get("items") and {item["id"] for item in outfit["items"]} <= capsule_ids
        and any(item["category"] == "tops" for item in outfit["items"])
        and any(item["category"] == "bottoms" for item in outfit["items"])
    ]
    if not day_candidates:
        day_candidates = suggestions[:]

    daily: list[dict] = []
    used_keys: set[tuple[str, ...]] = set()
    for day in range(1, requested_days + 1):
        pool = [o for o in day_candidates if tuple(sorted(i["id"] for i in o["items"])) not in used_keys] or day_candidates or suggestions
        chosen = pool[(day - 1) % len(pool)] if pool else None
        if not chosen:
            break
        key = tuple(sorted(i["id"] for i in chosen["items"]))
        used_keys.add(key)
        daily.append({
            **chosen,
            "id": f"capsule_day_{day}",
            "day": day,
            "name": f"Day {day}: {_auto_name(chosen['items'])}",
        })

    notes = [
        f"{len(capsule_items)} pieces for {days} day{'s' if days != 1 else ''}",
        f"Weather profile: {norm_weather}",
        f"Style profile: {style or 'balanced'}",
    ]
    if targets.get("outerwear"):
        notes.append("Includes a layer for changing weather")
    if days >= 4:
        notes.append("Designed for rewearing tops/bottoms across multiple combinations")

    return {
        "trip": {
            "duration_days": days,
            "location": location,
            "weather": norm_weather,
            "requested_weather": weather,
            "style": style,
            "constraints": constraints or [],
        },
        "packing_notes": notes,
        "capsule_items": capsule_items,
        "daily_outfits": daily,
        "counts": {
            "pieces": len(capsule_items),
            "daily_outfits": len(daily),
            "categories": {cat: sum(1 for item in capsule_items if item["category"] == cat) for cat in sorted(targets)},
        },
    }


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
