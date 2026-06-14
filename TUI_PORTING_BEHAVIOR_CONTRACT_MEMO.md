# TUI Porting Behavior Contract Memo

Date: 2026-06-11

## Context

This project ports OpenAI Codex from the upstream Rust implementation in `codex/` to Python in `pycodex/`.

For `core`, the project has mostly followed Rust crate/module ownership, public APIs, behavior contracts, and Rust test parity. That method works well for logic-heavy runtime modules.

For `tui`, we agreed that the porting method must be different. The Rust `tui` crate is not just logic; it is terminal interaction, rendering, input editing, snapshots, event routing, and user experience. Therefore, Python should not mechanically translate Rust TUI implementation line by line. Instead, Python should reproduce the behavior expressed by Rust TUI tests and snapshots.

Short version:

```text
core should be like Rust.
tui should feel like Codex.
```

## Goal

The project should not settle for a simplified or basic TUI. A simplified TUI would make the Python port lose much of its meaning, because the user-facing Codex experience would diverge from Rust Codex.

The goal is full TUI behavior parity over time.

However, full TUI parity does not mean all extension runtimes must be implemented immediately. MCP, skills, plugins, marketplace, and similar extension runtimes can still be phased, but the TUI structure, states, views, and user-visible behavior should preserve the Rust Codex contract and leave clear integration points.

## Why TUI is high risk

The Rust `tui` crate is large and complex.

Measured from local upstream Rust source, after excluding obvious test files:

```text
tui strict production Rust files: 295
tui strict production Rust lines: 148,187
```

This is larger than the measured `core` production-code body.

Large Rust TUI files include:

```text
src/bottom_pane/chat_composer.rs              9,518 lines
src/resume_picker.rs                          5,767 lines
src/bottom_pane/textarea.rs                   3,384 lines
src/bottom_pane/request_user_input/mod.rs     3,047 lines
src/bottom_pane/mod.rs                        2,648 lines
src/keymap.rs                                 2,598 lines
src/markdown_render.rs                        2,550 lines
src/diff_render.rs                            2,276 lines
src/bottom_pane/approval_overlay.rs           2,225 lines
src/app/event_dispatch.rs                     2,116 lines
src/chatwidget/plugins.rs                     2,042 lines
```

The complexity is mostly in:

- terminal input and editing behavior,
- streaming output,
- message and history rendering,
- approval overlays,
- diff/markdown rendering,
- session resume and thread routing,
- keyboard shortcuts,
- terminal resize/reflow,
- cross-platform terminal behavior.

The biggest risks for a Python implementation are:

- terminal UI library differences (`ratatui`/`crossterm` vs Python libraries),
- multi-line input and cursor behavior,
- Unicode/wide-character behavior,
- streaming/event ordering,
- visual rendering drift,
- Windows terminal behavior,
- snapshot and PTY test infrastructure.

## Why Rust TUI tests are valuable

The Rust `tui` crate already contains a large behavior test surface.

Local inventory found approximately:

```text
Rust TUI test functions: 2684
Rust files with tests: 176
Rust TUI snapshot files: 481
```

High-density test areas include:

```text
src/bottom_pane/chat_composer.rs                  163 tests
src/app/tests.rs                                  110 tests
src/chatwidget/tests/status_and_layout.rs         107 tests
src/markdown_render_tests.rs                      102 tests
src/history_cell/tests.rs                          95 tests
src/resume_picker.rs                               91 tests
src/chatwidget/tests/slash_commands.rs             83 tests
src/bottom_pane/textarea.rs                        77 tests
src/chatwidget/tests/popups_and_settings.rs        67 tests
src/bottom_pane/request_user_input/mod.rs          63 tests
src/chatwidget/tests/plan_mode.rs                  61 tests
src/keymap.rs                                      60 tests
src/diff_render.rs                                 48 tests
src/chatwidget/tests/exec_flow.rs                  48 tests
src/streaming/controller.rs                        45 tests
```

Snapshot distribution:

```text
chatwidget snapshots: 173
bottom_pane snapshots: 155
src-root snapshots: 92
history_cell snapshots: 42
status snapshots: 15
total snapshots: 481
```

These tests and snapshots should be treated as the primary behavior-contract source for the Python TUI port.

## Porting principle for TUI

Do not mechanically translate Rust TUI implementation line by line.

Instead:

```text
Rust source/test/snapshot evidence -> behavior contract -> Python implementation -> Python behavior/snapshot tests
```

Rust module/file structure is still useful for planning and inventory, but acceptance should be based on observable behavior.

Python implementation may use different classes, layout mechanisms, or event loops if the behavior contract is preserved.

## Behavior contract granularity

Use layered behavior contracts, not a single granularity.

### Level 1: Pure helper contracts

Examples:

- key normalization,
- terminal title sanitization,
- wrapping helpers,
- markdown parsing helpers,
- table detection,
- width calculations.

Test style:

```text
input -> output
```

### Level 2: Component state contracts

Examples:

- textarea cursor movement,
- composer paste/backspace behavior,
- history search state,
- approval overlay selection,
- request-user-input selection,
- resume picker selection/filtering.

Test style:

```text
initial state + key sequence -> expected state
```

### Level 3: Operation emission contracts

Examples:

- pressing Enter submits a user turn,
- approval overlay emits an approval decision,
- interrupt key emits interrupt/shutdown behavior,
- resume picker emits resume selection.

Test style:

```text
user action -> expected core/app operation
```

### Level 4: Event transition contracts

Examples:

- core/app event updates active turn state,
- agent-message delta updates streaming cell,
- tool-call begin/end updates history cell,
- request-user-input event opens bottom pane UI,
- turn completed clears pending state.

Test style:

```text
event sequence -> TUI state + visible output
```

### Level 5: Visual snapshot contracts

Examples:

- chat composer rendering,
- footer/status rendering,
- markdown rendering,
- diff rendering,
- history cell rendering,
- resume picker rendering,
- approval overlay rendering.

Test style:

```text
fixed state + fixed terminal dimensions + fixed theme -> screen snapshot
```

### Level 6: End-to-end interaction scripts

Examples:

- type prompt, submit, stream assistant answer,
- shell approval prompt, accept, command output displayed,
- slash command opens popup, select item,
- resume picker navigation and restore,
- resize reflows transcript.

Test style:

```text
scripted key/event sequence -> final screen + emitted operations
```

## Visual behavior is measurable

TUI visual behavior can be measured because terminal output can be represented as structured screen data.

Measurable objects include:

- cell character,
- row/column position,
- foreground/background color,
- styles such as bold/dim/underline/reverse,
- border characters,
- line wrapping,
- truncation/ellipsis,
- cursor position and visibility,
- viewport/scroll offset,
- overlay bounds,
- ANSI reset behavior.

Preferred representation:

```text
ScreenBuffer(width, height, cells, cursor, styles)
```

Snapshot forms:

```text
*.txt.snap       text/layout snapshot
*.style.json     style/color snapshot
*.cursor.json    cursor snapshot
```

Two visual parity modes are allowed:

### Strict visual parity

Use for stable, strongly visible components:

- approval overlay,
- footer,
- status line,
- diff render,
- resume picker,
- history cell.

Compare:

- text,
- position,
- bounds,
- styles/colors.

### Normalized visual parity

Use where Python/Rust library rendering differs but semantics must match:

- markdown render,
- streaming output,
- chat composer complex layout,
- large transcript views.

Normalize only with documented rules, such as:

- strip trailing spaces,
- normalize ANSI reset sequences,
- normalize equivalent border glyphs only if intentionally adapted,
- preserve text order, visible labels, layout bounds, and color semantics.

## Metrics we can track

TUI behavior parity should be measurable with explicit counters.

Suggested metrics:

```text
rust_tui_tests_total
rust_tui_snapshots_total
behavior_contracts_total
behavior_contracts_mapped
behavior_contracts_passed
snapshots_total
snapshots_mapped
snapshots_passed
critical_flows_total
critical_flows_passed
```

Visual-specific metrics:

```text
text_snapshot_passed
style_snapshot_passed
cursor_snapshot_passed
layout_invariants_passed
unicode_width_invariants_passed
resize_reflow_invariants_passed
```

For each behavior contract:

```text
Contract ID
Rust source/test/snapshot evidence
Python component
Contract type
Input/events/state
Expected state/output/operation
Python test
Status
Deferred dependencies
```

## Suggested files to create

Create these files before starting major TUI port work:

```text
TUI_PORTING_STATUS.md
TUI_RUST_TEST_PARITY.md
TUI_BEHAVIOR_CONTRACTS.md
```

### TUI_PORTING_STATUS.md

Tracks implementation status by Rust TUI area and Python component.

### TUI_RUST_TEST_PARITY.md

Inventory of Rust TUI test functions and snapshots, mapped to Python tests.

### TUI_BEHAVIOR_CONTRACTS.md

Behavior-contract ledger, grouped by user-visible behavior rather than only Rust file path.

## Suggested first implementation order

Start with the highest-impact, most measurable contracts:

1. `textarea` and `chat_composer` input behavior.
2. `keymap` and key event normalization.
3. `markdown_render` text rendering.
4. `diff_render` patch rendering.
5. `history_cell` rendering.
6. `chatwidget` message/status/layout behavior.
7. `approval_overlay` behavior and snapshots.
8. `resume_picker` behavior and snapshots.
9. `streaming/controller` behavior.
10. VT100/PTY-style integration scripts.
11. Larger `app/tests.rs` state-transition contracts.

## Testing harness recommendation

Build a Python TUI test harness early.

Suggested directory:

```text
tests/tui_harness/
```

Suggested capabilities:

- construct deterministic TUI state,
- send key events,
- inject core/app events,
- render to `ScreenBuffer`,
- compare text snapshots,
- compare style snapshots,
- assert cursor position,
- assert layout invariants,
- normalize ANSI output with documented rules,
- eventually run scripted PTY/terminal tests.

## Technology note

A full Python TUI likely needs a mature terminal UI/input library. Candidate approaches discussed:

- `prompt_toolkit` for input editing and full-screen terminal apps,
- `rich` for rendering support,
- possibly `textual` for a more complete app framework, though it may diverge more from the Rust Codex feel.

This should be decided deliberately before large TUI implementation begins.

## Final agreement

The agreed strategy is:

```text
Do not line-by-line translate Rust TUI implementation.
Do port the behavior expressed by Rust TUI tests and snapshots.
Make behavior and visual parity measurable through tests.
Use Rust tests/snapshots as the primary contract source.
Keep TUI full-parity as the goal, not a simplified clone.
```
