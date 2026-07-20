# Stillhem image build (pi-gen) — design

**Parent context:** `HANDOFF.md` hard requirement #1 ("Reproducible build on macOS"). This is
sub-project 2 of 5 (after the rebrand, before the captive-portal wizard). Deliverable: a **locally
buildable** flashable `.img`, produced on the developer's Mac. Release automation (GitHub Actions)
is sub-project 5; the first-boot AP + captive portal is sub-project 3.

## Goal

From a clean checkout on a Mac with Docker Desktop, run one script and get a versioned, flashable
`stillhem-<version>.img.xz` that boots on a Raspberry Pi 3 B+ straight into the existing admin
service (Unbound resolver + FastAPI `/setup` wizard), with no manual `install.sh` step.

## Distribution model (why this shape)

The build host (Mac + Docker) and the run host (buyer's Pi) are fully decoupled. **Only the
developer builds.** The buyer downloads the finished `.img`, writes it with Raspberry Pi Imager, and
boots — no Docker, no terminal. The `.img` is therefore self-contained (Unbound, the Python package,
its venv, and the systemd unit are all baked into the root filesystem) and generic across any
Pi 3 B+ — nothing is pre-seeded per device. That last point is what forces first-boot setup
(Wi-Fi + admin password) into sub-project 3 rather than the image.

## Target hardware

Raspberry Pi 3 B+ (the board the developer has on hand). It is 64-bit capable, so the image is
built from **Raspberry Pi OS Lite 64-bit** per the handoff. One arm64 image also boots Pi 4/5, but
3 B+ is the only supported/tested target for this sub-project.

## Deviation from the handoff: no dnscrypt-proxy

The handoff says "bake in Unbound + dnscrypt-proxy config." The repo no longer uses dnscrypt-proxy —
commit `578e08a` (2026-05-19) changed Unbound to forward directly to 1.1.1.1 / 9.9.9.9
(`firmware/dns/unbound.conf.j2` `forward-zone`). We bake **only what the repo actually uses**:
Unbound with direct upstream forwarding. dnscrypt-proxy is intentionally omitted. (If encrypted
upstream is wanted later, it's a separate, deliberate change to the DNS template, not image plumbing.)

## Build architecture

Everything lives in a new top-level `image/` directory. No pi-gen fork — the build script clones
upstream pi-gen pinned to a specific commit into a git-ignored working dir.

```
image/
├── build.sh              # entrypoint, run on the Mac
├── config                # pi-gen config, sourced by build-docker.sh
├── .gitignore            # ignores pi-gen/ and deploy/
└── stage-stillhem/       # custom pi-gen stage, appended after stage2
    ├── prerun.sh         # standard pi-gen stage prerun (copy prev rootfs)
    ├── EXPORT_IMAGE      # this stage exports the image
    └── 00-install/
        ├── 00-packages       # unbound python3-venv python3-pip avahi-daemon
        ├── 00-run.sh         # (host) unpack repo snapshot into rootfs /opt/stillhem
        └── 01-run-chroot.sh  # (chroot) build venv, pip install, enable services, set hostname
```

### `build.sh` responsibilities (in order)

1. Resolve `VERSION` by reading `version` from `firmware/pyproject.toml`.
2. Ensure a clean git tree (`git status --porcelain` empty) — the image must correspond to a real
   commit. Abort with a clear message otherwise. (Override via `ALLOW_DIRTY=1` for local iteration.)
3. Clone pi-gen **arm64 branch at a pinned commit** into `image/pi-gen/` if absent (64-bit images
   require the `arm64` branch; there is no arch config variable). The pinned SHA lives in `build.sh`
   as a constant.
4. Snapshot the repo into the stage's files via `git archive HEAD` →
   `stage-stillhem/00-install/files/stillhem-src.tar` (clean tree only; no scratch files, no
   `.venv-sdd`). This is what lands at `/opt/stillhem`.
5. Copy `config` and `stage-stillhem/` into `image/pi-gen/`.
6. `cd image/pi-gen && ./build-docker.sh` (the arm64 branch's supported Docker entrypoint; the
   branch itself selects 64-bit, so no arch flag is needed. `build-docker.sh` runs the privileged
   container, loop devices, and binfmt itself — the supported macOS path).
7. On success, move `image/pi-gen/deploy/*.img.xz` to `image/deploy/stillhem-<version>.img.xz` and
   print the path + size.

`PRESERVE_CONTAINER=1` and `CONTINUE=1` are passed through from the environment for incremental
iteration.

### `config` (key pi-gen variables)

```
IMG_NAME="stillhem"
RELEASE="bookworm"          # pinned; not defaulting to trixie mid-development
DEPLOY_COMPRESSION="xz"
COMPRESSION_LEVEL="6"
TARGET_HOSTNAME="stillhem"
FIRST_USER_NAME="stillhem"
FIRST_USER_PASS="stillhem"  # DEV ONLY — see hardening handoff below
DISABLE_FIRST_BOOT_USER_RENAME="1"
ENABLE_SSH="1"              # DEV ONLY — see hardening handoff below
LOCALE_DEFAULT="en_US.UTF-8"
KEYBOARD_KEYMAP="se"
TIMEZONE_DEFAULT="Europe/Stockholm"
WPA_COUNTRY="SE"
STAGE_LIST="stage0 stage1 stage2 ${STILLHEM_STAGE_DIR}"
```

Stage2 keeps its own `EXPORT_IMAGE`, which would emit a second (plain Lite) image; we suppress it by
dropping a `SKIP_IMAGES` file into the stage2 copy so only the Stillhem image is produced. Desktop
stages 3–5 are simply not in `STAGE_LIST`, so Lite is the base.

### What the custom stage bakes in

- **Packages** (`00-packages`): `unbound`, `python3-venv`, `python3-pip`, `avahi-daemon`.
  `avahi-daemon` gives `stillhem.local` mDNS from first boot — cheap, and the handoff wants it as a
  post-setup convenience. **No dnscrypt-proxy.**
- **Source** (`00-run.sh`, host): unpack `files/stillhem-src.tar` into the rootfs at `/opt/stillhem`.
- **Install** (`01-run-chroot.sh`, chroot), mirroring `firmware/systemd/install.sh` but inside the
  image:
  - `python3 -m venv /opt/stillhem/venv`
  - `/opt/stillhem/venv/bin/pip install -e /opt/stillhem/firmware`
  - initialise the DB at `/var/lib/stillhem/stillhem.db` via `stillhem.db.init_db`
  - render an Unbound config with an empty blocklist to
    `/etc/unbound/unbound.conf.d/stillhem.conf` so DNS resolves from first boot
  - install and `systemctl enable` the `stillhem-admin.service` unit and `unbound`
  - hostname is handled by `TARGET_HOSTNAME`; no extra step needed

Net effect: a flashed card boots with Unbound resolving, the admin UI reachable, and the existing
`/setup` password wizard waiting — the same end state `install.sh` produces on a running Pi, minus
the manual step.

## Dev vs. release posture (hardening handoff)

The `FIRST_USER_PASS="stillhem"` and `ENABLE_SSH="1"` choices are **developer conveniences** for
iterating on the 3 B+. Because the same `.img` ships to every buyer, a baked-in password would be a
credential shared across all devices. Sub-project 5 (release) must, before any buyer-facing image:
lock the first user / remove the baked password, and set SSH to off or key-only. Recorded here so it
is not forgotten; out of scope for this sub-project.

## Out of scope (later sub-projects)

- Wi-Fi AP + captive-portal first-boot wizard → sub-project 3.
- GitHub Actions release automation → sub-project 5 (this sub-project is local-build only).
- 48h commitment lock → deferred per handoff.

## Testing / acceptance

No unit tests — this is build plumbing. Acceptance is a manual end-to-end run, documented in
`image/README.md`:

1. `bash image/build.sh` on the Mac completes and emits `image/deploy/stillhem-<version>.img.xz`.
2. Flash to an SD card with Raspberry Pi Imager; boot the Pi 3 B+.
3. `ping stillhem.local` resolves; the admin UI loads at `http://stillhem.local/` and shows the
   `/setup` wizard.
4. Set a password, add a domain (e.g. `example.com`), point a client's DNS at the Pi, confirm the
   domain returns NXDOMAIN and a non-blocked domain still resolves.

A green build plus a booting image that serves the wizard is the definition of done; steps 3–4 are
the developer's manual confirmation on real hardware.

## Risks / open points

- **pi-gen arm64 branch structure at the pinned commit.** Branch layout and `build-docker.sh`
  behavior can drift. Mitigation: pin a specific SHA; the first implementation task is to get a bare
  upstream build running before adding the custom stage, so any drift surfaces immediately.
- **Build time / disk.** A pi-gen build pulls a full Debian bootstrap and needs several GB. First
  build is slow; `PRESERVE_CONTAINER=1` makes iteration cheaper. Documented in `image/README.md`.
