import os
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .blocklist import export_to_file

UNBOUND_CONF_PATH = Path(
    os.environ.get("ALGORO_UNBOUND_CONF", "/etc/unbound/unbound.conf.d/algoro.conf")
)
DEFAULT_TEMPLATE_DIR = Path(
    os.environ.get("ALGORO_DNS_TEMPLATE_DIR", str(Path(__file__).parent.parent.parent / "dns"))
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


def reload_dns(
    db_path: Path,
    blocklist_path: Path,
    unbound_conf_path: Path = UNBOUND_CONF_PATH,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> None:
    export_to_file(db_path, blocklist_path)
    generate_unbound_conf(blocklist_path, unbound_conf_path, template_dir)
    if is_unbound_running():
        reload_unbound()
