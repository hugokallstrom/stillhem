import sqlite3
from pathlib import Path
from stillhem.db import init_db, get_db


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    names = {r["name"] for r in rows}
    assert "config" in names
    assert "blocked_domains" in names


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    init_db(db_path)  # must not raise or corrupt


def test_get_db_returns_row_factory(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_db(db_path) as conn:
        conn.execute("INSERT INTO config (key, value) VALUES ('k', 'v')")
    with get_db(db_path) as conn:
        row = conn.execute("SELECT key, value FROM config").fetchone()
    assert row["key"] == "k"
    assert row["value"] == "v"


from stillhem.db import delete_config, get_config, set_config


def test_set_and_get_config(db_path: Path) -> None:
    assert get_config(db_path, "k") is None
    set_config(db_path, "k", "v")
    assert get_config(db_path, "k") == "v"


def test_set_config_overwrites(db_path: Path) -> None:
    set_config(db_path, "k", "v1")
    set_config(db_path, "k", "v2")
    assert get_config(db_path, "k") == "v2"


def test_delete_config_removes_key(db_path: Path) -> None:
    set_config(db_path, "k", "v")
    delete_config(db_path, "k")
    assert get_config(db_path, "k") is None


def test_delete_config_missing_key_is_noop(db_path: Path) -> None:
    delete_config(db_path, "absent")  # must not raise
    assert get_config(db_path, "absent") is None
