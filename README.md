# 🎡 Wonderla Photo Retrieval Web Application

A full-featured web application to search, preview, and batch-download high-resolution Wonderla ride photos using just a **Claim Code** or by scanning a **QR Code**.

Deployable directly to **Vercel** serverless cloud or run locally in **Termux / Linux / Windows / macOS**.

---

## ⚡ Deployment to Vercel

This repository is pre-configured with Vercel serverless functions:
- **Frontend**: Static files in `public/` (`index.html`, `style.css`, `app.js`, `html5-qrcode.min.js`).
- **Backend API**: Python Serverless Function in `api/index.py` using Flask.
- **Routing**: Pre-configured `vercel.json` rewrites.

### Method 1: Import via Vercel Dashboard (1-Click)
1. Push this repository to your GitHub account (see instructions below).
2. Go to **[vercel.com/new](https://vercel.com/new)**.
3. Select your repository `wonderla-photo-fetcher`.
4. Click **Deploy**! Vercel will build and assign you a live HTTPS URL (e.g. `https://wonderla-photo-fetcher.vercel.app`).

### Method 2: Deploy with Vercel CLI
If you have Vercel CLI installed:
```bash
# 1. Login to Vercel
vercel login

# 2. Deploy to production
vercel --prod
```

---

## 🐙 Push to Your GitHub

### Option A: Using GitHub CLI (Automated)
```bash
# Login to GitHub (one-time)
gh auth login

# Run helper script or create repo directly
./push_to_github.sh
```

### Option B: Using Git Remote URL
1. Create a new repository on GitHub at [github.com/new](https://github.com/new) (e.g. `wonderla-photo-fetcher`).
2. Run:
```bash
cd ~/wonderla-photo-fetcher
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<REPO_NAME>.git
git push -u origin main
```

---

## 🚀 Local Run (Termux / Linux)

```bash
cd ~/wonderla-photo-fetcher
./start.sh
```

- Open in browser: `http://localhost:8080`
- Access across your local Wi-Fi: `http://<your-lan-ip>:8080`

---

## 🌟 Features

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
  - **Download All as ZIP**: Concurrently fetches all park photos and streams a single `.zip` file (works everywhere on Vercel and local).
  - **Download Selected as ZIP**: Bundles only your chosen photos into a `.zip` file.
  - **Save to Device Storage**: Saves photos directly into Android's `/sdcard/Download/Wonderla_Photos/` (available in local Termux mode).

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
