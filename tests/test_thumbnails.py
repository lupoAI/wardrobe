import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from wardrobe import thumbnails


class ThumbnailBackgroundTests(unittest.TestCase):
    def test_remove_plain_background_outputs_transparent_square(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "raw.jpg"
            dest = Path(tmp) / "clean.png"
            img = Image.new("RGB", (80, 60), (242, 238, 228))
            for x in range(25, 55):
                for y in range(12, 50):
                    img.putpixel((x, y), (150, 20, 30))
            img.save(src)

            result = thumbnails.remove_plain_background(src, dest, size=128)
            out = Image.open(dest).convert("RGBA")

            self.assertEqual(out.size, (128, 128))
            self.assertEqual(out.getpixel((0, 0))[3], 0)
            self.assertGreater(out.getpixel((64, 64))[3], 200)
            self.assertGreater(result["transparent_ratio"], 0.4)
            self.assertEqual(result["output_size"], [128, 128])

    def test_clean_thumbnail_prefers_raw_source_and_writes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            thumb_dir = root / "thumbs"
            meta_dir = root / "meta"
            raw = meta_dir / "item_test.raw.jpg"
            original = root / "original.jpg"
            meta_dir.mkdir()
            Image.new("RGB", (50, 50), (240, 236, 226)).save(original)
            img = Image.new("RGB", (50, 50), (240, 236, 226))
            for x in range(18, 32):
                for y in range(12, 42):
                    img.putpixel((x, y), (10, 100, 180))
            img.save(raw)
            item = {"id": "item_test", "image_path": str(original), "category": "tops", "subcategory": "shirt"}

            with patch.object(thumbnails, "THUMBNAIL_DIR", thumb_dir), patch.object(thumbnails, "THUMBNAIL_META_DIR", meta_dir):
                result = thumbnails.clean_thumbnail(item, size=64)
                status = thumbnails.thumbnail_status(item)
                metadata = json.loads((meta_dir / "item_test.json").read_text())

            self.assertFalse(result["skipped"])
            self.assertEqual(Path(result["source_path"]), raw)
            self.assertTrue((thumb_dir / "item_test.png").is_file())
            self.assertEqual(status["state"], "clean")
            self.assertTrue(metadata["background_removed"])
            self.assertEqual(metadata["cleanup"]["output_size"], [64, 64])


if __name__ == "__main__":
    unittest.main()
