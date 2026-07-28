# stillhem

Blocks social media on every screen in your house. A small device that plugs into your router — no apps, no willpower, no subscription.

DNS-level blocking enforced at the network. Every device in the house is covered without installing anything. The admin interface is password-protected — forgetting the password means re-flashing the SD card.

Sold in Sweden as a finished product. See [stillhem.com](https://stillhem.com).

## How it works

The Pi runs Unbound as a DNS resolver. Point your router's DNS at the Pi's IP and the blocklist takes effect on every connected device. Blocked domains return NXDOMAIN — no browser extension, no app to uninstall, no toggle to click.

On first boot the device serves a setup wizard where you pick a preset and set the admin password. After that, changes require knowing that password.

## Blocklist presets

| Preset | What it blocks |
|---|---|
| `social_only` | Social media |
| `social_news` | Social media + news |
| `hard_mode` | Social, news, and entertainment |

Custom domain lists are also supported from the admin UI.

## Building the image

Requires Docker. On Linux/x86 you can also build armhf images; arm64 is the default.

```bash
bash image/build.sh
```

The image is also built automatically on every push to `main` via GitHub Actions (arm64 release). Manual `workflow_dispatch` runs let you choose arch and variant.

Flash the resulting `.img.xz` to an SD card with Raspberry Pi Imager or `dd`.

## Development

**Requirements:** Python 3.11+, `unbound`

```bash
cd firmware
pip install -e ".[dev]"
pytest
```

## License

Copyright (c) 2026 Hugo Linder. Licensed under AGPLv3 — see [LICENSE](LICENSE).
