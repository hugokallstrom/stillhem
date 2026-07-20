# First-boot AP + captive-portal setup wizard — design

**Parent context:** `HANDOFF.md` hard requirement #2 ("Non-technical first-boot = setup Wi-Fi AP
(captive portal)"). Sub-project 3 of 5 (after the image build, before the router-DNS UX polish and
release automation). This is the core UX of the product for a non-technical buyer.

## Goal

On first boot with no saved home Wi-Fi, the device broadcasts its own Wi-Fi AP. The buyer connects
a phone; a captive portal auto-opens a 3-step wizard (home Wi-Fi + password → blocklist preset →
admin password). The device saves the config, switches from AP to joining the home network, and
reboots into normal operation — no terminal, no IP addresses, no `.local` dependency.

## Decisions taken (from brainstorming)

- **Network stack: NetworkManager / `nmcli`** — the bookworm default already in the image.
  `nmcli` hotspot with `ipv4.method shared` provides DHCP + a DNS forwarder to connecting phones for
  free, persists the home-Wi-Fi profile, and handles the client-mode switch. This **supersedes the
  handoff's "hostapd + dnsmasq" suggestion**, which was the pre-bookworm approach.
- **Wizard lives in the existing admin app, two modes** — onboarding routes and captive-portal
  responders are added to the current FastAPI app; a boot-time script selects setup-mode vs
  normal-mode. Reuses the existing password (`/setup`) and preset-import logic. No second service.

## Hardware constraint that shapes the design

The Pi 3 B+ has a **single Wi-Fi radio**. It cannot be an AP and scan for/join other networks at
the same time. So the flow is strictly **sequential**, exactly as the handoff describes:

1. At boot (before the AP goes up), scan for nearby networks and cache the SSID list.
2. Bring up the AP; serve the wizard from the cached list.
3. On completion, tear down the AP, join the home network, reboot.

No AP+STA concurrency is required or attempted.

## Architecture — three layers

### Layer 1: network-mode module (`stillhem.netmode`)

A Python module wrapping `nmcli` via `subprocess`, mirroring the testable pattern of the existing
`stillhem.dns_control` (functions shell out; tests mock `subprocess`). Responsibilities:

- `home_wifi_configured() -> bool` — is there a saved NetworkManager wifi **client** profile (any
  wifi connection profile other than the `Stillhem Setup` AP)? This is the source of truth for
  which mode to boot into.
- `scan_networks() -> list[dict]` — `nmcli -t -f SSID,SIGNAL,SECURITY device wifi list`, deduped,
  sorted by signal, empty SSIDs dropped. Cached to `/var/lib/stillhem/wifi_scan.json`.
- `start_ap()` / `stop_ap()` — create/activate and tear down the `Stillhem Setup` hotspot
  (`nmcli ... wifi.mode ap wifi.ssid "Stillhem Setup" ipv4.method shared`, open network — a setup
  AP needs no password, and WPA on the shared setup network adds a step with no security benefit
  since it carries only LAN-local setup traffic).
- `save_home_wifi(ssid, psk)` — create (but do not activate) an NM client profile for the home
  network.
- No captive-portal or web concerns live here — pure network state.

### Layer 2: boot-time mode selector (`stillhem-netmode.service`)

A systemd **oneshot**, ordered `After=NetworkManager.service` and `Before=stillhem-admin.service`,
running `python -m stillhem.netmode boot`:

- If `home_wifi_configured()` → write `/var/lib/stillhem/mode` = `normal` and exit. NetworkManager
  auto-connects to the home network; the admin service then serves normally.
- Else → `scan_networks()` (cache it), `start_ap()`, install the captive dnsmasq snippet, write
  `/var/lib/stillhem/mode` = `setup`, exit.

**Deliberate non-fallback:** once a home profile exists, the device stays in normal mode even if the
home network is temporarily unreachable (router reboot, etc.). It never silently drops back to AP
mode — that would be alarming and insecure. Re-entering setup is an explicit reset, consistent with
the product's "forgetting the admin password means re-flashing the SD card" philosophy. (A physical
reset path is out of scope here; noted for a future sub-project.)

### Layer 3: the admin app in two modes

The existing FastAPI app reads `/var/lib/stillhem/mode` at startup into `app.state.setup_mode`
(defaulting to `setup` if the file is missing or unreadable — a fresh, unconfigured device should
show the wizard, never an unconfigured dashboard). A small launcher (`python -m stillhem.launch`,
the new `stillhem-admin.service` ExecStart) runs uvicorn on **port 80** in both modes (the appliance
image has no nginx — the pre-existing 8080 was for the install-on-existing-Pi path; the image
standardises on 80, matching the README). Updating that unit's `ExecStart` and port is part of this
sub-project.

- **Setup mode** (`setup_mode = True`):
  - **Captive-portal responders** — a router that answers the OS connectivity-probe URLs so the
    phone auto-opens the wizard: Apple (`captive.apple.com/hotspot-detect.html`), Android
    (`/generate_204` on any host), Microsoft (`www.msftconnecttest.com/connecttest.txt`). Because
    the dnsmasq snippet resolves **every** domain to the Pi's AP IP, all probes reach our server; a
    catch-all route returns `302` to the wizard, triggering the "Sign in to network" popup.
  - **Wizard routes** — the 3 steps below. Everything else redirects to the current wizard step.
- **Normal mode** (`setup_mode = False`): captive-portal + wizard routes are inert; the existing
  dashboard / login / blocklist flow serves as today.

### The captive dnsmasq snippet

`/etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf` containing `address=/#/10.42.0.1`
(NM's shared mode uses the 10.42.0.0/24 subnet with the Pi at `10.42.0.1`). This makes every DNS
query during AP mode resolve to the Pi, which is what routes the probes and the buyer's browser to
the wizard. It only has effect while the shared-mode AP is active.

### How the new system files reach the image

The repo snapshot (`git archive HEAD`) already carries every new *repo* file into `/opt/stillhem`
automatically, so new Python modules and templates need no image change. The new files that must
land in **system** paths — the `stillhem-netmode.service` unit, the updated `stillhem-admin.service`,
and the dnsmasq snippet at `/etc/NetworkManager/dnsmasq-shared.d/stillhem-captive.conf` — are
installed by extending the sub-project-2 chroot install script
(`image/stage-stillhem/00-install/01-run-chroot.sh`) to copy them into place and `systemctl enable`
the netmode oneshot. `network-manager` is already the bookworm default, so no extra package is
needed; the stage's `00-packages` is unchanged.

## The wizard (3 steps, matching the handoff)

Reachable at any URL while in setup mode (captive redirect sends the phone here). State is persisted
as each step completes, so a dropped connection resumes at the right step:

1. **Home Wi-Fi** (`GET/POST /wizard/wifi`) — shows the cached scan list (pick an SSID) plus a
   password field. POST calls `save_home_wifi(ssid, psk)` (creates the inactive NM profile), then
   advances. A "network not listed" manual-SSID entry is included (hidden networks / weak signal).
2. **Blocklist preset** (`GET/POST /wizard/preset`) — radio choice of `social_only` / `social_news`
   / `hard_mode` (the existing presets). POST calls the existing `import_preset` into the DB.
3. **Admin password** (`GET/POST /wizard/password`) — reuses the existing password rules
   (`set_password`, min length, confirm match — the same validation as today's `/setup`). POST sets
   the password, then shows a **completion screen**: "Setup complete. The device will restart and
   join <home-SSID>." and triggers a deferred reboot.

On reboot, `home_wifi_configured()` is now true → `mode = normal` → the device joins the home
network and serves the dashboard.

### Post-setup reachability

After setup the admin UI is on the home network. `avahi-daemon` (baked in sub-project 2) advertises
`stillhem.local` as the friendly way back. Per the handoff, first-time setup does **not** depend on
mDNS — it happens entirely over the captive AP. The completion screen names `stillhem.local` and
notes the router-DNS step (detailed per-router instructions are sub-project 4).

## Scope boundaries

- **Router DNS instructions / DHCP auto-advertise** → sub-project 4. Here the completion screen only
  states the Pi's role and points forward; no per-router content.
- **Dev-vs-release hardening** (SSH, baked password from sub-project 2) → sub-project 5.
- **Physical factory-reset path** → future; not in this sub-project.
- **48h commitment lock** → deferred per handoff.

## Testing / acceptance

Layered, so most logic is verified off-hardware and only the real AP needs the Pi:

- **`stillhem.netmode`** — unit tests mocking `subprocess`, asserting the exact `nmcli` argv for
  scan/AP-up/AP-down/save-home and the parse of `nmcli -t` output (same style as
  `test_dns_control.py`).
- **Wizard + captive routes** — FastAPI `TestClient` tests: setup-mode app redirects probe URLs
  with 302; each wizard step renders and persists (wifi profile call mocked, preset import and
  password set assert real DB state); normal-mode app leaves probe/wizard routes inert and serves
  the dashboard.
- **On-hardware acceptance** (developer, Pi 3 B+, folded into the image build): flash → boot with no
  home Wi-Fi → phone sees `Stillhem Setup` → captive wizard auto-opens → complete all 3 steps →
  device reboots, joins home Wi-Fi, `stillhem.local` serves the dashboard, blocking works.

## Risks / open points

- **Captive-portal auto-open is inherently flaky across phone OSes/versions.** The redirect trick
  works for the majority but not universally; the fallback is the buyer opening any URL in a browser
  while on the AP, which the catch-all still routes to the wizard. The completion/AP screens should
  mention this fallback.
- **`nmcli` argument/exact-output drift** across NetworkManager versions. Mitigated by pinning the
  bookworm image and mocking the exact argv in tests; the on-hardware run is the real confirmation.
- **Single-radio scan timing.** The pre-AP scan is a snapshot; if the buyer's network wasn't
  broadcasting at boot it won't be listed — the manual-SSID entry in step 1 covers that.
