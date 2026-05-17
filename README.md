# ⚡ Build & Chill Auto Poster

A local Mac app to auto-post content to YouTube, TikTok, Instagram, and Facebook.
No subscriptions. No cloud. Runs on your Mac.

---

## 🚀 Quick Start

1. **Put this folder somewhere on your Mac** (e.g. your Desktop or Documents)

2. **Open Terminal and run:**
   ```bash
   cd ~/Desktop/AutoPoster   # or wherever you put it
   chmod +x start.sh
   ./start.sh
   ```

3. **Your browser will open automatically** at http://localhost:8888

That's it. The app is running.

---

## 📁 Folder Structure

```
AutoPoster/
├── queue/          ← Drop files here (auto-picked up)
├── posted/         ← Completed posts moved here
├── failed/         ← Failed posts moved here
├── db/             ← SQLite database (don't touch)
├── platform_handlers/
│   ├── youtube_handler.py
│   ├── tiktok_handler.py
│   └── meta_handler.py
├── templates/      ← Dashboard HTML
├── main.py         ← FastAPI app
├── scheduler.py    ← Background posting engine
├── database.py     ← Database layer
├── start.sh        ← One-click start
└── requirements.txt
```

---

## 🔌 Connecting Platforms

Go to **http://localhost:8888/settings** after starting.

### YouTube
1. Go to https://console.cloud.google.com
2. Create a project → Enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials (Web App type)
4. Add redirect URI: `http://localhost:8888/auth/youtube/callback`
5. Paste Client ID + Secret in Settings → click **Connect with Google**

### TikTok
1. Go to https://developers.tiktok.com → Register
2. Create an app → Request **Video Upload** permission
3. Set redirect URI: `http://localhost:8888/auth/tiktok/callback`
4. Sandbox mode works immediately (no review needed for testing)
5. For public posting: submit app for review (~1-2 weeks)

### Instagram
1. Go to https://developers.facebook.com → Create App (Business type)
2. Add **Instagram Graph API** product
3. Your Instagram must be a **Professional account** linked to a Facebook Page
4. Generate a long-lived Page Access Token via Graph API Explorer
5. Find your Instagram Business Account ID
6. Paste all credentials in Settings

### Facebook
1. Same Meta app as Instagram
2. Add **Pages API** product
3. Get your Page ID from Facebook Page Settings
4. Generate a long-lived Page Access Token with `pages_manage_posts` permission

---

## 📤 Posting Content

### Option 1: Dashboard Upload
- Go to http://localhost:8888
- Upload a file, write your caption + hashtags
- Select platforms
- Leave schedule blank for immediate, or pick a date/time
- Hit **Add to Queue**

### Option 2: Drop files in /queue folder
- The scheduler checks every 60 seconds
- Files dropped in `/queue` need to be added via the dashboard to set caption/platforms

---

## 🔄 How the Scheduler Works

- Runs in the background while the app is open
- Checks every **60 seconds** for queued or scheduled posts
- Posts run in parallel threads (one per platform)
- Check logs for each post at: Dashboard → Logs button

---

## 🛑 Stopping the App

Press `Ctrl+C` in Terminal.

To restart: run `./start.sh` again.

---

## 💡 Tips

- **Videos** work on all platforms (YouTube, TikTok, Instagram Reels, Facebook)
- **Images** work on Instagram and Facebook (not YouTube/TikTok via API)
- Keep captions under 150 chars for TikTok (hard limit)
- Instagram requires a **public URL** for video uploads — local file path works only for Facebook/YouTube direct upload. For Instagram video, consider hosting on a public URL or Dropbox public link.
- Reschedule failed posts using the **Retry** button on the dashboard

---

Built for Build & Chill 🤙
