# 🎡 Wonderla Photo Retrieval Web Application

A full-featured web application to search, preview, and batch-download high-resolution Wonderla ride photos using just a **Claim Code** or by scanning a **QR Code**.

---

## 🚀 Features

- **Multi-method Input**:
  - Direct Claim Code entry (e.g. `WB41D99UDUNGM`).
  - **Live Camera QR Code Scanner** (scans wristband/ticket directly with front or rear phone camera).
  - **QR Code Image Upload** (upload screenshots or camera roll photos of your ticket/wristband).
  - Auto-normalizes code even from full URLs (e.g., `https://wecapture.life/wonderla?code=...`).
- **Interactive Photo Gallery**:
  - Grid view of all ride captures with high-res thumbnails.
  - Attraction badges (e.g., *Boomerang*, *Roller Coaster*), timestamps, dimensions, and file sizes.
  - Ride filter to view photos from specific rides only.
  - Multi-select checkboxes to pick specific photos.
- **Full-Screen Lightbox**:
  - High-res viewer with touch and arrow-key navigation (`←` / `→`).
  - Direct single-photo download button.
- **Batch Download Options**:
  - **Download All as ZIP**: Concurrently fetches all park photos and streams a single `.zip` file.
  - **Download Selected as ZIP**: Bundles only your chosen photos into a `.zip` file.
  - **Save to Device Storage**: Saves photos directly into Android's `/sdcard/Download/Wonderla_Photos/` with a live progress bar.

---

## 🏃 Quick Start

To launch the web server, run:

```bash
cd ~/wonderla-photo-fetcher
./start.sh
```

Or directly with Python:

```bash
python3 server.py
```

### Accessing the Web UI:
- **On this Android device**: Open `http://localhost:8080` in Chrome / Firefox.
- **On another phone or PC (same Wi-Fi)**: Open `http://<your-lan-ip>:8080` (e.g. `http://192.0.0.8:8080`).

---

## 📡 API Endpoints

- `POST /api/search`
  - Body: `{"code": "WB41D99UDUNGM"}`
  - Returns metadata, total photos, ride names, dimensions, and asset IDs.
- `GET /api/asset-preview?id=<asset_id>&venueId=<venue_id>`
  - 302 redirects straight to Azure Blob Storage signed URL for instant high-speed rendering.
- `GET /api/asset-download?id=<asset_id>&venueId=<venue_id>`
  - 302 redirects to Azure Blob Storage with attachment content disposition for 1-click downloading.
- `GET /api/download-zip?venueId=<venue_id>&ids=<id1,id2>&code=<code>`
  - Multithreaded server-side packaging and download of a `.zip` archive.
- `POST /api/save-local`
  - Saves photos in the background to `/sdcard/Download/Wonderla_Photos/`.
- `GET /api/save-progress`
  - Returns current save progress and count.
