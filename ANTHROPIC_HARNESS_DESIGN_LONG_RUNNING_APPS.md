# Harness Design for Long-Running Application Development

> Structured notes based on the official Anthropic engineering article. This
> is a paraphrased project reference, not a verbatim republication.

## Source

- Publisher: Anthropic
- Author: Prithvi Rajasekaran
- Published: March 24, 2026
- Official article: <https://www.anthropic.com/engineering/harness-design-long-running-apps>
- Retrieved: July 20, 2026

## Core argument

Long-running coding agents can lose coherence as context grows, terminate work
prematurely, and judge their own output too generously. A stronger harness
separates specification, implementation, and evaluation, and gives each phase
explicit artifacts and observable acceptance criteria.

The described architecture used planner, generator, and evaluator roles. This
is not a requirement for every task. It is evidence that independent planning
and evaluation can add value when task complexity exceeds what one agent can
reliably complete and verify alone.

## Architecture

- The planner expands a short objective into product scope and high-level design
  without over-specifying fragile implementation details.
- The generator implements bounded work against the agreed scope and records its
  result.
- The evaluator exercises the running system as a user would, checks UI, API,
  and persistent state, and reports concrete failures.
- Before implementation, generator and evaluator agree on a contract defining
  what will be built and how completion will be verified.
- Feedback returns to the generator until the contract passes or the harness
  reaches a stopping condition.

Separating evaluator from generator reduces the bias of self-evaluation. The
evaluator still needs calibration: an independent but permissive reviewer can
approve shallow tests or excuse real defects.

## Context reset versus compaction

Compaction shortens prior conversation while preserving continuity. A context
reset starts a fresh session and relies on a structured handoff. Resets can
reduce behavior caused by an overloaded context but add orchestration cost and
require a complete handoff artifact. The right choice depends on measured model
behavior, not a permanent rule.

## Avoiding stale harness architecture

Every harness component encodes an assumption about a model limitation. As
models improve, those assumptions may stop being true. Anthropic recommends
testing realistic traces and removing components methodically, one at a time,
to determine which parts still improve results.

This point is directly relevant to architecture drift: scaffolding intended to
help an older model can become redundant ownership, duplicate execution paths,
or a source of behavior different from the upstream implementation.

## Application to codex-python

- Define parity acceptance before editing: Rust owner, anchor, expected event or
  state sequence, Python owner, and verification method.
- Use a separate checker for user-visible or stateful behavior when self-authored
  implementation tests cannot establish parity.
- For TUI and reconnect work, evaluate the running interface and normalized event
  trace, not only the final output string.
- Treat a manifest candidate as a planning signal; an evaluator must still prove
  ownership and behavior.
- Do not introduce planner, evaluator, or reset machinery globally. Add it only
  where a measured contract justifies its cost and where it preserves the Rust
  module boundaries.
- Revisit old compatibility layers after model or runtime changes and remove
  those that no longer carry parity value.

## Review checklist

- Is "done" defined before implementation begins?
- Does verification exercise the real user or runtime path?
- Is the evaluator independent enough to challenge the implementation?
- Are handoff artifacts sufficient after a context reset?
- Which harness assumptions have been measured recently?
- Can any component be removed without reducing verified performance?
