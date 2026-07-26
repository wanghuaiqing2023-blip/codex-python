# Claude Code Best Practices

> Structured notes based on Anthropic's official Claude Code documentation.
> This is a paraphrased project reference, not a verbatim republication. Product
> commands mentioned by the source are examples, not requirements for PyCodex.

## Source

- Publisher: Anthropic
- Document: Best practices for Claude Code
- Official documentation: <https://code.claude.com/docs/en/best-practices>
- Earlier engineering article published: April 18, 2025
- Retrieved: July 20, 2026

## Core argument

Agentic coding works best when the repository gives the agent precise context
and a direct way to verify results. Context capacity is a practical constraint:
performance can degrade as instructions, file reads, command output, and
conversation history accumulate. Effective work therefore separates discovery,
planning, implementation, and verification while keeping each phase focused.

## Recommended workflow

1. Explore the relevant code before changing it.
2. Form a plan when scope, ownership, or approach is uncertain.
3. Implement against known patterns and explicit constraints.
4. Run tests or interact with the product to verify the result.
5. Preserve a descriptive change record for review and future sessions.

Small, obvious changes do not require ceremonial planning. Larger cross-module
changes benefit from separating investigation from editing so that the agent
does not commit early to the wrong architecture.

## Repository configuration

- Keep repository instructions concise, current, and focused on facts the agent
  cannot reliably infer.
- Point to specific files, examples, constraints, and expected tests in task
  prompts.
- Provide stable commands for build, test, lint, and product verification.
- Use hooks or deterministic gates for requirements that must always hold.
- Use focused skills or subagents for isolated domains rather than expanding the
  global instruction set indefinitely.
- Correct direction early when the agent is solving the wrong problem; do not
  wait for a large diff.

## Verification ladder

Verification can be requested in the task, enforced by a deterministic gate,
or delegated to an independent reviewer. Strong completion evidence includes
the command that ran, its result, a test report, a screenshot, or verified
environment state. A final sentence claiming success is not enough.

Independent review is especially valuable when the authoring agent is likely to
accept its own assumptions. Deterministic checks remain preferable for exact
invariants such as formatting, type safety, module ownership, or protocol
schemas.

## Application to codex-python

- Start parity work by exploring the Rust owner and Python counterpart before
  proposing implementation.
- Use the existing module workflow in `AGENTS.md`; do not copy Claude-specific
  commands or directory conventions into the runtime.
- Make test and manifest commands easy to discover from repository docs.
- Ask for direct parity evidence: source anchor, test anchor, normalized runtime
  trace, or rendered TUI outcome as appropriate.
- Use subagents for bounded source research or independent review, not as a way
  to create a second implementation owner.
- Keep sessions focused; move durable findings into module documentation and
  tests rather than relying on chat history.

## Review checklist

- Did the agent inspect the relevant implementation before editing?
- Was planning proportional to uncertainty and scope?
- Did the prompt identify constraints and existing patterns?
- Can the agent run the same checks a maintainer would run?
- Is success demonstrated by evidence?
- Are repository instructions concise enough to stay salient?
