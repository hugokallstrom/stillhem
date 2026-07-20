# First-boot captive-portal setup wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On first boot with no network configured, the device raises a `Stillhem Setup` Wi-Fi AP whose captive portal auto-opens a 3-step wizard (home Wi-Fi → blocklist preset → admin password); on completion it saves config, reboots, and joins the home network.

**Architecture:** Three layers. (1) `stillhem.netmode` — an `nmcli` wrapper + boot-time mode selector, tested with mocked `subprocess` exactly like the existing `stillhem.dns_control`. (2) The existing FastAPI app gains a two-mode switch (`setup_mode`) and a launcher. (3) `wizard_routes` — the captive-portal responders + 3 wizard steps. A final task wires the systemd units, the dnsmasq snippet, and the image install script, plus on-hardware acceptance.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, NetworkManager/`nmcli`, systemd, pytest. No new pip dependencies (`network-manager` is the bookworm default, already in the image).

## Global Constraints

- Network stack is **NetworkManager/`nmcli`** (bookworm default) — not hostapd/dnsmasq.
- AP: SSID `Stillhem Setup`, open (no password), `ipv4.method shared`, interface `wlan0`, NM connection name `Stillhem Setup`.
- The device enters setup mode **only** when there is no saved Wi-Fi client profile AND no other active connection (a wired dev machine must NOT be hijacked into AP mode). Once configured it never auto-falls-back to AP.
- Mode flag file: `/var/lib/stillhem/mode` (values `setup` / `normal`; **default `setup`** when missing/invalid). Scan cache: `/var/lib/stillhem/wifi_scan.json`.
- Captive DNS: `/etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf` = `address=/#/10.42.0.1` (NM shared subnet gateway).
- The appliance serves the admin UI / wizard on **port 80** (image has no nginx). The `stillhem-admin.service` ExecStart becomes `python -m stillhem.launch`.
- Blocklist presets are the existing three: `social_only`, `social_news`, `hard_mode`.
- Every code task must leave `pytest -m "not integration"` passing when run from `firmware/` (use `firmware/.venv-sdd/bin/pytest` if `pytest` isn't on PATH; never commit `.venv-sdd/`).

---

### Task 1: `stillhem.netmode` — nmcli wrapper + boot mode selector

**Files:**
- Create: `firmware/src/stillhem/netmode.py`
- Create: `firmware/tests/test_netmode.py`

**Interfaces:**
- Produces:
  - `home_wifi_configured() -> bool`
  - `should_enter_setup() -> bool`
  - `scan_networks() -> list[dict]` (each `{"ssid": str, "signal": int, "secured": bool}`)
  - `cache_scan(networks: list[dict]) -> None`, `read_cached_scan() -> list[dict]`
  - `start_ap() -> None`, `stop_ap() -> None`
  - `save_home_wifi(ssid: str, psk: str) -> None`
  - `read_mode() -> str`, `write_mode(mode: str) -> None`
  - `boot() -> None` (the oneshot entrypoint; also runnable via `python -m stillhem.netmode boot`)
  - Constants: `AP_CON_NAME = "Stillhem Setup"`, `WIFI_IFACE = "wlan0"`, `MODE_PATH`, `SCAN_CACHE_PATH`.

- [ ] **Step 1: Write the failing tests** `firmware/tests/test_netmode.py`

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import stillhem.netmode as netmode


def _completed(stdout=""):
    return MagicMock(stdout=stdout, returncode=0)


def test_home_wifi_configured_true_for_non_ap_wifi_profile():
    out = "Stillhem Setup:802-11-wireless\nHomeNet:802-11-wireless\n"
    with patch("subprocess.run", return_value=_completed(out)) as run:
        assert netmode.home_wifi_configured() is True
    args = run.call_args[0][0]
    assert args[:2] == ["nmcli", "-t"]


def test_home_wifi_configured_false_when_only_ap_profile():
    out = "Stillhem Setup:802-11-wireless\nWired connection 1:802-3-ethernet\n"
    with patch("subprocess.run", return_value=_completed(out)):
        assert netmode.home_wifi_configured() is False


def test_should_enter_setup_false_when_wired_connected():
    def fake_run(args, **kw):
        if "connection" in args:
            return _completed("Stillhem Setup:802-11-wireless\n")  # no home wifi
        return _completed("eth0:ethernet:connected\nwlan0:wifi:disconnected\n")
    with patch("subprocess.run", side_effect=fake_run):
        assert netmode.should_enter_setup() is False


def test_should_enter_setup_true_when_nothing_connected():
    def fake_run(args, **kw):
        if "connection" in args:
            return _completed("Stillhem Setup:802-11-wireless\n")
        return _completed("wlan0:wifi:disconnected\neth0:ethernet:unavailable\n")
    with patch("subprocess.run", side_effect=fake_run):
        assert netmode.should_enter_setup() is True


def test_scan_networks_parses_dedupes_and_sorts():
    out = "\n".join([
        "42:WPA2:HomeNet",
        "88:WPA2:HomeNet",   # duplicate, stronger signal wins
        "17:--:OpenCafe",
        "0::",               # empty ssid dropped
    ]) + "\n"
    with patch("subprocess.run", return_value=_completed(out)):
        nets = netmode.scan_networks()
    assert nets == [
        {"ssid": "HomeNet", "signal": 88, "secured": True},
        {"ssid": "OpenCafe", "signal": 17, "secured": False},
    ]


def test_start_ap_issues_expected_nmcli_calls():
    with patch("subprocess.run", return_value=_completed()) as run:
        netmode.start_ap()
    calls = [c.args[0] for c in run.call_args_list]
    assert calls[0][:6] == ["nmcli", "connection", "add", "type", "wifi", "ifname"]
    assert "ap" in calls[1] and "shared" in calls[1]
    assert calls[2] == ["nmcli", "connection", "up", "Stillhem Setup"]


def test_save_home_wifi_sets_psk_when_present():
    with patch("subprocess.run", return_value=_completed()) as run:
        netmode.save_home_wifi("HomeNet", "s3cret")
    calls = [c.args[0] for c in run.call_args_list]
    assert calls[0][:3] == ["nmcli", "connection", "add"]
    assert "wifi-sec.psk" in calls[1] and "s3cret" in calls[1]


def test_save_home_wifi_open_network_skips_psk():
    with patch("subprocess.run", return_value=_completed()) as run:
        netmode.save_home_wifi("OpenCafe", "")
    calls = [c.args[0] for c in run.call_args_list]
    assert len(calls) == 1  # only the add, no wifi-sec modify


def test_read_mode_defaults_to_setup_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    assert netmode.read_mode() == "setup"


def test_write_then_read_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    netmode.write_mode("normal")
    assert netmode.read_mode() == "normal"


def test_cache_and_read_scan_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "SCAN_CACHE_PATH", tmp_path / "wifi_scan.json")
    nets = [{"ssid": "HomeNet", "signal": 88, "secured": True}]
    netmode.cache_scan(nets)
    assert netmode.read_cached_scan() == nets


def test_boot_normal_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    with patch.object(netmode, "should_enter_setup", return_value=False):
        netmode.boot()
    assert netmode.read_mode() == "normal"


def test_boot_setup_brings_up_ap_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(netmode, "STATE_DIR", tmp_path)
    monkeypatch.setattr(netmode, "MODE_PATH", tmp_path / "mode")
    monkeypatch.setattr(netmode, "SCAN_CACHE_PATH", tmp_path / "wifi_scan.json")
    with patch.object(netmode, "should_enter_setup", return_value=True), \
         patch.object(netmode, "scan_networks", return_value=[{"ssid": "X", "signal": 1, "secured": False}]), \
         patch.object(netmode, "start_ap") as start:
        netmode.boot()
    start.assert_called_once()
    assert netmode.read_mode() == "setup"
    assert netmode.read_cached_scan() == [{"ssid": "X", "signal": 1, "secured": False}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_netmode.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stillhem.netmode'`.

- [ ] **Step 3: Write `firmware/src/stillhem/netmode.py`**

```python
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


def should_enter_setup() -> bool:
    """Enter setup only with no home wifi profile AND no other active link."""
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
        cache_scan(scan_networks())
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_netmode.py -q`
Expected: PASS (all ~13 tests).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `cd firmware && .venv-sdd/bin/pytest -m "not integration" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add firmware/src/stillhem/netmode.py firmware/tests/test_netmode.py
git commit -m "feat: netmode module (nmcli AP/mode control) with boot selector

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 2: App two-mode plumbing + config helpers + launcher

**Files:**
- Modify: `firmware/src/stillhem/db.py` (add `get_config` / `set_config`)
- Modify: `firmware/src/stillhem/admin/app.py` (add `setup_mode` param + state)
- Create: `firmware/src/stillhem/launch.py`
- Modify: `firmware/tests/test_db.py` (config helper tests)
- Create: `firmware/tests/test_launch.py`

**Interfaces:**
- Consumes: `stillhem.netmode.read_mode` (Task 1).
- Produces:
  - `stillhem.db.get_config(db_path, key) -> str | None`, `set_config(db_path, key, value) -> None`
  - `create_app(..., setup_mode: bool = False)` sets `app.state.setup_mode`
  - `stillhem.launch.build() -> FastAPI` (reads mode file → sets `setup_mode`), `stillhem.launch.main()` (runs uvicorn on port 80)

- [ ] **Step 1: Write failing tests — append to `firmware/tests/test_db.py`**

```python
from stillhem.db import get_config, set_config


def test_set_and_get_config(db_path: Path) -> None:
    assert get_config(db_path, "k") is None
    set_config(db_path, "k", "v")
    assert get_config(db_path, "k") == "v"


def test_set_config_overwrites(db_path: Path) -> None:
    set_config(db_path, "k", "v1")
    set_config(db_path, "k", "v2")
    assert get_config(db_path, "k") == "v2"
```

- [ ] **Step 2: Write failing test `firmware/tests/test_launch.py`**

```python
from unittest.mock import patch

from stillhem import launch


def test_build_setup_mode(monkeypatch):
    with patch("stillhem.launch.netmode.read_mode", return_value="setup"):
        app = launch.build()
    assert app.state.setup_mode is True


def test_build_normal_mode(monkeypatch):
    with patch("stillhem.launch.netmode.read_mode", return_value="normal"):
        app = launch.build()
    assert app.state.setup_mode is False
```

- [ ] **Step 3: Run to verify failure**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_db.py::test_set_and_get_config tests/test_launch.py -q`
Expected: FAIL (`ImportError: cannot import name 'get_config'`, `No module named 'stillhem.launch'`).

- [ ] **Step 4: Add config helpers to `firmware/src/stillhem/db.py`** (append after `init_db`)

```python
def get_config(path: Path, key: str) -> str | None:
    with get_db(path) as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_config(path: Path, key: str, value: str) -> None:
    with get_db(path) as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
```

- [ ] **Step 5: Add `setup_mode` to `create_app` in `firmware/src/stillhem/admin/app.py`**

Change the `create_app` signature and body:
```python
def create_app(
    db_path: Path,
    blocklist_path: Path = ACTIVE_BLOCKLIST_PATH,
    unbound_conf_path: Path = UNBOUND_CONF_PATH,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
    setup_mode: bool = False,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None)
    app.state.db_path = db_path
    app.state.blocklist_path = blocklist_path
    app.state.unbound_conf_path = unbound_conf_path
    app.state.template_dir = template_dir
    app.state.setup_mode = setup_mode
```
Leave the rest of `create_app` (mounts, routers, module-level `app`) unchanged for now — the wizard router and gate are added in Task 3.

- [ ] **Step 6: Write `firmware/src/stillhem/launch.py`**

```python
import os
from pathlib import Path

from stillhem import netmode
from stillhem.admin.app import create_app


def build():
    return create_app(
        db_path=Path(os.environ.get("STILLHEM_DB_PATH", "/var/lib/stillhem/stillhem.db")),
        setup_mode=netmode.read_mode() == "setup",
    )


def main() -> None:
    import uvicorn

    uvicorn.run(build(), host="0.0.0.0", port=80)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the targeted tests, then the full suite**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_db.py tests/test_launch.py -q && .venv-sdd/bin/pytest -m "not integration" -q`
Expected: both PASS.

- [ ] **Step 8: Commit**

```bash
git add firmware/src/stillhem/db.py firmware/src/stillhem/admin/app.py firmware/src/stillhem/launch.py firmware/tests/test_db.py firmware/tests/test_launch.py
git commit -m "feat: two-mode app plumbing (setup_mode, config helpers, launcher)

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 3: Wizard routes, captive-portal gate, and templates

**Files:**
- Create: `firmware/src/stillhem/admin/routes/wizard_routes.py`
- Modify: `firmware/src/stillhem/admin/app.py` (include wizard router + setup-mode gate middleware)
- Create: `firmware/templates/wizard_wifi.html`
- Create: `firmware/templates/wizard_preset.html`
- Create: `firmware/templates/wizard_password.html`
- Create: `firmware/templates/wizard_done.html`
- Create: `firmware/tests/test_wizard.py`

**Interfaces:**
- Consumes: `netmode.read_cached_scan`, `netmode.save_home_wifi` (Task 1); `get_config`/`set_config` (Task 2); existing `set_password`, `is_password_set`, `import_preset`, `reload_dns`; `app.state.setup_mode`.
- Produces: routes `/wizard/wifi`, `/wizard/preset`, `/wizard/password`, `/wizard/done`, `/wizard/finish`; a `setup_mode` gate that (a) in setup mode redirects any non-`/wizard`, non-`/static` request to `/wizard/wifi` (covering OS captive-portal probes), and (b) in normal mode redirects `/wizard/*` to `/`.

- [ ] **Step 1: Write failing tests `firmware/tests/test_wizard.py`**

```python
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from stillhem.admin.app import create_app
from stillhem.auth import is_password_set
from stillhem.blocklist import list_domains
from stillhem.db import get_config


@pytest.fixture
def setup_client(db_path: Path):
    return TestClient(create_app(db_path=db_path, setup_mode=True))


@pytest.fixture
def normal_client(db_path: Path):
    from stillhem.auth import set_password
    set_password("done", db_path)  # a configured device has a password
    return TestClient(create_app(db_path=db_path, setup_mode=False))


def test_captive_probe_redirects_to_wizard(setup_client):
    resp = setup_client.get("/generate_204", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/wifi"


def test_wifi_page_lists_cached_networks(setup_client):
    with patch("stillhem.admin.routes.wizard_routes.netmode.read_cached_scan",
               return_value=[{"ssid": "HomeNet", "signal": 80, "secured": True}]):
        resp = setup_client.get("/wizard/wifi")
    assert resp.status_code == 200
    assert "HomeNet" in resp.text


def test_wifi_submit_saves_profile_and_advances(setup_client, db_path):
    with patch("stillhem.admin.routes.wizard_routes.netmode.save_home_wifi") as save:
        resp = setup_client.post("/wizard/wifi",
                                 data={"ssid": "HomeNet", "password": "s3cret"},
                                 follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/preset"
    save.assert_called_once_with("HomeNet", "s3cret")
    assert get_config(db_path, "home_wifi_ssid") == "HomeNet"


def test_wifi_submit_prefers_manual_ssid(setup_client, db_path):
    with patch("stillhem.admin.routes.wizard_routes.netmode.save_home_wifi") as save:
        resp = setup_client.post(
            "/wizard/wifi",
            data={"ssid": "", "ssid_manual": "HiddenNet", "password": "pw"},
            follow_redirects=False)
    assert resp.status_code == 302
    save.assert_called_once_with("HiddenNet", "pw")
    assert get_config(db_path, "home_wifi_ssid") == "HiddenNet"


def test_wifi_submit_rejects_empty_ssid(setup_client):
    resp = setup_client.post("/wizard/wifi", data={"ssid": "", "ssid_manual": "  ", "password": ""},
                             follow_redirects=False)
    assert resp.status_code == 200
    assert "choose or enter" in resp.text.lower()


def test_preset_submit_imports_and_advances(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")  # wifi step already done
    with patch("stillhem.admin.routes.wizard_routes.reload_dns"):
        resp = setup_client.post("/wizard/preset", data={"preset": "social_only"},
                                 follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/password"
    assert get_config(db_path, "wizard_preset") == "social_only"
    assert any(d["domain"] == "instagram.com" for d in list_domains(db_path))


def test_preset_rejects_unknown(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    resp = setup_client.post("/wizard/preset", data={"preset": "bogus"}, follow_redirects=False)
    assert resp.status_code == 200


def test_password_submit_sets_password_and_advances(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    set_config(db_path, "wizard_preset", "social_only")
    resp = setup_client.post("/wizard/password",
                             data={"password": "hunter2", "confirm": "hunter2"},
                             follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/done"
    assert is_password_set(db_path)


def test_password_submit_rejects_mismatch(setup_client, db_path):
    from stillhem.db import set_config
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    set_config(db_path, "wizard_preset", "social_only")
    resp = setup_client.post("/wizard/password",
                             data={"password": "hunter2", "confirm": "nope"},
                             follow_redirects=False)
    assert resp.status_code == 200
    assert not is_password_set(db_path)


def test_wizard_step_guard_snaps_forward(setup_client):
    # Landing on /wizard/preset before wifi is done bounces back to wifi.
    resp = setup_client.get("/wizard/preset", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/wizard/wifi"


def test_finish_schedules_reboot(setup_client, db_path):
    from stillhem.db import set_config
    from stillhem.auth import set_password
    set_config(db_path, "home_wifi_ssid", "HomeNet")
    set_config(db_path, "wizard_preset", "social_only")
    set_password("hunter2", db_path)
    with patch("stillhem.admin.routes.wizard_routes.subprocess.Popen") as popen:
        resp = setup_client.post("/wizard/finish", follow_redirects=False)
    popen.assert_called_once()
    assert resp.status_code in (200, 302)


def test_normal_mode_wizard_redirects_home(normal_client):
    resp = normal_client.get("/wizard/wifi", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_wizard.py -q`
Expected: FAIL (`No module named 'stillhem.admin.routes.wizard_routes'`).

- [ ] **Step 3: Write `firmware/src/stillhem/admin/routes/wizard_routes.py`**

```python
import subprocess
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from stillhem import netmode
from stillhem.auth import is_password_set, set_password
from stillhem.blocklist import import_preset
from stillhem.db import get_config, set_config
from stillhem.dns_control import reload_dns

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)

PRESETS = ["social_only", "social_news", "hard_mode"]


def _current_step(db_path: Path) -> str:
    if not get_config(db_path, "home_wifi_ssid"):
        return "/wizard/wifi"
    if not get_config(db_path, "wizard_preset"):
        return "/wizard/preset"
    if not is_password_set(db_path):
        return "/wizard/password"
    return "/wizard/done"


def _guard(request: Request):
    """Snap a wizard GET to the current step; returns a redirect or None."""
    step = _current_step(request.app.state.db_path)
    if request.url.path != step:
        return RedirectResponse(url=step, status_code=302)
    return None


@router.get("/wizard/wifi", response_class=HTMLResponse)
def wifi_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    networks = netmode.read_cached_scan()
    return templates.TemplateResponse(request, "wizard_wifi.html", {"networks": networks, "error": None})


@router.post("/wizard/wifi")
def wifi_submit(
    request: Request,
    ssid: str = Form(""),
    ssid_manual: str = Form(""),
    password: str = Form(""),
):
    # A typed-in network name takes precedence over the dropdown selection.
    chosen = ssid_manual.strip() or ssid.strip()
    if not chosen:
        networks = netmode.read_cached_scan()
        return templates.TemplateResponse(
            request, "wizard_wifi.html",
            {"networks": networks, "error": "Please choose or enter a network."}, status_code=200)
    netmode.save_home_wifi(chosen, password)
    set_config(request.app.state.db_path, "home_wifi_ssid", chosen)
    return RedirectResponse(url="/wizard/preset", status_code=302)


@router.get("/wizard/preset", response_class=HTMLResponse)
def preset_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "wizard_preset.html", {"presets": PRESETS, "error": None})


@router.post("/wizard/preset")
def preset_submit(request: Request, preset: str = Form(...)):
    db_path = request.app.state.db_path
    if preset not in PRESETS:
        return templates.TemplateResponse(
            request, "wizard_preset.html",
            {"presets": PRESETS, "error": "Please choose a preset."}, status_code=200)
    import_preset(preset, db_path)
    set_config(db_path, "wizard_preset", preset)
    reload_dns(
        db_path,
        request.app.state.blocklist_path,
        request.app.state.unbound_conf_path,
        request.app.state.template_dir,
    )
    return RedirectResponse(url="/wizard/password", status_code=302)


@router.get("/wizard/password", response_class=HTMLResponse)
def password_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "wizard_password.html", {"error": None})


@router.post("/wizard/password")
def password_submit(request: Request, password: str = Form(...), confirm: str = Form(...)):
    db_path = request.app.state.db_path
    if len(password) < 5:
        return templates.TemplateResponse(
            request, "wizard_password.html",
            {"error": "Password must be at least 5 characters."}, status_code=200)
    if password != confirm:
        return templates.TemplateResponse(
            request, "wizard_password.html",
            {"error": "Passwords do not match."}, status_code=200)
    set_password(password, db_path)
    return RedirectResponse(url="/wizard/done", status_code=302)


@router.get("/wizard/done", response_class=HTMLResponse)
def done_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    ssid = get_config(request.app.state.db_path, "home_wifi_ssid") or "your home network"
    return templates.TemplateResponse(request, "wizard_done.html", {"ssid": ssid})


@router.post("/wizard/finish")
def finish(request: Request):
    ssid = get_config(request.app.state.db_path, "home_wifi_ssid") or "your home network"
    # Deferred so the HTTP response flushes before the box reboots.
    subprocess.Popen(["systemd-run", "--on-active=3", "systemctl", "reboot"])
    return templates.TemplateResponse(request, "wizard_done.html", {"ssid": ssid, "restarting": True})
```

- [ ] **Step 4: Wire the router + gate into `firmware/src/stillhem/admin/app.py`**

Add the import near the other route imports:
```python
from stillhem.admin.routes.wizard_routes import router as wizard_router
```
In `create_app`, register the router alongside the others:
```python
    app.include_router(wizard_router)
```
And add the setup-mode gate as middleware (place after the routers are included, before `return app`):
```python
    from fastapi.responses import RedirectResponse

    @app.middleware("http")
    async def _mode_gate(request, call_next):
        path = request.url.path
        if request.app.state.setup_mode:
            if not (path.startswith("/wizard") or path.startswith("/static")):
                return RedirectResponse(url="/wizard/wifi", status_code=302)
        elif path.startswith("/wizard"):
            return RedirectResponse(url="/", status_code=302)
        return await call_next(request)
```

- [ ] **Step 5: Write the four templates**

`firmware/templates/wizard_wifi.html`:
```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Connect Stillhem to Wi-Fi</h1>
  <p>Choose your home network so the device can join it.</p>
  <form method="post" action="/wizard/wifi">
    <label for="ssid">Network</label>
    <select name="ssid" id="ssid">
      {% for n in networks %}
      <option value="{{ n.ssid }}">{{ n.ssid }}{% if n.secured %} 🔒{% endif %}</option>
      {% endfor %}
      <option value="">Other (type below)</option>
    </select>
    <label for="ssid_manual">…or enter a network name</label>
    <input type="text" id="ssid_manual" name="ssid_manual" placeholder="Network name (optional)">
    <label for="password">Wi-Fi password</label>
    <input type="password" id="password" name="password" autocomplete="off">
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <button type="submit">Next</button>
  </form>
</main>
{% endblock %}
```
(Note: the dropdown submits `ssid` and the manual field submits `ssid_manual`; the handler prefers a typed-in `ssid_manual` when present, else the dropdown `ssid`. Distinct names avoid ambiguous duplicate-key form binding.)

`firmware/templates/wizard_preset.html`:
```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Choose what to block</h1>
  <form method="post" action="/wizard/preset">
    {% for p in presets %}
    <label><input type="radio" name="preset" value="{{ p }}" {% if loop.first %}checked{% endif %}> {{ p }}</label>
    {% endfor %}
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <button type="submit">Next</button>
  </form>
</main>
{% endblock %}
```

`firmware/templates/wizard_password.html`:
```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Set an admin password</h1>
  <p><strong>This is the only way to manage the device.</strong> If you forget it, the only recovery is re-flashing the SD card.</p>
  <form method="post" action="/wizard/password">
    <label for="password">Password (min 5 characters)</label>
    <input type="password" id="password" name="password" required minlength="5" autocomplete="off">
    <label for="confirm">Confirm password</label>
    <input type="password" id="confirm" name="confirm" required minlength="5" autocomplete="off">
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <button type="submit">Next</button>
  </form>
</main>
{% endblock %}
```

`firmware/templates/wizard_done.html`:
```html
{% extends "base.html" %}
{% block content %}
<main>
  {% if restarting %}
  <h1>Restarting…</h1>
  <p>Stillhem is joining <strong>{{ ssid }}</strong>. Reconnect your phone to your normal Wi-Fi. In a minute the admin page will be at <code>http://stillhem.local/</code>.</p>
  {% else %}
  <h1>Setup complete</h1>
  <p>Stillhem will restart and join <strong>{{ ssid }}</strong>. After that, manage it at <code>http://stillhem.local/</code>. You'll still need to point your router's DNS at the device — instructions will be on the admin page.</p>
  <form method="post" action="/wizard/finish">
    <button type="submit">Finish &amp; restart</button>
  </form>
  {% endif %}
</main>
{% endblock %}
```

- [ ] **Step 6: Run the wizard tests, then the full suite**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_wizard.py -q && .venv-sdd/bin/pytest -m "not integration" -q`
Expected: both PASS. If the existing `test_admin.py` tests break because the module-level default `create_app` behavior changed, investigate — they should not, since default `setup_mode=False` preserves prior behavior.

- [ ] **Step 7: Commit**

```bash
git add firmware/src/stillhem/admin/ firmware/templates/wizard_*.html firmware/tests/test_wizard.py
git commit -m "feat: captive-portal setup wizard (wifi/preset/password) with mode gate

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 4: System integration (systemd units, dnsmasq snippet, image install) + on-hardware acceptance

**Files:**
- Create: `firmware/systemd/stillhem-netmode.service`
- Modify: `firmware/systemd/stillhem-admin.service` (ExecStart → launcher; drop port 8080)
- Create: `firmware/network/dnsmasq-shared.d/stillhem-captive.conf`
- Modify: `image/stage-stillhem/00-install/01-run-chroot.sh` (install the new unit + snippet, enable netmode)
- Modify: `firmware/systemd/install.sh` (parity for the manual-install path)

**Interfaces:**
- Consumes: `stillhem.netmode.boot` and `stillhem.launch.main` (Tasks 1–2).
- Produces: an image whose first boot runs the mode selector before the admin service, with the captive DNS snippet in place.

This task's shell/unit files are verified by `bash -n` and inspection; the **real** verification is the on-hardware acceptance (Step 7), which the controller/user runs — it needs a full image build (sub-project 2) and a Pi 3 B+.

- [ ] **Step 1: Write `firmware/systemd/stillhem-netmode.service`**

```ini
[Unit]
Description=Stillhem network mode selector (AP setup vs. normal)
After=NetworkManager.service
Wants=NetworkManager.service
Before=stillhem-admin.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/stillhem/venv/bin/python -m stillhem.netmode boot

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Update `firmware/systemd/stillhem-admin.service`**

Replace the `[Unit]` after-line and the `ExecStart` so it depends on the selector and launches via the port-80 launcher:
```ini
[Unit]
Description=stillhem Admin Web Interface
After=network.target unbound.service stillhem-netmode.service
Wants=stillhem-netmode.service

[Service]
ExecStart=/opt/stillhem/venv/bin/python -m stillhem.launch
WorkingDirectory=/opt/stillhem/firmware
Environment="STILLHEM_DB_PATH=/var/lib/stillhem/stillhem.db"
Environment="STILLHEM_BLOCKLIST_PATH=/var/lib/stillhem/active_blocklist.txt"
Environment="STILLHEM_UNBOUND_CONF=/etc/unbound/unbound.conf.d/stillhem.conf"
Environment="STILLHEM_DNS_TEMPLATE_DIR=/opt/stillhem/firmware/dns"
Environment="STILLHEM_PRESET_DIR=/opt/stillhem/firmware/blocklists"
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Write `firmware/network/dnsmasq-shared.d/stillhem-captive.conf`**

```
# During AP (shared) mode, resolve every domain to the Pi so the captive
# portal and the buyer's browser reach the setup wizard.
address=/#/10.42.0.1
```

- [ ] **Step 4: Extend `image/stage-stillhem/00-install/01-run-chroot.sh`**

After the existing `install ... stillhem-admin.service` / `systemctl enable` block, add:
```bash
# Network-mode selector (AP setup vs. normal) + captive DNS for AP mode
install -m 644 /opt/stillhem/firmware/systemd/stillhem-netmode.service \
    /etc/systemd/system/stillhem-netmode.service
install -Dm 644 /opt/stillhem/firmware/network/dnsmasq-shared.d/stillhem-captive.conf \
    /etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf
systemctl enable stillhem-netmode.service
```

- [ ] **Step 5: Update `firmware/systemd/install.sh`** (manual-install parity)

After the existing systemd install block (the `ln -sf ... stillhem-admin.service` and enable lines), add the netmode unit + snippet install and enable it:
```bash
echo "==> Installing network-mode selector + captive DNS..."
ln -sf "$INSTALL_DIR/systemd/stillhem-netmode.service" /etc/systemd/system/stillhem-netmode.service
install -Dm 644 "$INSTALL_DIR/network/dnsmasq-shared.d/stillhem-captive.conf" \
    /etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf
systemctl enable stillhem-netmode
```
(Note: `should_enter_setup()` will not hijack an already-connected machine — a manually-installed Pi with wifi or ethernet already up boots straight to `normal` mode.)

- [ ] **Step 6: Syntax-check the shell scripts**

Run: `bash -n image/stage-stillhem/00-install/01-run-chroot.sh firmware/systemd/install.sh`
Expected: no output.

- [ ] **Step 7: Commit the integration files**

```bash
git add firmware/systemd/stillhem-netmode.service firmware/systemd/stillhem-admin.service firmware/network/ image/stage-stillhem/00-install/01-run-chroot.sh firmware/systemd/install.sh
git commit -m "feat: image integration for setup wizard (netmode unit, captive DNS, launcher)

Co-Authored-By: <model> <noreply@anthropic.com>"
```

- [ ] **Step 8: On-hardware acceptance (developer-run, Pi 3 B+)**

Rebuild the image (`bash image/build.sh`), flash, and boot a Pi with **no** saved Wi-Fi:
1. A `Stillhem Setup` open network appears; connecting a phone auto-opens the wizard (or open any URL if it doesn't).
2. Complete all three steps; the done screen appears and the device reboots.
3. The Pi joins the chosen home network; `http://stillhem.local/` serves the dashboard (login with the password just set); the chosen preset's domains return NXDOMAIN for a client using the Pi as DNS.

Record the outcome. Failures here loop back to the relevant task (netmode nmcli calls, the gate, or the image install).

---

## Self-review notes

- **Spec coverage:** AP + captive portal + 3-step wizard + reboot-to-client are Tasks 1/3/4; the boot-mode decision and non-fallback are Task 1 (`should_enter_setup`, `boot`); two-mode app + port 80 are Tasks 2/4; the dnsmasq captive redirect and mDNS-independent setup are Task 4. Router-DNS detail and dev-hardening are correctly deferred (only a forward-pointing line on the done screen).
- **Type consistency:** `create_app(setup_mode=)`, `get_config`/`set_config`, `netmode.*`, and `reload_dns(db_path, blocklist_path, unbound_conf_path, template_dir)` match their definitions across tasks; wizard tests patch the names at their point of use (`stillhem.admin.routes.wizard_routes.netmode.save_home_wifi`, `...wizard_routes.reload_dns`, `...wizard_routes.subprocess.Popen`).
- **Known soft spots (hardware-only):** exact `nmcli` behavior on the pinned bookworm image, single-radio scan-then-AP timing, and cross-phone captive-portal auto-open — all covered by Task 4 Step 8 on real hardware, with the "open any URL" fallback in the UI copy.
