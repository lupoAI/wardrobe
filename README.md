# Wardrobe

Local wardrobe catalog for clothing photos.

It currently:

- stores uploaded clothing images under `data/images/<category>/`
- records metadata in SQLite at `data/wardrobe.sqlite3`
- extracts rough dominant colors and pattern tags
- creates a deterministic local image embedding saved as `.npy`
- supports similarity search by image or existing item id
- includes a local web dressing room for replacing the base avatar, generating dressed avatar looks, saving them into a lookbook, regenerating bad outputs, and exporting share cards

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

## Avatar dressing room

Run the local web app:

```bash
wardrobe-web --port 8765
```

Open the **Dress** tab to:

- replace the base avatar from the app, or via `POST /api/avatar` with `multipart/form-data` field `avatar` or JSON `{ "image_path": "/path/to/avatar.png" }`
- generate a dressed avatar from selected wardrobe pieces with `POST /api/dressing/generate`
- force a fresh try if the output is bad with `POST /api/dressing/generate` and `{ "force": true, "item_ids": [...] }`
- browse saved generated looks at `GET /api/dressing/lookbook`
- export a shareable outfit card with `POST /api/dressing/lookbook/<look_id>/card`

Generated images, metadata, lookbook JSON, and exported cards stay local under `data/user/salo/dressed/`.

## Notes

The first embedding implementation is offline and lightweight: color histograms plus texture features. It gives useful visual similarity immediately. Later we can swap in CLIP/OpenAI image embeddings while keeping the same catalog/database layout.
