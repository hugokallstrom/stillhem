import sqlite3
from pathlib import Path

DB_PATH = Path("/var/lib/stillhem/stillhem.db")


def get_db(path: Path = DB_PATH) -> sqlite3.Connection:
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
            CREATE TABLE IF NOT EXISTS blocked_domains (
                domain   TEXT PRIMARY KEY,
                preset   TEXT,
                enabled  INTEGER NOT NULL DEFAULT 1,
                added_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)


def get_config(path: Path, key: str) -> str | None:
    with get_db(path) as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_config(path: Path, key: str, value: str) -> None:
    with get_db(path) as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
