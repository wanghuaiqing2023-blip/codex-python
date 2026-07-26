# Effective Harnesses for Long-Running Agents

> Structured notes based on the official Anthropic engineering article. This
> is a paraphrased project reference, not a verbatim republication.

## Source

- Publisher: Anthropic
- Published: November 26, 2025
- Official article: <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- Retrieved: July 20, 2026

## Problem addressed

Long tasks span context windows. A fresh session does not automatically know
what previous sessions changed, why they changed it, what remains broken, or
how to run the project. Compaction alone may leave an ambiguous handoff. Two
common failures follow:

- The agent attempts too much at once and leaves a half-implemented state.
- A later session sees substantial progress and declares the whole task complete
  without checking the remaining requirements.

Both failures create drift between intended behavior and repository state.

## Harness structure

Anthropic's experiment used two roles:

- An initializer prepared the repository for repeated sessions. It created a
  feature inventory, startup instructions, progress artifacts, and initial
  version-control state.
- Each coding session selected a bounded feature, verified the existing baseline,
  made incremental progress, and left a clean state plus a durable handoff.

The exact filenames in the experiment are implementation examples, not universal
requirements. The durable principle is that future sessions need a reliable way
to reconstruct current state from the repository and version history.

## Session protocol

A productive session should:

1. Confirm the working directory and repository state.
2. Read the current progress and requirement inventory.
3. Inspect recent version-control history.
4. Use the documented startup path.
5. Run a basic end-to-end check before adding new behavior.
6. Select one coherent incomplete feature or contract.
7. Implement and verify it without rewriting unrelated areas.
8. Leave the repository in a clean, runnable state.
9. Update durable status and commit history with evidence.

The baseline check is important: adding a feature on top of an undocumented
failure usually makes diagnosis and ownership less clear.

## Anti-drift mechanisms

- A complete requirement inventory prevents premature victory.
- Feature status begins as unverified and changes only after evidence exists.
- Progress notes preserve decisions that cannot be reconstructed cheaply.
- Git history records exactly what changed between sessions.
- A standard startup command prevents repeated environment rediscovery.
- Incremental scope reduces half-finished cross-cutting changes.
- End-of-session cleanliness keeps the next session from inheriting unrelated
  breakage.

## Application to codex-python

- Porting manifests can provide inventory, ownership, and evidence coordinates,
  but they must not claim behavior is complete merely because a candidate file
  exists.
- `PORTING_STATUS.md` should change only when a module contract has meaningful
  evidence; turn-by-turn narration belongs elsewhere or should be omitted.
- A new parity task should begin by checking the current test baseline and dirty
  worktree without reverting user changes.
- Handoffs should name the Rust owner, Python owner, contract, tests, observed
  failure, and remaining work.
- Completion should mean the selected contract passes and the collaborating
  mainline remains runnable, not that many files were touched.

## Review checklist

- Can a fresh session understand current state without the old conversation?
- Is incomplete work distinguishable from verified work?
- Is there one documented way to start and smoke-test the system?
- Does the change leave unrelated modules clean and runnable?
- Is the next action bounded and explicit?
