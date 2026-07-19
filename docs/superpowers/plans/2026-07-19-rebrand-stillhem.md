# Rebrand Algoro → Stillhem + license fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the product from Algoro to Stillhem everywhere public-facing in this repo, and fix the LICENSE/README contradiction (README claims AGPLv3, LICENSE file is currently MIT text) by replacing LICENSE with the full AGPLv3 text.

**Architecture:** This is a pure rename/text-substitution effort with no new behavior — there is nothing to TDD in the "write a failing test first" sense. Instead, each task ends by running the existing test suite (`pytest -m "not integration"` from `firmware/`) to confirm the rename didn't break anything. Tasks are ordered so the suite stays green after every task.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, pytest — no new dependencies.

## Global Constraints

- Do not touch `docs/superpowers/plans/*.md` or `docs/superpowers/specs/*.md` — historical records, explicitly out of scope per the spec.
- Do not touch hostname/mDNS/avahi config — doesn't exist yet in this repo.
- Do not rename the GitHub repository (`hugokallstrom/algoro-pi`) as part of these tasks — that happens manually after this PR merges (see Task 9, which is a note, not a code task).
- Every task must leave `pytest -m "not integration"` passing when run from `firmware/`.

---

### Task 1: Rename the Python package and fix internal imports

**Files:**
- Move: `firmware/src/algoro/` → `firmware/src/stillhem/` (git mv, preserves all subfiles)
- Modify: `firmware/pyproject.toml`
- Modify: `firmware/src/stillhem/admin/app.py`
- Modify: `firmware/src/stillhem/admin/deps.py`
- Modify: `firmware/src/stillhem/admin/routes/blocklist_routes.py`
- Modify: `firmware/src/stillhem/admin/routes/setup_routes.py`
- Modify: `firmware/src/stillhem/admin/routes/auth_routes.py`
- Modify: `firmware/conftest.py`
- Modify: `firmware/tests/test_setup.py`
- Modify: `firmware/tests/test_db.py`
- Modify: `firmware/tests/test_auth.py`
- Modify: `firmware/tests/test_admin.py`
- Modify: `firmware/tests/test_blocklist.py`
- Modify: `firmware/tests/test_dns_control.py`
- Modify: `firmware/tests/test_integration.py`

**Interfaces:**
- Produces: package importable as `stillhem.*` (was `algoro.*`) — `stillhem.db`, `stillhem.auth`, `stillhem.blocklist`, `stillhem.dns_control`, `stillhem.admin.app.create_app`, `stillhem.admin.deps.require_auth`. All function signatures inside these modules are unchanged by this task.

- [ ] **Step 1: Move the package directory**

```bash
cd firmware
git mv src/algoro src/stillhem
```

- [ ] **Step 2: Update `firmware/pyproject.toml`**

Change:
```toml
[project]
name = "algoro"
```
To:
```toml
[project]
name = "stillhem"
```

- [ ] **Step 3: Update `firmware/src/stillhem/admin/app.py`**

Change lines 7-11 from:
```python
from algoro.admin.routes.auth_routes import router as auth_router
from algoro.admin.routes.blocklist_routes import router as blocklist_router
from algoro.admin.routes.setup_routes import router as setup_router
from algoro.blocklist import ACTIVE_BLOCKLIST_PATH
from algoro.dns_control import DEFAULT_TEMPLATE_DIR, UNBOUND_CONF_PATH
```
To:
```python
from stillhem.admin.routes.auth_routes import router as auth_router
from stillhem.admin.routes.blocklist_routes import router as blocklist_router
from stillhem.admin.routes.setup_routes import router as setup_router
from stillhem.blocklist import ACTIVE_BLOCKLIST_PATH
from stillhem.dns_control import DEFAULT_TEMPLATE_DIR, UNBOUND_CONF_PATH
```

(Leave the `os.environ.get("ALGORO_...")` lines further down untouched — those are handled in Task 2.)

- [ ] **Step 4: Update `firmware/src/stillhem/admin/deps.py`**

Change line 5 from:
```python
    from algoro.auth import validate_session_token
```
To:
```python
    from stillhem.auth import validate_session_token
```

- [ ] **Step 5: Update `firmware/src/stillhem/admin/routes/blocklist_routes.py`**

Change lines 7-9 from:
```python
from algoro.admin.deps import require_auth
from algoro.blocklist import add_domain, list_domains, remove_domain
from algoro.dns_control import is_unbound_running, reload_dns
```
To:
```python
from stillhem.admin.deps import require_auth
from stillhem.blocklist import add_domain, list_domains, remove_domain
from stillhem.dns_control import is_unbound_running, reload_dns
```

- [ ] **Step 6: Update `firmware/src/stillhem/admin/routes/setup_routes.py`**

Change line 7 from:
```python
from algoro.auth import is_password_set, set_password
```
To:
```python
from stillhem.auth import is_password_set, set_password
```

- [ ] **Step 7: Update `firmware/src/stillhem/admin/routes/auth_routes.py`**

Change lines 6-7 from:
```python
from algoro.auth import check_password, create_session_token, validate_session_token
from algoro.admin.deps import require_auth
```
To:
```python
from stillhem.auth import check_password, create_session_token, validate_session_token
from stillhem.admin.deps import require_auth
```

Change line 36 from:
```python
    from algoro.db import get_db
```
To:
```python
    from stillhem.db import get_db
```

- [ ] **Step 8: Update `firmware/conftest.py`**

Change line 3 from:
```python
from algoro.db import init_db
```
To:
```python
from stillhem.db import init_db
```

- [ ] **Step 9: Update `firmware/tests/test_setup.py`**

Change lines 6-7 from:
```python
from algoro.admin.app import create_app
from algoro.auth import is_password_set
```
To:
```python
from stillhem.admin.app import create_app
from stillhem.auth import is_password_set
```

- [ ] **Step 10: Update `firmware/tests/test_db.py`**

Change line 3 from:
```python
from algoro.db import init_db, get_db
```
To:
```python
from stillhem.db import init_db, get_db
```

- [ ] **Step 11: Update `firmware/tests/test_auth.py`**

Change line 2 from:
```python
from algoro.auth import (
```
To:
```python
from stillhem.auth import (
```

- [ ] **Step 12: Update `firmware/tests/test_admin.py`**

Change lines 6-7 from:
```python
from algoro.auth import set_password
from algoro.admin.app import create_app
```
To:
```python
from stillhem.auth import set_password
from stillhem.admin.app import create_app
```

Change line 68 from:
```python
from algoro.blocklist import add_domain, list_domains
```
To:
```python
from stillhem.blocklist import add_domain, list_domains
```

Change line 86 from:
```python
    with patch("algoro.admin.routes.blocklist_routes.reload_dns"):
```
To:
```python
    with patch("stillhem.admin.routes.blocklist_routes.reload_dns"):
```

Change line 97 from:
```python
    with patch("algoro.admin.routes.blocklist_routes.reload_dns"):
```
To:
```python
    with patch("stillhem.admin.routes.blocklist_routes.reload_dns"):
```

Change line 107 from:
```python
    with patch("algoro.admin.routes.blocklist_routes.reload_dns"):
```
To:
```python
    with patch("stillhem.admin.routes.blocklist_routes.reload_dns"):
```

(Leave line 55, `assert "algoro" in resp.text.lower()`, untouched — that's Task 6, since the template still renders "algoro" until then.)

- [ ] **Step 13: Update `firmware/tests/test_blocklist.py`**

Change line 3 from:
```python
from algoro.blocklist import (
```
To:
```python
from stillhem.blocklist import (
```

Change line 98 from:
```python
    from algoro.db import init_db
```
To:
```python
    from stillhem.db import init_db
```

(Leave the four `os.environ["ALGORO_PRESET_DIR"] = PRESET_DIR` lines at 71, 81, 88, 95 untouched — that's Task 2.)

- [ ] **Step 14: Update `firmware/tests/test_dns_control.py`**

Change line 6 from:
```python
from algoro.dns_control import (
```
To:
```python
from stillhem.dns_control import (
```

Change lines 63-64 from:
```python
    from algoro.db import init_db
    from algoro.blocklist import add_domain
```
To:
```python
    from stillhem.db import init_db
    from stillhem.blocklist import add_domain
```

Change lines 71-72 from:
```python
    with patch("algoro.dns_control.is_unbound_running", return_value=True), \
         patch("algoro.dns_control.reload_unbound") as mock_reload:
```
To:
```python
    with patch("stillhem.dns_control.is_unbound_running", return_value=True), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
```

Change lines 82-83 from:
```python
    from algoro.db import init_db
    from algoro.blocklist import add_domain
```
To:
```python
    from stillhem.db import init_db
    from stillhem.blocklist import add_domain
```

Change lines 90-91 from:
```python
    with patch("algoro.dns_control.is_unbound_running", return_value=False), \
         patch("algoro.dns_control.reload_unbound") as mock_reload:
```
To:
```python
    with patch("stillhem.dns_control.is_unbound_running", return_value=False), \
         patch("stillhem.dns_control.reload_unbound") as mock_reload:
```

(Leave the `tmp_path / "algoro.conf"` lines at 19, 29, 37, 69, 88 untouched — those are local test filenames, not package references. Renaming them is cosmetic only; skip to keep the diff focused.)

- [ ] **Step 15: Update `firmware/tests/test_integration.py`**

Change lines 8-11 from:
```python
from algoro.auth import set_password
from algoro.blocklist import add_domain, export_to_file
from algoro.db import init_db
from algoro.dns_control import (
```
To:
```python
from stillhem.auth import set_password
from stillhem.blocklist import add_domain, export_to_file
from stillhem.db import init_db
from stillhem.dns_control import (
```

(Leave the `"algoro-integration-test-blocked.invalid"` test domain strings at lines 26 and 35 untouched — they're arbitrary test fixture domains, not package/product references.)

- [ ] **Step 16: Reinstall the package so the new module name is on the path**

```bash
pip install -e ".[dev]"
```

- [ ] **Step 17: Run the test suite to confirm the rename is clean**

Run: `pytest -m "not integration" -v`
Expected: All tests PASS (same pass count as before the rename).

- [ ] **Step 18: Commit**

```bash
git add -A
git commit -m "refactor: rename algoro package to stillhem"
```

---

### Task 2: Rename env vars and hardcoded paths in source defaults

**Files:**
- Modify: `firmware/src/stillhem/db.py`
- Modify: `firmware/src/stillhem/blocklist.py`
- Modify: `firmware/src/stillhem/dns_control.py`
- Modify: `firmware/src/stillhem/admin/app.py`
- Modify: `firmware/tests/test_blocklist.py`

**Interfaces:**
- Produces: env vars `STILLHEM_DB_PATH`, `STILLHEM_BLOCKLIST_PATH`, `STILLHEM_UNBOUND_CONF`, `STILLHEM_DNS_TEMPLATE_DIR`, `STILLHEM_PRESET_DIR` (replacing the `ALGORO_*` names). Default filesystem paths change from `/opt/algoro`, `/var/lib/algoro`, `/etc/unbound/unbound.conf.d/algoro.conf` to their `stillhem` equivalents. No function signatures change.

- [ ] **Step 1: Update `firmware/src/stillhem/db.py`**

Change line 4 from:
```python
DB_PATH = Path("/var/lib/algoro/algoro.db")
```
To:
```python
DB_PATH = Path("/var/lib/stillhem/stillhem.db")
```

- [ ] **Step 2: Update `firmware/src/stillhem/blocklist.py`**

Change lines 6-11 from:
```python
ACTIVE_BLOCKLIST_PATH = Path(
    os.environ.get("ALGORO_BLOCKLIST_PATH", "/var/lib/algoro/active_blocklist.txt")
)
PRESET_DIR = Path(
    os.environ.get("ALGORO_PRESET_DIR", str(Path(__file__).parent.parent.parent / "blocklists"))
)
```
To:
```python
ACTIVE_BLOCKLIST_PATH = Path(
    os.environ.get("STILLHEM_BLOCKLIST_PATH", "/var/lib/stillhem/active_blocklist.txt")
)
PRESET_DIR = Path(
    os.environ.get("STILLHEM_PRESET_DIR", str(Path(__file__).parent.parent.parent / "blocklists"))
)
```

- [ ] **Step 3: Update `firmware/src/stillhem/dns_control.py`**

Change lines 9-14 from:
```python
UNBOUND_CONF_PATH = Path(
    os.environ.get("ALGORO_UNBOUND_CONF", "/etc/unbound/unbound.conf.d/algoro.conf")
)
DEFAULT_TEMPLATE_DIR = Path(
    os.environ.get("ALGORO_DNS_TEMPLATE_DIR", str(Path(__file__).parent.parent.parent / "dns"))
)
```
To:
```python
UNBOUND_CONF_PATH = Path(
    os.environ.get("STILLHEM_UNBOUND_CONF", "/etc/unbound/unbound.conf.d/stillhem.conf")
)
DEFAULT_TEMPLATE_DIR = Path(
    os.environ.get("STILLHEM_DNS_TEMPLATE_DIR", str(Path(__file__).parent.parent.parent / "dns"))
)
```

- [ ] **Step 4: Update `firmware/src/stillhem/admin/app.py`**

Change lines 36-40 from:
```python
app = create_app(
    db_path=Path(os.environ.get("ALGORO_DB_PATH", "/var/lib/algoro/algoro.db")),
    blocklist_path=Path(os.environ.get("ALGORO_BLOCKLIST_PATH", str(ACTIVE_BLOCKLIST_PATH))),
    unbound_conf_path=Path(os.environ.get("ALGORO_UNBOUND_CONF", str(UNBOUND_CONF_PATH))),
    template_dir=Path(os.environ.get("ALGORO_DNS_TEMPLATE_DIR", str(DEFAULT_TEMPLATE_DIR))),
)
```
To:
```python
app = create_app(
    db_path=Path(os.environ.get("STILLHEM_DB_PATH", "/var/lib/stillhem/stillhem.db")),
    blocklist_path=Path(os.environ.get("STILLHEM_BLOCKLIST_PATH", str(ACTIVE_BLOCKLIST_PATH))),
    unbound_conf_path=Path(os.environ.get("STILLHEM_UNBOUND_CONF", str(UNBOUND_CONF_PATH))),
    template_dir=Path(os.environ.get("STILLHEM_DNS_TEMPLATE_DIR", str(DEFAULT_TEMPLATE_DIR))),
)
```

- [ ] **Step 5: Update `firmware/tests/test_blocklist.py`**

Change the four occurrences (lines 71, 81, 88, 95) of:
```python
    os.environ["ALGORO_PRESET_DIR"] = PRESET_DIR
```
To:
```python
    os.environ["STILLHEM_PRESET_DIR"] = PRESET_DIR
```

- [ ] **Step 6: Run the test suite**

Run: `pytest -m "not integration" -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename ALGORO_* env vars and default paths to STILLHEM_*"
```

---

### Task 3: Rename and update the systemd service file

**Files:**
- Move: `firmware/systemd/algoro-admin.service` → `firmware/systemd/stillhem-admin.service`

**Interfaces:**
- Produces: systemd unit file named `stillhem-admin.service`, referencing the `stillhem` module and `STILLHEM_*` env vars from Task 2, and `/opt/stillhem` paths (install path itself is finalized in Task 4, but this file's own content must be internally consistent now).

- [ ] **Step 1: Move the file**

```bash
git mv firmware/systemd/algoro-admin.service firmware/systemd/stillhem-admin.service
```

- [ ] **Step 2: Update the file contents**

Change:
```ini
[Unit]
Description=algoro Admin Web Interface
After=network.target unbound.service

[Service]
ExecStart=/opt/algoro/venv/bin/uvicorn algoro.admin.app:app --host 0.0.0.0 --port 8080
WorkingDirectory=/opt/algoro/firmware
Environment="ALGORO_DB_PATH=/var/lib/algoro/algoro.db"
Environment="ALGORO_BLOCKLIST_PATH=/var/lib/algoro/active_blocklist.txt"
Environment="ALGORO_UNBOUND_CONF=/etc/unbound/unbound.conf.d/algoro.conf"
Environment="ALGORO_DNS_TEMPLATE_DIR=/opt/algoro/firmware/dns"
Environment="ALGORO_PRESET_DIR=/opt/algoro/firmware/blocklists"
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```
To:
```ini
[Unit]
Description=stillhem Admin Web Interface
After=network.target unbound.service

[Service]
ExecStart=/opt/stillhem/venv/bin/uvicorn stillhem.admin.app:app --host 0.0.0.0 --port 8080
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

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: rename systemd unit to stillhem-admin.service"
```

---

### Task 4: Update install.sh

**Files:**
- Modify: `firmware/systemd/install.sh`

**Interfaces:**
- Consumes: `firmware/systemd/stillhem-admin.service` (from Task 3), `stillhem.db` module (from Task 1).
- Produces: an install script that installs to `/opt/stillhem`, `/var/lib/stillhem`, and enables `stillhem-admin.service`.

- [ ] **Step 1: Update the full file**

Change:
```bash
#!/usr/bin/env bash
# Run as root on the Pi. Assumes:
# - repo is checked out at /opt/algoro
# - Python 3.11+, python3-venv, unbound, dnscrypt-proxy are installed
set -euo pipefail

INSTALL_DIR=/opt/algoro/firmware
DATA_DIR=/var/lib/algoro
VENV=/opt/algoro/venv

echo "==> Creating virtualenv..."
python3 -m venv "$VENV"

echo "==> Installing Python package..."
"$VENV/bin/pip" install -e "$INSTALL_DIR"

echo "==> Creating data directory..."
mkdir -p "$DATA_DIR"

echo "==> Initialising database..."
"$VENV/bin/python" -c "
from pathlib import Path
from algoro.db import init_db
init_db(Path('/var/lib/algoro/algoro.db'))
"

echo "==> Installing systemd units..."
ln -sf "$INSTALL_DIR/systemd/algoro-admin.service" /etc/systemd/system/algoro-admin.service
systemctl daemon-reload
systemctl enable algoro-admin
systemctl start algoro-admin

echo "==> Done. Admin UI running at http://$(hostname -I | awk '{print $1}')"
echo "    Set your router's DNS server to that IP."
```
To:
```bash
#!/usr/bin/env bash
# Run as root on the Pi. Assumes:
# - repo is checked out at /opt/stillhem
# - Python 3.11+, python3-venv, unbound, dnscrypt-proxy are installed
set -euo pipefail

INSTALL_DIR=/opt/stillhem/firmware
DATA_DIR=/var/lib/stillhem
VENV=/opt/stillhem/venv

echo "==> Creating virtualenv..."
python3 -m venv "$VENV"

echo "==> Installing Python package..."
"$VENV/bin/pip" install -e "$INSTALL_DIR"

echo "==> Creating data directory..."
mkdir -p "$DATA_DIR"

echo "==> Initialising database..."
"$VENV/bin/python" -c "
from pathlib import Path
from stillhem.db import init_db
init_db(Path('/var/lib/stillhem/stillhem.db'))
"

echo "==> Installing systemd units..."
ln -sf "$INSTALL_DIR/systemd/stillhem-admin.service" /etc/systemd/system/stillhem-admin.service
systemctl daemon-reload
systemctl enable stillhem-admin
systemctl start stillhem-admin

echo "==> Done. Admin UI running at http://$(hostname -I | awk '{print $1}')"
echo "    Set your router's DNS server to that IP."
```

- [ ] **Step 2: Verify the script is still valid bash**

Run: `bash -n firmware/systemd/install.sh`
Expected: no output (syntax OK).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: update install.sh for stillhem paths and service name"
```

---

### Task 5: Update README.md

**Files:**
- Modify: `README.md`

**Interfaces:**
- None (documentation only).

- [ ] **Step 1: Update the title**

Change:
```markdown
# algoro
```
To:
```markdown
# stillhem
```

- [ ] **Step 2: Update the install section**

Change:
```markdown
Clone to `/opt/algoro` and run as root:

```bash
bash /opt/algoro/firmware/systemd/install.sh
```

This installs the Python package, initialises the SQLite database, and starts the `algoro-admin` systemd service on port 80.
```
To:
```markdown
Clone to `/opt/stillhem` and run as root:

```bash
bash /opt/stillhem/firmware/systemd/install.sh
```

This installs the Python package, initialises the SQLite database, and starts the `stillhem-admin` systemd service on port 80.
```

- [ ] **Step 3: Update the environment variables table**

Change:
```markdown
| Variable | Default | Description |
|---|---|---|
| `ALGORO_DB_PATH` | `/var/lib/algoro/algoro.db` | SQLite database |
| `ALGORO_BLOCKLIST_PATH` | `/var/lib/algoro/active_blocklist.txt` | Active blocklist file |
| `ALGORO_UNBOUND_CONF` | `/etc/unbound/unbound.conf.d/algoro.conf` | Generated Unbound config |
| `ALGORO_DNS_TEMPLATE_DIR` | `firmware/dns` | Jinja2 template directory |
| `ALGORO_PRESET_DIR` | `firmware/blocklists` | Preset list directory |
```
To:
```markdown
| Variable | Default | Description |
|---|---|---|
| `STILLHEM_DB_PATH` | `/var/lib/stillhem/stillhem.db` | SQLite database |
| `STILLHEM_BLOCKLIST_PATH` | `/var/lib/stillhem/active_blocklist.txt` | Active blocklist file |
| `STILLHEM_UNBOUND_CONF` | `/etc/unbound/unbound.conf.d/stillhem.conf` | Generated Unbound config |
| `STILLHEM_DNS_TEMPLATE_DIR` | `firmware/dns` | Jinja2 template directory |
| `STILLHEM_PRESET_DIR` | `firmware/blocklists` | Preset list directory |
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for stillhem rebrand"
```

---

### Task 6: Update templates and the admin test that asserts on rendered text

**Files:**
- Modify: `firmware/templates/base.html`
- Modify: `firmware/templates/dashboard.html`
- Modify: `firmware/templates/login.html`
- Modify: `firmware/templates/setup.html`
- Modify: `firmware/tests/test_admin.py`

**Interfaces:**
- None (template text only; no Jinja variable/block names change).

- [ ] **Step 1: Update `firmware/templates/base.html`**

Change line 6 from:
```html
  <title>algoro</title>
```
To:
```html
  <title>stillhem</title>
```

- [ ] **Step 2: Update `firmware/templates/dashboard.html`**

Change line 4 from:
```html
  <h1>algoro</h1>
```
To:
```html
  <h1>stillhem</h1>
```

- [ ] **Step 3: Update `firmware/templates/login.html`**

Change line 4 from:
```html
  <h1>algoro</h1>
```
To:
```html
  <h1>stillhem</h1>
```

- [ ] **Step 4: Update `firmware/templates/setup.html`**

Change line 4 from:
```html
  <h1>algoro — first-time setup</h1>
```
To:
```html
  <h1>stillhem — first-time setup</h1>
```

- [ ] **Step 5: Update `firmware/tests/test_admin.py`**

Change line 55 from:
```python
    assert "algoro" in resp.text.lower()
```
To:
```python
    assert "stillhem" in resp.text.lower()
```

- [ ] **Step 6: Run the test suite**

Run: `pytest -m "not integration" -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: update templates and admin test for stillhem branding"
```

---

### Task 7: Replace LICENSE with the full AGPLv3 text

**Files:**
- Modify: `LICENSE`

**Interfaces:**
- None.

- [ ] **Step 1: Replace the file contents with the canonical AGPLv3 text**

The current `LICENSE` file contains MIT license text, but `README.md`'s "## License" section states AGPLv3. Fetch the canonical, unmodified AGPLv3 text from GitHub's licenses API (this is the exact text GitHub's `licensee` detector matches against — do not paraphrase, shorten, or insert a copyright line into it):

```bash
curl -s https://api.github.com/licenses/agpl-3.0 | python3 -c "import json,sys; sys.stdout.write(json.load(sys.stdin)['body'])" > LICENSE
```

The LICENSE file must be the verbatim license text only. The "how to apply" copyright notice convention for AGPLv3 places `Copyright (c) 2026 Hugo Linder` in source file headers or the README, not in the LICENSE file itself — the README's existing "## License" section already covers attribution.

- [ ] **Step 2: Verify the file is the canonical AGPLv3 text**

Run: `head -5 LICENSE && wc -l LICENSE`
Expected: first lines contain `GNU AFFERO GENERAL PUBLIC LICENSE` and `Version 3, 19 November 2007` (not MIT boilerplate), and the file is roughly 600+ lines.

- [ ] **Step 3: Commit**

```bash
git add LICENSE
git commit -m "fix: replace MIT LICENSE text with AGPLv3 to match README"
```

---

### Task 8: Final verification sweep

**Files:** None modified — verification only.

- [ ] **Step 1: Grep for any remaining case-insensitive "algoro" references outside the excluded historical docs**

```bash
grep -rIn "algoro" --include="*" . 2>/dev/null | grep -v '\.git/' | grep -v 'docs/superpowers/plans/' | grep -v 'docs/superpowers/specs/'
```
Expected: no output.

- [ ] **Step 2: Grep for any remaining "ALGORO" env var references outside the excluded historical docs**

```bash
grep -rIn "ALGORO" --include="*" . 2>/dev/null | grep -v '\.git/' | grep -v 'docs/superpowers/plans/' | grep -v 'docs/superpowers/specs/'
```
Expected: no output.

- [ ] **Step 3: Run the full non-integration test suite one final time**

```bash
cd firmware && pytest -m "not integration" -v
```
Expected: All tests PASS.

- [ ] **Step 4: No commit needed** — this task is verification-only. If either grep finds a stray reference, fix it in place and make a small follow-up commit:

```bash
git add -A
git commit -m "refactor: catch remaining algoro references missed by earlier tasks"
```

---

## Post-merge note (not a task in this plan)

After this PR merges into `main`, rename the GitHub repository from `hugokallstrom/algoro-pi` to `stillhem` via `gh repo rename stillhem`, then update the local `origin` remote URL with `git remote set-url origin <new-url>`. This is deliberately not automated in this plan since it changes shared/external state outside the repo's own files.
