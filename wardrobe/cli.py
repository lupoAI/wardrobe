from __future__ import annotations

import argparse
import json
from .catalog import add_item, items, similar
from .db import connect

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

if __name__ == "__main__":
    main()
