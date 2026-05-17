from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from typing import List
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import shutil, os, json, uuid
from pathlib import Path
from database import (init_db, get_all_posts, add_post, get_post, delete_post,
                      update_post_status, get_stats, save_platform_config,
                      get_platform_config, get_all_platform_configs, get_logs,
                      get_posts_by_month, get_tiktok_accounts, add_account,
                      get_account, update_account, delete_account, rename_account,
                      get_all_accounts, get_accounts_by_platform, check_queued_duplicate)
from scheduler import start_scheduler

app = FastAPI(title="Build & Chill Auto Poster")
templates = Jinja2Templates(directory="templates")

QUEUE_DIR = Path(__file__).parent / "queue"
POSTED_DIR = Path(__file__).parent / "posted"
FAILED_DIR = Path(__file__).parent / "failed"
THUMBNAIL_DIR = Path(__file__).parent / "thumbnails"
WELL_KNOWN_DIR = Path(__file__).parent / "well-known"
PREVIEW_DIR = Path(__file__).parent / "previews"

app.mount("/thumbnails", StaticFiles(directory=str(THUMBNAIL_DIR)), name="thumbnails")
app.mount("/queue_files", StaticFiles(directory=str(QUEUE_DIR)), name="queue_files")
app.mount("/.well-known", StaticFiles(directory=str(WELL_KNOWN_DIR)), name="well-known")
app.mount("/previews", StaticFiles(directory=str(PREVIEW_DIR)), name="previews")

@app.on_event("startup")
def startup():
    THUMBNAIL_DIR.mkdir(exist_ok=True)
    WELL_KNOWN_DIR.mkdir(exist_ok=True)
    PREVIEW_DIR.mkdir(exist_ok=True)
    init_db()
    start_scheduler()

# ─── LANDING PAGE (public) ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/legal/privacy-policy")
async def privacy_policy():
    return FileResponse("legal/privacy-policy.html", media_type="text/html")

@app.get("/legal/terms-of-service")
async def terms_of_service():
    return FileResponse("legal/terms-of-service.html", media_type="text/html")

# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    posts = get_all_posts()
    stats = get_stats()
    platform_configs = get_all_platform_configs()
    all_accounts = get_all_accounts()
    tiktok_accounts = [a for a in all_accounts if a['platform'] == 'tiktok']
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "posts": posts,
        "stats": stats,
        "platform_configs": platform_configs,
        "all_accounts": all_accounts,
        "tiktok_accounts": tiktok_accounts
    })

# ─── UPLOAD ───────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload(
    files: List[UploadFile] = File(...),
    thumbnail: UploadFile = File(None),
    caption: str = Form(""),
    hashtags: str = Form(""),
    platforms: str = Form(""),
    scheduled_time: str = Form(""),
    per_platform_data: str = Form("{}")
):
    if not platforms or not platforms.strip():
        raise HTTPException(status_code=400, detail="At least one platform must be selected.")
    if not files:
        raise HTTPException(status_code=400, detail="At least one file must be uploaded.")

    # Save all uploaded files
    saved_paths = []
    for f in files:
        dest = QUEUE_DIR / f.filename
        with open(dest, "wb") as fh:
            shutil.copyfileobj(f.file, fh)
        saved_paths.append(str(dest))

    primary_file = files[0]
    primary_dest = saved_paths[0]
    ext = Path(primary_file.filename).suffix.lower()

    if len(files) > 1:
        content_type = "carousel"
        carousel_paths = json.dumps(saved_paths)
    else:
        content_type = "video" if ext in [".mp4", ".mov", ".avi", ".mkv"] else "image"
        carousel_paths = None

    sched = scheduled_time if scheduled_time else None

    thumb_path = None
    if thumbnail and thumbnail.filename:
        thumb_ext = Path(thumbnail.filename).suffix.lower()
        thumb_name = f"{Path(primary_file.filename).stem}_thumb{thumb_ext}"
        thumb_dest = THUMBNAIL_DIR / thumb_name
        with open(thumb_dest, "wb") as fh:
            shutil.copyfileobj(thumbnail.file, fh)
        thumb_path = str(thumb_dest)

    # Check for duplicates before queuing
    duplicate_warnings = []
    for entry in platforms.split(','):
        entry = entry.strip()
        if not entry:
            continue
        existing = check_queued_duplicate(primary_file.filename, entry)
        if existing:
            duplicate_warnings.append(f"{entry} (post #{existing['id']} is already {existing['status']})")

    post_id = add_post(primary_file.filename, primary_dest, content_type, caption, hashtags, platforms,
                       sched, thumb_path, per_platform_data, carousel_paths)

    # Build human-readable platform names for the confirmation response
    platform_labels = {'tiktok': 'TikTok', 'youtube': 'YouTube', 'instagram': 'Instagram', 'facebook': 'Facebook'}
    platform_names = []
    for entry in platforms.split(','):
        entry = entry.strip()
        if not entry or ':' not in entry:
            continue
        platform_key, account_id_str = entry.split(':', 1)
        try:
            account = get_account(int(account_id_str))
            label = platform_labels.get(platform_key, platform_key.capitalize())
            platform_names.append(f"{label} — {account['nickname']}" if account else label)
        except Exception:
            platform_names.append(platform_key.capitalize())

    return JSONResponse({
        "success": True,
        "post_id": post_id,
        "platforms": platforms,
        "platform_names": platform_names,
        "scheduled": scheduled_time or "now",
        "duplicate_warnings": duplicate_warnings,
        "carousel_count": len(files) if len(files) > 1 else None
    })

# ─── DELETE POST ──────────────────────────────────────────────────────────────

@app.post("/delete/{post_id}")
async def delete(post_id: int):
    delete_post(post_id)
    return RedirectResponse("/dashboard", status_code=303)

# ─── RETRY POST ───────────────────────────────────────────────────────────────

@app.post("/retry/{post_id}")
async def retry(post_id: int):
    update_post_status(post_id, "queued")
    return RedirectResponse("/dashboard", status_code=303)

# ─── LOGS ─────────────────────────────────────────────────────────────────────

@app.get("/logs/{post_id}", response_class=HTMLResponse)
async def logs(request: Request, post_id: int):
    post = get_post(post_id)
    logs = get_logs(post_id)
    return templates.TemplateResponse("logs.html", {"request": request, "post": post, "logs": logs})

# ─── PLATFORM SETTINGS ────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    platform_configs = get_all_platform_configs()
    all_accounts = get_all_accounts()
    tiktok_accounts = [a for a in all_accounts if a['platform'] == 'tiktok']
    youtube_accounts = [a for a in all_accounts if a['platform'] == 'youtube']
    instagram_accounts = [a for a in all_accounts if a['platform'] == 'instagram']
    facebook_accounts = [a for a in all_accounts if a['platform'] == 'facebook']
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "platform_configs": platform_configs,
        "all_accounts": all_accounts,
        "tiktok_accounts": tiktok_accounts,
        "youtube_accounts": youtube_accounts,
        "instagram_accounts": instagram_accounts,
        "facebook_accounts": facebook_accounts,
    })

@app.post("/settings/save/{platform}")
async def save_settings(platform: str, request: Request):
    form = await request.form()
    config = dict(form)
    save_platform_config(platform, json.dumps(config), connected=True)
    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/save/tiktok_app")
async def save_tiktok_app(request: Request):
    form = await request.form()
    config = dict(form)
    save_platform_config("tiktok_app", json.dumps(config), connected=True)
    return RedirectResponse("/settings", status_code=303)

# ─── MULTI-ACCOUNT MANAGEMENT ─────────────────────────────────────────────────

@app.post("/settings/accounts/tiktok/add")
async def add_tiktok_account(nickname: str = Form(...)):
    account_id = add_account("tiktok", nickname)
    return RedirectResponse(f"/auth/tiktok/start?account_id={account_id}", status_code=303)

@app.post("/settings/accounts/{platform}/add")
async def add_platform_account(platform: str, request: Request):
    form = await request.form()
    nickname = form.get("nickname", "").strip()
    if not nickname:
        return RedirectResponse("/settings", status_code=303)

    if platform == "tiktok":
        account_id = add_account("tiktok", nickname)
        return RedirectResponse(f"/auth/tiktok/start?account_id={account_id}", status_code=303)

    elif platform == "youtube":
        config = {
            "client_id": form.get("client_id", ""),
            "client_secret": form.get("client_secret", ""),
        }
        account_id = add_account("youtube", nickname)
        update_account(account_id, json.dumps(config), connected=False)
        return RedirectResponse(f"/auth/youtube/start?account_id={account_id}", status_code=303)

    elif platform in ("instagram", "facebook"):
        config = {k: v for k, v in form.items() if k != "nickname"}
        account_id = add_account(platform, nickname)
        update_account(account_id, json.dumps(config), connected=True)
        return RedirectResponse("/settings", status_code=303)

    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/accounts/{account_id}/delete")
async def remove_account(account_id: int):
    delete_account(account_id)
    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/accounts/{account_id}/rename")
async def rename_account_route(account_id: int, nickname: str = Form(...)):
    rename_account(account_id, nickname)
    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/disconnect/{platform}")
async def disconnect(platform: str):
    save_platform_config(platform, "{}", connected=False)
    return RedirectResponse("/settings", status_code=303)

# ─── API ENDPOINTS ────────────────────────────────────────────────────────────

@app.get("/api/posts")
def api_posts():
    return get_all_posts()

@app.get("/api/stats")
def api_stats():
    return get_stats()

@app.get("/api/logs/{post_id}")
def api_logs(post_id: int):
    return get_logs(post_id)

@app.get("/api/calendar")
def api_calendar(year: int, month: int):
    posts = get_posts_by_month(year, month)
    grouped = {}
    for post in posts:
        # Determine the display date for the calendar
        date_str = (post.get("scheduled_time") or post.get("posted_time") or post.get("created_at") or "")[:10]
        if not date_str:
            continue
        if date_str not in grouped:
            grouped[date_str] = []
        grouped[date_str].append({
            "id": post["id"],
            "filename": post["filename"],
            "status": post["status"],
            "platforms": post.get("platforms", ""),
            "thumbnail_path": post.get("thumbnail_path"),
            "scheduled_time": post.get("scheduled_time"),
            "posted_time": post.get("posted_time"),
        })
    return grouped

# ─── OAUTH CALLBACKS ──────────────────────────────────────────────────────────

@app.get("/auth/youtube/callback")
async def youtube_callback(request: Request, code: str = None, error: str = None, state: str = None):
    if error:
        return HTMLResponse(f"<h2>Auth Error: {error}</h2><a href='/settings'>Back</a>")

    # account_id passed via OAuth state param (avoids redirect_uri mismatch)
    account_id = int(state) if state and state.isdigit() else None

    if account_id:
        account = get_account(account_id)
        if not account:
            return HTMLResponse("<h2>Account not found</h2><a href='/settings'>Back</a>")
        cfg = json.loads(account.get("config_json") or "{}")
    else:
        config = get_platform_config("youtube")
        if not config:
            return HTMLResponse("<h2>YouTube not configured yet</h2><a href='/settings'>Back</a>")
        cfg = json.loads(config["config_json"])

    from platform_handlers.youtube_handler import YouTubeHandler
    handler = YouTubeHandler(cfg)
    redirect_uri = "http://localhost:8888/auth/youtube/callback"

    try:
        credentials = handler.exchange_code(code, redirect_uri)
        cfg["credentials"] = credentials
        if account_id:
            update_account(account_id, json.dumps(cfg), connected=True)
            acc = get_account(account_id)
            return HTMLResponse(f"<h2>✅ YouTube account '{acc['nickname']}' connected!</h2><a href='/settings'>Back to Settings</a>")
        else:
            save_platform_config("youtube", json.dumps(cfg), connected=True)
            return HTMLResponse("<h2>✅ YouTube connected!</h2><a href='/settings'>Back to Settings</a>")
    except Exception as e:
        return HTMLResponse(f"<h2>Error: {e}</h2><a href='/settings'>Back</a>")

@app.get("/auth/tiktok/callback")
async def tiktok_callback(request: Request, code: str = None, error: str = None, state: str = None):
    if error:
        return HTMLResponse(f"<h2>Auth Error: {error}</h2><a href='/settings'>Back</a>")

    # Try tiktok_app config first
    app_config = get_platform_config("tiktok_app") or get_platform_config("tiktok")
    if not app_config:
        return HTMLResponse("<h2>TikTok not configured yet</h2><a href='/settings'>Back</a>")

    cfg = json.loads(app_config["config_json"])
    account_id = cfg.pop("_pending_account_id", None)
    redirect_uri = cfg.pop("_redirect_uri", str(request.url).split("?")[0])
    code_verifier = cfg.pop("_pkce_verifier", None)

    from platform_handlers.tiktok_handler import TikTokHandler
    handler = TikTokHandler(cfg)

    try:
        token_data = handler.exchange_code(code, redirect_uri, code_verifier=code_verifier)

        if account_id and str(account_id) != 'None':
            # Save to accounts table
            acc = get_account(int(account_id))
            if acc:
                acc_cfg = json.loads(acc.get("config_json") or "{}")
                acc_cfg.update(cfg)  # include client_key etc
                acc_cfg.update(token_data)
                update_account(int(account_id), json.dumps(acc_cfg), connected=True)
                acc = get_account(int(account_id))
                nickname = acc["nickname"]
                return HTMLResponse(f"<h2>TikTok account '{nickname}' connected!</h2><a href='/settings'>Back to Settings</a>")

        # Legacy fallback: save to platform_config
        cfg.update(token_data)
        save_platform_config("tiktok", json.dumps(cfg), connected=True)
        return HTMLResponse("<h2>TikTok connected!</h2><a href='/settings'>Back to Settings</a>")
    except Exception as e:
        return HTMLResponse(f"<h2>Error: {e}</h2><a href='/settings'>Back</a>")

@app.get("/auth/tiktok/start")
async def tiktok_auth_start(request: Request, account_id: int = None):
    # Get app credentials - try tiktok_app first, fall back to tiktok
    app_config = get_platform_config("tiktok_app") or get_platform_config("tiktok")
    if not app_config:
        return HTMLResponse("<h2>TikTok app not configured yet</h2><a href='/settings'>Back</a>")

    cfg = json.loads(app_config["config_json"])
    redirect_uri = "http://localhost:8888/auth/tiktok/callback"
    ngrok_url = cfg.get("ngrok_url", "").strip().rstrip("/")
    if ngrok_url:
        redirect_uri = f"{ngrok_url}/auth/tiktok/callback"

    from platform_handlers.tiktok_handler import TikTokHandler
    handler = TikTokHandler(cfg)

    # Encode account_id in state param
    import secrets as secrets_mod
    state = f"autoposter_{account_id or 'legacy'}_{secrets_mod.token_hex(8)}"
    url = handler.get_auth_url(redirect_uri)
    # Replace state param in URL
    import urllib.parse
    parsed = list(urllib.parse.urlparse(url))
    params = urllib.parse.parse_qs(parsed[4])
    params['state'] = [state]
    parsed[4] = urllib.parse.urlencode(params, doseq=True)
    url = urllib.parse.urlunparse(parsed)

    # Save PKCE verifier and redirect_uri
    cfg["_pkce_verifier"] = handler.config.get("_pkce_verifier")
    cfg["_redirect_uri"] = redirect_uri
    cfg["_pending_account_id"] = account_id
    save_platform_config("tiktok_app", json.dumps(cfg), connected=True)
    # Also keep backward compat
    tiktok_legacy = get_platform_config("tiktok")
    legacy_connected = bool(tiktok_legacy and json.loads(tiktok_legacy["config_json"]).get("access_token"))
    save_platform_config("tiktok", json.dumps(cfg), connected=legacy_connected)
    return RedirectResponse(url)

@app.get("/auth/youtube/start")
async def youtube_auth_start(request: Request, account_id: int = None):
    if account_id:
        account = get_account(account_id)
        if not account:
            return RedirectResponse("/settings")
        cfg = json.loads(account.get("config_json") or "{}")
    else:
        config = get_platform_config("youtube")
        if not config:
            return RedirectResponse("/settings")
        cfg = json.loads(config["config_json"])

    redirect_uri = "http://localhost:8888/auth/youtube/callback"

    from platform_handlers.youtube_handler import YouTubeHandler
    handler = YouTubeHandler(cfg)
    url = handler.get_auth_url(redirect_uri, state=account_id)
    return RedirectResponse(url)


# ─── FEED PREVIEW SHARING ─────────────────────────────────────────────────────

@app.post("/preview/create")
async def create_preview(
    images: List[UploadFile] = File(...),
    caption: str = Form(""),
    mode: str = Form("grid"),
    device: str = Form("mobile")
):
    preview_id = str(uuid.uuid4())[:8]
    preview_subdir = PREVIEW_DIR / preview_id
    preview_subdir.mkdir(exist_ok=True)

    saved = []
    for img in images:
        ext = Path(img.filename).suffix.lower() or ".jpg"
        dest = preview_subdir / f"{len(saved):02d}{ext}"
        with open(dest, "wb") as fh:
            shutil.copyfileobj(img.file, fh)
        saved.append(dest.name)

    with open(preview_subdir / "meta.json", "w") as f:
        json.dump({"caption": caption, "mode": mode, "device": device, "images": saved}, f)

    base_url = "http://localhost:8888"
    try:
        cfg_row = get_platform_config("tiktok")
        if cfg_row:
            cfg_data = json.loads(cfg_row.get("config_json", "{}"))
            ngrok = cfg_data.get("ngrok_url", "").strip().rstrip("/")
            if ngrok:
                base_url = ngrok
    except Exception:
        pass

    return JSONResponse({"success": True, "id": preview_id, "url": f"{base_url}/preview/{preview_id}"})


@app.get("/preview/{preview_id}", response_class=HTMLResponse)
async def view_preview(request: Request, preview_id: str):
    meta_file = PREVIEW_DIR / preview_id / "meta.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    with open(meta_file) as f:
        meta = json.load(f)
    image_urls = [f"/previews/{preview_id}/{name}" for name in meta.get("images", [])]
    return templates.TemplateResponse("preview_page.html", {
        "request": request,
        "preview_id": preview_id,
        "caption": meta.get("caption", ""),
        "mode": meta.get("mode", "grid"),
        "device": meta.get("device", "mobile"),
        "image_urls": image_urls,
    })
