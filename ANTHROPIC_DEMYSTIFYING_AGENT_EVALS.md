# Demystifying Evals for AI Agents

> Structured notes based on the official Anthropic engineering article. This
> is a paraphrased project reference, not a verbatim republication.

## Source

- Publisher: Anthropic
- Published: January 9, 2026
- Official article: <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>
- Retrieved: July 20, 2026

## Core argument

Manual testing and intuition can support early prototyping, but they do not
provide a stable way to distinguish regressions from run-to-run variation.
Agent systems require evaluations that cover multi-turn behavior, tool use,
environment changes, and final outcomes. The agent harness and the model must
be evaluated together.

This is the most direct Anthropic reference for making architecture drift
visible before users encounter it.

## Evaluation vocabulary

- A task defines the input and success criteria.
- A trial is one attempt; multiple trials reveal nondeterministic variation.
- A grader checks one aspect of performance using one or more assertions.
- A transcript or trace records turns, tool calls, intermediate results, and
  other execution details.
- An outcome is the final environment state, which may differ from what the
  agent claims in its final message.
- An evaluation harness runs tasks, records traces, applies graders, and
  aggregates results.
- An evaluation suite groups tasks around a capability or behavior.

## Grader strategy

No single grader type is sufficient:

- Code-based graders are fast and reproducible. They can check tests, static
  analysis, tool names and arguments, event order, state, tokens, or latency.
- Model-based graders handle nuanced or open-ended quality, but need explicit
  rubrics and calibration.
- Human review catches requirements and quality dimensions that automated
  graders miss, and provides calibration data for the other graders.

Prefer outcome checks for objective behavior. Transcript checks are appropriate
when the route itself is part of the contract, such as required approval,
sandbox, retry, or tool-dispatch semantics. Avoid over-constraining internal
steps when several valid routes produce the same required outcome.

## Anti-drift evaluation design

1. Convert each reported regression into a reusable task when it represents a
   durable product contract.
2. Record normalized traces for intermediate behavior that users can observe or
   that affects safety and state.
3. Check final environment state separately from final prose.
4. Run multiple trials where model variation matters.
5. Maintain a stable regression suite and a broader capability suite.
6. Track latency, token use, error rate, and retry behavior alongside pass rate.
7. Periodically compare automated graders with human judgment.
8. Update tasks when the product contract changes; do not preserve accidental
   implementation details as permanent requirements.

## Application to codex-python

- Module parity tests should derive from Rust tests or source contracts and name
  that evidence.
- Dynamic Rust/Python comparison should normalize equivalent events before
  comparing them and should target one contract at a time.
- Reconnect testing should capture connection state transitions, retry notices,
  working-indicator state, terminal events, cancellation, and terminal outcome.
- TUI screenshots are useful outcome evidence but cannot replace event and state
  assertions for transient behavior.
- Manifest checks should prove structural ownership and coverage; they should
  not substitute for runtime integration tests.
- A passing Python-only test is regression evidence, not Rust parity evidence,
  unless it is tied to an authoritative Rust contract.

## Review checklist

- Does the test grade the claim, the trajectory, the outcome, or all three?
- Is each intermediate assertion required by the product contract?
- Are nondeterministic trials repeated enough to detect instability?
- Can failures be diagnosed from the recorded trace?
- Is the suite measuring behavior rather than file existence?
- Is the Rust baseline pinned and identifiable?
