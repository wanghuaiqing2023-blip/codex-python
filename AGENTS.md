# AGENTS.md

## Project mission

This project ports OpenAI Codex from the upstream Rust implementation in `codex/` to Python in `pycodex/`.

The goal is to preserve the core logic and common user-facing behavior as closely as possible while avoiding complex Python third-party dependencies. Prefer Python standard-library implementations unless a dependency is clearly necessary and approved.

## Highest-level porting methodology

`PORTING_PROJECT_PRINCIPLES.md` is the current highest-level methodology for this port. It supersedes earlier mainline-first and function-ledger thinking when those conflict with the rules below.

The alignment target is the whole upstream Rust code tree, not only one execution mainline. Use this coordinate system when scoping, implementing, reviewing, or testing work:

```text
Rust workspace
  -> Rust crate
    -> Rust module
      -> Rust item/function/type
        -> Rust tests
          -> Python package/module/item/test
```

Important distinctions:

- Containment structure is mostly a tree.
- Dependency structure is a directed graph.
- Runtime dispatch is a dynamic graph.

Do not collapse these into a single mainline. Execution mainlines are validation paths; Rust crate/module boundaries are the default alignment map.

The regular minimum alignment and acceptance unit is a `module-scoped behavior contract`.

### Module boundary and dependency handling

Module-scoped porting should focus on the selected Rust module's own behavior contract, not on completing every upstream or downstream dependency at the same time.

Use dependency relationships to understand the selected module's inputs, outputs, types, invariants, call semantics, and runtime anchors. Do not let dependency relationships silently expand the acceptance unit beyond the selected module.

This keeps module porting independent and parallelizable: separate modules can be implemented, audited, or promoted without waiting for all neighboring modules to be complete.

When validating a module:

- Treat dependent modules as interface constraints for the current module, not as additional implementation scope.
- A module can be considered complete when its own public APIs, important internal items, trait impls, runtime registration points, and Rust tests/fixtures are mirrored or intentionally adapted in Python.
- Missing or partial Python implementations of neighboring modules should be handled with existing facades, lightweight shims, focused test doubles, or documented follow-up debt when that is enough to verify the selected module.
- Do not block module completion merely because downstream runtime orchestration, transport, UI, persistence, or extension behavior is incomplete.

In practical terms:

- Crate decides ownership and dependency context.
- Module provides the default behavior boundary.
- Public APIs, important internal items, trait impls, and runtime registration points provide local anchors.
- Tests and fixtures provide evidence.
- Function-level alignment is allowed for pure functions, public APIs, or small well-tested units, but it is not the default minimum unit.
- Whole-crate alignment is usually too coarse for implementation acceptance, though crate-level registration should still be tracked.

Where practical, Python directory and file structure should encode the Rust counterpart structure. If Python merges, splits, or adapts Rust modules for idiomatic reasons, document that mapping close to the code, preferably in the package `README.md`. Do not keep duplicate old paths after a migration unless a compatibility package is intentionally retained and documented.

## Current implementation priority

Current scope decision: first replicate Codex's core and commonly used features. MCP, plugin, marketplace, and other extension capabilities are not part of the active implementation target unless the core runtime directly needs a compatibility shim.

Focus on the common and core Codex experience first:

- CLI entrypoints needed for normal use, especially `exec` and interactive task execution.
- Core agent loop: user input, model request construction, streaming/response handling, tool-call execution, and final answer generation.
- Context assembly: project instructions, working directory, environment metadata, model/config selection, and conversation/session state.
- File and command tools: shell execution, reading/writing files, applying patches, and returning tool results to the model.
- Approval/safety behavior: dangerous command handling, write/network/sandbox policy approximation, and clear user-facing errors.
- App-server protocol/event model only where it is needed by the CLI/core runtime path.

## Deprioritized extension areas

Do not spend significant implementation time on these until the core agent loop is useful and stable:

- MCP runtime and external MCP server integrations.
- Plugin marketplace, plugin install/cache details, and plugin runtime behavior.
- Marketplace management beyond compatibility stubs needed to avoid obvious CLI breakage.
- Skills/plugin discovery beyond what is required for the core prompt/context path.
- Multi-agent/sub-agent orchestration.
- Cloud tasks and remote task execution.
- Telemetry, analytics, update checks, and marketplace backend features.
- App-server daemon, proxy, remote control, websocket transport, and schema-generation paths, except where a small compatibility shim helps the core CLI flow.

## Compatibility rule for extension areas

For MCP/plugin/marketplace and similar extension areas:

- Prefer lightweight compatibility shims over deep implementation.
- Keep existing behavior from regressing when it is already implemented.
- Do not continue expanding these areas unless the user explicitly asks or the core runtime depends on them.
- Document known gaps instead of fully implementing non-core extension behavior.

## Upstream knowledge graph

The upstream Rust source tree in `codex/` has an understand knowledge graph at:

- `codex/.understand-anything/knowledge-graph.json`

Use this graph as a navigation aid before doing broad source searches. It is intended to reduce token usage and search time by helping identify relevant files, symbols, import relationships, layers, and tour entry points inside the upstream implementation.

The graph is an index, not the source of truth. Final dependency and behavior claims must be confirmed against Rust source code.

Authoritative evidence order:

1. Cargo workspace and crate `Cargo.toml` files for crate boundaries and direct crate dependencies.
2. Rust `mod`, `pub mod`, `use`, and `pub use` declarations for crate-internal module structure and visibility.
3. Rust public APIs, important internal items, trait impls, and runtime registration points for behavior contracts and dynamic anchors.
4. Rust unit tests, integration tests, fixtures, and generated outputs for behavioral verification.
5. Knowledge graph metadata for navigation only.

Recommended workflow when comparing or porting Rust behavior:

- Do not load the entire knowledge graph into model context.
- Query it selectively with small scripts or targeted JSON inspection, and summarize only the relevant nodes, edges, layers, or tour steps.
- Start with Cargo/module structure and the knowledge graph to locate likely upstream files and relationships.
- Then read the smallest authoritative Rust files needed for the behavior being ported.
- Cross-check against `pycodex/` only after the upstream behavior is clear.
- Prefer targeted searches guided by graph node paths and edge relationships over broad repository scans.
- Treat repeated broad scans as a smell. Use targeted re-scans only when the selected module boundary or dynamic anchor is unclear.

The graph was generated for `codex/` only. Do not assume it describes `pycodex/`, tests, or project files outside `codex/` unless a separate graph is generated for those areas.

## Source-tree and module-boundary priorities

When deciding what to implement next, use the upstream Rust crate/module structure as the first planning input, with dependency graph relationships as support. Do not choose work only because it appears next on an execution mainline.

### Prompt to use for task planning

Before choosing any new task, answer:

> "Which Rust crate owns this behavior? Which Rust module defines the behavior boundary? Which Rust public API, important internal item, or runtime registration point anchors it? Which Rust tests or fixtures describe it? Which Python package/module should carry it? Which Python tests prove parity?"

Then apply this filter:

1. Identify the Rust crate and module that own the behavior.
2. Confirm the module boundary through Cargo, `mod`, `pub mod`, `use`, and `pub use` evidence.
3. Identify public APIs, important internal items, trait impls, and runtime registration points that define the behavior contract.
4. Use the knowledge graph to understand dependencies, fan-in/fan-out, and dynamic anchors.
5. Map the behavior to the corresponding `pycodex/` package/module path, creating or moving structure when the Rust coordinate is clear.
6. Implement the smallest coherent Python slice that preserves the module-scoped behavior contract.
7. Record skipped peripherals as follow-up debt rather than parallel parity work.
8. Confirm each behavior claim against Rust source, not just Rust graph metadata.

Priority workflow:

- Start from Rust crate/module ownership for the behavior being changed.
- Prefer modules that are both core to common Codex usage and high fan-in/fan-out on dependency or runtime paths.
- Rank work by whether it closes a module-scoped behavior contract and improves an end-to-end common Codex flow.
- Filter out MCP/plugin/marketplace/cloud/TUI branches unless the dependency path shows they are required for the core runtime slice being implemented.
- After identifying the Rust behavior slice, map it to the corresponding `pycodex/` package/module and implement only the smallest safe slice.
- Use execution mainlines such as `exec -> context -> model request -> stream handling -> tool dispatch -> final answer` to validate module collaboration, not to define the architecture.

## Execution mainlines as validation paths

Execution mainlines are still important, but their role is to discover runtime gaps and validate that module contracts collaborate correctly.

Correct use:

```text
mainline discovers runtime gaps
module contracts solve the gaps
mainline validates module collaboration
```

Incorrect use:

```text
follow the mainline and implement whatever appears next
```

Use this balance when choosing work:

- Prefer module-scoped behavior closure over open-ended adjacent edge-case scanning.
- Use mainline tests and smoke runs to validate connected behavior after a module slice changes.
- When a runtime issue appears, localize it to the owning Rust crate/module before changing Python.
- When a parity issue is outside the current module contract, document it as follow-up unless it is a clear regression or a small compatibility shim needed by core use.
- Treat repeated scans after all known branches are marked complete as a process warning. Re-scan only with a named purpose, such as import migration, path cleanup, encoding damage, or test discovery.
- A healthy default split is roughly 60-70% crate/module behavior alignment, 20-30% focused parity tests or mainline validation for touched modules, and 10% documentation/status cleanup.

## Tests and evidence

Testing should primarily reuse or derive from Rust's own tests.

Preferred test source order:

1. Rust unit tests in `#[cfg(test)] mod tests` or `src/*_tests.rs`.
2. Rust integration tests in `tests/` or `tests/suite/`.
3. Rust source behavior contracts inferred from authoritative source code.
4. Targeted golden tests for stable, serializable modules.
5. Python regression and project-policy tests that protect local implementation choices.

Python tests should include source comments when possible, naming the Rust crate, module, test, and behavior contract. Tests written only from Python behavior must not be treated as Rust parity proof unless tied back to Rust source, Rust tests, or a documented behavior contract.

Golden tests are versioned behavior snapshots against a specific Rust Codex reference body. They are useful for stable serializable modules, but they are not the default first step for complex runtime paths.

## TUI slash-command framework discipline

This project no longer maintains a Textual UI path. Slash-command behavior must be implemented through the Rust-aligned terminal TUI framework only.

All slash-command work must be framework-based, not command-specific terminal patches. Do not fix only `/model`, `/permissions`, `/keymap`, or any single command by adding special-case behavior in terminal runtime, terminal surface, or rendering glue.

Bugs may be discovered through one command, but fixes must live at the framework layer and be verified at the category level. If a bug is discovered through one slash command, first identify the framework layer that owns the behavior, then fix that layer so all commands in the same category benefit. Do not leave behavior in one-off command branches, runtime shortcuts, rendering exceptions, or test-only adapters.

The Rust-aligned ownership map is:

- `slash_command` owns command registry, canonical names, aliases, visibility, inline-argument support, and availability rules.
- `bottom_pane::command_popup` and `bottom_pane::slash_commands` own popup filtering, ordering, selected row state, display flags, and completion candidates.
- `bottom_pane::chat_composer` owns first-line slash detection, draft mutation, popup routing, and Tab/Enter/Esc/Up/Down semantics.
- `chatwidget::slash_dispatch` owns command dispatch, local-vs-user-turn decisions, inline argument preparation, guard checks, and queued command behavior.
- Commands that open interactive UI must route through `BottomPaneView`, `SelectionViewParams`, `ListSelectionView`, or another Rust-aligned active view.
- Terminal rendering must go through the bottom-pane frame model: state -> frame -> terminal render adapter.

The required terminal TUI path is:

```text
tui::event_stream
  -> bottom_pane::chat_composer
  -> command_popup / slash_dispatch / active BottomPaneView
  -> bottom-pane frame model
  -> terminal render adapter
```

Slash-command fixes must be category-based. When touching slash behavior, verify the affected category and at least one adjacent category:

- Discovery and completion: `/`, filtered input such as `/m`, Up/Down selection, Tab completion, Enter dispatch.
- Local immediate commands: examples include `/clear`, `/status`, `/quit`, `/exit`, `/raw`, `/diff`, `/copy`, `/mention`.
- Inline-argument commands: examples include `/review`, `/rename`, `/goal`, `/plan`, `/raw`, `/mcp`, `/keymap`, `/resume`, `/side`.
- View-opening commands: examples include `/model`, `/permissions`, `/keymap`, `/memories`, `/settings`, `/apps`, `/plugins`, `/skills`, `/hooks`, `/agent`, `/multi-agents`, `/subagents`.
- Guarded/contextual commands: side-conversation-only, unavailable-during-task, review-only, login/session-dependent, or hidden commands.
- Alias commands: examples include `/quit` and `/exit`, `/clean`, `/pet`, `/approve`, `/subagents` and `/multi-agents`.

`/model` is only one representative view-opening command. It must not become a special implementation path. The same popup, selection, active-view stack, key handling, and frame rendering rules must apply to every slash-command category.

Any slash-command change must be regression-tested as a framework behavior, not as a single-command fix. At minimum, verify:

- Normal text and IME text still submit as user turns.
- `/` and filtered slash input show the popup in the expected bottom-pane location.
- Up/Down moves the highlighted candidate.
- Tab completes the highlighted slash command without executing it.
- Enter dispatches the selected or typed command according to Rust behavior.
- Local commands do not become user turns.
- Inline-argument commands preserve arguments and text elements.
- View-opening commands use the active-view stack and bottom-pane frame renderer.
- Guarded commands respect side conversation, active task, review mode, and visibility rules.
- The command being changed is tested together with at least one neighboring command category.

## Porting discipline

When implementing functionality:

- Use `codex/` as the authoritative source for Rust behavior.
- Prefer module-scoped behavior contracts over broad mainline chasing or file-only mapping.
- Keep Python structure aligned with Rust crate/module coordinates where practical, and document any intentional split/merge close to the code.
- Prefer narrow, behavior-focused slices that move Python closer to Rust Codex.
- Keep the implementation dependency-light and standard-library-first.
- Update `PORTING_STATUS.md` only for meaningful module-status changes. Keep
  durable evidence in module `README.md` files, Rust-derived Python tests, and
  focused alignment documents; do not create per-turn migration logs.
- Validate only the touched behavior unless broader validation is explicitly requested.
