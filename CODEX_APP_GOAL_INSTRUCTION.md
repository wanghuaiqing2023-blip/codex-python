# Codex App Goal Instruction

## Purpose

Use this file as the long-running goal instruction for continuing the Python port of OpenAI Codex.

The project ports the upstream Rust implementation in `codex/` to Python in `pycodex/`. The goal is not a mechanical file translation. The goal is behavior-preserving migration of the core Codex experience, with a stable Rust-tree-based structure that both humans and Codex can use to reason about progress.

## Copyable goal instruction

```text
/goal Continue the OpenAI Codex Rust-to-Python port in this repository.

Authoritative source:
- Treat `codex/` as the authoritative Rust implementation.
- Treat `codex/.understand-anything/knowledge-graph.json` as a navigation index only.
- Use the knowledge graph to locate crates, modules, dependencies, imports, exports, calls, and likely entrypoints.
- Confirm behavior from Rust source code before changing Python code.

Target implementation:
- Implement the port in `pycodex/`.
- Prefer Python standard-library implementations.
- Do not introduce new third-party dependencies unless the dependency is clearly necessary and explicitly approved.
- Preserve core logic and common user-facing behavior as closely as practical.

Current priority:
- Focus on the common Codex runtime path first:
  `CLI entrypoint -> config/context assembly -> model request -> stream/response handling -> tool dispatch -> file/shell/patch execution -> final answer`.
- Give especially high priority to `codex exec` and interactive task execution.
- Defer MCP, plugin marketplace, cloud tasks, telemetry, app-server daemon, remote control, multi-agent orchestration, and other extension systems unless the core runtime needs a small compatibility shim.

Structural principle:
- Use the upstream Rust tree as the stable reference structure.
- At the crate level, register every upstream Rust crate in the Python migration map, even if it is not implemented yet.
- At the Rust module level, map modules one-to-one where practical.
- If exact one-to-one mapping is not practical, document the reason and choose the closest behavior-preserving Python coordinate.
- Existing Python code must be moved into the canonical Rust-corresponding Python coordinate when possible.
- Old duplicate paths should not remain as parallel implementations. If compatibility imports are temporarily needed, keep them thin and document them.

Alignment unit:
- The default behavior-alignment unit is the Rust module.
- Use crate-level alignment for global structure and dependency planning.
- Use function-level or quasi-function-level alignment only for high-risk public contracts, shared data types, policy decisions, tool handlers, or bug localization.
- Do not use vague mainline labels as the primary progress model. Progress should be tied to Rust crates, Rust modules, and their Python coordinates.

Work selection rule:
- Before choosing a new implementation task, answer:
  "Based on the upstream Rust dependency graph, which crate/module on the core runtime path unlocks the largest amount of user-visible behavior with the smallest safe Python-only slice?"
- Prefer graph-selected core runtime progress over open-ended local edge-case scanning.
- Prefer one coherent end-to-end slice over many disconnected helper ports.
- Prefer moving existing Python work into the correct coordinate before rewriting functionality.

Per-module workflow:
1. Locate the upstream Rust crate and module using the knowledge graph.
2. Read only the authoritative Rust source files needed for the selected module.
3. Identify the module's public behavior boundary:
   exports, public structs/enums/functions, data contracts, user-visible errors, event shapes, side effects, and tests.
4. Locate or create the corresponding Python coordinate under `pycodex/`.
5. Move existing Python code into that coordinate if it already implements the behavior.
6. Implement the smallest behavior-preserving Python slice.
7. Add or adjust focused tests for the touched behavior.
8. Record progress in status/notes with Rust source anchors, Python target files, validation, and known gaps.

Per-crate success condition:
- A crate is considered complete for the current migration phase only when:
  - It is registered in the migration structure.
  - Its relevant Rust modules are mapped to Python coordinates or explicitly marked deferred/out-of-scope.
  - Core-path modules inside the crate have behavior-preserving Python implementations.
  - Extension-only modules are shimmed or deferred with documented rationale.
  - There are no known duplicate Python implementations for the same Rust behavior.
  - Focused tests or documented evidence cover the implemented public behavior.
  - Remaining gaps are explicit and do not block the selected core runtime path.

Per-module success condition:
- A Rust module is considered complete for the selected phase only when:
  - Its Rust source path and Python target path are recorded.
  - Its public behavior boundary is understood from Rust source, not only from the graph.
  - Existing Python code has been moved or connected to the canonical coordinate.
  - Public data shapes, return values, errors, ordering, and side effects relevant to common use are matched.
  - Extension-only or unsupported branches are explicitly shimmed, deferred, or marked out-of-scope.
  - Focused Python tests cover the implemented behavior, preferably derived from Rust unit tests when available.
  - The module can be used by its upstream/downstream Python callers without requiring a parallel old implementation.

Slice termination condition:
- A work slice must stop when:
  - The selected Rust crate/module behavior has been mapped and implemented for the intended scope.
  - Focused validation for touched behavior has passed, or a concrete blocker has been documented.
  - Status notes identify what was aligned, what remains deferred, and what downstream path was unblocked.
- Do not continue scanning the same completed slice without a new concrete hypothesis, failing test, missing Rust source anchor, or user-visible blocker.

Testing principle:
- Prefer existing upstream Rust tests as the first clue for behavior.
- When Rust tests are not directly reusable, write Python parity tests that document their Rust source or behavior source in comments.
- Use golden/differential tests when the Rust behavior can be run deterministically.
- Validate only the touched behavior unless broader validation is explicitly requested.

Documentation principle:
- Important progress must be recorded.
- Use root-level status or porting notes to record:
  Rust crate/module, Rust source files, Python target files, behavior contract, tests run, known gaps, and deferred branches.
- Keep deprecated ledgers clearly marked as deprecated if they no longer match the current module-tree strategy.

Bug localization principle:
- When a bug appears, first identify the Rust crate/module and Python coordinate responsible for that behavior.
- Compare behavior inside that local module contract before changing unrelated paths.
- Avoid broad rewrites. Prefer small local corrections tied to a Rust source anchor.

Final objective:
- Produce a Python Codex implementation whose core user-facing behavior is explainably close to upstream Rust Codex.
- The project should know what is aligned, what is shimmed, what is deferred, and why.
```

## Status vocabulary

Use these status labels when recording crate/module progress:

- `registered`: the upstream Rust crate or module is recorded, but no implementation decision has been made.
- `mapped`: the Rust coordinate and Python coordinate are known.
- `implemented`: the intended Python behavior exists for the selected scope.
- `verified`: focused tests or strong evidence validate the implemented behavior.
- `shim`: a lightweight compatibility implementation exists, usually for deferred extension behavior.
- `deferred`: intentionally postponed because it is outside the current core runtime objective.
- `gap`: a known missing behavior or mismatch.

## Practical interpretation

The project should not measure progress by repeated broad scans of the same mainline. It should measure progress by completed Rust-tree coordinates.

The knowledge graph answers: "Where is the relevant Rust behavior and what depends on it?"

The Rust source answers: "What exactly must the Python behavior do?"

The Python tree answers: "Where does this behavior live in the port?"

The tests and notes answer: "How do we know this slice is done enough to move forward?"
