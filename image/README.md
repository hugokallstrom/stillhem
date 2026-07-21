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

Output: `image/deploy/stillhem-<version>-<arch>.img.xz`. The build refuses to run
on a dirty git tree (the image must map to a committed state); use
`ALLOW_DIRTY=1` to override during local iteration. `DRY_RUN=1` prepares pi-gen
without building.

### Architecture

`arm64` (default) is the shipping target — Pi 3 B+, Zero 2 W, Pi 4/5.

```bash
PIGEN_ARCH=armhf bash image/build.sh
```

builds a 32-bit ARMv6 image that *also* boots pre-Pi-3 boards (Pi 1, Zero),
which cannot run a 64-bit kernel at all. Note those older boards have no
onboard Wi-Fi, so the first-boot AP setup wizard does not apply to them — they
boot straight to normal mode over Ethernet.

The pi-gen branch is chosen per arch and must match `RELEASE` in `image/config`;
`build.sh` fails up front if they disagree.
`PRESERVE_CONTAINER=1` keeps the pi-gen container between runs for faster
iteration.

## Acceptance (on a Pi 3 B+)

1. Flash `stillhem-<version>-<arch>.img.xz` with Raspberry Pi Imager; boot the Pi.
2. `ping stillhem.local` resolves; open `http://stillhem.local/` → the setup
   wizard appears.
3. Set a password, add a domain (e.g. `example.com`), point a client's DNS at
   the Pi's IP, confirm the domain returns NXDOMAIN and other domains resolve.

## Dev vs. release

`image/config` bakes in a known password and enables SSH for development. These
are shared across every image and MUST be locked down before a buyer-facing
release (tracked in the release-automation sub-project).
