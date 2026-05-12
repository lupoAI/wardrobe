import json
import sqlite3
from pathlib import Path
from .config import DB_PATH, DATA_DIR, IMAGE_DIR, EMBEDDING_DIR

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS dressed_looks (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    combo_hash TEXT NOT NULL,
    image_path TEXT NOT NULL,
    item_ids_json TEXT NOT NULL,
    model TEXT,
    elapsed_seconds REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dressed_combo ON dressed_looks(combo_hash);
CREATE INDEX IF NOT EXISTS idx_dressed_created ON dressed_looks(created_at);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    original_filename TEXT NOT NULL,
    image_path TEXT NOT NULL,
    embedding_path TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    colors_json TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);

CREATE TABLE IF NOT EXISTS outfits (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    occasion TEXT NOT NULL,
    weather TEXT NOT NULL,
    vibe TEXT NOT NULL,
    score INTEGER NOT NULL,
    reasons_json TEXT NOT NULL,
    item_ids_json TEXT NOT NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_outfits_created_at ON outfits(created_at);

CREATE TABLE IF NOT EXISTS outfit_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    outfit_id TEXT NOT NULL,
    rating INTEGER NOT NULL,
    reason TEXT,
    FOREIGN KEY(outfit_id) REFERENCES outfits(id)
);
CREATE INDEX IF NOT EXISTS idx_outfit_feedback_outfit ON outfit_feedback(outfit_id);
"""

def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    EMBEDDING_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con

def insert_item(con: sqlite3.Connection, item: dict) -> None:
    con.execute(
        """
        INSERT INTO items(id, original_filename, image_path, embedding_path, category, subcategory, colors_json, tags_json, notes)
        VALUES(:id, :original_filename, :image_path, :embedding_path, :category, :subcategory, :colors_json, :tags_json, :notes)
        """,
        {
            **item,
            "colors_json": json.dumps(item.get("colors", [])),
            "tags_json": json.dumps(item.get("tags", [])),
        },
    )
    con.commit()

def list_items(con: sqlite3.Connection, category: str | None = None) -> list[dict]:
    if category:
        rows = con.execute("SELECT * FROM items WHERE category = ? ORDER BY created_at DESC", (category,)).fetchall()
    else:
        rows = con.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["colors"] = json.loads(d.pop("colors_json"))
        d["tags"] = json.loads(d.pop("tags_json"))
        out.append(d)
    return out


def insert_outfit(con: sqlite3.Connection, outfit: dict) -> None:
    con.execute(
        """
        INSERT INTO outfits(id, name, occasion, weather, vibe, score, reasons_json, item_ids_json, notes)
        VALUES(:id, :name, :occasion, :weather, :vibe, :score, :reasons_json, :item_ids_json, :notes)
        """,
        {
            **outfit,
            "reasons_json": json.dumps(outfit.get("reasons", [])),
            "item_ids_json": json.dumps(outfit.get("item_ids", [])),
        },
    )
    con.commit()


def list_outfits(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute("SELECT * FROM outfits ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["reasons"] = json.loads(d.pop("reasons_json"))
        d["item_ids"] = json.loads(d.pop("item_ids_json"))
        out.append(d)
    return out


def insert_outfit_feedback(con: sqlite3.Connection, outfit_id: str, rating: int, reason: str | None = None) -> None:
    con.execute(
        "INSERT INTO outfit_feedback(outfit_id, rating, reason) VALUES(?, ?, ?)",
        (outfit_id, rating, reason),
    )
    con.commit()


def insert_dressed_look(con: sqlite3.Connection, look: dict) -> None:
    con.execute(
        "INSERT OR IGNORE INTO dressed_looks"
        "(id, combo_hash, image_path, item_ids_json, model, elapsed_seconds)"
        " VALUES(:id, :combo_hash, :image_path, :item_ids_json, :model, :elapsed_seconds)",
        {**look, "item_ids_json": json.dumps(look.get("item_ids", []))},
    )
    con.commit()


def list_dressed_looks(con: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM dressed_looks ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["item_ids"] = json.loads(d.pop("item_ids_json"))
        out.append(d)
    return out
