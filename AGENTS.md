# AGENTS.md

## Mission and authority

This project ports OpenAI Codex from the upstream Rust implementation in
`codex/` to Python in `pycodex/`. Preserve core logic and common user-facing
behavior as closely as possible. Prefer the Python standard library unless a
dependency is clearly necessary and approved.

`PORTING_PROJECT_PRINCIPLES.md` is the highest-level methodology for this
port. This file keeps the rules that must be applied on every task; consult the
principles document for their rationale and fuller treatment.

Rust is the behavioral source of truth. Use this evidence order:

1. Cargo workspace and crate `Cargo.toml` files.
2. Rust `mod`, `pub mod`, `use`, and `pub use` declarations.
3. Public APIs, important internal items, trait impls, and runtime registration
   points.
4. Rust unit tests, integration tests, fixtures, and generated outputs.
5. Knowledge-graph metadata for navigation only.

## Non-negotiable porting rules

- The alignment target is the whole Rust source tree, organized as:
  `workspace -> crate -> module -> item/type -> Rust test -> Python counterpart`.
- The regular minimum alignment and acceptance unit is a
  `module-scoped behavior contract`, not an execution mainline, isolated file,
  function ledger, or whole crate.
- Before changing Python behavior, identify the owning Rust crate and module,
  the API or runtime anchor that defines it, the Rust tests or fixtures that
  describe it, and the corresponding Python module and tests.
- Confirm behavior against Rust source. Similar output, a Python-only test, or
  knowledge-graph metadata is not parity evidence by itself.
- Treat neighboring modules as interface constraints. Do not silently expand
  a module task into all upstream or downstream dependencies. Use existing
  facades, narrow shims, focused test doubles, or documented follow-up debt
  when they are sufficient to prove the selected module's contract.
- Do not implement Python-specific shortcuts, one-off command branches,
  rendering exceptions, runtime bypasses, or test-only adapters in place of
  the Rust-owned architecture.
- Execution mainlines discover runtime gaps and validate module collaboration;
  they do not define ownership. Localize a runtime defect to its owning Rust
  module before editing Python.
- Keep Python package and module structure aligned with Rust coordinates where
  practical. Document intentional merges, splits, or adaptations near the
  package, preferably in its `README.md`. Do not retain duplicate old paths
  unless an intentional compatibility package is documented.
- Prefer the smallest coherent implementation that closes the selected module
  contract. Record unrelated parity gaps as follow-up work instead of repairing
  adjacent modules opportunistically.

## Active scope

Prioritize the core and commonly used Codex experience:

- CLI entrypoints for `exec` and interactive task execution.
- The agent loop, model request construction, streaming, tool dispatch, and
  final responses.
- Context, instructions, working directory, model/config selection, and
  conversation/session state.
- Shell, file, patch, approval, sandbox, and safety behavior.
- The Rust-aligned terminal TUI and the protocol/event surfaces required by
  the CLI and core runtime.

MCP, plugins, marketplace, cloud tasks, remote execution, multi-agent systems,
telemetry, update services, and app-server transport are outside the active
scope unless the user explicitly asks for them or the core runtime requires a
compatibility boundary. Prefer lightweight compatibility shims, preserve
already-working behavior, and document known gaps rather than expanding these
areas by default.

## Module workflow and acceptance

Before starting a port or parity fix, answer:

1. Which Rust crate and module own the behavior?
2. Which public API, internal item, trait impl, or runtime registration point
   anchors it?
3. Which Rust tests, fixtures, or source contracts describe it?
4. Which Python package/module should own it?
5. Which Python tests will prove parity?

Then implement and validate only the smallest coherent slice. A module is
complete when its own public APIs, important internal items, trait behavior,
runtime anchors, and relevant Rust tests/fixtures are mirrored or intentionally
adapted and evidenced in Python. Do not block module completion only because a
neighboring transport, UI, persistence, extension, or orchestration module is
incomplete.

Mainline smoke tests should follow module work and verify collaboration, for
example `exec -> context -> model request -> stream -> tool dispatch -> final
answer`. If they expose a new defect, map it back to its Rust module before
fixing it.

## Navigation and test evidence

Use `codex/.understand-anything/knowledge-graph.json` selectively to locate
Rust files, symbols, dependencies, layers, and runtime anchors before broad
searches. It is an index of `codex/`, not a source of truth and not a map of
`pycodex/`. Query only the relevant nodes or edges, then verify every behavior
and dependency claim against the smallest authoritative Rust sources. Repeated
broad scans without a named purpose are a process smell.

Tests should be derived, in order of preference, from Rust unit tests, Rust
integration tests, explicit Rust source contracts, stable golden behavior, and
finally Python regression or policy requirements. When practical, Python tests
should name the Rust crate, module, test, and behavior contract they port.
Python-only behavior must not be labeled Rust parity without such evidence.

Golden tests are useful for stable serializable modules, but they are not the
default for complex runtime paths. Pin them to a specific Rust reference body.

## Terminal TUI framework discipline

The supported UI is the Rust-aligned terminal TUI; there is no maintained
Textual path. Follow `pycodex/tui/README.md` and its fixed Rust baseline.
Python terminal adapters may translate ANSI, Windows console, or scrollback
details, but they do not own slash commands, selections, approvals, history,
model state, or resize semantics.

Slash-command behavior must use this ownership map:

- `slash_command`: registry, names, aliases, visibility, inline arguments, and
  availability.
- `bottom_pane::command_popup` and `bottom_pane::slash_commands`: filtering,
  ordering, selection, display flags, and completion candidates.
- `bottom_pane::chat_composer`: first-line slash detection, draft mutation,
  popup routing, and Tab/Enter/Esc/Up/Down semantics.
- `chatwidget::slash_dispatch`: dispatch, local-vs-user-turn decisions, inline
  argument preparation, guards, and queued behavior.
- `BottomPaneView`, `SelectionViewParams`, `ListSelectionView`, or another
  Rust-aligned active view: interactive command UI.
- Bottom-pane frame state and the terminal render adapter: rendering.

The required path is:

```text
tui::event_stream
  -> bottom_pane::chat_composer
  -> command_popup / slash_dispatch / active BottomPaneView
  -> bottom-pane frame model
  -> terminal render adapter
```

Never fix only `/model`, `/permissions`, `/goal`, `/keymap`, or another command
through a terminal/runtime special case. Locate the owning framework layer and
fix the entire affected category: discovery/completion, local immediate,
inline-argument, view-opening, guarded/contextual, or alias commands. Test the
affected category and at least one adjacent category.

Slash/TUI regression coverage must verify normal and IME text, popup placement,
filtering and selection, Tab completion, Enter dispatch, Esc behavior, local
commands not becoming user turns, inline arguments, active-view routing,
guards, aliases, cursor behavior, and bottom-pane frame rendering as applicable
to the touched contract.

## Change and documentation discipline

- Preserve module boundaries and dependency direction; do not trade parity for
  a locally convenient Python design.
- Add concise comments only where the implementation is not self-explanatory.
- Validate the touched behavior unless broader validation is explicitly
  requested.
- Update `PORTING_STATUS.md` only for meaningful module-status changes.
- Keep durable evidence in module `README.md` files, Rust-derived tests, and
  focused alignment documents. Do not create per-turn migration logs.
