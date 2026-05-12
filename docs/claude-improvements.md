# Claude Improvement Pass — 2026-05-12

Branch: `improve-claude`

---

## Overview

A focused improvement pass targeting three areas: dressing-room look history, documentation, and test coverage. All changes are backward-compatible (no schema migrations needed for existing data).

---

## 1. Dressing Room — Generated Look History

### Problem

Every time the user generated a dressed-avatar image, the result appeared in the `dressedResults` div but vanished on page refresh. There was no way to browse, revisit, or restore past outfit combinations. Generated files existed on disk (keyed by combo hash) but were invisible to the UI.

### Solution

**DB layer (`wardrobe/db.py`)**

- Added `dressed_looks` table to `SCHEMA` with columns: `id`, `created_at`, `combo_hash` (UNIQUE), `image_path`, `item_ids_json`, `model`, `elapsed_seconds`.
- `INSERT OR IGNORE` semantics on `combo_hash` so re-generating the same combination doesn't create a duplicate row — the original timestamp is preserved.
- Added `insert_dressed_look(con, look)` and `list_dressed_looks(con, limit)` helpers.

**Backend (`wardrobe/web.py`)**

- Imported `connect`, `insert_dressed_look`, `list_dressed_looks` from `db`.
- In `_run_dress_generation()`: after writing the JSON metadata file, write a `dressed_looks` row. Wrapped in `try/except` so a DB failure never breaks the generation response.
- Added `GET /api/dressing/history?limit=N` endpoint: queries `dressed_looks`, resolves item objects, skips rows whose image file has been deleted, returns JSON.

**Frontend (`wardrobe/web.py` — HTML/CSS/JS)**

- Added "Recent Looks" section (`#dressingHistory` / `#historyGrid`) at the bottom of the Dress tab.
- History loads automatically when the Dress tab opens (`initDressing`) and refreshes after each successful generation.
- Each history card shows: dressed-avatar thumbnail (2:3 ratio), locale-formatted timestamp, per-slot category pills, and a "Re-dress this look" button.
- `restoreDressingLook(itemIds)` maps item IDs back to `selectedDressing` slots by category, persists to `localStorage`, updates all slot UI, and scrolls to the avatar stage.
- Responsive history grid: 2 columns (mobile) → 3 (≥ 600 px) → 4 (≥ 900 px).

### Files changed

- `wardrobe/db.py` — new table, two new functions
- `wardrobe/web.py` — import, persistence, endpoint, HTML section, CSS rules, JS functions

### Rationale

The biggest UX gap was losing generated looks on refresh. The combo-hash file cache already existed; the only missing piece was a DB index and a UI to surface it. The `INSERT OR IGNORE` approach keeps history clean without requiring a migration on existing databases.

---

## 2. Documentation

### Problem

No CLAUDE.md (developer onboarding) and no record of what Claude has changed or recommended.

### Solution

**`CLAUDE.md`** (new)

- Architecture table (layer → tech → file)
- Directory layout
- How to run the server and CLI
- Database schema summary
- How to run tests
- How to add a new API endpoint
- Key design constraints (no framework deps, single-user, local-only, optional Gemini)

**`docs/claude-improvements.md`** (this file)

- Full changelog for this improvement pass

### Files changed

- `CLAUDE.md` (new)
- `docs/claude-improvements.md` (new)

---

## 3. Test Coverage

### Problem

Only `wardrobe/vision.py` had tests. `db.py` and `outfits.py` — the two modules with the most business logic — had none.

### Solution

**`tests/test_db.py`** (12 tests)

- Schema creation (all four tables present, idempotent on double-run)
- `insert_outfit` / `list_outfits` round-trip and ordering
- `insert_outfit_feedback` single and multiple rows
- `insert_dressed_look` / `list_dressed_looks`: round-trip, `INSERT OR IGNORE` deduplication, limit, item_ids JSON fidelity, model field storage

All tests use `sqlite3.connect(":memory:")` + `executescript(SCHEMA)` — no filesystem I/O, no real DB touched.

**`tests/test_outfits.py`** (31 tests)

- `item_profile`: all required keys, pattern strength (solid/subtle/statement), formality (casual/smart-casual/formal), weight (light/warm/mid), color lowercasing
- `_color_temp`: neutral, warm, cool, mixed, empty set
- `score_outfit`: range clamping, completeness bonus, shoes bonus, outerwear weather bonus/penalty, neutral palette bonus, pattern-clash penalty, reason list types and ≤5 cap, empty-parts safety
- `_auto_name`: string output, color/subcategory content, join separator, capped at 3 items

**`tests/test_vision.py`** (22 tests)

- Pure-function coverage for `nearest_color_name`, `visual_tags`, `image_embedding`, and `dominant_colors` using synthetic PIL images.

All tests use synthetic item dicts/images — no catalog, no DB, no network.

### Test run

```
node --check /tmp/wardrobe_claude_web.js
py_compile wardrobe/web.py wardrobe/db.py wardrobe/outfits.py wardrobe/vision.py
65 passed in 0.14s
```

(65 tests total)

### Files changed

- `tests/__init__.py` (new)
- `tests/test_db.py` (new)
- `tests/test_outfits.py` (new)
- `tests/test_vision.py` (new)

---

## Commits

| Hash | Message |
|---|---|
| `ee8607f` | feat: add dressing room look history — DB table, API, and Recent Looks UI |
| `cb38395` | test: add test_db and test_outfits covering scoring and DB layer |
| `6ae14b3` | docs: add CLAUDE.md developer guide and claude-improvements changelog |
| `(follow-up)` | test: add vision coverage from Claude pass |
| `(follow-up)` | docs: finalize Claude pass validation notes |

---

## Follow-up Ideas

1. **Backfill history from disk** — On server startup, scan `dressed/` for existing `.json` metadata files and `INSERT OR IGNORE` into `dressed_looks`. This surfaces looks generated before this feature was added.
2. **Delete look from history** — Add a `DELETE /api/dressing/history/<id>` endpoint and a trash button on history cards.
3. **Pin / favourite a look** — Add a `pinned` boolean column to `dressed_looks` and a "Pin" button; show pinned looks at the top of history.
4. **Outfit → dressing pipeline** — "Dress this outfit" button on a saved/suggested outfit card that pre-fills the dressing-room slots and generates immediately.
5. **Replace `alert()` calls** — The `saveSuggestion` and `rate` JS functions still use `alert()` / `alert()`. Replace with inline toast/status messages (noted in the existing UX review).
6. **Pagination / infinite scroll** — History is currently capped at 24 items; add load-more or pagination for users with many generations.
7. **Look sharing** — Export a history card as a PNG composite (dressed image + item strip) for sharing.

---

## Ambitious Avatar Studio Follow-up — 2026-05-12

- Reworked the Dress tab into a cinematic avatar atelier with a large editorial hero, glowing body-zone stage, slot rail, scene picker, and richer copy.
- Added vibe preset buttons (Minimal, Streetwear, Summer, Night Out, Chaos fit) that auto-pick catalog pieces from local item metadata.
- Added scene direction to dressing generation payload/prompt so generated looks can target studio, street, loft, runway, or rooftop moods.
- Replaced the plain generation status with staged progress storytelling, a shimmer skeleton preview card, and toast feedback.
- Added responsive studio/console/lookbook styling without new dependencies.
