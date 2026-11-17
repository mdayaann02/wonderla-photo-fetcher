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
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, redirect, Response, send_file

app = Flask(__name__)

# Token cache
token_cache = {
    "access_token": None,
    "expires_at": 0,
    "lock": threading.Lock()
}

# Asset link cache
link_cache = {}
link_cache_lock = threading.Lock()

def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def fetch_with_retry(req_or_url, headers=None, data=None, retries=3, timeout=15):
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
    with token_cache["lock"]:
        now = time.time()
        if not force_refresh and token_cache["access_token"] and token_cache["expires_at"] > now + 60:
            return token_cache["access_token"]

        token_url = "https://wecapture.life/api/wso2-api-bridge"
        headers = {
            "Channel": "B2C",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8;application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        }
        data = b"grant_type=client_credentials"

        raw = fetch_with_retry(token_url, headers=headers, data=data, retries=3, timeout=15)
        body = json.loads(raw.decode("utf-8"))
        token = body.get("access_token")
        expires_in = body.get("expires_in", 3600)
        token_cache["access_token"] = token
        token_cache["expires_at"] = now + expires_in
        return token

def clean_code(input_str):
    if not input_str:
        return ""
    input_str = input_str.strip()
    if "://" in input_str or "?" in input_str:
        parsed = urllib.parse.urlparse(input_str)
        qs = urllib.parse.parse_qs(parsed.query)
        for param in ["code", "c", "claim", "id", "associationValue"]:
            if param in qs and qs[param]:
                return qs[param][0].strip().upper()
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            last = path_parts[-1].strip().upper()
            if re.match(r"^[A-Z0-9_\-]+$", last):
                return last

    return re.sub(r"[^A-Za-z0-9_\-]", "", input_str).upper()

def search_photos(code):
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
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
            raw = fetch_with_retry(search_url, headers=headers, data=body, retries=3, timeout=15)
            data = json.loads(raw.decode("utf-8"))
            total_files = data.get("total_files", 0)
            if total_files > 0:
                found_field = field
                first_page_res = data
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

    if total_pages > 1:
        for p in range(2, total_pages + 1):
            p_body = json.dumps({
                "extended_result": True,
                "sort_by": ["assetId_ASC"],
                "page": p,
                "schema_criteria": {
                    "data_schema_id": "1",
                    "fields": {found_field: code}
                }
            }).encode("utf-8")
            try:
                p_raw = fetch_with_retry(search_url, headers=headers, data=p_body, retries=3, timeout=15)
                p_data = json.loads(p_raw.decode("utf-8"))
                all_results.extend(p_data.get("result", []))
                all_extended.update(p_data.get("extended_result", {}))
            except Exception as e:
                print(f"[Warning] Failed to fetch page {p}: {e}", file=sys.stderr)

    photos = []
    venue_name = "Wonderla"
    venue_id = "IN06"

    for asset_id in all_results:
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    }

    raw = fetch_with_retry(api_url, headers=headers, retries=3, timeout=15)
    url = raw.decode("utf-8").strip()
    if url.startswith("http"):
        with link_cache_lock:
            link_cache[cache_key] = (url, now + 7200)
        return url
    else:
        raise ValueError(f"Invalid signed URL received: {url}")

def download_single_asset_bytes(venue_id, asset_id):
    url = get_asset_url(venue_id, asset_id, download=True)
    return fetch_with_retry(url, headers={"User-Agent": "Mozilla/5.0"}, retries=3, timeout=30)

# Routes
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "Wonderla Photo API", "platform": "Vercel"})

@app.route("/api/search", methods=["POST"])
def search():
    body = request.get_json(silent=True) or {}
    raw_code = body.get("code", "")
    code = clean_code(raw_code)

    if not code:
        return jsonify({
            "status": "error",
            "message": "Please enter a valid claim code or scan a QR code."
        }), 400

    try:
        result = search_photos(code)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Server error: {str(e)}"
        }), 500

@app.route("/api/asset-preview", methods=["GET"])
def asset_preview():
    asset_id = request.args.get("id")
    venue_id = request.args.get("venueId", "IN06")
    if not asset_id:
        return jsonify({"error": "Missing id"}), 400
    try:
        url = get_asset_url(venue_id, asset_id, download=False)
        return redirect(url, code=302)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/asset-download", methods=["GET"])
def asset_download():
    asset_id = request.args.get("id")
    venue_id = request.args.get("venueId", "IN06")
    if not asset_id:
        return jsonify({"error": "Missing id"}), 400
    try:
        url = get_asset_url(venue_id, asset_id, download=True)
        return redirect(url, code=302)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download-zip", methods=["GET", "POST"])
def download_zip():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        venue_id = body.get("venueId", "IN06")
        asset_ids = body.get("assetIds", [])
        zip_name = body.get("filename", "Wonderla_Photos.zip")
    else:
        venue_id = request.args.get("venueId", "IN06")
        ids_str = request.args.get("ids", "")
        code = request.args.get("code", "Wonderla")
        asset_ids = [i.strip() for i in ids_str.split(",") if i.strip()]
        zip_name = f"{code}_Photos.zip"

    if not asset_ids:
        return jsonify({"error": "No asset IDs provided"}), 400

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

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name
        )
    except Exception as e:
        return jsonify({"error": f"Failed to build ZIP: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
