# Bead Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CI test gate and a codified on-demand worker skill so a dispatched agent can take a bead through design → implement → review → push with auto-merge on green.

**Architecture:** Two deliverables. (1) A GitHub Actions `test.yml` that runs the `firmware/` pytest suite on every PR — the safety gate that makes auto-merge meaningful. (2) A project skill `.claude/skills/work-bead/SKILL.md` that the main session loads and hands to a single dispatched subagent, which runs the full loop in a git worktree.

**Tech Stack:** GitHub Actions, Python 3.11+, pytest / pytest-asyncio, hatchling (editable install), beads (`bd`), Claude Code skills + subagents.

## Global Constraints

- Python floor: **3.11** (`requires-python = ">=3.11"` in `firmware/pyproject.toml`).
- Tests live in `firmware/tests/`; exclude the `integration` marker in CI (needs Unbound on a Pi).
- Test invocation: editable install of `firmware[dev]`, then `pytest -m "not integration"`.
- Branch naming: `bd-<id>-<slug>`, branched off fresh `origin/main`.
- PR body: exactly **Why** and **What** sections, ~25 lines, ending with the Claude Code footer.
- Git policy is conservative-by-default; this workflow is the explicit opt-in that lets a dispatched worker commit/push/PR/auto-merge/close. A live "do not push" instruction still wins.
- Task tracking uses `bd` only — never TodoWrite/markdown TODOs.

---

## File Structure

- `.github/workflows/test.yml` — **create.** Runs pytest on PRs and pushes to main. New file, single responsibility (kept separate from the heavier `build-image.yml`).
- `.claude/skills/work-bead/SKILL.md` — **create.** The worker loop, plus a short "How this is dispatched" section for the main session.

---

### Task 1: CI test gate for `firmware/`

**Files:**
- Create: `.github/workflows/test.yml`
- Reference: `firmware/pyproject.toml` (deps + `integration` marker), `firmware/tests/`

**Interfaces:**
- Produces: a required status check named `firmware-tests` that later gates auto-merge. Branch protection (making it *required*) is a repo-admin GitHub setting, called out in Task 1 Step 5 — it is configuration, not code.

- [ ] **Step 1: Confirm the test command passes locally**

Run (needs network for pip; the CI runner has it):
```bash
cd firmware && python3 -m venv .venv && . .venv/bin/activate \
  && pip install -e ".[dev]" && pytest -m "not integration" -q
```
Expected: all non-integration tests PASS. If any fail, stop and file a bead — do not paper over it in CI.

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/test.yml`:
```yaml
name: firmware-tests

on:
  pull_request:
    paths:
      - "firmware/**"
      - ".github/workflows/test.yml"
  push:
    branches: [main]
    paths:
      - "firmware/**"
      - ".github/workflows/test.yml"

jobs:
  firmware-tests:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: firmware
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: pip install -e ".[dev]"
      - name: Test
        run: pytest -m "not integration" -q
```

- [ ] **Step 3: Validate the YAML parses**

Run:
```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/test.yml')); print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: run firmware pytest suite on PRs"
```

- [ ] **Step 5: Enable branch protection (human/admin step — record, don't fake)**

In GitHub → Settings → Branches → `main`: require the `firmware-tests` check to pass before merge, and enable "Allow auto-merge" for the repo. If you lack admin rights, note this in the handoff as a blocking follow-up — auto-merge is unsafe until the check is required.

---

### Task 2: `work-bead` worker skill

**Files:**
- Create: `.claude/skills/work-bead/SKILL.md`
- Reference: `AGENTS.md` / `CLAUDE.md` (git + PR conventions), superpowers skills (test-driven-development, requesting-code-review)

**Interfaces:**
- Consumes: the `firmware-tests` check from Task 1 (auto-merge waits on it).
- Produces: a loadable skill the main session reads when the user says "work `<bead-id>`", then dispatches to one subagent (via the Agent tool, `isolation: "worktree"`).

This deliverable is a prose artifact, so its "tests" are an acceptance checklist (Step 2) and an optional live dry-run (Step 4), not pytest.

- [ ] **Step 1: Write the skill file**

Create `.claude/skills/work-bead/SKILL.md`:
```markdown
---
name: work-bead
description: Take a single beads issue through design → implement → review → push. Use when the user says "work <bead-id>" or "work the top ready bead". Dispatches one worker subagent in a git worktree.
---

# work-bead

Runs one bead end-to-end. **One bead per dispatch.** Auto-merge means the review
step is the only human-free gate before `main` — do not skip or soften it.

## How this is dispatched (main session)

1. Resolve the bead: an explicit id, or the top of `bd ready`.
2. Dispatch **one** subagent with the Agent tool using `isolation: "worktree"`,
   handing it this file's "Worker loop" as its instructions plus the bead id.
3. When it reports back, relay the PR link + bead status. Do not batch multiple beads.

## Worker loop (the subagent follows this)

### 1. Claim & design
- `bd show <id>` — read description + acceptance criteria.
- `bd update <id> --claim`.
- If the bead is too vague to implement confidently, STOP and report back with the
  ambiguity — do not guess.
- Record a one-paragraph design note: `bd update <id> --design="<approach>"`.

### 2. Implement (TDD)
- `git fetch origin && git switch -c bd-<id>-<slug> origin/main`.
- Use the superpowers:test-driven-development skill: write a failing test in
  `firmware/tests/`, watch it fail, implement minimally, watch it pass.
- Run the suite: `pytest -m "not integration" -q` from `firmware/` (use a venv with
  `pip install -e ".[dev]"`). All green before moving on.

### 3. Review (the gate)
- Dispatch a FRESH review subagent using superpowers:requesting-code-review, giving it
  the diff and the bead's acceptance criteria.
- Address every finding, then re-run the suite. Do not proceed until the reviewer's
  concerns are resolved and tests are green again.

### 4. Push & integrate
- Commit with a conventional message referencing the bead.
- `git push -u origin bd-<id>-<slug>`.
- Open a PR whose body has exactly **Why** and **What** sections (~25 lines), ending
  with the Claude Code footer. Use `gh pr create`.
- Enable auto-merge: `gh pr merge --auto --squash`.
- `bd close <id>`.
- Report the PR URL and that auto-merge is armed.

## Guardrails
- Never merge without the review step passing and tests green.
- Never touch beads other than the one dispatched.
- If `firmware-tests` branch protection is not yet required, say so and do NOT rely on
  auto-merge as a safety net — treat it as needing human merge.
```

- [ ] **Step 2: Acceptance checklist (self-review the file)**

Confirm the file contains, in order: claim + design-note recording; TDD implement with the exact `pytest -m "not integration"` command; a *fresh* review subagent gate; branch off `origin/main` with `bd-<id>-<slug>`; Why/What PR via `gh`; `gh pr merge --auto`; `bd close`. Fix any missing item inline.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/work-bead/SKILL.md
git commit -m "feat: add work-bead worker skill"
```

- [ ] **Step 4: Optional live dry-run**

Pick a small ready bead (e.g. `slopstop-1z4` "stop_ap() is dead code") and dispatch the
worker per "How this is dispatched." Verify it produces a branch, a green suite, a review
pass, and a Why/What PR with auto-merge armed. If anything in the loop is unclear to the
subagent, tighten the wording in `SKILL.md` and re-commit. (Requires Task 1 Step 5 done
for auto-merge to actually gate.)

---

## Self-Review

**Spec coverage:**
- On-demand single-bead dispatch → Task 2 "How this is dispatched" (one subagent, no batching). ✓
- Worktree isolation → Task 2 dispatch step (`isolation: "worktree"`). ✓
- Claim + design note → Task 2 §1. ✓
- TDD implement + pytest → Task 2 §2. ✓
- Independent review gate → Task 2 §3 (fresh subagent). ✓
- Branch/PR/auto-merge/close → Task 2 §4. ✓
- CI test job prerequisite → Task 1. ✓
- "Green means tests ran" + required check → Task 1 Steps 2 & 5. ✓
- Trunk-based branch/PR conventions → Global Constraints + Task 2 §4. ✓
- Out-of-scope items (cron, batching, review-less merge) → not implemented. ✓

**Placeholder scan:** No TBD/TODO; every code/config block is complete. The one
"optional" step (Task 2 Step 4) is explicitly optional and fully specified.

**Type consistency:** Check name `firmware-tests` is identical in the workflow `name:`,
job id, and Task 1 interface/branch-protection references. Branch pattern `bd-<id>-<slug>`
is identical across Global Constraints and Task 2 §2/§4.
