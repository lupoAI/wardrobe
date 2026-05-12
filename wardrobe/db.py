import datetime
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

CREATE TABLE IF NOT EXISTS wear_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worn_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    worn_date TEXT NOT NULL,
    item_id TEXT,
    outfit_id TEXT,
    note TEXT,
    FOREIGN KEY(item_id) REFERENCES items(id),
    FOREIGN KEY(outfit_id) REFERENCES outfits(id)
);
CREATE INDEX IF NOT EXISTS idx_wear_log_item ON wear_log(item_id, worn_date);
CREATE INDEX IF NOT EXISTS idx_wear_log_outfit ON wear_log(outfit_id, worn_date);
CREATE INDEX IF NOT EXISTS idx_wear_log_date ON wear_log(worn_date DESC);
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


def log_wear(
    con: sqlite3.Connection,
    *,
    item_id: str | None = None,
    outfit_id: str | None = None,
    note: str | None = None,
    worn_date: str | None = None,
) -> dict:
    if not item_id and not outfit_id:
        raise ValueError("item_id or outfit_id required")
    if worn_date is None:
        worn_date = datetime.date.today().isoformat()
    con.execute(
        "INSERT INTO wear_log(worn_date, item_id, outfit_id, note) VALUES(?, ?, ?, ?)",
        (worn_date, item_id, outfit_id, note),
    )
    con.commit()
    return {"worn_date": worn_date, "item_id": item_id, "outfit_id": outfit_id, "note": note}


def get_wear_stats(
    con: sqlite3.Connection,
    *,
    item_id: str | None = None,
    outfit_id: str | None = None,
) -> dict:
    if item_id:
        row = con.execute(
            "SELECT COUNT(*) as count, MAX(worn_date) as last_worn FROM wear_log WHERE item_id = ?",
            (item_id,),
        ).fetchone()
    elif outfit_id:
        row = con.execute(
            "SELECT COUNT(*) as count, MAX(worn_date) as last_worn FROM wear_log WHERE outfit_id = ?",
            (outfit_id,),
        ).fetchone()
    else:
        raise ValueError("item_id or outfit_id required")
    return {"wear_count": row["count"], "last_worn": row["last_worn"]}


def get_all_item_wear_stats(con: sqlite3.Connection) -> dict[str, dict]:
    rows = con.execute(
        "SELECT item_id, COUNT(*) as count, MAX(worn_date) as last_worn"
        " FROM wear_log WHERE item_id IS NOT NULL GROUP BY item_id"
    ).fetchall()
    return {r["item_id"]: {"wear_count": r["count"], "last_worn": r["last_worn"]} for r in rows}


def get_all_outfit_wear_stats(con: sqlite3.Connection) -> dict[str, dict]:
    rows = con.execute(
        "SELECT outfit_id, COUNT(*) as count, MAX(worn_date) as last_worn"
        " FROM wear_log WHERE outfit_id IS NOT NULL GROUP BY outfit_id"
    ).fetchall()
    return {r["outfit_id"]: {"wear_count": r["count"], "last_worn": r["last_worn"]} for r in rows}


def recent_wear(
    con: sqlite3.Connection,
    limit: int = 20,
    *,
    item_id: str | None = None,
    outfit_id: str | None = None,
) -> list[dict]:
    if item_id:
        rows = con.execute(
            "SELECT * FROM wear_log WHERE item_id = ? ORDER BY worn_date DESC, id DESC LIMIT ?",
            (item_id, limit),
        ).fetchall()
    elif outfit_id:
        rows = con.execute(
            "SELECT * FROM wear_log WHERE outfit_id = ? ORDER BY worn_date DESC, id DESC LIMIT ?",
            (outfit_id, limit),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM wear_log ORDER BY worn_date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
