# Stillhem pi-gen image build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a clean checkout on a Mac with Docker Desktop, `bash image/build.sh` produces a flashable `image/deploy/stillhem-<version>.img.xz` that boots a Raspberry Pi 3 B+ into the existing Unbound + FastAPI admin service.

**Architecture:** A new top-level `image/` directory holds a build entrypoint (`build.sh`), a pi-gen `config`, and a custom pi-gen stage (`stage-stillhem`). `build.sh` clones upstream pi-gen (arm64 branch, pinned SHA) into a git-ignored working dir, snapshots the repo at HEAD via `git archive` into the stage, and invokes pi-gen's `build-docker.sh`. This is build plumbing — there are no unit tests; each task ends with a concrete verification command, and the final task is a full build + on-hardware acceptance.

**Tech Stack:** pi-gen (Debian bootstrap image builder), Docker Desktop on macOS/arm64, bash. No changes to the Python package.

## Global Constraints

- Pinned pi-gen commit: **`ca8aeed0ae300c2a89f55ce9617d5f96a27e99e5`** (RPi-Distro/pi-gen, `arm64` branch). Hardcode this SHA in `build.sh`.
- Debian release: **`bookworm`** (pinned in `config`, not pi-gen's default).
- Image name / output: `IMG_NAME="stillhem"`, `DEPLOY_COMPRESSION="xz"`; final artifact renamed to `image/deploy/stillhem-<version>.img.xz` where `<version>` is `version` from `firmware/pyproject.toml` (currently `0.1.0`).
- Do NOT bake in dnscrypt-proxy — Unbound forwards directly (repo already does this). Packages baked in: `unbound python3-venv python3-pip avahi-daemon`.
- Target hostname `stillhem`; first user `stillhem` / pass `stillhem`; `ENABLE_SSH=1`. These are DEV-ONLY conveniences (hardening is deferred to sub-project 5) — put a comment saying so in `config`.
- `image/pi-gen/` and `image/deploy/` are git-ignored; everything else under `image/` is committed.
- `build.sh` must refuse to build on a dirty git tree (the image must map to a real commit) unless `ALLOW_DIRTY=1`.

---

### Task 1: Scaffold `image/` and the build entrypoint

**Files:**
- Create: `image/build.sh`
- Create: `image/config`
- Create: `image/.gitignore`
- Create: `image/README.md`

**Interfaces:**
- Produces: `image/build.sh`, runnable as `bash image/build.sh`. Supports env vars `ALLOW_DIRTY=1` (skip clean-tree check), `DRY_RUN=1` (do everything except invoke `build-docker.sh`), and passes through `PRESERVE_CONTAINER` / `CONTINUE` to pi-gen. Reads version from `firmware/pyproject.toml`. Writes the repo snapshot to `image/stage-stillhem/00-install/files/stillhem-src.tar` (Task 2 creates that stage dir; in Task 1 the script must `mkdir -p` the parent before writing).

- [ ] **Step 1: Write `image/.gitignore`**

```gitignore
pi-gen/
deploy/
stage-stillhem/00-install/files/stillhem-src.tar
```

- [ ] **Step 2: Write `image/config`**

```bash
# pi-gen config for the Stillhem image. Sourced by build-docker.sh.
IMG_NAME="stillhem"
RELEASE="bookworm"
DEPLOY_COMPRESSION="xz"
COMPRESSION_LEVEL="6"
TARGET_HOSTNAME="stillhem"

# --- DEV-ONLY convenience credentials/access. ---
# The same .img ships to every buyer, so a baked-in password is a shared
# credential. Sub-project 5 (release automation) MUST lock the first user
# and disable (or set key-only) SSH before any buyer-facing image. Do not
# ship as-is.
FIRST_USER_NAME="stillhem"
FIRST_USER_PASS="stillhem"
DISABLE_FIRST_BOOT_USER_RENAME="1"
ENABLE_SSH="1"

LOCALE_DEFAULT="en_US.UTF-8"
KEYBOARD_KEYMAP="se"
TIMEZONE_DEFAULT="Europe/Stockholm"
WPA_COUNTRY="SE"
```

(Note: `STAGE_LIST` is deliberately NOT set here — `build.sh` appends it after locating the pi-gen clone and the custom stage, so the absolute path is correct.)

- [ ] **Step 3: Write `image/build.sh`**

```bash
#!/usr/bin/env bash
# Build the Stillhem Raspberry Pi image. Run on a Mac with Docker Desktop.
set -euo pipefail

PIGEN_REPO="https://github.com/RPi-Distro/pi-gen.git"
PIGEN_BRANCH="arm64"
PIGEN_COMMIT="ca8aeed0ae300c2a89f55ce9617d5f96a27e99e5"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_DIR="$REPO_ROOT/image"
PIGEN_DIR="$IMAGE_DIR/pi-gen"
STAGE_DIR="$IMAGE_DIR/stage-stillhem"
DEPLOY_DIR="$IMAGE_DIR/deploy"

# 1. Version from pyproject.toml
VERSION="$(grep -E '^version = ' "$REPO_ROOT/firmware/pyproject.toml" | head -1 | sed -E 's/version = "(.*)"/\1/')"
if [ -z "$VERSION" ]; then
  echo "ERROR: could not read version from firmware/pyproject.toml" >&2
  exit 1
fi
echo "==> Building Stillhem image version $VERSION"

# 2. Clean-tree check (image must map to a real commit)
if [ "${ALLOW_DIRTY:-0}" != "1" ]; then
  if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
    echo "ERROR: working tree is dirty. Commit changes first, or set ALLOW_DIRTY=1." >&2
    exit 1
  fi
fi

# 3. Clone + pin pi-gen
if [ ! -d "$PIGEN_DIR/.git" ]; then
  echo "==> Cloning pi-gen ($PIGEN_BRANCH) into $PIGEN_DIR"
  git clone --branch "$PIGEN_BRANCH" "$PIGEN_REPO" "$PIGEN_DIR"
fi
echo "==> Pinning pi-gen at $PIGEN_COMMIT"
git -C "$PIGEN_DIR" fetch --quiet origin "$PIGEN_BRANCH"
git -C "$PIGEN_DIR" checkout --quiet "$PIGEN_COMMIT"

# 4. Snapshot repo at HEAD into the stage
echo "==> Snapshotting repo at HEAD into stage"
mkdir -p "$STAGE_DIR/00-install/files"
git -C "$REPO_ROOT" archive --format=tar HEAD > "$STAGE_DIR/00-install/files/stillhem-src.tar"

# 5. Copy config + stage into pi-gen
cp "$IMAGE_DIR/config" "$PIGEN_DIR/config"
rm -rf "$PIGEN_DIR/stage-stillhem"
cp -R "$STAGE_DIR" "$PIGEN_DIR/stage-stillhem"
# Suppress stage2's own image export so only the Stillhem image is produced
touch "$PIGEN_DIR/stage2/SKIP_IMAGES"
# Select stages: Lite base + our stage
echo 'STAGE_LIST="stage0 stage1 stage2 '"$PIGEN_DIR"'/stage-stillhem"' >> "$PIGEN_DIR/config"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "==> DRY_RUN=1: prepared pi-gen at $PIGEN_DIR, skipping build-docker.sh"
  exit 0
fi

# 6. Build
echo "==> Running pi-gen build-docker.sh (this takes a while)"
( cd "$PIGEN_DIR" && ./build-docker.sh )

# 7. Collect artifact
mkdir -p "$DEPLOY_DIR"
SRC_IMG="$(ls -t "$PIGEN_DIR"/deploy/*.img.xz | head -1)"
DEST_IMG="$DEPLOY_DIR/stillhem-$VERSION.img.xz"
mv "$SRC_IMG" "$DEST_IMG"
echo "==> Done: $DEST_IMG ($(du -h "$DEST_IMG" | cut -f1))"
```

- [ ] **Step 4: Make it executable**

Run: `chmod +x image/build.sh`

- [ ] **Step 5: Write `image/README.md`**

```markdown
# Stillhem image build

Builds a flashable Raspberry Pi image from this repo. **Only the developer runs
this** — buyers just flash the resulting `.img` with Raspberry Pi Imager.

## Requirements

- macOS with Docker Desktop running
- ~10 GB free disk, a fast connection (first build bootstraps Debian)

## Build

```bash
bash image/build.sh
```

Output: `image/deploy/stillhem-<version>.img.xz`. The build refuses to run on a
dirty git tree (the image must map to a committed state); use `ALLOW_DIRTY=1` to
override during local iteration. `DRY_RUN=1` prepares pi-gen without building.
`PRESERVE_CONTAINER=1` keeps the pi-gen container between runs for faster
iteration.

## Acceptance (on a Pi 3 B+)

1. Flash `stillhem-<version>.img.xz` with Raspberry Pi Imager; boot the Pi.
2. `ping stillhem.local` resolves; open `http://stillhem.local/` → the setup
   wizard appears.
3. Set a password, add a domain (e.g. `example.com`), point a client's DNS at
   the Pi's IP, confirm the domain returns NXDOMAIN and other domains resolve.

## Dev vs. release

`image/config` bakes in a known password and enables SSH for development. These
are shared across every image and MUST be locked down before a buyer-facing
release (tracked in the release-automation sub-project).
```

- [ ] **Step 6: Verify the script's non-build logic with DRY_RUN**

First commit the new files (the clean-tree check needs them committed, and this exercises that path):

```bash
git add image/ && git commit -m "wip: image build scaffolding"
DRY_RUN=1 bash image/build.sh
```
Expected: prints the version (`0.1.0`), clones pi-gen, prints `Pinning pi-gen at ca8aeed…`, writes `image/stage-stillhem/00-install/files/stillhem-src.tar`, appends `STAGE_LIST` to `image/pi-gen/config`, and exits at the `DRY_RUN=1` message with status 0. (The `stage-stillhem` dir it copies is minimal until Task 2 — that's fine; DRY_RUN stops before the build.)

- [ ] **Step 7: Verify the clean-tree guard and tar contents**

```bash
tar tf image/stage-stillhem/00-install/files/stillhem-src.tar | grep -E '^firmware/pyproject.toml$'
echo "dirty" > image/scratch-dirtycheck.txt
bash image/build.sh 2>&1 | grep -q "working tree is dirty" && echo "guard OK"
rm image/scratch-dirtycheck.txt
```
Expected: the tar lists `firmware/pyproject.toml`; the dirty guard prints "guard OK".

- [ ] **Step 8: Amend the scaffolding commit**

```bash
git add image/
git commit --amend -m "feat: image build scaffolding (build.sh, config, README)

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 2: Custom pi-gen stage (`stage-stillhem`)

**Files:**
- Create: `image/stage-stillhem/prerun.sh`
- Create: `image/stage-stillhem/EXPORT_IMAGE`
- Create: `image/stage-stillhem/00-install/00-packages`
- Create: `image/stage-stillhem/00-install/00-run.sh`
- Create: `image/stage-stillhem/00-install/01-run-chroot.sh`

**Interfaces:**
- Consumes: `image/stage-stillhem/00-install/files/stillhem-src.tar` (written by `build.sh` at build time — do NOT commit it; it's git-ignored). The tar unpacks to a repo tree whose `firmware/` holds the installable Python package and `firmware/systemd/stillhem-admin.service` is the unit.
- Produces: a pi-gen stage that, layered on stage2 Lite, yields a rootfs with Unbound + the admin service enabled.

- [ ] **Step 1: Write `image/stage-stillhem/prerun.sh`**

This is the standard pi-gen stage prerun that copies the previous stage's rootfs forward.

```bash
#!/bin/bash -e

if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
```

- [ ] **Step 2: Create the export marker**

Run: `touch image/stage-stillhem/EXPORT_IMAGE`

(An empty `EXPORT_IMAGE` file tells pi-gen to emit the image from this stage. pi-gen also reads a stage-level `prerun.sh` and, for naming, the `EXPORT_IMAGE` file may set `IMG_SUFFIX`/`NOOBS_NAME` — not needed here; `IMG_NAME` from config governs.)

- [ ] **Step 3: Write `image/stage-stillhem/00-install/00-packages`**

```
unbound python3-venv python3-pip avahi-daemon
```

- [ ] **Step 4: Write `image/stage-stillhem/00-install/00-run.sh`** (runs on host, unpacks source into rootfs)

```bash
#!/bin/bash -e

# Unpack the repo snapshot (created by build.sh) into /opt/stillhem in the image.
install -d "${ROOTFS_DIR}/opt/stillhem"
tar -x -f files/stillhem-src.tar -C "${ROOTFS_DIR}/opt/stillhem"
```

- [ ] **Step 5: Write `image/stage-stillhem/00-install/01-run-chroot.sh`** (runs inside the image)

```bash
#!/bin/bash -e

# Build the venv and install the package (mirrors firmware/systemd/install.sh)
python3 -m venv /opt/stillhem/venv
/opt/stillhem/venv/bin/pip install --upgrade pip
/opt/stillhem/venv/bin/pip install -e /opt/stillhem/firmware

# Initialise the database and an empty-blocklist Unbound config so DNS works
# from first boot.
install -d /var/lib/stillhem
/opt/stillhem/venv/bin/python - <<'PY'
from pathlib import Path
from stillhem.db import init_db
from stillhem.blocklist import export_to_file
from stillhem.dns_control import generate_unbound_conf

db = Path("/var/lib/stillhem/stillhem.db")
init_db(db)
blocklist = Path("/var/lib/stillhem/active_blocklist.txt")
export_to_file(db, blocklist)  # empty DB -> empty blocklist file
generate_unbound_conf(
    blocklist,
    Path("/etc/unbound/unbound.conf.d/stillhem.conf"),
    Path("/opt/stillhem/firmware/dns"),
)
PY

# Install and enable services
install -m 644 /opt/stillhem/firmware/systemd/stillhem-admin.service \
    /etc/systemd/system/stillhem-admin.service
systemctl enable stillhem-admin.service
systemctl enable unbound.service
```

- [ ] **Step 6: Make the run scripts executable**

Run: `chmod +x image/stage-stillhem/prerun.sh image/stage-stillhem/00-install/00-run.sh image/stage-stillhem/00-install/01-run-chroot.sh`

- [ ] **Step 7: Syntax-check all shell scripts**

Run: `bash -n image/stage-stillhem/prerun.sh image/stage-stillhem/00-install/00-run.sh image/stage-stillhem/00-install/01-run-chroot.sh`
Expected: no output (all parse).

- [ ] **Step 8: Sanity-check the embedded Python against the real modules**

The chroot script calls `stillhem.blocklist.export_to_file`, `stillhem.db.init_db`, and `stillhem.dns_control.generate_unbound_conf`. Confirm those names/signatures exist so the build won't fail deep inside the chroot:

```bash
cd firmware && .venv-sdd/bin/python - <<'PY'
import inspect
from stillhem import db, blocklist, dns_control
print("init_db", inspect.signature(db.init_db))
print("export_to_file", inspect.signature(blocklist.export_to_file))
print("generate_unbound_conf", inspect.signature(dns_control.generate_unbound_conf))
PY
```
Expected: prints three signatures matching the calls in `01-run-chroot.sh` — `init_db(path)`, `export_to_file(db_path, out_path=...)`, `generate_unbound_conf(blocklist_path, out_path=..., template_dir=...)`. If any differ, fix the chroot script to match before committing.

- [ ] **Step 9: Commit**

```bash
git add image/stage-stillhem/
git commit -m "feat: custom pi-gen stage bakes in unbound + stillhem admin service

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 3: Full build + acceptance documentation

**Files:**
- Modify: `image/README.md` (only if the build surfaces a needed correction)

**Interfaces:**
- Consumes: everything from Tasks 1–2.
- Produces: `image/deploy/stillhem-0.1.0.img.xz` and a verified acceptance run.

This task runs the real build and is the definition of done. It is expensive (full Debian bootstrap, privileged Docker, tens of minutes) and requires Docker Desktop running on the Mac. If executing via subagents, the controller should run this task directly rather than delegating, since it needs the local Docker daemon and real hardware.

- [ ] **Step 1: Ensure a clean committed tree**

Run: `git status --porcelain`
Expected: empty (Tasks 1–2 committed). The build requires this.

- [ ] **Step 2: Run the full build**

Run: `bash image/build.sh`
Expected: completes with `==> Done: image/deploy/stillhem-0.1.0.img.xz (<size>)`. First run is slow; `unbound`, `python3-venv`, `python3-pip`, `avahi-daemon` install without error, and the chroot Python block runs cleanly.

- [ ] **Step 3: Verify the artifact exists and is non-trivial**

```bash
ls -lh image/deploy/stillhem-0.1.0.img.xz
```
Expected: a file of at least a few hundred MB.

- [ ] **Step 4: On-hardware acceptance (manual, developer-run on the Pi 3 B+)**

Flash with Raspberry Pi Imager, boot, then verify per `image/README.md`:
- `ping stillhem.local` resolves
- `http://stillhem.local/` shows the `/setup` wizard
- after setting a password and adding `example.com`, a client using the Pi as DNS gets NXDOMAIN for `example.com` and normal resolution for other domains

Record the outcome. If anything fails, this is where a build/stage fix loops back into Task 2.

- [ ] **Step 5: No code commit unless a fix was needed.** If Step 4 required a correction to a stage script or README, commit it:

```bash
git add image/
git commit -m "fix: <what the acceptance run surfaced>

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** build.sh + config (Task 1) covers the "reproducible build on macOS / versioned .img" requirement; stage-stillhem (Task 2) covers "bake in firmware, Unbound config, systemd service, blocklist presets" (presets ship inside the archived `firmware/blocklists`); Task 3 covers acceptance. dnscrypt-proxy intentionally omitted per spec. AP/captive-portal and release automation are explicitly other sub-projects.
- **Pinned values are concrete:** pi-gen SHA `ca8aeed…`, RELEASE bookworm, version parsed from pyproject. No TBDs.
- **Known soft spot:** the exact behavior of pi-gen's arm64 branch at the pinned SHA (stage/export mechanics, `build-docker.sh` on Apple Silicon) can only be fully confirmed by Task 3's real build. Task 1's `DRY_RUN` and Task 2's `bash -n` de-risk everything short of the actual bootstrap. If the pinned SHA's stage conventions differ (e.g. `SKIP_IMAGES` placement or `STAGE_LIST` absolute-path handling), Task 3 surfaces it and the fix is localized to `build.sh`/stage files.
