import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "db" / "autoposter.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            content_type TEXT,
            caption TEXT,
            hashtags TEXT,
            platforms TEXT,
            status TEXT DEFAULT 'queued',
            scheduled_time TEXT,
            posted_time TEXT,
            error_message TEXT,
            youtube_id TEXT,
            tiktok_id TEXT,
            instagram_id TEXT,
            facebook_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS platform_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT UNIQUE NOT NULL,
            config_json TEXT,
            connected INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS post_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            platform TEXT,
            message TEXT,
            level TEXT DEFAULT 'info',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            nickname TEXT NOT NULL,
            config_json TEXT DEFAULT '{}',
            connected INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Migrate: add new columns if they don't exist yet
    for col_def in ["thumbnail_path TEXT", "per_platform_data TEXT", "carousel_paths TEXT"]:
        try:
            c.execute(f"ALTER TABLE posts ADD COLUMN {col_def}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_all_posts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM posts ORDER BY created_at DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_post(post_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE id=?", (post_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def add_post(filename, filepath, content_type, caption, hashtags, platforms, scheduled_time=None,
             thumbnail_path=None, per_platform_data=None, carousel_paths=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO posts (filename, filepath, content_type, caption, hashtags, platforms,
                           scheduled_time, status, thumbnail_path, per_platform_data, carousel_paths)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (filename, filepath, content_type, caption, hashtags, platforms, scheduled_time,
          'scheduled' if scheduled_time else 'queued', thumbnail_path, per_platform_data, carousel_paths))
    conn.commit()
    post_id = c.lastrowid
    conn.close()
    return post_id

def update_post_status(post_id, status, error_message=None, platform_id=None, platform=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if status == "posted":
        c.execute("UPDATE posts SET status=?, posted_time=datetime('now') WHERE id=?", (status, post_id))
    else:
        c.execute("UPDATE posts SET status=?, error_message=? WHERE id=?", (status, error_message, post_id))
    conn.commit()
    conn.close()

def delete_post(post_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM posts WHERE id=?", (post_id,))
    c.execute("DELETE FROM post_log WHERE post_id=?", (post_id,))
    conn.commit()
    conn.close()

def get_pending_posts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    c.execute("""
        SELECT * FROM posts 
        WHERE status='queued' 
        OR (status='scheduled' AND scheduled_time <= ?)
    """, (now,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_platform_config(platform, config_json, connected=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO platform_config (platform, config_json, connected, updated_at)
        VALUES (?, ?, ?, datetime('now'))
    ''', (platform, config_json, 1 if connected else 0))
    conn.commit()
    conn.close()

def get_platform_config(platform):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM platform_config WHERE platform=?", (platform,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_platform_configs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT platform, connected, updated_at FROM platform_config")
    rows = c.fetchall()
    conn.close()
    return {row['platform']: dict(row) for row in rows}

def add_log(post_id, platform, message, level="info"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO post_log (post_id, platform, message, level) VALUES (?,?,?,?)",
              (post_id, platform, message, level))
    conn.commit()
    conn.close()

def get_logs(post_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM post_log WHERE post_id=? ORDER BY created_at ASC", (post_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_posts_by_month(year, month):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    prefix = f"{year:04d}-{month:02d}"
    c.execute("""
        SELECT * FROM posts
        WHERE scheduled_time LIKE ? OR posted_time LIKE ? OR
              (scheduled_time IS NULL AND created_at LIKE ?)
        ORDER BY COALESCE(scheduled_time, posted_time, created_at) ASC
    """, (f"{prefix}%", f"{prefix}%", f"{prefix}%"))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) as count FROM posts GROUP BY status")
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def get_tiktok_accounts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE platform='tiktok' ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_accounts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM accounts ORDER BY platform ASC, created_at ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_accounts_by_platform(platform):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE platform=? ORDER BY created_at ASC", (platform,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_account(platform, nickname):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO accounts (platform, nickname, config_json, connected) VALUES (?,?,?,?)",
              (platform, nickname, '{}', 0))
    conn.commit()
    account_id = c.lastrowid
    conn.close()
    return account_id

def get_account(account_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE id=?", (account_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_account(account_id, config_json, connected=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE accounts SET config_json=?, connected=? WHERE id=?",
              (config_json, 1 if connected else 0, account_id))
    conn.commit()
    conn.close()

def delete_account(account_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()

def rename_account(account_id, nickname):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE accounts SET nickname=? WHERE id=?", (nickname, account_id))
    conn.commit()
    conn.close()

def check_duplicate_post(filepath, platform_entry, exclude_post_id=None):
    """Return a post dict if this filepath was already successfully posted to the given platform:account_id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if exclude_post_id is not None:
        c.execute("SELECT id, status, platforms FROM posts WHERE filepath=? AND status='posted' AND id!=?",
                  (filepath, exclude_post_id))
    else:
        c.execute("SELECT id, status, platforms FROM posts WHERE filepath=? AND status='posted'",
                  (filepath,))
    rows = c.fetchall()
    conn.close()
    for row in rows:
        platforms_list = [p.strip() for p in (row['platforms'] or '').split(',')]
        if platform_entry in platforms_list:
            return dict(row)
    return None

def check_queued_duplicate(filename, platform_entry):
    """Return a post dict if this filename is already queued/scheduled/posted for the given platform:account_id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, status, platforms FROM posts WHERE filename=? AND status IN ('queued','scheduled','posted')",
              (filename,))
    rows = c.fetchall()
    conn.close()
    for row in rows:
        platforms_list = [p.strip() for p in (row['platforms'] or '').split(',')]
        if platform_entry in platforms_list:
            return dict(row)
    return None
