# Wear Tracking

Records when individual items or saved outfits are worn. All data is stored locally in the existing SQLite database.

## Database

A new `wear_log` table is added to `data/wardrobe.sqlite3` via the schema in `wardrobe/db.py`:

```sql
CREATE TABLE wear_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    worn_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- full timestamp
    worn_date   TEXT NOT NULL,                            -- YYYY-MM-DD for queries
    item_id     TEXT,                                     -- references items.id
    outfit_id   TEXT,                                     -- references outfits.id
    note        TEXT
);
```

Each row records either an item or an outfit (one of the two id columns is non-null). The table is created automatically on first run via `PRAGMA journal_mode=WAL` + `executescript`.

## DB helpers (`wardrobe/db.py`)

| Function | Description |
|---|---|
| `log_wear(con, *, item_id, outfit_id, note, worn_date)` | Insert a wear event. Requires at least one of `item_id` / `outfit_id`. `worn_date` defaults to today. |
| `get_wear_stats(con, *, item_id, outfit_id)` | Returns `{wear_count, last_worn}` for one item or outfit. |
| `get_all_item_wear_stats(con)` | Returns `{item_id: {wear_count, last_worn}}` for all items with any log entries. |
| `get_all_outfit_wear_stats(con)` | Same for outfits. |
| `recent_wear(con, limit, *, item_id, outfit_id)` | Returns recent wear events, optionally filtered to one item or outfit. |

## API endpoints

### `POST /api/wear`

Log a wear event.

**Request body:**
```json
{ "item_id": "item_abc123", "note": "optional note", "worn_date": "2026-05-12" }
```
or
```json
{ "outfit_id": "outfit_xyz", "worn_date": "2026-05-12" }
```

`worn_date` is optional and defaults to today (server-local date, `YYYY-MM-DD`).

**Response (201):**
```json
{ "worn_date": "2026-05-12", "item_id": "item_abc123", "outfit_id": null, "note": null }
```

### `GET /api/wear`

Fetch recent wear events.

**Query parameters:**
- `limit` — max events to return (default 20)
- `item_id` — filter to a specific item
- `outfit_id` — filter to a specific outfit

**Response (200):** array of wear log rows.

### Enriched item/outfit responses

`GET /api/items`, `GET /api/items/<id>`, and `GET /api/outfits` now include:

```json
{ "wear_count": 3, "last_worn": "2026-04-20" }
```

`last_worn` is `null` for items/outfits that have never been logged.

## UI affordances

- **Item detail modal** — shows "Worn" row (`Last worn Xd ago` / `Never worn`) and a **Mark worn today** button.
- **Saved outfits** (Saved tab) — each outfit card shows the last-worn label and a **Worn today** button.
- Suggested outfits (Plan tab) are ephemeral and have no worn tracking; only saved outfits do.

## Tests

```
python -m unittest tests.test_db_wear -v
```

Run from the project root (`/Users/agent/projects/worktrees/wardrobe-wear-tracking`). No extra dependencies required.
