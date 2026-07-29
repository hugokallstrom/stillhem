# On-demand bead worker — design

**Date:** 2026-07-29
**Status:** Approved, pending implementation plan

## Why

Beads is populated (15 issues, ~10 ready) but there is no repeatable way to hand a
bead to an agent and get it worked end-to-end. We want to: create beads tasks, then
on demand have an agent pick one up and run a full **design → implement → review →
push** loop, landing a small PR that auto-merges when CI is green.

The constraint that shapes everything: the user opted for **auto-merge on green**, so
the pre-merge review is the *only* human-free gate before `main`. That makes two things
non-negotiable — (1) CI must actually run the test suite, and (2) an independent review
must run before the PR opens. A worker rationalizing its own diff cannot be the gate.

## What

### Orchestration model

- **Trigger:** on-demand dispatch. The user says "work `<bead-id>`" or "work the top
  ready bead." The main session dispatches **one** subagent scoped to that single bead.
  No cron, no polling, one bead per dispatch.
- **Isolation:** the worker runs in a **git worktree** (auto-cleaned) so branch work
  never disturbs the main checkout.
- **Deliverable of the effort:** a codified worker skill/prompt loaded on each dispatch,
  so the loop is consistent and reviewable rather than re-improvised per run.

### The worker loop

1. **Claim & design.**
   - `bd show <id>` to read description + acceptance criteria.
   - `bd update <id> --claim`.
   - Write a short design note back onto the bead: `bd update <id> --design="..."`.
   - If the bead is too fuzzy to implement confidently, **stop and ask** rather than guess.
2. **Implement (TDD).**
   - Branch off fresh `origin/main`: `git fetch` then branch `bd-<id>-<slug>`.
   - Use the test-driven-development skill: failing test first → implementation → green.
   - Run `pytest` in `firmware/`.
3. **Review (independent gate).**
   - Dispatch a *fresh* review subagent (requesting-code-review skill) that judges the
     diff against the bead's acceptance criteria.
   - The worker must address findings and re-verify (re-run tests) before proceeding.
4. **Push & integrate.**
   - Commit, push the branch.
   - Open a small PR with exactly **Why** and **What** sections, ~25 lines (per user
     CLAUDE.md). PR body ends with the Claude Code footer.
   - Enable auto-merge so the PR lands when CI is green.
   - `bd close <id>`.

### Prerequisite (must land first): CI test job

Auto-merge is only safe if "green" means tests ran. Today `.github/workflows/build-image.yml`
only builds the Pi image. Add a GitHub Actions job that, on PR and push:

- sets up Python 3.11+,
- `pip install -e firmware[dev]` (installs pytest + pytest-asyncio + anyio),
- runs `pytest firmware/` excluding the `integration` marker (which needs Unbound on a Pi).

Until this job exists and is required for merge, auto-merge would rubber-stamp broken code.
This is **step zero** of the implementation plan.

### Git / policy alignment

- Trunk-based: short-lived `bd-<id>-*` branches, small PRs, branch off fresh `origin/main`.
- This workflow is an explicit opt-in to a team-maintainer-style flow (agent commits,
  pushes, opens PR, enables auto-merge, closes the bead) for beads dispatched this way.
  A live "do not push" instruction still overrides it.

## Out of scope (YAGNI)

- Scheduled/cron automation and unattended polling of `bd ready`.
- Multi-bead batching in a single dispatch.
- Auto-merge without the independent review gate.

These are easy to add later if the on-demand loop proves out.

## Success criteria

- CI runs `pytest firmware/` on every PR and is a required check.
- Saying "work `<bead-id>`" results in: bead claimed, a design note recorded, a TDD
  implementation on a short-lived branch, an independent review addressed, a small
  Why/What PR opened with auto-merge enabled, and the bead closed.
- `main` stays releasable: nothing merges without green tests + a passed review.
