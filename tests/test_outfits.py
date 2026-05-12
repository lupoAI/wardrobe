"""Tests for wardrobe.outfits pure functions (no DB, no real catalog)."""
from __future__ import annotations

import pytest

from wardrobe.outfits import (
    _auto_name,
    _color_temp,
    item_profile,
    score_outfit,
)


def _item(
    category: str = "tops",
    tags: list[str] | None = None,
    colors: list[str] | None = None,
    subcategory: str | None = None,
    notes: str = "",
) -> dict:
    return {
        "id": f"item_{category}",
        "category": category,
        "subcategory": subcategory or category,
        "tags": tags or [],
        "colors": colors or [],
        "notes": notes,
    }


# ── item_profile ──────────────────────────────────────────────────────────────


class TestItemProfile:
    def test_returns_required_keys(self):
        p = item_profile(_item())
        assert {"tags", "colors", "pattern_strength", "formality", "weight"} <= p.keys()

    def test_solid_when_no_pattern_tags(self):
        p = item_profile(_item(tags=["cotton", "slim-fit"]))
        assert p["pattern_strength"] == "solid"

    def test_subtle_with_one_pattern_tag(self):
        p = item_profile(_item(tags=["striped"]))
        assert p["pattern_strength"] == "subtle"

    def test_statement_with_multiple_pattern_tags(self):
        p = item_profile(_item(tags=["striped", "plaid"]))
        assert p["pattern_strength"] == "statement"

    def test_casual_default_formality(self):
        p = item_profile(_item(tags=["hoodie", "cotton"]))
        assert p["formality"] == "casual"

    def test_smart_casual_with_smart_tags(self):
        p = item_profile(_item(tags=["shirt", "collared"]))
        assert p["formality"] == "smart-casual"

    def test_formal_blazer(self):
        p = item_profile(_item(notes="wool blazer"))
        assert p["formality"] == "formal"

    def test_light_weight(self):
        p = item_profile(_item(tags=["linen", "lightweight"]))
        assert p["weight"] == "light"

    def test_warm_weight(self):
        p = item_profile(_item(tags=["knit", "sweater"]))
        assert p["weight"] == "warm"

    def test_mid_weight_default(self):
        p = item_profile(_item(tags=["cotton"]))
        assert p["weight"] == "mid"

    def test_colors_are_lowercased_set(self):
        p = item_profile(_item(colors=["Black", "WHITE"]))
        assert "black" in p["colors"]
        assert "white" in p["colors"]


# ── _color_temp ────────────────────────────────────────────────────────────────


class TestColorTemp:
    def test_neutral_only(self):
        assert _color_temp({"black", "white", "beige"}) == "neutral"

    def test_warm(self):
        assert _color_temp({"brown", "tan"}) == "warm"

    def test_cool(self):
        assert _color_temp({"blue", "teal"}) == "cool"

    def test_mixed_warm_and_cool(self):
        assert _color_temp({"blue", "brown"}) == "mixed"

    def test_empty_is_neutral(self):
        assert _color_temp(set()) == "neutral"


# ── score_outfit ──────────────────────────────────────────────────────────────


class TestScoreOutfit:
    def test_score_in_range(self):
        top = _item("tops", colors=["black"])
        bottom = _item("bottoms", colors=["black"])
        score, _ = score_outfit([top, bottom])
        assert 0 <= score <= 100

    def test_two_parts_higher_than_one(self):
        top = _item("tops", colors=["black"])
        bottom = _item("bottoms", colors=["black"])
        score_two, _ = score_outfit([top, bottom])
        score_one, _ = score_outfit([top])
        assert score_two > score_one

    def test_shoes_bonus(self):
        top = _item("tops", colors=["black"])
        bottom = _item("bottoms", colors=["black"])
        shoes = _item("shoes", colors=["black"])
        with_shoes, _ = score_outfit([top, bottom, shoes])
        without_shoes, _ = score_outfit([top, bottom])
        assert with_shoes > without_shoes

    def test_outerwear_bonus_in_cold(self):
        top = _item("tops", colors=["navy"])
        bottom = _item("bottoms", colors=["navy"])
        outer = _item("outerwear", tags=["knit"])
        with_outer, _ = score_outfit([top, bottom, outer], weather="cold")
        without_outer, _ = score_outfit([top, bottom], weather="cold")
        assert with_outer > without_outer

    def test_outerwear_penalty_in_hot(self):
        top = _item("tops", colors=["beige"], tags=["linen"])
        outer = _item("outerwear", tags=["coat"])
        with_outer, _ = score_outfit([top, outer], weather="hot")
        without_outer, _ = score_outfit([top], weather="hot")
        assert with_outer < without_outer

    def test_neutral_palette_bonus(self):
        top = _item("tops", colors=["black"])
        bottom = _item("bottoms", colors=["white"])
        score, reasons = score_outfit([top, bottom])
        reason_text = " ".join(reasons)
        assert "neutral" in reason_text.lower()

    def test_pattern_clash_penalty(self):
        top = _item("tops", tags=["striped", "plaid"])
        bottom = _item("bottoms", tags=["geometric", "dotted-pattern"])
        score, reasons = score_outfit([top, bottom])
        reason_text = " ".join(reasons)
        assert "pattern" in reason_text.lower()

    def test_reasons_list_is_strings(self):
        _, reasons = score_outfit([_item("tops"), _item("bottoms")])
        assert all(isinstance(r, str) for r in reasons)

    def test_reasons_capped_at_five(self):
        items = [_item("tops", tags=["shirt"], colors=["black"]),
                 _item("bottoms", colors=["black"]),
                 _item("shoes", colors=["black"]),
                 _item("outerwear", tags=["knit"])]
        _, reasons = score_outfit(items, occasion="work", weather="cold", vibe="minimal")
        assert len(reasons) <= 5

    def test_empty_parts_still_returns_tuple(self):
        score, reasons = score_outfit([])
        assert isinstance(score, int)
        assert isinstance(reasons, list)


# ── _auto_name ────────────────────────────────────────────────────────────────


class TestAutoName:
    def test_single_item(self):
        name = _auto_name([_item("tops", colors=["black"], subcategory="tee")])
        assert isinstance(name, str)
        assert len(name) > 0

    def test_includes_color_and_subcategory(self):
        top = _item("tops", colors=["navy"], subcategory="shirt")
        name = _auto_name([top])
        assert "navy" in name.lower() or "shirt" in name.lower()

    def test_two_items_joined(self):
        top = _item("tops", colors=["black"], subcategory="tee")
        bottom = _item("bottoms", colors=["white"], subcategory="jeans")
        name = _auto_name([top, bottom])
        assert "+" in name

    def test_capped_at_three_items(self):
        parts = [_item(f"item{i}", subcategory=f"piece{i}") for i in range(5)]
        name = _auto_name(parts)
        # At most 3 items contribute; name should not explode in length
        assert name.count("+") <= 2
