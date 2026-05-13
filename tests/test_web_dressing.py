from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import wardrobe.web as web


class WebDressingFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.user_dir = self.root / "data" / "user" / "salo"
        self.avatar_dir = self.user_dir / "avatar"
        self.dressed_dir = self.user_dir / "dressed"
        self.card_dir = self.dressed_dir / "cards"
        self.image_dir = self.root / "data" / "images"
        self.thumb_dir = self.root / "data" / "thumbnails"
        self.patches = [
            patch.object(web, "USER_DIR", self.user_dir),
            patch.object(web, "AVATAR_DIR", self.avatar_dir),
            patch.object(web, "DRESSED_DIR", self.dressed_dir),
            patch.object(web, "BASE_AVATAR_PATH", self.avatar_dir / "neutral_avatar.jpg"),
            patch.object(web, "BASE_AVATAR_TRANSPARENT_PATH", self.avatar_dir / "neutral_avatar_transparent.png"),
            patch.object(web, "AVATAR_META_PATH", self.avatar_dir / "avatar.json"),
            patch.object(web, "LOOKBOOK_PATH", self.dressed_dir / "lookbook.json"),
            patch.object(web, "LOOK_CARD_DIR", self.card_dir),
            patch.object(web, "IMAGE_DIR", self.image_dir),
            patch.object(web, "THUMBNAIL_DIR", self.thumb_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def make_image(self, path: Path, color: str = "navy") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 180), color).save(path)
        return path

    def test_replace_base_avatar_updates_current_avatar_and_metadata(self) -> None:
        old_avatar = self.make_image(self.avatar_dir / "neutral_avatar.jpg", "gray")
        new_avatar = self.make_image(self.root / "incoming_avatar.png", "white")

        result = web._replace_base_avatar(new_avatar, original_filename="avatar.png")

        self.assertTrue(result["ok"])
        self.assertTrue(result["exists"])
        self.assertEqual(result["original_filename"], "avatar.png")
        self.assertFalse(old_avatar.exists())
        self.assertEqual(web._current_avatar_path(), self.avatar_dir / "neutral_avatar.png")
        self.assertEqual(result["image_url"], "/user/avatar/neutral_avatar.png")

    def test_lookbook_saves_generated_look_and_exports_share_card(self) -> None:
        look = self.make_image(self.dressed_dir / "dressed_avatar_demo.jpg", "beige")
        item_image = self.make_image(self.image_dir / "tops" / "item_top.jpg", "black")
        meta = {
            "look_id": "dressed_avatar_demo",
            "combo_hash": "demo",
            "image_path": str(look),
            "image_url": "/user/dressed/dressed_avatar_demo.jpg",
            "item_ids": ["item_top"],
            "items": [{"id": "item_top", "category": "tops", "subcategory": "shirt", "notes": "black shirt", "image_path": str(item_image)}],
            "model": "test-model",
            "generated_at": "2026-05-13T20:40:00Z",
        }

        entry = web._save_lookbook_entry(meta)
        self.assertEqual(entry["look_id"], "dressed_avatar_demo")
        self.assertEqual(len(web._lookbook()), 1)

        card = web._export_look_card("dressed_avatar_demo")
        self.assertTrue(Path(card["card_path"]).is_file())
        self.assertEqual(card["card_url"], "/user/dressed/cards/dressed_avatar_demo.jpg")
        self.assertEqual(web._lookbook()[0]["card_url"], card["card_url"])

    def test_cached_dressing_generation_is_added_to_lookbook(self) -> None:
        self.make_image(self.avatar_dir / "neutral_avatar.jpg", "gray")
        item = {"id": "item_a", "category": "tops", "subcategory": "shirt", "notes": "test shirt", "image_path": str(self.make_image(self.image_dir / "tops" / "item_a.jpg", "red"))}
        combo_hash = "e667454aefc7e4bd"  # sha256('item_a')[:16]
        out = self.make_image(self.dressed_dir / f"dressed_avatar_{combo_hash}.jpg", "green")
        meta_path = self.dressed_dir / f"dressed_avatar_{combo_hash}.json"
        meta_path.write_text(json.dumps({"image_path": str(out), "combo_hash": combo_hash, "item_ids": ["item_a"], "items": [item]}))

        with patch.object(web, "items", return_value=[item]):
            result = web._run_dress_generation(["item_a"])

        self.assertTrue(result["cached"])
        self.assertEqual(result["look_id"], f"dressed_avatar_{combo_hash}")
        self.assertEqual(web._lookbook()[0]["look_id"], f"dressed_avatar_{combo_hash}")


if __name__ == "__main__":
    unittest.main()
