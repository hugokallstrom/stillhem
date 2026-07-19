# Rebrand Algoro → Stillhem + license fix

**Parent context:** `HANDOFF.md` (Stillhem image-build handoff doc, downloaded 2026-07-19) lists two
"repo cleanups to do alongside" the image-build work: the rename and the LICENSE/README mismatch.
Per trunk-based-development practice, this is split out as its own short-lived branch/PR since it
has no dependency on the image-build sub-projects and is small enough to ship first.

## Goal

1. Rename the product from Algoro to Stillhem everywhere public-facing in this repo.
2. Fix the license contradiction: README says AGPLv3, LICENSE file is MIT text. AGPLv3 is the
   intended license — replace LICENSE with the full AGPLv3 text.

## Scope

### Package rename
- `firmware/src/algoro/` → `firmware/src/stillhem/`
- Update every `from algoro...` / `import algoro...` reference in `firmware/src/`, `firmware/tests/`,
  `firmware/conftest.py`
- `firmware/pyproject.toml`: `name = "algoro"` → `name = "stillhem"`

### Env vars (5, used in code defaults, README, systemd unit)
`ALGORO_DB_PATH`, `ALGORO_BLOCKLIST_PATH`, `ALGORO_UNBOUND_CONF`, `ALGORO_DNS_TEMPLATE_DIR`,
`ALGORO_PRESET_DIR` → `STILLHEM_*`

### Paths
- `/opt/algoro` → `/opt/stillhem`
- `/var/lib/algoro` → `/var/lib/stillhem`
- Generated Unbound conf filename `algoro.conf` → `stillhem.conf`

### systemd
- `firmware/systemd/algoro-admin.service` → `firmware/systemd/stillhem-admin.service`
- Update `Description`, `ExecStart`, `WorkingDirectory`, `Environment` lines to match new
  paths/module name

### `firmware/systemd/install.sh`
Update all path and service-name references to match the above.

### `README.md`
Title, install instructions, env var table — replace `algoro`/`ALGORO_*` throughout.

### Templates
`dashboard.html`, `login.html`, `setup.html`, `base.html` — "algoro" → "stillhem" in
headings/`<title>`.

### Tests
`firmware/tests/test_admin.py:55` — `assert "algoro" in resp.text.lower()` → `"stillhem"`.

### LICENSE
Replace the current MIT license body with the full, unmodified GNU AGPLv3 license text.
Keep `Copyright (c) 2026 Hugo Linder` as the copyright line (AGPLv3's own boilerplate notice,
placed as a header comment convention or left to the README's existing "License" section — the
LICENSE file itself is the verbatim AGPLv3 text, which is what GitHub's license detector needs to
correctly identify it).

## Explicitly out of scope

- **`docs/superpowers/plans/*.md` and `docs/superpowers/specs/*.md`** — historical implementation
  records. `2026-05-11-slopstop-v1-design.md` already states *"Working title: 'algoro' — rename
  throughout once brand is chosen"*, so these are accurate as written and are not rewritten, the
  same way git history isn't rewritten.
- **Hostname / mDNS / avahi config** — does not exist in the repo yet (no `stillhem.local` setup
  currently exists). That's part of the later first-boot/captive-portal sub-project from the
  handoff doc, not this one.
- **GitHub repository rename** (`hugokallstrom/algoro-pi` → `stillhem`) — done via `gh` **after**
  this PR merges, plus updating the local `origin` remote URL. Not done while a PR is open against
  the old repo name.

## Testing

Run `pytest -m "not integration"` from `firmware/` after the rename to confirm no import or
string reference still points at the old package/env-var names.

## Sequencing note

This is sub-project 1 of 5 identified from the handoff doc (rebrand+license → pi-gen Docker build →
first-boot AP/captive-portal wizard → router DNS UX → GitHub Actions release automation). Each gets
its own spec/plan/PR.
