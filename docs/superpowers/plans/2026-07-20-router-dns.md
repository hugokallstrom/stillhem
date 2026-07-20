# Router-DNS step UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the buyer a clear, per-brand "point your router's DNS at the Pi" page showing the Pi's IP, plus a dashboard indicator that tells them whether the change took effect.

**Architecture:** Two tasks. (1) Testable primitives: `stillhem.netinfo.primary_ip`, `stillhem.dns_control.total_queries`, and a pure `stillhem.serving` module (queries-per-minute + threshold). (2) The web layer: a `/router` page with per-brand instructions, and a dashboard banner driven by the serving heuristic, plus a one-line wizard done-screen copy update.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, Unbound (`unbound-control`), pytest. No new pip dependencies.

## Global Constraints

- The "serving your network" signal is a **traffic-volume heuristic**, not a per-client device count (Unbound doesn't cheaply expose per-client counts). UI copy and comments must say so; a quiet network reading "not set up yet" is acceptable.
- `SERVING_QPM_THRESHOLD = 3.0` (queries/min). A counter that went backwards (Unbound restart) reads as not-serving.
- DHCP takeover is NOT built (documented non-choice in the spec).
- Router brands: Telia, Tele2/Comhem, Bahnhof, Telenor, plus generic Asus / TP-Link / Netgear, plus an ISP-locked-router per-device fallback. Static template content.
- Every task leaves `pytest -m "not integration"` passing (run from `firmware/`, use `firmware/.venv-sdd/bin/pytest`; never commit `.venv-sdd/`).

---

### Task 1: Primitives — `netinfo`, `total_queries`, `serving`

**Files:**
- Create: `firmware/src/stillhem/netinfo.py`
- Modify: `firmware/src/stillhem/dns_control.py` (add `total_queries`)
- Create: `firmware/src/stillhem/serving.py`
- Create: `firmware/tests/test_netinfo.py`
- Modify: `firmware/tests/test_dns_control.py` (add `total_queries` tests)
- Create: `firmware/tests/test_serving.py`

**Interfaces:**
- Produces:
  - `netinfo.primary_ip() -> str` (LAN IPv4; `"127.0.0.1"` on error)
  - `dns_control.total_queries() -> int` (Unbound total queries; `0` if unavailable/unparseable)
  - `serving.SERVING_QPM_THRESHOLD: float`, `serving.queries_per_minute(prev_ts, prev_count, cur_ts, cur_count) -> float`, `serving.is_serving(qpm) -> bool`

- [ ] **Step 1: Write failing tests `firmware/tests/test_netinfo.py`**

```python
from unittest.mock import MagicMock, patch

from stillhem import netinfo


def test_primary_ip_returns_socket_name():
    sock = MagicMock()
    sock.getsockname.return_value = ("192.168.1.42", 51234)
    with patch("socket.socket", return_value=sock):
        assert netinfo.primary_ip() == "192.168.1.42"
    sock.connect.assert_called_once()
    sock.close.assert_called_once()


def test_primary_ip_falls_back_on_error():
    sock = MagicMock()
    sock.connect.side_effect = OSError("no route")
    with patch("socket.socket", return_value=sock):
        assert netinfo.primary_ip() == "127.0.0.1"
    sock.close.assert_called_once()
```

- [ ] **Step 2: Write failing tests `firmware/tests/test_serving.py`**

```python
from stillhem.serving import SERVING_QPM_THRESHOLD, is_serving, queries_per_minute


def test_qpm_basic_rate():
    # 300 queries over 60 seconds = 300/min
    assert queries_per_minute(1000.0, 0, 1060.0, 300) == 300.0


def test_qpm_zero_when_no_time_elapsed():
    assert queries_per_minute(1000.0, 0, 1000.0, 50) == 0.0


def test_qpm_zero_on_counter_reset():
    # cur_count < prev_count means Unbound restarted; treat as no signal
    assert queries_per_minute(1000.0, 500, 1060.0, 10) == 0.0


def test_is_serving_threshold():
    assert is_serving(SERVING_QPM_THRESHOLD) is True
    assert is_serving(SERVING_QPM_THRESHOLD - 0.1) is False
    assert is_serving(0.0) is False
```

- [ ] **Step 3: Add failing `total_queries` tests to `firmware/tests/test_dns_control.py`** (append)

```python
from unittest.mock import MagicMock, patch as _patch

from stillhem.dns_control import total_queries


def test_total_queries_parses_stat():
    out = "thread0.num.queries=5\ntotal.num.queries=1234\ntotal.num.cachehits=9\n"
    with _patch("subprocess.run", return_value=MagicMock(stdout=out)):
        assert total_queries() == 1234


def test_total_queries_zero_when_line_missing():
    with _patch("subprocess.run", return_value=MagicMock(stdout="total.num.cachehits=9\n")):
        assert total_queries() == 0


def test_total_queries_zero_on_control_error():
    import subprocess
    with _patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "unbound-control")):
        assert total_queries() == 0
```

- [ ] **Step 4: Run the three test files to verify they fail**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_netinfo.py tests/test_serving.py tests/test_dns_control.py -q`
Expected: FAIL (`No module named 'stillhem.netinfo'`, `...serving`, `cannot import name 'total_queries'`).

- [ ] **Step 5: Write `firmware/src/stillhem/netinfo.py`**

```python
import socket


def primary_ip() -> str:
    """Best-effort primary LAN IPv4. Uses a UDP socket's local name (no packets
    are actually sent by connect() on a datagram socket). Falls back to loopback."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 53))  # TEST-NET-1; unreachable but sets a route
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
```

- [ ] **Step 6: Write `firmware/src/stillhem/serving.py`**

```python
"""Heuristic for whether the LAN's DNS is pointed at this device.

Traffic-volume signal, NOT a device count: an idle appliance resolves almost
nothing, so query volume jumps once the router points the LAN's DNS at the Pi.
"""

SERVING_QPM_THRESHOLD = 3.0


def queries_per_minute(prev_ts: float, prev_count: int, cur_ts: float, cur_count: int) -> float:
    elapsed = cur_ts - prev_ts
    if elapsed <= 0:
        return 0.0
    delta = cur_count - prev_count
    if delta < 0:  # counter reset (Unbound restarted) — no usable signal
        return 0.0
    return delta / elapsed * 60.0


def is_serving(qpm: float) -> bool:
    return qpm >= SERVING_QPM_THRESHOLD
```

- [ ] **Step 7: Add `total_queries` to `firmware/src/stillhem/dns_control.py`** (append after `is_unbound_running`)

```python
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
```

- [ ] **Step 8: Run the targeted tests, then the full suite**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_netinfo.py tests/test_serving.py tests/test_dns_control.py -q && .venv-sdd/bin/pytest -m "not integration" -q`
Expected: both PASS.

- [ ] **Step 9: Commit**

```bash
git add firmware/src/stillhem/netinfo.py firmware/src/stillhem/serving.py firmware/src/stillhem/dns_control.py firmware/tests/test_netinfo.py firmware/tests/test_serving.py firmware/tests/test_dns_control.py
git commit -m "feat: primitives for router-DNS UX (primary_ip, total_queries, serving heuristic)

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 2: `/router` page, dashboard serving banner, wizard copy

**Files:**
- Create: `firmware/src/stillhem/admin/routes/router_routes.py`
- Modify: `firmware/src/stillhem/admin/app.py` (include the router)
- Modify: `firmware/src/stillhem/admin/routes/blocklist_routes.py` (dashboard passes `serving` + `pi_ip`)
- Create: `firmware/templates/router.html`
- Modify: `firmware/templates/dashboard.html` (serving banner)
- Modify: `firmware/templates/wizard_done.html` (name the router step)
- Modify: `firmware/tests/test_admin.py` (dashboard banner tests)
- Create: `firmware/tests/test_router.py`

**Interfaces:**
- Consumes: `netinfo.primary_ip`, `dns_control.total_queries`, `serving.queries_per_minute`/`is_serving` (Task 1); `get_config`/`set_config` (sub-project 3); existing `require_auth`.
- Produces: `GET /router` (auth-required); dashboard template vars `serving: bool`, `pi_ip: str`.

- [ ] **Step 1: Write failing test `firmware/tests/test_router.py`**

```python
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from stillhem.admin.app import create_app
from stillhem.auth import set_password


@pytest.fixture
def authed_client(db_path: Path):
    set_password("testpass", db_path)
    client = TestClient(create_app(db_path=db_path))
    client.post("/login", data={"password": "testpass"})
    return client


def test_router_page_requires_auth(db_path: Path):
    client = TestClient(create_app(db_path=db_path))
    set_password("testpass", db_path)
    resp = client.get("/router", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


def test_router_page_shows_ip_and_a_brand(authed_client: TestClient):
    with patch("stillhem.admin.routes.router_routes.primary_ip", return_value="192.168.1.50"):
        resp = authed_client.get("/router")
    assert resp.status_code == 200
    assert "192.168.1.50" in resp.text
    assert "Telia" in resp.text  # at least one per-brand section renders
```

- [ ] **Step 2: Add failing dashboard-banner tests to `firmware/tests/test_admin.py`** (append)

```python
import time as _time

from stillhem.db import set_config as _set_config


def test_dashboard_shows_not_set_up_when_quiet(authed_client: TestClient, db_path) -> None:
    with patch("stillhem.admin.routes.blocklist_routes.total_queries", return_value=0):
        resp = authed_client.get("/")
    assert resp.status_code == 200
    assert "isn't set up yet" in resp.text
    assert "/router" in resp.text


def test_dashboard_shows_serving_when_traffic_flowing(authed_client: TestClient, db_path) -> None:
    # Seed a prior sample 60s ago at count 0; now report 300 -> 300 q/min -> serving.
    _set_config(db_path, "serving_sample", f"{_time.time() - 60}:0")
    with patch("stillhem.admin.routes.blocklist_routes.total_queries", return_value=300):
        resp = authed_client.get("/")
    assert resp.status_code == 200
    assert "serving your network" in resp.text
```

(Note: `authed_client` and `patch` already exist in `test_admin.py`; reuse them.)

- [ ] **Step 3: Run to verify failure**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_router.py tests/test_admin.py -q`
Expected: FAIL (no `router_routes`; dashboard doesn't emit the banner strings).

- [ ] **Step 4: Write `firmware/src/stillhem/admin/routes/router_routes.py`**

```python
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from stillhem.admin.deps import require_auth
from stillhem.netinfo import primary_ip

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent.parent.parent / "templates")
)


@router.get("/router", response_class=HTMLResponse)
def router_page(request: Request, _token: str = Depends(require_auth)) -> HTMLResponse:
    return templates.TemplateResponse(request, "router.html", {"pi_ip": primary_ip()})
```

- [ ] **Step 5: Register the router in `firmware/src/stillhem/admin/app.py`**

Add the import with the other route imports:
```python
from stillhem.admin.routes.router_routes import router as router_setup_router
```
And include it with the others in `create_app`:
```python
    app.include_router(router_setup_router)
```

- [ ] **Step 6: Add the serving computation to `firmware/src/stillhem/admin/routes/blocklist_routes.py`**

Add imports at the top:
```python
import time

from stillhem.db import get_config, set_config
from stillhem.dns_control import is_unbound_running, reload_dns, total_queries
from stillhem.netinfo import primary_ip
from stillhem.serving import is_serving, queries_per_minute
```
(Replace the existing `from stillhem.dns_control import is_unbound_running, reload_dns` line with the combined one above.)

Add a helper above `_dashboard_response`:
```python
def _is_serving(db_path) -> bool:
    now = time.time()
    count = total_queries()
    serving = False
    prev = get_config(db_path, "serving_sample")
    if prev:
        try:
            prev_ts, prev_count = prev.split(":")
            qpm = queries_per_minute(float(prev_ts), int(prev_count), now, count)
            serving = is_serving(qpm)
        except ValueError:
            serving = False
    set_config(db_path, "serving_sample", f"{now}:{count}")
    return serving
```

Update `_dashboard_response` to pass `serving` and `pi_ip`:
```python
def _dashboard_response(request: Request) -> HTMLResponse:
    db_path = request.app.state.db_path
    domains = list_domains(db_path)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "domains": domains,
            "domain_count": len(domains),
            "blocking_active": is_unbound_running(),
            "serving": _is_serving(db_path),
            "pi_ip": primary_ip(),
        },
    )
```

- [ ] **Step 7: Add the banner to `firmware/templates/dashboard.html`** (immediately after the `<nav>...</nav>` block, before the existing `<p class="status">`)

```html
{% if serving %}
<p class="status"><span class="status-active">Stillhem is serving your network ✓</span></p>
{% else %}
<p class="status"><span class="status-inactive">DNS isn't set up yet</span> —
  <a href="/router">Set up your router</a> (point it at {{ pi_ip }})</p>
{% endif %}
```

- [ ] **Step 8: Write `firmware/templates/router.html`**

```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Set up your router</h1>
  <p>Stillhem only blocks once your router sends every device's DNS to it. Set your
     router's DNS server to this device's address:</p>
  <p style="font-size:1.5rem;font-weight:bold">{{ pi_ip }}</p>

  <h2>Generic steps</h2>
  <ol>
    <li>Open your router's admin page in a browser (often <code>192.168.0.1</code> or
        <code>192.168.1.1</code>).</li>
    <li>Log in (the password is usually on a sticker on the router).</li>
    <li>Find the <strong>DNS</strong> setting — usually under Internet, LAN, or DHCP.</li>
    <li>Set the primary DNS server to <strong>{{ pi_ip }}</strong>. Clear any secondary DNS,
        or set it to the same address.</li>
    <li>Save, then reconnect a device (or wait a few minutes) for it to take effect.</li>
  </ol>

  <h2>Instructions for common routers</h2>
  <details><summary>Telia</summary>
    <p>Telia Router → <em>Avancerade inställningar</em> → <em>Nätverk / LAN</em> →
       DNS. Set primary DNS to {{ pi_ip }}.</p></details>
  <details><summary>Tele2 / Comhem</summary>
    <p>Login at the router's address → <em>Inställningar</em> → <em>Nätverk</em> → DHCP/DNS.
       Set DNS to {{ pi_ip }}.</p></details>
  <details><summary>Bahnhof</summary>
    <p>Router admin → <em>LAN</em> / <em>DHCP-server</em> → DNS. Set to {{ pi_ip }}.</p></details>
  <details><summary>Telenor</summary>
    <p>Telenor router → <em>Inställningar</em> → <em>Nätverk / LAN</em> → DNS. Set to {{ pi_ip }}.</p></details>
  <details><summary>Asus</summary>
    <p>asusrouter.com → <em>LAN</em> → <em>DHCP Server</em> → "DNS Server 1" = {{ pi_ip }}.</p></details>
  <details><summary>TP-Link</summary>
    <p>tplinkwifi.net → <em>Advanced</em> → <em>Network</em> → <em>DHCP Server</em> →
       Primary DNS = {{ pi_ip }}.</p></details>
  <details><summary>Netgear</summary>
    <p>routerlogin.net → <em>Advanced</em> → <em>Setup</em> → <em>Internet/LAN Setup</em> →
       DNS = {{ pi_ip }}.</p></details>

  <h2>If your router won't let you change DNS</h2>
  <p>Some ISP-locked routers don't allow it. You can instead set the DNS to {{ pi_ip }} on
     each device (phone/computer Wi-Fi settings → DNS), though that only covers the devices
     you change.</p>

  <p><a href="/">← Back to dashboard</a></p>
</main>
{% endblock %}
```

- [ ] **Step 9: Update `firmware/templates/wizard_done.html`** — name the router step in the non-restarting branch

Change the completion sentence that currently points vaguely at the admin page so it names the step; replace:
```html
  <p>Stillhem will restart and join <strong>{{ ssid }}</strong>. After that, manage it at <code>http://stillhem.local/</code>. You'll still need to point your router's DNS at the device — instructions will be on the admin page.</p>
```
with:
```html
  <p>Stillhem will restart and join <strong>{{ ssid }}</strong>. After that, open <code>http://stillhem.local/</code> and follow <strong>Set up your router</strong> to finish — that's the last step before blocking works.</p>
```

- [ ] **Step 10: Run the router + dashboard tests, then the full suite**

Run: `cd firmware && .venv-sdd/bin/pytest tests/test_router.py tests/test_admin.py -q && .venv-sdd/bin/pytest -m "not integration" -q`
Expected: both PASS. Existing dashboard tests still pass (the banner is additive; `total_queries` is called on load — in tests without a patch it returns 0 via the FileNotFoundError path, so unpatched dashboard tests see the "not set up" banner, which doesn't conflict with their existing assertions about domains/blocking).

- [ ] **Step 11: Commit**

```bash
git add firmware/src/stillhem/admin/ firmware/templates/router.html firmware/templates/dashboard.html firmware/templates/wizard_done.html firmware/tests/test_router.py firmware/tests/test_admin.py
git commit -m "feat: router-DNS setup page + dashboard serving indicator

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** per-brand instructions + Pi IP = Task 2 (`/router` + `router.html`); the "is it working" loop-closer = the serving heuristic (Task 1 primitives + Task 2 dashboard banner); the wizard→router handoff = the done-screen copy update; the DHCP-takeover non-choice is documented in the spec, nothing to build. ISP-locked fallback is in `router.html`.
- **Type consistency:** `primary_ip() -> str`, `total_queries() -> int`, `queries_per_minute(float,int,float,int) -> float`, `is_serving(float) -> bool` are used consistently; the dashboard test patches `stillhem.admin.routes.blocklist_routes.total_queries` (imported into that module), and the router test patches `stillhem.admin.routes.router_routes.primary_ip`.
- **Known soft spot:** the serving indicator is a heuristic (documented); it writes a `serving_sample` config row on each dashboard load (infrequent, negligible SD wear). No hardware needed to merge; an optional real-router check can confirm the banner flips.
