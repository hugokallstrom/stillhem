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

# Network-mode selector (AP setup vs. normal) + captive DNS for AP mode
install -m 644 /opt/stillhem/firmware/systemd/stillhem-netmode.service \
    /etc/systemd/system/stillhem-netmode.service
install -Dm 644 /opt/stillhem/firmware/network/dnsmasq-shared.d/stillhem-captive.conf \
    /etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf
systemctl enable stillhem-netmode.service
