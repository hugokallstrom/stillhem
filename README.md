# stillhem

A Raspberry Pi appliance that makes a chosen set of websites unreachable for every device on your home network. DNS-level blocking, set once, enforced always. The admin interface is password-protected — forgetting the password means re-flashing the SD card.

Sold in Sweden first as a finished product. Aimed at adults who have already opted out of smartphone slop and want the same for their home network.

## How it works

The Pi runs Unbound as a DNS resolver. You point your router's DNS at the Pi's IP. Any domain on the blocklist returns NXDOMAIN — no browser extension, no app to uninstall, no toggle to click.

On first boot the device serves a setup wizard where you choose a preset and set the admin password. After that, changes require knowing that password.

## Blocklist presets

| Preset | What it blocks |
|---|---|
| `social_only` | Social media |
| `social_news` | Social media + news |
| `hard_mode` | Social, news, and entertainment |

Custom domain lists are also supported from the admin UI.

## Development

**Requirements:** Python 3.11+, `unbound`, `dnscrypt-proxy`

```bash
cd firmware
pip install -e ".[dev]"
pytest
```

Integration tests that require a running Unbound instance are marked and skipped by default:

```bash
pytest -m "not integration"
```

## Installing on a Pi

Clone to `/opt/stillhem` and run as root:

```bash
bash /opt/stillhem/firmware/systemd/install.sh
```

This installs the Python package, initialises the SQLite database, and starts the `stillhem-admin` systemd service on port 80.

Set your router's primary DNS server to the Pi's IP. The admin UI is then available at `http://<pi-ip>/`.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `STILLHEM_DB_PATH` | `/var/lib/stillhem/stillhem.db` | SQLite database |
| `STILLHEM_BLOCKLIST_PATH` | `/var/lib/stillhem/active_blocklist.txt` | Active blocklist file |
| `STILLHEM_UNBOUND_CONF` | `/etc/unbound/unbound.conf.d/stillhem.conf` | Generated Unbound config |
| `STILLHEM_DNS_TEMPLATE_DIR` | `firmware/dns` | Jinja2 template directory |
| `STILLHEM_PRESET_DIR` | `firmware/blocklists` | Preset list directory |

## License

Copyright (c) 2026 Hugo Linder. Licensed under AGPLv3 — see [LICENSE](LICENSE).
