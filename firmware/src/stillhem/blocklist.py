import os
from pathlib import Path

from .db import get_db

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

    result = []
    for cat in category_order:
        plats = by_cat.get(cat, [])
        if not plats and cat == "custom":
            # Always include custom card even if empty
            result.append({
                "name": cat,
                "label": category_labels[cat],
                "platforms": [],
                "blocked_count": 0,
                "total_count": 0,
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
        })
    return result


def export_to_file(db_path: Path, out_path: Path = ACTIVE_BLOCKLIST_PATH) -> None:
    """Export all enabled domains respecting platform enabled state."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT bd.domain
            FROM blocked_domains bd
            LEFT JOIN platforms p ON bd.platform = p.name
            WHERE bd.enabled = 1
              AND (bd.platform IS NULL OR p.enabled = 1)
            """
        ).fetchall()
    domains = [r["domain"] for r in rows]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(domains) + "\n" if domains else "")


def import_preset(preset_name: str, db_path: Path) -> int:
    preset_path = PRESET_DIR / f"{preset_name}.txt"
    lines = preset_path.read_text().splitlines()
    domains = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    for domain in domains:
        add_domain(domain, db_path, preset=preset_name)
    return len(domains)
