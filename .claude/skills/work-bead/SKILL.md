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
- Address every finding, then re-run the suite.
- Re-dispatch the review subagent on the POST-FIX diff. Do not proceed to step 4 until a
  review pass returns no unaddressed Critical/Important findings AND tests are green.

### 4. Push & integrate
- Commit with a conventional message referencing the bead; PR title `<type>: <summary> (bd-<id>)`.
- `git push -u origin bd-<id>-<slug>`.
- Open a PR whose body has exactly **Why** and **What** sections (~25 lines), ending
  with the Claude Code footer. Use `gh pr create`.
- Verify the merge gate exists BEFORE arming auto-merge:
  `gh api repos/{owner}/{repo}/branches/main/protection/required_status_checks --jq '.contexts'`
  - If `firmware-tests` is in the output: arm auto-merge with `gh pr merge --auto --squash`.
  - If it is NOT (or the call errors because protection is unset): do NOT arm auto-merge.
    Report "human merge required — firmware-tests is not a required check on main" and leave
    the PR for a human to merge.
- `bd close <id>`.
- Report the PR URL and the merge state (auto-merge armed vs. human merge required).

## Guardrails
- Never merge without the review step passing and tests green.
- Never touch beads other than the one dispatched.
- If `firmware-tests` branch protection is not yet required, say so and do NOT rely on
  auto-merge as a safety net — treat it as needing human merge.
