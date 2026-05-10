import json
import sqlite3
from pathlib import Path
from .config import DB_PATH, DATA_DIR, IMAGE_DIR, EMBEDDING_DIR

SCHEMA = """
PRAGMA journal_mode=WAL;
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
