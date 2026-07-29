import sqlite3
from pathlib import Path

DB_PATH = Path("/var/lib/stillhem/stillhem.db")

# The DEFAULT blocklist the built image ships enabled from first boot: the union
# of the social set and the video-streaming set (see blocklists/default.txt).
# News and gaming domains are deliberately excluded. init_db seeds these enabled,
# so a freshly imaged box blocks social + video before the wizard is even run;
# every platform stays toggleable from the dashboard afterwards.
_SEED_PLATFORMS = [
    # (name, display_name, primary_domain, category, domains...)
    ("instagram", "Instagram", "instagram.com", "social",
     ["instagram.com", "cdninstagram.com", "fbcdn.net"]),
    ("tiktok", "TikTok", "tiktok.com", "social",
     ["tiktok.com", "tiktokcdn.com", "tiktokv.com"]),
    ("reddit", "Reddit", "reddit.com", "social",
     ["reddit.com", "redd.it", "redditstatic.com", "redditmedia.com", "reddituploads.com"]),
    ("x", "X", "x.com", "social",
     ["x.com", "twitter.com", "t.co", "twimg.com"]),
    ("facebook", "Facebook", "facebook.com", "social",
     ["facebook.com", "threads.net"]),
    ("snapchat", "Snapchat", "snapchat.com", "social",
     ["snapchat.com", "sc-cdn.net"]),
    ("pinterest", "Pinterest", "pinterest.com", "social",
     ["pinterest.com", "pinimg.com"]),
    ("linkedin", "LinkedIn", "linkedin.com", "social",
     ["linkedin.com", "licdn.com"]),
    ("youtube", "YouTube", "youtube.com", "video",
     ["youtube.com", "youtu.be", "googlevideo.com", "ytimg.com"]),
    ("netflix", "Netflix", "netflix.com", "video",
     ["netflix.com", "nflxvideo.net"]),
    ("twitch", "Twitch", "twitch.tv", "video",
     ["twitch.tv", "twitchsvc.net"]),
]


def get_db(path: Path = DB_PATH) -> sqlite3.Connection:
    # Callers use `with get_db(path) as conn:` — sqlite3.Connection.__exit__
    # commits on success (and rolls back on error), so writes must stay inside
    # that block to be persisted.
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with get_db(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS platforms (
                name           TEXT PRIMARY KEY,
                display_name   TEXT NOT NULL,
                primary_domain TEXT NOT NULL,
                category       TEXT NOT NULL,
                enabled        INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS blocked_domains (
                domain   TEXT PRIMARY KEY,
                preset   TEXT,
                enabled  INTEGER NOT NULL DEFAULT 1,
                added_at TEXT    NOT NULL DEFAULT (datetime('now')),
                platform TEXT    REFERENCES platforms(name)
            );
            CREATE TABLE IF NOT EXISTS category_schedules (
                category   TEXT PRIMARY KEY,   -- 'social' | 'video' | 'custom'
                days       TEXT    NOT NULL,   -- CSV of weekday() ints 0..6, Mon=0
                start_min  INTEGER NOT NULL,   -- minutes since local midnight, 0..1439
                end_min    INTEGER NOT NULL    -- minutes since local midnight, 0..1439
            );
        """)
        # Seed platforms (only if they don't exist yet)
        for name, display_name, primary_domain, category, domains in _SEED_PLATFORMS:
            conn.execute(
                "INSERT OR IGNORE INTO platforms (name, display_name, primary_domain, category)"
                " VALUES (?, ?, ?, ?)",
                (name, display_name, primary_domain, category),
            )
            for domain in domains:
                conn.execute(
                    "INSERT OR IGNORE INTO blocked_domains (domain, platform) VALUES (?, ?)",
                    (domain, name),
                )


def get_config(path: Path, key: str) -> str | None:
    with get_db(path) as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_config(path: Path, key: str, value: str) -> None:
    with get_db(path) as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))


def delete_config(path: Path, key: str) -> None:
    with get_db(path) as conn:
        conn.execute("DELETE FROM config WHERE key = ?", (key,))
