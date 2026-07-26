# Anthropic References for Preventing Agent Architecture Drift

> Project-oriented reading notes based on official Anthropic publications.
> These files are paraphrased references, not verbatim copies of the source
> articles.

## Purpose

This collection gathers Anthropic's most relevant guidance for keeping
long-running coding agents coherent, observable, and aligned with the intended
architecture. Anthropic does not use one single definition of "architecture
drift" across these publications. The useful controls are distributed across
their work on agent design, context engineering, long-running harnesses,
independent evaluation, and coding-agent workflows.

## Reading order

1. [Building effective agents](ANTHROPIC_BUILDING_EFFECTIVE_AGENTS.md)
   establishes the baseline: use the simplest composable architecture that can
   be measured, keep the system transparent, and design tools deliberately.
2. [Effective context engineering](ANTHROPIC_EFFECTIVE_CONTEXT_ENGINEERING.md)
   explains how to keep instructions, tools, history, and retrieved evidence
   relevant over time.
3. [Effective harnesses for long-running agents](ANTHROPIC_EFFECTIVE_LONG_RUNNING_HARNESSES.md)
   covers durable state, incremental progress, clean handoffs, and feature-level
   completion evidence across context windows.
4. [Harness design for long-running application development](ANTHROPIC_HARNESS_DESIGN_LONG_RUNNING_APPS.md)
   adds planner-generator-evaluator separation, explicit acceptance contracts,
   and independent end-to-end verification.
5. [Demystifying evals for AI agents](ANTHROPIC_DEMYSTIFYING_AGENT_EVALS.md)
   turns expected behavior into repeatable tasks, traces, outcome checks, and
   regression suites.
6. [Claude Code best practices](ANTHROPIC_CLAUDE_CODE_BEST_PRACTICES.md)
   applies these ideas to day-to-day repository work: explore, plan, implement,
   verify, and preserve context intentionally.

## Combined anti-drift model

The publications converge on a practical control loop:

```text
authoritative intent
  -> discoverable repository context
  -> smallest suitable agent/workflow
  -> incremental implementation
  -> observable trace and environment state
  -> independent verification
  -> durable handoff and regression evidence
  -> simplify or revise the harness when assumptions change
```

For this repository, these ideas complement rather than replace the porting
rules in `AGENTS.md` and `PORTING_PROJECT_PRINCIPLES.md`. Rust remains the
behavioral source of truth. Anthropic's material is useful for improving the
harness that discovers, verifies, and preserves that parity.

## Project-level implications

- Repository instructions should be an index into durable, scoped evidence,
  not an ever-growing prompt containing every known edge case.
- A task should begin by locating authoritative ownership and current state,
  then select one coherent unit of work.
- Completion should be supported by environmental evidence, not only by an
  agent's final statement or self-authored tests.
- Runtime traces should preserve intermediate events, tool calls, state
  transitions, and final outcomes when those details define parity.
- Static manifests and dynamic integration tests solve different problems:
  manifests check ownership and coverage; integration tests check collaboration
  and behavior over time.
- Harness components should be retained only while measurements show that they
  improve outcomes. A workaround that once helped can become stale architecture.

## Source list

- <https://www.anthropic.com/engineering/building-effective-agents>
- <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- <https://www.anthropic.com/engineering/harness-design-long-running-apps>
- <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>
- <https://code.claude.com/docs/en/best-practices>

Retrieved: July 20, 2026.
