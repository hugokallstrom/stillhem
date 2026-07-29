import os
import sqlite3
from pathlib import Path
from stillhem.blocklist import (
    add_domain,
    add_custom_domain,
    remove_domain,
    list_domains,
    export_to_file,
    import_preset,
    get_categories,
    list_platforms,
    toggle_platform,
)

PRESET_DIR = str(Path(__file__).parent.parent / "blocklists")


# ── Helpers ──────────────────────────────────────────────────────────────────

def domain_set(db_path):
    return {d["domain"] for d in list_domains(db_path)}


def _bare_db(tmp_path):
    """Return a path to a minimal DB with the schema but no seed data."""
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE platforms (name TEXT PRIMARY KEY, display_name TEXT NOT NULL,"
        " primary_domain TEXT NOT NULL, category TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)"
    )
    conn.execute(
        "CREATE TABLE blocked_domains (domain TEXT PRIMARY KEY, preset TEXT,"
        " enabled INTEGER NOT NULL DEFAULT 1,"
        " added_at TEXT NOT NULL DEFAULT (datetime('now')), platform TEXT)"
    )
    conn.commit()
    conn.close()
    return db


# ── add_domain ────────────────────────────────────────────────────────────────

def test_add_and_list_domain(db_path: Path) -> None:
    # DB is pre-seeded; check the domain exists in the result set
    assert "instagram.com" in domain_set(db_path)


def test_add_new_domain(db_path: Path) -> None:
    add_domain("example-test.com", db_path)
    assert "example-test.com" in domain_set(db_path)


def test_add_domain_normalises_whitespace_and_case(db_path: Path) -> None:
    add_domain("  NewSite.COM  ", db_path)
    assert "newsite.com" in domain_set(db_path)


def test_add_domain_strips_trailing_dot(db_path: Path) -> None:
    add_domain("newsite.com.", db_path)
    assert "newsite.com" in domain_set(db_path)


def test_add_domain_is_idempotent(db_path: Path) -> None:
    before = len(list_domains(db_path))
    add_domain("instagram.com", db_path)
    after = len(list_domains(db_path))
    assert after == before  # INSERT OR IGNORE: no duplicate


def test_remove_domain(db_path: Path) -> None:
    add_domain("tiktok.com", db_path)
    remove_domain("tiktok.com", db_path)
    assert "tiktok.com" not in domain_set(db_path)


def test_remove_nonexistent_domain_does_not_raise(db_path: Path) -> None:
    remove_domain("nothere.com", db_path)  # must not raise


# ── export_to_file ────────────────────────────────────────────────────────────

def test_export_writes_enabled_domains(db_path: Path, tmp_path: Path) -> None:
    # instagram.com and tiktok.com are pre-seeded and their platforms are enabled
    out = tmp_path / "blocklist.txt"
    export_to_file(db_path, out)
    lines = out.read_text().splitlines()
    assert "instagram.com" in lines
    assert "tiktok.com" in lines


def test_export_respects_platform_disabled(db_path: Path, tmp_path: Path) -> None:
    # Disable the instagram platform; its domains should not be exported
    toggle_platform("instagram", db_path)
    out = tmp_path / "blocklist.txt"
    export_to_file(db_path, out)
    lines = out.read_text().splitlines()
    assert "instagram.com" not in lines
    assert "cdninstagram.com" not in lines


def test_export_empty_blocklist_writes_empty_file(tmp_path: Path) -> None:
    db = _bare_db(tmp_path)
    out = tmp_path / "blocklist.txt"
    export_to_file(db, out)
    assert out.read_text() == ""


def test_export_includes_legacy_domains_without_platform(tmp_path: Path) -> None:
    db = _bare_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO blocked_domains (domain, enabled) VALUES ('legacy.com', 1)")
    conn.commit()
    conn.close()
    out = tmp_path / "blocklist.txt"
    export_to_file(db, out)
    assert "legacy.com" in out.read_text().splitlines()


# ── add_domain preset field ───────────────────────────────────────────────────

def test_add_domain_stores_preset(db_path: Path) -> None:
    # Use a fresh unique domain so INSERT OR IGNORE actually inserts
    add_domain("new-preset-test.com", db_path, preset="social_only")
    domains = list_domains(db_path)
    match = [d for d in domains if d["domain"] == "new-preset-test.com"]
    assert len(match) == 1
    assert match[0]["preset"] == "social_only"


# ── import_preset ─────────────────────────────────────────────────────────────

def test_import_social_only_preset(db_path: Path) -> None:
    os.environ["STILLHEM_PRESET_DIR"] = PRESET_DIR
    count = import_preset("social_only", db_path)
    assert count > 0
    domains = domain_set(db_path)
    assert "instagram.com" in domains
    assert "facebook.com" in domains
    assert "tiktok.com" in domains


def test_import_preset_skips_comment_lines(db_path: Path) -> None:
    os.environ["STILLHEM_PRESET_DIR"] = PRESET_DIR
    import_preset("social_only", db_path)
    for d in list_domains(db_path):
        assert not d["domain"].startswith("#")


def test_hard_mode_contains_more_domains_than_social_only(db_path: Path, tmp_path: Path) -> None:
    os.environ["STILLHEM_PRESET_DIR"] = PRESET_DIR
    db_social = tmp_path / "social.db"
    db_hard = tmp_path / "hard.db"
    from stillhem.db import init_db
    init_db(db_social)
    init_db(db_hard)
    social_count = import_preset("social_only", db_social)
    hard_count = import_preset("hard_mode", db_hard)
    assert hard_count > social_count


# ── platforms ─────────────────────────────────────────────────────────────────

def test_init_db_seeds_platforms(db_path: Path) -> None:
    platforms = list_platforms(db_path)
    names = {p["name"] for p in platforms}
    assert "instagram" in names
    assert "youtube" in names
    assert "twitch" in names


def test_platforms_have_correct_categories(db_path: Path) -> None:
    platforms = list_platforms(db_path)
    by_name = {p["name"]: p for p in platforms}
    assert by_name["instagram"]["category"] == "social"
    assert by_name["youtube"]["category"] == "video"


def test_toggle_platform_flips_enabled(db_path: Path) -> None:
    # instagram starts enabled
    new_state = toggle_platform("instagram", db_path)
    assert new_state is False
    # toggle back
    new_state = toggle_platform("instagram", db_path)
    assert new_state is True


def test_toggle_unknown_platform_raises(db_path: Path) -> None:
    import pytest
    with pytest.raises(KeyError):
        toggle_platform("does-not-exist", db_path)


# ── add_custom_domain ─────────────────────────────────────────────────────────

def test_add_custom_domain_creates_platform_and_domain(db_path: Path) -> None:
    add_custom_domain("aftonbladet.se", db_path)
    domains = domain_set(db_path)
    assert "aftonbladet.se" in domains
    platforms = {p["name"]: p for p in list_platforms(db_path)}
    assert "aftonbladet.se" in platforms
    assert platforms["aftonbladet.se"]["category"] == "custom"


def test_add_custom_domain_is_idempotent(db_path: Path) -> None:
    add_custom_domain("aftonbladet.se", db_path)
    add_custom_domain("aftonbladet.se", db_path)
    custom = [p for p in list_platforms(db_path) if p["name"] == "aftonbladet.se"]
    assert len(custom) == 1


# ── get_categories ────────────────────────────────────────────────────────────

def test_get_categories_returns_all_three_groups(db_path: Path) -> None:
    cats = get_categories(db_path)
    names = {c["name"] for c in cats}
    assert "social" in names
    assert "video" in names
    assert "custom" in names


def test_get_categories_counts_blocked_correctly(db_path: Path) -> None:
    # Disable instagram; social blocked count should decrease by 1
    cats_before = {c["name"]: c for c in get_categories(db_path)}
    social_blocked_before = cats_before["social"]["blocked_count"]
    toggle_platform("instagram", db_path)
    cats_after = {c["name"]: c for c in get_categories(db_path)}
    assert cats_after["social"]["blocked_count"] == social_blocked_before - 1


# ── remove custom domain cleans up platform ───────────────────────────────────

def test_remove_custom_domain_cleans_platform(db_path: Path) -> None:
    add_custom_domain("aftonbladet.se", db_path)
    assert "aftonbladet.se" in {p["name"] for p in list_platforms(db_path)}
    remove_domain("aftonbladet.se", db_path)
    assert "aftonbladet.se" not in {p["name"] for p in list_platforms(db_path)}


def test_remove_seeded_domain_does_not_remove_platform(db_path: Path) -> None:
    # Removing one domain from a multi-domain platform keeps the platform
    remove_domain("cdninstagram.com", db_path)
    platform_names = {p["name"] for p in list_platforms(db_path)}
    assert "instagram" in platform_names
