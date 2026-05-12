"""Tests for wear-log DB helpers."""
import datetime
import sys
import tempfile
import unittest
from pathlib import Path

# Allow running from repo root without installation
sys.path.insert(0, str(Path(__file__).parent.parent))

from wardrobe.db import (
    connect,
    get_all_item_wear_stats,
    get_all_outfit_wear_stats,
    get_wear_stats,
    log_wear,
    recent_wear,
)


def _con(tmp):
    return connect(Path(tmp) / "test.sqlite3")


class TestLogWear(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = _con(self.tmp)

    def test_log_item_defaults_today(self):
        result = log_wear(self.con, item_id="item_abc")
        self.assertEqual(result["worn_date"], datetime.date.today().isoformat())
        self.assertEqual(result["item_id"], "item_abc")
        self.assertIsNone(result["outfit_id"])

    def test_log_outfit(self):
        result = log_wear(self.con, outfit_id="outfit_xyz", note="Date night")
        self.assertEqual(result["outfit_id"], "outfit_xyz")
        self.assertEqual(result["note"], "Date night")

    def test_log_wear_requires_id(self):
        with self.assertRaises(ValueError):
            log_wear(self.con)

    def test_log_wear_custom_date(self):
        result = log_wear(self.con, item_id="item_abc", worn_date="2024-12-25")
        self.assertEqual(result["worn_date"], "2024-12-25")


class TestGetWearStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = _con(self.tmp)

    def test_never_worn_returns_zero(self):
        stats = get_wear_stats(self.con, item_id="item_never")
        self.assertEqual(stats["wear_count"], 0)
        self.assertIsNone(stats["last_worn"])

    def test_single_wear(self):
        log_wear(self.con, item_id="item_x", worn_date="2025-03-10")
        stats = get_wear_stats(self.con, item_id="item_x")
        self.assertEqual(stats["wear_count"], 1)
        self.assertEqual(stats["last_worn"], "2025-03-10")

    def test_multiple_wears_returns_latest(self):
        log_wear(self.con, item_id="item_x", worn_date="2025-01-01")
        log_wear(self.con, item_id="item_x", worn_date="2025-06-15")
        log_wear(self.con, item_id="item_x", worn_date="2025-03-20")
        stats = get_wear_stats(self.con, item_id="item_x")
        self.assertEqual(stats["wear_count"], 3)
        self.assertEqual(stats["last_worn"], "2025-06-15")

    def test_outfit_stats(self):
        log_wear(self.con, outfit_id="outfit_o1", worn_date="2025-05-01")
        log_wear(self.con, outfit_id="outfit_o1", worn_date="2025-05-20")
        stats = get_wear_stats(self.con, outfit_id="outfit_o1")
        self.assertEqual(stats["wear_count"], 2)
        self.assertEqual(stats["last_worn"], "2025-05-20")

    def test_requires_id(self):
        with self.assertRaises(ValueError):
            get_wear_stats(self.con)

    def test_item_and_outfit_stats_are_independent(self):
        log_wear(self.con, item_id="item_a", worn_date="2025-04-01")
        log_wear(self.con, outfit_id="outfit_b", worn_date="2025-04-02")
        item_stats = get_wear_stats(self.con, item_id="item_a")
        outfit_stats = get_wear_stats(self.con, outfit_id="outfit_b")
        self.assertEqual(item_stats["wear_count"], 1)
        self.assertEqual(outfit_stats["wear_count"], 1)


class TestGetAllWearStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = _con(self.tmp)

    def test_empty_returns_empty_dict(self):
        self.assertEqual(get_all_item_wear_stats(self.con), {})
        self.assertEqual(get_all_outfit_wear_stats(self.con), {})

    def test_bulk_item_stats(self):
        log_wear(self.con, item_id="item_a", worn_date="2025-01-10")
        log_wear(self.con, item_id="item_a", worn_date="2025-02-10")
        log_wear(self.con, item_id="item_b", worn_date="2025-03-01")
        all_stats = get_all_item_wear_stats(self.con)
        self.assertEqual(all_stats["item_a"]["wear_count"], 2)
        self.assertEqual(all_stats["item_a"]["last_worn"], "2025-02-10")
        self.assertEqual(all_stats["item_b"]["wear_count"], 1)
        self.assertNotIn("item_c", all_stats)

    def test_bulk_outfit_stats(self):
        log_wear(self.con, outfit_id="outfit_x", worn_date="2025-05-01")
        all_stats = get_all_outfit_wear_stats(self.con)
        self.assertEqual(all_stats["outfit_x"]["wear_count"], 1)


class TestRecentWear(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = _con(self.tmp)

    def test_returns_most_recent_first(self):
        log_wear(self.con, item_id="item_a", worn_date="2025-01-01")
        log_wear(self.con, item_id="item_b", worn_date="2025-06-01")
        log_wear(self.con, item_id="item_a", worn_date="2025-03-15")
        events = recent_wear(self.con, 10)
        self.assertEqual(events[0]["worn_date"], "2025-06-01")
        self.assertEqual(events[-1]["worn_date"], "2025-01-01")

    def test_limit_respected(self):
        for i in range(5):
            log_wear(self.con, item_id=f"item_{i}", worn_date=f"2025-0{i+1}-01")
        events = recent_wear(self.con, 3)
        self.assertEqual(len(events), 3)

    def test_filter_by_item_id(self):
        log_wear(self.con, item_id="item_a", worn_date="2025-01-01")
        log_wear(self.con, item_id="item_b", worn_date="2025-02-01")
        log_wear(self.con, item_id="item_a", worn_date="2025-03-01")
        events = recent_wear(self.con, 10, item_id="item_a")
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["item_id"] == "item_a" for e in events))

    def test_filter_by_outfit_id(self):
        log_wear(self.con, outfit_id="outfit_x", worn_date="2025-01-01")
        log_wear(self.con, item_id="item_a", worn_date="2025-02-01")
        events = recent_wear(self.con, 10, outfit_id="outfit_x")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outfit_id"], "outfit_x")

    def test_empty_log(self):
        events = recent_wear(self.con, 20)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
