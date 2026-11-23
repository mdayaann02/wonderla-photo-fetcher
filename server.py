#!/usr/bin/env python3
"""
Wonderla Photo Retrieval Web Server
Author: Antigravity
Provides a web interface and API to search, preview, and download Wonderla photos
via claim code or scanned QR code using the wecapture.life platform.
"""

import os
import sys
import json
import re
import ssl
import time
import zipfile
import io
import urllib.request
import urllib.parse
import urllib.error
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from concurrent.futures import ThreadPoolExecutor, as_completed

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEFAULT_SAVE_DIR = "/sdcard/Download/Wonderla_Photos"

# In-memory token cache
token_cache = {
    "access_token": None,
    "expires_at": 0,
    "lock": threading.Lock()
}

# In-memory link cache for assets to avoid rate limits
link_cache = {}
link_cache_lock = threading.Lock()

# Background download task status
save_task_status = {
    "is_running": False,
    "total": 0,
    "current": 0,
    "filename": "",
    "error": None,
    "saved_path": ""
}
save_task_lock = threading.Lock()

def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def fetch_with_retry(req_or_url, headers=None, data=None, retries=3, timeout=15):
    """Robust HTTP fetcher with retry logic for network and DNS hiccups"""
    ctx = get_ssl_context()
    last_err = None

    for attempt in range(retries):
        try:
            if isinstance(req_or_url, str):
                req = urllib.request.Request(req_or_url, data=data, headers=headers or {})
            else:
                req = req_or_url

            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            # If 401 Unauthorized, invalidate token cache and bubble up
            if e.code == 401:
                with token_cache["lock"]:
                    token_cache["expires_at"] = 0
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))

    raise last_err

def get_access_token(force_refresh=False):
    """Retrieve or refresh B2C Bearer token from wecapture.life"""
    with token_cache["lock"]:
        now = time.time()
        if not force_refresh and token_cache["access_token"] and token_cache["expires_at"] > now + 60:
            return token_cache["access_token"]

        token_url = "https://wecapture.life/api/wso2-api-bridge"
        headers = {
            "Channel": "B2C",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8;application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
        }
        data = b"grant_type=client_credentials"
        
        try:
            raw = fetch_with_retry(token_url, headers=headers, data=data, retries=3, timeout=15)
            body = json.loads(raw.decode("utf-8"))
            token = body.get("access_token")
            expires_in = body.get("expires_in", 3600)
            token_cache["access_token"] = token
            token_cache["expires_at"] = now + expires_in
            print(f"[Auth] Obtained access token (valid for {expires_in}s)")
            return token
        except Exception as e:
            print(f"[Error] Failed to fetch access token: {e}", file=sys.stderr)
            raise

def clean_code(input_str):
    """
    Extracts Wonderla claim code from raw string or scanned QR URL.
    Examples:
      - WB41D99UDUNGM
      - https://wecapture.life/wonderla?code=WB41D99UDUNGM
      - https://wecapture.life/c/WB41D99UDUNGM
    """
    if not input_str:
        return ""
    input_str = input_str.strip()

    # Check if URL with query parameter code= or c= or claim=
    if "://" in input_str or "?" in input_str:
        parsed = urllib.parse.urlparse(input_str)
        qs = urllib.parse.parse_qs(parsed.query)
        for param in ["code", "c", "claim", "id", "associationValue"]:
            if param in qs and qs[param]:
                return qs[param][0].strip().upper()
        # If in path (e.g. /c/WB41D99UDUNGM)
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            last = path_parts[-1].strip().upper()
            if re.match(r"^[A-Z0-9_\-]+$", last):
                return last

    # Direct code string: clean out non-alphanumeric except hyphen
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", input_str).upper()
    return cleaned

def search_photos(code):
    """Search for photos associated with the given claim code across all fields and pages"""
    token = get_access_token()
    fields_to_try = [
        "captureAssociationValue",
        "permanentAssociationValue",
        "salesAssociationValue"
    ]
    
    search_url = "https://apim.wecapture.life/api/v1/assets/search"
    headers = {
        "Channel": "B2C",
        "Content-Type": "application/json",
        "ocp-apim-subscription-key": "983eadcf05954bc0bff4c15cf873b866",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
    }

    found_field = None
    first_page_res = None

    for field in fields_to_try:
        body = json.dumps({
            "extended_result": True,
            "sort_by": ["assetId_ASC"],
            "page": 1,
            "schema_criteria": {
                "data_schema_id": "1",
                "fields": {field: code}
            }
        }).encode("utf-8")

        try:
            raw = fetch_with_retry(f"{search_url}?page=1", headers=headers, data=body, retries=3, timeout=15)
            data = json.loads(raw.decode("utf-8"))
            total_files = data.get("total_files", 0)
            if total_files > 0:
                found_field = field
                first_page_res = data
                print(f"[Search] Code '{code}' matched field '{field}' with {total_files} photos.")
                break
        except Exception as e:
            print(f"[Warning] Search failed for field {field}: {e}", file=sys.stderr)

    if not found_field or not first_page_res:
        return {
            "status": "not_found",
            "message": f"No photos found for code '{code}'. Please verify your ticket or wristband code.",
            "total": 0,
            "photos": []
        }

    total_files = first_page_res.get("total_files", 0)
    total_pages = first_page_res.get("total_pages", 1)

    all_results = list(first_page_res.get("result", []))
    all_extended = dict(first_page_res.get("extended_result", {}))

    # WeCapture API uses ?page=p query parameter for pagination
    if total_pages > 1:
        def fetch_page_data(p_num):
            p_url = f"{search_url}?page={p_num}"
            p_body = json.dumps({
                "extended_result": True,
                "sort_by": ["assetId_ASC"],
                "schema_criteria": {
                    "data_schema_id": "1",
                    "fields": {found_field: code}
                }
            }).encode("utf-8")
            try:
                p_raw = fetch_with_retry(p_url, headers=headers, data=p_body, retries=3, timeout=15)
                return p_num, json.loads(p_raw.decode("utf-8"))
            except Exception as err:
                print(f"[Warning] Failed to fetch page {p_num}: {err}", file=sys.stderr)
                return p_num, None

        max_workers = min(8, total_pages - 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {executor.submit(fetch_page_data, p): p for p in range(2, total_pages + 1)}
            page_data_map = {}
            for fut in as_completed(future_to_page):
                p_num, p_data = fut.result()
                if p_data:
                    page_data_map[p_num] = p_data

        # Append in strict sequential page order
        for p in range(2, total_pages + 1):
            if p in page_data_map:
                p_data = page_data_map[p]
                all_results.extend(p_data.get("result", []))
                all_extended.update(p_data.get("extended_result", {}))

    # Deduplicate asset IDs while maintaining discovery order
    seen_ids = set()
    unique_results = []
    for aid in all_results:
        if aid not in seen_ids:
            seen_ids.add(aid)
            unique_results.append(aid)

    # Process and structure photo items
    photos = []
    venue_name = "Wonderla"
    venue_id = "IN06"

    for asset_id in unique_results:
        asset_info = all_extended.get(asset_id, {})
        data_block = asset_info.get("data", {})
        metadata_block = asset_info.get("metadata", {})

        v_name = data_block.get("venueName") or asset_info.get("venueName")
        if v_name:
            venue_name = v_name
        v_id = data_block.get("venueId") or asset_info.get("venueId")
        if v_id:
            venue_id = v_id

        ride = data_block.get("locationName") or "Park Photo"
        cap_date = data_block.get("captureDate") or asset_info.get("upload_time") or ""
        
        # Format date readable: 2026-11-15T09:47:20Z -> 2026-11-15 09:47:20
        date_formatted = cap_date.replace("T", " ").replace("Z", "") if cap_date else "Unknown"

        size_bytes = asset_info.get("size", 0)
        size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else 0

        width = metadata_block.get("width")
        height = metadata_block.get("height")
        dim_str = f"{width}x{height}" if width and height else data_block.get("dimension", "")

        photos.append({
            "id": asset_id,
            "filename": asset_info.get("name") or f"{asset_id}.jpg",
            "ride": ride,
            "venue": venue_name,
            "venueId": venue_id,
            "captureDate": date_formatted,
            "sizeBytes": size_bytes,
            "sizeFormatted": f"{size_mb} MB" if size_mb > 0 else "High Res",
            "dimension": dim_str,
            "orientation": data_block.get("orientation", "Landscape")
        })

    return {
        "status": "success",
        "code": code,
        "matchedField": found_field,
        "venue": venue_name,
        "venueId": venue_id,
        "total": len(photos),
        "totalPages": total_pages,
        "photos": photos
    }

def get_asset_url(venue_id, asset_id, download=False):
    """Retrieve signed Azure Blob Storage link for an asset"""
    cache_key = (venue_id, asset_id, bool(download))
    now = time.time()
    
    with link_cache_lock:
        if cache_key in link_cache:
            url, expiry = link_cache[cache_key]
            if expiry > now:
                return url

    token = get_access_token()
    download_param = "true" if download else "false"
    api_url = f"https://apim.wecapture.life/api/v1/assets/{asset_id}/get_link?venueId={venue_id}&download={download_param}"
    
    headers = {
        "Channel": "B2C",
        "ocp-apim-subscription-key": "983eadcf05954bc0bff4c15cf873b866",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
    }

    raw = fetch_with_retry(api_url, headers=headers, retries=3, timeout=15)
    url = raw.decode("utf-8").strip()
    if url.startswith("http"):
        with link_cache_lock:
            # Cache for 2 hours (signed links typically valid for 24 hours)
            link_cache[cache_key] = (url, now + 7200)
        return url
    else:
        raise ValueError(f"Invalid signed URL received: {url}")

def download_single_asset_bytes(venue_id, asset_id):
    """Fetch binary image data for an asset"""
    url = get_asset_url(venue_id, asset_id, download=True)
    return fetch_with_retry(url, headers={"User-Agent": "Mozilla/5.0"}, retries=3, timeout=30)

def run_local_save(asset_list, venue_id, dest_dir):
    """Background thread to download photos directly to Android storage"""
    global save_task_status
    with save_task_lock:
        save_task_status["is_running"] = True
        save_task_status["total"] = len(asset_list)
        save_task_status["current"] = 0
        save_task_status["error"] = None
        save_task_status["saved_path"] = dest_dir

    try:
        os.makedirs(dest_dir, exist_ok=True)

        for idx, item in enumerate(asset_list):
            asset_id = item["id"]
            filename = item.get("filename", f"{asset_id}.jpg")
            target_path = os.path.join(dest_dir, filename)

            with save_task_lock:
                save_task_status["filename"] = filename

            if not (os.path.exists(target_path) and os.path.getsize(target_path) > 1000):
                content = download_single_asset_bytes(venue_id, asset_id)
                with open(target_path, "wb") as f:
                    f.write(content)

            with save_task_lock:
                save_task_status["current"] = idx + 1

    except Exception as e:
        with save_task_lock:
            save_task_status["error"] = str(e)
    finally:
        with save_task_lock:
            save_task_status["is_running"] = False


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class WonderlaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

    def do_HEAD(self):
        self.do_GET(head_only=True)

    def send_json(self, data, status_code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self, head_only=False):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # Asset direct preview redirect
        if path == "/api/asset-preview":
            asset_id = qs.get("id", [None])[0]
            venue_id = qs.get("venueId", ["IN06"])[0]
            if not asset_id:
                self.send_error(400, "Missing id parameter")
                return
            try:
                url = get_asset_url(venue_id, asset_id, download=False)
                self.send_response(302)
                self.send_header("Location", url)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Error getting preview: {e}")
            return

        # Asset direct download redirect
        if path == "/api/asset-download":
            asset_id = qs.get("id", [None])[0]
            venue_id = qs.get("venueId", ["IN06"])[0]
            if not asset_id:
                self.send_error(400, "Missing id parameter")
                return
            try:
                url = get_asset_url(venue_id, asset_id, download=True)
                self.send_response(302)
                self.send_header("Location", url)
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Error getting download: {e}")
            return

        # Check local save progress
        if path == "/api/save-progress":
            with save_task_lock:
                self.send_json(dict(save_task_status))
            return

        # ZIP download via GET
        if path == "/api/download-zip":
            venue_id = qs.get("venueId", ["IN06"])[0]
            ids_str = qs.get("ids", [""])[0]
            code = qs.get("code", ["Wonderla"])[0]
            if not ids_str:
                self.send_error(400, "Missing ids parameter")
                return
            asset_ids = [i.strip() for i in ids_str.split(",") if i.strip()]
            self.stream_zip(venue_id, asset_ids, f"{code}_Photos.zip")
            return

        # Static fallback
        if path == "/":
            self.path = "/index.html"
        if head_only:
            super().do_HEAD()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        # Search endpoint
        if path == "/api/search":
            raw_code = body.get("code", "")
            code = clean_code(raw_code)
            if not code:
                self.send_json({
                    "status": "error",
                    "message": "Please enter a valid claim code or scan a QR code."
                }, status_code=400)
                return

            try:
                result = search_photos(code)
                self.send_json(result)
            except Exception as e:
                self.send_json({
                    "status": "error",
                    "message": f"Server error while searching: {str(e)}"
                }, status_code=500)
            return

        # Start background local device save
        if path == "/api/save-local":
            assets = body.get("assets", [])
            venue_id = body.get("venueId", "IN06")
            dest_dir = body.get("destDir") or DEFAULT_SAVE_DIR

            if not assets:
                self.send_json({"status": "error", "message": "No assets provided"}, status_code=400)
                return

            with save_task_lock:
                if save_task_status["is_running"]:
                    self.send_json({"status": "busy", "message": "A download is already in progress"}, status_code=409)
                    return

            thread = threading.Thread(target=run_local_save, args=(assets, venue_id, dest_dir), daemon=True)
            thread.start()
            self.send_json({"status": "started", "destination": dest_dir, "total": len(assets)})
            return

        # ZIP download via POST
        if path == "/api/download-zip":
            venue_id = body.get("venueId", "IN06")
            asset_ids = body.get("assetIds", [])
            zip_name = body.get("filename", "Wonderla_Photos.zip")
            if not asset_ids:
                self.send_json({"status": "error", "message": "No assetIds provided"}, status_code=400)
                return
            self.stream_zip(venue_id, asset_ids, zip_name)
            return

        self.send_error(404, "Endpoint not found")

    def stream_zip(self, venue_id, asset_ids, zip_filename):
        """Build ZIP file in memory using multithreaded fetching and stream to client"""
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                def fetch_and_write(aid):
                    try:
                        data = download_single_asset_bytes(venue_id, aid)
                        return aid, data, None
                    except Exception as err:
                        return aid, None, str(err)

                max_workers = min(8, len(asset_ids))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(fetch_and_write, aid) for aid in asset_ids]
                    for fut in as_completed(futures):
                        aid, data, err = fut.result()
                        if data:
                            zf.writestr(f"{aid}.jpg", data)
                        else:
                            print(f"[Warning] Failed to fetch {aid} for ZIP: {err}", file=sys.stderr)

            zip_buffer.seek(0)
            zip_bytes = zip_buffer.getvalue()

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{zip_filename}"')
            self.send_header("Content-Length", str(len(zip_bytes)))
            self.end_headers()
            self.wfile.write(zip_bytes)
        except Exception as e:
            print(f"[Error] Failed to generate zip: {e}", file=sys.stderr)
            self.send_error(500, f"Error building ZIP: {e}")

def main():
    os.chdir(BASE_DIR)
    os.makedirs(STATIC_DIR, exist_ok=True)
    server_address = ("0.0.0.0", PORT)
    httpd = ThreadedHTTPServer(server_address, WonderlaHandler)
    
    print("=" * 60)
    print("      Wonderla Photo Retrieval Web Server Started")
    print("=" * 60)
    print(f" * Local access:    http://localhost:{PORT}")
    print(f" * Network access:  http://0.0.0.0:{PORT}")
    print(f" * Target Web UI:   {STATIC_DIR}/index.html")
    print("=" * 60)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down gracefully...")
        httpd.server_close()

if __name__ == "__main__":
    main()
