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
