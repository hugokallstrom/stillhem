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

builds a 32-bit ARMv6 image that *also* boots pre-Pi-3 boards (Pi 1, Pi B+,
Zero), which cannot run a 64-bit kernel at all. Those older boards have no
onboard Wi-Fi, so there is no setup AP to join: the first-boot wizard runs over
Ethernet at `http://stillhem.local/` and skips the Wi-Fi step.

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

## Acceptance (Ethernet-only board, e.g. Pi B+)

Use the `armhf` image — the B+ is ARMv6 and cannot boot the arm64 one at all.

1. Flash, plug in Ethernet, power on. First boot takes a few minutes on a B+.
2. From another machine on the same LAN: `ping stillhem.local`.
3. Open `http://stillhem.local/` → the wizard appears **at the preset step**;
   there is no Wi-Fi step because the board has no radio.
4. Choose a preset, set the admin password, finish. The box reboots and comes
   back at `http://stillhem.local/`.

If `stillhem.local` does not resolve, plug in HDMI: tty1 auto-logs in and prints
the device's IP and the status of `stillhem-admin`, `unbound`, and
`stillhem-netmode`. Reach the admin UI by IP and read logs with
`journalctl -u stillhem-admin -b`.

## Console access

There is no console login prompt: tty1 auto-logs in as `stillhem` and shows a
status banner (`image/stage-stillhem/01-console`). The reasoning is in that
script — briefly, SSH is off in release images, so the console is reachable only
with physical access, and whoever holds the board can read the SD card anyway.
The real admin boundary is the web UI password set in the wizard.

## Dev vs. release

Release images ship hardened: SSH off, and the OS account password in
`image/config` is unreachable remotely. `PIGEN_VARIANT=dev` re-enables SSH with
that known password for debugging; dev artifacts are suffixed `-dev` and must
never be published.
