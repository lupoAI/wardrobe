# Web Upload and Item Metadata Editing

Adds a self-contained catalog maintenance flow to the wardrobe web app.

## Features

- Upload JPG/PNG/WEBP clothing photos from the Pieces tab.
- Optional category and notes fields during upload.
- Uploaded images reuse the existing catalog pipeline: copy into `data/images`, create NumPy embedding, extract colors/tags, and insert into SQLite.
- Item detail modal now includes editable category, subcategory, colors, tags, and notes.
- Metadata edits are saved through `POST /api/items/<item_id>` and returned as normal item JSON.

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
