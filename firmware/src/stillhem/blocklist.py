import os
from pathlib import Path

from .db import get_db

ACTIVE_BLOCKLIST_PATH = Path(
    os.environ.get("ALGORO_BLOCKLIST_PATH", "/var/lib/algoro/active_blocklist.txt")
)
PRESET_DIR = Path(
    os.environ.get("ALGORO_PRESET_DIR", str(Path(__file__).parent.parent.parent / "blocklists"))
)


def add_domain(domain: str, db_path: Path, preset: str | None = None) -> None:
    domain = domain.strip().lower().rstrip(".")
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blocked_domains (domain, preset) VALUES (?, ?)",
            (domain, preset),
        )


def remove_domain(domain: str, db_path: Path) -> None:
    domain = domain.strip().lower().rstrip(".")
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM blocked_domains WHERE domain = ?", (domain,))


def list_domains(db_path: Path) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT domain, preset, enabled, added_at FROM blocked_domains ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def export_to_file(db_path: Path, out_path: Path = ACTIVE_BLOCKLIST_PATH) -> None:
    domains = [r["domain"] for r in list_domains(db_path) if r["enabled"]]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(domains) + "\n" if domains else "")


def import_preset(preset_name: str, db_path: Path) -> int:
    preset_path = PRESET_DIR / f"{preset_name}.txt"
    lines = preset_path.read_text().splitlines()
    domains = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    for domain in domains:
        add_domain(domain, db_path, preset=preset_name)
    return len(domains)
