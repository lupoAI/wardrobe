# Wardrobe — Developer & Operator Guide

## What this is

A self-hosted, single-user wardrobe catalog and outfit planner. It ingests clothing photos, extracts color/texture metadata locally, scores outfit combinations algorithmically, and uses Gemini Flash for avatar try-on image generation. No external hosting required; all data lives in `data/` under the project root.

## Stack at a glance

| Layer | Tech | Key file |
|---|---|---|
| Web server | Pure-Python `ThreadingHTTPServer` | `wardrobe/web.py` |
| SPA frontend | Vanilla HTML/CSS/JS embedded in `web.py` | `wardrobe/web.py` → `CSS` / `JS` constants |
| Database | SQLite (WAL mode) | `wardrobe/db.py`, `data/wardrobe.sqlite3` |
| Vision | Offline PIL + NumPy (no network) | `wardrobe/vision.py` |
| Outfit scoring | Pure Python heuristics | `wardrobe/outfits.py` |
| Image generation | Gemini Flash via `openclaw` CLI | `wardrobe/thumbnails.py`, `wardrobe/web.py` |
| CLI | argparse | `wardrobe/cli.py` |

## Directory layout

```
wardrobe/           Python package (server + business logic)
data/
  images/           Original clothing photos
  embeddings/       168-dim numpy vectors (one .npy per item)
  thumbnails/       Game-style generated PNGs/JPGs
  thumbnail_metadata/
  user/
    salo/
      avatar/       neutral_avatar.jpg + neutral_avatar_transparent.png
      dressed/      Gemini-generated dressed-avatar images + JSON metadata
  wardrobe.sqlite3  Main database
docs/               Human-readable docs
prompts/            Gemini prompt templates
tests/              Pytest test suite
```

## Running the server

```bash
# One-time install (editable)
pip install -e .

# Start the web UI (default port 8765)
wardrobe-web

# Or with a custom port
wardrobe-web --port 9000
```

Open `http://127.0.0.1:8765` in a browser, or the LAN IP printed at startup for mobile access.

## CLI commands

```bash
wardrobe init                    # create data dirs and DB schema
wardrobe add path/to/photo.jpg   # ingest a clothing item
wardrobe list                    # list all items
wardrobe similar <item_id>       # find visually similar items
wardrobe thumbnails              # generate game-style thumbnails for all items
```

## Database schema

Three core tables — all created by `db.connect()`:

- **items** — one row per clothing photo; stores path, category, colors, tags, embedding path.
- **outfits** — saved outfit combinations with scoring metadata.
- **outfit_feedback** — thumbs-up/down ratings linked to an outfit.
- **dressed_looks** — each Gemini-generated avatar image, keyed by `combo_hash` (sha256[:16] of sorted item IDs). `INSERT OR IGNORE` keeps the original timestamp on repeated generations of the same combo.

Schema is idempotent (`CREATE TABLE IF NOT EXISTS`) so `connect()` is safe to call on every startup.

## Image generation (Gemini)

Both thumbnail generation and avatar dressing call `openclaw infer image edit` subprocess with the Gemini Flash image-editing model. Requires `openclaw` to be installed and authenticated separately. Generation results are cached on disk (check combo_hash file before running); the dressed-look cache also has a DB entry in `dressed_looks` so the Recent Looks UI can list them without scanning the filesystem.

## Running tests

```bash
# From the project root
python -m pytest tests/ -v
```

All tests use synthetic data (PIL images, in-memory SQLite); no real photos or network calls required.

Test files:
- `tests/test_vision.py` — color extraction, pattern detection, embeddings
- `tests/test_outfits.py` — outfit scoring, item profiling, auto-naming
- `tests/test_db.py` — schema creation, insert/list for all tables

## Adding a new API endpoint

1. For GET: add a branch in `WardrobeHandler.do_GET` before the final 404.
2. For POST: add a branch in `WardrobeHandler.do_POST`.
3. For HTML changes: edit the `f`-string in `_render_page()`.
4. For CSS/JS: append to the `CSS` or `JS` module-level constants.

The entire frontend is a single-page app rendered server-side. Tab switching is client-side JS; data is fetched from `/api/*` endpoints.

## Key design constraints

- **No framework dependencies** — only `pillow` and `numpy`. The HTTP server is stdlib `http.server`.
- **Single user** — no auth, no multi-tenancy. Paths are hardcoded to `data/user/salo/`.
- **Local-only** — designed to run on a home server or laptop. LAN access is intentional for mobile.
- **Gemini dependency is optional** — the catalog, outfit planner, and similarity search all work offline. Only avatar dressing and thumbnail generation need `openclaw` + Gemini.
