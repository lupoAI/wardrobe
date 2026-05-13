# WardrobeApp native iOS scaffold

This is the first native SwiftUI migration slice for the local Wardrobe catalog. It is intentionally small and reviewable: Swift source plus Swift Package metadata, no checked-in Xcode-derived build artifacts.

## What it includes

- SwiftUI item grid with category/search filters.
- Item detail screen using the existing image and thumbnail URLs.
- Upload/import screen that sends a selected photo to the Python backend.
- `WardrobeAPI` client and Codable models matching the JSON endpoints in `wardrobe.web`.
- Backend base URL setting persisted in `UserDefaults`.

## Run the backend for device/simulator access

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
wardrobe init
wardrobe-web --host 0.0.0.0 --port 8765
```

Use `http://127.0.0.1:8765` in the iOS Simulator. For a physical device, use the Mac's LAN IP printed by the web server, for example `http://192.168.1.23:8765`.

> App Transport Security: this local prototype uses plain HTTP to the LAN backend. If this is converted into a full Xcode project, add a debug-only ATS exception for the backend host or serve the Python app through HTTPS.

## Open in Xcode

1. Open Xcode 15+.
2. Choose **File → Open…** and select `ios/WardrobeApp/Package.swift`.
3. Select the `WardrobeApp` scheme and an iOS simulator.
4. Run, then set the backend URL from the app toolbar settings button.

## API contract used by the app

The app uses these endpoints from `wardrobe.web`:

- `GET /api/items?category=&q=` → `[WardrobeItem]`
- `GET /api/items/{id}` → `WardrobeItem`
- `POST /api/items` with JSON body:

```json
{
  "filename": "shirt.jpg",
  "image_base64": "...",
  "category": "tops",
  "notes": "linen summer shirt"
}
```

The upload endpoint returns the created `WardrobeItem` with `image_url`, `thumbnail_url`, and `original_image_url` resolved for the local server.

## Next migration steps

- Convert the Swift Package into a signed `.xcodeproj`/workspace when bundle IDs and signing team are known.
- Add authenticated remote sync if this catalog moves beyond a trusted local network.
- Add outfit planner and dressing-generation screens on top of the existing `/api/outfits*` and `/api/dressing/generate` endpoints.
