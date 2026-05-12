from wardrobe.outfits import item_profile, score_outfit

def test_item_profile():
    item = {
        "id": "item_1",
        "category": "tops",
        "subcategory": "shirt",
        "notes": "Linen summer shirt",
        "tags": ["linen", "lightweight", "button-up"],
        "colors": ["white"]
    }
    profile = item_profile(item)
    assert profile["formality"] == "smart-casual"
    assert profile["weight"] == "light"
    assert "white" in profile["colors"]

def test_score_outfit_basic():
    top = {"id": "t1", "category": "tops", "colors": ["white"], "tags": ["linen"]}
    bottom = {"id": "b1", "category": "bottoms", "colors": ["navy"], "tags": ["chinos"]}
    score, reasons = score_outfit([top, bottom])
    assert score > 50
    assert "complete base outfit" in reasons

def test_score_outfit_weather():
    top = {"id": "t1", "category": "tops", "colors": ["white"], "tags": ["linen"]}
    bottom = {"id": "b1", "category": "bottoms", "colors": ["navy"], "tags": ["chinos"]}
    outer = {"id": "o1", "category": "outerwear", "colors": ["black"], "tags": ["coat", "warm"]}
    
    # Cold weather with outerwear
    score_cold, reasons_cold = score_outfit([top, bottom, outer], weather="cold")
    assert "outerwear fits weather" in reasons_cold
    
    # Hot weather with outerwear
    score_hot, reasons_hot = score_outfit([top, bottom, outer], weather="hot")
    assert "outerwear may be too warm" in reasons_hot
