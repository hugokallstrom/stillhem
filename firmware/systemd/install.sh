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

echo "==> Installing network-mode selector + captive DNS..."
ln -sf "$INSTALL_DIR/systemd/stillhem-netmode.service" /etc/systemd/system/stillhem-netmode.service
install -Dm 644 "$INSTALL_DIR/network/dnsmasq-shared.d/stillhem-captive.conf" \
    /etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf
systemctl enable stillhem-netmode

echo "==> Done. Admin UI running at http://$(hostname -I | awk '{print $1}')"
echo "    Set your router's DNS server to that IP."
