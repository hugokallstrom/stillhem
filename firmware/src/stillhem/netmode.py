import json
import subprocess
import sys
from pathlib import Path

AP_CON_NAME = "Stillhem Setup"
AP_SSID = "Stillhem Setup"
WIFI_IFACE = "wlan0"

STATE_DIR = Path("/var/lib/stillhem")
MODE_PATH = STATE_DIR / "mode"
SCAN_CACHE_PATH = STATE_DIR / "wifi_scan.json"
SETUP_COMPLETE_PATH = STATE_DIR / "setup_complete"

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


def should_enter_setup() -> bool:
    """Enter setup only with no home wifi profile AND no other active link."""
    if setup_complete():
        return False
    if home_wifi_configured():
        return False
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


def stop_ap() -> None:
    _run(["connection", "down", AP_CON_NAME])
    _run(["connection", "delete", AP_CON_NAME])


def save_home_wifi(ssid: str, psk: str) -> None:
    _run(["connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
          "con-name", ssid, "ssid", ssid, "autoconnect", "yes"])
    if psk:
        _run(["connection", "modify", ssid, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", psk])


def read_mode() -> str:
    if not MODE_PATH.exists():
        return "setup"
    mode = MODE_PATH.read_text().strip()
    return mode if mode in _VALID_MODES else "setup"


def write_mode(mode: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MODE_PATH.write_text(mode)


def boot() -> None:
    if should_enter_setup():
        try:
            networks = scan_networks()
        except Exception:
            networks = read_cached_scan()  # possibly empty; manual SSID entry covers it
        cache_scan(networks)
        start_ap()
        write_mode("setup")
    else:
        write_mode("normal")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "boot":
        boot()
    else:
        print("usage: python -m stillhem.netmode boot", file=sys.stderr)
        sys.exit(2)
