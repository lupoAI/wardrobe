from __future__ import annotations

import json
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from wardrobe import outfits
from wardrobe.web import FastThreadingHTTPServer, WardrobeHandler


def item(item_id, category, subcategory, colors, tags, notes=""):
    return {
        "id": item_id,
        "created_at": "2026-01-01T00:00:00Z",
        "original_filename": f"{item_id}.jpg",
        "image_path": f"/tmp/{item_id}.jpg",
        "embedding_path": f"/tmp/{item_id}.npy",
        "category": category,
        "subcategory": subcategory,
        "colors": colors,
        "tags": tags,
        "notes": notes,
    }


FIXTURE = [
    item("top_linen", "tops", "shirt", ["white"], ["linen", "lightweight", "shirt"], "white linen travel shirt"),
    item("top_tee", "tops", "t-shirt", ["navy"], ["t-shirt", "tee"], "navy tee"),
    item("top_sweater", "tops", "sweater", ["gray"], ["knit", "sweater"], "warm gray sweater"),
    item("bottom_chinos", "bottoms", "chinos", ["khaki"], ["chinos"], "khaki chinos"),
    item("bottom_jeans", "bottoms", "jeans", ["dark indigo"], ["jeans"], "dark jeans"),
    item("shoe_sneakers", "shoes", "sneakers", ["white"], ["sneakers"], "white sneakers"),
    item("shoe_boots", "shoes", "boots", ["brown"], ["boots"], "brown waterproof boots"),
    item("outer_rain", "outerwear", "jacket", ["black"], ["lightweight"], "black waterproof rain jacket"),
    item("outer_puffer", "outerwear", "puffer-jacket", ["black"], ["puffer-jacket", "down-jacket"], "warm puffer jacket"),
    item("acc_cap", "accessories", "cap", ["black"], ["cap"], "black cap"),
]


class TravelCapsuleTests(unittest.TestCase):
    def test_hot_capsule_is_deterministic_and_compact(self):
        with patch.object(outfits, "items", return_value=FIXTURE):
            first = outfits.generate_capsule(4, location="beach", weather="hot", style="minimal linen")
            second = outfits.generate_capsule(4, location="beach", weather="hot", style="minimal linen")

        self.assertEqual(
            [item["id"] for item in first["capsule_items"]],
            [item["id"] for item in second["capsule_items"]],
        )
        self.assertEqual(first["trip"]["weather"], "hot")
        self.assertLessEqual(first["counts"]["pieces"], 10)
        self.assertEqual(len(first["daily_outfits"]), 4)
        self.assertIn("top_linen", {item["id"] for item in first["capsule_items"]})
        self.assertNotIn("outer_puffer", {item["id"] for item in first["capsule_items"]})

    def test_rainy_capsule_includes_weather_layer(self):
        with patch.object(outfits, "items", return_value=FIXTURE):
            capsule = outfits.generate_capsule(3, location="London", weather="rainy", style="travel")

        ids = {item["id"] for item in capsule["capsule_items"]}
        self.assertEqual(capsule["trip"]["weather"], "rainy")
        self.assertIn("outer_rain", ids)
        self.assertGreaterEqual(capsule["counts"]["categories"]["outerwear"], 1)
        self.assertTrue(all("day" in outfit for outfit in capsule["daily_outfits"]))

    def test_travel_capsule_api_returns_json(self):
        server = FastThreadingHTTPServer(("127.0.0.1", 0), WardrobeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(outfits, "items", return_value=FIXTURE):
                url = f"http://127.0.0.1:{server.server_port}/api/travel/capsule?days=2&location=London&weather=rainy&style=minimal"
                with urlopen(url, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))

                req = Request(
                    f"http://127.0.0.1:{server.server_port}/api/travel/capsule",
                    data=json.dumps({"days": 2, "weather": "hot", "style": "linen", "constraints": ["sneakers"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=5) as response:
                    posted = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(data["trip"]["duration_days"], 2)
        self.assertIn("capsule_items", data)
        self.assertIn("daily_outfits", data)
        self.assertTrue(data["capsule_items"][0]["image_url"].startswith("/images/"))
        self.assertEqual(posted["trip"]["weather"], "hot")
        self.assertEqual(posted["trip"]["constraints"], ["sneakers"])


if __name__ == "__main__":
    unittest.main()
