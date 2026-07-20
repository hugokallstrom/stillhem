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
