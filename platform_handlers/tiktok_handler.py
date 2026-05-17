"""
TikTok Platform Handler
Uses TikTok Content Posting API
Setup:
1. Go to https://developers.tiktok.com
2. Create a developer account
3. Create an app → request "Video Upload" and "Photo Publish" permissions
4. Use sandbox for testing (immediate), production requires review (1-2 weeks)
"""
import json
import sqlite3
import requests
from pathlib import Path

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
    return TikTokHandler(json.loads(config_json))

class TikTokHandler:
    def __init__(self, config):
        self.config = config
        self.client_key = config.get("client_key")
        self.client_secret = config.get("client_secret")
        self.access_token = config.get("access_token")

    def post(self, filepath, caption, hashtags, content_type, platform_data=None, carousel_paths=None):
        try:
            if not self.access_token:
                return False, "No access token. Please authenticate TikTok first."

            pd = platform_data or {}
            tt_title = pd.get("title") or (caption[:90] if caption else "")
            tt_description = pd.get("caption") or ""
            privacy_level = pd.get("privacy_level", "PUBLIC_TO_EVERYONE")
            disable_duet = pd.get("disable_duet", False)
            disable_comment = pd.get("disable_comment", False)
            disable_stitch = pd.get("disable_stitch", False)
            auto_add_music = pd.get("auto_add_music", False)

            if content_type == "carousel" or (carousel_paths and len(carousel_paths) > 1):
                paths = carousel_paths if carousel_paths else [filepath]
                return self._post_photo_carousel(paths, tt_title, privacy_level, disable_comment, auto_add_music)

            if content_type not in ["video"]:
                return False, "TikTok API supports video uploads or photo carousels (multiple images) only"

            # Step 1: Initialize upload
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            file_size = __import__('os').path.getsize(filepath)

            init_data = {
                "post_info": {
                    "title": tt_title,
                    "description": tt_description,
                    "privacy_level": privacy_level,
                    "disable_duet": disable_duet,
                    "disable_comment": disable_comment,
                    "disable_stitch": disable_stitch,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": file_size,
                    "total_chunk_count": 1
                }
            }

            init_resp = requests.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers=headers,
                json=init_data
            )

            if init_resp.status_code != 200:
                return False, f"TikTok init failed: {init_resp.text}"

            result = init_resp.json()
            publish_id = result.get("data", {}).get("publish_id")
            upload_url = result.get("data", {}).get("upload_url")

            if not upload_url:
                return False, f"No upload URL received: {init_resp.text}"

            # Step 2: Upload the file
            with open(filepath, "rb") as f:
                video_data = f.read()

            upload_headers = {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
                "Content-Length": str(file_size)
            }

            upload_resp = requests.put(upload_url, headers=upload_headers, data=video_data)

            if upload_resp.status_code not in [200, 201, 206]:
                return False, f"TikTok upload failed: {upload_resp.text}"

            return True, f"TikTok post submitted. Publish ID: {publish_id}"

        except Exception as e:
            return False, str(e)

    def _post_photo_carousel(self, filepaths, title, privacy_level, disable_comment, auto_add_music=False):
        try:
            ngrok_url = _get_ngrok_url()
            if not ngrok_url:
                return False, "TikTok photo carousel requires ngrok_url — configure it in TikTok app settings"

            photo_urls = [f"{ngrok_url}/queue_files/{Path(fp).name}" for fp in filepaths]

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            init_data = {
                "post_mode": "DIRECT_POST",
                "media_type": "PHOTO",
                "post_info": {
                    "title": title,
                    "privacy_level": privacy_level,
                    "disable_comment": disable_comment,
                    "auto_add_music": auto_add_music
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_images": photo_urls,
                    "photo_cover_index": 0
                }
            }

            resp = requests.post(
                "https://open.tiktokapis.com/v2/post/publish/content/init/",
                headers=headers,
                json=init_data
            )

            if resp.status_code != 200:
                return False, f"TikTok photo carousel failed: {resp.text}"

            result = resp.json()
            publish_id = result.get("data", {}).get("publish_id")
            return True, f"TikTok photo carousel submitted ({len(filepaths)} images). Publish ID: {publish_id}"

        except Exception as e:
            return False, str(e)

    def get_auth_url(self, redirect_uri):
        import urllib.parse, secrets, hashlib, base64
        # Generate PKCE code_verifier and code_challenge (required by TikTok)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        # Store verifier in config so callback can retrieve it
        self.config["_pkce_verifier"] = code_verifier
        params = {
            "client_key": self.client_key,
            "scope": "video.upload,video.publish,video.list,photo.publish",
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": "autoposter",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        return "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params)

    def exchange_code(self, code, redirect_uri, code_verifier=None):
        payload = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier
        resp = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data=payload)
        data = resp.json()
        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "open_id": data.get("open_id")
        }
