#!/bin/bash -e

# Build the venv and install the package (mirrors firmware/systemd/install.sh)
python3 -m venv /opt/stillhem/venv
/opt/stillhem/venv/bin/pip install --upgrade pip
/opt/stillhem/venv/bin/pip install -e /opt/stillhem/firmware

# Initialise the database and the Unbound config so DNS blocking is live from
# first boot. init_db seeds the default social+video blocklist enabled, so the
# exported file is non-empty and the box blocks out of the box.
install -d /var/lib/stillhem
/opt/stillhem/venv/bin/python - <<'PY'
from pathlib import Path
from stillhem.db import init_db
from stillhem.blocklist import export_to_file
from stillhem.dns_control import generate_unbound_conf

db = Path("/var/lib/stillhem/stillhem.db")
init_db(db)
blocklist = Path("/var/lib/stillhem/active_blocklist.txt")
export_to_file(db, blocklist)  # seeded DB -> default social+video blocklist
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
# stillhem.local is the only advertised way in, so don't rely on the package's
# install-time preset having enabled avahi in the chroot.
systemctl enable avahi-daemon.service

# Reconcile timer: recomputes the effective blocklist from schedules every minute
install -m 644 /opt/stillhem/firmware/systemd/stillhem-reconcile.service \
    /etc/systemd/system/stillhem-reconcile.service
install -m 644 /opt/stillhem/firmware/systemd/stillhem-reconcile.timer \
    /etc/systemd/system/stillhem-reconcile.timer
systemctl enable stillhem-reconcile.timer

# Network-mode selector (AP setup vs. normal) + captive DNS for AP mode
install -m 644 /opt/stillhem/firmware/systemd/stillhem-netmode.service \
    /etc/systemd/system/stillhem-netmode.service
install -Dm 644 /opt/stillhem/firmware/network/dnsmasq-shared.d/stillhem-captive.conf \
    /etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf
systemctl enable stillhem-netmode.service
