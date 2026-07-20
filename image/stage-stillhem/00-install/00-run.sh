#!/bin/bash -e

# Unpack the repo snapshot (created by build.sh) into /opt/stillhem in the image.
install -d "${ROOTFS_DIR}/opt/stillhem"
tar -x -f files/stillhem-src.tar -C "${ROOTFS_DIR}/opt/stillhem"
