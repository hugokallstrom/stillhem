"""The Pi's wall clock and its NTP-sync state.

Schedules are evaluated against the Pi's local time, so a wrong clock silently
blocks/allows at the wrong hours. This surfaces the real time + timezone and
warns when the clock is not disciplined by NTP. On a non-systemd host (e.g. a
Mac used for local development) `timedatectl` is absent; we still report a real
local time and leave the NTP state unknown rather than failing.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClockStatus:
    now: str  # formatted local time, e.g. "2026-07-29 14:03"
    timezone: str | None  # IANA tz name, or None when unknown
    ntp_synced: bool | None  # True/False, or None when it can't be determined


def parse_timedatectl(out: str) -> tuple[str | None, bool | None]:
    """Parse `timedatectl show -p Timezone -p NTPSynchronized` key=value output."""
    tz: str | None = None
    synced: bool | None = None
    for line in out.splitlines():
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key == "Timezone" and value:
            tz = value
        elif key == "NTPSynchronized":
            synced = value == "yes"
    return tz, synced


def _run_timedatectl() -> str | None:
    """Return timedatectl show output, or None when it can't be run."""
    try:
        return subprocess.run(
            ["timedatectl", "show", "-p", "Timezone", "-p", "NTPSynchronized"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def clock_status(now: datetime | None = None) -> ClockStatus:
    when = now or datetime.now()
    out = _run_timedatectl()
    tz, synced = parse_timedatectl(out) if out is not None else (None, None)
    return ClockStatus(now=when.strftime("%Y-%m-%d %H:%M"), timezone=tz, ntp_synced=synced)
