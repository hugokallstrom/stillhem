import json
import logging
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# start_ap() drives several nmcli calls; a single transient failure (device
# busy, NM not settled at boot) would otherwise leave the unit with no AP and
# no way in. Retry a few times with a short backoff before giving up loudly.
AP_START_ATTEMPTS = 3
AP_START_BACKOFF_SEC = 2.0

AP_CON_NAME = "Stillhem Setup"
AP_SSID = "Stillhem Setup"
WIFI_IFACE = "wlan0"

STATE_DIR = Path("/var/lib/stillhem")
MODE_PATH = STATE_DIR / "mode"
SCAN_CACHE_PATH = STATE_DIR / "wifi_scan.json"
SETUP_COMPLETE_PATH = STATE_DIR / "setup_complete"
WIFI_PRESENT_PATH = STATE_DIR / "wifi_present"

_VALID_MODES = ("setup", "normal")


def _run(args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["nmcli", *args], capture_output=capture, text=True, check=True)


def home_wifi_configured() -> bool:
    """True if a saved NetworkManager wifi client profile (not our AP) exists."""
    out = _run(["-t", "-f", "NAME,TYPE", "connection", "show"], capture=True).stdout
    for line in out.splitlines():
        # nmcli -t escapes ':' inside a field as '\:'; TYPE never contains ':',
        # so the last ':' is always the field separator.
        name, _, ctype = line.rpartition(":")
        if ctype == "802-11-wireless" and name.replace("\\:", ":") != AP_CON_NAME:
            return True
    return False


def setup_complete() -> bool:
    return SETUP_COMPLETE_PATH.exists()


def mark_setup_complete() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_COMPLETE_PATH.write_text("1")


def has_wifi_device() -> bool:
    out = _run(["-t", "-f", "DEVICE,TYPE", "device", "status"], capture=True).stdout
    return any(
        len(line.split(":")) >= 2 and line.split(":")[1] == "wifi"
        for line in out.splitlines()
    )


def should_enter_setup() -> bool:
    """Enter setup only with no home wifi profile AND no other active link.

    Ethernet suppression is skipped when no wifi device exists — on Ethernet-only
    hardware (e.g. Pi B+) the wizard is the only way to configure the device.
    """
    if setup_complete():
        return False
    if home_wifi_configured():
        return False
    if not has_wifi_device():
        return True
    out = _run(["-t", "-f", "DEVICE,TYPE,STATE", "device", "status"], capture=True).stdout
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] != "wifi" and parts[2] == "connected":
            return False
    return True


def scan_networks() -> list[dict]:
    out = _run(
        ["-t", "-f", "SIGNAL,SECURITY,SSID", "device", "wifi", "list", "--rescan", "yes"],
        capture=True,
    ).stdout
    best: dict[str, dict] = {}
    for line in out.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        signal_s, security, ssid = parts
        ssid = ssid.replace("\\:", ":").strip()
        if not ssid:
            continue
        try:
            signal = int(signal_s)
        except ValueError:
            signal = 0
        prev = best.get(ssid)
        if prev is None or signal > prev["signal"]:
            best[ssid] = {"ssid": ssid, "signal": signal, "secured": security not in ("", "--")}
    return sorted(best.values(), key=lambda n: n["signal"], reverse=True)


def cache_scan(networks: list[dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SCAN_CACHE_PATH.write_text(json.dumps(networks))


def read_cached_scan() -> list[dict]:
    if not SCAN_CACHE_PATH.exists():
        return []
    try:
        return json.loads(SCAN_CACHE_PATH.read_text())
    except json.JSONDecodeError:
        return []


def start_ap() -> None:
    _run(["connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
          "con-name", AP_CON_NAME, "autoconnect", "no", "ssid", AP_SSID])
    _run(["connection", "modify", AP_CON_NAME,
          "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg", "ipv4.method", "shared"])
    _run(["connection", "up", AP_CON_NAME])


def start_ap_with_retry() -> None:
    """Bring up the setup AP, retrying transient failures with a short backoff.

    Every failed attempt tears down any half-created profile before retrying (and
    before giving up), so neither a retry nor the next boot trips over a duplicate
    con-name. After AP_START_ATTEMPTS failures the last error is logged loudly and
    re-raised — the unit surfaces the failure rather than sitting silently with no AP.
    """
    for attempt in range(1, AP_START_ATTEMPTS + 1):
        try:
            start_ap()
            return
        except Exception:
            # A failed attempt may leave a half-created profile behind; clear it
            # so a retry (or the next boot) doesn't trip over a duplicate con-name.
            try:
                stop_ap()
            except Exception:
                pass
            if attempt >= AP_START_ATTEMPTS:
                logger.error(
                    "start_ap failed after %d attempts; device has no setup AP",
                    AP_START_ATTEMPTS,
                    exc_info=True,
                )
                raise
            logger.warning(
                "start_ap attempt %d/%d failed; retrying in %.1fs",
                attempt,
                AP_START_ATTEMPTS,
                AP_START_BACKOFF_SEC,
                exc_info=True,
            )
            time.sleep(AP_START_BACKOFF_SEC)


def stop_ap() -> None:
    _run(["connection", "down", AP_CON_NAME])
    _run(["connection", "delete", AP_CON_NAME])


def save_home_wifi(ssid: str, psk: str) -> None:
    _run(["connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
          "con-name", ssid, "ssid", ssid, "autoconnect", "yes"])
    if psk:
        _run(["connection", "modify", ssid, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", psk])


def write_wifi_present(present: bool) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    WIFI_PRESENT_PATH.write_text("1" if present else "0")


def wifi_present() -> bool:
    """Whether this board has Wi-Fi hardware, as recorded at boot.

    The admin service reads this to decide whether the wizard should ask for a
    home network at all. Unrecorded (netmode has not run yet) means True: a box
    with Wi-Fi is the common case, and the Wi-Fi step is harmless on hardware
    that turns out to have none — it's only skipped once we know there is none.
    """
    if not WIFI_PRESENT_PATH.exists():
        return True
    return WIFI_PRESENT_PATH.read_text().strip() != "0"


def read_mode() -> str:
    if not MODE_PATH.exists():
        return "setup"
    mode = MODE_PATH.read_text().strip()
    return mode if mode in _VALID_MODES else "setup"


def write_mode(mode: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MODE_PATH.write_text(mode)


def boot() -> None:
    try:
        wifi = has_wifi_device()
    except Exception:
        wifi = True  # assume the common case; only a definite "no" changes behaviour
    write_wifi_present(wifi)

    if not should_enter_setup():
        write_mode("normal")
        return

    # Ethernet-only hardware (e.g. Pi B+): there is no radio to scan with and no
    # AP to raise, so setup runs over the wired link — the buyer reaches the
    # wizard at http://stillhem.local/ instead of joining a setup network.
    # Attempting the AP here would fail the unit and leave mode unwritten.
    if not wifi:
        write_mode("setup")
        return

    try:
        networks = scan_networks()
    except Exception:
        networks = read_cached_scan()  # possibly empty; manual SSID entry covers it
    cache_scan(networks)
    # Mode is written before the AP goes up so a failed AP still leaves correct
    # state on disk (and the unit still reports the failure).
    write_mode("setup")
    start_ap_with_retry()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "boot":
        boot()
    else:
        print("usage: python -m stillhem.netmode boot", file=sys.stderr)
        sys.exit(2)
