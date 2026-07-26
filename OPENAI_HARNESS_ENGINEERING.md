# Harness Engineering: Leveraging Codex in an Agent-First World

> Structured notes based on the official OpenAI engineering article. This is
> a paraphrased project reference, not a verbatim republication.

## Source

- Publisher: OpenAI
- Author: Ryan Lopopolo, Member of the Technical Staff
- Published: February 11, 2026
- Category: Engineering
- Official article: <https://openai.com/index/harness-engineering/>
- Retrieved: July 20, 2026

## Executive summary

OpenAI describes an experiment in which a small engineering team built and
operated a large internal product while requiring Codex to generate all code,
tests, CI configuration, documentation, observability, and developer tooling.
The main lesson is that reliable agentic development depends less on repeatedly
prompting the model and more on engineering an environment that makes the
correct behavior discoverable, executable, observable, and mechanically
enforceable.

Human engineers move up one level of abstraction. They define intent, provide
maps and tools, encode feedback loops, and decide which invariants must be
enforced. Agents perform implementation, testing, review, and maintenance
inside those constraints.

## 1. Start with scaffolding, not task prompting

An underspecified repository limits the agent even when the model is capable.
When a task fails, the useful question is not how to make the agent try harder,
but which missing capability prevented success and how that capability can be
made both visible and enforceable.

The team worked depth-first:

1. Break a large objective into design, implementation, review, and validation
   building blocks.
2. Add the tools and abstractions needed for each block.
3. Let later tasks reuse those capabilities.
4. Feed failures back into the repository as durable improvements.

## 2. Make the application legible to agents

Agents need direct access to the same evidence that a human engineer would use
to debug and validate a system. OpenAI made each worktree independently
bootable and exposed UI state, screenshots, browser automation, logs, metrics,
and traces to Codex.

This turns vague requirements into executable checks. Instead of asking an
agent to infer whether a change worked, the harness lets it reproduce a bug,
observe state, apply a fix, restart the application, and validate the same user
journey again.

Important harness capabilities include:

- Isolated application instances per worktree.
- Programmatic UI inspection and interaction.
- Worktree-local logs, metrics, and traces.
- Stable commands for reproduction and verification.
- Feedback loops that can run for hours without losing observability.

## 3. Treat repository knowledge as the system of record

A single very large `AGENTS.md` did not scale. It consumed context, made every
rule look equally important, became stale quickly, and was difficult to verify
mechanically.

The replacement model is progressive disclosure:

- Keep `AGENTS.md` short and use it as a table of contents.
- Keep architecture, design, product, reliability, security, and operational
  knowledge in focused repository documents.
- Index those documents so an agent can navigate from a stable entry point.
- Version execution plans and technical debt next to the code.
- Generate machine-derived references where possible.
- Use linters and recurring maintenance tasks to detect stale documentation.

The repository, rather than chat history or undocumented human knowledge,
becomes the durable source an agent can inspect during future tasks.

## 4. Optimize for agent legibility

Information that is inaccessible during an agent run effectively does not
exist for that agent. Important architectural decisions, product rules, and
operational knowledge therefore need repository-local representations.

Legibility does not mean adding unlimited prose. It means exposing the right
information through stable structures:

- Clear module and package boundaries.
- Discoverable ownership and dependency direction.
- Typed or validated data shapes at system boundaries.
- Boring, composable abstractions that can be inspected locally.
- Tests, logs, and schemas that explain behavior without oral context.

## 5. Enforce architecture mechanically

Documentation alone cannot prevent architectural drift in a high-throughput,
agent-generated codebase. OpenAI uses a rigid layered architecture with a
small set of permitted dependency directions. Cross-cutting concerns enter
through explicit provider interfaces rather than arbitrary imports.

The core principle is to enforce invariants without prescribing every local
implementation detail. Mechanical controls include:

- Custom architecture linters.
- Structural dependency tests.
- Boundary validation for external data.
- Naming conventions for schemas and types.
- Structured logging requirements.
- File-size constraints.
- Platform-specific reliability checks.
- Actionable lint messages that explain remediation to the agent.

Central constraints protect boundaries, correctness, and reproducibility.
Within those boundaries, agents retain implementation freedom.

## 6. Encode taste as enforceable feedback

Human review comments and recurring defects should not remain one-off advice.
When a preference matters repeatedly, it should become one of the following:

- A documented design principle.
- A reusable abstraction.
- A lint rule.
- A structural test.
- A runtime assertion.
- An evaluation or integration test.

This allows one human judgment to influence every future generated change.

## 7. Treat entropy as a garbage-collection problem

Agents reproduce existing repository patterns, including weak or inconsistent
ones. Without maintenance, local shortcuts multiply and architectural drift
compounds.

OpenAI moved from periodic manual cleanup to continuous mechanical cleanup:

1. Define a small set of opinionated golden principles.
2. Scan the repository regularly for violations.
3. Update quality grades and debt inventories.
4. Open small, targeted refactoring changes.
5. Review and merge those changes continuously.

Examples include preferring shared utilities over duplicate local helpers and
requiring validated boundary data instead of guessing object shapes.

Small continuous cleanup prevents technical debt from becoming a large,
expensive migration.

## 8. Autonomy depends on repository investment

End-to-end agent autonomy is not an automatic property of a capable model. It
depends on a repository that supports the complete loop:

1. Validate the starting state.
2. Reproduce the defect.
3. Capture evidence of the failure.
4. Implement the change.
5. Exercise the application directly.
6. Capture evidence of the corrected behavior.
7. Review the change.
8. Detect and remediate CI failures.
9. Escalate only decisions requiring human judgment.

## Implications for codex-python

The article suggests that this project's parity harness should separate
navigation evidence from acceptance evidence.

### Recommended evidence levels

```text
inventoried
  -> candidate
  -> structurally_mapped
  -> evidence_mapped
  -> parity_verified
```

- `inventoried`: the Rust module exists in the fixed upstream graph.
- `candidate`: a possible Python counterpart was found.
- `structurally_mapped`: the file or bounded package follows the permitted
  module mapping and ownership rules.
- `evidence_mapped`: Rust APIs, runtime anchors, tests, or explicit source
  contracts are linked to Python tests.
- `parity_verified`: focused module tests and relevant dynamic behavior tests
  pass against the fixed Rust baseline.

### Structural controls to retain

- Detect duplicate owners and scattered one-to-many mappings.
- Permit one Rust module to map to one bounded Python package.
- Reject sibling `name.py` and `name/__init__.py` shadow implementations.
- Require Python-only adapters to declare Rust-owned responsibilities.
- Keep test-support and manifest metadata separate from production ownership.
- Prevent candidate discovery from automatically claiming parity.

### Dynamic controls for critical paths

Static structure should be supplemented by focused integration tests for:

- Slash-command discovery, completion, dispatch, and active views.
- Composer cursor movement, IME text, history, and popup placement.
- Approval state, permission selection, and sandbox handoff.
- Streaming lifecycle, Working/Reconnecting visibility, and retry completion.
- Goal and plan continuation state, context, tools, and accounting.
- Terminal viewport, history insertion, resize reflow, and scrollback.

### Continuous maintenance

The manifest checker should support recurring cleanup rather than act only as
a one-time completion report. Useful recurring checks include:

- Unowned or multiply owned files.
- Unreferenced production modules.
- Stale compatibility paths and package shadows.
- Dependency-direction violations.
- Missing Rust source/test anchors.
- Documentation that disagrees with executable manifests.
- Growth in Python-only policy or command-specific exceptions.

## Project takeaway

The harness should not try to prove architectural parity from filenames or a
green Python-only test suite. Its job is to make architecture and behavior
legible, encode module boundaries, connect each claim to authoritative Rust
evidence, and fail mechanically when those claims drift.

This turns `AGENTS.md` into a map, the manifest into an ownership and evidence
index, tests into executable contracts, and recurring cleanup into the system
that prevents entropy from accumulating.

