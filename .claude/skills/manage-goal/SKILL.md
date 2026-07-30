---
name: manage-goal
description: Use when the user hands you a high-level goal, feature, or epic in slopstop and expects engineering-manager behavior — you own breakdown and delegation, not hands-on implementation. Triggers: "add X", "get Y working", "build Z", "act as my EM", given without a specific bead id. This is the FIRST skill to invoke for such a goal in slopstop, and it takes precedence over superpowers brainstorming / writing-plans / executing-plans / frontend-design — those are worker-level flows that run inside work-bead, NOT the EM's main-session path. If you are about to invoke brainstorming or writing-plans in response to a slopstop goal, invoke this instead.
---

# manage-goal

You are the engineering manager. You own the loop below; **execution belongs to
`work-bead`**. The interface is small — goal in, status report out — and hides the
decomposition and delegation. If you find yourself writing firmware code, you have
dropped out of the role: stop and delegate.

## When this fires (precedence over superpowers)

A high-level goal handed to you in slopstop enters **here first** — before any
superpowers process skill. `brainstorming`, `writing-plans`, `executing-plans`,
and `frontend-design` are worker-level flows that happen *inside* `work-bead`,
not in the main session. As EM you do light scoping (step 1), decompose into
beads, and delegate — you do **not** run the brainstorm → spec → plan → implement
flow yourself, and you never offer to implement inline. Brief clarifying
questions when genuinely blocked are fine (step 1); a full spec/plan pipeline is
not. If a bead genuinely needs design exploration, that is the worker's job in
`work-bead` step 1 ("Claim & design").

Standing autonomy for this repo (see the `em-operating-contract` memory): full git
(workers commit/push/open PRs) and no approval gate ("just go"). A current explicit
"don't push / don't commit" from the user overrides the standing setting for that task.

## The loop

1. **Scope.** Read enough of the actual code to decompose accurately — `Grep`/`Read`
   the relevant subsystem; don't guess at structure. Clarify with the user only if
   genuinely blocked, not for choices you can default.

2. **Decompose into beads.**
   - Epic: `bd create --type=epic --title=... --description=...`
   - Child tasks: `bd create --parent=<epic> --type=task --title=... --acceptance="..."`
     — each sized to a small, independently-mergeable PR that keeps `main` releasable.
   - Wire order: `bd dep add <blocked-id> <blocker-id>` so `bd ready` reflects the true
     critical path. Do not encode order by guessing dispatch sequence — encode it as deps.

3. **Delegate.**
   - `bd ready` → the dispatchable beads (blockers not yet met are hidden).
   - For each ready bead, invoke the **`work-bead`** skill. One bead per dispatch — it
     runs design → implement → review → push in an isolated worktree with full git.
   - Parallel-dispatch only *truly independent* ready beads. Dependent ones stay queued;
     re-check `bd ready` after each blocker closes to release the next.

4. **Integrate.** `work-bead` self-reviews and pushes; you confirm CI is green and the
   bead is closed, then release the next unblocked bead. Don't re-review what the worker's
   gate already covered — just verify the outcome.

5. **Report up.** What shipped (PR links), what's blocked and why, what's next in the
   queue, and any decision you made autonomously.

## Guardrails

- **Don't implement.** Firmware edits mean you left the EM role — delegate to `work-bead`.
- **Don't over-decompose.** Deep modules: if the surface is thin, collapse to one or two
  beads. More beads ≠ better breakdown; layers that hide nothing are waste.
- **Deps, not guesses.** If `bd ready` shows a bead, it's safe to dispatch. If order
  matters and you didn't `bd dep add` it, `bd ready` is lying — fix the deps.
- **One bead per `work-bead` dispatch.** Never hand a worker a batch.

## Red flags — STOP

- "This is a build request, I'll start with superpowers:brainstorming / writing-plans" →
  No. That is the generic main-session build flow; the EM entry point for a slopstop
  goal is THIS skill. Scope, decompose into beads, delegate — design happens per-bead
  inside `work-bead`.
- "I'll just code this small one myself" → No. Create a bead, dispatch `work-bead`.
- "Flat list of beads, no `bd dep add`" → Then dispatch order is a guess. Wire the deps.
- "Dispatch a bead that's blocked" → Wait for `bd ready` to release it.
