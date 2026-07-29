"""Entrypoint for the 1-minute reconcile timer (`python -m stillhem.reconcile`).

Recomputes the effective blocklist from the current schedules and reloads Unbound
when the content changed or a prior reload is still pending (skipped/failed).
`reload_dns` no-ops when nothing changed and nothing is pending, so per-minute
runs are cheap.
"""
import os
import subprocess
from pathlib import Path

from .dns_control import reload_dns


def main() -> None:
    db_path = Path(os.environ["STILLHEM_DB_PATH"])
    blocklist = Path(os.environ["STILLHEM_BLOCKLIST_PATH"])
    unbound_conf = Path(os.environ["STILLHEM_UNBOUND_CONF"])
    template_dir = Path(os.environ["STILLHEM_DNS_TEMPLATE_DIR"])
    # Exit 0 even if the reload fails: the timer runs every minute, so a transient
    # error (e.g. unbound-control socket not ready) should just retry next tick
    # rather than leaving a failed systemd unit and a log line every 60s.
    try:
        changed = reload_dns(db_path, blocklist, unbound_conf, template_dir)  # now=None
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"reconciled: reload failed, will retry next tick: {exc}")
        return
    print("reconciled: reloaded" if changed else "reconciled: no change")


if __name__ == "__main__":
    main()
