# Wardrobe

Local wardrobe catalog for clothing photos.

It currently:

- stores uploaded clothing images under `data/images/<category>/`
- records metadata in SQLite at `data/wardrobe.sqlite3`
- extracts rough dominant colors and pattern tags
- creates a deterministic local image embedding saved as `.npy`
- supports similarity search by image or existing item id

## Setup

```bash
cd /Users/agent/projects/wardrobe
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
wardrobe init
```

## Add a clothing item

```bash
wardrobe add /path/to/photo.jpg --category tops --notes "linen summer shirt"
```

If no category is given, the app tries to infer from the filename. Otherwise it stores as `unknown`.

Known categories: `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`, `underwear`, `unknown`.

## List items

```bash
wardrobe list
wardrobe list --category shoes
```

## Find similar items

```bash
wardrobe similar --id item_abc123 --limit 5
wardrobe similar --image /path/to/photo.jpg --limit 5
```

## Notes

The first embedding implementation is offline and lightweight: color histograms plus texture features. It gives useful visual similarity immediately. Later we can swap in CLIP/OpenAI image embeddings while keeping the same catalog/database layout.
