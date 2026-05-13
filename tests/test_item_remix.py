from unittest.mock import patch

from wardrobe.outfits import suggest_outfits


MOCK_ITEMS = [
    {"id": "item_top1", "category": "tops", "subcategory": "t-shirt", "tags": [], "colors": ["red"], "notes": "red tee"},
    {"id": "item_top2", "category": "tops", "subcategory": "shirt", "tags": ["collared"], "colors": ["blue"], "notes": "blue shirt"},
    {"id": "item_bot1", "category": "bottoms", "subcategory": "trousers", "tags": [], "colors": ["black"], "notes": "black trousers"},
    {"id": "item_shoe1", "category": "shoes", "subcategory": "sneakers", "tags": [], "colors": ["white"], "notes": "white sneakers"},
    {"id": "item_out1", "category": "outerwear", "subcategory": "blazer", "tags": [], "colors": ["gray"], "notes": "gray blazer"},
    {"id": "item_acc1", "category": "accessories", "subcategory": "tie", "tags": [], "colors": ["navy"], "notes": "navy tie"},
]


@patch("wardrobe.outfits.items")
def test_remix_constrains_core_category(mock_items):
    mock_items.return_value = MOCK_ITEMS

    outfits = suggest_outfits(item_id="item_top2", limit=20)

    assert outfits
    for outfit in outfits:
        ids = [item["id"] for item in outfit["items"]]
        assert "item_top2" in ids
        assert "item_top1" not in ids


@patch("wardrobe.outfits.items")
def test_remix_appends_accessory(mock_items):
    mock_items.return_value = MOCK_ITEMS

    outfits = suggest_outfits(item_id="item_acc1", limit=20)

    assert outfits
    for outfit in outfits:
        assert "item_acc1" in [item["id"] for item in outfit["items"]]


@patch("wardrobe.outfits.items")
def test_remix_unknown_item_raises(mock_items):
    mock_items.return_value = MOCK_ITEMS

    try:
        suggest_outfits(item_id="missing")
    except ValueError as exc:
        assert "No item found" in str(exc)
    else:
        raise AssertionError("expected ValueError")
