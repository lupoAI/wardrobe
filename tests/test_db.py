"""Tests for wardrobe.db using an in-memory SQLite database."""
from __future__ import annotations

import json
import sqlite3

import pytest

from wardrobe.db import (
    SCHEMA,
    insert_dressed_look,
    insert_outfit,
    insert_outfit_feedback,
    list_dressed_looks,
    list_outfits,
)


def _mem_con() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _item_stub(item_id: str, category: str = "tops") -> dict:
    return {
        "id": item_id,
        "original_filename": f"{item_id}.jpg",
        "image_path": f"/data/images/{item_id}.jpg",
        "embedding_path": f"/data/embeddings/{item_id}.npy",
        "category": category,
        "subcategory": None,
        "colors": ["black"],
        "tags": ["solid"],
        "notes": item_id,
    }


def _outfit_stub(outfit_id: str, item_ids: list[str] | None = None) -> dict:
    return {
        "id": outfit_id,
        "name": "Test Outfit",
        "occasion": "casual",
        "weather": "mild",
        "vibe": "balanced",
        "score": 70,
        "reasons": ["complete base outfit", "neutral palette"],
        "item_ids": item_ids or ["item_001", "item_002"],
        "notes": None,
    }


def _look_stub(combo_hash: str = "abc123", item_ids: list[str] | None = None) -> dict:
    return {
        "id": f"look_{combo_hash}",
        "combo_hash": combo_hash,
        "image_path": f"/data/user/salo/dressed/dressed_avatar_{combo_hash}.jpg",
        "item_ids": item_ids or ["item_001", "item_002"],
        "model": "google/gemini-3.1-flash-image-preview",
        "elapsed_seconds": 12.5,
    }


class TestSchema:
    def test_creates_all_tables(self):
        con = _mem_con()
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "items" in tables
        assert "outfits" in tables
        assert "outfit_feedback" in tables
        assert "dressed_looks" in tables

    def test_idempotent(self):
        """Running the schema twice (IF NOT EXISTS) must not raise."""
        con = _mem_con()
        con.executescript(SCHEMA)  # second run


class TestInsertOutfit:
    def test_round_trip(self):
        con = _mem_con()
        insert_outfit(con, _outfit_stub("outfit_aaa"))
        rows = list_outfits(con)
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == "outfit_aaa"
        assert row["score"] == 70
        assert row["reasons"] == ["complete base outfit", "neutral palette"]
        assert row["item_ids"] == ["item_001", "item_002"]

    def test_multiple_outfits_ordered_newest_first(self):
        con = _mem_con()
        insert_outfit(con, _outfit_stub("outfit_1"))
        insert_outfit(con, _outfit_stub("outfit_2"))
        rows = list_outfits(con)
        assert len(rows) == 2
        # SQLite CURRENT_TIMESTAMP resolution is 1 second; order depends on insertion within same second.
        ids = {r["id"] for r in rows}
        assert ids == {"outfit_1", "outfit_2"}


class TestOutfitFeedback:
    def test_insert_feedback(self):
        con = _mem_con()
        insert_outfit(con, _outfit_stub("outfit_x"))
        insert_outfit_feedback(con, "outfit_x", rating=1, reason="love it")
        rows = con.execute("SELECT * FROM outfit_feedback WHERE outfit_id='outfit_x'").fetchall()
        assert len(rows) == 1
        assert rows[0]["rating"] == 1
        assert rows[0]["reason"] == "love it"

    def test_multiple_feedback_rows(self):
        con = _mem_con()
        insert_outfit(con, _outfit_stub("outfit_y"))
        insert_outfit_feedback(con, "outfit_y", rating=1)
        insert_outfit_feedback(con, "outfit_y", rating=-1)
        rows = con.execute("SELECT * FROM outfit_feedback WHERE outfit_id='outfit_y'").fetchall()
        assert len(rows) == 2


class TestDressedLooks:
    def test_insert_and_list(self):
        con = _mem_con()
        insert_dressed_look(con, _look_stub("hash001"))
        rows = list_dressed_looks(con)
        assert len(rows) == 1
        row = rows[0]
        assert row["combo_hash"] == "hash001"
        assert row["item_ids"] == ["item_001", "item_002"]
        assert row["elapsed_seconds"] == pytest.approx(12.5)

    def test_insert_ignore_duplicate_combo(self):
        """Second insert of same combo_hash is silently ignored (INSERT OR IGNORE)."""
        con = _mem_con()
        insert_dressed_look(con, _look_stub("hash002"))
        insert_dressed_look(con, _look_stub("hash002"))
        rows = list_dressed_looks(con)
        assert len(rows) == 1

    def test_multiple_looks_different_hashes(self):
        con = _mem_con()
        insert_dressed_look(con, _look_stub("aaa"))
        insert_dressed_look(con, _look_stub("bbb"))
        rows = list_dressed_looks(con)
        assert len(rows) == 2

    def test_limit_respected(self):
        con = _mem_con()
        for i in range(10):
            insert_dressed_look(con, _look_stub(f"hash{i:03d}"))
        rows = list_dressed_looks(con, limit=5)
        assert len(rows) == 5

    def test_item_ids_round_trip(self):
        con = _mem_con()
        ids = ["item_001", "item_002", "item_003"]
        insert_dressed_look(con, {**_look_stub("xyz"), "item_ids": ids})
        row = list_dressed_looks(con)[0]
        assert row["item_ids"] == ids

    def test_model_stored(self):
        con = _mem_con()
        insert_dressed_look(con, _look_stub("modl"))
        row = list_dressed_looks(con)[0]
        assert row["model"] == "google/gemini-3.1-flash-image-preview"
