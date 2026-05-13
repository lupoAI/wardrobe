from __future__ import annotations

import argparse
import json
from .catalog import add_item, items, similar
from .db import connect
from .thumbnails import clean_all_thumbnails, clean_thumbnail, generate_all_thumbnails, generate_thumbnail, thumbnail_status, thumbnail_statuses

def emit(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))

def main(argv=None):
    p = argparse.ArgumentParser(prog="wardrobe", description="Local wardrobe image catalog")
    sub = p.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create DB and data directories")

    add = sub.add_parser("add", help="Add a clothing image")
    add.add_argument("image")
    add.add_argument("--category", "-c")
    add.add_argument("--notes")

    ls = sub.add_parser("list", help="List catalog items")
    ls.add_argument("--category", "-c")

    sim = sub.add_parser("similar", help="Find similar items")
    g = sim.add_mutually_exclusive_group(required=True)
    g.add_argument("--image")
    g.add_argument("--id")
    sim.add_argument("--limit", type=int, default=5)

    thumbs = sub.add_parser("thumbnails", help="Generate game-style item thumbnails")
    thumbs.add_argument("--id", help="Generate one item thumbnail by id")
    thumbs.add_argument("--category", "-c", help="Generate thumbnails for one category")
    thumbs.add_argument("--limit", type=int, help="Limit the number of items processed")
    thumbs.add_argument("--force", action="store_true", help="Regenerate existing thumbnails")
    thumbs.add_argument("--clean-only", action="store_true", help="Refresh transparent PNG cutouts from existing raw/legacy/original images without model calls")
    thumbs.add_argument("--status", action="store_true", help="Report thumbnail/cutout status without generating anything")
    thumbs.add_argument("--size", type=int, default=1024, help="Output cutout size for --clean-only (default: 1024)")

    args = p.parse_args(argv)
    if args.cmd == "init":
        with connect():
            pass
        emit({"ok": True, "message": "wardrobe database initialized"})
    elif args.cmd == "add":
        emit(add_item(args.image, category=args.category, notes=args.notes))
    elif args.cmd == "list":
        emit(items(args.category))
    elif args.cmd == "similar":
        emit(similar(image_path=args.image, item_id=args.id, limit=args.limit))
    elif args.cmd == "thumbnails":
        if args.id:
            row = next((r for r in items() if r["id"] == args.id), None)
            if not row:
                raise SystemExit(f"No item found with id {args.id}")
            if args.status:
                emit(thumbnail_status(row))
            elif args.clean_only:
                emit(clean_thumbnail(row, force=args.force, size=args.size))
            else:
                emit(generate_thumbnail(row, force=args.force))
        elif args.status:
            emit(thumbnail_statuses(category=args.category, limit=args.limit))
        elif args.clean_only:
            emit(clean_all_thumbnails(category=args.category, limit=args.limit, force=args.force, size=args.size))
        else:
            emit(generate_all_thumbnails(category=args.category, limit=args.limit, force=args.force))

if __name__ == "__main__":
    main()
