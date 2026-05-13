from __future__ import annotations

import argparse
import html
import hashlib
import json
import mimetypes
import os
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .catalog import items
from .config import IMAGE_DIR, PROJECT_ROOT, THUMBNAIL_DIR
from .db import (
    connect as db_connect,
    get_all_item_wear_stats,
    get_all_outfit_wear_stats,
    get_wear_stats,
    log_wear as db_log_wear,
    recent_wear as db_recent_wear,
)
from .outfits import rate_outfit, save_outfit, saved_outfits, suggest_outfits


USER_DIR = PROJECT_ROOT / "data" / "user" / "salo"
AVATAR_DIR = USER_DIR / "avatar"
DRESSED_DIR = USER_DIR / "dressed"
BASE_AVATAR_PATH = AVATAR_DIR / "neutral_avatar.jpg"
BASE_AVATAR_TRANSPARENT_PATH = AVATAR_DIR / "neutral_avatar_transparent.png"
DRESS_MODEL = "google/gemini-3.1-flash-image-preview"


def _asset_path(item: dict) -> str:
    path = Path(item["image_path"])
    try:
        rel = path.resolve().relative_to(IMAGE_DIR.resolve())
    except ValueError:
        rel = path.name
    return "/images/" + quote(str(rel).replace(os.sep, "/"))


def _thumbnail_path(item: dict) -> Path:
    png = THUMBNAIL_DIR / f"{item['id']}.png"
    if png.is_file():
        return png
    return THUMBNAIL_DIR / f"{item['id']}.jpg"


def _thumbnail_url(item: dict) -> str:
    thumb = _thumbnail_path(item)
    if thumb.is_file():
        return "/thumbnails/" + quote(thumb.name)
    return _asset_path(item)


def _user_asset_url(path: Path) -> str:
    rel = path.resolve().relative_to(USER_DIR.resolve())
    return "/user/" + quote(str(rel).replace(os.sep, "/"))


def _avatar_url() -> str:
    if BASE_AVATAR_TRANSPARENT_PATH.is_file():
        return _user_asset_url(BASE_AVATAR_TRANSPARENT_PATH)
    return _user_asset_url(BASE_AVATAR_PATH)


def _dress_prompt(selected: list[dict]) -> str:
    garments = "\n".join(
        f"- {row.get('category')}/{row.get('subcategory') or 'item'}: {row.get('notes') or row['id']}"
        for row in selected
    )
    return f"""Dress the avatar in the selected garments using the reference images.

Inputs: the first image is the base avatar. Every following image is a real clothing reference to apply to the avatar.

Selected garments:
{garments}

Requirements:
- Preserve the avatar identity, face, body proportions, neutral forward-facing pose, and full-body framing.
- Dress the avatar naturally with the selected garments only. Match each garment's real color, material, silhouette, neckline/waist/opening shape, hems, shoes, texture, and distinctive details from the original photos.
- Layer clothing realistically: outerwear over tops, bottoms at waist/legs, shoes on feet, accessories only if selected.
- Keep a clean neutral fitting-room/avatar look with plain neutral light grey background and soft studio lighting.
- No extra people, mannequins, hangers, mirror, phone, text, logos unless actually present on the garment, UI, frame, or decorative background.
- Non-sexualized, realistic anatomy, no pose change beyond tiny natural clothing fit adjustments."""


def _run_dress_generation(item_ids: list[str], timeout: int = 240) -> dict:
    DRESSED_DIR.mkdir(parents=True, exist_ok=True)
    all_items = {row["id"]: row for row in items()}
    selected = [all_items[item_id] for item_id in item_ids if item_id in all_items]
    if not selected:
        raise ValueError("Choose at least one wardrobe item")
    if not BASE_AVATAR_PATH.is_file():
        raise FileNotFoundError(f"Missing avatar: {BASE_AVATAR_PATH}")

    canonical_item_ids = sorted(row["id"] for row in selected)
    combo_hash = hashlib.sha256("|".join(canonical_item_ids).encode("utf-8")).hexdigest()[:16]
    out = DRESSED_DIR / f"dressed_avatar_{combo_hash}.jpg"
    meta_out = DRESSED_DIR / f"dressed_avatar_{combo_hash}.json"
    if out.is_file() and meta_out.is_file():
        try:
            meta = json.loads(meta_out.read_text())
            meta["image_url"] = _user_asset_url(out)
            meta["cached"] = True
            return meta
        except (OSError, json.JSONDecodeError):
            pass
    prompt = _dress_prompt(selected)
    cmd = [
        "openclaw", "infer", "image", "edit",
        "--file", str(BASE_AVATAR_PATH),
    ]
    for row in selected:
        cmd.extend(["--file", str(Path(row["image_path"]))])
    cmd.extend([
        "--prompt", prompt,
        "--model", DRESS_MODEL,
        "--aspect-ratio", "2:3",
        "--resolution", "2K",
        "--output", str(out),
        "--json",
        "--timeout-ms", str(timeout * 1000),
    ])
    started = time.time()
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout + 45)
    if proc.returncode != 0:
        raise RuntimeError(f"Gemini dress generation failed: {proc.stderr or proc.stdout}")
    data = json.loads(proc.stdout)
    outputs = data.get("outputs") or []
    generated_path = Path(outputs[0].get("path", out)) if outputs else out
    if not generated_path.is_file():
        raise RuntimeError(f"No dressed avatar image was generated: {data}")
    meta = {
        "image_path": str(generated_path),
        "image_url": _user_asset_url(generated_path),
        "combo_hash": combo_hash,
        "item_ids": canonical_item_ids,
        "selected_order": [row["id"] for row in selected],
        "items": [_json_item(row) for row in selected],
        "model": DRESS_MODEL,
        "prompt": prompt,
        "elapsed_seconds": round(time.time() - started, 2),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider_output": outputs[0] if outputs else data,
    }
    meta_out.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return meta


def _host_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _filtered_items(query: dict[str, list[str]]) -> list[dict]:
    category = (query.get("category") or [""])[0].strip()
    q = (query.get("q") or [""])[0].strip().lower()
    rows = items(category or None)
    if q:
        def haystack(row: dict) -> str:
            parts = [
                row.get("id", ""), row.get("category", ""), row.get("subcategory", ""),
                row.get("notes", ""), row.get("original_filename", ""),
                " ".join(row.get("colors", [])), " ".join(row.get("tags", [])),
            ]
            return " ".join(p for p in parts if p).lower()
        rows = [row for row in rows if q in haystack(row)]
    return rows


def _categories(rows: list[dict]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))


def _json_item(row: dict, wear: dict | None = None) -> dict:
    w = wear or {}
    return {
        **row,
        "image_url": _asset_path(row),
        "original_image_url": _asset_path(row),
        "thumbnail_url": _thumbnail_url(row),
        "has_thumbnail": _thumbnail_path(row).is_file(),
        "wear_count": w.get("wear_count", 0),
        "last_worn": w.get("last_worn"),
    }


def _json_outfit(outfit: dict, wear: dict | None = None) -> dict:
    w = wear or {}
    return {
        **outfit,
        "items": [_json_item(item) for item in outfit.get("items", [])],
        "wear_count": w.get("wear_count", 0),
        "last_worn": w.get("last_worn"),
    }


def _render_page(query: dict[str, list[str]]) -> bytes:
    all_rows = items()
    rows = _filtered_items(query)
    selected = (query.get("category") or [""])[0].strip()
    q = (query.get("q") or [""])[0].strip()
    cats = _categories(all_rows)

    cards = "\n".join(_render_card(row) for row in rows)
    empty = "" if rows else "<div class='empty'>No pieces match that filter.</div>"
    chips = [f"<a class='chip {'active' if not selected else ''}' href='/'>All <span>{len(all_rows)}</span></a>"]
    for cat, count in cats:
        href = "/?category=" + quote(cat)
        chips.append(f"<a class='chip {'active' if selected == cat else ''}' href='{href}'>{html.escape(cat)} <span>{count}</span></a>")

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>Wardrobe</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">Local catalog</p>
        <h1>Wardrobe</h1>
        <p class="sub">{len(all_rows)} pieces indexed · outfit planning beta</p>
      </div>
      <div class="stat"><strong>{len(cats)}</strong><span>categories</span></div>
    </header>

    <nav class="tabs">
      <button class="tab active" data-tab="items" onclick="showTab('items')">Pieces</button>
      <button class="tab" data-tab="dressing" onclick="showTab('dressing'); initDressing()">Dress</button>
      <button class="tab" data-tab="planner" onclick="showTab('planner')">Plan</button>
      <button class="tab" data-tab="saved" onclick="showTab('saved'); loadSavedOutfits()">Saved</button>
    </nav>

    <section id="itemsTab" class="tab-panel active-panel">
      <form class="search" method="get" action="/">
        <input type="search" name="q" value="{html.escape(q)}" placeholder="Search color, tag, item id…" autocomplete="off" />
        {f'<input type="hidden" name="category" value="{html.escape(selected)}" />' if selected else ''}
        <button>Search</button>
      </form>
      <div class="view-toggle" role="group" aria-label="Image view mode">
        <span>Images</span>
        <button type="button" class="mode active" data-mode="original" onclick="setImageMode('original')">Photos</button>
        <button type="button" class="mode" data-mode="thumbnail" onclick="setImageMode('thumbnail')">Game icons</button>
      </div>
      <nav class="chips" aria-label="Categories">{''.join(chips)}</nav>
      <main class="grid">{cards}{empty}</main>
    </section>

    <section id="dressingTab" class="tab-panel">
      <div class="dressing-room">
        <div class="avatar-stage">
          <div class="avatar-hint">Tap a body area → choose clothes below</div>
          <img id="avatarBase" class="avatar-base" src="{html.escape(_avatar_url())}" alt="Neutral avatar" />
          <button type="button" class="body-hotspot head" data-slot="accessories" aria-pressed="false">Accessories</button>
          <button type="button" class="body-hotspot torso" data-slot="tops" aria-pressed="false">Top</button>
          <button type="button" class="body-hotspot outer" data-slot="outerwear" aria-pressed="false">Outerwear</button>
          <button type="button" class="body-hotspot legs" data-slot="bottoms" aria-pressed="false">Bottom</button>
          <button type="button" class="body-hotspot feet" data-slot="shoes" aria-pressed="false">Shoes</button>
        </div>
        <aside class="dresser-panel">
          <p class="eyebrow">Character dressing</p>
          <h2 class="section-title">Build the look</h2>
          <p class="help">1. Tap the avatar area you want to dress. 2. Pick the clothing card below. 3. Generate the final try-on image.</p>
          <div id="slotButtons" class="slot-buttons"></div>
          <p id="slotCount" class="slot-count">0 of 5 slots filled</p>
          <div id="selectedLook" class="selected-look"></div>
          <button id="generateDressed" type="button" class="primary wide" onclick="generateDressedAvatar()">Dress avatar with Gemini</button>
          <div id="dressStatus" class="dress-status"></div>
        </aside>
      </div>
      <div class="picker-head">
        <div>
          <p class="eyebrow">Picker below</p>
          <h2 class="section-title" id="pickerTitle">Choose a top</h2>
          <p id="pickerHelp" class="picker-help">These are Top pieces. Tap a card to assign it to the active slot.</p>
        </div>
        <div class="picker-actions">
          <div class="view-toggle compact" role="group" aria-label="Dress picker image mode">
            <span>Images</span>
            <button type="button" class="mode active" data-mode="original" onclick="setImageMode('original')">Photos</button>
            <button type="button" class="mode" data-mode="thumbnail" onclick="setImageMode('thumbnail')">Icons</button>
          </div>
          <button type="button" class="primary ghost" onclick="clearDressingSlot()">Clear slot</button>
        </div>
      </div>
      <div id="dresserGrid" class="grid"></div>
      <div id="dressedResults" class="dressed-results"></div>
    </section>

    <section id="plannerTab" class="tab-panel">
      <div class="planner-card">
        <div>
          <p class="eyebrow">Outfit generator</p>
          <h2 class="section-title">Pick the context</h2>
          <p class="help">I’ll score combinations by palette, pattern balance, occasion, fabric weight and completeness.</p>
        </div>
        <div class="controls">
          <label>Occasion<select id="occasion"><option>casual</option><option>work</option><option>dinner</option><option>date</option><option>travel</option><option>smart</option></select></label>
          <label>Weather<select id="weather"><option>mild</option><option>hot</option><option>cold</option><option>rainy</option></select></label>
          <label>Vibe<select id="vibe"><option>balanced</option><option>minimal</option><option>statement</option></select></label>
          <button class="primary" onclick="loadSuggestions()">Generate outfits</button>
        </div>
      </div>
      <div id="suggestions" class="outfit-list"><div class="empty">Tap “Generate outfits” to get combinations.</div></div>
    </section>

    <section id="savedTab" class="tab-panel">
      <div class="planner-card compact"><div><p class="eyebrow">Saved outfits</p><h2 class="section-title">Looks you liked</h2></div><button class="primary ghost" onclick="loadSavedOutfits()">Refresh</button></div>
      <div id="savedOutfits" class="outfit-list"><div class="empty">No saved outfits yet.</div></div>
    </section>
  </div>

  <dialog id="detail"><button class="close" onclick="detail.close()">×</button><div id="detailBody"></div></dialog>

  <script>{JS}</script>
</body>
</html>"""
    return page.encode("utf-8")


def _render_card(row: dict) -> str:
    colors = "".join(f"<span class='swatch'>{html.escape(c)}</span>" for c in row.get("colors", [])[:3])
    tags = "".join(f"<span class='pill'>{html.escape(t)}</span>" for t in row.get("tags", [])[:4])
    notes = html.escape(row.get("notes") or row["id"])
    sub = html.escape(row.get("subcategory") or row.get("category") or "")
    item_id = html.escape(row["id"])
    img = html.escape(_asset_path(row))
    thumb = html.escape(_thumbnail_url(row))
    return f"""
      <article class="card" onclick="openItem('{item_id}')" tabindex="0" onkeydown="if(event.key==='Enter') openItem('{item_id}')">
        <div class="photo"><img class="wardrobe-img" loading="lazy" src="{img}" data-original="{img}" data-thumbnail="{thumb}" alt="{notes}" /></div>
        <div class="card-copy">
          <div class="row"><span class="type">{sub}</span><code>{item_id.replace('item_', '')}</code></div>
          <h2>{notes}</h2>
          <div class="pills">{colors}</div>
          <div class="pills muted">{tags}</div>
        </div>
      </article>"""


CSS = r"""
:root { color-scheme: light; --bg:#f6f2ea; --ink:#171613; --muted:#736b60; --line:rgba(23,22,19,.12); --card:rgba(255,255,255,.72); --strong:rgba(255,255,255,.93); --accent:#111827; --accent2:#c67a45; --good:#166534; --shadow:0 18px 50px rgba(33,28,20,.12); }
*{box-sizing:border-box} body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",sans-serif;background:radial-gradient(circle at 12% 0%,rgba(198,122,69,.18),transparent 30rem),radial-gradient(circle at 88% 8%,rgba(38,70,83,.14),transparent 28rem),var(--bg);color:var(--ink)}
.shell{width:min(1180px,100%);margin:0 auto;padding:max(18px,env(safe-area-inset-top)) 14px 40px}.hero{display:flex;justify-content:space-between;gap:18px;align-items:end;padding:22px 6px 18px}.eyebrow{margin:0 0 6px;text-transform:uppercase;letter-spacing:.14em;font-size:11px;color:var(--muted);font-weight:800}h1{margin:0;font-size:clamp(42px,12vw,84px);line-height:.86;letter-spacing:-.075em}.sub{margin:12px 0 0;color:var(--muted);font-weight:600}.stat{min-width:94px;padding:16px;border:1px solid var(--line);background:var(--card);backdrop-filter:blur(16px);border-radius:24px;text-align:center;box-shadow:var(--shadow)}.stat strong{display:block;font-size:28px}.stat span{color:var(--muted);font-size:12px;font-weight:700}
.tabs{position:sticky;top:0;z-index:7;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:8px;margin-bottom:12px;background:rgba(246,242,234,.78);backdrop-filter:blur(18px);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow)}.tab{border:0;border-radius:16px;padding:13px 10px;background:transparent;font:inherit;font-weight:900;color:var(--muted)}.tab.active{background:var(--ink);color:white}.tab-panel{display:none}.active-panel{display:block}
.search{display:flex;gap:8px;padding:8px;background:rgba(255,255,255,.45);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow)}.search input{min-width:0;flex:1;border:0;outline:0;border-radius:16px;padding:15px 14px;background:rgba(255,255,255,.78);color:var(--ink);font:inherit;font-weight:650}.search button,.primary{border:0;border-radius:16px;padding:0 18px;background:var(--accent);color:white;font-weight:900;min-height:48px}.primary.ghost{background:rgba(23,22,19,.08);color:var(--ink)}
.view-toggle{display:flex;align-items:center;gap:8px;width:max-content;max-width:100%;margin:12px 2px 0;padding:7px;border:1px solid var(--line);background:rgba(255,255,255,.52);border-radius:18px;box-shadow:0 8px 24px rgba(33,28,20,.08);overflow-x:auto}.view-toggle.compact{margin:0;box-shadow:none;background:rgba(255,255,255,.66)}.view-toggle span{padding:0 7px;color:var(--muted);font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:.08em}.mode{white-space:nowrap;border:0;border-radius:13px;padding:10px 12px;background:transparent;color:var(--muted);font:inherit;font-size:13px;font-weight:900}.mode.active{background:var(--ink);color:white}.photo img.thumbnail-mode,.strip img.thumbnail-mode{object-fit:contain;background:transparent;padding:7%}
.chips{display:flex;gap:9px;overflow-x:auto;padding:16px 2px 14px;scrollbar-width:none}.chips::-webkit-scrollbar{display:none}.chip{white-space:nowrap;text-decoration:none;color:var(--ink);border:1px solid var(--line);background:rgba(255,255,255,.55);padding:10px 13px;border-radius:999px;font-weight:800;text-transform:capitalize}.chip span{color:var(--muted);margin-left:5px}.chip.active{background:var(--ink);color:white;border-color:var(--ink)}.chip.active span{color:rgba(255,255,255,.65)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.card{border:1px solid var(--line);background:var(--card);backdrop-filter:blur(16px);border-radius:26px;overflow:hidden;box-shadow:0 12px 34px rgba(33,28,20,.10);cursor:pointer;transition:transform .18s ease}.card:active{transform:scale(.985)}.photo{aspect-ratio:4/5;background:#e8dfd2;overflow:hidden}.photo img{width:100%;height:100%;object-fit:cover;display:block}.card-copy{padding:12px}.row{display:flex;justify-content:space-between;gap:8px;align-items:center}.type{color:var(--accent2);text-transform:capitalize;font-size:12px;font-weight:900}code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;color:var(--muted)}h2{margin:7px 0 10px;font-size:14px;line-height:1.18;letter-spacing:-.02em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.pills{display:flex;flex-wrap:wrap;gap:5px}.pills.muted{margin-top:7px;opacity:.72}.pill,.swatch{display:inline-flex;align-items:center;min-height:24px;padding:5px 8px;border-radius:999px;background:rgba(23,22,19,.07);font-size:11px;font-weight:800;color:#3a352e}.swatch{background:rgba(198,122,69,.13)}.empty{padding:42px 16px;border:1px dashed var(--line);border-radius:24px;text-align:center;color:var(--muted);font-weight:800;grid-column:1/-1}
.planner-card{border:1px solid var(--line);background:var(--card);backdrop-filter:blur(16px);border-radius:28px;box-shadow:var(--shadow);padding:18px;margin-bottom:14px}.planner-card.compact{display:flex;align-items:center;justify-content:space-between;gap:16px}.section-title{display:block;overflow:visible;-webkit-line-clamp:unset;margin:0 0 8px;font-size:28px}.help{color:var(--muted);font-weight:650;margin:0 0 16px;line-height:1.35}.controls{display:grid;grid-template-columns:1fr;gap:10px}.controls label{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:900}.controls select{width:100%;margin-top:5px;border:1px solid var(--line);background:var(--strong);border-radius:16px;padding:14px;font:inherit;font-weight:850;color:var(--ink)}
.outfit-list{display:grid;gap:14px}.outfit{border:1px solid var(--line);background:var(--strong);border-radius:28px;overflow:hidden;box-shadow:0 12px 34px rgba(33,28,20,.10)}.outfit-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px}.score{width:58px;height:58px;border-radius:50%;display:grid;place-items:center;background:rgba(22,101,52,.12);color:var(--good);font-weight:1000;font-size:18px}.outfit-title{min-width:0}.outfit-title h3{margin:0 0 4px;font-size:18px;line-height:1.1}.outfit-title p{margin:0;color:var(--muted);font-size:12px;font-weight:800}.strip{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;background:#eadfce}.strip img{width:100%;aspect-ratio:4/5;object-fit:cover;display:block}.strip.two{grid-template-columns:repeat(2,1fr)}.strip.three{grid-template-columns:repeat(3,1fr)}.outfit-body{padding:14px}.reasons{margin:0 0 12px;padding-left:18px;color:var(--muted);font-weight:700;font-size:13px;line-height:1.3}.actions{display:flex;gap:8px;flex-wrap:wrap}.actions button{border:0;border-radius:14px;min-height:42px;padding:0 13px;background:rgba(23,22,19,.08);font-weight:900;color:var(--ink)}.actions .save{background:var(--accent);color:white}.actions .yes{background:rgba(22,101,52,.12);color:var(--good)}.actions .no{background:rgba(153,27,27,.10);color:#991b1b}
dialog{width:min(760px,calc(100vw - 20px));max-height:min(860px,calc(100dvh - 20px));border:0;border-radius:30px;padding:0;background:var(--strong);box-shadow:0 30px 100px rgba(0,0,0,.35);overflow:auto}dialog::backdrop{background:rgba(20,18,15,.52);backdrop-filter:blur(8px)}.close{position:sticky;float:right;top:10px;right:10px;z-index:2;margin:10px;border:0;width:42px;height:42px;border-radius:50%;background:rgba(0,0,0,.72);color:white;font-size:28px;line-height:1}.detail-img{width:100%;max-height:62dvh;object-fit:contain;background:#eadfce;display:block}.detail-copy{padding:18px}.detail-copy h2{display:block;overflow:visible;-webkit-line-clamp:unset;font-size:23px;margin-bottom:18px}.meta{display:grid;grid-template-columns:86px 1fr;gap:12px;padding:11px 0;border-top:1px solid var(--line);align-items:start}.meta b{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}.meta span{overflow-wrap:anywhere}
.wide{width:100%}.dressing-room{display:grid;grid-template-columns:1fr;gap:14px;margin-bottom:16px}.avatar-stage{position:relative;min-height:560px;border:1px solid var(--line);border-radius:32px;background:linear-gradient(180deg,#eee9df,#dfd5c8);box-shadow:var(--shadow);overflow:hidden;display:grid;place-items:center}.avatar-hint{position:absolute;top:14px;left:14px;right:14px;z-index:2;padding:10px 12px;border-radius:18px;background:rgba(255,255,255,.82);border:1px solid var(--line);font-weight:950;text-align:center;box-shadow:0 8px 24px rgba(33,28,20,.10)}.avatar-base{max-height:92%;max-width:86%;object-fit:contain;filter:drop-shadow(0 18px 28px rgba(33,28,20,.18))}.body-hotspot{position:absolute;border:1px solid rgba(255,255,255,.82);background:rgba(17,24,39,.78);color:white;border-radius:999px;padding:9px 12px;font-weight:950;box-shadow:0 8px 28px rgba(0,0,0,.2);cursor:pointer;transition:transform .16s ease,background .16s ease,box-shadow .16s ease}.body-hotspot.active{background:var(--accent2);box-shadow:0 0 0 5px rgba(198,122,69,.22),0 12px 34px rgba(0,0,0,.24)}.body-hotspot.head{top:12%;left:50%;transform:translateX(-50%)}.body-hotspot.torso{top:31%;left:50%;transform:translateX(-50%)}.body-hotspot.outer{top:38%;right:13%}.body-hotspot.legs{top:57%;left:50%;transform:translateX(-50%)}.body-hotspot.feet{bottom:7%;left:50%;transform:translateX(-50%)}.dresser-panel,.picker-head{border:1px solid var(--line);background:var(--card);backdrop-filter:blur(16px);border-radius:28px;padding:16px;box-shadow:var(--shadow)}.slot-count{margin:4px 0 10px;color:var(--accent2);font-weight:1000}.slot-buttons{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.slot-btn{border:1px solid var(--line);background:rgba(255,255,255,.64);border-radius:999px;padding:10px 12px;font-weight:950;text-transform:capitalize;cursor:pointer}.slot-btn.active{background:var(--ink);color:#fff}.selected-look{display:grid;gap:8px;margin:12px 0}.selected-slot{display:grid;grid-template-columns:52px 1fr auto;gap:10px;align-items:center;padding:8px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.55)}.selected-slot.active{border-color:rgba(198,122,69,.72);background:rgba(198,122,69,.12)}.selected-slot img{width:52px;height:64px;object-fit:contain;background:#eee2d3;border-radius:12px}.selected-slot b{text-transform:capitalize}.selected-slot small{display:block;color:var(--muted);font-weight:850;margin-top:2px}.selected-slot button{border:0;border-radius:12px;padding:8px 10px;background:rgba(23,22,19,.08);font-weight:900;cursor:pointer}.picker-head{position:sticky;top:76px;z-index:6;display:grid;grid-template-columns:1fr;gap:12px;margin-bottom:12px}.picker-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.picker-help{margin:0;color:var(--muted);font-weight:800}.dresser-choice.selected{outline:4px solid rgba(22,101,52,.22);border-color:rgba(22,101,52,.55)}.dresser-choice.selected h2:after{content:' ✓ Selected';color:var(--good);font-weight:1000}.dress-status{margin-top:10px;color:var(--muted);font-weight:800}.dressed-results{margin-top:18px;display:grid;gap:14px}.dressed-card{border:1px solid var(--line);background:var(--strong);border-radius:28px;overflow:hidden;box-shadow:var(--shadow)}.dressed-card img{width:100%;display:block;background:#eee9df}.dressed-card .detail-copy{padding:14px}
@media (min-width:900px){.dressing-room{grid-template-columns:minmax(360px,560px) 1fr}.avatar-stage{min-height:680px}.dressed-results{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:720px){.shell{padding-left:24px;padding-right:24px}.grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.card-copy{padding:15px}h2{font-size:16px}.controls{grid-template-columns:repeat(4,1fr);align-items:end}.outfit-list{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (min-width:1040px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}.outfit-list{grid-template-columns:repeat(3,minmax(0,1fr))}}
.worn-note{margin:0 0 10px;font-size:12px;font-weight:800;color:var(--muted)}.actions .worn{background:rgba(198,122,69,.13);color:#7c4a1e}
"""


JS = r"""
function readJsonStorage(key, fallback){
  try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); }
  catch(e){ localStorage.removeItem(key); return fallback; }
}
let imageMode = localStorage.getItem('wardrobeImageMode') || 'original';
function imageFor(item){ return imageMode === 'thumbnail' ? (item.thumbnail_url || item.image_url) : (item.original_image_url || item.image_url); }
function setImageMode(mode){
  imageMode = mode === 'thumbnail' ? 'thumbnail' : 'original';
  localStorage.setItem('wardrobeImageMode', imageMode);
  document.querySelectorAll('.mode').forEach(b=>b.classList.toggle('active', b.dataset.mode===imageMode));
  document.querySelectorAll('img.wardrobe-img').forEach(img=>{
    img.src = imageMode === 'thumbnail' ? (img.dataset.thumbnail || img.dataset.original) : img.dataset.original;
    img.classList.toggle('thumbnail-mode', imageMode === 'thumbnail');
  });
}
window.addEventListener('DOMContentLoaded',()=>setImageMode(imageMode));
function showTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.tab===name));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active-panel'));
  document.getElementById(name+'Tab').classList.add('active-panel');
}
async function openItem(id){
  const res=await fetch('/api/items/'+encodeURIComponent(id)); const item=await res.json();
  const chips=(item.tags||[]).map(t=>`<span class="pill">${escapeHtml(t)}</span>`).join('');
  const colors=(item.colors||[]).map(t=>`<span class="swatch">${escapeHtml(t)}</span>`).join('');
  const detailImg=imageFor(item);
  document.getElementById('detailBody').innerHTML=`<img class="detail-img ${imageMode==='thumbnail'?'thumbnail-mode':''}" src="${detailImg}" alt="${escapeHtml(item.notes||item.id)}"><div class="detail-copy"><p class="eyebrow">${escapeHtml(item.category)} / ${escapeHtml(item.subcategory||'—')}</p><h2>${escapeHtml(item.notes||item.id)}</h2><div class="meta"><b>ID</b><code>${escapeHtml(item.id)}</code></div><div class="meta"><b>View</b><span>${imageMode==='thumbnail'?(item.has_thumbnail?'Generated thumbnail':'Original fallback'):'Original photo'}</span></div><div class="meta"><b>Created</b><span>${escapeHtml(item.created_at||'')}</span></div><div class="meta"><b>Colors</b><div class="pills">${colors}</div></div><div class="meta"><b>Tags</b><div class="pills">${chips}</div></div><div class="meta"><b>Original</b><span>${escapeHtml(item.original_filename||'')}</span></div><div class="meta"><b>Worn</b><span>${wornLabel(item.last_worn,item.wear_count)}</span></div><div style="padding:14px 0 4px"><button class="primary ghost" onclick="markWorn('item','${escapeHtml(item.id)}','${escapeHtml(item.notes||item.id)}')">Mark worn today</button></div></div>`;
  detail.showModal();
}
async function loadSuggestions(){
  const params=new URLSearchParams({occasion:occasion.value,weather:weather.value,vibe:vibe.value,limit:'12'});
  const box=document.getElementById('suggestions'); box.innerHTML='<div class="empty">Scoring combinations…</div>';
  const outfits=await (await fetch('/api/outfits/suggest?'+params)).json();
  box.innerHTML=outfits.length?outfits.map(o=>renderOutfit(o,true)).join(''):'<div class="empty">No outfits found.</div>';
}
async function loadSavedOutfits(){
  const box=document.getElementById('savedOutfits'); box.innerHTML='<div class="empty">Loading saved looks…</div>';
  const outfits=await (await fetch('/api/outfits')).json();
  box.innerHTML=outfits.length?outfits.map(o=>renderOutfit(o,false)).join(''):'<div class="empty">No saved outfits yet. Save a suggestion first.</div>';
}
function renderOutfit(o,canSave){
  const imgs=(o.items||[]).map(i=>`<img class="wardrobe-img ${imageMode==='thumbnail'?'thumbnail-mode':''}" src="${imageFor(i)}" data-original="${i.original_image_url||i.image_url}" data-thumbnail="${i.thumbnail_url||i.image_url}" alt="${escapeHtml(i.notes||i.id)}" onclick="openItem('${i.id}')">`).join('');
  const cls=(o.items||[]).length===2?'two':(o.items||[]).length===3?'three':'';
  const reasons=(o.reasons||[]).map(r=>`<li>${escapeHtml(r)}</li>`).join('');
  const itemIds=JSON.stringify((o.items||[]).map(i=>i.id)).replaceAll('"','&quot;');
  const wornNote=!canSave?`<p class="worn-note">${wornLabel(o.last_worn,o.wear_count)}</p>`:'';
  const wornBtn=!canSave?`<button class="worn" onclick="markWorn('outfit','${escapeHtml(o.id)}','${escapeHtml(o.name||autoName(o))}')">Worn today</button>`:'';
  return `<article class="outfit"><div class="outfit-head"><div class="outfit-title"><h3>${escapeHtml(o.name||autoName(o))}</h3><p>${escapeHtml(o.occasion||'casual')} · ${escapeHtml(o.weather||'mild')} · ${escapeHtml(o.vibe||'balanced')}</p></div><div class="score">${o.score}</div></div><div class="strip ${cls}">${imgs}</div><div class="outfit-body"><ul class="reasons">${reasons}</ul>${wornNote}<div class="actions">${canSave?`<button class="save" onclick="saveSuggestion(${itemIds})">Save outfit</button>`:''}<button class="yes" onclick="rate('${escapeHtml(o.id)}',1)">👍 Good</button><button class="no" onclick="rate('${escapeHtml(o.id)}',-1)">👎 No</button>${wornBtn}</div></div></article>`;
}
function autoName(o){return (o.items||[]).map(i=>[(i.colors||[])[0],i.subcategory||i.category].filter(Boolean).join(' ')).slice(0,3).join(' + ')}
async function saveSuggestion(itemIds){
  const payload={item_ids:itemIds,occasion:occasion?.value||'casual',weather:weather?.value||'mild',vibe:vibe?.value||'balanced'};
  const res=await fetch('/api/outfits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!res.ok){ alert('Could not save outfit'); return; }
  const o=await res.json(); alert('Saved: '+(o.name||o.id));
}
async function rate(outfitId,rating){
  if(outfitId.startsWith('suggestion_')){ alert('Save the outfit first, then ratings become durable.'); return; }
  await fetch('/api/outfits/'+encodeURIComponent(outfitId)+'/rate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rating})});
  alert(rating>0?'Marked as good':'Marked as not for you');
}

const dressingSlots = ['tops','outerwear','bottoms','shoes','accessories'];
let dressingItems = [];
let activeSlot = localStorage.getItem('wardrobeActiveSlot') || 'tops';
let selectedDressing = readJsonStorage('wardrobeSelectedDressing', {});
async function initDressing(){
  try{
    if(!dressingItems.length){ dressingItems = await (await fetch('/api/items')).json(); }
    renderSlotButtons(); renderSelectedLook(); selectSlot(activeSlot, false);
  }catch(e){
    const status=document.getElementById('dressStatus');
    if(status) status.textContent='Could not load wardrobe items: '+e.message;
  }
}
function selectSlot(slot, persist=true){
  activeSlot = dressingSlots.includes(slot) ? slot : 'tops';
  if(persist) localStorage.setItem('wardrobeActiveSlot', activeSlot);
  renderSlotButtons(); updateActiveHotspots();
  const title=document.getElementById('pickerTitle'); if(title) title.textContent='Choose '+slotLabel(activeSlot).toLowerCase();
  const help=document.getElementById('pickerHelp'); if(help) help.textContent=`These are ${slotLabel(activeSlot)} pieces. Tap a card below to assign it to the active slot.`;
  const rows=dressingItems.filter(i=>i.category===activeSlot);
  const grid=document.getElementById('dresserGrid'); if(!grid) return;
  grid.innerHTML = rows.length ? rows.map(renderDresserChoice).join('') : '<div class="empty">No pieces in this slot.</div>';
  renderSelectedLook();
  setImageMode(imageMode);
  if(persist && window.matchMedia('(max-width: 899px)').matches){ grid.scrollIntoView({behavior:'smooth',block:'start'}); }
}
function updateActiveHotspots(){
  document.querySelectorAll('.body-hotspot[data-slot]').forEach(b=>{
    const on=b.dataset.slot===activeSlot; b.classList.toggle('active', on); b.setAttribute('aria-pressed', on?'true':'false');
  });
}
function slotLabel(slot){return ({tops:'Top',outerwear:'Outerwear',bottoms:'Bottom',shoes:'Shoes',accessories:'Accessories'}[slot]||slot)}
function renderSlotButtons(){
  const box=document.getElementById('slotButtons'); if(!box) return;
  box.innerHTML=dressingSlots.map(s=>`<button type="button" class="slot-btn ${s===activeSlot?'active':''}" data-slot="${s}">${slotLabel(s)}</button>`).join('');
}
function renderDresserChoice(item){
  const selected=selectedDressing[activeSlot]===item.id;
  const original=item.original_image_url||item.image_url;
  const thumbnail=item.thumbnail_url||item.image_url;
  const src=imageFor(item);
  return `<article class="card dresser-choice ${selected?'selected':''}" data-item-id="${escapeHtml(item.id)}" role="button" tabindex="0"><div class="photo"><img class="wardrobe-img ${imageMode==='thumbnail'?'thumbnail-mode':''}" loading="lazy" src="${src}" data-original="${original}" data-thumbnail="${thumbnail}" alt="${escapeHtml(item.notes||item.id)}" /></div><div class="card-copy"><div class="row"><span class="type">${escapeHtml(item.subcategory||item.category)}</span><code>${escapeHtml(item.id.replace('item_',''))}</code></div><h2>${escapeHtml(item.notes||item.id)}</h2></div></article>`;
}
function chooseDressingItem(id){
  selectedDressing[activeSlot]=id;
  localStorage.setItem('wardrobeSelectedDressing', JSON.stringify(selectedDressing));
  renderSelectedLook(); selectSlot(activeSlot, false);
}
function clearDressingSlot(){
  delete selectedDressing[activeSlot];
  localStorage.setItem('wardrobeSelectedDressing', JSON.stringify(selectedDressing));
  renderSelectedLook(); selectSlot(activeSlot, false);
}
function renderSelectedLook(){
  const box=document.getElementById('selectedLook'); if(!box) return;
  const byId=Object.fromEntries(dressingItems.map(i=>[i.id,i]));
  const filled=dressingSlots.filter(slot=>selectedDressing[slot]).length;
  const count=document.getElementById('slotCount'); if(count) count.textContent=`${filled} of ${dressingSlots.length} slots filled`;
  const btn=document.getElementById('generateDressed'); if(btn) btn.disabled=filled===0;
  box.innerHTML=dressingSlots.map(slot=>{
    const item=byId[selectedDressing[slot]];
    const active=slot===activeSlot;
    if(!item) return `<div class="selected-slot ${active?'active':''}"><div></div><div><b>${slotLabel(slot)}</b><small>${active?'Active slot — pick from the grid below':'Not selected'}</small></div><button type="button" data-slot="${slot}">Pick</button></div>`;
    const original=item.original_image_url||item.image_url;
    const thumbnail=item.thumbnail_url||item.image_url;
    return `<div class="selected-slot ${active?'active':''}"><img class="wardrobe-img ${imageMode==='thumbnail'?'thumbnail-mode':''}" src="${imageFor(item)}" data-original="${original}" data-thumbnail="${thumbnail}" alt=""><div><b>${slotLabel(slot)}</b><small>${escapeHtml(item.subcategory||item.category)}</small><span>${escapeHtml(item.notes||item.id)}</span></div><button type="button" data-slot="${slot}">Change</button></div>`;
  }).join('');
}
document.addEventListener('click', (event)=>{
  const slotButton = event.target.closest('[data-slot]');
  if(slotButton){ event.preventDefault(); selectSlot(slotButton.dataset.slot); return; }
  const choice = event.target.closest('.dresser-choice[data-item-id]');
  if(choice){ event.preventDefault(); chooseDressingItem(choice.dataset.itemId); }
});
document.addEventListener('keydown', (event)=>{
  if((event.key==='Enter' || event.key===' ') && event.target.matches('.dresser-choice[data-item-id]')){
    event.preventDefault(); chooseDressingItem(event.target.dataset.itemId);
  }
});
async function generateDressedAvatar(){
  const item_ids=dressingSlots.map(s=>selectedDressing[s]).filter(Boolean);
  if(!item_ids.length){ alert('Pick at least one clothing item first.'); return; }
  const status=document.getElementById('dressStatus');
  const btn=document.getElementById('generateDressed');
  status.textContent='Sending avatar + original garment photos to Gemini Flash…'; btn.disabled=true;
  let data=null;
  try{
    const res=await fetch('/api/dressing/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_ids})});
    data=await res.json();
    if(!res.ok) throw new Error(data.error||'Generation failed');
  }catch(e){
    status.textContent='Generation failed: '+e.message;
    return;
  }finally{ btn.disabled=false; }
  try{
    renderDressedResult(data, item_ids.length);
    status.textContent='Done. Saved as '+(data.combo_hash||'generated look')+'.';
  }catch(e){
    status.textContent='Done — Gemini saved it, but this browser could not draw the preview. Tap Open image below.';
    renderDressedFallback(data);
  }
}
function dressedImageUrl(data){
  const rawUrl=String(data && data.image_url || '');
  if(!rawUrl) return '';
  const cacheBust=String(data.combo_hash||Date.now()).replace(/[^a-zA-Z0-9_-]/g,'');
  return rawUrl+(rawUrl.indexOf('?')>=0?'&':'?')+'v='+cacheBust;
}
function renderDressedResult(data, count){
  const results=document.getElementById('dressedResults'); if(!results) return;
  const url=dressedImageUrl(data);
  if(!url) throw new Error('No image URL returned');
  const html=`<article class="dressed-card"><img src="${escapeHtml(url)}" alt="Dressed avatar"><div class="detail-copy"><p class="eyebrow">Generated look</p><h2>${String(count)} selected item${count===1?'':'s'}</h2><div class="meta"><b>Hash</b><code>${escapeHtml(data.combo_hash||'')}</code></div><div class="actions"><a class="chip active" href="${escapeHtml(url)}" target="_blank" rel="noopener">Open image</a></div></div></article>`;
  results.insertAdjacentHTML('afterbegin', html);
}
function renderDressedFallback(data){
  const results=document.getElementById('dressedResults'); if(!results) return;
  const url=dressedImageUrl(data) || String(data && data.image_url || '');
  if(!url) return;
  results.insertAdjacentHTML('afterbegin', `<article class="dressed-card"><div class="detail-copy"><p class="eyebrow">Generated look</p><h2>Preview fallback</h2><div class="actions"><a class="chip active" href="${escapeHtml(url)}" target="_blank" rel="noopener">Open image</a></div></div></article>`);
}

function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function wornLabel(lastWorn, count){
  if(!lastWorn || !count) return 'Never worn';
  const today=new Date().toISOString().slice(0,10);
  const diff=Math.round((new Date(today)-new Date(lastWorn))/86400000);
  const times=count>1?' (×'+count+')':'';
  if(diff===0) return 'Worn today'+times;
  if(diff===1) return 'Worn yesterday'+times;
  if(diff<14) return 'Last worn '+diff+'d ago'+times;
  if(diff<60) return 'Last worn '+Math.round(diff/7)+'w ago'+times;
  return 'Last worn '+Math.round(diff/30)+'mo ago'+times;
}
async function markWorn(type, id, label){
  const payload=type==='item'?{item_id:id}:{outfit_id:id};
  const res=await fetch('/api/wear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(res.ok){ alert('Logged as worn today: '+label); }
  else { const d=await res.json().catch(()=>{}); alert('Could not log wear: '+(d&&d.error||'unknown error')); }
}
"""


class FastThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        self.socket.bind(self.server_address)
        host, port = self.socket.getsockname()[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class WardrobeHandler(BaseHTTPRequestHandler):
    server_version = "WardrobeWeb/0.2"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            self._send(200, _render_page(query), "text/html; charset=utf-8"); return
        if parsed.path == "/api/items":
            con = db_connect()
            all_wear = get_all_item_wear_stats(con)
            self._send_json([_json_item(row, all_wear.get(row["id"])) for row in _filtered_items(query)]); return
        if parsed.path.startswith("/api/items/"):
            item_id = unquote(parsed.path.removeprefix("/api/items/"))
            row = next((r for r in items() if r["id"] == item_id), None)
            if row:
                con = db_connect()
                wear = get_wear_stats(con, item_id=item_id)
                self._send_json(_json_item(row, wear))
            else:
                self._send_json({"error": "not found"}, status=404)
            return
        if parsed.path == "/api/outfits/suggest":
            limit = int((query.get("limit") or ["12"])[0])
            outfits = suggest_outfits(
                occasion=(query.get("occasion") or ["casual"])[0],
                weather=(query.get("weather") or ["mild"])[0],
                vibe=(query.get("vibe") or ["balanced"])[0],
                limit=limit,
            )
            self._send_json([_json_outfit(o) for o in outfits]); return
        if parsed.path == "/api/outfits":
            con = db_connect()
            all_wear = get_all_outfit_wear_stats(con)
            self._send_json([_json_outfit(o, all_wear.get(o["id"])) for o in saved_outfits()]); return
        if parsed.path == "/api/wear":
            limit = int((query.get("limit") or ["20"])[0])
            item_id_f = (query.get("item_id") or [None])[0]
            outfit_id_f = (query.get("outfit_id") or [None])[0]
            con = db_connect()
            self._send_json(db_recent_wear(con, limit, item_id=item_id_f, outfit_id=outfit_id_f)); return
        if parsed.path.startswith("/user/"):
            self._send_user_asset(unquote(parsed.path.removeprefix("/user/"))); return
        if parsed.path.startswith("/images/"):
            self._send_image(unquote(parsed.path.removeprefix("/images/"))); return
        if parsed.path.startswith("/thumbnails/"):
            self._send_thumbnail(unquote(parsed.path.removeprefix("/thumbnails/"))); return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/outfits":
                outfit = save_outfit(
                    item_ids=payload.get("item_ids") or [],
                    name=payload.get("name"),
                    occasion=payload.get("occasion") or "casual",
                    weather=payload.get("weather") or "mild",
                    vibe=payload.get("vibe") or "balanced",
                    notes=payload.get("notes"),
                )
                self._send_json(_json_outfit(outfit), status=201); return
            if parsed.path.startswith("/api/outfits/") and parsed.path.endswith("/rate"):
                outfit_id = unquote(parsed.path.removeprefix("/api/outfits/").removesuffix("/rate"))
                self._send_json(rate_outfit(outfit_id, int(payload.get("rating", 0)), payload.get("reason"))); return
            if parsed.path == "/api/dressing/generate":
                item_ids = [str(x) for x in (payload.get("item_ids") or [])]
                self._send_json(_run_dress_generation(item_ids), status=201); return
            if parsed.path == "/api/wear":
                item_id = payload.get("item_id") or None
                outfit_id = payload.get("outfit_id") or None
                if not item_id and not outfit_id:
                    self._send_json({"error": "item_id or outfit_id required"}, status=400); return
                con = db_connect()
                result = db_log_wear(con, item_id=item_id, outfit_id=outfit_id, note=payload.get("note"), worn_date=payload.get("worn_date"))
                self._send_json(result, status=201); return
            self._send_json({"error": "not found"}, status=404)
        except Exception as e:  # small local tool; surface useful errors
            self._send_json({"error": str(e)}, status=400)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_image(self, rel: str) -> None:
        self._send_file_from(IMAGE_DIR, rel)

    def _send_thumbnail(self, rel: str) -> None:
        self._send_file_from(THUMBNAIL_DIR, rel)

    def _send_user_asset(self, rel: str) -> None:
        self._send_file_from(USER_DIR, rel)

    def _send_file_from(self, base_dir: Path, rel: str) -> None:
        base = base_dir.resolve()
        path = (base / rel).resolve()
        if base not in path.parents and path != base:
            self._send(403, b"Forbidden", "text/plain; charset=utf-8"); return
        if not path.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8"); return
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as f:
            self.wfile.write(f.read())

    def _send_json(self, data: object, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if content_type.startswith("text/html"):
            self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the wardrobe web UI")
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    args = parser.parse_args(argv)

    server = FastThreadingHTTPServer((args.host, args.port), WardrobeHandler)
    ip = _host_ip()
    print("Wardrobe UI running")
    print(f"Local:   http://127.0.0.1:{args.port}")
    print(f"Phone:   http://{ip}:{args.port}")
    print(f"Root:    {PROJECT_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping wardrobe UI")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
