# TUI interface scaffold status

Generated Python interface scaffolds from Rust `codex-tui` module files.

- Rust source root: `codex/codex-rs/tui/src`
- Python target root: `pycodex/tui`
- Module files processed: `300`
- Top-level Rust symbols scaffolded: `5330`
- Behavior status: interface boundary only, runtime behavior not implemented unless already present before this pass.

This file is separate from `TUI_RUST_TEST_PARITY.md`; it tracks interface boundary coverage, not behavior/test parity.

## Follow-up notes

- `updates.rs` adjacent integration note: Python `pycodex/tui/updates.py` currently defines `NPM_PACKAGE_URL` separately; when revisiting `updates.rs`, align it to import/use `pycodex.tui.npm_registry.PACKAGE_URL` and `ensure_version_ready` now that this module is implemented.

## 2026-06-12 - key_hint.rs

- Rust module: `codex-tui::key_hint`
- Python module: `pycodex.tui.key_hint`
- Status: `complete`
- Notes: Ported key-binding matching and display semantics: press/repeat filtering, shifted-letter normalization, raw C0 Ctrl compatibility, plain-text key classification, binding-list matching, constructor helpers, display labels/spans, modifier ordering, and platform AltGr handling. Python uses semantic key/modifier strings and `Span` DTOs instead of crossterm/ratatui values.
## 2026-06-12 - version.rs

- Rust module: `codex-tui::version`
- Python module: `pycodex.tui.version`
- Status: `complete`
- Notes: `CODEX_CLI_VERSION` mirrors Rust `env!("CARGO_PKG_VERSION")` for the current upstream workspace package version inherited by `codex-tui`; no framework or runtime behavior is involved.

## 2026-06-12 - debug_config.rs

- Rust module: `codex-tui::debug_config`
- Python module: `pycodex.tui.debug_config`
- Status: `complete_slice`
- Notes: Ported debug-config visible output semantics for config layers, disabled reasons, session flags, MDM raw TOML, requirement/source/value rows, web-search normalization, managed hooks, network domain/unix-socket constraints, filesystem deny-read rows, and session proxy URLs. Python keeps semantic config-stack DTOs and text lines rather than ratatui `Line` and concrete `codex_config` types.

## 2026-06-12 - cwd_prompt.rs

- Rust module: `codex-tui::cwd_prompt`
- Python module: `pycodex.tui.cwd_prompt`
- Status: `complete_slice`
- Notes: Ported cwd prompt action/selection/outcome semantics, prompt-screen key handling, frame scheduling, semantic redraw loop, paste-ignore behavior, default Session fallback, and resume/fork render text. Concrete ratatui modal rendering and real Tui event stream integration remain framework boundaries.

## 2026-06-12 - branch_summary.rs

- Rust module: `codex-tui::branch_summary`
- Python module: `pycodex.tui.branch_summary`
- Status: `complete_slice`
- Notes: Ported the TUI-owned git/PR status-line lookup semantics through injected workspace-command facades: branch-name trimming, optional best-effort failures, concurrent summary aggregation, remote/default-local branch resolution, merge-base numstat parsing, GitHub PR lookup fallback order, open-only PR filtering, and parent-first repo search order. Concrete `git`/`gh` execution remains owned by `workspace_command`.

## 2026-06-12 - additional_dirs.rs

- Rust module: `codex-tui::additional_dirs`
- Python module: `pycodex.tui.additional_dirs`
- Status: `complete`
- Notes: Ported the complete add-dir warning helper behavior with semantic permission profile and file-system policy models: empty add-dir suppression, disabled/external/full-disk/workspace-write no-warning branches, cwd write-permission checks including writable parent roots, and exact warning text/path joining.

## 2026-06-12 - streaming/chunking.rs

- Rust module: `codex-tui::streaming::chunking`
- Python module: `pycodex.tui.streaming.chunking`
- Status: `complete`
- Notes: Ported adaptive smooth/catch-up chunking policy, queue snapshot thresholds, hysteresis exit hold, re-entry hold, severe backlog bypass, and semantic drain plans. Python represents Rust `Duration` thresholds as seconds and keeps ratatui-independent policy semantics.

## 2026-06-12 - streaming/commit_tick.rs

- Rust module: `codex-tui::streaming::commit_tick`
- Python module: `pycodex.tui.streaming.commit_tick`
- Status: `complete_slice`
- Notes: Ported commit-tick orchestration boundary: combined queue snapshots, chunking policy resolution, catch-up-only suppression, single/batch drain dispatch, output ordering, and idle aggregation. Downstream stream controller internals remain owned by `streaming/controller.rs` and are represented by duck-typed controller interfaces in this module's tests.

## 2026-06-12 - streaming/table_holdback.rs

- Rust module: `codex-tui::streaming::table_holdback`
- Python module: `pycodex.tui.streaming.table_holdback`
- Status: `complete`
- Notes: Ported table holdback state, incremental scanner, stateless test helper, blockquote stripping, fence-context suppression, pending-header/confirmed transitions, and Rust byte-offset semantics for source starts. Controller live-tail use remains owned by `streaming/controller.rs`.

## 2026-06-12 - streaming/mod.rs

- Rust module: `codex-tui::streaming`
- Python module: `pycodex.tui.streaming`
- Status: `complete_slice`
- Notes: Ported `StreamState` FIFO queue behavior, enqueue timestamps, front-drain step, bounded `drain_n`, queue clear, full clear lifecycle state reset, queue depth, and oldest queued age. `MarkdownStreamCollector` remains a dependency boundary and is injected/held rather than implemented here.

## 2026-06-12 - diff_model.rs

- Rust module: `codex-tui::diff_model`
- Python module: `pycodex.tui.diff_model`
- Status: `complete`
- Notes: Ported `FileChange` add/delete/update variant model and serde-tagged dict shape with `type = add/delete/update`, `content`, `unified_diff`, and optional `move_path`. No Rust local unit tests exist; Python tests anchor the source-defined serde contract.

## 2026-06-12 - app_server_approval_conversions.rs

- Rust module: `codex-tui::app_server_approval_conversions`
- Python module: `pycodex.tui.app_server_approval_conversions`
- Status: `complete_slice`
- Notes: Ported app-server approval conversion helpers for permission profile grants and file update display changes. Python keeps lightweight semantic app-server DTOs and duck-typed mapping/object input compatibility rather than requiring a full generated app-server protocol runtime in this module.

## 2026-06-12 - approval_events.rs

- Rust module: `codex-tui::approval_events`
- Python module: `pycodex.tui.approval_events`
- Status: `complete_slice`
- Notes: Ported TUI approval event models, effective approval id fallback, explicit/default command approval decision selection, network allow amendment ordering, additional-permissions branch, execpolicy amendment branch, and apply-patch approval request shape. Full app-server protocol enum serialization remains a dependency boundary represented by lightweight semantic decision DTOs.

## 2026-06-12 - app_command.rs

- Rust module: `codex-tui::app_command`
- Python module: `pycodex.tui.app_command`
- Status: `complete_slice`
- Notes: Ported `AppCommand` semantic variant model, constructor helpers, Review predicate, user-turn approvals reviewer default, path normalization for cwd/cwds, and clone-like `from_`. Full serde compatibility with generated app-server/protocol value types remains a dependency boundary represented by semantic payload values.

## 2026-06-12 - app_event_sender.rs

- Rust module: `codex-tui::app_event_sender`
- Python module: `pycodex.tui.app_event_sender`
- Status: `complete`
- Notes: Ported sender wrapper behavior, CodexOp and SubmitThreadOp helper construction, non-CodexOp inbound logging boundary, swallowed send-error behavior, and semantic channel-like send targets. Full `app_event.rs` and `app_command.rs` enum/command surfaces remain separate module contracts; this module's sender-level behavior is complete.

### app_event_sender.rs - complete

- Python module: `pycodex.tui.app_event_sender`
- Rust source: `codex/codex-rs/tui/src/app_event_sender.rs`
- Status: `complete`
- Notes: The complete module-scoped behavior contract is represented in Python: sender construction, event forwarding, inbound logging skipped for `CodexOp`, swallowed send failures with optional error logging, all CodexOp helper wrappers, all SubmitThreadOp helper wrappers, and semantic send/list/callable target support standing in for Tokio `UnboundedSender`.

## 2026-06-12 - app_event.rs

- Rust module: `codex-tui::app_event`
- Python module: `pycodex.tui.app_event`
- Status: `complete_slice`
- Notes: Ported local enums, DTO field shapes, audio-device label helpers, and a semantic `AppEvent(kind, payload)` event-bus model with constructors for important variants. Exhaustive event handling remains owned by the app runtime modules that consume these events.

## 2026-06-12 - clipboard_copy.rs

- Rust module: `codex-tui::clipboard_copy`
- Python module: `pycodex.tui.clipboard_copy`
- Status: `complete_slice`
- Notes: Ported OSC52 construction, OSC52 writer write-vs-flush error boundaries, tmux readiness checks, environment helpers, injected backend decision tree, SSH/local/WSL fallback ordering, lease DTO, and Rust error-string composition. Python keeps the native clipboard backend explicitly unavailable by default to avoid adding non-standard dependencies; the Rust fallback path remains active and deterministic.

## 2026-06-12 - clipboard_paste.rs

- Rust module: `codex-tui::clipboard_paste`
- Python module: `pycodex.tui.clipboard_paste`
- Status: `complete_slice`
- Notes: Ported pasted image error/display model, encoded-format labels, image-info DTO, file URL/shell/quoted/Windows/UNC path normalization, WSL path conversion helper, and extension-based pasted image format inference. Real clipboard image capture/PNG encoding remains blocked behind non-stdlib platform dependencies and returns explicit unavailable errors.

## 2026-06-12 - slash_command.rs

- Rust module: `codex-tui::slash_command`
- Python module: `pycodex.tui.slash_command`
- Status: `complete_slice`
- Notes: Ported the slash command enum table, canonical command strings, aliases, user-visible descriptions, inline-args predicates, side-conversation/task availability predicates, platform/debug visibility, and built-in command presentation order.

## 2026-06-12 - external_editor.rs

- Rust module: `codex-tui::external_editor`
- Python module: `pycodex.tui.external_editor`
- Status: `complete_slice`
- Notes: Ported editor command resolution from VISUAL/EDITOR, error boundaries, shlex-style splitting, Windows program resolution helper, temporary `.md` seed-file workflow, editor subprocess execution, nonzero-exit error string, read-back content flow, and env restore helpers. Real editor interaction remains a subprocess side effect invoked only by callers.

## 2026-06-12 - workspace_command.rs

- Rust module: `codex-tui::workspace_command`
- Python module: `pycodex.tui.workspace_command`
- Status: `complete_slice`
- Notes: Ported workspace command DTO defaults/builders, output success predicate, error display, executor protocol, and app-server one-off command request conversion with non-tty/no-stream parameters, timeout milliseconds, cwd/env forwarding, output-cap handling, and transport error wrapping. The actual app-server transport remains a dependency boundary supplied by the request handle.

## 2026-06-12 - session_log.rs

- Rust module: `codex-tui::session_log`
- Python module: `pycodex.tui.session_log`
- Status: `complete_slice`
- Notes: Ported JSONL session logger, environment-gated initialization, explicit/default log path behavior, session_start/session_end records, generic outbound record writing, and inbound AppEvent summary records for the variants handled specially by Rust. Python exposes injectable logger arguments for deterministic tests while preserving the global `LOGGER` boundary.

## 2026-06-12 - file_search.rs

- Rust module: `codex-tui::file_search`
- Python module: `pycodex.tui.file_search`
- Status: `complete_slice`
- Notes: Ported TUI-owned file search orchestration: latest-query deduplication, empty-query session drop, search-dir updates, session-token rollover boundary, session creation options, swallowed session-start errors, reporter token/query guards, and `AppEvent::FileSearchResult` emission. The actual `codex-file-search` backend remains a dependency boundary supplied via session factory.

## 2026-06-12 - model_migration.rs

- Rust module: `codex-tui::model_migration`
- Python module: `pycodex.tui.model_migration`
- Status: `complete_slice`
- Notes: Ported migration copy construction, markdown placeholder replacement, outcome/menu enums, prompt state machine, highlighted option changes, numeric/arrow/vim-style key handling, Ctrl-C/Ctrl-D exit handling, key-release ignore, non-opt-out accept behavior, alt-screen guard boundary, and semantic render lines. Ratatui snapshot rendering is represented by user-visible semantic lines rather than widget-tree replication.

## 2026-06-12 - startup_hooks_review.rs

- Rust module: `codex-tui::startup_hooks_review`
- Python module: `pycodex.tui.startup_hooks_review`
- Status: `complete_slice`
- Notes: Ported startup hook review predicates, review-needed count, selection index mapping, semantic selection view params, menu item construction, trust-all disabled/error/trusting states, rendered prompt text, and async orchestration shape with injectable RPC dependencies. Full ratatui rendering and app-server hook RPC implementations remain dependency boundaries.

## 2026-06-12 - keymap.rs

- Rust module: `codex-tui::keymap`
- Python module: `pycodex.tui.keymap`
- Status: `complete_slice`
- Notes: Ported semantic `KeyBinding`, key spec parsing for modifiers, named keys, function keys and minus aliases, binding-list parsing/deduplication, primary binding helper, selected built-in defaults covered by Rust tests, config remap/unbind shape, and basic duplicate conflict validation. Full Rust keymap table, legacy-default pruning, fixed shortcut exceptions, and all cross-surface conflict rules remain follow-up slices.

## 2026-06-12 - bottom_pane/popup_consts.rs

- Rust module: `codex-tui::bottom_pane::popup_consts`
- Python module: `pycodex.tui.bottom_pane.popup_consts`
- Status: `complete`
- Notes: Promoted the module-scoped behavior contract to complete: `MAX_POPUP_ROWS`, standard Enter/Esc hint text, keymap primary-binding hint selection, all accept/cancel option branches, and Rust `key_hint::KeyBinding::display_label`-style labels are represented with Python semantic strings instead of ratatui `Line`/`Span`.

- Status: `complete_slice`
- Notes: Ported shared popup row cap and standard accept/cancel footer hint text generation. Python represents ratatui `Line` output as semantic visible strings and uses `ListKeymap` primary bindings for keymap-aware hints.

## 2026-06-12 - bottom_pane/slash_commands.rs

- Rust module: `codex-tui::bottom_pane::slash_commands`
- Python module: `pycodex.tui.bottom_pane.slash_commands`
- Status: `complete`
- Notes: Ported built-in slash command feature gating, service-tier command insertion after `/model`, exact builtin/service-tier lookup, side-conversation popup-vs-dispatch distinction, and command-item method delegation. The Rust fuzzy-match dependency is represented by a deterministic Python subsequence matcher for this module's prefix contract.

## 2026-06-12 - bottom_pane/action_required_title.rs

- Rust module: `codex-tui::bottom_pane::action_required_title`
- Python module: `pycodex.tui.bottom_pane.action_required_title`
- Status: `complete`
- Notes: Ported action-required preview prefix and title text assembly: prefix-first parts, spinner exclusion, caller-excluded item filtering, optional value omission, and `" | "` joining. Added a lightweight `TerminalTitleItem` enum interface in `title_setup.py` as a dependency boundary only; `title_setup.rs` behavior remains scaffolded and is not marked complete by this slice.

## 2026-06-12 - bottom_pane/prompt_args.rs

- Rust module: `codex-tui::bottom_pane::prompt_args`
- Python module: `pycodex.tui.bottom_pane.prompt_args`
- Status: `complete`
- Notes: Ported `parse_slash_name` first-line slash command parsing, including non-slash/empty-name rejection, Unicode whitespace separation, left-trimmed rest preservation, and Rust-compatible UTF-8 byte offsets for the returned rest index.

## 2026-06-12 - bottom_pane/scroll_state.rs

- Rust module: `codex-tui::bottom_pane::scroll_state`
- Python module: `pycodex.tui.bottom_pane.scroll_state`
- Status: `complete`
- Notes: Completed the generic vertical list scroll/selection state contract: new/reset, empty-list clearing, clamp without scroll movement, wrap up/down, non-wrapping page up/down, top/bottom jumps, zero-visible scroll reset, ensure-visible window adjustment, and Rust's None-selection initialization behavior for navigation methods.


- Rust module: `codex-tui::bottom_pane::scroll_state`
- Python module: `pycodex.tui.bottom_pane.scroll_state`
- Status: `complete`
- Notes: Ported `ScrollState` selection and scroll-window state machine: reset, empty clearing, selection clamping, wrap-around up/down movement, non-wrapping page movement, top/bottom jumps, and visibility adjustment for selected rows.

## 2026-06-12 - bottom_pane/paste_burst.rs

- Rust module: `codex-tui::bottom_pane::paste_burst`
- Python module: `pycodex.tui.bottom_pane.paste_burst`
- Status: `complete`
- Notes: Completed the pure paste-burst state-machine contract: ASCII first-char hold/typed flush, fast two-char buffering from pending, active paste flushing, modified-input flush, pastey retro-grab heuristic, Enter suppression window, UTF-8 retro byte offsets, active newline/try-append helpers, non-char window clearing, explicit paste clearing, and non-ASCII/IME no-hold branch behavior. Timing is represented with numeric/datetime-compatible seconds in Python.


- Rust module: `codex-tui::bottom_pane::paste_burst`
- Python module: `pycodex.tui.bottom_pane.paste_burst`
- Status: `complete_slice`
- Notes: Ported the paste-burst state machine behavior covered by Rust tests: first ASCII character hold/typed flush, fast two-character burst buffering, active idle paste flush, pending-char modified-input flush, retro-grab pastey heuristic, Enter suppression window, UTF-8 byte-index retro start calculation, newline append, try-append, and clear boundaries. Python represents Rust `Instant`/`Duration` as seconds-like values or datetime-compatible values; Windows/non-Windows active idle timeout follows Python `sys.platform`.

## 2026-06-12 - bottom_pane/selection_tabs.rs

- Rust module: `codex-tui::bottom_pane::selection_tabs`
- Python module: `pycodex.tui.bottom_pane.selection_tabs`
- Status: `complete`
- Notes: Promoted selection-tabs semantics to complete: `SelectionTab` shape, `TAB_GAP_WIDTH`, active/inactive tab units, two-space gaps, width clamp to at least one, pre-unit wrapping, empty-tab zero height, visible-line clipping, mapping/object area support, and Rust's unclamped out-of-range active index behavior. Python uses semantic `StyledLine`/`StyledSpan` and append-only rendered lines instead of ratatui `Line`/`Span`/`Buffer`.


- Rust module: `codex-tui::bottom_pane::selection_tabs`
- Python module: `pycodex.tui.bottom_pane.selection_tabs`
- Status: `complete_slice`
- Notes: Ported tab bar semantic layout: active tab bracket/accent spans, inactive dim spans, two-space gaps, width-based line wrapping, empty-tab height, width clamping, and area-height clipping. Python uses semantic `StyledLine`/`StyledSpan` plus append-only rendered lines instead of ratatui buffer mutation.

## 2026-06-12 - bottom_pane/selection_popup_common.rs

- Rust module: `codex-tui::bottom_pane::selection_popup_common`
- Python module: `pycodex.tui.bottom_pane.selection_popup_common`
- Status: `complete_slice`
- Notes: Added local branch coverage for empty menu-surface render no-op and empty row measurement placeholder height. Python continues to represent this module with semantic `Rect`/`Line`/`Span` rows and append-only buffers; exact ratatui cell painting, colors, and Unicode-width rendering remain renderer boundaries.


- Rust module: `codex-tui::bottom_pane::selection_popup_common`
- Python module: `pycodex.tui.bottom_pane.selection_popup_common`
- Status: `complete_slice`
- Notes: Ported the common selection-popup semantic model: display row DTOs, column-width modes/config, menu surface inset/padding, row full-line composition, wrap indent rules, two-column wrapping fallback, item-window calculation, selected/disabled row styling, placeholder rendering, single-line truncation, and row-height measurement. Python represents ratatui `Line`/`Span`/`Rect`/`Buffer` as semantic values and append-only rendered lines; exact cell-grid mutation and Unicode-width-perfect wrapping remain renderer-level follow-up work.

## 2026-06-12 - bottom_pane/pending_input_preview.rs

- Rust module: `codex-tui::bottom_pane::pending_input_preview`
- Python module: `pycodex.tui.bottom_pane.pending_input_preview`
- Status: `complete_slice`
- Notes: Ported pending input preview semantics as rendered text lines: empty/narrow no-op, pending steers before rejected steers before queued messages, configurable edit/interrupt binding hints, queued-message edit hint visibility, preview line cap with overflow marker, URL-like token no-ellipsis behavior, desired height, and area-height clipping. Python uses semantic `RenderedLine`/`Rect` instead of ratatui `Paragraph`/`Buffer`; exact snapshot cell styling remains renderer-level follow-up work.

## 2026-06-12 - bottom_pane/pending_thread_approvals.rs

- Rust module: `codex-tui::bottom_pane::pending_thread_approvals`
- Python module: `pycodex.tui.bottom_pane.pending_thread_approvals`
- Status: `complete_slice`
- Notes: Ported pending-thread approval state and visible rendering semantics: `set_threads` change detection, empty predicate, test-only thread snapshot, empty/narrow no-op, up to three warning rows, overflow marker for additional threads, `/agent` switch hint, desired height, area-height clipping, and Rust-test-like padded snapshot rows. Python uses semantic `RenderedLine`/`Rect` instead of ratatui `Paragraph`/`Buffer`.

## 2026-06-12 - bottom_pane/chat_composer/draft_state.rs

- Rust module: `codex-tui::bottom_pane::chat_composer::draft_state`
- Python module: `pycodex.tui.bottom_pane.chat_composer.draft_state`
- Status: `complete_slice`
- Notes: Ported draft-state container defaults and `ComposerMentionBinding` DTO fields: textarea/state dependency objects, bash mode, pending paste list, input enabled/placeholder fields, paste-burst state, paste-burst disable flag, mention binding map, and recent submission mention binding list. Full `textarea.rs` and composer control-flow behavior remain separate module boundaries.

## 2026-06-12 - bottom_pane/chat_composer/attachment_state.rs

- Rust module: `codex-tui::bottom_pane::chat_composer::attachment_state`
- Python module: `pycodex.tui.bottom_pane.chat_composer.attachment_state`
- Status: `complete_slice`
- Notes: Ported attachment bookkeeping semantics: local and remote image containers, placeholder numbering via `local_image_label_text`, remote-image count offset for local labels, attach insertion, reset/take/clear operations, prune by text-element placeholders, take recent submission images with/without placeholders, remote selection lines, keyboard selection/deletion behavior, and relabeling through a small textarea protocol. Added concrete `LocalImageAttachment` fields in `bottom_pane/__init__.py` as a dependency interface; full textarea behavior remains a separate module boundary.

### codex-tui `bottom_pane/mod.rs` - complete_slice
- Python module: `pycodex.tui.bottom_pane`
- Tests: `tests/test_tui_bottom_pane_mod.py`
- Notes: Ported the visible module-owned semantic surface for `LocalImageAttachment`, `MentionBinding`, `CancellationEvent`, `QUIT_SHORTCUT_TIMEOUT`, `APPROVAL_PROMPT_TYPING_IDLE_DELAY`, and `DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED`. The large `BottomPane` runtime/router/render methods stay as explicit `not_ported` interface scaffold rather than silent fallback.

### codex-tui `render/highlight.rs` - complete_slice
- Python module: `pycodex.tui.render.highlight`
- Tests: `tests/test_tui_render_highlight.py`
- Notes: Ported the portable Python slice for theme identifiers, custom theme path/listing/warnings, `.tmTheme` plist parsing, scope foreground/background/fontStyle extraction, ANSI alpha color conversion, syntax alias resolution, highlight size/line guardrails, content-preserving fallback lines, active theme preview state, and vendored-Pygments token highlighting for known languages. Exact syntect/two_face grammar/theme fidelity remains an explicit dependency/framework boundary.

### codex-tui `color.rs` - complete
- Python module: `pycodex.tui.color`
- Tests: `tests/test_tui_color.py`
- Notes: The full Rust module behavior is ported: luminance thresholding in `is_light`, float blend with Rust-style u8 truncation in `blend`, and CIE76-style perceptual RGB distance via the same sRGB -> XYZ -> Lab approximation in `perceptual_distance`. No ratatui/crossterm framework types are involved.

## 2026-06-12 - bottom_pane/chat_composer/footer_state.rs

- Rust module: `codex-tui::bottom_pane::chat_composer::footer_state`
- Python module: `pycodex.tui.bottom_pane.chat_composer.footer_state`
- Status: `complete_slice`
- Notes: Ported footer-state container fields plus helper behavior: flash expiry visibility, test-style show-flash state creation, and status-line span text concatenation. Python uses semantic `Line`/`Span` and monotonic-compatible float timestamps; full `footer.rs` rendering and key binding formatting remain separate module boundaries.

## 2026-06-12 - bottom_pane/chat_composer/popup_state.rs

- Rust module: `codex-tui::bottom_pane::chat_composer::popup_state`
- Python module: `pycodex.tui.bottom_pane.chat_composer.popup_state`
- Status: `complete`
- Notes: Ported popup lifecycle state: default no-popup state, active predicate, command/file/skill/mention-v2 active variants, and dismissed file/query/mention token fields. Popup payload behavior remains owned by each popup module and is represented here with duck-typed semantic payloads.

## 2026-06-12 - bottom_pane/chat_composer/history_search.rs

- Rust module: `codex-tui::bottom_pane::chat_composer::history_search`
- Python module: `pycodex.tui.bottom_pane.chat_composer.history_search`
- Status: `complete_slice`
- Notes: Ported local history-search session/status semantics, Unicode-aware case-insensitive UTF-8 byte match ranges, footer visible line/status styling, highlight-range gating, and history-result status mapping. Full `ChatComposer` lifecycle behavior, textarea preview/cursor mutation, history navigation, and cancel/accept key handling remain separate module boundaries represented by explicit `not_ported` Rust test-name scaffolds.

## 2026-06-12 - bottom_pane/chat_composer/slash_input.rs

- Rust module: `codex-tui::bottom_pane::chat_composer::slash_input`
- Python module: `pycodex.tui.bottom_pane.chat_composer.slash_input`
- Status: `complete_slice`
- Notes: Ported slash-input local contracts: submission validation, bare/inline command detection, dequeue action selection, command-element range calculation, command-under-cursor/filter extraction with UTF-8 byte-boundary checks, selected command completion/dispatch-on-tab helpers, prepared-args extraction, and argument text-element range translation. Full `ChatComposer` slash-popup key handling, draft-tail replacement, textarea mutation, and command dispatch remain composer module boundaries represented by explicit `not_ported` Rust test-name scaffolds.

## 2026-06-12 - bottom_pane/chat_composer_history.rs

- Rust module: `codex-tui::bottom_pane::chat_composer_history`
- Python module: `pycodex.tui.bottom_pane.chat_composer_history`
| `pycodex/tui/bottom_pane/chat_composer_history.py` | `complete_slice` | Refreshed `HistoryEntry::new` parity to call mention decoding, restoring persisted linked mentions into visible text plus `MentionBinding` values while keeping attachment fields empty. |
- Status: `complete_slice`
- Notes: Ported the composer history state machine: history entry DTOs, metadata reset, local submission dedupe, boundary-gated Up/Down navigation, lazy persistent lookup event emission, async response integration, incremental Ctrl+R search across local and persistent offset space, duplicate text suppression, cached unique match revisiting, boundary exhaustion, case-insensitive matching, empty-query latest match behavior, and navigation/search reset semantics. Real `AppEventSender`, `ThreadId`, and mention-codec decoding remain dependency boundaries represented by semantic values.

## 2026-06-12 - bottom_pane/command_popup.rs

- Rust module: `codex-tui::bottom_pane::command_popup`
- Python module: `pycodex.tui.bottom_pane.command_popup`
- Status: `complete_slice`
- Notes: Added parity coverage for composer text filter extraction: only the first line is inspected, leading whitespace after `/` is trimmed, and only the first token becomes `command_filter`. Existing semantic coverage remains command filtering, exact/prefix ordering, alias hiding in empty filter, service-tier entries, feature gates, selection movement, and row DTO generation; ratatui `WidgetRef` rendering remains represented by selection-popup semantic rows.


- Rust module: `codex-tui::bottom_pane::command_popup`
- Python module: `pycodex.tui.bottom_pane.command_popup`
- Status: `complete_slice`
- Notes: Ported command popup state and filtering: flags conversion, built-in/service-tier item model, hidden debug/apps popup entries, alias hiding only for empty filters, composer text filter extraction, exact-before-prefix ordering, presentation-order preservation, feature gates, service-tier catalog labels/descriptions, scroll selection movement, selected item lookup, required-height delegation, and semantic row conversion. Ratatui `WidgetRef` cell rendering remains a renderer boundary represented by semantic row rendering helpers.

## 2026-06-12 - bottom_pane/list_selection_view.rs

- Rust module: `codex-tui::bottom_pane::list_selection_view`
- Python module: `pycodex.tui.bottom_pane.list_selection_view`
- Status: `complete_slice`
- Notes: Ported core selection-list state contracts: popup content width, side-by-side layout width rules, side-content width model, selection params/items/toggles, default/current/initial selection, search filtering and actual-index mapping, selection-changed callback guard, tab activation/switching with search reset, disabled-row detection and skip navigation, page/jump clamping, toggle callbacks, accept/cancel completion flags, child-dismiss flag, active footer/header lookup, and semantic `GenericDisplayRow` construction. Ratatui snapshot rendering, side-content buffer clearing/style preservation, and exhaustive `ListKeymap` key event dispatch remain renderer/runtime follow-up slices.

## 2026-06-12 - bottom_pane/multi_select_picker.rs

- Rust module: `codex-tui::bottom_pane::multi_select_picker`
- Python module: `pycodex.tui.bottom_pane.multi_select_picker`
- Status: `complete_slice`
- Notes: Added parity coverage for the reordering guard while a search query is active. The Python semantic picker now covers filtering, selection preservation, toggles, callbacks, ordering constraints, section-break row mapping, page/jump navigation, and filtered-view no-reorder behavior; full ratatui rendering and exhaustive `ListKeymap` event dispatch remain renderer/runtime boundaries.


- Rust module: `codex-tui::bottom_pane::multi_select_picker`
- Python module: `pycodex.tui.bottom_pane.multi_select_picker`
- Status: `complete_slice`
- Notes: Ported multi-select picker state contracts: item defaults, builder flow, filtering with fuzzy-style subsequence matching and score/name ordering, selected-index preservation, scroll/page/jump navigation, row DTO construction including checkbox markers and section breaks, toggle/change callbacks, confirm selected IDs, cancel close, preview refresh, ordering constraints around non-orderable items, reorder selection restoration, and a small semantic key-event helper. Full ratatui rendering, exact fuzzy-match scoring, footer key-hint formatting, and exhaustive `ListKeymap` event dispatch remain follow-up slices.


## 2026-06-12 - bottom_pane/status_line_style.rs

- Rust module: `codex-tui::bottom_pane::status_line_style`
- Python module: `pycodex.tui.bottom_pane.status_line_style`
- Status: `complete_slice`
- Notes: Ported status-line styling behavior: segment order and text joining, `STATUS_LINE_SEPARATOR`, accent grouping by `StatusLineItem` name, fallback foreground colors, theme-style priority, RGB luma/channel softening, light named-color downshifts, disabled-theme dimming, pull-request underline, and empty-input `None`. Python uses semantic `StyledLine`/`StyledSpan` objects instead of ratatui values; exact theme scope resolution remains a renderer/theme dependency boundary.


## 2026-06-12 - bottom_pane/status_surface_preview.rs

- Rust module: `codex-tui::bottom_pane::status_surface_preview`
- Python module: `pycodex.tui.bottom_pane.status_surface_preview`
- Status: `complete_slice`
- Notes: Ported preview data contracts: `StatusSurfacePreviewItem` ordering and placeholder copy, default population, live value insertion, placeholder non-overwrite of live data, placeholder suppression, value/live-value accessors, rate-limit prefix copy selection, fallback name/description behavior, and semantic `status_line_for_items` bridging through `status_line_style`. Full interactive status-line setup remains a separate `status_line_setup.rs` module boundary.


## 2026-06-12 - bottom_pane/unified_exec_footer.rs

- Rust module: `codex-tui::bottom_pane::unified_exec_footer`
- Python module: `pycodex.tui.bottom_pane.unified_exec_footer`
- Status: `complete_slice`
- Notes: Ported unified-exec footer state behavior: `new`, `set_processes` change detection, owned process-list copy semantics, `is_empty`, singular/plural summary text, count-only session copy, `width < 4` no-op, two-space indentation, `take_prefix_by_width` truncation, dim semantic footer rows, desired height, and simple area-height clipping. Exact ratatui buffer snapshots remain renderer-level follow-up work.


## 2026-06-12 - bottom_pane/app_link_view.rs

- Rust module: `codex-tui::bottom_pane::app_link_view`
- Python module: `pycodex.tui.bottom_pane.app_link_view`
- Status: `complete_slice`
- Notes: Ported core app-link behavior: trusted external URL validation, ChatGPT auth host allowlist, codex-apps auth metadata extraction, generic URL elicitation params, action-label matrices for installed/uninstalled/auth/external/tool suggestions, selection movement, open URL transitions, install/auth/external confirmation, connector refresh decisions, elicitation accept/decline semantic events, enable/disable event emission, completion predicates, terminal title action predicate, matching app-server request dismissal, and semantic visible content lines with URL-like token preservation. Exact ratatui snapshots, full `ListKeymap` remapping, and concrete app-server protocol/event variants remain follow-up runtime/renderer slices.


## 2026-06-12 - bottom_pane/custom_prompt_view.rs

- Rust module: `codex-tui::bottom_pane::custom_prompt_view`
- Python module: `pycodex.tui.bottom_pane.custom_prompt_view`
- Status: `complete_slice`
- Notes: Ported custom prompt view behavior: constructor title/placeholder/context/on-submit fields, initial text insertion and cursor-to-end setup, Enter submission of trimmed non-empty text, modified Enter delegated to textarea input, Esc/Ctrl-C cancellation, paste empty/non-empty boundaries, completion state, desired height and input-height clamp, cursor-position offset semantics, gutter/title/context/placeholder/hint semantic rendering. Python uses a lightweight `SimpleTextArea` and `DisplayLine` model instead of ratatui `TextArea`/`Buffer` internals.


## 2026-06-12 - bottom_pane/experimental_features_view.rs

- Rust module: `codex-tui::bottom_pane::experimental_features_view`
- Python module: `pycodex.tui.bottom_pane.experimental_features_view`
- Status: `complete_slice`
- Notes: Ported experimental feature toggle behavior: item DTOs, initial selection, visible length, row construction with selected/enabled markers, wrap up/down navigation, clamped page movement, top/bottom jumps, scroll visibility, selected toggle, rows-width saturation, Enter/Esc close handling, save-on-close `UpdateFeatureFlags` semantic event, complete state, popup hint text, desired-height approximation, and empty-state semantic render lines. Exact ratatui layout/buffer rendering and full `ListKeymap` dispatch remain follow-up runtime/renderer slices.


## 2026-06-12 - bottom_pane/skills_toggle_view.rs

- Rust module: `codex-tui::bottom_pane::skills_toggle_view`
- Python module: `pycodex.tui.bottom_pane.skills_toggle_view`
- Status: `complete_slice`
- Notes: Ported skills toggle behavior: item DTOs, search placeholder/prompt constants, initial filter and selection, display-name-first skill filtering with canonical-name fallback, score/name ordering, selection preservation, row construction with selected/enabled markers and skill-name truncation, wrap/page/jump navigation, plain printable key search behavior, backspace filtering, toggle `SetSkillEnabled` semantic event, idempotent close with `ManageSkillsClosed` and forced list-skills reload, rows width/height, hint text, empty-state and semantic render lines. `skills_helpers` remains a separate dependency boundary; exact ratatui rendering and full keymap binding formatting remain follow-up slices.


## 2026-06-12 - bottom_pane/skill_popup.rs

- Rust module: `codex-tui::bottom_pane::skill_popup`
- Python module: `pycodex.tui.bottom_pane.skill_popup`
- Status: `complete_slice`
- Notes: Ported skill popup behavior: `MentionItem` fields, query/mention updates with selection clamping, required height, filtered item preservation beyond popup height, display-name-first fuzzy matching with search-term fallback, sorting by display-match presence/score/sort-rank/name, selected mention lookup, wrap up/down navigation, scroll visibility, row construction with truncation and category/description composition, empty-state semantic render text, and hint line. Exact ratatui `WidgetRef` buffer rendering remains a renderer-level follow-up slice.


## 2026-06-12 - bottom_pane/feedback_view.rs

- Rust module: `codex-tui::bottom_pane::feedback_view`
- Python module: `pycodex.tui.bottom_pane.feedback_view`
- Status: `complete_slice`
- Notes: Ported feedback behavior: `FeedbackNoteView` submit/cancel/paste/key handling, trimmed optional note emission, input/cursor/height semantic rendering, category title/placeholder/classification mapping, connectivity diagnostics visibility rule, internal/external issue URL routing, success-message copy for logs/no-logs and employee/external audiences, feedback category selection params, disabled-feedback params, upload-consent attachment list including doctor report, Windows sandbox log, rollout files, auto-review rollout, diagnostics file, connectivity diagnostic details, and yes/no actions. Python uses semantic `DisplayLine`/`WebHyperlinkHistoryCell`/selection params and event dictionaries instead of ratatui/history-cell concrete rendering.



## 2026-06-12 - bottom_pane/mcp_server_elicitation.rs

- Rust module: \`codex-tui::bottom_pane::mcp_server_elicitation\`
- Python module: \`pycodex.tui.bottom_pane.mcp_server_elicitation\`
- Status: \`complete_slice\`
- Notes: Ported MCP server elicitation schema/request parsing, approval action construction, tool suggestion metadata DTOs, tool approval display-param formatting, answer state, form/approval submission events, Ctrl-C cancellation, FIFO request queueing, and resolved-request dismissal. Python uses semantic event dictionaries and lightweight form/field DTOs instead of ratatui overlay and crossterm key internals; exact buffer rendering, textarea widget behavior, and exhaustive keymap dispatch remain follow-up renderer/runtime slices.


## 2026-06-12 - bottom_pane/status_line_setup.rs

- Rust module: \`codex-tui::bottom_pane::status_line_setup\`
- Python module: \`pycodex.tui.bottom_pane.status_line_setup\`
- Status: \`complete_slice\`
- Notes: Ported status-line item canonical IDs and legacy aliases, descriptions, preview-item mapping, setup view item ordering/deduplication, theme-color toggle, rate-limit preview naming, preview builder, confirm/cancel semantic events, Ctrl-C close, and semantic render lines. Exact ratatui buffer snapshots and full crossterm/ListKeymap dispatch remain follow-up renderer/runtime slices.


## 2026-06-12 - bottom_pane/mentions_v2/search_mode.rs

- Rust module: \`codex-tui::bottom_pane::mentions_v2::search_mode\`
- Python module: \`pycodex.tui.bottom_pane.mentions_v2.search_mode\`
- Status: \`complete\`
- Notes: Ported SearchMode enum behavior completely: previous/next cyclic navigation, mention-type acceptance filters for all/filesystem/tools modes, and visible labels. Candidate MentionType remains a separate module boundary; this module accepts compatible enum/string values semantically.


## 2026-06-12 - bottom_pane/mentions_v2/candidate.rs

- Rust module: \`codex-tui::bottom_pane::mentions_v2::candidate\`
- Python module: \`pycodex.tui.bottom_pane.mentions_v2.candidate\`
- Status: \`complete_slice\`
- Notes: Ported candidate/result DTOs, Selection file/tool variants, MentionType variants, filesystem predicate, padded tag labels, semantic span styling, and Candidate.to_result clone-like conversion. Python uses SemanticSpan instead of ratatui Span/Style concrete types, preserving visible tag text and style intent.


## 2026-06-12 - bottom_pane/mentions_v2/filter.rs

- Rust module: \`codex-tui::bottom_pane::mentions_v2::filter\`
- Python module: \`pycodex.tui.bottom_pane.mentions_v2.filter\`
- Status: \`complete_slice\`
- Notes: Ported query trimming, candidate filtering by SearchMode, display-name fuzzy matching, search-term fallback scoring, optional file-match row conversion, search-mode filtering of file rows, and row sorting by mention type, direct-match presence, score, and display name. Python uses a deterministic subsequence fuzzy-match adapter and compatible FileMatch DTO/dict inputs rather than implementing the external codex-file-search backend here.


## 2026-06-12 - bottom_pane/mentions_v2/footer.rs

- Rust module: \`codex-tui::bottom_pane::mentions_v2::footer\`
- Python module: \`pycodex.tui.bottom_pane.mentions_v2.footer\`
- Status: \`complete_slice\`
- Notes: Ported footer hint visible text, search-mode indicator labels and active styles, width split between left hint and right indicator, narrow-width right-indicator suppression, and semantic truncation. Python uses FooterLine/FooterSpan/RenderedFooter instead of ratatui Buffer/Rect mutation; exact terminal cell styling remains a renderer boundary.


## 2026-06-12 - bottom_pane/mentions_v2/render.rs

- Rust module: \`codex-tui::bottom_pane::mentions_v2::render\`
- Python module: \`pycodex.tui.bottom_pane.mentions_v2.render\`
- Status: \`complete_slice\`
- Notes: Ported semantic popup row rendering: file-name/path splitting, primary and secondary spans, match-index highlighting, selected-row bold styling, file/tag color intent, primary-column alignment, right-side mention tag placement, empty-message rendering, scroll-window adjustment around selected rows, and footer inclusion for tall areas. Python represents ratatui Line/Span/Buffer output with RenderLine/RenderSpan/RenderedPopup; exact terminal cell rendering remains a renderer boundary.


## 2026-06-12 - bottom_pane/mentions_v2/search_catalog.rs

- Rust module: \`codex-tui::bottom_pane::mentions_v2::search_catalog\`
- Python module: \`pycodex.tui.bottom_pane.mentions_v2.search_catalog\`
- Status: \`complete_slice\`
- Notes: Ported search catalog construction for skills and plugins: skill display/description/search terms, tool selection insert text/path, plugin config-name marketplace splitting, plugin search terms, plugin description fallback, capability labels, and skill-before-plugin ordering. Dependency crate DTOs are accepted as duck-typed objects or mappings; their owning crates remain separate boundaries.


## 2026-06-12 - bottom_pane/request_user_input/layout.rs

- Rust module: \`codex-tui::bottom_pane::request_user_input::layout\`
- Python module: \`pycodex.tui.bottom_pane.request_user_input.layout\`
- Status: \`complete_slice\`
- Notes: Ported request-user-input layout planning: options/no-options branches, tight question truncation, options min/preferred/full heights, notes visibility collapse, footer/progress/spacer allocation, section Rect stacking, and layout_sections aggregation. Python uses semantic Rect/LayoutPlan/LayoutSections and duck-typed overlay hooks instead of ratatui Rect and the full overlay implementation.


## 2026-06-12 - bottom_pane/request_user_input/render.rs

- Rust module: \`codex-tui::bottom_pane::request_user_input::render\`
- Python module: \`pycodex.tui.bottom_pane.request_user_input.render\`
- Status: \`complete_slice\`
- Notes: Ported semantic render behavior: desired-height composition/minimum, unanswered confirmation data/layout/height, line ownership/width helpers, bottom-aligned rows, word-boundary ellipsis truncation, cursor-position gating, notes masking signal, footer tip line rendering, and normal/unanswered render branches as semantic events. Exact ratatui Buffer/Paragraph/cell mutation and full shared selection renderer integration remain renderer/runtime boundaries.

## 2026-06-12 - bottom_pane/request_user_input/render.rs
- Rust module: `codex-rs/tui/src/bottom_pane/request_user_input/render.rs`
- Python module: `pycodex/tui/bottom_pane/request_user_input/render.py`
- Status: `complete_slice`
- Notes: Implemented request-user-input overlay semantic render behavior: desired height, unanswered confirmation planning, footer/progress/question/notes events, row bottom alignment, cursor-position gating, and word-boundary truncation. Ratatui buffer rendering is represented by semantic events.

## 2026-06-12 - auto_review_denials.rs
- Rust module: `codex-tui::auto_review_denials`
- Python module: `pycodex.tui.auto_review_denials`
- Status: `complete`
- Notes: Implemented the module-local denial deque contract and action summary formatting. Python includes lightweight protocol-shaped dataclasses/dict coercion so callers can pass local facades without depending on Rust protocol types.

## 2026-06-12 - app_backtrack.rs
- Rust module: `codex-tui::app_backtrack`
- Python module: `pycodex.tui.app_backtrack`
- Status: `complete_slice`
- Notes: Ports module-local backtrack DTOs, transcript user/session/agent position iterators, trim-to-selected-user, drop-last-n-user-turns rollback trimming, target detection, agent-group counting, unavailable-message text, pure global Esc decision, pure overlay event decision, prime/reset/overlay-close/overlay-sync backtrack state, preview selection clamping after transcript trims, main-view confirm selection/reset, older/newer selection stepping and clamping, highlight-cell index selection, base-thread guarded selection, selected user payload extraction, stale-index empty selection behavior, pending rollback guard, rollback turn-count planning, pending rollback recording, composer/remote-image payload planning, pending rollback success/failure clearing, stale-thread ignore, and non-pending rollback trim planning. App/Tui event routing, alt-screen switching, actual deferred scrollback flushing, ChatWidget hint clearing/prefill/submission/history truncation side effects, actual event dispatch, scrollback refresh scheduling, overlay cell replacement, and transcript overlay live-tail drawing remain runtime boundaries.
- Status: `complete_slice`
- Notes: Added semantic preview open/begin planning for no-target info/reset, latest-user selection, and overlay BeginBacktrack priming while leaving concrete overlay construction, frame scheduling, and terminal rendering side effects out of scope.
- Status: `complete_slice`
- Notes: Implemented Backtrack state DTOs and local transcript semantics: latest-session user positions, user/backtrack target count, trim to nth user, drop last N user turns, agent group counting, and Rust unit-test helper behavior. App/Tui overlay event routing remains a separate runtime slice.
## 2026-06-12 - app/pending_interactive_replay.rs
- Rust module: `codex-tui::app::pending_interactive_replay`
- Python module: `pycodex.tui.app.pending_interactive_replay`
- Status: `complete_slice`
- Notes: Implemented the pending interactive replay state machine: request registration, outbound operation resolution, server notification resolution, evicted request cleanup, snapshot replay filtering, FIFO request-user-input answers, pending approval/user-input flags, and Rust-test-shaped request helpers. Python uses semantic DTOs instead of app-server protocol enum classes.
## 2026-06-12 - app/replay_filter.rs
- Rust module: `codex-tui::app::replay_filter`
- Python module: `pycodex.tui.app.replay_filter`
- Status: `complete`
- Notes: Implemented pending interactive request detection and replay notice classification for semantic ThreadBufferedEvent/ThreadEventSnapshot values.
## 2026-06-12 - app/thread_events.rs
- Rust module: `codex-tui::app::thread_events`
- Python module: `pycodex.tui.app.thread_events`
- Status: `complete_slice`
- Notes: Implemented thread event store snapshot and buffer behavior: active turn tracking, session/turn restore, request replay filtering through pending interactive replay state, capacity eviction cleanup, session-refresh rebase survival rules, side-parent pending status, rollback reset, and file-change lookup. Python represents the mpsc channel as an in-memory queue stub.

## 2026-06-12 - app/loaded_threads.rs
- Rust module: `codex-tui::app::loaded_threads`
- Python module: `pycodex.tui.app.loaded_threads`
- Status: `complete`
- Notes: Implemented the pure loaded-subagent tree walk with semantic `Thread` and `LoadedSubagentThread` models. SessionSource parsing is represented by JSON-like `subAgent.thread_spawn.parent_thread_id` data, with invalid or non-spawn sources ignored as in Rust.

## 2026-06-12 - tui/frame_rate_limiter.rs
- Rust module: `codex-tui::tui::frame_rate_limiter`
- Python module: `pycodex.tui.tui.frame_rate_limiter`
- Status: `complete`
- Notes: Implemented the pure 120 FPS draw deadline limiter. Python stores the Rust `MIN_FRAME_INTERVAL` as the exact nanosecond integer for deterministic monotonic-clock semantics, with a lightweight datetime adapter for semantic callers.

## 2026-06-12 - app/agent_navigation.rs
- Rust module: `codex-tui::app::agent_navigation`
- Python module: `pycodex.tui.app.agent_navigation`
- Status: `complete`
- Notes: Implemented the pure multi-agent picker/navigation state: first-seen order preservation, upsert/close/remove/clear transitions, ordered thread queries, wraparound next/previous traversal, active agent labels, and picker subtitle shortcut copy. Ratatui `Span`/keybinding concrete types are represented by semantic strings.

## 2026-06-12 - app/app_server_event_targets.rs
- Rust module: `codex-tui::app::app_server_event_targets`
- Python module: `pycodex.tui.app.app_server_event_targets`
- Status: `complete_slice`
- Notes: Implemented request thread-id extraction and notification target classification as semantic dict/object app-server variants, including valid thread routing, invalid thread-id preservation, and global notifications. Full concrete `codex_app_server_protocol` enum integration remains a neighboring dependency boundary.

## 2026-06-12 - app/agent_message_consolidation.rs
- Rust module: `codex-tui::app::agent_message_consolidation`
- Python module: `pycodex.tui.app.agent_message_consolidation`
- Status: `complete_slice`
- Notes: Implemented the finalized agent-message consolidation transition: deferred cell insertion, trailing streaming-cell run detection, replacement by source-backed markdown cell, overlay consolidation, frame scheduling, and reflow completion mode dispatch. Real `App`, `HistoryCell`, pager overlay, and resize-reflow concrete integrations remain adjacent module/runtime boundaries.

## 2026-06-12 - transcript_reflow.rs
- Rust module: `codex-tui::transcript_reflow`
- Python module: `pycodex.tui.transcript_reflow`
- Status: `complete`
- Notes: Implemented the pure transcript scrollback reflow state machine with the Rust 75ms debounce interval, observed/reflowed width separation, pending target tracking, immediate scheduling, pending deadline helpers, and stream-time final-reflow flags.

## 2026-06-12 - tui/frame_requester.rs
- Rust module: `codex-tui::tui::frame_requester`
- Python module: `pycodex.tui.tui.frame_requester`
- Status: `complete_slice`
- Notes: Implemented deterministic semantic frame scheduling: request handles, draw channel notifications, earliest-deadline coalescing, delayed/immediate request handling, 120 FPS limiter integration, and no-op test dummy. Real tokio actor task, mpsc receiver, and broadcast channel integration remain runtime boundaries.

## 2026-06-12 - app/app_server_requests.rs
- Rust module: `codex-tui::app::app_server_requests`
- Python module: `pycodex.tui.app.app_server_requests`
- Status: `complete_slice`
- Notes: Implemented the pending app-server request correlation state for exec/file-change/permissions approvals, request-user-input FIFO queues, MCP elicitation request keys, notification-side resolution removal, contains/clear semantics, and Rust unsupported-request messages. Full app-server protocol DTO serialization and async reject-server-request transport remain dependency/runtime boundaries.

## 2026-06-12 - app/history_ui.rs
- Rust module: `codex-tui::app::history_ui`
- Python module: `pycodex.tui.app.history_ui`
- Status: `complete_slice`
- Notes: Implemented semantic URL-open success/error messages, clear header queueing, alt-screen vs inline clear behavior, viewport anchoring after clear, and transcript/backtrack/reflow state reset after `/clear`. Exact `SessionHeaderHistoryCell` card rendering, real terminal clearing, and real browser launching remain dependency/runtime boundaries.

## 2026-06-12 - tui/keyboard_modes.rs
- Rust module: `codex-tui::tui::keyboard_modes`
- Python module: `pycodex.tui.tui.keyboard_modes`
- Status: `complete_slice`
- Notes: Implemented env flag parsing, WSL+VSCode auto-disable rule, VSCode/tmux detection helpers, csi-u modifyOtherKeys gate, reset/enable/disable ANSI command strings, and semantic enable/restore/reset command ordering. Real crossterm stdout execution, legacy WinAPI execution, WSL `cmd.exe` probing, and tmux subprocess probing remain explicit platform/runtime boundaries.

## 2026-06-12 - tui/terminal_stderr.rs
- Rust module: `codex-tui::tui::terminal_stderr`
- Python module: `pycodex.tui.tui.terminal_stderr`
- Status: `complete_slice`
- Notes: Implemented semantic stderr suppression ownership lifecycle: inactive install when not targeting the stdout terminal, active install-suppression guard, duplicate-owner rejection, pause/resume/finish/drop idempotence, and captured-vs-hidden stderr output. Real macOS file descriptor duplication/restoration and terminal inode checks remain platform boundaries.

## 2026-06-12 - tui/job_control.rs
- Rust module: `codex-tui::tui::job_control`
- Python module: `pycodex.tui.tui.job_control`
- Status: `complete_slice`
- Notes: Implemented semantic Ctrl-Z suspend/resume coordination: alt-screen vs inline resume intent capture, cached cursor row, one-shot prepared resume actions, inline viewport realignment, alt-screen restoration, and suspend-process mode transition trace. Real SIGTSTP delivery, stdout crossterm commands, and terminal backend mutation remain platform/runtime boundaries.

## 2026-06-12 - voice.rs
- Rust module: `codex-tui::voice`
- Python module: `pycodex.tui.voice`
- Status: `complete_slice`
- Notes: Implemented pure PCM conversion, f32/i16/u16 peak helpers, semantic recording meter history, realtime audio chunk base64 encoding, playback queue decode/convert/clear behavior, output fill helpers, and VoiceCapture stop/accessors. Real cpal device selection/build/start streams and exact Unicode meter glyphs remain dependency/platform boundaries.

## 2026-06-12 - audio_device.rs
- Rust module: `codex-tui::audio_device`
- Python module: `pycodex.tui.audio_device`
- Status: `complete_slice`
- Notes: Confirmed and recorded the semantic audio-device boundary: injected host/device enumeration, duplicate-name filtering, configured/default device selection, preferred input sample-rate/config ranking, config-name lookup, and Rust error-message text are covered in `tests/test_tui_audio_device.py`. Real `cpal` host/device enumeration remains an explicit platform backend boundary and is not silently faked.

## 2026-06-12 - get_git_diff.rs
- Rust module: `codex-tui::get_git_diff`
- Python module: `pycodex.tui.get_git_diff`
- Status: `complete`
- Notes: Implemented git diff orchestration through the semantic `WorkspaceCommandExecutor`: repository detection, tracked diff capture, untracked file listing, per-file `git diff --no-index` against the platform null device, exit-code handling, command construction with cwd/30s timeout/disabled output cap, and Rust-test-shaped fake runner helpers.

## 2026-06-12 - external_agent_config_migration.rs
- Rust module: `codex-tui::external_agent_config_migration`
- Python module: `pycodex.tui.external_agent_config_migration`
- Status: `complete_slice`
- Notes: Implemented semantic migration-prompt state: outcome/action/focus models, selected-item toggles, all/none selection, proceed validation, skip/skip-forever/exit paths, numeric/arrow/vim/space/enter/esc/Ctrl-C/Ctrl-D key handling, description path reformatting, plugin detail row caps, section grouping, frame-request scheduling, and semantic render lines. Real TUI event stream/draw loop and ratatui cell snapshot rendering remain runtime/renderer boundaries.

## 2026-06-12 - external_agent_config_migration_startup.rs
- Rust module: `codex-tui::external_agent_config_migration_startup`
- Python module: `pycodex.tui.external_agent_config_migration_startup`
- Status: `complete_slice`
- Notes: Implemented startup feature/trust gating, hidden/cooldown scope filtering, project-key and last-prompt lookup, five-day cooldown expiry, plugin-aware success messages, semantic prompt-shown timestamp persistence, dismissal preference persistence, and a semantic app-server/prompt-runner orchestration slice. Real config file edit application, full ConfigBuilder reload, concrete app-server protocol DTOs, and TUI prompt event loop remain runtime/dependency boundaries.

## 2026-06-12 - oss_selection.rs
- Rust module: `codex-tui::oss_selection`
- Python module: `pycodex.tui.oss_selection`
- Status: `complete_slice`
- Notes: Implemented OSS provider selection semantics: provider option/status DTOs, Ctrl-H/Ctrl-L and arrow navigation, case-insensitive provider hotkeys, Enter/Esc/Ctrl-C decisions, completion/desired-height helpers, semantic render lines, auto-selection when exactly one provider is running, and stdlib localhost port probing mapped to Running/NotRunning/Unknown. Real raw-mode alternate screen setup, crossterm event reading, ratatui cell rendering, and exact Unicode status glyph styling remain runtime/renderer boundaries.

| codex-rs/tui/src/local_chatgpt_auth.rs | pycodex.tui.local_chatgpt_auth | complete | Test-only local ChatGPT auth behavior is ported: managed auth fixture writing/loading, JWT-shaped helper claims, auth-mode/openai-api-key rejection, missing-token/account errors, forced workspace filtering, id-token account fallback, managed-auth precedence over ignored external token files, and plan wire-name lowercasing. Real `codex_login` credential-store backends remain an external dependency boundary. |

| codex-rs/tui/src/selection_list.rs | pycodex.tui.selection_list | complete | Semantic selection option row construction is ported; concrete ratatui widget rendering is represented by Python segment/style dataclasses. |

### selection_list.rs - complete

- Python module: `pycodex.tui.selection_list`
- Rust source: `codex/codex-rs/tui/src/selection_list.rs`
- Status: `complete`
- Notes: The complete module-scoped behavior contract is represented in Python: selected/unselected one-based prefixes, prefix display width, cyan selected style precedence, dim unselected style, label wrapping/no-trim semantics, and semantic row/segment dataclasses standing in for ratatui `RowRenderable`/`Paragraph`.


| codex-rs/tui/src/skills_helpers.rs | pycodex.tui.skills_helpers | complete | Skill metadata display/description/truncation/matching semantics are ported: interface display-name precedence including empty Some values, plugin-qualified fallback formatting, description precedence with empty Some values, Rust truncate length, display-name-first matching, canonical-name fallback with suppressed highlight indices, and equal-name fallback suppression. Exact external fuzzy-match crate score values remain a dependency boundary. |

| codex-rs/tui/src/test_backend.rs | pycodex.tui.test_backend | complete_slice | In-memory VT100Backend semantics are ported for Python TUI tests; real crossterm backend and vt100 escape parser behavior remain outside this module slice. |
| codex-rs/tui/src/test_backend.rs | pycodex.tui.test_backend | complete_slice | Added explicit clear-region semantic coverage for All, AfterCursor, and BeforeCursor in the in-memory backend. Real crossterm backend calls and vt100 ANSI escape parsing remain dependency/framework boundaries rather than silent fallbacks. |

| codex-rs/tui/src/pager_overlay.rs | pycodex.tui.pager_overlay | complete_slice | Pager/overlay state semantics are ported for scrolling, live-tail caching, static wrapping, insertion, and consolidation highlight remapping; concrete ratatui/crossterm rendering and hyperlink buffer marking remain framework boundaries. |

| codex-rs/tui/src/theme_picker.rs | pycodex.tui.theme_picker | complete_slice | Theme picker preview, subtitle, and selection parameter semantics are ported; exact syntax highlighting, ratatui rendering, AppEventSender dispatch, and config persistence remain dependency boundaries. |

| codex-rs/tui/src/insert_history.rs | pycodex.tui.insert_history | complete_slice | History insertion wrapping, ANSI command, span styling, hyperlink, and row-accounting semantics are ported with a Python TerminalModel; exact crossterm/vt100/custom_terminal behavior remains a framework boundary. |

| codex-rs/tui/src/model_catalog.rs | pycodex.tui.model_catalog | complete | ModelCatalog snapshot/list-clone behavior is fully ported; no external runtime dependency remains for this module. |

| codex-rs/tui/src/session_state.rs | pycodex.tui.session_state | complete | Session state dataclasses and cwd retargeting workspace-root behavior are ported; external protocol types are intentionally represented as carried Python values. |

| codex-rs/tui/src/session_resume.rs | pycodex.tui.session_resume | complete | Rollout JSONL resume-state parsing and cwd/model/thread resolution semantics are ported: explicit UUID handling, malformed-line skip, empty-rollout error, session_meta fallback, latest turn_context precedence, StateRuntime-like model/cwd precedence, missing-history Continue(None), cwd normalization, allow_prompt gating, and current/session/exit prompt outcomes. Real Tui prompt UI, StateRuntime, ThreadId, and tracing/error-stack integration remain dependency boundaries. |

| codex-rs/tui/src/hooks_rpc.rs | pycodex.tui.hooks_rpc | complete | Hooks list/trust request helper semantics are ported with duck-typed app-server request handles: UUID-prefixed request ids, HooksList params, response coercion, cwd entry lookup/fallback, Untrusted/Modified review detection, hooks.state ConfigBatchWrite Upsert payloads, single-trust wrapper, and contextual request errors. Concrete app-server protocol types, transport, and ConfigWriteResponse decoding remain dependency boundaries. |

| codex-rs/tui/src/exec_command.rs | pycodex.tui.exec_command | complete | Command escaping/splitting and home-relative path behavior are fully ported with Python standard-library shlex/path semantics. |

| codex-rs/tui/src/cli.rs | pycodex.tui.cli | complete | TUI CLI option data model and module-owned approval-policy conflict marking are ported: all public/skipped/default fields, config-overrides default, Cli/TuiSharedCliOptions deref wrappers, mapping/object update semantics, and augment_args/augment_args_for_update conflict marking. Real clap parser generation and codex_utils_cli parsing remain dependency boundaries. |

| codex-rs/tui/src/multi_agents.rs | pycodex.tui.multi_agents | complete | Multi-agent picker/history-row presentation semantics are ported with Python span/cell models: picker labels/status dots, shortcut matching, spawn request summaries, prompt/status/error previews, agent labels, spawn/send/wait/resume/close history-row text, in-progress no-render branches, wait ordering, and first-agent-state fallback. Protocol enum structs, ratatui style rendering, crossterm key events, and app coordination remain dependency/framework boundaries. |

| codex-rs/tui/src/app_server_session.rs | pycodex.tui.app_server_session | complete_slice | App-server session helper/interface slice is ported: JSON-RPC unsupported-method detection, request facade sequencing, remote/embedded cwd/provider rules, config override and permission/sandbox lifecycle parameter construction. Full bootstrap/session response decoding and concrete app-server protocol transport remain runtime boundaries. |

| codex-rs/tui/src/bottom_pane/mentions_v2/popup.rs | pycodex.tui.bottom_pane.mentions_v2.popup | complete | Mentions v2 popup state is ported: file-search pending/result/empty-query state, query synchronization, stale result rejection, MAX_POPUP_ROWS capping, candidate replacement with selection clamp/reset, selection wrap/visibility, selected row lookup, search-mode cycling, row filtering, fixed required height, and semantic render delegation. Concrete ratatui WidgetRef/Buffer painting remains represented by the separate semantic render module. |

| codex-rs/tui/src/bottom_pane/title_setup.rs | pycodex.tui.bottom_pane.title_setup | complete | Terminal title setup semantics are ported: canonical and legacy item IDs, descriptions, preview-item mapping including spinner omission, separator/preview text rules, parser all-or-nothing behavior, configured-item ordering with dedup and unknown-id skip, semantic picker items, rate-limit preview naming, and confirm/cancel events. Concrete MultiSelectPicker internals and ratatui rendering remain widget/runtime boundaries represented by semantic view events. |
| codex-rs/tui/src/bottom_pane/title_setup.rs | pycodex.tui.bottom_pane.title_setup | complete | Tightened action-required preview parity: when Spinner is selected, Python now mirrors Rust's `build_action_required_title_text` branch with `[ ! ] Action Required` and ` | ` joining for non-spinner preview values. |

| codex-rs/tui/src/bottom_pane/footer.rs | pycodex.tui.bottom_pane.footer | complete_slice | Footer state/formatting semantics are ported: footer modes, key-hint defaults, shortcut/esc/activity mode transitions, footer-height line counting, passive status/agent lines, queue/status precedence, mode indicators, context text, and WSL paste-image shortcut binding. Full ratatui Span/Buffer rendering and exhaustive width-collapse layout remain renderer/widget boundaries. |

| codex-rs/tui/src/bottom_pane/file_search_popup.rs | pycodex.tui.bottom_pane.file_search_popup | complete_slice | File-search popup state is ported: pending/display query separation, waiting/empty prompt handling, stale result rejection, first-page result capping, selection wrap/clamp, selected path lookup, required height, and semantic row conversion. Concrete ratatui WidgetRef/Buffer rendering remains a renderer boundary. |
| codex-rs/tui/src/bottom_pane/file_search_popup.rs | pycodex.tui.bottom_pane.file_search_popup | complete_slice | Added stable-list behavior while a newer query is in flight: `set_query` updates `pending_query` and `waiting` but preserves the current display query, matches, and required height until matching results arrive. Concrete ratatui WidgetRef/Buffer rendering remains a renderer boundary. |
| codex-rs/tui/src/bottom_pane/file_search_popup.rs | pycodex.tui.bottom_pane.file_search_popup | complete_slice | Refreshed empty-result parity: matching empty results stop loading, clear selection, keep one placeholder row, and show `no matches`. |

| codex-rs/tui/src/bottom_pane/approval_overlay.rs | pycodex.tui.bottom_pane.approval_overlay | complete_slice | Approval overlay decision-routing semantics are ported: request matching, queue advancement, selection/cancel events, resolved-request dismissal, MCP Esc cancel precedence, option construction, footer hints, network target helpers, and permission-rule formatting. Concrete app-event transport, history cells, ListSelectionView internals, and ratatui rendering remain widget/runtime boundaries. |
| `bottom_pane/memories_settings_view.rs` | `pycodex.tui.bottom_pane.memories_settings_view` | `complete_slice` | Semantic popup model for memories settings, update/reset events, confirmation flow, key handling, and text render rows are available; framework widget rendering is intentionally adapted. |
| `bottom_pane/hooks_browser_view.rs` | `pycodex.tui.bottom_pane.hooks_browser_view` | `complete_slice` | Semantic hooks browser state machine is available with event rows, handler rows/details, trust/enablement event emission, Esc/Ctrl-C handling, and text rendering; framework widget styling is intentionally not copied. |
| `test_support.rs` | `pycodex.tui.test_support` | `complete_slice` | TUI test helper interfaces now provide deterministic `test_path_buf`/display helpers plus app-server wire conversion helpers for CLI session source and user/repo skill scopes. |
| `status/account.rs` | `pycodex.tui.status.account` | `complete` | Full semantic model for `StatusAccountDisplay::{ChatGpt,ApiKey}` is available, including optional payload fields and wire conversion helpers. |
| `chatwidget/session_header.rs` | `pycodex.tui.chatwidget.session_header` | `complete` | Full semantic `SessionHeader` state model is available with `new` and `set_model`. |
| `chatwidget/review.rs` | `pycodex.tui.chatwidget.review` | `complete` | Full semantic `ReviewState` data model is available, including real `RecentAutoReviewDenials` default and explicit tri-state pre-review token snapshot. |
| `chatwidget/warnings.rs` | `pycodex.tui.chatwidget.warnings` | `complete` | Full semantic warning display state is available with fallback model metadata warning slug extraction and deduplication. |
| `chatwidget/side.rs` | `pycodex.tui.chatwidget.side` | `complete` | Side-conversation ChatWidget helper methods are available as widget-like functions and a mixin, covering submit policy, placeholder toggling, active state, and context-label forwarding. |
| `chatwidget/hooks.rs` | `pycodex.tui.chatwidget.hooks` | `complete` | ChatWidget hooks helper methods are available as widget-like functions and a mixin, covering fetch events, loaded-result routing, error handling, browser view creation, and redraw requests. |
| `chatwidget/goal_validation.rs` | `pycodex.tui.chatwidget.goal_validation` | `complete_slice` | Goal objective validation helpers are available as widget-like functions and a mixin, covering live/queued source behavior, error formatting, pending-paste expansion boundary, and composer cleanup semantics. |
| `chatwidget/exec_state.rs` | `pycodex.tui.chatwidget.exec_state` | `complete` | Unified exec state helpers are available with running/process summary dataclasses, wait-state/streak behavior, source classification, parsed command classification, and command/action conversion. |
| `onboarding/mod.rs` | `pycodex.tui.onboarding` | `complete_slice` | Package boundary mirrors Rust `onboarding` module declarations through metadata and re-exports the two auth hyperlink helpers without marking the auth submodule behavior complete. |
| `public_widgets/mod.rs` | `pycodex.tui.public_widgets` | `complete_slice` | Package boundary mirrors Rust `public_widgets` module metadata and declared `composer_input` submodule without claiming submodule behavior completion. |
| `exec_cell/mod.rs` | `pycodex.tui.exec_cell` | `complete_slice` | Package boundary mirrors Rust `exec_cell` module metadata and re-exports selected model/render items while preserving submodule behavior as separate work. |
| `status/mod.rs` | `pycodex.tui.status` | `complete_slice` | Package boundary mirrors Rust `status` module metadata, declared submodules, and selected re-exports while preserving submodule behavior as separate work. |
| `app/test_support.rs` | `pycodex.tui.app.test_support` | `complete_slice` | Test support helpers provide semantic telemetry and effective-config app lookup; `make_test_app` remains an explicit full-App fixture boundary instead of a fabricated App. |
| `status/helpers.rs` | `pycodex.tui.status.helpers` | `complete` | Status helper functions are available with semantic implementations for model details, agents path summaries, plan names, compact token counts, directory display, timestamps, and title casing. |
| `status/remote_connection.rs` | `pycodex.tui.status.remote_connection` | `complete` | Remote connection status helpers are available with semantic target/endpoint shape support, sanitized websocket display addresses, unix socket display, and version formatting. |
| `onboarding/keys.rs` | `pycodex.tui.onboarding.keys` | `complete` | Fixed onboarding shortcut constants are ported as semantic `KeyBinding` tuples, matching Rust plain, Ctrl, and Ctrl+Shift bindings before user keymap configuration exists. |
| `status/format.rs` | `pycodex.tui.status.format` | `complete` | Status formatting helpers are ported: field label alignment, continuation indentation, label de-duplication, Unicode display width, and style-preserving line truncation use semantic Python Line/Span models. |
| `status/rate_limits.rs` | `pycodex.tui.status.rate_limits` | `complete_slice` | Rate-limit status shaping is ported for display data rows, stale detection, non-codex grouping, credits balance formatting, duration labels, progress bars, and duck-typed protocol snapshot conversion; concrete protocol DTOs/local-time rendering remain semantic boundaries. |
| `status/card.rs` | `pycodex.tui.status.card` | `complete_slice` | Status card semantic slice is available for token/context spans, rate-limit refresh/line shaping, permission/provider/url labels, usage-link hyperlink metadata, and lightweight status output composition; full Config/protocol/history-cell/ratatui rendering remains a dependency boundary. |
| `exec_cell/model.rs` | `pycodex.tui.exec_cell.model` | `complete` | Grouped exec-call model is ported: command output defaults, source helpers, exploring grouping, reverse call-id completion/append routing, flush/active/failure state transitions, and animation flag semantics. Parsed command and command source protocol types remain duck-typed boundary inputs. |
| `public_widgets/composer_input.rs` | `pycodex.tui.public_widgets.composer_input` | `complete_slice` | Public ComposerInput wrapper semantics are available for text submission, paste handling, hint overrides, desired height/cursor/render metadata, paste-burst state, and default construction; full ChatComposer internals and ratatui Buffer rendering remain dependency boundaries. |
| `exec_cell/render.rs` | `pycodex.tui.exec_cell.render` | `complete_slice` | Exec-cell renderer semantic slice is ported for active command construction, output truncation/ellipsis hints, command/exploring display lines, unified interaction summaries, transcript/raw helpers, long-token preservation, and row-aware truncation approximations; exact ratatui/ANSI/adaptive-wrap rendering remains a framework boundary. |
| `onboarding/auth.rs` | `pycodex.tui.onboarding.auth` | `complete_slice` | Onboarding auth state-machine semantics are ported for sign-in states/options, forced-login restrictions, API-key entry/save, active-attempt cancellation, account notifications, step state, animation suppression, and semantic hyperlink marking; async app-server transport, browser side effects, ratatui rendering, and headless device-code submodule remain boundaries. |
| `onboarding/auth/headless_chatgpt_login.rs` | `pycodex.tui.onboarding.auth.headless_chatgpt_login` | `complete_slice` | Headless ChatGPT device-code login semantics are ported for pending request setup, request-id guarded state/error transitions, stale response cancellation signal, pending/ready render text, animation scheduling guard, and semantic URL hyperlink marking; Tokio transport and ratatui Buffer rendering remain boundaries. |
| `chatwidget/rate_limits.rs` | `pycodex.tui.chatwidget.rate_limits` | `complete` | Chatwidget rate-limit warning and helper semantics are ported: constants, threshold warning state, 100% cap suppression, duration labels, fallback labels, switch prompt states, and app-server error classification. Full ChatWidget prompt orchestration remains out of scope. |
| `bottom_pane/bottom_pane_view.rs` | `pycodex.tui.bottom_pane.bottom_pane_view` | `complete` | BottomPaneView trait defaults are ported as a Python Protocol/default mixin, covering completion state, identity/selection, cancellation, paste burst, request consumption, resolved-request dismissal, terminal action title, and next-frame-delay defaults. Concrete views remain separate module contracts. |

### codex-tui `line_truncation.rs` - complete
- Python module: `pycodex.tui.line_truncation`
- Tests: `tests/test_tui_line_truncation.py`
- Notes: The full Rust module behavior is ported with semantic `Line`/`Span` values: display-width summation, span/style preserving truncation, zero-width span preservation, Rust-style empty-line return for `max_width == 0`, no-overflow identity return, and overflow truncation with ellipsis styled from the last retained span. Concrete ratatui types are intentionally represented by Python semantic models.

### codex-tui `terminal_hyperlinks.rs` - complete_slice
- Python module: `pycodex.tui.terminal_hyperlinks`
- Tests: `tests/test_tui_terminal_hyperlinks.py`
- Notes: Extended the existing OSC8/link-detection slice with semantic terminal-buffer mutation: `SemanticBuffer`/`SemanticCell`/`SemanticRect`, direct hyperlink cell marking, URL-style underlined cyan filtering, generic underlined filtering, scroll-row clipping, and blank/skip-cell guards. Exact ratatui `Paragraph` wrapping and concrete `Buffer` cell integration remain renderer-framework boundaries rather than silent fallbacks.

### codex-tui `style.rs` - complete
- Python module: `pycodex.tui.style`
- Tests: `tests/test_tui_style.py`
- Notes: The full Rust module behavior is ported with semantic `Style`/`Color` values: accent color selection, table separator blending/dimming, user-message/proposed-plan background blending, default terminal-palette facades, and no-op styles when terminal colors are unavailable. Exact `terminal_palette::best_color` quantization remains represented as a semantic RGB target, but no `style.rs` behavior is left unimplemented.

### codex-tui `width.rs` - complete
- Python module: `pycodex.tui.width`
- Tests: `tests/test_tui_width.py`
- Notes: The full Rust module behavior is ported: strict-positive usable content width after reserved-column subtraction, exhausted-width `None` fallback semantics, and the `u16` wrapper preserving the same contract with Python-side unsigned/u16 boundary checks.

### codex-tui `text_formatting.rs` - complete
- Python module: `pycodex.tui.text_formatting`
- Tests: `tests/test_tui_text_formatting.py`
- Notes: The full Rust module behavior is ported: first-character capitalization, JSON compact formatting, tool-result format/truncate budget, grapheme-aware text truncation, center path truncation with semantic ellipsis, front-truncation fallback, and English list joining. Python uses stdlib JSON and a combining-mark grapheme approximation; no ratatui/crossterm framework types are involved.

### codex-tui `render/line_utils.rs` - complete
- Python module: `pycodex.tui.render.line_utils`
- Tests: `tests/test_tui_render_line_utils.py`
- Notes: The full Rust module behavior is ported with semantic `Line`/`Span` values: borrowed-to-owned line cloning, append-owned-lines behavior, test-only blank-line detection with literal-space-only semantics, and prefixing with initial/subsequent spans while preserving line style and matching Rust's reconstructed-line alignment reset.

### codex-tui `render/renderable.rs` - complete
- Python module: `pycodex.tui.render.renderable`
- Tests: `tests/test_tui_render_renderable.py`
- Notes: The full module behavior is represented with Python semantic render primitives: default renderable behavior, string/span/line/paragraph height and render recording, `RenderableItem` dispatch, column/flex/row/inset layout, cursor position/style forwarding, and the `RenderableExt::inset` helper shape. Concrete ratatui `Buffer`, `Paragraph`, and crossterm cursor-style values are intentionally modeled as semantic Python values rather than framework objects.

### codex-tui `terminal_palette.rs` - complete_slice
- Python module: `pycodex.tui.terminal_palette`
- Tests: `tests/test_tui_terminal_palette.py`
- Notes: Ported the deterministic palette semantics: color-level enum, semantic RGB/indexed/default colors, xterm 256-color table generation with first-16 skip, perceptual-distance ANSI256 selection, truecolor/default fallback, startup-probe default color cache, environment-based stdout color-level approximation, and u8 index bounds. Real `supports_color` probing, crossterm OSC 10/11 default-color querying, and focus-event requery side effects remain platform/runtime boundaries.

### codex-tui `render/mod.rs` - complete
- Python module: `pycodex.tui.render`
- Tests: `tests/test_tui_render.py`
- Notes: The full Rust module behavior is ported: `Insets::tlbr`, `Insets::vh`, and `RectExt::inset` with saturating x/y/width/height geometry. Python exposes the Rust extension-trait shape through `RectExt.inset` plus the module-level `inset` helper, using semantic `Rect` values rather than ratatui framework types.
| `markdown_stream.rs` | `complete_slice` | `MarkdownStreamCollector` source-buffer commit/finalize/clear behavior and semantic plain-line helpers are ported in `pycodex.tui.markdown_stream`; full markdown rendering and ratatui styling remain a dependency boundary. |
| `chatwidget/goal_status.rs` | `complete` | Goal status indicator semantics are ported: status mapping, budget/time usage labels, active-turn elapsed accounting, and protocol-like status normalization. |
| `chatwidget/goal_menu.rs` | `complete` | Bare `/goal` summary semantics are ported: text rows, status labels, command hints, token budget display, and edit-status normalization. ChatWidget popup/event wiring remains outside this helper module. |
| `chatwidget/connectors.rs` | `complete_slice` | Connector cache state, refresh gating, mention snapshot lookup, connector labels/descriptions, semantic popup params, final/partial/error load handling, and enabled-state mutation are ported; concrete AppEvent/browser/bottom-pane runtime remains a boundary. |
| `chatwidget/command_lifecycle.rs` | `complete_slice` | Unified-exec process tracking, footer sync data, recent chunk retention, and terminal wait-streak semantics are ported with a Python lifecycle state model; ExecCell/transcript/AppEvent/redraw runtime remains a boundary. |
| `chatwidget/input_queue.rs` | `complete` | Queued input state is ported: category-separated previews, history-record fallback/override semantics, follow-up detection, enqueue helpers, and clear reset behavior. Full user-message rendering remains owned by `chatwidget/user_messages.rs`. |
| `chatwidget/interrupts.rs` | `complete` | Interrupt queue semantics are ported: prompt/lifecycle enqueueing, variant-specific resolved prompt removal, FIFO flush dispatch to duck-typed ChatWidget handlers, and helper fixture shapes. |
| `chatwidget/hook_lifecycle.rs` | `complete_slice` | Hook lifecycle reducer semantics are ported: active hook-cell creation/update, completion routing, persistent output flush, idle finish, visibility advancement, and frame timer scheduling data. Concrete HookCell rendering/AppEvent/frame-requester runtime remains a boundary. |
| `chatwidget/ide_context.rs` | `complete_slice` | Chat-widget IDE context command semantics are ported: enabled/warned state, /ide on/off/status handling, fetch success/failure messages, prompt-skip warning suppression, prompt injection routing, and status indicator sync. Lower-level IDE context fetching remains separate. |
| `chatwidget/reasoning_shortcuts.rs` | `complete` | Reasoning shortcut helper semantics are ported: effort rank/order, model-supported choices, next-effort movement, boundary messages, and semantic handler guardrails for modal/startup/unavailable/Plan-mode paths. |
| `chatwidget/keymap_picker.rs` | `complete_slice` | ChatWidget keymap picker integration is ported semantically: root/action/capture/debug/replace views, invalid-config errors, selected-action return routing, fast-mode filter, and atomic live keymap cache synchronization. Concrete keymap setup/runtime parsing remains separate. |


## 2026-06-12 - token_usage.rs

- Rust module: `codex-tui::token_usage`
- Python module: `pycodex.tui.token_usage`
- Status: `complete`
- Notes: Ported token usage structs and display semantics: zero detection, cached/non-cached input accounting, blended totals, raw context-window tokens, remaining-context percentage with 12k baseline and Rust-style rounding, separator formatting, cached/reasoning suffixes, negative-value clamp/raw-output behavior, and `TokenUsageInfo` defaults.

## 2026-06-12 - motion.rs

- Rust module: `codex-tui::motion`
- Python module: `pycodex.tui.motion`
- Status: `complete_slice`
- Notes: Ported motion mode selection, reduced-motion fallback behavior, semantic animated indicator/shimmer output, and source-tree animation primitive allowlist checks. Exact terminal truecolor detection and ratatui shimmer styling remain renderer/runtime boundaries.

## 2026-06-12 - shimmer.rs

- Rust module: `codex-tui::shimmer`
- Python module: `pycodex.tui.shimmer`
- Status: `complete_slice`
- Notes: Ported shimmer span generation with deterministic elapsed-time injection, padding/period sweep, cosine band intensity, fallback style thresholds, and semantic truecolor RGB blend output. Concrete terminal color probing and ratatui style/color values remain renderer/runtime boundaries.

## 2026-06-12 - permission_compat.rs

- Rust module: `codex-tui::permission_compat`
- Python module: `pycodex.tui.permission_compat`
- Status: `complete_slice`
- Notes: Ported legacy-compatible permission profile projection with bridgeable-profile preservation, managed-profile workspace-write rebuild, extra writable-root preservation, cwd de-duplication, network policy preservation, and tmp exclusion flags through the protocol permission facade. Concrete upstream `codex_protocol`/`codex_utils_absolute_path` types remain dependency boundaries.

## 2026-06-12 - service_tier_resolution.rs

- Rust module: `codex-tui::service_tier_resolution`
- Python module: `pycodex.tui.service_tier_resolution`
- Status: `complete_slice`
- Notes: Ported service-tier selection and core-update semantics with semantic config/model preset DTOs. The Rust `Option<Option<String>>` outer no-update branch is represented by Python `None`; update payloads are represented by strings because upstream has no `Some(None)` branch in this module.

## 2026-06-12 - table_detect.rs

- Rust module: `codex-tui::table_detect`
- Python module: `pycodex.tui.table_detect`
- Status: `complete`
- Notes: Ported the full pure text table/fence detection module, including GFM pipe-table structural parsing and incremental fenced-code context tracking. No framework/runtime boundary remains for this module.

## 2026-06-12 - resize_reflow_cap.rs

- Rust module: `codex-tui::resize_reflow_cap`
- Python module: `pycodex.tui.resize_reflow_cap`
- Status: `complete_slice`
- Notes: Ported terminal-specific resize reflow cap selection and explicit config handling with semantic terminal/config DTOs. Concrete `codex_terminal_detection::terminal_info()` and `running_in_vscode_terminal()` are represented as injectable runtime boundaries.

## 2026-06-12 - bottom_pane/mentions_v2/candidate.rs

- Rust module: `codex-tui::bottom_pane::mentions_v2::candidate`
- Python module: `pycodex.tui.bottom_pane.mentions_v2.candidate`
- Status: `complete_slice`
- Notes: Mention candidate DTO behavior is ported for selection variants, mention type ordering-adjacent labels, filesystem classification, tag padding, Candidate-to-SearchResult cloning, and semantic span styling. Exact ratatui `Span`/`Style` objects remain represented by Python semantic `SemanticSpan` data.

## 2026-06-12 - bottom_pane/textarea/vim.rs

- Rust module: `codex-tui::bottom_pane::textarea::vim`
- Python module: `pycodex.tui.bottom_pane.textarea.vim`
- Status: `complete_slice`
- Notes: Replaced interface-only scaffold with semantic Vim enum/state variants, `idx_range`, separator word-piece splitting, and a lightweight `TextAreaVim` model for word, big-word, paired delimiter, quoted-string, escape, line, and text-element exclusion range behavior. Full key-event routing and parent `TextArea` editing integration remain `bottom_pane/textarea.rs` scope.

## 2026-06-12 - bottom_pane/mentions_v2/mod.rs

- Rust module: `codex-tui::bottom_pane::mentions_v2`
- Python module: `pycodex.tui.bottom_pane.mentions_v2`
- Status: `complete`
- Notes: Parent package boundary now mirrors Rust `mod.rs` re-exports for `MentionV2Selection`, `MentionV2Popup`, and `build_search_catalog`. Candidate, popup, and search-catalog behavior remain tracked by their own module contracts.

## 2026-06-12 - bottom_pane/request_user_input/mod.rs

- Rust module: `codex-tui::bottom_pane::request_user_input`
- Python module: `pycodex.tui.bottom_pane.request_user_input`
- Status: `complete_slice`
- Notes: Added a semantic slice over the existing interface scaffold for constants, `Focus`, `ComposerDraft`, `AnswerState`, `FooterTip`, option/digit helpers, notes visibility, question wrapping, and footer-tip wrapping/height. Full overlay key handling, submission/queue lifecycle, paste burst integration, concrete app-server request types, `ChatComposer`, and ratatui snapshot rendering remain explicit follow-up boundaries.

## 2026-06-12 - bottom_pane/chat_composer.rs

- Rust module: `codex-tui::bottom_pane::chat_composer`
- Python module: `pycodex.tui.bottom_pane.chat_composer`
- Status: `complete_slice`
- Notes: Added the first semantic slice for the composer boundary: input-result and queued-action DTOs, config flags/default/plain-text preset, draft snapshot field shape, large-paste/input-size constants, too-large message copy, and plan-mode nudge copy. Full editing, popup routing, history, submission preparation, paste burst, attachments, app-event integration, and ratatui rendering remain explicit follow-up slices.
### diff_render.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/diff_render.rs`

Python target: `pycodex/tui/diff_render.py`

Status: `complete_slice`

Implemented semantic interface:

- `DiffLineType`
- `DiffTheme`
- `DiffColorLevel`
- `RichDiffColorLevel`
- `Style`
- `Span`
- `Line`
- `ResolvedDiffBackgrounds`
- `DiffRenderStyleContext`
- Diff theme/color constants and background-resolution helpers
- Terminal color-level promotion helper
- Path language hint helper
- Display-width and styled-span wrapping helpers

Blocked/follow-up interface:

- Full ratatui `Frame`/`Buffer` rendering remains blocked until a shared Python TUI render buffer is available.
- Syntax-highlight style extraction remains blocked on an injected or ported highlighting theme model.
- `FileChange` and `diffy` patch rendering should be ported as a later renderer slice, not as part of this low-level color/wrapping contract.
### history_cell/base.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/base.rs`

Python target: `pycodex/tui/history_cell/base.py`

Status: `complete_slice`

Implemented semantic interface:

- `HistoryCell` protocol
- `PlainHistoryCell`
- `WebHyperlinkHistoryCell`
- `PrefixedWrappedHistoryCell`
- `CompositeHistoryCell`
- module-level forwarding helpers for display, hyperlink display, transcript hyperlink, and raw lines
- semantic `plain_lines` and prefix wrapping helpers

Follow-up interface:

- Full renderer snapshot parity remains downstream of the shared TUI line/wrapping/render buffer model.
- Rust `adaptive_wrap_lines` exactness can be promoted from semantic approximation to full parity when the shared wrapping layer is expanded.
### history_cell/separators.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/separators.rs`

Python target: `pycodex/tui/history_cell/separators.py`

Status: `complete_slice`

Implemented semantic interface:

- `RuntimeMetricTotals`
- `RuntimeMetricsSummary`
- `FinalMessageSeparator`
- `runtime_metrics_label`
- `format_duration_ms`
- `pluralize`
- module-level `display_lines` and `raw_lines` forwarding helpers

Follow-up interface:

- Exact ratatui dim style and snapshot cell rendering remain renderer-level follow-up work.
### history_cell/notices.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/notices.rs`

Python target: `pycodex/tui/history_cell/notices.py`

Status: `complete_slice`

Implemented semantic interface:

- `UpdateAvailableHistoryCell`
- `CyberPolicyNoticeCell`
- `DeprecationNoticeCell`
- `new_warning_event`
- `new_cyber_policy_error_event`
- `new_deprecation_notice`
- `new_info_event`
- `new_error_event`
- module-level display/raw/hyperlink forwarding helpers

Follow-up interface:

- Exact ratatui border/glyph styling is intentionally left to the renderer layer.
- Upstream source glyphs appear encoding-damaged in this checkout, so Python keeps ASCII semantic prefixes for stable tests.
### history_cell/messages.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/messages.rs`

Python target: `pycodex/tui/history_cell/messages.py`

Status: `complete_slice`

Implemented semantic interface:

- `ByteRange`
- `TextElement`
- `UserHistoryCell`
- `ReasoningSummaryCell`
- `AgentMessageCell`
- `AgentMarkdownCell`
- `StreamingAgentTailCell`
- `build_user_message_lines_with_elements`
- `remote_image_display_line`
- `trim_trailing_blank_lines`
- `new_user_prompt`
- `new_reasoning_summary_block`
- module-level display/raw/transcript/hyperlink helpers

Blocked/follow-up interface:

- Exact markdown rendering with cwd-aware local file links awaits shared markdown renderer parity.
- Exact hyperlink column remapping across adaptive wrapping awaits shared terminal hyperlink wrapping parity.
- Streaming table/tail holdback behavior remains owned by streaming controller modules.
### history_cell/plans.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/plans.rs`

Python target: `pycodex/tui/history_cell/plans.py`

Status: `complete_slice`

Implemented semantic interface:

- `StepStatus`
- `PlanItemArg`
- `UpdatePlanArgs`
- `StreamingPlanTailCell`
- `ProposedPlanCell`
- `ProposedPlanStreamCell`
- `PlanUpdateCell`
- `new_plan_update`
- `new_proposed_plan`
- `new_proposed_plan_stream`
- module-level display/raw/hyperlink/continuation forwarding helpers

Blocked/follow-up interface:

- Exact plan markdown rendering and local-link cwd semantics await shared markdown renderer parity.
- Exact ratatui styling/glyph rendering remains a renderer-layer follow-up.
### history_cell/approvals.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/approvals.rs`

Python target: `pycodex/tui/history_cell/approvals.py`

Status: `complete_slice`

Implemented semantic interface:

- `ReviewDecision`
- `ApprovalDecisionSubject`
- `ApprovalDecisionActor`
- `ExecPolicyAmendment`
- `NetworkPolicyAmendment`
- `NetworkPolicyRuleAction`
- `truncate_exec_snippet`
- `exec_snippet`
- `non_empty_exec_snippet`
- `new_approval_decision_cell`
- guardian denied/approved/timed-out helper constructors
- `new_review_status_line`

Follow-up interface:

- Exact shell escaping and protocol approval type integration remain dependent-interface follow-up work.
- Exact ratatui glyph/color rendering remains renderer-layer follow-up work.
### history_cell/patches.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/patches.rs`

Python target: `pycodex/tui/history_cell/patches.py`

Status: `complete_slice`

Implemented semantic interface:

- `PatchHistoryCell`
- `create_diff_summary` module-local semantic fallback
- `new_patch_event`
- `new_patch_apply_failure`
- `new_view_image_tool_call`
- `new_image_generation_call`
- module-level display/raw helpers

Follow-up interface:

- Exact `diff_render::create_diff_summary` integration is a downstream dependency follow-up.
- Exact patch/image glyph styling remains renderer-layer follow-up work.
### history_cell/session.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/session.rs`

Python target: `pycodex/tui/history_cell/session.py`

Status: `complete_slice`

Implemented semantic interface:

- `SESSION_HEADER_MAX_INNER_WIDTH`
- `card_inner_width`
- `with_border`
- `with_border_with_inner_width`
- `with_border_internal`
- `padded_emoji`
- `TooltipHistoryCell`
- `SessionInfoCell`
- `SessionHeaderHistoryCell`
- `new_session_info`
- `is_yolo_mode`
- `has_yolo_permissions`
- module-level display/raw/height/transcript forwarding helpers

Follow-up interface:

- Exact ratatui border glyph/style parity remains renderer-layer work.
- Tooltip catalog lookup remains owned by `tooltips.rs`; this module consumes an override without performing network/catalog work.
- Full Config/ThreadSessionState protocol integration can replace the current dict/attribute facades later.
### history_cell/search.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/search.rs`

Python target: `pycodex/tui/history_cell/search.py`

Status: `complete_slice`

Implemented semantic interface:

- `WebSearchActionKind`
- `WebSearchAction`
- `WebSearchCell`
- `web_search_header`
- `web_search_action_detail`
- `web_search_detail`
- `new_active_web_search_call`
- `new_web_search_call`
- module-level display/raw helpers

Follow-up interface:

- Animated activity indicator rendering remains a UI renderer concern, not part of this semantic slice.
- Exact Rust `WebSearchAction` protocol integration can replace the current dict/attribute facade later.
### history_cell/hook_cell.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/hook_cell.rs`

Python target: `pycodex/tui/history_cell/hook_cell.py`

Status: `complete_slice`

Implemented semantic interface:

- `HookEventName`
- `HookRunStatus`
- `HookOutputEntryKind`
- `HookOutputEntry`
- `HookRunSummary`
- `HookRunState`
- `HookRunCell`
- `RunningHookGroupKey`
- `RunningHookGroup`
- `HookCell`
- lifecycle timers and transition helpers
- hook output prefix/event label/bullet helpers
- active/completed hook cell constructors
- module-level display/raw/transcript/render/height helpers

Follow-up interface:

- Exact ratatui rendering and motion shimmer/spinner output remain renderer/motion follow-up work.
- Full app-server protocol type integration can replace local dataclass facades later.
### history_cell/request_user_input.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/request_user_input.rs`

Python target: `pycodex/tui/history_cell/request_user_input.py`

Status: `complete_slice`

Implemented semantic interface:

- `ToolRequestUserInputQuestion`
- `ToolRequestUserInputAnswer`
- `RequestUserInputResultCell`
- `wrap_with_prefix`
- `split_request_user_input_answer`
- module-level display/raw helpers

Follow-up interface:

- Exact ratatui styling and glyphs remain renderer-layer follow-up work.
- Full app-server protocol DTO integration can replace local dataclass facades later.
### history_cell/mcp.rs - complete_slice

Rust source: `codex/codex-rs/tui/src/history_cell/mcp.rs`

Python target: `pycodex/tui/history_cell/mcp.py`

Status: `complete_slice`

Implemented semantic interface:

- `McpAuthStatus`
- `McpServerStatusDetail`
- `McpInvocation`
- `CallToolResult`
- `CompletedMcpToolCallWithImageOutput`
- `McpToolCallCell`
- `Resource`
- `ResourceTemplate`
- `McpServerStatus`
- `McpInventoryLoadingCell`
- auth labels, invocation formatting, content block rendering, image-output detection
- empty/status inventory output helpers
- active tool call and loading constructors

Follow-up interface:

- Real MCP runtime/RPC integration remains outside this history-cell module.
- Exact image decoding beyond magic-byte detection would require an approved image dependency.
- Exact ratatui styling and spinner rendering remain renderer/motion follow-up work.
### history_cell/exec.rs - complete_slice

- Python module: `pycodex.tui.history_cell.exec`
- Rust source: `codex/codex-rs/tui/src/history_cell/exec.rs`
- Status: `complete_slice`
- Notes: Implemented semantic history cells for background terminal interaction and `/ps` process summaries: waited/interacted headers, optional command labels, stdin/raw transcript extraction, first-stdin-line marker plus subsequent continuation indent, empty-process output, process/chunk truncation, max-process cap, remaining-count line, tiny-width handling, desired-height, and composite `/ps` output. Ratatui styling/color spans are represented by plain semantic lines.
### ascii_animation.rs - complete

- Python module: `pycodex.tui.ascii_animation`
- Rust source: `codex/codex-rs/tui/src/ascii_animation.rs`
- Status: `complete`
- Notes: The complete module-scoped behavior contract is represented in Python: construction through default/all variants or explicit variants, non-empty assertion, variant-index clamping, tick-aligned frame scheduling, current-frame selection by elapsed tick modulo, zero-tick defensive behavior, random variant picking that cannot keep the current variant, and frame requester callbacks. Python uses injectable clock/RNG test seams while preserving Rust semantics.
### goal_display.rs - complete

- Python module: `pycodex.tui.goal_display`
- Rust source: `codex/codex-rs/tui/src/goal_display.rs`
- Status: `complete`
- Notes: The complete module-scoped behavior contract is represented in Python: elapsed-time compaction with negative clamp, thread-goal status labels, objective/time/token usage summary formatting, optional-field omission, and local compact token formatting required by the module's visible output.
### mention_codec.rs - complete

- Python module: `pycodex.tui.mention_codec`
- Rust source: `codex/codex-rs/tui/src/mention_codec.rs`
- Status: `complete`
- Notes: The complete module-scoped behavior contract is represented in Python: linked mention dataclasses, ordered encode binding for repeated visible mentions, decode of `$` links and plugin `@` links into visible `$mention` text with captured paths, common environment-variable rejection, tool-path scheme and `SKILL.md` basename recognition, path trimming/empty-path rejection, and ASCII mention-name character rules.
### startup_error.rs - complete

- Python module: `pycodex.tui.startup_error`
- Rust source: `codex/codex-rs/tui/src/startup_error.rs`
- Status: `complete`
- Notes: The complete module-scoped behavior contract is represented in Python: `LocalStateDbStartupError::new`, stored state DB path/detail accessors, and Rust-style Display text for sqlite state DB initialization failures.
### git_action_directives.rs - complete

- Python module: `pycodex.tui.git_action_directives`
- Rust source: `codex/codex-rs/tui/src/git_action_directives.rs`
- Status: `complete`
- Notes: The complete module-scoped behavior contract is represented in Python: git action directive DTOs, `created_branch_cwd`, parsed assistant markdown visible-text stripping, malformed directive hiding without action creation, directive de-duplication with first-seen order, reverse lookup of last created branch cwd, quoted/bare attribute parsing, stage/commit/create-branch/push/create-pr construction, optional PR URL, and `isDraft == "true"` handling.
## 2026-06-12 - bottom_pane/pending_input_preview.rs semantic refresh

- Rust module: `codex-tui::bottom_pane::pending_input_preview`
- Python module: `pycodex.tui.bottom_pane.pending_input_preview`
- Status: `complete_slice`
- Notes: Added coverage for optional edit-binding suppression and empty-area render no-op. The Python module now covers local preview ordering, section headers, width guards, height clipping, three-line truncation, URL-like no-overflow behavior, pending/rejected/queued section order, optional interrupt binding, queued-message-only edit hint, hidden edit-binding branch, and empty-area render guard. Exact ratatui style/glyph cell output remains intentionally represented by stable semantic lines.

- Rust module: `codex-tui::bottom_pane::pending_input_preview`
- Python module: `pycodex.tui.bottom_pane.pending_input_preview`
- Status: `complete_slice`
- Notes: Reworked the semantic preview model around stable ASCII section/item/overflow markers to avoid local Rust checkout encoding damage while preserving Rust-owned behavior: empty/narrow no-op, queued-message desired height, section ordering for pending/rejected/queued inputs, remappable/hidden interrupt binding text, edit hint only for queued messages, render height clipping, three-line preview cap, multiline continuation indentation, and URL-like token no-overflow behavior. Exact ratatui cell styling and original terminal glyph rendering remain framework/encoding boundaries.
## 2026-06-12 - bottom_pane/pending_thread_approvals.rs completion
- Rust module: `codex-tui::bottom_pane::pending_thread_approvals`
- Python module: `pycodex.tui.bottom_pane.pending_thread_approvals`
- Status: `complete`
- Notes: Promoted the module contract to complete. Python covers owned thread-list update semantics, unchanged detection, empty predicate, test-visible threads snapshot, empty/narrow no-op rendering, warning row wrapping with initial/subsequent indentation, three-thread display cap, overflow marker, `/agent` switch hint, desired-height calculation, and area-height clipping. Ratatui `Buffer`/`Paragraph`/cell styling remains represented by semantic `RenderedLine` rows rather than concrete framework types.
| codex-rs/tui/src/pager_overlay.rs | pycodex.tui.pager_overlay | complete_slice | Added transcript live-tail cache invalidation/removal parity: changed keys rebuild render-only tail state and `None` keys clear cached tail/renderable state. Concrete ratatui rendering and hyperlink buffer marking remain framework boundaries. |
### codex-tui `terminal_hyperlinks.rs` - complete_slice update
- Python module: `pycodex.tui.terminal_hyperlinks`
- Tests: `tests/test_tui_terminal_hyperlinks.py::test_mark_buffer_hyperlinks_follow_word_wrapping`
- Status: `complete_slice`
- Notes: Extended semantic terminal-buffer mutation with wrapped-line hyperlink remapping before OSC8 cell marking. This covers the Rust word-wrapping hyperlink behavior without fabricating ratatui `Paragraph`/`Buffer`; exact framework wrapping fidelity remains a renderer boundary.
### codex-tui `bottom_pane/status_line_style.rs` - complete update
- Python module: `pycodex.tui.bottom_pane.status_line_style`
| `pycodex/tui/bottom_pane/status_line_style.py` | `complete` | Refreshed visible separator parity with an explicit test for Rust's exact `STATUS_LINE_SEPARATOR` copy (`" è·¯ "`). |
- Tests: `tests/test_tui_bottom_pane_status_line_style.py`
- Status: `complete`
- Notes: Completed the module-scoped semantic contract for status-line styling: all Rust item-to-accent mappings, separator/text ordering, theme resolver/fallback behavior, color softening, disabled-theme dimming, and PR underline are covered. Theme scope resolution itself remains a dependency boundary in `render/highlight`, not unfinished behavior in this module.
### codex-tui `terminal_palette.rs` - complete_slice update
- Python module: `pycodex.tui.terminal_palette`
- Tests: `tests/test_tui_terminal_palette.py::test_rgb_color_rejects_out_of_u8_channels`
- Status: `complete_slice`
- Notes: Tightened the semantic color-construction boundary by enforcing Rust `u8` RGB channel constraints in Python `rgb_color`. Terminal probing side effects remain explicit platform/runtime boundaries.
### codex-tui `resize_reflow_cap.rs` - complete update
- Python module: `pycodex.tui.resize_reflow_cap`
- Tests: `tests/test_tui_resize_reflow_cap.py`
- Status: `complete`
- Notes: Completed the module-scoped resize-reflow cap strategy: terminal-specific caps, full fallback terminal bucket, VS Code probe precedence, configured limit/disabled behavior, and unknown-terminal-under-multiplexer fallback. Concrete terminal detection remains an injected dependency boundary.
### codex-tui `permission_compat.rs` - complete_slice update
- Python module: `pycodex.tui.permission_compat`
- Tests: `tests/test_tui_permission_compat.py::test_legacy_compatible_permission_profile_sets_tmpdir_exclusion_from_write_access`
- Status: `complete_slice`
- Notes: Extended the fallback compatibility projection with TMPDIR exclusion parity: writable TMPDIR keeps the env tmpdir included, while non-writable TMPDIR sets `exclude_tmpdir_env_var`. Real `/tmp` existence/writability probing remains a platform boundary.
### codex-tui `service_tier_resolution.rs` - complete update
- Python module: `pycodex.tui.service_tier_resolution`
- Tests: `tests/test_tui_service_tier_resolution.py`
- Status: `complete`
- Notes: Completed the module-scoped service-tier selection contract, including the `Some(false)` opt-out boundary, FastMode gate, configured/default/unsupported tier paths, core update fallback behavior, and model tier support lookup. The Python boundary intentionally flattens Rust `Option<Option<String>>` to `None` or a string because this Rust module only emits outer `None` or `Some(Some(value))`.
### codex-tui `shimmer.rs` - complete_slice update
- Python module: `pycodex.tui.shimmer`
- Tests: `tests/test_tui_shimmer.py::test_shimmer_sweep_repeats_every_two_seconds`
- Status: `complete_slice`
- Notes: Added the two-second modulo sweep repeat boundary to the semantic shimmer span model. Real terminal color capability probing and ratatui style objects remain renderer/runtime boundaries.
### codex-tui `motion.rs` - complete_slice update
- Python module: `pycodex.tui.motion`
- Tests: `tests/test_tui_motion.py::test_animation_primitives_are_only_used_by_motion_module`
- Status: `complete_slice`
- Notes: Tightened motion primitive allowlist parity by covering both forbidden direct calls, `spinner(...)` and `shimmer_spans(...)`, while still ignoring comment-only matches. Exact animated glyph/style rendering remains a renderer/runtime boundary.
### codex-tui `terminal_palette.rs` - complete_slice update
- Python module: `pycodex.tui.terminal_palette`
- Tests: `tests/test_tui_terminal_palette.py::test_best_color_truecolor_and_unknown_paths`
- Status: `complete_slice`
- Notes: Added explicit `Ansi16` fallback coverage for `best_color`, matching Rust's default-color path for non-truecolor/non-ANSI256 terminals. Real stdout capability probing remains a runtime boundary.
### codex-tui `motion.rs` - complete_slice update
- Python module: `pycodex.tui.motion`
- Tests: `tests/test_tui_motion.py::test_animated_activity_indicator_blinks_on_six_hundred_ms_ticks`
- Status: `complete_slice`
- Notes: Added deterministic coverage for the 600ms animated activity indicator cadence. Truecolor shimmer delegation and exact ratatui styling remain renderer/runtime boundaries.
### codex-tui `terminal_palette.rs` - complete_slice update
- Python module: `pycodex.tui.terminal_palette`
- Tests: `tests/test_tui_terminal_palette.py::test_default_colors_can_be_seeded_from_startup_probe_facade`
- Status: `complete_slice`
- Notes: Added startup-probe facade parity for copying external `fg`/`bg` default-color fields into the terminal-palette cache. Real terminal default-color querying remains a platform/runtime boundary.
### codex-tui `shimmer.rs` - complete_slice update
- Python module: `pycodex.tui.shimmer`
- Tests: `tests/test_tui_shimmer.py::test_truecolor_shimmer_blends_default_background_toward_foreground`
- Status: `complete_slice`
- Notes: Added deterministic truecolor blend parity using injected default foreground/background colors and Rust's `0.9` center-band scale. Real terminal color probing remains a runtime boundary.
### codex-tui `markdown_stream.rs` - complete_slice update
- Python module: `pycodex.tui.markdown_stream`
- Tests: `tests/test_tui_markdown_stream.py::test_finalize_and_drain_source_after_full_commit_clears_bookkeeping`
- Status: `complete_slice`
- Notes: Repaired newline literal handling in the Python source-boundary collector and tests, then added final-drain-after-full-commit state reset parity. Full markdown rendering and ratatui line styling remain renderer/dependency boundaries.
### codex-tui `token_usage.rs` - complete update
- Python module: `pycodex.tui.token_usage`
- Tests: `tests/test_tui_token_usage.py::test_display_format_omits_negative_reasoning_suffix`
- Status: `complete`
- Notes: Tightened display-format parity for reasoning suffix omission when the reasoning count is negative; the module remains complete.
### codex-tui `render/line_utils.rs` - complete update
- Python module: `pycodex.tui.render.line_utils`
- Tests: `tests/test_tui_render_line_utils.py`
- Status: `complete`
- Notes: Completed the module-scoped line utility behavior, including empty-input prefixing. Python semantic Line/Span values stand in for ratatui borrowed/owned line types.
### codex-tui `render/renderable.rs` - complete_slice update
- Python module: `pycodex.tui.render.renderable`
- Tests: `tests/test_tui_render_renderable.py::test_flex_renderable_gives_rounding_remainder_to_last_flex_child`
- Status: `complete_slice`
- Notes: Added FlexRenderable remainder-allocation parity: the last flex child receives the leftover space after integer division. Framework buffer/cursor objects remain semantic boundaries.
### codex-tui `render/renderable.rs` - complete_slice update
- Python module: `pycodex.tui.render.renderable`
- Tests: `tests/test_tui_render_renderable.py::test_row_renderable_stops_rendering_when_width_is_exhausted`
- Status: `complete_slice`
- Notes: Added RowRenderable width-exhaustion clipping parity: once remaining width is zero, later children are not rendered. Concrete ratatui buffer behavior remains a semantic recording boundary.
### codex-tui `render/renderable.rs` - complete_slice update
- Python module: `pycodex.tui.render.renderable`
- Tests: `tests/test_tui_render_renderable.py::test_column_renderable_clips_children_to_visible_area`
- Status: `complete_slice`
- Notes: Added ColumnRenderable parent-area intersection parity: partially visible children render only their clipped rect. Concrete ratatui buffer behavior remains a semantic recording boundary.
### codex-tui `transcript_reflow.rs` - complete update
- Python module: `pycodex.tui.transcript_reflow`
- Tests: `tests/test_tui_transcript_reflow.py::test_has_pending_reflow_tracks_pending_until_state`
- Status: `complete`
- Notes: Tightened pending-state helper coverage for `has_pending_reflow` and `clear_pending_reflow`; the resize-reflow scheduling module remains complete.
### codex-tui `terminal_palette.rs` - complete_slice update
- Python module: `pycodex.tui.terminal_palette`
- Tests: `tests/test_tui_terminal_palette.py::{test_default_colors_can_be_seeded_from_startup_probe,test_default_colors_can_be_seeded_from_startup_probe_facade}`
- Status: `complete_slice`
- Notes: Added explicit startup-probe `None` cache-clear parity for default foreground/background colors. Real terminal default-color querying and attempted-cache side effects remain runtime boundaries.

## 2026-06-12 - bottom_pane/status_surface_preview.rs completion refresh

- Rust module: `codex-tui::bottom_pane::status_surface_preview`
- Python module: `pycodex.tui.bottom_pane.status_surface_preview`
- Status: `complete`
- Notes: Completed preview data semantics: enum order/placeholders, default population, live value precedence, non-overwriting placeholders, placeholder suppression, live-only rate-limit label/description derivation, status-line item to preview item mapping, themed status-line bridge, and empty filtered segment omission. Downstream status-line styling remains owned by `status_line_style`/`status_line_setup`.
| `pycodex/tui/bottom_pane/footer.py` | `complete_slice` | Refreshed footer parity evidence for passive status + active-agent right indicator composition and queue-hint suppression of passive footer status layout. |
| `pycodex/tui/bottom_pane/status_line_setup.py` | `complete_slice` | Refreshed enum-contract parity evidence for `StatusLineItem`: `context-remaining` parse/display, all description arms, and every status-line item to preview-item mapping. |
| `pycodex/tui/bottom_pane/action_required_title.py` | `complete` | Refreshed parity evidence for iterator semantics: duplicate input items are preserved in order and `value_for` is not invoked for Spinner or explicitly excluded title items. |
| `pycodex/tui/bottom_pane/unified_exec_footer.py` | `complete_slice` | Refreshed render-boundary parity evidence for Rust's empty-area no-op when render width is zero; exact ratatui buffer mutation remains a renderer boundary. |
| `pycodex/tui/bottom_pane/chat_composer/footer_state.py` | `complete_slice` | Refreshed flash helper evidence for replacement semantics and preserving supplied `Line` span content/style. |
| `pycodex/tui/bottom_pane/chat_composer/popup_state.py` | `complete` | Refreshed evidence for Rust-like active popup field replacement and no-payload `None` variant behavior; concrete popup payload behavior remains owned by the corresponding modules. |
| `pycodex/tui/bottom_pane/chat_composer/draft_state.py` | `complete_slice` | Refreshed evidence for mutable draft flags, pending paste tuple storage, and integer-keyed mention binding map shape. |
| `pycodex/tui/bottom_pane/chat_composer/attachment_state.py` | `complete_slice` | Refreshed evidence for placeholder-preserving submission take and `clear_remote_image_urls` clearing remote selection without relabeling local placeholders. |
| `pycodex/tui/bottom_pane/chat_composer/slash_input.py` | `complete_slice` | Refreshed command-under-cursor evidence for Rust's slash-boundary cursor branch (`cursor <= name_start`) used by popup filter text. |
| `pycodex/tui/bottom_pane/chat_composer/history_search.py` | `complete_slice` | Refreshed footer match action copy to use Rust's ` Â· ` separator between accept/cancel hints. |
| `pycodex/tui/line_truncation.py` | `complete` | Refreshed overflow ellipsis parity: `truncate_line_with_ellipsis_if_overflow` now appends the semantic Rust ellipsis character `¡­` with the previous span style. |
| `pycodex/tui/width.py` | `complete` | Refreshed interface guardrail evidence: Python rejects negative usize-compatible widths and `u16` wrapper values above `u16::MAX` instead of silently coercing them. |
| `codex-tui/src/text_formatting.rs` | complete | Added JSON string/escape-state parity coverage for `format_json_compact`; Python semantic model remains aligned for this module slice. |
| `markdown_stream.rs` | `complete_slice` | Added source-boundary resume parity for `commit_complete_source`: incomplete tails remain buffered after a commit and are emitted only when later completed by newline. Full markdown-to-ratatui rendering remains a dependency boundary. |
| `key_hint.rs` | `complete` | Full key-binding primitive contract is covered: normalization, matching, plain-text classification, constructors, display labels/spans, AltGr boundary, and Python 3.7-compatible semantic DTOs. |
| `terminal_hyperlinks.rs` | `complete_slice` | Added `HyperlinkLine::push_span` parity coverage: appended web spans record display-column ranges, while empty spans and non-web destinations do not create hyperlinks. Exact ratatui paragraph wrapping remains a renderer boundary. |
| `additional_dirs.rs` | `complete` | Added independent full-disk-write policy guard coverage for managed permission profiles; the module warning contract remains complete. |
| `motion.rs` | `complete_slice` | Fixed animated activity indicator millisecond bucket parity by rounding elapsed seconds to integer milliseconds before the Rust 600ms blink calculation; semantic shimmer/truecolor rendering remains a framework boundary. |
| `config_update.rs` | `complete_slice` | Corrected app-server request-id prefixes to match Rust (`tui-config-write-`, `tui-config-read-`, `tui-skill-config-write-`) while keeping transport response typing caller-provided. |
| `cwd_prompt.rs` | `complete_slice` | Added vim-style `j`/`k` highlight navigation and numeric `1` Session selection coverage for `CwdPromptScreen::handle_key`; concrete ratatui modal rendering and real Tui event stream remain framework boundaries. |
| `terminal_palette.rs` | `complete_slice` | Added ANSI256 `best_color` coverage proving Rust `xterm_fixed_colors().skip(16)` behavior: theme-dependent system color indices 0..15 are never selected. Real terminal color probing remains a platform side-effect boundary. |
| `debug_config.rs` | `complete_slice` | Added `format_network_constraints` scalar field-order coverage for proxy ports, upstream/non-loopback/socket flags, managed-domain-only, and local-binding fields; ratatui `Line`/history-cell output remains represented as semantic strings. |
| `permission_compat.rs` | `complete_slice` | Added fallback `/tmp` exclusion parity: rebuilt workspace-write profiles exclude `/tmp` unless it exists and is writable under the source file-system policy; legacy protocol DTOs remain the dependency boundary. |
| `audio_device.rs` | `complete_slice` | Added configured/default missing-device selection error coverage for microphone and speaker paths; real `cpal` host enumeration remains blocked behind explicit injected-host boundary. |
| `clipboard_paste.rs` | `complete_slice` | Added WSL Windows-path conversion coverage for drive roots, mixed separators, and empty component filtering; native image clipboard capture remains blocked behind arboard/image dependency boundary. |
| `clipboard_copy.rs` | `complete_slice` | Added injected-backend parity for local tmux error composition when native clipboard, tmux clipboard, and OSC 52 fallback all fail; real native clipboard remains an explicit dependency boundary. |
| `approval_events.rs` | `complete` | Full approval event DTO contract is covered: effective approval id, explicit/default decision branches, network Allow amendment ordering, additional permissions, execpolicy amendment, patch approval shape, and Python 3.7-compatible annotations. |
| `branch_summary.rs` | `complete_slice` | Added direct REST commit-to-PR parser parity for first-open PR filtering; real `gh api` execution remains behind the injected workspace-command runner boundary. |
| `collaboration_modes.rs` | `complete_slice` | Added explicit cloned-return parity for collaboration mode masks; builtin preset discovery remains injected/semantic and `ModelCatalog` stays intentionally ignored as in Rust. |
| `custom_terminal.rs` | `complete_slice` | Added explicit empty-viewport `Terminal::clear` no-op parity; full ratatui/crossterm backend integration remains blocked behind the renderer/framework boundary. |
| `diff_model.rs` | `complete_slice` | Added direct-construction required-field boundary coverage for `FileChange` variants; renderer-level diff presentation remains owned by `diff_render.rs`. |
| `frames.rs` | `complete_slice` | Added authoritative upstream frame-file content coverage for `frames_for!`; Python continues to hard-fail on missing frame files rather than fabricating animation data. |
| `npm_registry.rs` | `complete_slice` | Added object-map validation coverage for `NpmPackageInfo` deserialization shape; live registry fetching remains outside this pure readiness-check module. |
| `notifications/bel.rs` | `complete` | Audited full module contract: BEL ANSI emission, message ignoring, repeated notify writes, Python stream flush semantics, and explicit Windows WinAPI rejection are covered. Python type annotations were normalized for Python 3.7 compatibility. |
| `notifications/osc9.rs` | `complete_slice` | Added repeated-notify OSC 9 emission coverage; Python keeps injectable streams while preserving one sequence per `notify` call and parent tmux detection remains a separate boundary. |
| `session_log.rs` | `complete_slice` | Added `SessionLogger::open` OnceLock first-file retention parity; Python keeps injectable loggers for tests while preserving the global logger boundary. |

## 2026-06-12 - oss_selection.rs press-only key event refinement
- Rust module: `codex-tui::oss_selection`
- Python module: `pycodex.tui.oss_selection`
- Status: `complete_slice`
- Notes: Refined `OssSelectionWidget.handle_key_event` to match Rust's `KeyEventKind::Press` gate; non-press events remain consumed by the modal but do not mutate selection or complete the widget.
| `external_agent_config_migration_startup.rs` | `pycodex.tui.external_agent_config_migration_startup` | `complete_slice` | Added parity coverage for the Rust import-failure retry loop: migration errors are surfaced back into the prompt while retaining selected items, and a later successful import continues startup with the normal success message. |
| `model_migration.rs` | `pycodex.tui.model_migration` | `complete` | Full semantic model-migration prompt contract is covered: copy generation, markdown fill, menu/key state machine, non-opt-out acceptance, Ctrl exit, semantic render rows, long URL tail preservation, alt-screen lifecycle, initial draw/redraw, Paste ignore, and exhaustion accept. Python uses semantic rows instead of ratatui snapshot cells. |
| `debug_config.rs` | `pycodex.tui.debug_config` | `complete_slice` | Added explicit parity coverage for the empty MDM raw value branch in `render_mdm_layer_details`; ratatui `Line` output remains represented as semantic strings. |
| `config_update.rs` | `pycodex.tui.config_update` | `complete_slice` | Refined the feature-toggle catalog adapter to prefer Rust's `default_enabled` field before the Python fallback `default`, preserving default-false clear semantics for injected `FEATURES`-shaped specs. |
| `audio_device.rs` | `pycodex.tui.audio_device` | `complete_slice` | Added output default-stream-config failure coverage with injected audio devices; real `cpal` host/device enumeration remains an explicit platform boundary. |
| pp_command.rs | pycodex.tui.app_command | complete_slice | Added explicit parity coverage for user_turn owned item-vector semantics: constructor copies the supplied items list before storing semantic payload data. |
| `app_command.rs` | `pycodex.tui.app_command` | `complete_slice` | Added explicit parity coverage for `user_turn` owned item-vector semantics: constructor copies the supplied items list before storing semantic payload data. |
| `live_wrap.rs` | `pycodex.tui.live_wrap` | `complete` | Added explicit zero-width clamp parity for `RowBuilder::new` and `set_width`, preserving Rust's `width.max(1)` invariant before wrapping. |
| `app/pets.rs` | `pycodex.tui.app.pets` | `complete_slice` | Implemented semantic helpers for ambient pet shutdown/render-error and picker preview render-error handling. Terminal errors propagate, asset errors update chat-widget state and attempt image clearing, and unported background/config methods raise explicit `not_ported` errors. |
| `app/background_requests.rs` | `pycodex.tui.app.background_requests` | `complete_slice` | Implemented Rust-test-covered pure helpers: marketplace source normalization, CLI-only marketplace filtering, MCP inventory map conversion, and feedback upload param construction. App-server RPC launchers remain explicit `not_ported` runtime boundaries. |
| `app/config_persistence.rs` | `pycodex.tui.app.config_persistence` | `complete_slice` | Implemented pure effective-config extraction helpers and overridden-write message fallback. Runtime config rebuild, disk persistence, feature-write side effects, and App/ChatWidget sync paths remain explicit `not_ported` boundaries. |
| `app/plugin_mentions.rs` | `pycodex.tui.app.plugin_mentions` | `complete_slice` | Implemented pure plugin-list-to-mention enrichment helpers and eligibility filtering. The app-server `fetch_plugin_mentions` RPC remains an explicit `not_ported` runtime boundary. |
| `app/platform_actions.rs` | `pycodex.tui.app.platform_actions` | `complete_slice` | Implemented portable platform-action semantics for sandbox state defaults, side-return shortcut matching, and failed-scan warning event construction. Windows sandbox scanning remains an explicit `not_ported` platform side-effect boundary. |
| `app/thread_goal_actions.rs` | `pycodex.tui.app.thread_goal_actions` | `complete_slice` | Implemented pure helper parity for ephemeral thread-goal error detection/message construction and goal replacement confirmation status rules. Goal menu/editor/set/clear UI and app-server paths remain explicit `not_ported` boundaries. |
| `app/thread_routing.rs` | `pycodex.tui.app.thread_routing` | `complete_slice` | Implemented pure routing predicates for startup wait/prompt handling, active thread event gating, and non-primary shutdown failover target selection. Thread channels, app-server operation submission, replay, and permission-profile config integration remain explicit `not_ported` boundaries. |
| `app/session_lifecycle.rs` | `pycodex.tui.app.session_lifecycle` | `complete_slice` | Implemented pure session lifecycle error classifiers for terminal thread-read failures, closed-state inference, and includeTurns fallback detection. Agent picker, live attach/select, fresh-session, and resume flows remain explicit `not_ported` boundaries. |
| `app/thread_session_state.rs` | `pycodex.tui.app.thread_session_state` | `complete_slice` | Implemented semantic helpers for active cached-session service-tier/permission sync and thread/read fallback session construction. Async App channel/store mutation and StateDB model lookup remain explicit runtime boundaries. |
| `app/thread_settings.rs` | `pycodex.tui.app.thread_settings` | `complete_slice` | Implemented pure thread-settings helpers for changed-field detection and semantic settings-to-session application. App-server thread-settings update sending and async channel/store writes remain explicit `not_ported` boundaries. |
| `app/startup_prompts.rs` | `pycodex.tui.app.startup_prompts` | `complete_slice` | Implemented pure startup prompt helpers for model migration gating, accepted migration event sequencing, model availability NUX selection, and harness writable-root normalization. TUI prompt execution and config persistence remain explicit `not_ported` boundaries. |
| `app/event_dispatch.rs` | `pycodex.tui.app.event_dispatch` | `complete_slice` | Implemented semantic exit-mode planning for `handle_exit_mode` and `SHUTDOWN_FIRST_EXIT_TIMEOUT = 2s`. Exhaustive `AppEvent` dispatch and actual async shutdown remain explicit `not_ported` boundaries. |
| `app/app_server_event_targets.rs` | `pycodex.tui.app.app_server_event_targets` | `complete` | Thread targeting helpers are fully ported at semantic level: `server_request_thread_id`, `ServerNotificationThreadTarget`, and `server_notification_thread_target` cover Rust scoped/global request variants, warning/guardian/thread notification routing, ThreadStarted nested thread IDs, and invalid thread-id classification. |
| `app/input.rs` | `pycodex.tui.app.input` | `complete_slice` | Implemented semantic app input helpers for keymap availability, backtrack Esc handling/rejection, side-edit unavailable message, and external-editor request/reset state. Full async key handling, terminal/TUI effects, agent navigation, and editor process execution remain explicit `not_ported` boundaries. |
| `app/app_server_requests.rs` | `pycodex.tui.app.app_server_requests` | `complete_slice` | Strengthened pending request correlation parity with Python tests for all Rust unit-test-covered branches plus `contains_server_request`, unsupported legacy/attestation messages, approval-id fallback, notification removal, and clear semantics. App-server client rejection transport remains outside this semantic slice. |
| `app/side.rs` | `pycodex.tui.app.side` | `complete_slice` | Implemented semantic side-conversation helpers for constants/prompts, parent status/state changes, UI sync labels, start blocking/error mapping, side discard selection, user-message restore, and fork snapshot reset. Async app-server fork/inject/select/discard/interrupt paths remain explicit `not_ported` runtime boundaries. |
| `bottom_pane/app_link_view.rs` | `pycodex.tui.bottom_pane.app_link_view` | `complete_slice` | Added URL elicitation/auth boundary parity for non-URL rejection, codex-app auth metadata validation, ChatGPT host restriction, connector metadata trim/fallback behavior, and generic URL host acceptance. |
| `app/resize_reflow.rs` | `pycodex.tui.app.resize_reflow` | `complete_slice` | Implemented semantic resize-reflow helpers for trailing stream-run detection, initial replay row retention, wrap-policy selection, history-insert separator behavior, row-capped transcript-tail rendering, stream-time detection, and history emission reset. Actual terminal resize clearing/insertion and debounce scheduling remain explicit runtime boundaries. |
| `bin/md-events.rs` | `pycodex.tui.bin.md-events` | `blocked` | Read-error handling is represented, but successful event output is blocked on faithful `pulldown_cmark::Parser` Debug-event parity. The Python module raises explicit `not_ported` for parser/main success paths rather than faking Markdown events. |
| `chatwidget/status_state.rs` | `pycodex.tui.chatwidget.status_state` | `complete` | Implemented pure ChatWidget status state: working status defaults, guardian-review status aggregation/update/finish, terminal-title status buckets, status setter, and retry status header remember/take-once behavior. |
| `chatwidget/status_controls.rs` | `pycodex.tui.chatwidget.status_controls` | `complete_slice` | Implemented semantic ChatWidget status controls for status detail normalization, footer/status-line setters, status-line config setup, terminal-title preview/revert/commit, cwd-gated branch/git summary updates, context percent/usage helpers, limit display, and reasoning-effort labels. View construction, full status history output, rendering, and async lookup remain runtime boundaries. |

### codex-tui::chatwidget::notifications - complete_slice (2026-06-12)

- Implemented semantic Python interface for notification variants, notification settings filtering, display text generation, input-request summaries, and pending notification coalescing.
- Rust framework boundary note: `ChatWidget::maybe_post_pending_notification(&mut Tui)` is modeled by returning the pending display string; actual terminal/desktop notification delivery remains outside this module.
- Status: `complete_slice`.

### codex-tui::chatwidget::service_tiers - complete_slice (2026-06-12)

- Implemented semantic Python interface for chatwidget service-tier state, fast-mode gating, current-model service-tier commands, service-tier toggles, and override/persist selection events.
- Reuses the existing `service_tier_resolution` Python port for effective service-tier and core-update resolution.
- Rust framework boundary note: `AppEvent::CodexOp(AppCommand::override_turn_context(...))` and `PersistServiceTierSelection` are modeled as semantic `ServiceTierSelectionEvent` values; real app event channel delivery remains outside this module.
- Status: `complete_slice`.

### codex-tui::chatwidget::status_surfaces - complete_slice (2026-06-12)

- Implemented semantic Python interface for status-surface selections, status/title item parsing with invalid collection, rate-limit window selection helpers, terminal-title truncation, spinner frame calculation, and action-required prefix timing.
- Reuses existing Python `StatusLineItem`, `TerminalTitleItem`, and rate-limit display models instead of duplicating Rust framework types.
- Boundary note: real `ChatWidget` refresh orchestration, git summary/branch async lookup, terminal OSC title writes, and full permission/approval display formatting are not completed in this slice; unsupported framework-dependent functions raise `NotImplementedError`.
- Status: `complete_slice`.

### codex-tui::chatwidget::streaming - complete_slice (2026-06-12)

- Implemented semantic Python state model for streaming status restoration, reasoning header extraction, reasoning transcript accumulation, stream-finished status hiding, message-completion restore flags, and active stream-tail clearing.
- Added `extract_first_bold` locally for the streaming behavior contract; this does not mark parent `chatwidget.rs` complete.
- Boundary note: controller rendering, adaptive chunking, consolidation events, interrupt queue ownership, and actual history-cell/TUI mutation are still framework/runtime work outside this slice.
- Status: `complete_slice`.

### codex-tui::chatwidget::permissions_menu - complete_slice (2026-06-12)

- Implemented semantic Python interface for permission profile menu construction, builtin/custom item ordering, active selection flags, disabled reasons, and selection action payloads.
- Boundary note: actual `bottom_pane.show_selection_view`, app-event channel dispatch, approval confirmation dialogs, and full permission validation stay in neighboring modules/runtime; this module returns semantic `SelectionViewParams`/`PermissionMenuAction` data.
- Status: `complete_slice`.

### codex-tui::chatwidget::model_popups - complete_slice (2026-06-12)

- Implemented semantic Python interface for model/reasoning popup construction, model selection event sequences, Plan-mode reasoning scope prompt decisions, and OpenAI base URL warning text.
- Boundary note: actual model catalog refresh errors, ratatui renderable headers, bottom-pane popup display, and app-event channel closure dispatch remain outside this slice; Python actions are represented as `ModelPopupEvent` values.
- Status: `complete_slice`.

### codex-tui::chatwidget::review_popups - complete_slice (2026-06-12)

- Implemented semantic Python interface for review preset, branch, commit, and custom prompt popup construction.
- Boundary note: git branch/commit discovery, real `CustomPromptView`, bottom-pane display, and event-channel closure dispatch are modeled as pure input/output data and remain runtime work outside this slice.
- Status: `complete_slice`.

### codex-tui::public_widgets - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/public_widgets/mod.rs`
- Python module: `pycodex.tui.public_widgets`
- Python parity tests: `tests/test_tui_public_widgets.py`
- Covered behavior: package facade declares the single `composer_input` submodule, matching Rust `pub(crate) mod composer_input;`.
- Status: `complete`; this records only the parent facade boundary and does not mark `public_widgets::composer_input` behavior complete.
- Tests not run per instruction.

### codex-tui::exec_cell - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/exec_cell/mod.rs`
- Python module: `pycodex.tui.exec_cell`
- Python parity tests: `tests/test_tui_exec_cell_facade.py`
- Covered behavior: parent package facade mirrors Rust `mod model; mod render;` plus the selected `pub(crate) use` exports.
- Status: `complete`; child modules remain tracked independently.
- Tests not run per instruction.

### codex-tui::onboarding - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/onboarding/mod.rs`
- Python module: `pycodex.tui.onboarding`
- Python parity tests: `tests/test_tui_onboarding_facade.py`
- Covered behavior: parent package facade mirrors Rust child-module declarations and auth hyperlink-helper re-exports.
- Status: `complete`; child modules remain tracked independently.
- Tests not run per instruction.

### codex-tui::status - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/status/mod.rs`
- Python module: `pycodex.tui.status`
- Python parity tests: `tests/test_tui_status_facade.py`
- Covered behavior: parent package facade mirrors Rust status submodule declarations and selected re-exports.
- Status: `complete`; child modules remain tracked independently.
- Tests not run per instruction.

### codex-tui::bottom_pane::mentions_v2 - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/bottom_pane/mentions_v2/mod.rs`
- Python module: `pycodex.tui.bottom_pane.mentions_v2`
- Python parity tests: `tests/test_tui_bottom_pane_mentions_v2_facade.py`
- Covered behavior: parent package facade mirrors Rust child-module declarations and selected re-exports.
- Status: `complete`; child modules remain tracked independently.
- Tests not run per instruction.

### codex-tui::tui - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/tui.rs`
- Python module: `pycodex.tui.tui`
- Python parity tests: `tests/test_tui_tui_slice.py`
- Covered behavior: notification-condition focus predicates and alternate-scroll ANSI command semantics.
- Status: `complete_slice`; terminal runtime and ratatui/crossterm side effects remain explicit boundaries.
- Tests not run per instruction.

### codex-tui::status::tests - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/status/tests.rs`
- Python module: `pycodex.tui.status.tests`
- Python parity tests: `tests/test_tui_status_tests_slice.py`
- Covered behavior: low-level Rust test helper functions for workspace-write profile shape, cwd mutation, line rendering, directory sanitization, reset timestamp calculation, and empty account-display helper.
- Status: `complete_slice`; large async snapshot tests remain explicit parity debt.
- Tests not run per instruction.

### codex-tui::notifications - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/notifications/mod.rs`
- Python module: `pycodex.tui.notifications`
- Python parity tests: `tests/test_tui_notifications.py`
- Covered behavior: explicit OSC9/BEL backend selection, supported/unsupported terminal OSC9 allow-list, Auto backend detection via semantic `TerminalInfo`, notification dispatch to OSC9/BEL backends, and tmux passthrough propagation for OSC9.
- Boundary note: Rust `terminal_info()` global terminal probing is represented by injected semantic terminal data; concrete platform terminal detection remains a dependency boundary.
- Status: `complete_slice`.
- Tests not run per instruction.

### codex-tui::ui_consts - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/ui_consts.rs`
- Python module: `pycodex.tui.ui_consts`
- Python parity tests: `tests/test_tui_ui_consts.py`
- Covered behavior: `LIVE_PREFIX_COLS = 2` and `FOOTER_INDENT_COLS = LIVE_PREFIX_COLS`, preserving the Rust layout/alignment constants for live-cell gutters, status alignment, and footer indentation.
- Status: `complete`.
- Tests not run per instruction.

### codex-tui::terminal_probe - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/terminal_probe.rs`
- Python module: `pycodex.tui.terminal_probe`
- Python parity tests: `tests/test_tui_terminal_probe.py`
- Covered behavior: CSI cursor-position parsing, OSC 10/11 color parsing with BEL/ST terminators, two/four digit RGB/RGBA component handling, default foreground/background pair extraction, keyboard enhancement/PDA fallback state classification, batched startup-probe parsing, completion predicate, and partial-keyboard finish promotion.
- Boundary note: Unix TTY duplication, nonblocking poll/read, real startup/default-color terminal I/O, and platform descriptor restoration remain explicit platform boundaries; Python raises `NotImplementedError` instead of simulating a terminal.
- Status: `complete_slice` with real TTY I/O boundary blocked.
- Tests not run per instruction.

### codex-tui markdown_render/table_key_value.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/markdown_render/table_key_value.rs`
- Python module: `pycodex/tui/markdown_render/table_key_value.py`
- Interface status: `complete_slice`
- Notes: replaced the generated `interface scaffold` with concrete semantic constants and functions for key/value record rendering. The module now exposes usable record-render decisions, aligned/stacked field rendering, cell wrapping, display-width helpers, and hyperlink offset preservation. Parent markdown rendering remains separate follow-up scope.

### codex-tui pets/image_protocol.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/image_protocol.rs`
- Python module: `pycodex/tui/pets/image_protocol.py`
- Interface status: `complete_slice`
- Notes: replaced the generated `interface scaffold` with concrete semantic protocol enums/support objects, terminal-support detection helpers, Kitty graphics command generation, tmux passthrough wrapping, and Rust-test-aligned helper constructors. `sixel_frame` is intentionally left as an explicit `not_ported` image-processing boundary because faithful resize/PNG-to-Sixel generation would require non-stdlib behavior and `pets/sixel.rs` is a separate module.

### codex-tui pets/sixel.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/sixel.rs`
- Python module: `pycodex/tui/pets/sixel.py`
- Interface status: `complete`
- Notes: replaced the generated `interface scaffold` with the full minimal Sixel encoder behavior: constants, RGBA validation, RGB332 palette construction, palette definitions, active-color band scanning, sixel byte generation, run-length compression, pixel offset/count helpers, and Rust-test-aligned transparent pixel handling.

### codex-tui pets/asset_pack.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/asset_pack.rs`
- Python module: `pycodex/tui/pets/asset_pack.py`
- Interface status: `complete_slice`
- Notes: replaced the generated `interface scaffold` with concrete cache path, CDN URL, HTTPS validation, bounded download, staging/install, and injectable ensure/test-pack control-flow behavior. Real WebP spritesheet dimension validation is intentionally explicit `not_ported`, and `pets/catalog.rs` remains a separate module boundary.

### codex-tui pets/catalog.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/catalog.rs`
- Python module: `pycodex/tui/pets/catalog.py`
- Interface status: `complete`
- Notes: replaced the generated `interface scaffold` with the full built-in pet catalog constants, `BuiltinPet` value model, catalog tuple, id lookup helper, and deterministic test spritesheet writer. Real WebP encoding is not owned by this catalog module.

### codex-tui resume_picker.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/resume_picker.rs`
- Python module: `pycodex/tui/resume_picker/__init__.py`
- Interface status: `complete_slice`
- Notes: added concrete semantic implementations for the low-dependency resume-picker constants, target/action/filter/density/control models, cwd/provider filter helpers, pasted-query normalization, sort labels, and list viewport width. The large interactive picker state machine, app-server loader, transcript overlay, and ratatui rendering remain explicit `not_ported` runtime boundaries.

### codex-tui ide_context/ipc.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/ide_context/ipc.rs`
- Python module: `pycodex/tui/ide_context/ipc.py`
- Interface status: `complete_slice`
- Notes: replaced the generated `interface scaffold` with concrete semantic IPC protocol behavior: error hinting, request construction, length-prefixed JSON frame IO, unsupported request responses, client discovery responses, response matching, result validation, and IDE context extraction. Real Unix/Windows IPC transport and socket ownership/deadline polling stay as explicit `not_ported` platform boundaries.

### codex-tui ide_context/windows_pipe.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/ide_context/windows_pipe.rs`
- Python module: `pycodex/tui/ide_context/windows_pipe.py`
- Interface status: `complete_slice`
- Notes: replaced the generated `interface scaffold` with portable semantic constants, stream/deadline wrappers, empty IO behavior, handle wrapper, timeout helper, and validation/error boundaries. Native Win32 named-pipe and SID ownership APIs remain explicit `not_ported` platform boundaries.

### codex-tui app/app_server_events.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/app/app_server_events.rs`
- Python module: `pycodex/tui/app/app_server_events.py`
- Interface status: `complete_slice`
- Notes: replaced the empty interface scaffold with semantic app-server event/notification/request routing planners and pending-request test doubles. Full async `App` mutation, app-server rejection transport, enqueue operations, config reload, and chat-widget rendering remain explicit runtime boundaries.

### codex-tui chatwidget/windows_sandbox_prompts.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/chatwidget/windows_sandbox_prompts.rs`
- Python module: `pycodex/tui/chatwidget/windows_sandbox_prompts.py`
- Interface status: `complete_slice`
- Implemented semantic prompt/status models for world-writable warnings, Windows sandbox enable prompts, fallback prompts, optional enable gating, and setup/clear status transitions.
- Runtime boundary: Windows sandbox scanning/setup, telemetry transport, AppEvent channels, and concrete TUI popup rendering are intentionally represented as action plans rather than executed in this module.

### codex-tui pets/model.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/model.rs`
- Python module: `pycodex/tui/pets/model.py`
- Interface status: `complete_slice`
- Implemented pet manifest/model semantics: selectors, default animations, manifest parsing/defaulting, frame and animation validation, cache key generation, and safe manifest-relative spritesheet path resolution.
- Runtime/dependency boundary: real WebP dimension decoding remains explicit `not_ported`; the Python slice validates the catalog test-spritesheet marker used by local parity tests.

### codex-tui pets/frames.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/frames.rs`
- Python module: `pycodex/tui/pets/frames.py`
- Interface status: `complete_slice`
- Implemented frame-cache filesystem semantics: expected frame paths, stale frame cleanup, cache reuse, and crop geometry planning.
- Runtime/dependency boundary: real spritesheet decoding and PNG writing remain an explicit injected-slicer boundary instead of a silent fallback.

### codex-tui pets/ambient.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/ambient.rs`
- Python module: `pycodex/tui/pets/ambient.py`
- Interface status: `complete_slice`
- Implemented ambient pet semantic model: notification vocabulary/lifetimes, animation tick timing, reduced-motion frame selection, image sizing, draw-request layout, preview centering, and protocol/layout suppression.
- Runtime boundary: pet/frame-cache loading, terminal image protocol auto-detection, frame requester integration, and actual terminal rendering remain explicit boundaries.

### codex-tui pets/preview.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/preview.rs`
- Python module: `pycodex/tui/pets/preview.py`
- Interface status: `complete`
- Implemented the full preview-state contract: shared state object, renderable wrapper, status transitions, last-area tracking, semantic render plans, desired height, and centered text area calculation.
- Framework adaptation: ratatui buffer/paragraph output is represented as a semantic render plan.

### codex-tui pets/picker.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/picker.rs`
- Python module: `pycodex/tui/pets/picker.py`
- Interface status: `complete_slice`
- Implemented `/pets` picker semantic params: entry discovery, sorting, disabled-first ordering, current/preferred selection, item actions, preview selection-change events, and side-content metadata.
- Framework adaptation: bottom-pane selection view structs and AppEvent callbacks are represented as semantic params/action plans.

### codex-tui pets/mod.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/mod.rs`
- Python module: `pycodex/tui/pets/__init__.py`
- Interface status: `complete_slice`
- Implemented the pets facade behavior: public constants/re-exports, built-in asset ensure dispatch, image render state, Kitty/Sixel clear behavior, semantic ANSI output ordering, and terminal-vs-asset error classification.
- Runtime/dependency boundary: real terminal writer behavior is modeled semantically and Sixel frame generation remains an explicit injected/dependency boundary.

### codex-tui ide_context/prompt.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/ide_context/prompt.rs`
- Python module: `pycodex/tui/ide_context/prompt.py`
- Interface status: `complete`
- Implemented the full prompt-rendering contract: context formatting, request delimiter handling, text input prefixing, text-element byte-range shifting, truncation/omission limits, and request extraction with offset.
- Dependency adaptation: app-server protocol inputs are represented as semantic dataclasses and duck-typed object/dict access.

### codex-tui onboarding/welcome.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/onboarding/welcome.rs`
- Python module: `pycodex/tui/onboarding/welcome.py`
- Interface status: `complete_slice`
- Implemented welcome-step semantics: animation layout breakpoints, render plan lines, animation suppression/scheduling, Ctrl+. variant rotation, layout-area override, and login-dependent step state.
- Framework adaptation: ratatui buffer rendering and real `AsciiAnimation` are represented by semantic render plans and a deterministic animation model.

### codex-tui onboarding/trust_directory.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/onboarding/trust_directory.rs`
- Python module: `pycodex/tui/onboarding/trust_directory.py`
- Interface status: `complete_slice`
- Implemented trust-directory onboarding state: trust/quit selections, key routing, release-event guard, should-quit flag, step-state behavior, Git-root warning, error rendering, option rows, and Windows sandbox hint footer.
- Framework adaptation: ratatui rendering is represented by a semantic `TrustDirectoryRenderPlan`.

### codex-tui onboarding/onboarding_screen.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/onboarding/onboarding_screen.rs`
- Python module: `pycodex/tui/onboarding/onboarding_screen.py`
- Interface status: `complete_slice`
- Implemented onboarding flow orchestration semantics: step visibility ordering, key/paste routing, quit safety for API-key entry, auth cancellation, trust quit propagation, animation suppression aggregation, and trust persistence failure handling.
- Runtime boundary: async TUI/app-server loop, real construction from Config/Tui, git-root resolution, and project trust persistence are explicit/injected boundaries.

### codex-tui status_indicator_widget.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/status_indicator_widget.rs`
- Python module: `pycodex/tui/status_indicator_widget.py`
- Interface status: `complete_slice`
- Implemented live status-row semantics: elapsed formatting, header/details/inline-message updates, interrupt forwarding, timer pause/resume behavior, desired-height/details wrapping, render-line clipping, interrupt hint variants, empty-area no-op, and animation frame scheduling.
- Runtime/render boundary: concrete ratatui buffer mutation, snapshot-perfect spinner/shimmer styling, and terminal cell rendering remain represented by Python semantic `Line`/`Span` values.

### codex-tui terminal_title.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/terminal_title.rs`
- Python module: `pycodex/tui/terminal_title.py`
- Interface status: `complete`
- Implemented terminal-title helper semantics: title sanitization, disallowed control/invisible character filtering, whitespace normalization, 240-character bound, OSC 0 BEL encoding, set-title result states, no-terminal no-op, no-visible-content no-op, and explicit clear-title output.
- Runtime adaptation: Python accepts injectable text streams as the semantic equivalent of Rust stdout/crossterm output, so no remaining module-owned behavior is blocked.

### codex-tui update_action.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/update_action.rs`
- Python module: `pycodex/tui/update_action.py`
- Python parity tests: `tests/test_tui_update_action.py`
- Status: `complete_slice`
- Covered behavior:
  - `UpdateAction` variants for npm, bun, brew, standalone Unix, and standalone Windows update paths.
  - `InstallMethod` / `StandalonePlatform` semantic install-context mapping, including `Other -> None`.
  - Full `command_args` table for package-manager and standalone installer commands.
  - `command_str` shell-join semantics using Python `shlex.join` as the semantic equivalent of Rust `shlex::try_join`.
  - Explicit `get_update_action` injection boundary for install-context detection.
- Boundary note: Rust release builds call `InstallContext::current()` from `codex_install_context`; Python intentionally requires an injected context/current-context callable until that dependency crate behavior is ported, so no install source is fabricated silently.

### codex-tui update_versions.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/update_versions.rs`
- Python module: `pycodex/tui/update_versions.py`
- Interface status: `complete`
- Implemented complete version-helper behavior: latest-tag prefix extraction, plain semver tuple parsing, malformed/prerelease rejection via `None`, source-build sentinel detection, whitespace trimming, Rust-like tuple comparison, and unsigned/u64 parse guardrails.
- Runtime boundary: none; this is a pure helper module.

### codex-tui update_prompt.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/update_prompt.rs`
- Python module: `pycodex/tui/update_prompt.py`
- Interface status: `complete_slice`
- Implemented update-prompt state-machine semantics: outcome/selection variants, cyclic navigation, release-key filtering, Ctrl-C/Ctrl-D/Esc skip, numeric selection, Enter confirmation, frame scheduling, semantic modal rows, run-update terminal clear, don't-remind dismissal, and dependency-absent continue behavior.
- 2026-06-13 update: added ratatui-bridge `Rect`/`Buffer`/`Clear`/`Line`/`Span` rendering for the prompt body while keeping the semantic snapshot helper.
- Runtime/render boundary: release-only TUI draw/event loop, terminal hyperlink OSC8 marking, and real update/install-context lookups remain represented by injected providers and semantic lines.

### codex-tui wrapping.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/wrapping.rs`
- Python module: `pycodex/tui/wrapping.py`
- Interface status: `complete_slice`
- Implemented semantic wrapping behavior: line/span flattening, styled span slicing, indent progression, word wrapping, URL-like heuristics, URL-preserving adaptive wrapping, mixed URL/prose wrapping, range trim/sentinel behavior, and semantic source-range reconstruction.
- Blocked sub-boundary: pointer/owned-line fidelity for Rust `textwrap::Cow` and penalty-character reconstruction remains explicit parity debt; user-visible wrapping and URL-preservation behavior are available through Python semantic models.

### codex-tui markdown.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/markdown.rs`
- Python module: `pycodex/tui/markdown.py`
- Interface status: `complete_slice`
- Implemented module-owned fence normalization behavior: markdown fence parsing, close-fence matching, blockquote-aware table detection, table-fence unwrapping, non-table/non-markdown passthrough, and unclosed fence restoration.
- Dependency boundary: concrete markdown rendering, `HyperlinkLine` generation, pulldown-cmark behavior, and ratatui line styling remain owned by `markdown_render.rs`; this module delegates rather than silently falling back.

### codex-tui resume_picker/transcript.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/resume_picker/transcript.rs`
- Python module: `pycodex/tui/resume_picker/transcript.py`
- Interface status: `complete_slice`
- Implemented transcript conversion semantics: app-server thread read, raw-reasoning visibility, user/agent/plan/reasoning item mapping, git-action visible markdown stripping, empty transcript fallback, and fallback rows for command/tool/file/image/review/context items.
- Dependency boundary: concrete `HistoryCell` implementations, ratatui styling, `Arc<dyn HistoryCell>`, and full display-line rendering remain represented by semantic `TranscriptCell` DTOs.

### codex-tui keymap_setup/debug.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/keymap_setup/debug.rs`
- Python module: `pycodex/tui/keymap_setup/debug.py`
- Interface status: `complete_slice`
- Implemented keymap debug inspector semantics: missing-key hints, delayed hint timing, key report generation, raw-event/modifier formatting, assigned-action row formatting, release-key ignore, Ctrl-C completion, Esc inspection preference, desired-height/render lines, and next-frame delay.
- Dependency boundary: full runtime keymap matching, key spec serialization, bottom-pane trait integration, and ratatui rendering are represented by semantic lines and injected/duck-typed action matches.


### codex-tui keymap_setup/actions.rs - complete_slice (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/keymap_setup/actions.rs`.
- Python target: `pycodex/tui/keymap_setup/actions.py`.
- Interface status: `complete_slice`.
- Exposed Python API: `KeymapActionDescriptor`, `KeymapActionFeature`, `KeymapActionFilter`, `KeymapDebugBindingSource`, `KeymapDebugActionMatch`, `BindingSlot`, `KEYMAP_ACTIONS`, `action`, `gated_action`, `action_label`, `binding_slot`, `global_fallback_slot`, `bindings_for_action`, `format_binding_summary`, `debug_binding_source`, and `matching_actions_for_key_event`.
- Notes: framework-specific Rust keymap/event storage is represented by semantic Python mappings/objects; this keeps the codex-tui module contract testable without claiming completion of neighboring keymap setup modules.


### codex-tui terminal_hyperlinks.rs - complete_slice update (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/terminal_hyperlinks.rs`.
- Python target: `pycodex/tui/terminal_hyperlinks.py`.
- Interface status: `complete_slice`.
- Exposed update: `adaptive_wrap_hyperlink_lines` is now implemented as a semantic wrapper over Python `wrapping.adaptive_wrap_line` plus existing hyperlink range remapping.
- Notes: this removes the previous explicit `not_ported` helper for the module-owned adaptive wrapping path while preserving renderer/framework boundaries for ratatui buffer fidelity.


### codex-tui history_cell/mod.rs - complete_slice (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/history_cell/mod.rs`.
- Python target: `pycodex/tui/history_cell/__init__.py`.
- Interface status: `complete_slice`.
- Exposed Python API: `RAW_DIFF_SUMMARY_WIDTH`, `RAW_TOOL_OUTPUT_WIDTH`, `HistoryRenderMode`, `HistoryCell`, `raw_lines_from_source`, `plain_lines`, rich/raw display helper functions, transcript helper functions, stream/animation defaults, and child-module facade re-exports.
- Notes: module-owned default trait behavior is semantic and testable; concrete child cells and ratatui buffer rendering continue to be tracked as separate behavior/runtime boundaries.


### codex-tui bottom_pane/command_popup.rs - complete_slice update (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/bottom_pane/command_popup.rs`.
- Python target: `pycodex/tui/bottom_pane/command_popup.py`.
- Interface status: `complete_slice`.
- Exposed Python API: `CommandItem`, `CommandPopupFlags`, `CommandPopup`, `from_`, `render_ref`, `ALIAS_COMMANDS`, and `COMMAND_COLUMN_WIDTH`.
- Notes: the generated test-name scaffolds were removed because they are not Rust module APIs; module-owned filtering/selection/row behavior is represented by the concrete Python implementation and parity tests. Exact ratatui buffer rendering remains a renderer boundary.


### codex-tui chatwidget/mcp_startup.rs - complete_slice (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/chatwidget/mcp_startup.rs`.
- Python target: `pycodex/tui/chatwidget/mcp_startup.py`.
- Interface status: `complete_slice`.
- Exposed Python API: `MCP_STARTUP_SINGLE_HEADER_PREFIX`, `MCP_STARTUP_MULTI_HEADER_PREFIX`, `McpStartupStatusKind`, `McpStartupStatus`, `McpServerStatusUpdatedNotification`, and `McpStartupModel`.
- Notes: replaces the generated interface scaffold with a concrete semantic state machine for module-owned startup behavior; concrete `ChatWidget` mutation and transport remain explicit neighboring boundaries.


### codex-tui chatwidget/pets.rs - complete_slice (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/chatwidget/pets.rs`.
- Python target: `pycodex/tui/chatwidget/pets.py`.
- Interface status: `complete_slice`.
- Exposed Python API: `PetsConfig`, `BottomPanePetsModel`, `ChatWidgetPetsModel`, `SelectionViewParamsPlan`, `PET_SELECTION_LOADING_VIEW_ID`, `AMBIENT_PET_WRAP_GAP_COLUMNS`, `load_ambient_pet`, `start_configured_pet_load_if_needed`, and `spawn_pet_load`.
- Notes: replaces the generated interface scaffold with concrete semantic pet state behavior; real asset loading, async execution, terminal image drawing, and full widget/bottom-pane runtime integration remain explicit dependency/runtime boundaries.


### codex-tui chatwidget/slash_dispatch.rs - complete_slice (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/chatwidget/slash_dispatch.rs`.
- Python target: `pycodex/tui/chatwidget/slash_dispatch.py`.
- Interface status: `complete_slice`.
- Exposed Python API: constants, `SlashCommandDispatchSource`, `QueueDrain`, `ByteRange`, `TextElement`, `PreparedSlashCommandArgs`, `PreparedUserMessage`, `GuardResult`, side/review guard helpers, queue-drain helper, argument remapping, prepared-message shaping, and pure inline-argument classifiers.
- Notes: replaces generated interface scaffold with a focused semantic dispatch helper slice; concrete widget command side effects and app runtime integration are intentionally not claimed complete.


### codex-tui chatwidget/plan_implementation.rs - complete (2026-06-12)
- Rust source: `codex/codex-rs/tui/src/chatwidget/plan_implementation.rs`.
- Python target: `pycodex/tui/chatwidget/plan_implementation.py`.
- Interface status: `complete`.
- Exposed Python API: plan implementation constants, semantic selection/action dataclasses, `standard_popup_hint_line`, and `selection_view_params`.
- Notes: replaces generated interface scaffold with full module-owned semantic behavior; Rust app-event closures are represented as serializable action plans.

### codex-tui chatwidget/realtime.rs - complete_slice (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/realtime.rs`
- Python module: `pycodex/tui/chatwidget/realtime.py`
- Interface status: `complete_slice`
- Notes: replaced the generated interface scaffold with a semantic realtime voice state machine covering conversation phases, websocket/WebRTC transport selection, footer hints, close/reset/fail transitions, realtime notifications, WebRTC offer/SDP/event handling, meter deletion guards, and task-hook plans.
- Runtime boundary: real microphone/audio playback, WebRTC networking, recording-meter background work, AppCommand/AppEvent transport, and ratatui rendering remain explicit dependency/runtime boundaries.

### codex-tui chatwidget/input_restore.rs - complete_slice (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/input_restore.rs`
- Python module: `pycodex/tui/chatwidget/input_restore.py`
- Interface status: `complete_slice`
- Notes: replaced the generated interface scaffold with a semantic input-restore model for initial input submission, rejected steer recovery, queued-message pop/merge behavior, interrupted-turn restore or immediate steer submission, composer restore, thread input state capture/restore, default history-record padding, and pending steer compare-key reconstruction.
- Runtime boundary: full `ChatWidget` mutation, bottom-pane composer internals, collaboration-mode concrete types, history-cell display, and exact Rust text-element/image-placeholder remapping remain explicit neighboring/runtime boundaries.

### codex-tui chatwidget/plugins.rs - complete_slice (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/plugins.rs`
- Python module: `pycodex/tui/chatwidget/plugins.py`
- Interface status: `complete_slice`
- Notes: replaced the generated interface scaffold with semantic plugin helper behavior for constants, plugin/marketplace DTOs, cache state, loading header shape, tab IDs, duplicate-label disambiguation, display-name/description fallback, status labels, selection-entry collection/sorting, detail summaries, hint/header text, and user-configured marketplace checks.
- Runtime boundary: full plugin marketplace UI orchestration, bottom-pane selection actions, app-server plugin operations, custom prompt callbacks, ratatui rendering, hyperlink marking, and concrete config-layer lookup remain explicit boundaries.

### codex-tui chatwidget/session_flow.rs - complete_slice (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/session_flow.rs`
- Python module: `pycodex/tui/chatwidget/session_flow.py`
- Interface status: `complete_slice`
- Notes: replaced the generated interface scaffold with semantic session orchestration for normal/quiet/side session handling, thread metadata, cwd/workspace/permission/service-tier state, collaboration-mode updates, normal header planning, quiet/side header clearing, initial-message handling, forked-thread events, connector prefetch gating, skill reset/reload, redraw suppression, and thread-name updates.
- Runtime boundary: full `ChatWidget`, permission constraint internals, history-cell rendering, transcript active-cell mutation, model catalog behavior, status surfaces, connector fetches, and app-event transport remain explicit boundaries.

### codex-tui chatwidget/tool_lifecycle.rs - complete_slice (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/tool_lifecycle.rs`
- Python module: `pycodex/tui/chatwidget/tool_lifecycle.py`
- Interface status: `complete_slice`
- Notes: replaced the generated interface scaffold with semantic lifecycle behavior for patch/image/MCP/web-search/collab events, active-cell transitions, MCP completion result shaping, work-activity flags, collab spawn request caching, defer queue routing, and queued item dispatch.
- Runtime boundary: concrete history cells, rendering, command lifecycle handlers, deferred queue orchestration, multi-agent metadata, app-event transport, and transcript downcasting remain explicit boundaries.

### codex-tui chatwidget/tool_requests.rs - complete_slice (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/tool_requests.rs`
- Python module: `pycodex/tui/chatwidget/tool_requests.py`
- Interface status: `complete_slice`
- Notes: replaced the generated interface scaffold with semantic request routing for exec/apply-patch approvals, guardian assessment footer/history decisions, elicitation routes, user-input prompts, permission requests, deferred queue handling, notifications, ambient waiting state, flushes, and redraws.
- Runtime boundary: concrete bottom-pane views, app-server request constructors, history-cell rendering, feature gating, pet rendering, and app-event transport remain explicit boundaries.

### codex-tui chatwidget/input_flow.rs - complete_slice (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/input_flow.rs`
- Python module: `pycodex/tui/chatwidget/input_flow.py`
- Interface status: `complete_slice`
- Notes: replaced the generated interface scaffold with semantic input-flow behavior for submitted/queued/command input results, immediate submit versus queue decisions, user-shell running guards, queue drain semantics, autosend suppression, pending-input preview updates, plan-mode effort overrides, collaboration-mode switch rejection, and queued-message snapshots.
- Runtime boundary: full bottom-pane composer integration, slash/shell command runtimes, command lifecycle state, formatted queue previews, collaboration-mode concrete types, and TUI status rendering remain explicit boundaries.

### codex-tui chatwidget/turn_lifecycle.rs - complete (2026-06-13)

- Rust module: `codex/codex-rs/tui/src/chatwidget/turn_lifecycle.rs`
- Python module: `pycodex/tui/chatwidget/turn_lifecycle.py`
- Interface status: `complete`
- Notes: replaced the generated interface scaffold with the complete turn lifecycle state contract: running start/finish/restore, active-turn timestamp, thread reset, prevent-idle-sleep inhibitor recreation, and budget-limited turn ID mark/take semantics.
- Runtime boundary: OS sleep inhibition is represented semantically by `SleepInhibitor`; no ratatui or app runtime behavior is owned by this module.

## 2026-06-13 - chatwidget/replay.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/replay.rs`
- Python module: `pycodex/tui/chatwidget/replay.py`
- Parity tests: `tests/test_tui_chatwidget_replay.py`
- Notes: Ports replay turn/item dispatch semantics into Python semantic DTOs and widget callbacks: in-progress turn start handling, terminal turn completion notification, replay item source wrapping, status-sensitive command/file/MCP routing, reasoning summary/raw replay behavior, web/image/review/context/collab dispatch, no-op variants, unknown variant errors, and thread-snapshot redraw behavior. Full live `ChatWidget` integration remains owned by surrounding chatwidget modules.

## 2026-06-13 - chatwidget/settings.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/settings.rs`
- Python module: `pycodex/tui/chatwidget/settings.py`
- Parity tests: `tests/test_tui_chatwidget_settings.py`
- Notes: Ports a semantic settings slice for feature toggles, realtime audio device state, model/reasoning/collaboration-mode masking, model display, image support messaging, Plan-mode nudge policy, model-dependent refresh hooks, and visible collaboration labels. Full thread-settings application, permission-profile constraint handling, Windows sandbox UI, account/connectors state, app-event submission, goal time-tick integration, and model catalog integration remain surrounding chatwidget/app integration debt.

## 2026-06-13 - chatwidget/permission_popups.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/permission_popups.rs`
- Python module: `pycodex/tui/chatwidget/permission_popups.py`
- Parity tests: `tests/test_tui_chatwidget_permission_popups.py`
- Notes: Ports semantic permission popup DTOs and actions: built-in presets, permissions popup item construction, guardian auto-review item, full-access confirmation gating and confirmation choices, permission-profile selection action, preset matching for full/read-only/auto modes, auto-review denials popup, and recent denial approval event semantics. Rust ratatui renderables, boxed channel closures, Windows sandbox prompts, world-writable warnings, and real app-event transport remain surrounding integration debt.

## 2026-06-13 - chatwidget/protocol.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/protocol.rs`
- Python module: `pycodex/tui/chatwidget/protocol.py`
- Parity tests: `tests/test_tui_chatwidget_protocol.py`
- Notes: Ports semantic app-server notification dispatch, side-conversation MCP suppression, replay-aware retry/status restoration, turn started/completed handling, item started/completed routing, reasoning raw delta gating, retry/non-retry error paths, realtime replay suppression, guardian review routing, and documented no-op notification variants. Concrete Rust protocol enum decoding, token usage conversion, ThreadId parsing, file-change display conversion, and full app-server integration remain surrounding protocol/app debt.

## 2026-06-13 - chatwidget/protocol_requests.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/protocol_requests.rs`
- Python module: `pycodex/tui/chatwidget/protocol_requests.py`
- Parity tests: `tests/test_tui_chatwidget_protocol_requests.py`
- Notes: Ports semantic server-request dispatch for command/file approval, MCP elicitation, permissions approval, tool user input, live-only TUI stub errors, skills-list response routing, guardian review notification to assessment event conversion, shutdown, turn diff refresh, ignored patch output delta, and deprecation notice side effects. Exact Rust app-server request DTO conversion, guardian action enum conversion, tracing, and real event transport remain surrounding integration debt.

## 2026-06-13 - chatwidget/skills.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/skills.rs`
- Python module: `pycodex/tui/chatwidget/skills.py`
- Parity tests: `tests/test_tui_chatwidget_skills.py`
- Notes: Ports semantic skill/app mention helpers and widget skill flows: skill list/menu insertion, manage-skills toggle state, skill response filtering by cwd, enabled-skill conversion, SKILL.md read annotation, plain and linked tool mention parsing, env-var suppression, skill path normalization, app id extraction, app mentionable filtering, app slug selection with ambiguity/skill-name collision checks, and Rust-covered accessible/enabled app mention behavior. Exact Rust serde scope conversion, connector metadata slug parity for all Unicode cases, ratatui toggle view wiring, and real app-event transport remain integration debt.

## 2026-06-13 - chatwidget/transcript.rs

- Status: complete
- Rust module: `codex/codex-rs/tui/src/chatwidget/transcript.rs`
- Python module: `pycodex/tui/chatwidget/transcript.py`
- Parity tests: `tests/test_tui_chatwidget_transcript.py`
- Notes: Ports the complete local transcript bookkeeping contract: active-cell revision wrapping, visible user turn counting, agent markdown copy history replacement/capping, copy history reset/truncation/rollback eviction flag, and per-turn flag reset behavior. `active_cell` remains opaque because rendering is owned by history-cell modules, matching this module's state-only boundary.

## 2026-06-13 - chatwidget/settings_popups.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/settings_popups.rs`
- Python module: `pycodex/tui/chatwidget/settings_popups.py`
- Parity tests: `tests/test_tui_chatwidget_settings_popups.py`
- Notes: Ports semantic popup construction for theme picker fallback/delegation, personality startup/model-support guards, Friendly/Pragmatic selection actions and labels/descriptions, realtime audio settings/device selection/restart prompts, and experimental feature menu filtering. Rust ratatui renderables, actual theme picker construction, OS audio device enumeration, app-event channel wiring, and concrete ExperimentalFeaturesView integration remain surrounding UI debt.

## 2026-06-13 - chatwidget/input_submission.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/input_submission.rs`
- Python module: `pycodex/tui/chatwidget/input_submission.py`
- Parity tests: `tests/test_tui_chatwidget_input_submission.py`
- Notes: Ports semantic submission behavior for user-message DTO construction, shell command handling and history, queued shell prompt dispatch, pre-session message queueing, empty input rejection, blocked image restore with mention bindings, shell escape policy, user-turn item construction for text/local/remote images and skill/app/plugin mentions, unavailable-model restoration, history mention encoding, pending steer creation during running turns, and transcript separator reset. Exact Rust `AppCommand::user_turn` permission/service-tier/core DTO construction, IDE context details, text-element conversion, and full app-server submission integration remain surrounding debt.

## 2026-06-13 - chatwidget/interaction.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/interaction.rs`
- Python module: `pycodex/tui/chatwidget/interaction.py`
- Parity tests: `tests/test_tui_chatwidget_interaction.py`
- Notes: Ports a semantic interaction slice: attach-image support guard, composer/external-edit/footer/selection helpers, Ctrl+L running-task guard, copy-last-agent markdown success/error/empty/rollback-evicted paths, paste/paste-burst handling, rename allowance guard, Ctrl+C realtime/handled/interruption/double-press quit state machine, Ctrl+D empty-composer double-press quit handling, and active-goal pause event on interrupt. Full key-event routing/keymap matching, OS paste-image backend, real clipboard lease type, prompt rename view construction, and terminal timing integration remain surrounding UI debt.

## 2026-06-13 - chatwidget/constructor.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/constructor.rs`
- Python module: `pycodex/tui/chatwidget/constructor.py`
- Parity tests: `tests/test_tui_chatwidget_constructor.py`
- Notes: Ports semantic construction contract: `new_with_app_event` delegation, model trimming/blank filtering and config writeback, header model/collaboration-mode initialization, placeholder session header active cell, bottom-pane construction params, welcome/current-cwd/prevent-idle-sleep state, and post-construction bottom-pane/widget sync calls. Full Rust `ChatWidget` field inventory, runtime keymap parsing, service-tier resolution, pets startup, terminal info, rate-limit prefetch, Windows sandbox wiring, and real UI component construction remain integration debt.

## 2026-06-13 - chatwidget/rendering.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/rendering.rs`
- Python module: `pycodex/tui/chatwidget/rendering.py`
- Parity tests: `tests/test_tui_chatwidget_rendering.py`
- Notes: Ports semantic render composition: active transcript cell and optional active hook cell wrapping, ambient-pet right reserve, bottom-pane composer reserve with top inset, transcript child-area saturation, scroll-to-bottom overflow behavior, desired-height delegation, cursor position/style delegation, and last-rendered width recording. Rust ratatui `Buffer`, `Paragraph`, `Clear`, and concrete terminal rendering remain UI backend debt.

## 2026-06-13 - chatwidget/tests.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/tests.rs`
- Python module: `pycodex/tui/chatwidget/tests/__init__.py`
- Parity tests: `tests/test_tui_chatwidget_tests_module.py`
- Notes: Ports the test-only aggregation boundary: snapshot directory/path helper, snapshot assertion naming semantics, declared chatwidget test submodule list, and explicitly re-exported helper names. This module contains no production ChatWidget behavior; individual Rust test submodules remain evidence for their owning production modules rather than separate production implementation targets.

## 2026-06-13 - app/tests.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/app/tests.rs`
- Python module: `pycodex/tui/app/tests/__init__.py`
- Parity tests: `tests/test_tui_app_tests_module.py`
- Notes: Replaced the generated interface scaffold with the test-only aggregation boundary: declared child test modules, app snapshot path/assertion semantics, absolute path helper, line-flattening helper, lightweight helper name inventory, drop-notification semantic helper, and explicit not-ported boundaries for heavyweight async App/AppServer fixtures. Production app behavior remains owned by the corresponding app modules and Rust test cases remain parity evidence for those owners.

## 2026-06-13 - chatwidget/notifications.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/notifications.rs`
- Python module: `pycodex/tui/chatwidget/notifications.py`
- Parity tests: `tests/test_tui_chatwidget_notifications.py`
- Notes: Records existing semantic implementation for desktop notification coalescing: notification variants/display text, type-name filtering, priority replacement, agent-turn preview normalization, user-input request summaries, and pending notification posting. Concrete desktop/TUI notification backend remains outside this module slice.

## 2026-06-13 - chatwidget/service_tiers.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/service_tiers.rs`
- Python module: `pycodex/tui/chatwidget/service_tiers.py`
- Parity tests: `tests/test_tui_chatwidget_service_tiers.py`
- Notes: Records existing semantic implementation for service-tier state: current/configured/effective service tier, fast-mode gating, model service-tier command extraction, toggle-to-default behavior, emitted selection events, fast status visibility, and model-dependent refresh accounting. Full ChatWidget/AppEvent transport and model catalog runtime remain surrounding boundaries.

## 2026-06-13 - chatwidget/review_popups.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/review_popups.rs`
- Python module: `pycodex/tui/chatwidget/review_popups.py`
- Parity tests: `tests/test_tui_chatwidget_review_popups.py`
- Notes: Records existing semantic implementation for review popup construction: preset menu, base-branch picker, commit picker, custom prompt metadata, trimmed custom-review action creation, search values, and selection action payloads. Async git branch/commit discovery and concrete bottom-pane rendering remain dependency/runtime boundaries.

## 2026-06-13 - chatwidget/model_popups.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/model_popups.rs`
- Python module: `pycodex/tui/chatwidget/model_popups.py`
- Parity tests: `tests/test_tui_chatwidget_model_popups.py`
- Notes: Records existing semantic implementation for model/reasoning popup behavior: visible preset filtering, auto-model ordering, all-models fallback, model menu warning, reasoning effort labels/choices/defaults/warnings, Plan-mode scope prompt gating/actions, and persistence event shaping. Full ChatWidget mutation, ratatui renderables, model catalog fetching, and app-event transport remain surrounding boundaries.

## 2026-06-13 - chatwidget/streaming.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/chatwidget/streaming.rs`
- Python module: `pycodex/tui/chatwidget/streaming.py`
- Parity tests: `tests/test_tui_chatwidget_streaming.py`
- Notes: Records existing semantic implementation for streaming state helpers: bold reasoning header extraction, reasoning status restore, stream-idle status restoration gate, reasoning delta/final buffering, stream-error status updates, agent-message completion restore flags, and active stream-tail predicates/clearing. Commit animation, concrete stream controllers, history cells, transcript mutation, and app-event integration remain runtime boundaries.

## 2026-06-13 - history_cell/tests.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/history_cell/tests.rs`
- Python module: `pycodex/tui/history_cell/tests.py`
- Parity tests: `tests/test_tui_history_cell_tests_module.py`
- Notes: Replaced generated scaffold with the test-support boundary owned by this Rust test module: small PNG fixture, temp cwd/config helper, MCP stdio/streamable-http config builders, TOML-like string map conversion, line/transcript flattening, unstyled-line assertion, MCP content block builders, and inventories documenting production rendering tests as evidence for their owning history_cell modules. Full snapshot/rendering assertions remain child-module behavior, not this test-support module's production contract.

## 2026-06-13 - status/tests.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/status/tests.rs`
- Python module: `pycodex/tui/status/tests.py`
- Parity tests: `tests/test_tui_status_tests_module.py`
- Notes: Replaced generated scaffold with the test-support boundary owned by this Rust test module: workspace-write permission profile fixture, temp config/cwd workspace-root helper, account-display `None` helper, token usage info fixture, ratatui-like line flattening, directory sanitization, reset timestamp helper, and inventory documenting snapshot tests as evidence for production status modules. Full status-card rendering and permissions text extraction remain production `status` module behavior.

## 2026-06-13 - markdown_render_tests.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/markdown_render_tests.rs`
- Python module: `pycodex/tui/markdown_render_tests.py`
- Parity tests: `tests/test_tui_markdown_render_tests_module.py`
- Notes: Replaced generated scaffold with the test-support boundary owned by this Rust evidence module: `render_markdown_text_for_cwd` delegation with Rust defaults, `plain_lines` flattening for ratatui-like Text/Line/Span shapes, and categorized renderer-test inventory for paragraphs, blockquotes, lists, inline styling, file links, code blocks, and tables. Production markdown rendering remains owned by `markdown_render.rs`.

## 2026-06-13 - keymap_setup/picker.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/keymap_setup/picker.rs`
- Python module: `pycodex/tui/keymap_setup/picker.py`
- Parity tests: `tests/test_tui_keymap_setup_picker.py`
- Notes: Replaced generated scaffold with semantic picker construction: constants, action-row model, context/common/custom/unbound/debug tabs, header/count/hint text, search values, row prefix custom/unbound indicators, selected-action initial index, name-column width, and semantic AppEvent action payloads. Concrete ratatui renderables, bottom-pane view stack, and event-channel transport remain neighboring/runtime boundaries.

## 2026-06-13 - keymap_setup/debug.rs

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/keymap_setup/debug.rs`
- Python module: `pycodex/tui/keymap_setup/debug.py`
- Parity tests: `tests/test_tui_keymap_setup_debug.py`
- Notes: Records existing semantic implementation for the keypress inspector bottom-pane view: missing-key hint delay, initial/delayed lines, keypress report construction, release-event ignoring, detected/config/raw event display, assigned-action matching, Ctrl+C completion, Esc routing preference, next-frame delay, and modifier debug-label ordering. Concrete ratatui rendering, crossterm key types, and bottom-pane view-stack integration remain runtime boundaries.

## 2026-06-13 - TUI framework vendoring architecture note

- Status: complete_slice
- Scope: vendored Textual architecture boundary
- Python modules: `pycodex/vendor`, `pycodex/tui/textual_compat`, `pycodex/tui/ratatui_bridge`
- Notes: Established the architecture boundary for using vendored Textual while preserving Rust ratatui semantics. `pycodex/vendor` records pinned third-party package provenance, `textual_compat` is the sole project-facing Textual import adapter, and `ratatui_bridge` is the Rust `ratatui` semantic mapping layer. No Textual source has been vendored yet and no existing TUI behavior was changed.

## 2026-06-13 - Textual Python 3.7 candidate pin audit

- Status: complete_slice
- Scope: vendored Textual version selection
- Vendor plan: `pycodex/vendor/VENDORING_PLAN.md`
- Notes: Selected `textual==0.43.2` as the candidate portability-first pin because PyPI metadata reports `Requires-Python: >=3.7,<4.0`, while modern Textual releases require Python 3.9+. Recorded candidate runtime dependency pins for Rich, markdown-it-py extras, importlib-metadata, typing-extensions, Pygments, uc-micro-py, and zipp. No third-party source was vendored in this step.

## 2026-06-13 - Textual 0.43.2 wheel metadata audit

- Status: complete_slice
- Scope: vendored Textual candidate metadata audit
- Audit report: `pycodex/vendor/TEXTUAL_0_43_2_AUDIT.md`
- Notes: Downloaded candidate wheels to `.tmp/textual_vendor_audit`, inspected wheel metadata, import roots, license files, runtime dependency metadata, and SHA256 hashes. No third-party source was vendored into the runtime import path and no existing TUI behavior was changed.

## 2026-06-13 - Vendored Textual source import plan

- Status: complete_slice
- Scope: vendored Textual source layout and import boundary
- Import plan: `pycodex/vendor/VENDOR_IMPORT_PLAN.md`
- Notes: Defined the target layout for extracting audited Textual wheels into `pycodex/vendor/_packages`, `_dist_info`, and `licenses`; documented extraction rules, metadata requirements, import policy, path-integrity checks, first `textual_compat` exports, and first `ratatui_bridge` semantic types. No third-party source was extracted in this step and no existing TUI behavior was changed.

## 2026-06-13 - Textual 0.43.2 vendored source extraction

- Status: complete_slice
- Scope: vendored Textual candidate source extraction
- Extraction report: `pycodex/vendor/TEXTUAL_0_43_2_EXTRACTED.md`
- Machine-readable manifest: `pycodex/vendor/VENDORED_PACKAGES.json`
- Notes: Extracted audited wheels into `pycodex/vendor/_packages`, `_dist_info`, and `licenses`. This adds vendored third-party source files but does not wire them into the TUI runtime; project code should still use `pycodex.tui.textual_compat` as the future import boundary. No tests were run.

## 2026-06-13 - Textual vendored import helper and compatibility entrypoint

- Status: complete_slice
- Scope: vendored Textual runtime import boundary
- Helper: `pycodex/vendor/__init__.py`
- Compatibility module: `pycodex/tui/textual_compat/__init__.py`
- Notes: Added centralized vendored import helpers with path-integrity checks and lazy `textual_compat` exports for the first approved Textual/Rich API subset. Existing TUI modules were not migrated to Textual in this step and no tests were run.

## 2026-06-13 - ratatui_bridge minimal semantic API

- Status: complete_slice
- Scope: Rust ratatui semantic bridge infrastructure
- Python modules: `pycodex/tui/ratatui_bridge/{style.py,text.py,layout.py,renderable.py,__init__.py}`
- Parity tests: `tests/test_tui_ratatui_bridge.py`
- Notes: Added the first shared bridge types for `Style`/`Color`/`Modifier`, `Span`/`Line`/`Text`, `Rect`, and a `Renderable` protocol. Rich/Textual conversion is lazy and goes through `pycodex.tui.textual_compat`; existing TUI modules were not migrated in this step and no tests were run.

## 2026-06-13 - ratatui_bridge Buffer/Renderable contract

- Status: complete_slice
- Scope: Rust ratatui semantic bridge infrastructure
- Python modules: `pycodex/tui/ratatui_bridge/{buffer.py,renderable.py,__init__.py}`
- Parity tests: `tests/test_tui_ratatui_bridge.py`
- Notes: Added a shared semantic `Cell`/`Buffer` render target and tightened the bridge `Renderable` protocol to accept that buffer, matching Rust's `render(area, buf)` shape for future module ports. `pycodex/tui/render/renderable.py` already contains a separate module-scoped port of `codex-tui::render::renderable`; unifying that existing model with `ratatui_bridge.Buffer` is intentionally left as a follow-up migration to avoid changing a completed render module in this bridge slice.

## 2026-06-13 - render model unification audit

- Status: complete_slice
- Scope: Rust ratatui semantic bridge / `codex-tui::render::renderable` model boundary
- Audit note: `pycodex/tui/ratatui_bridge/RENDER_MODEL_AUDIT.md`
- Notes: Audited direct reuse of `ratatui_bridge.Rect/Buffer` inside `pycodex/tui/render/renderable.py`. Decision: do not directly replace the existing recording-buffer model yet, because `render.renderable` parity tests verify layout/delegation records while `ratatui_bridge.Buffer` verifies cell-level backend semantics. Recommended next step is adapter-first migration so completed `render::renderable` behavior remains stable while future concrete render modules can target the shared cell buffer.

## 2026-06-13 - render/renderable shared ratatui_bridge model migration

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/render/renderable.rs`
- Python module: `pycodex/tui/render/renderable.py`
- Bridge modules: `pycodex/tui/ratatui_bridge/{layout.py,buffer.py}`
- Notes: Migrated `render.renderable` away from its local recording `Rect`/`Buffer` model to the shared `ratatui_bridge.Rect` and cell-addressable `ratatui_bridge.Buffer`. `TextRenderable` and `ParagraphRenderable` now write text into the shared cell buffer instead of appending recording entries. `ratatui_bridge.Rect` gained `new`, `bottom`, `right`, `intersection`, and `inset` helpers needed by the Rust `render::renderable` layout contract. Tests were updated from recording assertions to buffer plain-line assertions, but were not run in this step.

## 2026-06-13 - local render model replacement scan

- Status: complete_slice
- Scope: local temporary render model replacement
- Python modules: `pycodex/tui/pager_overlay.py`, `pycodex/tui/chatwidget/rendering.py`, `pycodex/tui/ratatui_bridge/RENDER_MODEL_AUDIT.md`
- Notes: Scanned for local temporary render definitions after the `render.renderable` migration. Replaced `pager_overlay.Rect` with shared `ratatui_bridge.Rect`. Replaced `chatwidget.rendering` local `Rect`, `EmptyRenderable`, `FlexRenderable`, and `InsetRenderable` definitions with shared `ratatui_bridge.Rect` plus `render.renderable` primitives. Kept `RenderLog` as module-owned composition evidence rather than a ratatui buffer substitute. Backend/domain models such as `custom_terminal`, `test_backend`, `diff_render` spans/lines, and composer footer/history-search spans/lines were intentionally not mechanically replaced in this slice.

## 2026-06-13 - local temporary render definition rescan

- Status: complete_slice
- Scope: local temporary render definition cleanup verification
- Notes: Re-scanned `pycodex/tui` for local `Rect`, `Buffer`, `Cell`, `Renderable`, `TextRenderable`, `FlexRenderable`, `InsetRenderable`, `Line`, and `Span` definitions after the shared `ratatui_bridge` migration. Replaced additional local `Rect` DTOs in `app/history_ui.py`, `bottom_pane/pending_input_preview.py`, `bottom_pane/pending_thread_approvals.py`, `bottom_pane/selection_popup_common.py`, `bottom_pane/request_user_input/layout.py`, and `tui/job_control.py` with shared `ratatui_bridge.Rect`. Remaining non-bridge `Rect`/`Buffer`/`Cell` definitions are in `custom_terminal.py` and `test_backend.py`, which are backend/test-backend implementations rather than temporary ratatui shims. Remaining `Span`/`Line` definitions are module-owned text/domain models and were intentionally not mechanically replaced in this scan.

## 2026-06-13 - codex-tui used ratatui API ledger

Status: complete_slice

Created `pycodex/tui/ratatui_bridge/RATATUI_USED_API.md` to scope the bridge to ratatui APIs actually referenced by `codex-rs/tui`. The ledger separates covered, partial, missing, semantic-only, and backend/test-only APIs so future bridge work can stay module-driven instead of cloning full ratatui.

## 2026-06-13 - ratatui bridge layout/widget semantic APIs

Status: complete_slice

Filled the next bridge layer for codex-tui-used ratatui APIs: layout dataclasses/enums (`Size`, `Position`, `Offset`, `Margin`, `Alignment`, `Direction`, `Constraint`, `Layout`), buffer helpers (`__getitem__`, `__setitem__`, `set_style`, `fill`), style reset/reversed helpers, and widget semantics (`Widget`, `Clear`, `Paragraph`, `Wrap`, `Block`, `Borders`, `BorderType`). Layout and widgets remain semantic bridge models rather than a full ratatui clone.

## 2026-06-13 - ratatui bridge Rust-call-shape aliases

Status: complete_slice

Extended the bridge with Rust-like call-shape aliases for layout, style, and widget APIs: PascalCase enum aliases, `Constraint.Length`/`Percentage`/`Ratio`/`Min`/`Max`/`Fill`, ratatui-style color constants such as `Color.Cyan` and `Color.LightBlue`, and `WidgetRef`/`StatefulWidgetRef` protocols. Also replaced newly introduced Python 3.10 union syntax with Python 3.7-compatible `typing` forms in the bridge files touched by this slice.

## 2026-06-13 - ratatui bridge backend/test-backend shell

Status: complete_slice

Added a portable backend layer for codex-tui-used ratatui backend APIs: `Backend`, `TestBackend`, `WindowSize`, `Terminal`, and `Frame` with semantic buffer-backed drawing, plus a `CrosstermBackend` placeholder that explicitly raises `NotImplementedError` for runtime-specific terminal side effects. Also added Rust-like constructor aliases for color/style/text APIs while keeping the bridge dependency-light.

## 2026-06-13 - ratatui bridge Textual/Rich adapter

Status: complete_slice

Added `pycodex.tui.ratatui_bridge.textual_adapter` as the narrow handoff layer from semantic ratatui bridge values to vendored Rich/Textual renderables. The adapter converts `Span`, `Line`, `Text`, `Cell`, and `Buffer` to Rich `Text`, provides plain-buffer snapshots, and can render bridge-style objects into a fresh `Buffer` before converting to Rich. This keeps real terminal behavior owned by Textual while preserving ratatui-style semantic rendering in Python.

## 2026-06-13 - ratatui bridge adapter export cleanup

Status: complete_slice

Normalized the Textual/Rich adapter exports and buffer conversion helpers with explicit file rewrites to keep the new adapter surface deterministic and Python 3.7-compatible. `Buffer` now exposes `to_rich_text` and `to_plain_text` convenience methods that delegate to `textual_adapter` without creating terminal side effects.

## 2026-06-13 - ratatui bridge surface completion pass

Status: complete_slice

Completed the next codex-tui-used bridge surface: side-specific `Borders` bitflags, unicode border glyph rendering for `Block`, paragraph scroll support, `WidgetRef`/`StatefulWidgetRef` adapter helpers, additional `Rect`/`Layout` helpers, and a no-side-effect `crossterm` compatibility module for clear/attribute/color command values plus explicit `NotImplementedError` raw-terminal operations. Real terminal behavior remains delegated to Textual.

## 2026-06-13 - render/renderable bridge ratatui type acceptance

Status: complete_slice

Tightened `pycodex.tui.render.renderable` so Rust ratatui counterparts represented by the bridge (`Span`, `Line`, `Text`, and `Paragraph`) are accepted by `as_renderable`. Span/line rendering now preserves bridge styles in `Buffer`, and paragraph rendering delegates to `ratatui_bridge.widgets.Paragraph` rather than flattening everything to plain strings.

## 2026-06-13 - ratatui bridge behavior test expansion

Status: complete_slice

Expanded `tests/test_tui_ratatui_bridge.py` with behavior checks for layout constraint allocation, side-specific unicode block borders, paragraph wrapping/alignment/scroll plus clear behavior, Textual/Rich adapter conversion, WidgetRef fallback dispatch, and Terminal/TestBackend buffer-backed draw semantics. Verified the touched bridge/render test set with `26 passed`.

## 2026-06-13 - ratatui bridge high-risk contract tests

Status: complete_slice

Added additional `ratatui_bridge` contract tests for layout overflow/min/zero-area behavior, buffer intersection/indexing, paragraph style/no-wrap/scroll/block behavior, block tiny/title boundaries, adapter immutability, and explicit `crossterm` no-side-effect errors. Verified the focused bridge/render suite with `36 passed`.

## 2026-06-13 - codex-tui theme_picker bridge render completion

- Status: complete_slice
- Rust module: `codex/codex-rs/tui/src/theme_picker.rs`
- Python module: `pycodex/tui/theme_picker.py`
- Tests: `tests/test_tui_theme_picker.py`
- Notes: Added ratatui-bridge `Rect`/`Buffer` rendering for wide and narrow theme preview renderables while preserving the existing semantic preview-line model. Preview rows now render styled line numbers, diff markers, and inserted/deleted/context code into the shared cell buffer; deleted preview code carries the DIM modifier. Exact syntax highlighting, upstream diff style context, concrete `AppEventSender` callbacks, and config persistence remain dependency/runtime boundaries.
## 2026-06-14 - render/highlight.rs no-op syntax highlighting boundary

- Status: `blocked`
- Rust module: `codex-tui::render::highlight`
- Python module: `pycodex.tui.render.highlight`
- Notes: Replaced the previous Pygments/token approximation with an explicit no-op syntax-highlighting boundary. The module keeps public API shape, built-in theme names, theme-selection helpers, syntax lookup aliases, highlight limits, and plain-text fallback helpers, but real token-level highlighting returns `None`. Exact syntect/TextMate behavior is deferred because available Python candidates either require Python >=3.8/3.9 or introduce non-portable dependencies.

## 2026-06-14 - tui/event_stream.rs

- Rust module: `codex-tui::tui::event_stream`
- Python module: `pycodex.tui.tui.event_stream`
- Status: `complete_slice`
- Notes: Implemented semantic event broker and TUI event stream behavior: pause/resume source lifecycle, resume generation wakeups, fake event source/handle, draw queue mapping including lagged draws, crossterm-like key/resize/paste/focus mapping, unmapped-event skipping, error termination, and round-robin draw/input polling. Real crossterm stdin, tokio stream scheduling, Unix suspend key handling, and terminal palette side effects remain explicit runtime boundaries.

## 2026-06-14 - tui/textual_event_source.py

- Scope: Textual backend adapter for `codex-tui::tui::event_stream`
- Python module: `pycodex.tui.tui.textual_event_source`
- Status: `complete_slice`
- Notes: Added an internal Textual event adapter that preserves Rust-style `EventSource`/`EventBroker`/`TuiEventStream` APIs while accepting Textual-like key, resize, paste, focus, blur, and draw inputs. Business modules do not import Textual directly; real Textual app lifecycle and terminal I/O remain backend/runtime concerns.

## 2026-06-14 - tui/textual_event_source lifecycle bridge

- Scope: Textual lifecycle hook binding for `codex-tui::tui::event_stream`
- Python module: `pycodex.tui.tui.textual_event_source.TextualEventBridge`
- Status: `complete_slice`
- Notes: Added a small lifecycle bridge with `on_key`, `on_resize`, `on_paste`, `on_focus`, and `on_blur` methods that forward Textual app/widget events into the Rust-style `TuiEventStream`. This completes the project-facing API shape for Textual-backed input while keeping actual Textual scheduling and terminal I/O framework-owned.

## 2026-06-14 - tui/event_stream.rs complete promotion

- Rust module: `codex-tui::tui::event_stream`
- Python module: `pycodex.tui.tui.event_stream`
- Textual adapter: `pycodex.tui.tui.textual_event_source`
- Status: `complete`
- Notes: Promoted from `complete_slice` to `complete`. Python now preserves the Rust-facing event stream API and all module-owned behavior while using a Textual-backed event source/lifecycle bridge instead of Rust crossterm/tokio internals. Business modules consume `EventBroker`, `TuiEventStream`, and `TuiEvent`; Textual remains an internal backend adapter.

## 2026-06-14 - chatwidget/turn_runtime.rs

- Rust module: `codex-tui::chatwidget::turn_runtime`
- Python module: `pycodex.tui.chatwidget.turn_runtime`
- Status: `complete_slice`
- Notes: Replaced the empty scaffold with a semantic ChatWidget turn-runtime state model covering task-running derivation, task-start reset/working status, runtime metrics merge/logging, finalize-turn cleanup, warning deduplication, plan update progress, plan implementation prompt gating/context label, and interrupted-turn messages. Full concrete `ChatWidget`, history cell rendering, app-server error/rate-limit flows, and real notification/backends remain adjacent module or runtime boundaries.

## 2026-06-14 - notifications/osc9.rs complete promotion

- Rust module: `codex-tui::notifications::osc9`
- Python module: `pycodex.tui.notifications.osc9`
- Status: `complete`
- Notes: Promoted from `complete_slice` to `complete`. The Python module now exposes the Rust-facing `Osc9Backend`/`PostNotification` behavior, semantic tmux passthrough detection, OSC 9 ANSI formatting, tmux ESC-byte escaping, and explicit ANSI-only Windows behavior without introducing terminal side-effect dependencies.

## 2026-06-14 - config_update.rs complete promotion

- Rust module: `codex-tui::config_update`
- Python module: `pycodex.tui.config_update`
- Status: `complete`
- Notes: Promoted from `complete_slice` to `complete`. The Python module now carries the Rust `FEATURES` key/default table used by `build_feature_enabled_edit`, preserves module-owned config edit builders and app-server request payload shapes, and keeps real app-server I/O behind the injected request-handle boundary rather than fabricating transport behavior.

## 2026-06-14 - service_tier_resolution.py compatibility cleanup

- Rust module: `codex-tui::service_tier_resolution`
- Python module: `pycodex.tui.service_tier_resolution`
- Status: `complete`
- Notes: Confirmed the module already had a complete status entry and normalized remaining Python 3.10 union type syntax to Python 3.7-compatible `typing` annotations. No behavior changes and no tests were run in this step.

## 2026-06-14 - collaboration_modes.rs complete promotion

- Rust module: `codex-tui::collaboration_modes`
- Python module: `pycodex.tui.collaboration_modes`
- Status: `complete`
- Notes: Promoted from `complete_slice` to `complete`. The Python module mirrors the Rust helper contract around builtin collaboration presets, TUI-visible modes, default/plan lookups, next-mode cycling, cloned returns, and the intentionally ignored `ModelCatalog` parameter. Type annotations were normalized for Python 3.7 compatibility.

## 2026-06-14 - motion.rs complete promotion

- Rust module: `codex-tui::motion`
- Python module: `pycodex.tui.motion`
- Status: `complete`
- Notes: Promoted from `complete_slice` to `complete`. The Python module now covers the truecolor shimmer branch and Rust `as_millis()` truncation behavior in addition to reduced-motion fallbacks, blink cadence, shimmer delegation, and source-policy scanning. `supports_color` probing remains a small injectable semantic boundary rather than a terminal side effect.

## 2026-06-14 - wrapping.rs completion audit

- Rust module: `codex-tui::wrapping`
- Python module: `pycodex.tui.wrapping`
- Status: `complete_slice`
- Notes: Not promoted to `complete`. Python has the semantic URL-aware wrapping behavior needed by TUI callers, but exact Rust `textwrap` owned/borrowed-line and byte-range reconstruction behavior remains an explicit blocked sub-boundary. Type annotations were partially normalized for Python 3.7 compatibility without changing wrapping behavior.

## 2026-06-14 - shimmer.rs complete promotion

- Rust module: `codex-tui::shimmer`
- Python module: `pycodex.tui.shimmer`
- Status: `complete`
- Notes: Promoted from `complete_slice` to `complete`. The Python module now covers the full shimmer algorithm and the Rust stdout truecolor-probe branch using semantic style objects instead of ratatui framework values. Type annotations were normalized for Python 3.7 compatibility.

## 2026-06-14 - tooltips.rs completion audit

- Rust module: `codex-tui::tooltips`
- Python module: `pycodex.tui.tooltips`
- Status: `complete_slice`
- Notes: Not promoted to `complete`. The Python module now sources tooltip catalog text from the upstream Rust `tooltips.txt` file when available and has a Python 3.7-compatible announcement TOML fallback parser. Real remote announcement fetching remains an explicit network/runtime boundary, so full module completion is blocked unless we choose to implement a no-proxy timeout HTTP fetch policy.

## 2026-06-14 - update_action.rs complete promotion

- Rust module: `codex-tui::update_action`
- Python module: `pycodex.tui.update_action`
- Status: `complete`
- Notes: Promoted from `complete_slice` to `complete`. The previous blocked install-context boundary is now wired to the ported `pycodex.install_context.InstallContext.current` by default, while preserving injection for tests. The module only resolves update actions and command strings; it does not execute update commands.

### update_versions.rs Python 3.7 compatibility audit

| Rust module | Status | Notes |
|---|---|---|
| `update_versions.rs` | `complete` | Full Rust module behavior remains complete; Python annotations now avoid 3.10-only union and generic built-in syntax for Python 3.7 portability. |

### app_server_approval_conversions.rs completion audit

| Rust module | Status | Notes |
|---|---|---|
| `app_server_approval_conversions.rs` | `complete` | Narrow app-server approval conversion helpers are fully covered against Rust source/tests; Python keeps semantic dataclass models and 3.7-compatible annotations. |

### approval_events.rs completion audit

| Rust module | Status | Notes |
|---|---|---|
| `approval_events.rs` | `complete` | TUI-owned approval request models and default decision logic are complete against the Rust module boundary. App-server protocol serialization remains represented by semantic DTOs, which is the local module contract rather than missing behavior. |

### key_hint.rs completion audit

| Rust module | Status | Notes |
|---|---|---|
| `key_hint.rs` | `complete` | Key binding matching, display helpers, plain-text input boundary, C0 control compatibility, shifted-letter compatibility, binding-list alternatives, and platform AltGr handling are complete against the Rust module boundary. Python uses semantic key strings and Span DTOs instead of crossterm/ratatui concrete types. |

### model_migration.rs completion audit

| Rust module | Status | Notes |
|---|---|---|
| `model_migration.rs` | `complete` | Model migration copy, prompt screen state machine, semantic rendering, event loop lifecycle, and alt-screen guard behavior are complete against the Rust module boundary. Framework concrete rendering is represented by semantic rows per project ratatui/Textual bridge strategy. |

### slash_command.rs completion audit

| Rust module | Status | Notes |
|---|---|---|
| `slash_command.rs` | `complete` | Slash command enum/table behavior is complete: canonical strings, parse aliases, descriptions, inline-argument support, side-conversation/task availability, visibility filtering, presentation order, `subagents` canonical command, and Python 3.7-compatible parsing. |

### keymap.rs completion audit - remains complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Re-audited for possible promotion. The current Python module is a useful semantic slice, but the Rust module owns a much larger runtime resolver contract: complete default table, global fallback, explicit unbinding, legacy-default pruning, fixed shortcuts, reserved overlaps, and exhaustive conflict validation. It should remain `complete_slice` until those rules are ported and tested. |

### keymap.rs resolver behavior expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Implemented a much larger semantic resolver slice: global fallback, explicit unbind, legacy pruning, reserved/fixed shortcut validation, approval overlay conflicts, optional-action remapping, interrupt-turn rules, and broader defaults. Remaining work for `complete`: exact full Rust default table, every Rust conflict-validation test, and complete legacy/fixed-overlap matrix parity. |

### keymap.rs legacy pruning and explicit-conflict expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Tightened resolver parity: legacy pruning now only removes unconfigured new defaults, preserving explicit conflicts; added approval conflict and reassignable fixed-shortcut remap behavior. Remaining work for `complete` is still the exact full default table and exhaustive Rust keymap test inventory. |

### keymap.rs interrupt-question-navigation conflict expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added request-user-input question-navigation conflict validation for `chat.interrupt_turn` versus list left/right bindings. This closes another Rust-tested resolver rule while the full default table and exhaustive conflict matrix remain outstanding. |

### keymap.rs parser and precedence expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added broader named-key parser coverage and resolver precedence tests for global app bindings plus composer local overrides. Remaining `complete` work is still exact full Rust default table and exhaustive validation matrix parity. |

### keymap.rs binding helper precedence expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added helper-level resolver parity coverage for explicit unbind and local/global/default precedence. This strengthens the resolver core while full default-table and exhaustive conflict-test parity remain outstanding. |

### keymap.rs diagnostics expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added diagnostics parity coverage for invalid binding config paths and conflict messages containing both action names. Remaining complete work is exact full default table plus exhaustive Rust keymap test inventory. |

### keymap.rs struct inventory expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added dataclass field-inventory parity coverage for every RuntimeKeymap child struct. This makes remaining default-table and resolver-matrix work safer by catching field drift against the Rust module boundary. |

### keymap.rs conflict scope and modifier parser expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added parity evidence for Vim/pager conflict scopes and modifier parser alias/composition behavior. Remaining complete work is still exact full default table and exhaustive Rust test coverage. |

### keymap.rs default alias and explicit-unbind expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added parity evidence for explicit empty-array unbinding, raw output toggle remapping, editor newline/deletion aliases, composer shortcut alias, and approval fullscreen alias. Remaining complete work is exact full default table and exhaustive Rust test inventory. |

### keymap.rs new-default helper and symmetric list conflict expansion - still complete_slice

| Rust module | Status | Notes |
|---|---|---|
| `keymap.rs` | `complete_slice` | Added direct tests for new-default pruning helpers and symmetric list move/page conflict behavior. This closes another resolver-rule seam while full default-table parity remains outstanding. |

### keymap.rs cross-surface conflict parity expansion - 2026-06-14

Status: `complete_slice`.

Implemented another Rust-backed slice of the keymap runtime resolver:
- App/global actions now reject shadowing of list and approval handlers, with the Rust-documented `clear_terminal` / `list.move_right` `ctrl-l` exception.
- Main handlers now reject shadowing editor handlers, matching Rust tests where composer/app bindings would otherwise consume before textarea editor logic.
- Canonical `ctrl-alt-shift-a` parsing is now covered by a Python parity test.

This improves behavioral fidelity but does not yet close the entire `keymap.rs` contract.

### keymap.rs editor newline ownership expansion - 2026-06-14

Status: `complete_slice`.

Adjusted keymap defaults so plain `Enter` is owned by `composer.submit`, not `editor.insert_newline`. This matches the newly ported main-handler shadowing model and prevents the Python default keymap from conflicting with itself. Added parity coverage for explicit `editor.insert_newline = enter` conflict behavior.

### keymap.rs composer shadowing guard expansion - 2026-06-14

Status: `complete_slice`.

Added Python parity tests for Rust composer shadowing cases where app/global bindings collide with `composer.queue` and `composer.toggle_shortcuts`. This strengthens evidence for the already implemented main-scope resolver rule.

### keymap.rs composer submit shadowing guard - 2026-06-14

Status: `complete_slice`.

Added Python parity coverage for the Rust app-scope composer submit shadowing test. This closes the composer submit/queue/toggle-shortcuts shadowing group at the test-evidence level while the broader keymap module remains `complete_slice`.

### keymap.rs main/editor allowed-overlap correction - 2026-06-14

Status: `complete_slice`.

Corrected the previous editor newline ownership slice after confirming Rust source: plain `Enter` is intentionally present in both `composer.submit` and `editor.insert_newline`, and Rust allows that exact overlap. Python validator and tests now reflect the Rust allowed-overlap list instead of rejecting it.

### keymap.rs main-surface default table expansion - 2026-06-14

Status: `complete_slice`.

Aligned app/chat/composer built-in defaults with Rust `RuntimeKeymap::built_in_defaults`, including external editor, vim-mode toggle, edit queued message, queue, and shortcut overlay bindings. Added Python parity coverage for the main-surface default table slice.

### keymap.rs editor default table expansion - 2026-06-14

Status: `complete_slice`.

Aligned the Python `EditorKeymap` built-in defaults with Rust `RuntimeKeymap::built_in_defaults`, including Ctrl movement aliases, Alt/Ctrl word movement aliases, line boundary order, and deletion word bindings. Added a complete Python parity guard for the editor default vector contents and order.

### keymap.rs Vim default table expansion - 2026-06-14

Status: `complete_slice`.

Aligned Python Vim normal/operator/text-object built-in defaults with Rust `RuntimeKeymap::built_in_defaults`, including operator motion scope, `$` line-end bindings, and expanded text-object aliases. Added full Python parity guard for the Vim default groups.

### keymap.rs pager/list/approval default table expansion - 2026-06-14

Status: `complete_slice`.

Aligned Python pager/list/approval built-in defaults with Rust `RuntimeKeymap::built_in_defaults`, including pager close semantics, list Ctrl navigation aliases, and approval action bindings. Added full Python parity guard for these default groups.

### keymap.rs invalid path and prune-all guard expansion - 2026-06-14

Status: `complete_slice`.

Added Python parity guards for invalid global transcript/editor binding path diagnostics and the list move-up prune-all boundary where legacy bindings consume every new page-up default. No module promotion yet; this is another Rust-test coverage slice.

### keymap.rs exact pruning guard expansion - 2026-06-14

Status: `complete_slice`.

Added exact Python parity guards for app/list, approval/list, Vim normal, and Vim operator pruning behavior after the full default-table updates. This strengthens Rust-test evidence but still leaves final parser/validation audit before `complete`.

### keymap.rs approval overlay allowed-overlap correction - 2026-06-14

Status: `complete_slice`.

Corrected approval overlay validation to match Rust's special-case overlap: `list.cancel` and `approval.decline` may share plain `Esc`, while other overlay collisions still fail. Added Python parity guard for both the allowed and rejected cases.

### keymap.rs context conflict guard expansion - 2026-06-14

Status: `complete_slice`.

Added explicit Python parity guards for Rust's editor, pager, list movement, and list page/jump conflict tests, plus the invalid `global.copy = meta-o` diagnostic path. Module remains `complete_slice` pending final audit.

### keymap.rs fixed shortcut edge guard expansion - 2026-06-14

Status: `complete_slice`.

Added explicit Python parity guards for fixed shortcut and reassignable-empty-default behavior: reserved paste image, `alt-.` reassignment, `kill_whole_line`, and `toggle_fast_mode`. This is evidence strengthening before final module audit, not yet a completion promotion.

### keymap.rs pair validator interface cleanup - 2026-06-14

Status: `complete_slice`.

Exported the new pair-based shadow validator and added focused parity-style coverage for exact allowed overlap handling. This keeps the Python validator surface coherent while the module awaits final audit before any `complete` promotion.

### keymap.rs completion audit - 2026-06-14

Status: `complete`.

Promoted `keymap.rs` from `complete_slice` to `complete` after final Rust-test inventory audit. Python now carries the module-scoped behavior contract: key binding parsing, runtime keymap defaults, global/local resolution, explicit unbinds, legacy/default pruning, fixed shortcut handling, conflict validation scopes, allowed overlap exceptions, and diagnostics. Tests were not run in this turn; completion is based on source and parity-test coverage audit.

### wrapping.rs display-width and indent guard expansion - 2026-06-14

Status: `complete_slice`.

Added Python parity guards for Rust wrapping behavior around indent width accounting, double-width emoji wrapping, and no-indent multi-line wrapping. The module remains `complete_slice` because range reconstruction and mixed URL continuation-width edge cases still need source/test audit before safe promotion.

### bottom_pane::status_line_style completion audit - 2026-06-14

Status: `complete`.

Promoted `bottom_pane::status_line_style` to `complete`. The Python module now matches the Rust behavior contract for status-line segment ordering, separator text, accent fallback styles, theme resolver precedence, dim/underline modifiers, RGB and named-color softening, and empty input handling. Fixed the separator mojibake to Rust's `" Â· "`. Tests were not run in this turn.

### render::renderable completion audit - 2026-06-14

Status: `complete`.

Promoted `render::renderable` to `complete`. The Python module carries the Rust behavior contract for renderable trait defaults, text/paragraph semantic rendering, column/flex/row/inset layout, cursor position/style delegation, and inset helper behavior. Rust has no in-file tests for this module; Python parity tests cover the public behavior anchors. Tests were not run in this turn.

### keymap_setup::debug completion audit - 2026-06-14

Status: `complete`.

Promoted `pycodex.tui.keymap_setup.debug` to complete for the Rust `codex-tui::keymap_setup::debug` module. The Python implementation mirrors the Rust debug-pane lifecycle and report semantics using plain semantic lines rather than ratatui `Line`/`Span` values: initial/delayed help copy, key-event report construction, unsupported config-key reporting, raw-event summaries, action-match listing, Ctrl-C completion, Esc preference, and next-frame delay behavior.

Tests mapped in `tests/test_tui_keymap_setup_debug.py`; not run in this turn.

### keymap_setup::picker completion audit - 2026-06-14

Status: `complete`.

Promoted `pycodex.tui.keymap_setup.picker` to complete for Rust `codex-tui::keymap_setup::picker`. The Python module now mirrors the picker construction contract with semantic dataclasses: tab inventory, headers, counts, row prefixes, selected-row lookup, debug tab action, footer hints, disabled empty states, and Unicode display-width name-column sizing. Runtime bottom-pane mounting and channel transport remain neighboring integration concerns rather than picker-owned behavior.

Tests mapped in `tests/test_tui_keymap_setup_picker.py`; not run in this turn.

### keymap_setup::actions completion audit - 2026-06-14

Status: `complete`.

Promoted `pycodex.tui.keymap_setup.actions` to complete for Rust `codex-tui::keymap_setup::actions`. The Python module now mirrors the UI-facing action catalog, Rust descriptions, feature filtering, binding-slot accessors, runtime binding lookup, binding summary order/de-dup semantics, debug binding source classification, and matching-action reports. Concrete `TuiKeymap`/`RuntimeKeymap` storage and crossterm event structs remain represented through semantic Python mappings and duck-typed objects, which is sufficient for this module-owned contract.

Tests mapped in `tests/test_tui_keymap_setup_actions.py`; not run in this turn.

### keymap_setup root module audit - 2026-06-14

Status: `blocked`.

`pycodex.tui.keymap_setup.__init__` remains a scaffold for Rust `codex-tui::keymap_setup` root behavior. Audit confirmed the Rust source is a large behavior-owning module rather than a pure aggregation facade. Completed neighboring modules (`actions`, `picker`, `debug`) are dependencies, but the root still owns menus, capture lifecycle, key serialization, config mutation, edit outcomes, and routing tests. Do not mark this module complete until those behaviors are implemented and covered by parity tests.

### session_log completion audit - 2026-06-14

Status: `complete`.

Promoted `pycodex.tui.session_log` to complete for Rust `codex-tui::session_log`. The Python module now covers the full session JSONL logging contract owned by the Rust module: environment enablement, explicit/default path handling, first-open retention, JSON-line writing, session metadata, inbound app-event summaries, outbound op records, session end, disabled no-op behavior, and deterministic test injection for the otherwise global logger.

Tests mapped in `tests/test_tui_session_log.py`; not run in this turn.

### file_search completion audit - 2026-06-14

Status: `complete`.

Promoted `pycodex.tui.file_search` to complete for Rust `codex-tui::file_search`. The module-owned orchestration contract is covered: query deduplication, empty-query clearing, CWD/search-dir reset, session creation parameters, start-error swallowing, token rollover, reporter filtering, result event emission, and completion no-op. The concrete file-search engine remains an injected dependency boundary matching Rust's use of the external `codex-file-search` crate.

Tests mapped in `tests/test_tui_file_search.py`; not run in this turn.
