import secrets
import time
from pathlib import Path

import bcrypt

from .db import get_db

SESSION_TTL_SECONDS = 30 * 60


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def set_password(password: str, db_path: Path) -> None:
    hashed = hash_password(password)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('password_hash', ?)",
            (hashed,),
        )


def check_password(password: str, db_path: Path) -> bool:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'password_hash'"
        ).fetchone()
    if row is None:
        return False
    return verify_password(password, row["value"])


def is_password_set(db_path: Path) -> bool:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'password_hash'"
        ).fetchone()
    return row is not None


def create_session_token(db_path: Path) -> str:
    token = secrets.token_urlsafe(32)
    expires = time.time() + SESSION_TTL_SECONDS
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('session_token', ?)",
            (token,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('session_expires', ?)",
            (str(expires),),
        )
    return token


def validate_session_token(token: str, db_path: Path) -> bool:
    """Return True if `token` is the active session and has not idled out.

    On success the idle window is slid forward (a fresh session_expires is
    written), so continued activity keeps the session alive. Both session keys
    are cleared ONLY when the matching token has expired — a wrong or stale
    token returns False without disturbing a valid session. This writes on the
    success path by design; require_auth is the sole caller and every protected
    handler funnels through it.
    """
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'session_token'"
        ).fetchone()
        if row is None or not secrets.compare_digest(token, row["value"]):
            return False
        exp = conn.execute(
            "SELECT value FROM config WHERE key = 'session_expires'"
        ).fetchone()
        expired = True
        if exp is not None:
            try:
                expired = time.time() >= float(exp["value"])
            except ValueError:
                expired = True
        if expired:
            conn.execute(
                "DELETE FROM config WHERE key IN ('session_token', 'session_expires')"
            )
            return False
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('session_expires', ?)",
            (str(time.time() + SESSION_TTL_SECONDS),),
        )
        return True
