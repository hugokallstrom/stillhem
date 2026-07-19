import secrets
from pathlib import Path

import bcrypt

from .db import get_db


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
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('session_token', ?)",
            (token,),
        )
    return token


def validate_session_token(token: str, db_path: Path) -> bool:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'session_token'"
        ).fetchone()
    if row is None:
        return False
    return secrets.compare_digest(token, row["value"])
