#!/usr/bin/env bash
# Build the Stillhem Raspberry Pi image. Run on a Mac with Docker Desktop.
set -euo pipefail

PIGEN_REPO="https://github.com/RPi-Distro/pi-gen.git"

# Target architecture. arm64 is the shipping target (Pi 3 B+ / Zero 2 W and
# newer). armhf builds an ARMv6 image that also boots pre-Pi-3 boards (Pi 1 /
# Zero), which physically cannot run a 64-bit kernel — useful for testing on
# older hardware. Override with: PIGEN_ARCH=armhf bash image/build.sh
PIGEN_ARCH="${PIGEN_ARCH:-arm64}"

# The pi-gen branch must match RELEASE in image/config: each branch bootstraps
# one Debian release (stage0/prerun.sh only *warns* on a mismatch, then the
# build dies later with NO_PUBKEY because the rootfs keyring is for the other
# release). Branch also determines 32- vs 64-bit; there is no arch config flag.
case "$PIGEN_ARCH" in
  arm64)
    PIGEN_BRANCH="bookworm-arm64"
    PIGEN_COMMIT="d7a31c6aa09f4b867902c51da2b45807c0a1709e"
    ;;
  armhf)
    PIGEN_BRANCH="bookworm"
    PIGEN_COMMIT="4be6bbd0933c900517cb309d4f4f44267d2c2cac"
    ;;
  *)
    echo "ERROR: PIGEN_ARCH must be 'arm64' or 'armhf' (got '$PIGEN_ARCH')." >&2
    exit 1
    ;;
esac
PIGEN_RELEASE="bookworm"  # must equal RELEASE in image/config

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

# 2b. Branch/release agreement. pi-gen only *warns* on a mismatch and then dies
# ~20 minutes later with an opaque NO_PUBKEY error, so fail loudly up front.
CONFIG_RELEASE="$(grep -E '^RELEASE=' "$IMAGE_DIR/config" | head -1 | sed -E 's/RELEASE="?([^"]*)"?/\1/')"
if [ "$CONFIG_RELEASE" != "$PIGEN_RELEASE" ]; then
  echo "ERROR: image/config RELEASE='$CONFIG_RELEASE' but pi-gen branch" >&2
  echo "       '$PIGEN_BRANCH' bootstraps '$PIGEN_RELEASE'." >&2
  echo "       Use the pi-gen branch matching the release (e.g. bookworm-arm64" >&2
  echo "       for bookworm, arm64 for trixie), or change RELEASE to match." >&2
  exit 1
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
# pi-gen's STAGE_LIST is space-delimited, so a repo path containing a space
# cannot be expressed in it. Fail early and clearly rather than mid-build.
case "$PIGEN_DIR" in
  *" "*)
    echo "ERROR: repo path contains a space ($PIGEN_DIR)." >&2
    echo "       pi-gen's STAGE_LIST cannot handle spaces; move the repo to a space-free path." >&2
    exit 1
    ;;
esac
cp "$IMAGE_DIR/config" "$PIGEN_DIR/config"
rm -rf "$PIGEN_DIR/stage-stillhem"
cp -R "$STAGE_DIR" "$PIGEN_DIR/stage-stillhem"
# Suppress stage2's own image export so only the Stillhem image is produced
touch "$PIGEN_DIR/stage2/SKIP_IMAGES"
# Select stages: Lite base + our stage
# Stage names are relative to the pi-gen root: the build runs as `cd /pi-gen`
# inside the container (the dir is baked into the image, not bind-mounted), so a
# host absolute path here would not resolve.
echo 'STAGE_LIST="stage0 stage1 stage2 stage-stillhem"' >> "$PIGEN_DIR/config"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "==> DRY_RUN=1: prepared pi-gen at $PIGEN_DIR, skipping build-docker.sh"
  exit 0
fi

# 6. Build
echo "==> Running pi-gen build-docker.sh (this takes a while)"
( cd "$PIGEN_DIR" && ./build-docker.sh )

# 7. Collect artifact
mkdir -p "$DEPLOY_DIR"
shopt -s nullglob
built_imgs=("$PIGEN_DIR"/deploy/*.img.xz)
shopt -u nullglob
if [ "${#built_imgs[@]}" -eq 0 ]; then
  echo "ERROR: build finished but produced no .img.xz in $PIGEN_DIR/deploy" >&2
  exit 1
fi
# Newest by mtime, in case a previous build left an older artifact behind.
SRC_IMG="$(ls -t "${built_imgs[@]}" | head -1)"
# Arch in the name so a 32-bit test image can't be mistaken for (or overwrite)
# the 64-bit shipping image.
DEST_IMG="$DEPLOY_DIR/stillhem-$VERSION-$PIGEN_ARCH.img.xz"
mv "$SRC_IMG" "$DEST_IMG"
echo "==> Done: $DEST_IMG ($(du -h "$DEST_IMG" | cut -f1))"
