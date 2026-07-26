# Effective Context Engineering for AI Agents

> Structured notes based on the official Anthropic engineering article. This
> is a paraphrased project reference, not a verbatim republication.

## Source

- Publisher: Anthropic
- Authors: Anthropic Applied AI team
- Published: September 29, 2025
- Official article: <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- Retrieved: July 20, 2026

## Core argument

Agent reliability depends on the complete inference context, not only on the
wording of a system prompt. Instructions, tool definitions, external data,
message history, retrieved files, and intermediate outputs all compete for a
finite context window. The engineering goal is to retain the smallest set of
high-signal information that makes the desired behavior likely.

Architecture drift can therefore be a context failure even when the repository
contains the correct design. If the owning module, authoritative tests, or
current task state are absent while stale summaries and unrelated files are
present, the model will optimize against the wrong representation of the
system.

## Context controls

- Keep system instructions clear and sufficiently specific, but avoid trying to
  enumerate every edge case in one prompt.
- Prefer a small set of diverse, canonical examples over a large catalogue of
  repetitive rules.
- Load detailed information just in time using stable references such as file
  paths, symbols, queries, and links.
- Use repository structure, naming, and metadata as navigation signals.
- Apply progressive disclosure: discover broad structure first, then read only
  the evidence needed for the next decision.
- Compact long histories carefully and preserve decisions, unresolved work,
  errors, and current state in structured form.
- Use external notes or artifacts when important state must survive beyond the
  active context window.
- Delegate isolated investigations to subagents when their verbose search traces
  would pollute the main task context.

## Risks to avoid

- Loading a whole repository or full knowledge graph before naming the question.
- Expanding `AGENTS.md` until every task pays the token and attention cost of
  every rule.
- Keeping old summaries after code or module ownership has changed.
- Treating retrieval as proof instead of checking the authoritative source.
- Returning huge tool outputs when a focused query or structured result would
  preserve the same evidence.
- Hiding tool errors or intermediate state that the next decision depends on.

## Application to codex-python

The repository's evidence hierarchy is compatible with this model:

1. Use `AGENTS.md` and project principles to identify the required workflow.
2. Locate the Rust crate and module using manifests or the knowledge graph.
3. Read the smallest authoritative Rust source and tests.
4. Read the corresponding Python owner and tests.
5. Keep unrelated uncovered modules out of the active task context.
6. Record durable mapping evidence in manifests and module documentation rather
   than relying on a conversation summary.

For runtime parity, capture the actual model context and tool registry in a
normalized form. Comparing only final UI text cannot reveal missing tools,
instructions, permissions, or state metadata.

## Review checklist

- Which tokens in the current context are authoritative?
- Which are merely navigation hints or historical summaries?
- Is the owning module and its contract present?
- Are tool schemas concise, distinct, and complete?
- Can bulky evidence be retrieved on demand instead of injected globally?
- Will critical state survive compaction, restart, or handoff?
