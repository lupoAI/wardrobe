from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .catalog import items
from .config import IMAGE_DIR, PROJECT_ROOT


def _asset_path(item: dict) -> str:
    path = Path(item["image_path"])
    try:
        rel = path.resolve().relative_to(IMAGE_DIR.resolve())
    except ValueError:
        rel = path.name
    return "/images/" + quote(str(rel).replace(os.sep, "/"))


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
                row.get("id", ""),
                row.get("category", ""),
                row.get("subcategory", ""),
                row.get("notes", ""),
                row.get("original_filename", ""),
                " ".join(row.get("colors", [])),
                " ".join(row.get("tags", [])),
            ]
            return " ".join(p for p in parts if p).lower()

        rows = [row for row in rows if q in haystack(row)]
    return rows


def _categories(rows: list[dict]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))


def _json_item(row: dict) -> dict:
    return {
        **row,
        "image_url": _asset_path(row),
    }


def _render_page(query: dict[str, list[str]]) -> bytes:
    all_rows = items()
    rows = _filtered_items(query)
    selected = (query.get("category") or [""])[0].strip()
    q = (query.get("q") or [""])[0].strip()
    cats = _categories(all_rows)

    cards = "\n".join(_render_card(row) for row in rows)
    empty = "" if rows else "<div class='empty'>No pieces match that filter.</div>"
    chips = [
        f"<a class='chip {'active' if not selected else ''}' href='/'>All <span>{len(all_rows)}</span></a>"
    ]
    for cat, count in cats:
        href = "/?category=" + quote(cat)
        chips.append(
            f"<a class='chip {'active' if selected == cat else ''}' href='{href}'>{html.escape(cat)} <span>{count}</span></a>"
        )

    category_counts = json.dumps({cat: count for cat, count in cats})
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
        <p class="sub">{len(all_rows)} pieces indexed · {len(rows)} shown</p>
      </div>
      <div class="stat">
        <strong>{len(cats)}</strong>
        <span>categories</span>
      </div>
    </header>

    <form class="search" method="get" action="/">
      <input type="search" name="q" value="{html.escape(q)}" placeholder="Search color, tag, item id…" autocomplete="off" />
      {f'<input type="hidden" name="category" value="{html.escape(selected)}" />' if selected else ''}
      <button>Search</button>
    </form>

    <nav class="chips" aria-label="Categories">{''.join(chips)}</nav>

    <main class="grid">
      {cards}
      {empty}
    </main>
  </div>

  <dialog id="detail">
    <button class="close" onclick="detail.close()">×</button>
    <div id="detailBody"></div>
  </dialog>

  <script>
    window.WARDROBE_COUNTS = {category_counts};
    async function openItem(id) {{
      const res = await fetch('/api/items/' + encodeURIComponent(id));
      const item = await res.json();
      const chips = (item.tags || []).map(t => `<span class="pill">${{escapeHtml(t)}}</span>`).join('');
      const colors = (item.colors || []).map(t => `<span class="swatch">${{escapeHtml(t)}}</span>`).join('');
      document.getElementById('detailBody').innerHTML = `
        <img class="detail-img" src="${{item.image_url}}" alt="${{escapeHtml(item.notes || item.id)}}">
        <div class="detail-copy">
          <p class="eyebrow">${{escapeHtml(item.category)}} / ${{escapeHtml(item.subcategory || '—')}}</p>
          <h2>${{escapeHtml(item.notes || item.id)}}</h2>
          <div class="meta"><b>ID</b><code>${{escapeHtml(item.id)}}</code></div>
          <div class="meta"><b>Created</b><span>${{escapeHtml(item.created_at || '')}}</span></div>
          <div class="meta"><b>Colors</b><div class="pills">${{colors}}</div></div>
          <div class="meta"><b>Tags</b><div class="pills">${{chips}}</div></div>
          <div class="meta"><b>Original</b><span>${{escapeHtml(item.original_filename || '')}}</span></div>
        </div>`;
      detail.showModal();
    }}
    function escapeHtml(s) {{
      return String(s ?? '').replace(/[&<>'"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[c]));
    }}
  </script>
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
    return f"""
      <article class="card" onclick="openItem('{item_id}')" tabindex="0" onkeydown="if(event.key==='Enter') openItem('{item_id}')">
        <div class="photo"><img loading="lazy" src="{img}" alt="{notes}" /></div>
        <div class="card-copy">
          <div class="row"><span class="type">{sub}</span><code>{item_id.replace('item_', '')}</code></div>
          <h2>{notes}</h2>
          <div class="pills">{colors}</div>
          <div class="pills muted">{tags}</div>
        </div>
      </article>"""


CSS = r"""
:root {
  color-scheme: light;
  --bg: #f6f2ea;
  --ink: #171613;
  --muted: #736b60;
  --line: rgba(23, 22, 19, .12);
  --card: rgba(255, 255, 255, .72);
  --card-strong: rgba(255, 255, 255, .92);
  --accent: #111827;
  --accent2: #c67a45;
  --shadow: 0 18px 50px rgba(33, 28, 20, .12);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
  background:
    radial-gradient(circle at 12% 0%, rgba(198,122,69,.18), transparent 30rem),
    radial-gradient(circle at 88% 8%, rgba(38,70,83,.14), transparent 28rem),
    var(--bg);
  color: var(--ink);
}
.shell { width: min(1180px, 100%); margin: 0 auto; padding: max(18px, env(safe-area-inset-top)) 14px 40px; }
.hero {
  display: flex; justify-content: space-between; gap: 18px; align-items: end;
  padding: 22px 6px 18px;
}
.eyebrow { margin: 0 0 6px; text-transform: uppercase; letter-spacing: .14em; font-size: 11px; color: var(--muted); font-weight: 800; }
h1 { margin: 0; font-size: clamp(42px, 12vw, 84px); line-height: .86; letter-spacing: -.075em; }
.sub { margin: 12px 0 0; color: var(--muted); font-weight: 600; }
.stat { min-width: 94px; padding: 16px; border: 1px solid var(--line); background: var(--card); backdrop-filter: blur(16px); border-radius: 24px; text-align: center; box-shadow: var(--shadow); }
.stat strong { display: block; font-size: 28px; }
.stat span { color: var(--muted); font-size: 12px; font-weight: 700; }
.search { position: sticky; top: 0; z-index: 5; display: flex; gap: 8px; padding: 8px; background: rgba(246,242,234,.78); backdrop-filter: blur(18px); border: 1px solid var(--line); border-radius: 22px; box-shadow: var(--shadow); }
.search input { min-width: 0; flex: 1; border: 0; outline: 0; border-radius: 16px; padding: 15px 14px; background: rgba(255,255,255,.78); color: var(--ink); font: inherit; font-weight: 650; }
.search button { border: 0; border-radius: 16px; padding: 0 18px; background: var(--accent); color: white; font-weight: 850; }
.chips { display: flex; gap: 9px; overflow-x: auto; padding: 16px 2px 14px; scrollbar-width: none; }
.chips::-webkit-scrollbar { display: none; }
.chip { white-space: nowrap; text-decoration: none; color: var(--ink); border: 1px solid var(--line); background: rgba(255,255,255,.55); padding: 10px 13px; border-radius: 999px; font-weight: 800; text-transform: capitalize; }
.chip span { color: var(--muted); margin-left: 5px; }
.chip.active { background: var(--ink); color: white; border-color: var(--ink); }
.chip.active span { color: rgba(255,255,255,.65); }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.card { border: 1px solid var(--line); background: var(--card); backdrop-filter: blur(16px); border-radius: 26px; overflow: hidden; box-shadow: 0 12px 34px rgba(33, 28, 20, .10); cursor: pointer; transition: transform .18s ease, box-shadow .18s ease; }
.card:active { transform: scale(.985); }
.photo { aspect-ratio: 4 / 5; background: #e8dfd2; overflow: hidden; }
.photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
.card-copy { padding: 12px; }
.row { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.type { color: var(--accent2); text-transform: capitalize; font-size: 12px; font-weight: 900; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; color: var(--muted); }
h2 { margin: 7px 0 10px; font-size: 14px; line-height: 1.18; letter-spacing: -.02em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.pills { display: flex; flex-wrap: wrap; gap: 5px; }
.pills.muted { margin-top: 7px; opacity: .72; }
.pill, .swatch { display: inline-flex; align-items: center; min-height: 24px; padding: 5px 8px; border-radius: 999px; background: rgba(23,22,19,.07); font-size: 11px; font-weight: 800; color: #3a352e; }
.swatch { background: rgba(198,122,69,.13); }
.empty { grid-column: 1 / -1; padding: 42px 16px; border: 1px dashed var(--line); border-radius: 24px; text-align: center; color: var(--muted); font-weight: 800; }
dialog { width: min(760px, calc(100vw - 20px)); max-height: min(860px, calc(100dvh - 20px)); border: 0; border-radius: 30px; padding: 0; background: var(--card-strong); box-shadow: 0 30px 100px rgba(0,0,0,.35); overflow: auto; }
dialog::backdrop { background: rgba(20, 18, 15, .52); backdrop-filter: blur(8px); }
.close { position: sticky; float: right; top: 10px; right: 10px; z-index: 2; margin: 10px; border: 0; width: 42px; height: 42px; border-radius: 50%; background: rgba(0,0,0,.72); color: white; font-size: 28px; line-height: 1; }
.detail-img { width: 100%; max-height: 62dvh; object-fit: contain; background: #eadfce; display: block; }
.detail-copy { padding: 18px; }
.detail-copy h2 { display: block; overflow: visible; -webkit-line-clamp: unset; font-size: 23px; margin-bottom: 18px; }
.meta { display: grid; grid-template-columns: 86px 1fr; gap: 12px; padding: 11px 0; border-top: 1px solid var(--line); align-items: start; }
.meta b { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
.meta span { overflow-wrap: anywhere; }
@media (min-width: 720px) {
  .shell { padding-left: 24px; padding-right: 24px; }
  .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
  .card-copy { padding: 15px; }
  h2 { font-size: 16px; }
}
@media (min-width: 1040px) {
  .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
"""


class FastThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server that avoids reverse-DNS lookups during bind on local networks."""

    daemon_threads = True

    def server_bind(self) -> None:
        self.socket.bind(self.server_address)
        host, port = self.socket.getsockname()[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class WardrobeHandler(BaseHTTPRequestHandler):
    server_version = "WardrobeWeb/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            self._send(200, _render_page(query), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/items":
            data = [_json_item(row) for row in _filtered_items(query)]
            self._send_json(data)
            return
        if parsed.path.startswith("/api/items/"):
            item_id = unquote(parsed.path.removeprefix("/api/items/"))
            row = next((r for r in items() if r["id"] == item_id), None)
            if not row:
                self._send_json({"error": "not found"}, status=404)
                return
            self._send_json(_json_item(row))
            return
        if parsed.path.startswith("/images/"):
            rel = unquote(parsed.path.removeprefix("/images/"))
            self._send_image(rel)
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _send_image(self, rel: str) -> None:
        base = IMAGE_DIR.resolve()
        path = (base / rel).resolve()
        if base not in path.parents and path != base:
            self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            return
        if not path.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
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
    print(f"Wardrobe UI running")
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
