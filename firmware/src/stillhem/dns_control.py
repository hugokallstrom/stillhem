import os
import subprocess
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .blocklist import export_to_file

UNBOUND_CONF_PATH = Path(
    os.environ.get("STILLHEM_UNBOUND_CONF", "/etc/unbound/unbound.conf.d/stillhem.conf")
)
DEFAULT_TEMPLATE_DIR = Path(
    os.environ.get("STILLHEM_DNS_TEMPLATE_DIR", str(Path(__file__).parent.parent.parent / "dns"))
)


def generate_unbound_conf(
    blocklist_path: Path,
    out_path: Path = UNBOUND_CONF_PATH,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> None:
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("unbound.conf.j2")
    text = blocklist_path.read_text() if blocklist_path.exists() else ""
    domains = [line.strip() for line in text.splitlines() if line.strip()]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.render(domains=domains))


def reload_unbound() -> None:
    subprocess.run(["unbound-control", "reload"], check=True)


def is_unbound_running() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "unbound"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return result.stdout.strip() == "active"


def total_queries() -> int:
    """Total queries Unbound has answered (via `unbound-control stats_noreset`).
    Returns 0 if unbound-control is unavailable or the stat can't be parsed."""
    try:
        out = subprocess.run(
            ["unbound-control", "stats_noreset"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0
    for line in out.splitlines():
        if line.startswith("total.num.queries="):
            try:
                return int(line.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def reload_dns(
    db_path: Path,
    blocklist_path: Path,
    unbound_conf_path: Path = UNBOUND_CONF_PATH,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
    now: datetime | None = None,
) -> bool:
    """Recompute the effective blocklist and reload Unbound only if it changed.

    The 1-minute reconcile timer calls this every minute, so it must not bounce
    Unbound when nothing changed. Returns True iff a reload happened. `now` is
    forwarded to `export_to_file` so callers/tests can inject a fixed clock.
    """
    changed = export_to_file(db_path, blocklist_path, now=now)
    if not changed:
        return False
    generate_unbound_conf(blocklist_path, unbound_conf_path, template_dir)
    if is_unbound_running():
        reload_unbound()
    return True
