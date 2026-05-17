"""
YouTube Platform Handler
Uses YouTube Data API v3
Setup: https://console.cloud.google.com → Create project → Enable YouTube Data API v3 → Create OAuth2 credentials
"""
import json
import os
import pickle
from pathlib import Path

def get_handler(config_json):
    return YouTubeHandler(json.loads(config_json))

class YouTubeHandler:
    def __init__(self, config):
        self.config = config
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")

    def post(self, filepath, caption, hashtags, content_type, platform_data=None, thumbnail_path=None):
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            creds_data = self.config.get("credentials")
            if not creds_data:
                return False, "No credentials found. Please authenticate YouTube first."

            creds = Credentials(
                token=creds_data.get("token"),
                refresh_token=creds_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
            )

            youtube = build("youtube", "v3", credentials=creds)

            pd = platform_data or {}
            tags = [h.strip("#") for h in hashtags.split()] if hashtags else []
            title = pd.get("title") or (caption[:100] if caption else Path(filepath).stem)
            description = pd.get("description") or caption or ""
            privacy = pd.get("privacy", "public")
            category_id = str(pd.get("category_id", "22"))

            if content_type == "video":
                body = {
                    "snippet": {
                        "title": title,
                        "description": description,
                        "tags": tags,
                        "categoryId": category_id
                    },
                    "status": {"privacyStatus": privacy}
                }
                media = MediaFileUpload(filepath, chunksize=-1, resumable=True)
                request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)
                response = request.execute()
                video_id = response["id"]

                # Upload custom thumbnail if provided
                if thumbnail_path and Path(thumbnail_path).exists():
                    try:
                        youtube.thumbnails().set(
                            videoId=video_id,
                            media_body=MediaFileUpload(thumbnail_path)
                        ).execute()
                    except Exception as thumb_err:
                        return True, f"https://youtube.com/watch?v={video_id} (thumbnail failed: {thumb_err})"

                return True, f"https://youtube.com/watch?v={video_id}"
            else:
                return False, "YouTube only supports video uploads via API"

        except Exception as e:
            return False, str(e)

    def get_auth_url(self, redirect_uri, state=None):
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"],
            redirect_uri=redirect_uri
        )
        kwargs = {"prompt": "consent", "access_type": "offline"}
        if state is not None:
            kwargs["state"] = str(state)
        auth_url, _ = flow.authorization_url(**kwargs)
        return auth_url

    def exchange_code(self, code, redirect_uri):
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"],
            redirect_uri=redirect_uri
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }
