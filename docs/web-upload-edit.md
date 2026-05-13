# Web Upload and Item Metadata Editing

Adds a self-contained catalog maintenance flow to the wardrobe web app.

## Features

- Upload JPG/PNG/WEBP clothing photos from the Pieces tab.
- Optional category and notes fields during upload.
- Uploaded images reuse the existing catalog pipeline: copy into `data/images`, create NumPy embedding, extract colors/tags, and insert into SQLite.
- Uploaded items immediately participate in the existing thumbnail pipeline: the web API returns `has_thumbnail: false` until `wardrobe thumbnails` generates `data/thumbnails/<item_id>.png`, then the app automatically uses that thumbnail through the existing `/thumbnails/<file>` route.
- Item detail modal now includes editable category, subcategory, colors, tags, and notes.
- Metadata edits are saved through `POST /api/items/<item_id>` and returned as normal item JSON.

## Thumbnail pipeline

Uploads intentionally do not call image generation during the HTTP request. The upload path is fast and deterministic: it creates the catalog item, stores the original image, computes metadata/embedding, and returns the new item with the same thumbnail fields as the rest of the API.

After upload, the item can be picked up by the existing thumbnail job:

```bash
wardrobe thumbnails --id <item_id>
# or batch later
wardrobe thumbnails --category tops --limit 10
```

Once the thumbnail exists, no extra upload-specific state is needed. `_json_item()` resolves `thumbnail_url` from the item id, the Pieces/Dress views switch from original-photo fallback to the generated thumbnail, and the global Originals/Game thumbnails toggle continues to work for uploaded and CLI-added items in the same way.

## API

- `POST /api/items/upload` accepts `multipart/form-data` with:
  - `image` file
  - optional `category`
  - optional `notes`
- `POST /api/items/<item_id>` accepts JSON metadata changes:
  - `category`
  - `subcategory`
  - `colors` as comma-separated string or list
  - `tags` as comma-separated string or list
  - `notes`

## Safety/limits

- Uploads are capped at 12MB.
- Allowed extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.
- Metadata updates reject unknown fields so image paths and embeddings cannot be overwritten through the API.
