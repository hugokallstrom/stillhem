#!/bin/bash -e

# Console behaviour for a headless appliance.
#
# Stillhem has no console UI: the product surface is the web admin at
# http://stillhem.local/. But a Pi on a desk still gets an HDMI cable plugged
# into it when something looks wrong, and what you want at that moment is the
# device's IP address — not a login prompt for a password you never chose and
# that is written in a public git repo anyway.
#
# So tty1 auto-logs in and prints a status banner. This does not weaken the
# security boundary described in image/config: SSH is off, so the console is
# reachable only with physical access, and anyone holding the board can read the
# SD card directly. The admin boundary is the web UI password, which the buyer
# sets in the first-boot wizard and which this does not touch.

FIRST_USER_NAME="${FIRST_USER_NAME:-stillhem}"

# --- Auto-login on tty1 ---------------------------------------------------
install -d "${ROOTFS_DIR}/etc/systemd/system/getty@tty1.service.d"
cat > "${ROOTFS_DIR}/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<EOF
[Service]
# Clearing ExecStart first is required: drop-ins append to a list, and
# ExecStart= (empty) resets it so the replacement below is the only entry.
ExecStart=
ExecStart=-/sbin/agetty --autologin ${FIRST_USER_NAME} --noclear %I \$TERM
EOF

# --- Pre-login banner -----------------------------------------------------
# agetty expands these escapes when it paints the prompt, so the address is
# current at display time rather than baked in at build time.
cat > "${ROOTFS_DIR}/etc/issue" <<'EOF'
Stillhem \n (\l)

  Admin:    http://stillhem.local/
  Wired:    \4{eth0}
  Wi-Fi:    \4{wlan0}

EOF

# --- Post-login banner ----------------------------------------------------
# Printed on the auto-login shell, where /etc/issue may be skipped. Unlike
# /etc/issue this can report service health, which is the other thing you came
# to the console to find out.
cat > "${ROOTFS_DIR}/etc/profile.d/stillhem-banner.sh" <<'EOF'
# Status banner for the console. Interactive shells only, so scp/rsync and
# other non-interactive sessions are not corrupted by the output.
case $- in *i*) ;; *) return ;; esac

_stillhem_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
printf '\n  Stillhem — admin at http://stillhem.local/'
[ -n "$_stillhem_ip" ] && printf ' (http://%s/)' "$_stillhem_ip"
printf '\n\n'
for _stillhem_unit in stillhem-admin unbound stillhem-netmode; do
    printf '    %-18s %s\n' "$_stillhem_unit" \
        "$(systemctl is-active "$_stillhem_unit" 2>/dev/null || echo unknown)"
done
printf '\n  Logs: journalctl -u stillhem-admin -b\n\n'
unset _stillhem_ip _stillhem_unit
EOF
chmod 644 "${ROOTFS_DIR}/etc/profile.d/stillhem-banner.sh"
