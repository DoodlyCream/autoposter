"""
Scheduler & Posting Engine
Runs in background, checks for queued/scheduled posts every minute
"""
import json
import threading
import time
from pathlib import Path
from database import get_pending_posts, update_post_status, add_log, get_platform_config, get_account, check_duplicate_post

def run_post(post):
    platforms = post.get("platforms", "").split(",")
    filepath = post["filepath"]
    caption = post.get("caption", "")
    hashtags = post.get("hashtags", "")
    content_type = post.get("content_type", "video")
    post_id = post["id"]
    thumbnail_path = post.get("thumbnail_path")
    try:
        pdata = json.loads(post.get("per_platform_data") or "{}")
    except Exception:
        pdata = {}
    try:
        carousel_paths = json.loads(post.get("carousel_paths") or "null")
    except Exception:
        carousel_paths = None

    if not Path(filepath).exists():
        update_post_status(post_id, "failed", f"File not found: {filepath}")
        add_log(post_id, "system", f"File not found: {filepath}", "error")
        return

    any_success = False
    all_failed = True

    for platform_entry in platforms:
        platform_entry = platform_entry.strip()
        if not platform_entry:
            continue

        # Check if this is a specific account (e.g. "tiktok:3")
        if ":" in platform_entry:
            platform_name, account_id_str = platform_entry.split(":", 1)
            platform_name = platform_name.strip()
            try:
                account_id = int(account_id_str)
            except ValueError:
                add_log(post_id, platform_entry, f"Invalid account ID: {account_id_str}", "warning")
                continue

            account = get_account(account_id)
            if not account or not account.get("connected"):
                add_log(post_id, platform_entry, f"Account ID {account_id} not connected — skipping", "warning")
                continue

            account_cfg = json.loads(account.get("config_json") or "{}")
            nickname = account.get("nickname", f"Account {account_id}")

            # Duplication guard: skip if this file was already posted to this account
            existing = check_duplicate_post(filepath, platform_entry, exclude_post_id=post_id)
            if existing:
                add_log(post_id, platform_entry,
                        f"⚠️ Duplicate guard: this video was already posted to '{nickname}' (post #{existing['id']}) — skipping",
                        "warning")
                all_failed = False
                continue

            try:
                if platform_name == "tiktok":
                    from platform_handlers.tiktok_handler import get_handler
                    handler = get_handler(json.dumps(account_cfg))
                    success, message = handler.post(filepath, caption, hashtags, content_type,
                                                    platform_data=pdata.get("tiktok", {}),
                                                    carousel_paths=carousel_paths)
                elif platform_name == "youtube":
                    from platform_handlers.youtube_handler import get_handler
                    handler = get_handler(json.dumps(account_cfg))
                    success, message = handler.post(filepath, caption, hashtags, content_type,
                                                    platform_data=pdata.get("youtube", {}),
                                                    thumbnail_path=thumbnail_path)
                elif platform_name in ("instagram", "facebook"):
                    from platform_handlers.meta_handler import get_handler
                    handler = get_handler(json.dumps(account_cfg))
                    success, message = handler.post(filepath, caption, hashtags, content_type,
                                                    platform=platform_name,
                                                    platform_data=pdata.get(platform_name, {}),
                                                    carousel_paths=carousel_paths)
                else:
                    add_log(post_id, platform_entry, f"Multi-account not supported for {platform_name}", "warning")
                    continue

                if success:
                    any_success = True
                    all_failed = False
                    add_log(post_id, platform_entry, f"✅ Posted to '{nickname}' successfully: {message}", "success")
                else:
                    add_log(post_id, platform_entry, f"❌ Failed for '{nickname}': {message}", "error")
            except Exception as e:
                add_log(post_id, platform_entry, f"❌ Exception for '{nickname}': {str(e)}", "error")
            continue

        # Single-platform (existing logic)
        platform = platform_entry
        config = get_platform_config(platform)
        if not config or not config.get("connected"):
            add_log(post_id, platform, f"{platform} not connected — skipping", "warning")
            continue

        try:
            if platform == "youtube":
                from platform_handlers.youtube_handler import get_handler
                handler = get_handler(config["config_json"])
                success, message = handler.post(filepath, caption, hashtags, content_type,
                                                platform_data=pdata.get("youtube", {}),
                                                thumbnail_path=thumbnail_path)

            elif platform == "tiktok":
                from platform_handlers.tiktok_handler import get_handler
                handler = get_handler(config["config_json"])
                success, message = handler.post(filepath, caption, hashtags, content_type,
                                                platform_data=pdata.get("tiktok", {}))

            elif platform == "instagram":
                from platform_handlers.meta_handler import get_handler
                handler = get_handler(config["config_json"])
                success, message = handler.post(filepath, caption, hashtags, content_type,
                                                platform="instagram",
                                                platform_data=pdata.get("instagram", {}))

            elif platform == "facebook":
                from platform_handlers.meta_handler import get_handler
                handler = get_handler(config["config_json"])
                success, message = handler.post(filepath, caption, hashtags, content_type,
                                                platform="facebook",
                                                platform_data=pdata.get("facebook", {}))

            else:
                add_log(post_id, platform, f"Unknown platform: {platform}", "warning")
                continue

            if success:
                any_success = True
                all_failed = False
                add_log(post_id, platform, f"✅ Posted successfully: {message}", "success")
            else:
                add_log(post_id, platform, f"❌ Failed: {message}", "error")

        except Exception as e:
            add_log(post_id, platform, f"❌ Exception: {str(e)}", "error")

    if any_success:
        update_post_status(post_id, "posted")
    elif all_failed:
        update_post_status(post_id, "failed", "All platforms failed — check logs")
    else:
        update_post_status(post_id, "partial", "Some platforms failed — check logs")


def scheduler_loop():
    while True:
        try:
            pending = get_pending_posts()
            for post in pending:
                update_post_status(post["id"], "processing")
                t = threading.Thread(target=run_post, args=(post,), daemon=True)
                t.start()
        except Exception as e:
            print(f"[Scheduler Error] {e}")
        time.sleep(60)  # Check every 60 seconds


def start_scheduler():
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    print("[Scheduler] Started — checking for posts every 60 seconds")
