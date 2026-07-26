# Building Effective Agents

> Structured notes based on the official Anthropic engineering article. This
> is a paraphrased project reference, not a verbatim republication.

## Source

- Publisher: Anthropic
- Authors: Erik Schluntz and Barry Zhang
- Published: December 19, 2024
- Official article: <https://www.anthropic.com/engineering/building-effective-agents>
- Retrieved: July 20, 2026

## Core argument

Successful agent systems usually begin with simple, composable patterns rather
than a large framework. Complexity is justified only when a measured task needs
it. Extra orchestration increases cost, latency, hidden state, and debugging
difficulty, so it must provide observable value.

Anthropic distinguishes two broad structures:

- A workflow follows code-defined paths and is appropriate when the stages are
  predictable.
- An agent lets the model choose steps and tools dynamically and is appropriate
  when the path cannot be known in advance.

Confusing these forms can create architectural drift. A deterministic rule that
belongs in code should not become an improvised model behavior, while an
open-ended investigation should not be forced through brittle hard-coded steps.

## Patterns and their boundaries

- Prompt chaining splits a stable sequence into smaller, checkable stages.
- Routing sends distinct request classes to specialized paths.
- Parallelization helps when work is independent or multiple judgments improve
  confidence.
- Orchestrator-worker designs help when subtasks must be discovered dynamically.
- Evaluator-optimizer loops help when quality criteria are explicit and feedback
  can measurably improve the output.
- Autonomous agents fit open-ended tasks with trustworthy environmental feedback
  and clear stopping conditions.

These are building blocks, not a mandate to use all of them. Adding a pattern
without evidence produces redundant ownership and makes failures harder to
localize.

## Anti-drift controls

1. Keep the architecture as small as the task permits.
2. Expose planning and intermediate steps so that behavior remains inspectable.
3. Give agents ground truth through tool results, code execution, tests, and
   environment state.
4. Design the agent-computer interface as carefully as a human-computer
   interface.
5. Document tool purpose, parameters, examples, edge cases, and boundaries from
   neighboring tools.
6. Test tools with realistic inputs and redesign their interfaces when repeated
   misuse reveals ambiguity.
7. Use stopping conditions, checkpoints, sandboxing, and human review where
   autonomy can compound errors.

## Application to codex-python

- Do not add a Python-only execution path when the Rust owner already defines
  the behavior through an existing module and event chain.
- Treat every facade, adapter, and special case as an architectural assumption
  that needs a named owner and a parity test.
- Prefer module-scoped contracts over one giant end-to-end controller.
- Keep tool registration and schemas visible enough to compare Rust and Python
  context directly.
- Use integration tests for multi-module event flow, while preserving unit and
  manifest tests for local ownership.
- Remove abstractions that merely obscure prompts, events, or tool calls without
  producing measured parity value.

## Review checklist

- Is this behavior a workflow rule or an agent decision?
- Is the selected pattern simpler than the alternatives?
- Are intermediate decisions and tool results observable?
- Does each tool have one clear purpose and owner?
- Is completion checked against environment state?
- Would deleting this new layer preserve behavior? If so, it may be redundant.
