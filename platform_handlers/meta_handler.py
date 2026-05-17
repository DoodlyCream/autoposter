"""
Meta Platform Handler (Instagram + Facebook)
Uses Meta Graph API
Setup:
1. Go to https://developers.facebook.com
2. Create an app → Business type
3. Add Instagram Graph API + Pages API products
4. Get a long-lived page access token
5. For Instagram: must be a Professional (Business/Creator) account linked to a Facebook Page
"""
import json
import sqlite3
from pathlib import Path
import requests

DB_PATH = Path(__file__).parent.parent / "db" / "autoposter.db"

def _get_ngrok_url():
    try:
        con = sqlite3.connect(str(DB_PATH))
        row = con.execute(
            "SELECT config_json FROM platform_config WHERE platform='tiktok_app'"
        ).fetchone()
        con.close()
        if row:
            cfg = json.loads(row[0])
            return cfg.get("ngrok_url", "").strip().rstrip("/")
    except Exception:
        pass
    return ""

def get_handler(config_json):
    return MetaHandler(json.loads(config_json))

class MetaHandler:
    def __init__(self, config):
        self.config = config
        self.app_id = config.get("app_id")
        self.app_secret = config.get("app_secret")
        self.page_access_token = config.get("page_access_token")
        self.page_id = config.get("page_id")
        self.instagram_account_id = config.get("instagram_account_id")

    def post_facebook(self, filepath, caption, hashtags, content_type):
        try:
            if not self.page_access_token or not self.page_id:
                return False, "Missing Facebook page credentials"

            full_caption = caption or ""
            if hashtags:
                full_caption += "\n\n" + hashtags

            if content_type == "video":
                url = f"https://graph.facebook.com/v18.0/{self.page_id}/videos"
                with open(filepath, "rb") as f:
                    resp = requests.post(url, data={
                        "description": full_caption,
                        "access_token": self.page_access_token
                    }, files={"source": f})
            else:
                url = f"https://graph.facebook.com/v18.0/{self.page_id}/photos"
                with open(filepath, "rb") as f:
                    resp = requests.post(url, data={
                        "caption": full_caption,
                        "access_token": self.page_access_token
                    }, files={"source": f})

            result = resp.json()
            if "error" in result:
                return False, result["error"].get("message", str(result))

            post_id = result.get("id") or result.get("post_id")
            return True, f"Facebook post ID: {post_id}"

        except Exception as e:
            return False, str(e)

    def post_instagram(self, filepath, caption, hashtags, content_type):
        try:
            if not self.page_access_token or not self.instagram_account_id:
                return False, "Missing Instagram credentials"

            full_caption = caption or ""
            if hashtags:
                full_caption += "\n\n" + hashtags

            # If filepath is local, serve it via the ngrok tunnel
            media_url = filepath
            if not filepath.startswith("http"):
                ngrok_url = _get_ngrok_url()
                if not ngrok_url:
                    return False, "Instagram requires a public URL — ngrok_url not configured in TikTok app settings"
                media_url = f"{ngrok_url}/queue_files/{Path(filepath).name}"

            # Step 1: Create media container
            ig_url = f"https://graph.facebook.com/v18.0/{self.instagram_account_id}/media"

            if content_type == "video":
                # For Reels
                container_resp = requests.post(ig_url, data={
                    "media_type": "REELS",
                    "video_url": media_url,
                    "caption": full_caption,
                    "access_token": self.page_access_token
                })
            else:
                container_resp = requests.post(ig_url, data={
                    "image_url": media_url,
                    "caption": full_caption,
                    "access_token": self.page_access_token
                })

            container_data = container_resp.json()

            if "error" in container_data:
                return False, f"IG container error: {container_data['error'].get('message')}"

            container_id = container_data.get("id")
            if not container_id:
                return False, f"No container ID: {container_data}"

            # Step 2: Publish
            publish_resp = requests.post(
                f"https://graph.facebook.com/v18.0/{self.instagram_account_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.page_access_token
                }
            )

            publish_data = publish_resp.json()
            if "error" in publish_data:
                return False, f"IG publish error: {publish_data['error'].get('message')}"

            return True, f"Instagram post ID: {publish_data.get('id')}"

        except Exception as e:
            return False, str(e)

    def post_instagram_carousel(self, filepaths, caption, hashtags):
        try:
            if not self.page_access_token or not self.instagram_account_id:
                return False, "Missing Instagram credentials"

            full_caption = caption or ""
            if hashtags:
                full_caption += "\n\n" + hashtags

            ngrok_url = _get_ngrok_url()
            if not ngrok_url:
                return False, "Instagram carousel requires ngrok_url — configure it in TikTok app settings"

            ig_url = f"https://graph.facebook.com/v18.0/{self.instagram_account_id}/media"
            container_ids = []

            for fp in filepaths:
                media_url = f"{ngrok_url}/queue_files/{Path(fp).name}"
                resp = requests.post(ig_url, data={
                    "image_url": media_url,
                    "is_carousel_item": "true",
                    "access_token": self.page_access_token
                })
                data = resp.json()
                if "error" in data:
                    return False, f"IG carousel item error: {data['error'].get('message')}"
                container_ids.append(data["id"])

            carousel_resp = requests.post(ig_url, data={
                "media_type": "CAROUSEL_ALBUM",
                "children": ",".join(container_ids),
                "caption": full_caption,
                "access_token": self.page_access_token
            })
            carousel_data = carousel_resp.json()
            if "error" in carousel_data:
                return False, f"IG carousel container error: {carousel_data['error'].get('message')}"

            carousel_id = carousel_data.get("id")
            publish_resp = requests.post(
                f"https://graph.facebook.com/v18.0/{self.instagram_account_id}/media_publish",
                data={"creation_id": carousel_id, "access_token": self.page_access_token}
            )
            publish_data = publish_resp.json()
            if "error" in publish_data:
                return False, f"IG carousel publish error: {publish_data['error'].get('message')}"

            return True, f"Instagram carousel posted ({len(filepaths)} images). ID: {publish_data.get('id')}"

        except Exception as e:
            return False, str(e)

    def post_facebook_carousel(self, filepaths, caption, hashtags):
        try:
            if not self.page_access_token or not self.page_id:
                return False, "Missing Facebook credentials"

            full_caption = caption or ""
            if hashtags:
                full_caption += "\n\n" + hashtags

            photo_ids = []
            for fp in filepaths:
                with open(fp, "rb") as f:
                    resp = requests.post(
                        f"https://graph.facebook.com/v18.0/{self.page_id}/photos",
                        data={"published": "false", "access_token": self.page_access_token},
                        files={"source": f}
                    )
                data = resp.json()
                if "error" in data:
                    return False, f"FB photo upload error: {data['error'].get('message')}"
                photo_ids.append({"media_fbid": data["id"]})

            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{self.page_id}/feed",
                data={
                    "message": full_caption,
                    "attached_media": json.dumps(photo_ids),
                    "access_token": self.page_access_token
                }
            )
            data = resp.json()
            if "error" in data:
                return False, f"FB multi-photo post error: {data['error'].get('message')}"

            return True, f"Facebook multi-photo post ({len(filepaths)} images). ID: {data.get('id')}"

        except Exception as e:
            return False, str(e)

    def post(self, filepath, caption, hashtags, content_type, platform="facebook", platform_data=None, carousel_paths=None):
        if platform == "instagram":
            if content_type == "carousel" or (carousel_paths and len(carousel_paths) > 1):
                paths = carousel_paths if carousel_paths else [filepath]
                return self.post_instagram_carousel(paths, caption, hashtags)
            return self.post_instagram(filepath, caption, hashtags, content_type)
        else:
            if content_type == "carousel" or (carousel_paths and len(carousel_paths) > 1):
                paths = carousel_paths if carousel_paths else [filepath]
                return self.post_facebook_carousel(paths, caption, hashtags)
            return self.post_facebook(filepath, caption, hashtags, content_type)
