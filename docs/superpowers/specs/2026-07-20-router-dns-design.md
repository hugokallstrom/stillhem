# Router-DNS step UX — design

**Parent context:** `HANDOFF.md` hard requirement #3 ("Router DNS step — make it as painless as
possible"). Sub-project 4 of 5 (after the setup wizard, before release automation). The product only
blocks once the router points the LAN's DNS at the Pi; for a non-technical buyer this is the hardest
step, and the handoff asks us to (a) end with clear per-brand instructions showing the Pi's IP, and
(b) investigate advertising DNS automatically via DHCP and flag tradeoffs.

## The DHCP self-advertisement investigation (the handoff's "flag tradeoffs")

There is **no safe fully-automatic way** to point a home LAN's DNS at the Pi without either
reconfiguring the router or having the Pi take over DHCP:

- **Reconfigure the router's DNS** (manual): the reliable, safe path — but per-brand and manual.
- **Pi takes over DHCP** (advertise itself as DNS via DHCP option 6): two DHCP servers on one LAN
  answer requests in a non-deterministic race, so doing it correctly requires *disabling the
  router's DHCP* and making the Pi the **sole** DHCP server. That makes the Pi a single point of
  failure for the entire network — if it is off, unplugged, or re-flashing, no device on the LAN
  gets an address at all. For an appliance a non-technical person owns, that is a worse failure mode
  than the manual step it replaces.

**Decision (recorded non-choice):** ship the manual router-DNS step made as painless as possible;
do **not** build or enable DHCP takeover. It is documented here as an advanced opt-in for a possible
future sub-project, with the single-point-of-failure and DHCP-race tradeoffs stated, so the choice
is deliberate and not revisited from scratch later.

Consequently this sub-project makes the manual step gentle: clear per-brand instructions, the Pi's
IP shown for them, and a **loop-closing "is it working?" indicator** so the buyer can tell the change
took effect (they otherwise have no feedback).

## What we build

### 1. Pi LAN-IP detection (`stillhem.netinfo.primary_ip`)

A helper that returns the Pi's primary LAN IPv4 using the standard UDP-socket trick (open a datagram
socket "connected" to a public IP and read the local socket name — no packets are sent), falling
back to `127.0.0.1` on error. Replaces the `hostname -I | awk` shell snippet used only in
`install.sh` today. Used by the router-setup page and the dashboard.

### 2. "Serving your network" verification (traffic heuristic)

Unbound does not cheaply expose per-client query counts via `unbound-control`, so a precise
"N devices are using Stillhem" number is not available without heavy query logging (SD-card wear).
Instead we use a **traffic-volume heuristic**, which is a genuine discriminator in practice: an idle
appliance resolves almost nothing, so Unbound sees ~0 queries until the router points the LAN's DNS
at it, after which every device's DNS flows through and volume jumps.

- `stillhem.dns_control.total_queries()` shells out to `unbound-control stats_noreset` and parses
  `total.num.queries=<n>` → int (same shell-out-and-parse pattern as the existing `dns_control`
  functions, so it mocks cleanly in tests).
- On each dashboard load the app records a `(timestamp, count)` sample in the DB config and computes
  queries-per-minute between the two most recent samples. If the rate is at or above a small floor
  (`SERVING_QPM_THRESHOLD`, e.g. 3 q/min sustained), the dashboard shows **"Stillhem is serving your
  network ✓"**; otherwise **"Waiting for your router — DNS isn't set up yet"** linking to the
  router-setup page.
- The spec is explicit in the UI copy and code comments that this is a *traffic* signal, not a
  device count, and can read "not set up yet" on a very quiet network — acceptable, since the buyer
  can re-check after using a device.

### 3. Router-setup page (`GET /router`, auth-required, normal mode only)

A new admin page that:
- Shows the Pi's detected LAN IP prominently (from `primary_ip()`), with a one-line "set this as your
  router's DNS server" instruction.
- Gives generic step-by-step instructions (log into the router admin, find LAN/DHCP DNS settings, set
  primary DNS to the Pi's IP, save, reconnect a device).
- Provides collapsible **per-brand** specifics for the common Swedish home/ISP routers — Telia,
  Tele2/Comhem, Bahnhof, Telenor — plus generic Asus / TP-Link / Netgear. Content is static markup;
  brand sections name the exact menu path where it reliably differs.
- Notes the caveat that some ISP-locked routers don't allow changing DNS, in which case the fallback
  is setting DNS per-device (with a short pointer), so the buyer isn't stuck with no path.

### 4. Dashboard integration

- A status line/banner at the top of the dashboard driven by the serving heuristic: green
  "serving your network ✓" or amber "DNS isn't set up yet → Set up your router" linking to `/router`.
- The existing blocking-active status and blocklist management stay as-is.

### 5. Wizard done-screen wording

The wizard's completion screen already forward-points to the admin page for the router step. Update
its copy to name it concretely ("After it restarts, open the admin page and follow **Set up your
router** to finish") so the handoff between the two sub-projects reads as one flow.

## Scope boundaries

- **DHCP takeover** — documented non-choice above; not built.
- **Automatic router reconfiguration** (UPnP/TR-069/vendor APIs) — out of scope: no reliable
  cross-brand mechanism exists and it would need router credentials; the manual step stands.
- **Dev-vs-release hardening** (SSH, baked password) — still sub-project 5.
- The router brand list is a curated starting set, not exhaustive; adding brands later is trivial
  (static template content).

## Testing / acceptance

Fully testable off-hardware:

- `netinfo.primary_ip` — returns a string; the error path (socket raises) returns `127.0.0.1`
  (mock the socket).
- `dns_control.total_queries` — parses sample `unbound-control stats_noreset` output (mock
  `subprocess`), including a malformed/missing-line fallback.
- Serving heuristic — a pure function over two `(timestamp, count)` samples: below-threshold →
  not serving, above → serving, single/no sample → not serving; tested directly.
- `/router` page — `TestClient`: requires auth; renders the Pi IP and at least one per-brand section.
- Dashboard banner — `TestClient`: shows the "not set up" state with a low/zero query rate and the
  "serving" state when the sampled rate is above threshold (seed the samples in the DB).

Optional on-hardware confirmation (developer): point a real router's DNS at the Pi and watch the
dashboard banner flip to "serving ✓" — not required for merge, since the heuristic is unit-tested.

## Risks / open points

- **Heuristic false-negatives on quiet networks.** A network with almost no DNS activity can read
  "not set up yet" even when correctly configured. Mitigated by honest copy ("try using a device,
  then refresh") and a low threshold. A precise per-client count is deliberately not pursued (log
  cost).
- **Per-brand instructions drift** as router firmware UIs change. Content is static and easy to
  update; we name menu paths conservatively and always fall back to the generic steps.
- **ISP-locked routers** that forbid changing DNS — surfaced as the per-device fallback so the buyer
  always has a path.
