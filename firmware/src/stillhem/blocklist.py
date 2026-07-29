import os
import sqlite3
from datetime import datetime
from pathlib import Path

from .db import get_db
from .schedule import window_active

ACTIVE_BLOCKLIST_PATH = Path(
    os.environ.get("STILLHEM_BLOCKLIST_PATH", "/var/lib/stillhem/active_blocklist.txt")
)
PRESET_DIR = Path(
    os.environ.get("STILLHEM_PRESET_DIR", str(Path(__file__).parent.parent.parent / "blocklists"))
)


def add_domain(domain: str, db_path: Path, preset: str | None = None,
               platform: str | None = None) -> None:
    domain = domain.strip().lower().rstrip(".")
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blocked_domains (domain, preset, platform) VALUES (?, ?, ?)",
            (domain, preset, platform),
        )


def remove_domain(domain: str, db_path: Path) -> None:
    domain = domain.strip().lower().rstrip(".")
    with get_db(db_path) as conn:
        # Find associated platform before deleting
        row = conn.execute(
            "SELECT platform FROM blocked_domains WHERE domain = ?", (domain,)
        ).fetchone()
        conn.execute("DELETE FROM blocked_domains WHERE domain = ?", (domain,))
        # If this was a custom-category platform with no other domains, clean it up
        if row and row["platform"]:
            plat = row["platform"]
            plat_row = conn.execute(
                "SELECT category FROM platforms WHERE name = ?", (plat,)
            ).fetchone()
            if plat_row and plat_row["category"] == "custom":
                remaining = conn.execute(
                    "SELECT COUNT(*) as cnt FROM blocked_domains WHERE platform = ?", (plat,)
                ).fetchone()["cnt"]
                if remaining == 0:
                    conn.execute("DELETE FROM platforms WHERE name = ?", (plat,))


def list_domains(db_path: Path) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT domain, preset, enabled, added_at, platform"
            " FROM blocked_domains ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_platforms(db_path: Path) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT name, display_name, primary_domain, category, enabled"
            " FROM platforms ORDER BY category, display_name"
        ).fetchall()
    return [dict(r) for r in rows]


def toggle_platform(platform_name: str, db_path: Path) -> bool:
    """Flip a platform's enabled flag. Returns the new enabled state."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT enabled FROM platforms WHERE name = ?", (platform_name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Platform not found: {platform_name!r}")
        new_state = 0 if row["enabled"] else 1
        conn.execute(
            "UPDATE platforms SET enabled = ? WHERE name = ?", (new_state, platform_name)
        )
    return bool(new_state)


def add_custom_domain(domain: str, db_path: Path) -> None:
    """Add a domain as a custom-category platform entry."""
    domain = domain.strip().lower().rstrip(".")
    slug = domain  # use the full domain as slug
    display_name = domain.split(".")[0].capitalize()
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO platforms"
            " (name, display_name, primary_domain, category)"
            " VALUES (?, ?, ?, 'custom')",
            (slug, display_name, domain),
        )
        conn.execute(
            "INSERT OR IGNORE INTO blocked_domains (domain, platform) VALUES (?, ?)",
            (domain, slug),
        )


def get_categories(db_path: Path) -> list[dict]:
    """Return category-grouped platform data for the dashboard template."""
    platforms = list_platforms(db_path)
    category_order = ["social", "video", "custom"]
    category_labels = {"social": "Social", "video": "Video", "custom": "Custom"}

    by_cat: dict[str, list[dict]] = {c: [] for c in category_order}
    for p in platforms:
        cat = p["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(p)

    now = datetime.now()
    schedules = load_schedules(db_path)  # one query, not one per category
    result = []
    for cat in category_order:
        plats = by_cat.get(cat, [])
        schedule = schedules.get(cat)
        active_now = window_active(schedule, now)
        if not plats and cat == "custom":
            # Always include custom card even if empty
            result.append({
                "name": cat,
                "label": category_labels[cat],
                "platforms": [],
                "blocked_count": 0,
                "total_count": 0,
                "schedule": schedule,
                "active_now": active_now,
            })
            continue
        if not plats:
            continue
        blocked = sum(1 for p in plats if p["enabled"])
        result.append({
            "name": cat,
            "label": category_labels[cat],
            "platforms": plats,
            "blocked_count": blocked,
            "total_count": len(plats),
            "schedule": schedule,
            "active_now": active_now,
        })
    return result


# ── Category allow-schedules ──────────────────────────────────────────────────
# blocklist.py is the only module that touches the category_schedules table; the
# helpers tolerate the table being absent (un-migrated Pi) by degrading to
# "no schedule".

def get_schedule(db_path: Path, category: str) -> dict | None:
    """Return the schedule row {days, start_min, end_min} for a category, or None."""
    try:
        with get_db(db_path) as conn:
            row = conn.execute(
                "SELECT days, start_min, end_min FROM category_schedules WHERE category = ?",
                (category,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None


def set_schedule(db_path: Path, category: str, days: list[int],
                 start_min: int, end_min: int) -> None:
    """Upsert a category's allow-schedule."""
    days_csv = ",".join(str(int(d)) for d in days)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO category_schedules (category, days, start_min, end_min)"
            " VALUES (?, ?, ?, ?)",
            (category, days_csv, start_min, end_min),
        )


def clear_schedule(db_path: Path, category: str) -> None:
    """Remove a category's schedule (back to always-follow-toggles behavior)."""
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM category_schedules WHERE category = ?", (category,))


def load_schedules(db_path: Path) -> dict[str, dict]:
    """Return {category: row} for all scheduled categories; {} if table missing."""
    try:
        with get_db(db_path) as conn:
            rows = conn.execute(
                "SELECT category, days, start_min, end_min FROM category_schedules"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    # Value shape matches get_schedule(): category is the map key, not repeated in
    # the row, so both consumers (export_to_file, get_categories) see one shape.
    return {
        r["category"]: {"days": r["days"], "start_min": r["start_min"], "end_min": r["end_min"]}
        for r in rows
    }


def export_to_file(db_path: Path, out_path: Path = ACTIVE_BLOCKLIST_PATH,
                   now: datetime | None = None) -> bool:
    """Write the effective blocklist. Return True iff the file content changed.

    Effective semantics: effective_blocked = platform.enabled AND NOT
    window_active(category, now). During an active allow-window the whole category
    drops out regardless of per-platform toggles; outside it, the per-platform
    toggle decides as before. `now` is a param purely so callers/tests can inject a
    fixed clock; the sole real clock read is `datetime.now()` (naive local).
    """
    now = now or datetime.now()
    active = {cat for cat, row in load_schedules(db_path).items() if window_active(row, now)}

    sql = (
        "SELECT bd.domain"
        " FROM blocked_domains bd"
        " LEFT JOIN platforms p ON bd.platform = p.name"
        " WHERE bd.enabled = 1"
        "   AND (bd.platform IS NULL OR (p.enabled = 1{cat_clause}))"
        # Deterministic order: change-detection compares the exact output text, so
        # the same logical set must always serialize identically or the 1-minute
        # reconcile timer would reload Unbound on nothing but a row-order shuffle.
        " ORDER BY bd.domain"
    )
    params: list = []
    if active:
        placeholders = ",".join("?" for _ in active)
        cat_clause = f" AND p.category NOT IN ({placeholders})"
        params = list(active)
    else:
        cat_clause = ""

    with get_db(db_path) as conn:
        rows = conn.execute(sql.format(cat_clause=cat_clause), params).fetchall()
    domains = [r["domain"] for r in rows]
    new_text = "\n".join(domains) + "\n" if domains else ""

    old_text = out_path.read_text() if out_path.exists() else None
    if new_text == old_text:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_text)
    return True


def import_preset(preset_name: str, db_path: Path) -> int:
    preset_path = PRESET_DIR / f"{preset_name}.txt"
    lines = preset_path.read_text().splitlines()
    domains = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    for domain in domains:
        add_domain(domain, db_path, preset=preset_name)
    return len(domains)
