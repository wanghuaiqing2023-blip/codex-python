# Porting Status

## 2026-07-14: shell_command typed TUI lifecycle closure

- Fixed the remaining interactive-session gap where `shell_command` executed
  successfully and returned output to the model, but produced no structured
  `Running`/`Ran` history cell in the terminal TUI.
- Root cause: the shared turn projection recognized only
  `exec_command`/`shell`/`local_shell`, and the product shell handler flattened
  `ExecToolCallOutput` into `FunctionToolOutput` before completion projection.
- Added a shared `CommandExecutionToolOutput` adapter that preserves the typed
  stdout, stderr, aggregate, exit code, duration, and timeout result while
  retaining the exact model-visible shell output. All shell-family tools now
  enter the same `CommandExecution` started/completed lifecycle consumed by
  `chatwidget::command_lifecycle`; no terminal rendering special case was
  added.
- Added a real product-runtime regression proving `shell_command` emits exactly
  one started item and one completed item with exit code `0` and captured
  output before the assistant follow-up.
- Fixed the Windows PowerShell command-title corruption that rendered embedded
  quotes as POSIX `shlex` escape fragments such as `'"'"'`. The shared command
  projection now resolves the same canonical session shell used by the product
  execution handler, including `InMemoryCodexSession.shell`, instead of falling
  back to a one-element raw command. The shared command parser then reverses
  app-server `shlex_join` output without consuming Windows path separators, so
  command lifecycle cells retain the original argv and render
  `Write-Output 'SHELL_COMMAND_OK'` consistently for every shell-family tool.
- Fixed behavior baseline remains commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`; `codex/` was not updated.
- Verification: core shell/turn/local-session/alignment groups `395 passed`;
  combined shell handler/turn runtime and TUI
  parsing/lifecycle/projection/app/terminal/alignment groups `376 passed`.

## 2026-07-13: shell_command product runtime closure

- Closed the interactive-session failure where `shell_command` was visible to
  the model but produced no command output or final assistant response. The
  Python handler previously required an injected test runner, while the fixed
  Rust owner constructs `tools::runtimes::shell::ShellRuntime` directly.
- Added the product `ShellRuntime` approval/sandbox/process path, including
  session approval caching, network approval metadata, timeout/cancellation,
  PowerShell UTF-8 setup, and structured `ExecToolCallOutput` formatting.
- CoreExec sessions now preserve the resolved default user shell, and the
  shell handler unwraps the Rust-shaped approval-policy cell used by real
  turns. Injected runners remain available only as focused test adapters.
- Added an end-to-end sampler regression that disables unified exec, verifies
  only `shell_command` is exposed, executes a real platform-shell command,
  feeds its output into the next model request, and receives the final answer.
- Fixed behavior baseline remains commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`; `codex/` was not updated.
- Verification: shell runtime, handler, CoreExec session, tool-plan, turn
  runtime, and TUI config-path groups passed (`522 passed`).

## 2026-07-13: Windows sandbox public CLI and parity evidence

- Closed a terminal-session enforcement gap discovered by manual acceptance
  scenario 3. The config bootstrap resolved the fixed-Rust
  `WindowsSandboxLevel`, but Python dropped it before constructing the exec
  session and turn context. As a result, `ToolOrchestrator` selected no native
  Windows sandbox even while `/status` correctly reported the workspace
  permission profile.
- The level now follows the Rust-owned path
  `ExecConfigBootstrapPlan -> ExecSessionConfig -> InMemoryCodexSession ->
  InMemoryTurnContext -> ShellCommandHandler/ToolOrchestrator`. Thread settings
  snapshots and updates preserve the same value.
- Added a native Windows product-path regression proving a workspace profile
  blocks an `exec_command` write outside the workspace. Focused config,
  session, orchestrator, TUI permission/status, alignment, and native sandbox
  verification passed (`438 passed` plus `7 passed, 216 deselected`). Manual
  scenario 3 remains pending user revalidation.

- Diagnosed the manual "Read Only still writes" report as an invalid test
  session: the startup card showed `permissions: YOLO mode`, matching the
  persisted `danger-full-access`/`never` configuration, and no
  `Permissions updated to Read Only` history event was present. A public
  `pycodex sandbox --permissions-profile :read-only` write probe exited `1`
  and left no marker. The manual runbook now starts with explicit
  `-s read-only -a on-request`, requires `/status` confirmation, and stops if
  YOLO is visible. A CLI regression proves these explicit flags override a
  persisted Full Access configuration.
- Completed the fixed-commit Rust/Python public sandbox comparison for
  read-only writes, workspace writes, outside-workspace writes, restricted
  network, and piped stdin. Results match and are recorded in
  `WINDOWS_SANDBOX_PARITY_EVIDENCE.md`.
- Replaced the Python Windows `sandbox` CLI capture replay with the native
  live-session path: stdin, stdout, and stderr are forwarded concurrently,
  Ctrl+C terminates the sandbox Job Object, output drains for the Rust-aligned
  five-second window, and native spawn/setup failures remain fail closed.
- Verified the fixed Rust ConPTY path by explicitly running its ignored CI test
  on this Windows host, and paired it with Python's real restricted ConPTY
  test. Added a real extra-read-root refresh case to the elevated security
  matrix; the root is readable and remains non-writable.
- Proved the sandbox-account Python runner can load and execute from an
  isolated staged package directory rather than the repository import path.
- Verification after these changes: Windows sandbox/CLI group `140 passed, 1
  skipped`; explicit elevated matrix passed; complete `pycodex/tui` tree `2410
  passed, 64 skipped`; root TUI/permission integration `1640 passed, 6 skipped,
  22 subtests passed`; all 942 root test files `12681 passed, 37 skipped, 873
  subtests passed`; remaining internal tests `3 passed`.
- The only remaining goal gate is recorded Windows Terminal acceptance. The
  goal remains active.

## 2026-07-12: Native Windows sandbox product path

- Implemented the native Windows sandbox product path against fixed Rust
  commit `1c7832ffa37a3ab56f601497c00bfce120370bf9`; the vendored baseline was not
  changed.
- Closed the former fail-open dispatch defect: raw exec and unified exec now
  route Windows sandbox requests to native legacy/elevated backends and refuse
  unrestricted fallback after native setup/spawn failures.
- Implemented permission resolution, root-specific capability SIDs, restricted
  tokens, private desktop, stdio, ConPTY resize, job-based descendant cleanup,
  and complete output draining.
- Implemented setup/refresh, local sandbox users, DPAPI credentials,
  capability ACLs, persistent deny-read reconciliation, offline/online
  firewall identities, fixed-GUID WFP defense filters, and daily sandbox logs.
- Elevated execution uses a sandbox-account command runner with framed binary
  I/O. Real tests cover PowerShell/cmd/direct execution, deny paths,
  case/device/junction/UNC bypasses, network denied/enabled behavior, 1.8 MB
  output, timeout/cancel, descendants, and TTY resize.
- Corrected stale deny ACE removal by rebuilding and verifying the DACL after
  the Win32 convenience API reported success without removing the entry.
- A real UAC setup completed and logged all 12 WFP filters installed.
- App-server setup/readiness and CLI debug paths delegate to the native backend.
- Verification: native elevated security matrix, Windows sandbox/core product
  groups, and focused TUI permission/status regression passed. The later
  2026-07-13 entry records the completed A/B, live CLI stdio, staged runner, and
  broader TUI evidence.

## 2026-07-12: terminal composer Up/Down history recall

- Connected the already ported `bottom_pane::chat_composer_history` state
  machine to the real terminal product path for fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Canonical submissions are now recorded at the shared composer submit
  boundary. Empty entries are ignored, adjacent duplicates collapse, Up walks
  toward older entries, Down walks toward newer entries, and moving past the
  newest entry clears the draft.
- Startup message-history metadata and lookup callbacks now provide Rust's
  combined offset space: persistent entries first, current-session entries
  after them. The initial persistent count remains fixed while local entries
  are appended, preventing newly persisted prompts from being counted twice.
- Active `BottomPaneView` input and visible slash-command popup navigation keep
  priority over history recall. Recalled slash text suppresses popup reopening
  while history browsing remains active.
- Verification: combined history/composer/controller/runtime/app/alignment
  tests `263 passed`; complete TUI suite `2410 passed, 64 skipped`.

## 2026-07-12: terminal composer wrapping and session-header parity

- Aligned the real terminal composer with fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9` owners
  `bottom_pane::chat_composer`, `textarea`, `chatwidget::rendering`, and
  `app::resize_reflow`. Long drafts now wrap by terminal-cell width, preserve
  the two-column live prefix on continuation rows, place the cursor on the
  final visual row, and expand/shrink the tracked live viewport without
  leaving stale rows.
- Audited the apparent startup permission-row difference against
  `history_cell/session.rs`. The fixed Rust header intentionally shows a
  permission row only for YOLO (`never` plus full access); read-only/on-request
  keeps the compact header. Python already follows that condition, and a named
  regression test now prevents either configuration from drifting.
- The fixed Rust baseline was not updated or synchronized.
- Verification: focused owner tests `183 passed`; terminal product/alignment
  tests `88 passed`; complete TUI suite `2405 passed, 64 skipped`.

## 2026-07-12: interactive project-trust permission defaults

- Aligned bare interactive `python -m pycodex` startup with fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`. The TUI bootstrap now resolves
  the active project using the configured cwd and Git root, applies Windows
  case-insensitive project lookup, and derives the fallback approval policy
  from `projects.<path>.trust_level`.
- Trusted projects default to `on-request`, untrusted projects default to
  `unless-trusted`, and projects without a trust record use Rust's interactive
  `on-request` default. The built-in permission profile follows the same Rust
  owner, including the Windows read-only fallback when no Windows sandbox
  backend is enabled and workspace-write for known projects when it is.
- Explicit CLI and `config.toml` `approval_policy`, `sandbox_mode`, and
  `default_permissions` values still take precedence. Non-interactive
  `codex exec` behavior remains unchanged at `never` plus its existing
  read-only fallback.
- Fixed behavior baseline remains the vendored commit above; `codex/` was not
  updated or synchronized.
- Verification: permission/config groups `156 passed, 4 subtests passed`;
  focused CLI runtime coverage `9 passed, 569 deselected`; complete TUI suite
  `2401 passed, 64 skipped`.

## 2026-07-12: fixed-Rust TUI approval automated closeout

- Corrected the manual session-grant verification gate: fixed Rust commit
  `1c7832f` exposes `request_permissions` and
  `exec_command.additional_permissions` through separate
  `request_permissions_tool` and `exec_permission_approvals` features. The
  runbook now enables both plus `unified_exec`; the Rust/Python ConPTY fixture
  asserts the actual model request schema contains `additional_permissions`
  before testing cross-turn grant reuse. The same fixture now adds a third
  deterministic file-write profile: both Rust and Python must open a fresh
  exec approval overlay after reusing the earlier network grant, and Esc must
  leave the target absent. The manual runbook uses this write profile instead
  of an ambiguous read already allowed by the base sandbox or exec policy.
- Fixed behavior baseline remains
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`; `codex/` was not updated or
  synchronized.
- Closed the automated Milestone 4 lifecycle evidence in
  `pycodex/tui/APPROVAL_ALIGNMENT.md`: pending replay, interruption wake-up,
  guardian terminal states and denial retry, shared active-view queues,
  external resolution, action-required terminal title restoration, typed
  decision history, MCP/user-input correlation, and resize/scrollback
  stability all use their Rust-owned module paths.
- The CoreExec bridge now preserves typed exec/network approval metadata and
  distinct call/approval identities. Apply-patch approval runs through the
  shared tool orchestrator and only writes after approval. A typed session
  conversation id keeps unified-exec approval requests on the real product
  path.
- Fixed-Rust visual evidence covers exec, patch, permissions, network,
  selected rows, footer hints, narrow Chinese text, and multi-file patches.
  Five Rust/Python interactive ConPTY round trips pass together for exec
  acceptance, exec cancellation with modal resize and next-turn Chinese
  recovery, apply-patch acceptance, request-permissions acceptance, and a
  session-scoped network permission reused by an identical later-turn tool
  profile without another decision key (`5 passed`), including modal input,
  blocked-operation recovery, stable history, title cleanup, and next-prompt
  recovery.
- Current verification: focused approval/replay/protocol/runtime groups
  `406 passed`; complete `pycodex/tui` suite `2401 passed, 64 skipped`.
- The cancellation comparison exposed two disconnected product-path bugs.
  Approval Abort was resolved as an ordinary failed tool call instead of
  interrupting the active turn, and interrupted-turn history was appended only
  to an internal semantic list instead of the canonical
  `HistoryProjectionSink`. Exec and patch Abort now share fixed-Rust
  `session::handlers` interruption semantics, and the fixed-Rust typed
  `Conversation interrupted` error cell reaches scrollback exactly once.
- The cross-turn session-grant fixture exposed an adjacent shared composer
  defect: continuously readable ASCII keys arriving slower than Rust's 8ms
  burst threshold replaced the previous held character because Python only
  flushed `PasteBurst` on idle polls. `bottom_pane::chat_composer` now mirrors
  fixed Rust `handle_input_basic_with_time` by flushing before every new key;
  owner tests and the real ConPTY session prove the complete post-modal prompt
  is preserved.
- The project Goal remains active until the user completes the final manual
  Windows Terminal session checklist: accept, reject/cancel, resize while a
  modal is active, exactly-once side effects/history, and successful input and
  response after the modal closes. `APPROVAL_ALIGNMENT.md` now contains a
  reproducible one-session runbook with exact CLI flags, disposable paths,
  tool-directed prompts, and a seven-row evidence table so this final gate is
  recorded rather than inferred from ad hoc testing.

## 2026-07-11: terminal session-scoped approval grants

- Closed approval-alignment Milestone 3 against fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- The terminal CoreExec session now owns a fresh `ApprovalStore`, matching
  Rust `SessionServices::tool_approvals`; only `ApprovedForSession` decisions
  are cached.
- Shell cache keys preserve normalized command, cwd, sandbox permissions, and
  additional permissions. Apply-patch keys preserve the local environment id
  and one absolute path per changed file.
- Incremental permission grants now survive the temporary per-turn callback
  config and remain visible to later turns in the same runtime.
- Multi-turn tests cover matching-key reuse, different-key prompting, denied
  decision non-caching, and fresh-runtime isolation. The focused approval,
  runtime, sandboxing, and runtime-key suites pass (`239 passed, 2 subtests`).
- Milestone 4 remains open for request queueing/replay, external-resolution
  dismissal, waiting/title state, typed audit history, and interruption edges.
- Started Milestone 4 at the shared bottom-pane owner: new approval requests
  are now offered to the active `ApprovalOverlay` through
  `BottomPaneView::try_consume_approval_request`, preserving Rust's LIFO queue
  instead of stacking independent terminal overlays. Focused view-stack and
  terminal product tests pass (`80 passed`).
- Connected fixed-Rust `app::app_server_requests` to the product runtime:
  typed JSON-RPC request ids are registered when requests arrive, external
  `ServerRequestResolved` notifications are converted back to exec/patch/
  permissions identities, and the terminal bottom-pane owner removes either
  the current request or a queued request without disturbing unrelated views.
  Unknown request ids are no-ops. The focused app/request/view/terminal and
  alignment suites pass (`214 passed`). Replay and broader interruption edges
  remain open.
- Connected `app::pending_interactive_replay` and `app::thread_events` to
  `TuiAppRuntime`. Snapshot replay now restores a typed `ThreadEventStore`,
  replays only unresolved requests, preserves request/thread/turn/item/
  approval identities, suppresses duplicate request-id projection, and routes
  all restored approvals through the normal ChatWidget/ApprovalOverlay queue.
  Outbound decisions update replay state and produce the correlated
  `AppServerRequestResolution`. Focused replay, app, view-stack, terminal, and
  alignment tests pass (`209 passed`). Turn-interruption completion remains the
  next Milestone 4 slice.
- Closed the local Core pending-waiter interruption gap: interrupting an active
  turn now aborts all exec/patch/permissions receivers and emits typed
  `ServerRequestResolved` notifications before interrupted `TurnCompleted`.
  The existing app-server correlation and bottom-pane dismissal path removes
  the current/queued overlay state, replay state reports no pending approvals,
  and a following turn can start normally. Product tests cover one waiter and
  three simultaneous approval categories. Global terminal input arbitration
  and inactive-thread request resurfacing remain open.

## 2026-07-11: terminal interactive approval round trip

- Completed approval-alignment Milestone 2 and connected the main Milestone 3
  round trip against fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Rebuilt `ApprovalOverlay` on the shared `ListSelectionView` and generic
  bottom-pane view stack. Up/Down, selected-row highlighting, Enter,
  shortcuts, Esc, and Ctrl+C now use the same framework as other active views.
- The submitted-turn event loop now multiplexes the existing terminal input
  source while an active view needs input; it does not create a competing
  reader or consume composer input during normal streaming.
- Approval choices now travel through `AppEventSender` and typed
  `AppCommand` operations. Exec, file-change, and incremental-permissions
  requests each have pending request/resolution paths that resume the same
  CoreExec turn.
- Added the local apply-patch callback boundary so on-request patches can ask
  the user instead of immediately returning an approval-required tool error.
- A real terminal product test covers request display, direction-key movement,
  Enter, `AppCommand::ExecApproval`, and turn completion. The complete TUI plus
  focused patch callback suite passed (`2444 passed, 59 skipped`), and exec
  session/config tests passed (`124 passed, 12 subtests passed`).
- Milestone 3 was subsequently closed by the session-scoped grant work above.
  Queue/replay, waiting/title state, typed audit history, and visual parity
  remain Milestones 4 and 5.
- A separate full `tests/test_exec_local_runtime.py` run reports 20 existing
  follow-up wire-shape failures involving a missing `success` field across
  unrelated tool categories; these are recorded rather than misrepresented as
  passing approval evidence.

## 2026-07-11: terminal typed approval request boundary

- Completed Milestone 1 of `pycodex/tui/APPROVAL_ALIGNMENT.md` against fixed
  Rust commit `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Replaced the Python-only `ExecApprovalRequested` notification with a typed
  `CommandExecutionRequestApproval` `ServerRequest`. The terminal protocol
  adapter now classifies requests generically and delegates their payloads to
  `chatwidget::protocol_requests`.
- Composed the existing `chatwidget::tool_requests` owner into the product
  `ChatWidgetProtocolRuntime`, added an approval-plan sink, and routed exec,
  patch, and incremental-permissions requests through canonical protocol event
  types instead of parallel simplified DTOs.
- Added full-payload coverage for ids, command/cwd/reason, decisions,
  exec-policy amendments, network context, and network-policy amendments, plus
  an alignment guard that forbids approval variants in `terminal_runtime.py`.
- Focused approval/protocol/runtime/alignment tests passed (`195 passed`); the
  complete TUI plus custom-terminal/insert-history suite passed (`2437 passed,
  59 skipped`).
- Approval is still not product-complete. Milestones 2 and 3 must add
  submitted-turn keyboard multiplexing, a real active approval view, and the
  decision round trip as one coherent slice.

## 2026-07-11: terminal approval alignment audit baseline

- Added `pycodex/tui/APPROVAL_ALIGNMENT.md` as the approval-specific
  implementation and acceptance baseline for fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Documented the complete approval lifecycle from policy decision through
  typed request, ChatWidget ownership, active bottom-pane view, task-time
  input, decision round trip, pending-operation resume, and typed audit
  history.
- Distinguished isolated DTO/owner coverage from real terminal product-path
  parity. The audit records the current implementation as partial: CoreExec can
  wait on an exec decision, but request routing, active-view presentation,
  submitted-turn keyboard input, and decision return are not connected.
- Added category matrices for exec, patch, incremental permissions, network,
  guardian/auto-review, and MCP elicitation, plus milestone exit gates and a
  regression matrix designed to prevent exec-only or terminal-runtime
  shortcuts.
- This entry records an audit baseline only. No approval behavior was changed
  or promoted to complete, so no code tests were required.

## 2026-07-11: terminal transcript overlay product closure

- Closed the fixed-Rust `Ctrl+T` product path through
  `tui::event_stream -> app::input -> app_backtrack -> pager_overlay -> custom_terminal`.
- The terminal input stream now emits a global `ctrl_t` event before composer
  mutation. Opening the overlay preserves the current draft and does not
  create a user turn.
- The overlay enters Rust's `1049` alternate screen with alternate-scroll
  support, renders through the minimal Frame/Buffer backend, applies pager
  navigation, and restores the hybrid scrollback/live-pane screen on close.
- Canonical typed history cells render through `transcript_hyperlink_lines`,
  so an exec cell's `ctrl + t to view transcript` hint now opens the complete
  command output rather than another truncated display projection.
- Pager navigation now normalizes Windows virtual-key, named, and ANSI forms
  for Up/Down, PageUp/PageDown, and Home/End. Changed rows containing Chinese
  or other wide cells use `custom_terminal` full-frame invalidation, preventing
  a moved pager offset from being hidden by an unsafe narrow-cell diff.
- Verification: owner/alignment/product tests passed (`176 passed`), the
  complete TUI plus custom-terminal suite passed (`2387 passed, 59 skipped`), and both the fixed
  Rust/Python Ctrl+T lifecycle and long-transcript scroll ConPTY comparisons
  passed (`2 passed`).

## 2026-07-11: structured terminal session history parity

- Aligned the interactive terminal session path to fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9` for reasoning summaries,
  command execution, file changes, final-message separators, and assistant
  output.
- Added a single `HistoryProjectionSink` boundary. Stable typed cells now
  enter the app-owned canonical transcript and `insert_history` exactly once;
  mutable command cells render through the bottom-pane frame and
  `custom_terminal` without entering scrollback.
- Replaced terminal-owned `Running`/`Ran` strings with canonical `ExecCell`
  lifecycle projection, including grouped calls, output, completion status,
  duration, and failure presentation.
- Core tool completion now emits the canonical completed CommandExecution
  before the model follow-up. Turn completion is deferred until all typed item
  notifications are queued, while model-history and rollout persistence no
  longer block the visible turn boundary.
- Replaced the thread-backed active-turn cancellation waiter with a cancellable
  async wait, preventing `asyncio.run()` shutdown from holding completed TUI
  turns open.
- Routed reasoning summaries, patch events, and final separators through their
  Rust-owned chat-widget/history-cell modules. Patch history now uses the
  shared `diff_render` path for operation headers, counts, line numbers,
  syntax spans, narrow-width wrapping, and raw copy text.
- Added deterministic product-sequence coverage and session comparison
  artifacts for raw VT, normalized scrollback, and current-screen evidence.
- Closed the Windows complex-command regressions found by manual testing:
  PowerShell output now receives Rust's last-mile UTF-8 prefix, tool bytes use
  the protocol smart decoder, and multiline shell scripts use the bounded
  exec-cell continuation layout instead of leaking the whole script.
- Removed the app adapter's duplicate projection of model `function_call`
  response items. Canonical core `CommandExecution` started/completed events
  are now the only owner of exec-cell lifecycle state, and protocol
  `CommandAction` mappings pass through the Rust `into_core` conversion.
- Closed the real `apply_patch` session gap: core now parses and verifies the
  patch before execution, emits the canonical `FileChange` started/completed
  pair through `tools::events`, and lets the existing patch history owner
  render Added/Modified/Deleted cells. The terminal adapter does not inspect
  patch text or synthesize display strings.
- Closed the multiline terminal-paste split: real terminals now enable
  bracketed paste and preserve its payload as one `TuiEvent::Paste`; the
  Rust-aligned `PasteBurst` state machine is also active as a fallback for
  terminals that only expose rapid key events. Embedded newlines mutate one
  composer draft and never dispatch intermediate user turns.
- Switched the real hybrid terminal history backend to Rust's existing
  `InsertHistoryMode::ZellijRaw` full-scroll insertion strategy. Stable typed
  cells are written through the terminal scrollback surface before blank live
  viewport rows are reserved, preventing Windows Terminal from silently
  dropping the leading rows of larger patch cells.
- Verification: focused owner/backend/runtime groups passed (`383 passed`),
  alignment and protocol owner tests passed (`83 passed`), the complete TUI
  plus tool-core regression suite passed (`2521 passed, 61 skipped, 3
  subtests passed`), and
  the fixed Rust/Python local-SSE ConPTY command-session comparison passed
  (`1 passed`).

## 2026-07-10: terminal permission profile transaction parity

- Fixed the terminal `/permissions` product path against Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Permission selections now resolve menu ids into concrete
  `PermissionProfile` and `ActivePermissionProfile` values, synchronize app,
  chat, session, and permissions state, and submit `OverrideTurnContext` to
  the active thread.
- The shared exec/TUI bootstrap now honors explicit `config.toml`
  `sandbox_mode` and `approval_policy` values with Rust precedence: explicit
  CLI overrides first, then config, then the existing exec fallback.
- Default now gives the next turn workspace-write permissions; Read Only and
  Full Access use their corresponding Rust built-in profiles.
- Reopening the popup reads the typed active-profile id and preserves the
  current-row highlight.
- Chat-widget info messages now enter the app-owned typed history event queue
  and flush through the terminal history sink. Permission changes therefore
  leave the Rust-style `• Permissions updated to ...` scrollback cell instead
  of remaining only in protocol runtime memory.
- Verification: focused permission/runtime/alignment tests passed
  (`145 passed`); TUI plus exec-config/bootstrap tests passed
  (`2403 passed, 59 skipped`).

## 2026-07-10: typed terminal history visual parity

- Aligned typed terminal history insertion with fixed Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- `TerminalHistoryWriter` now preserves semantic `Line`/`Span` styles through
  the real TTY insertion boundary instead of flattening status and history
  cells to plain strings.
- Rust `CompositeHistoryCell` spacing is preserved: `/status` and its card
  have one internal blank row, while typed user/assistant cells no longer gain
  a second synthetic separator.
- Prefix-aware pre-wrapping remains active for narrow terminal history rows.
- Verification: focused owner/alignment tests passed (`144 passed`), the full
  TUI suite passed (`2318 passed, 59 skipped`), and the fixed Rust/Python
  Windows ConPTY `/status` comparison passed (`1 passed`).

## 2026-07-10: terminal StreamController product path

- Bound the real terminal `AgentMessageDelta` path to the Rust-aligned
  `chatwidget::streaming -> StreamController -> commit_tick` lifecycle.
- Stable assistant cells now enter scrollback once through `insert_history`;
  the mutable tail is rendered in the bottom-pane frame and flushed by
  `custom_terminal`.
- Finalization now uses typed assistant transcript consolidation and the Rust
  `Required` / `IfResizeReflowRan` branches.
- Removed the obsolete product `TerminalAssistantStreamWriter` and absolute
  active-stream repaint path.
- Extended the canonical transcript to every terminal history write. User,
  session-header, status, stable assistant, and consolidated Markdown output
  now retain typed/source-backed cells; compatibility text writes are wrapped
  in a typed history cell before resize replay.
- Removed the parallel terminal string-stream state, delta renderer,
  open/write/finish projection APIs, and their tests. `ItemCompleted`-only
  assistant messages now enter the same StreamController/consolidation path.
- Aligned Ctrl-U kill-line and the composer shutdown presentation, both found
  by the fixed Rust/Python ConPTY resize comparison.
- Verification: `2406 passed, 59 skipped` for the complete
  TUI/backend/history suite. Low-level ConPTY output/resize passed (`2 passed`),
  and the fixed Rust/Python product resize-reflow comparison passed (`1 passed`).

Last updated: 2026-07-11

## Overall Objective
- Port OpenAI Codex from Rust (`codex/`) to Python (`pycodex/`) with behavior-first parity on core CLI/runtime paths while keeping dependencies minimal.

## Current Priority Focus
- Core command/runtime execution loop
- Local HTTP and in-memory core execution paths
- Tool dispatch and streaming/event mapping for common user flows
- Regression safety via smoke suites

## Progress This Turn
- Aligned the terminal resize/consolidation lifecycle with immutable Rust
  baseline `1c7832ffa37a3ab56f601497c00bfce120370bf9`. The product path now uses
  the existing 75 ms `TranscriptReflowState` debounce, coalesces continuous
  width/height changes, forces one source-backed replay when a resize occurs
  during streaming, and reserves full scrollback replay for actual resize.
  Normal `TurnCompleted` now follows the fixed Rust path explicitly:
  `chatwidget::streaming -> app::agent_message_consolidation ->
  ConsolidationScrollbackReflow::Required -> insert_history -> custom_terminal`.
  Python's single mutable stream tail is retained as canonical source before a
  required source-backed scrollback replay; the former adapter-only
  `repaint_finalized_tail` and cell-boundary cropping policy were removed.
  The VT evidence layer now models DECSTBM scroll regions and reverse index, so
  tests verify the same insert-history terminal effects instead of rewarding
  absolute-row repaint shortcuts. Added owner-level tests for continuous
  resize, stream-time resize, consolidation order, current-screen visibility,
  `/status` followed by a finalized turn, and buffer invalidation. The complete TUI suite passed
  (`2321 passed, 59 skipped`).
- Removed the streaming-time full history viewport replay that visibly moved
  the cursor through row 1 on every assistant delta. The terminal path now
  repairs only the retained prompt/current assistant tail near the history
  viewport bottom, while full viewport replay remains reserved for resize
  (including a resize deferred until stream completion). Regression coverage proves the user prompt stays
  visible, assistant text is not duplicated, unchanged footer rows are not
  repainted, and later deltas emit no `ESC[1;1H`. Focused tests passed
  (`162 passed`) and the complete TUI suite passed (`2315 passed, 59 skipped`).
- Fixed the terminal `/status` framework path against immutable Rust baseline
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`. Slash dispatch still treats it
  as an immediate local command, while the output callback now projects the
  live runtime through the canonical `status::card` composite history cell
  instead of the earlier reduced text DTO. The terminal card now carries
  model/reasoning details, directory, permissions, instruction sources,
  session metadata, token usage, and context window without submitting a user
  turn. ChatGPT-authenticated sessions now follow the Rust status refresh
  lifecycle before terminal projection, so current 5-hour/weekly limits replace
  the stale `data not available yet` placeholder. Focused/alignment tests passed
  (`98 passed`) and the complete TUI suite passed (`2315 passed, 59 skipped`).
- Completed the fixed-baseline terminal slash-view slice for `/review`,
  `/permissions`, and `/keymap`. Completed terminal input now crosses the
  composer boundary as Rust-like `InputResult` variants, recognized commands
  no longer fall through as user turns, and command-owned selection actions
  route through the shared `BottomPaneView` stack. Review targets submit real
  `AppCommand::Review` operations, permission selections persist and update
  the next-turn context, and keymap picker/action/capture/conflict flows persist
  edits and refresh live bindings. The alignment guard passed (`29 passed`)
  and the complete TUI suite passed (`2312 passed, 59 skipped`). All parity
  evidence remains pinned to commit `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Pinned the complete TUI alignment manifest to the immutable Rust Codex
  baseline commit `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
  `TuiAlignmentEntry`, `AdapterResponsibility`, and `TuiModuleOwner` now carry
  that commit explicitly. The alignment guard verifies the declared baseline,
  every mapped owner/responsibility, the parent repository's `codex` gitlink,
  and the checked-out `codex/` HEAD all match. It intentionally does not demand
  a clean submodule worktree, so local/user changes are preserved (`29 passed`).
- Fixed current GPT-5.6 catalog compatibility across the shared model/TUI
  owners. Production `models_cache.json` and `/models` responses can advertise
  `max` and `ultra` reasoning efforts for `gpt-5.6-sol`, `gpt-5.6-terra`, and
  `gpt-5.6-luna`; the Python protocol previously rejected the entire response,
  causing `/model` to silently fall back to the bundled GPT-5.5 catalog.
  Extended `protocol::openai_models`, model-cache parsing, reasoning ordering,
  `chatwidget::model_popups`, app state updates, shortcuts, and footer/status
  labels through the common owner path. A live account/catalog check now
  projects all three GPT-5.6 models into `TerminalModelPopupController`, and
  the complete TUI suite passes (`2305 passed, 59 skipped`).
- Completed the terminal TUI module-owner alignment audit for the current
  scrollback-first architecture milestone. `terminal_runtime.py` is now
  event-loop/runtime/draw/shutdown glue, and `terminal_controller.py` only
  binds `bottom_pane`, `app::resize_reflow`, and `custom_terminal` projection
  owners. The deleted `scrollback_runtime.py`, `terminal_surface.py`, and
  `terminal_frame.py` paths remain absent with no runtime imports; product TUI
  sources contain no Textual path. The alignment guard passed (`28 passed`),
  ratatui/custom-terminal tests passed (`91 passed`), and the complete
  `pycodex/tui` tree passed (`2302 passed, 59 skipped`). Also strengthened the
  Windows `tui::event_stream` IME-space contract so an IME-confirmation Space
  key-up is ignored while ordinary Space key-down text remains preserved
  (`42 passed`).
- Continued terminal TUI module-owner convergence for the scrollback-first
  product path:
  - Moved terminal scroll-region reset callback packaging out of
    `tui/terminal_runtime.py` and into
    `custom_terminal.TerminalScrollRegionResetter`. Runtime now binds the
    writer once and passes
    `reset_terminal_scroll_region=self._scroll_region.reset` into resize
    reflow instead of rebuilding `reset_scroll_region(self.stdout)` lambdas.
    Added custom-terminal owner coverage and alignment guards so
    scroll-region reset lifecycle stays with `codex-tui::custom_terminal`.
  - Moved terminal column callback packaging out of
    `tui/terminal_runtime.py` and into
    `custom_terminal.TerminalColumnProvider`. Runtime now binds the provider
    once and passes `terminal_columns=self._terminal_columns.columns` to
    history insertion and resize replay owners instead of rebuilding
    `terminal_size().columns` lambdas. Added custom-terminal owner coverage
    and alignment guards so backend terminal sizing stays with
    `codex-tui::custom_terminal`.
  - Moved terminal history-bottom-row callback packaging out of
    `bottom_pane/terminal_controller.py` and into
    `app.resize_reflow.TerminalBottomPaneFootprintCycleRunner.history_bottom_row_callback(...)`.
    The controller now binds a resize-reflow-owned callback once and its
    public `history_bottom_row(...)` method only delegates to that callback,
    instead of collecting terminal size, live status, bottom-pane state, and
    composer cursor policy locally for each history viewport query. Added
    resize-reflow owner coverage and alignment guards so history viewport
    bounds stay with `codex-tui::app::resize_reflow`.
  - Moved bottom-pane clear-cycle callback packaging out of
    `bottom_pane/terminal_controller.py` and into
    `app.resize_reflow.TerminalBottomPaneFootprintCycleRunner.clear_callback(...)`.
    The controller now supplies only a terminal-projection clear factory;
    `app::resize_reflow` owns when live status is collected and when the
    remembered bottom-pane footprint is cleared after a successful terminal
    clear. Added resize-reflow owner coverage and alignment guards so the
    controller no longer calls the footprint runner's clear cycle directly.
  - Moved bottom-pane clear/render request factory packaging out of
    `bottom_pane/terminal_controller.py` and into
    `bottom_pane.terminal_projection.TerminalBottomPaneRequestRunner`.
    The request runner now exposes `clear_factory_callback(...)` and
    `render_pass_factory_callback(...)` for resize-reflow callbacks to
    consume. The controller no longer stores stdin/layout/footer/live-status
    environment callbacks or defines local clear/render-pass factory methods;
    it only binds owner callbacks and delegates.
  - Moved bottom-pane render-cycle callback packaging out of
    `bottom_pane/terminal_controller.py` and into
    `app.resize_reflow.TerminalBottomPaneFootprintCycleRunner.render_for_view_state_callback(...)`.
    The controller now supplies only a terminal-projection render-pass factory;
    `app::resize_reflow` owns when terminal size, live status, bottom-pane
    render context, footprint repaint, and external repaint lifecycle are
    collected for a render pass. Added owner coverage and alignment guards so
    the controller no longer calls the footprint runner's render cycle
    directly.
  - Moved submitted-turn idle maintenance callback packaging out of
    `tui/terminal_runtime.py` and into
    `tui.event_stream.TerminalTurnIdleTicker`. Runtime now wires
    `on_idle=self._turn_idle.tick` into the submitted-turn event loop instead
    of importing `run_terminal_turn_idle_tick(...)` and rebuilding the
    resize-then-status lambda locally. Added event-stream owner coverage and
    alignment guards so idle poll handling stays with
    `codex-tui::tui::event_stream`.
  - Moved submitted-turn event-loop callback packaging out of
    `tui/terminal_runtime.py` and into
    `tui.event_stream.TerminalTurnEventLoopRunner`. Runtime now binds
    `on_event`, `on_closed`, `on_idle`, and `before_event` once and
    `_consume_events(...)` only calls `self._turn_events.consume(event_stream)`
    instead of invoking `run_terminal_turn_event_loop(...)` at the call site.
    Added event-stream owner coverage and alignment guards so submitted-turn
    event/idle/closed dispatch stays with `codex-tui::tui::event_stream`.
  - Moved passive footer text callback packaging out of
    `tui/terminal_runtime.py` and into
    `bottom_pane.footer.TerminalIdleFooterTextProvider`. Runtime now wires
    `footer_text=self._idle_footer.text` into the bottom-pane controller
    instead of importing `run_terminal_idle_footer_text_from_runtime(...)` and
    rebuilding the provider-backed footer lambda locally. Added footer-owner
    coverage and alignment guards so passive footer text stays with
    `codex-tui::bottom_pane::footer`.
  - Moved active-turn composer cursor visibility policy out of
    `tui/terminal_runtime.py` and into
    `chatwidget.status_surfaces.TerminalStatusSurfaceWriter.composer_cursor_visible()`.
    Runtime now wires `cursor_visible=self._status.composer_cursor_visible`
    into the bottom-pane controller instead of inspecting
    `self._status.turn_active` in a local lambda. The status writer also owns
    delayed bottom-pane render callback binding via
    `bind_render_bottom_pane(...)`, letting status be constructed before the
    bottom pane without introducing a runtime-local render lambda. Added
    status-surface owner coverage and alignment guards so cursor visibility
    follows the active-turn status owner.
  - Moved terminal composer prompt/submit/EOF callback packaging out of
    `tui/terminal_runtime.py` and into
    `bottom_pane.chat_composer.TerminalComposerEffectRunner`. Runtime now
    wires `write_nonterminal_prompt`,
    `submit=self._composer_effects.submit`, and
    `eof=self._composer_effects.eof` into the prompt reader instead of
    importing prompt/submit/EOF helpers or rebuilding runtime wrappers and
    clear-bottom-pane lambdas.
    Added chat-composer owner coverage and alignment guards to keep
    prompt/submit/EOF effect policy out of runtime glue.
  - Moved terminal composer prompt-read callback packaging out of
    `tui/terminal_runtime.py` and into
    `bottom_pane.chat_composer.TerminalComposerPromptReader`. Runtime now
    binds terminal-active, input-source, draft, resize, render,
    clear-live-pane, submit, interrupt, EOF, and key-routing callbacks once and
    `_read_prompt(...)` only calls `self._composer_prompt.read()` instead of
    invoking `run_terminal_composer_read_prompt(...)` at the call site. Added
    chat-composer owner coverage and alignment guards so prompt input
    lifecycle wiring stays with `codex-tui::bottom_pane::chat_composer`.
  - Moved terminal user-prompt scrollback output callback packaging out of
    `tui/terminal_runtime.py` and into
    `history_cell.messages.TerminalUserPromptOutputWriter`. Runtime now calls
    `self._user_prompt_output.write(prompt)` after prompt dispatch instead of
    invoking `run_terminal_user_prompt_output(...)` with live-status,
    insert-history, and bottom-pane render callbacks at the submit site. Added
    `history_cell::messages` owner coverage and alignment manifest entries so
    prompt scrollback output remains with the history-cell owner. Added
    `app.resize_reflow.TerminalResizeCoordinator.terminal_layout_active_state()`
    so this writer consumes a resize-owner dynamic layout-active provider
    instead of snapshotting the layout-active property at runtime construction.
  - Moved terminal startup notice callback packaging out of
    `tui/terminal_runtime.py` and into
    `history_cell.session.TerminalStartupNoticesWriter`. Runtime now calls
    `self._startup_notices.write()` during startup instead of importing
    `run_terminal_startup_notices_from_runtime(...)` and rebuilding
    write-history/blank-line callbacks in the event-loop owner. Added
    `history_cell::session` module-owner coverage and alignment guards so
    startup notice text and callback binding stay with the session history-cell
    owner.
  - Moved terminal startup session-header callback packaging out of
    `tui/terminal_runtime.py` and into
    `app.history_ui.TerminalSessionHeaderWriter`. Runtime now calls
    `self._session_header.write()` during startup instead of importing
    `run_terminal_session_header_from_runtime(...)` and rebuilding
    write-history/width arguments in the event-loop owner. The `/clear`
    executor factory now reuses the same app/history-ui writer boundary for
    header repaint after clearing, keeping session-header state collection and
    history-cell projection callback binding with `app::history_ui`.
  - Moved terminal `/clear` clear-screen/header callback packaging out of
    `tui/terminal_runtime.py` and into
    `app.history_ui.TerminalClearUiExecutor.for_terminal_runtime(...)`.
    Runtime now asks the `app::history_ui` owner for the bound clear executor
    instead of carrying `clear_terminal` and `render_header` lambdas or the
    ANSI clear helper. Added history-ui owner coverage and extended the TUI
    alignment manifest/critical module guard to include
    `pycodex/tui/app/history_ui.py`.
  - Moved the active-turn force status render callback out of
    `tui/terminal_runtime.py` and into
    `chatwidget.status_surfaces.TerminalStatusSurfaceWriter.render_turn_status_force()`.
    Runtime now wires `render_turn_status=self._status.render_turn_status_force`
    into turn submission instead of spelling out
    `render_turn_status(force=True)` in a lambda. Added status-surface owner
    coverage and alignment guards to keep turn-status force-render policy out
    of runtime glue.
  - Moved terminal user-turn submission callback packaging out of
    `tui/terminal_runtime.py` and into
    `chatwidget.turn_runtime.TerminalTurnSubmissionRunner`. Runtime now binds
    the runner once and `_run_turn(...)` only calls
    `self._turn_submission.submit(prompt)` instead of assembling started-at,
    history, status, protocol, app-runtime, and exit-code callbacks at the
    call site. Added `chatwidget::turn_runtime` manifest/module-owner
    coverage and critical-module guards so turn submission lifecycle policy
    stays out of runtime glue.
  - Moved the terminal `/status` local-command callback wrapper out of
    `tui/terminal_runtime.py` and into
    `status.card.TerminalStatusCardWriter`. Runtime now wires
    `status=self._status_card.run` into `TerminalLocalCommandDispatcher`
    instead of carrying a local lambda that calls
    `run_terminal_status_card_from_runtime(...)`. Added status-card owner
    coverage and extended the TUI alignment manifest/critical module guard to
    include `pycodex/tui/status/card.py`.
  - Moved the non-TTY fallback composer prompt literal out of
    `tui/terminal_runtime.py` and into
    `bottom_pane.chat_composer.run_terminal_composer_write_nonterminal_prompt(...)`.
    Runtime now delegates fallback prompt presentation to the chat-composer
    owner instead of carrying the `"\n› "` terminal UI string locally. Added
    chat-composer owner coverage and alignment guards to keep prompt
    presentation out of runtime glue.
  - Moved the protocol live-status hide callback policy out of
    `tui/terminal_runtime.py` and into
    `chatwidget.status_surfaces.TerminalStatusSurfaceWriter.hide_live_status()`.
    `TerminalProtocolEventDispatcher` now receives a status-owner method
    reference instead of a runtime lambda that calls
    `hide_inline_status(redraw_bottom_pane=True)`. Added status-surface owner
    coverage and alignment guards so live-status hide/clear redraw semantics
    stay with `chatwidget::status_surfaces`.
  - Moved bottom-pane no-resize clear/render callback packaging out of
    `tui/terminal_runtime.py` and into
    `TerminalBottomPaneController.clear_without_resize_check(...)` /
    `render_without_resize_check(...)`. Runtime collaborators now consume
    controller-owned callback boundaries instead of rebuilding
    `self._bottom_pane.clear/render(check_resize=False)` lambdas for
    history, resize, and composer flows. Added controller-owner coverage and
    alignment guards to keep the no-resize callback policy out of runtime.
  - Moved resize-replayed history insertion flag packaging out of
    `tui/terminal_runtime.py` and into
    `insert_history.TerminalHistoryWriter.insert_replayed_lines(...)`.
    `app.resize_reflow` still owns replay timing and active-bottom-pane
    reservation, while `insert_history` now owns the no-clear/no-render
    insertion helper. Added insert-history owner coverage and tightened the
    alignment guard so runtime cannot rebuild `clear_bottom_pane=False` /
    `render_bottom_pane=False` flag combinations for replayed rows.
  - Moved bottom-pane clear-cycle request packaging out of
    `bottom_pane/terminal_controller.py` and into
    `terminal_projection.TerminalBottomPaneRequestRunner.clear_callback(...)`.
    `TerminalBottomPaneController.clear(...)` now obtains a runner-owned clear
    callback and passes it to the `app.resize_reflow` footprint clear cycle
    instead of defining a local clear-request closure or calling
    `run_clear(...)` directly. Added projection-owner coverage for this clear
    callback boundary and tightened the alignment guard so direct clear-request
    invocation stays out of the controller. Focused checks passed (`59
    passed`), the broader TUI owner regression group passed (`1398 passed`),
    and deleted adapter searches for `scrollback_runtime`, `terminal_surface`,
    and `terminal_frame` found no runtime/test source files.
  - Moved terminal stdin TTY detection out of `tui/terminal_runtime.py` and
    into the Rust-aligned `tui/event_stream.py` owner via
    `terminal_stdin_is_terminal(...)`. `TerminalTuiRunner` now consumes the
    event-stream owner decision instead of directly probing `stdin.isatty()`.
    Added event-stream owner coverage for callable, false, missing, and broken
    `isatty` probes, updated the alignment guard to reject moving the probe
    back into runtime, and documented the responsibility in
    `tui_alignment.py`. Focused checks passed (`66 passed`), terminal runtime
    plus alignment checks passed (`98 passed`), and the broader TUI owner
    regression group passed (`1397 passed`). Deleted adapter searches for
    `scrollback_runtime`, `terminal_surface`, and `terminal_frame` found no
    runtime/test source files.
  - Moved the resize-reflow render-pass callback packaging out of
    `bottom_pane/terminal_controller.py` and into
    `terminal_projection.TerminalBottomPaneRequestRunner.render_pass_callback(...)`.
    The controller now obtains a runner-owned callback and passes it to
    `app.resize_reflow` instead of defining a local pass/context unpacking
    closure or calling `run_render_pass(...)` directly. Added projection-owner
    coverage for this callback boundary and tightened the alignment guard so
    request builders, render-pass protocols, and pass/context closure
    construction stay out of the controller. Focused checks passed (`58
    passed`), the broader TUI owner regression group passed (`1396 passed`),
    the alignment guard passed (`28 passed`), and deleted adapter searches for
    `scrollback_runtime`, `terminal_surface`, and `terminal_frame` found no
    runtime/test source files.
  - Removed the stale bottom-pane `SurfaceWriter` naming from the live terminal
    product path by renaming `TerminalBottomPaneSurfaceWriter` to
    `TerminalBottomPaneController`. This keeps `bottom_pane/terminal_controller.py`
    framed as runtime glue rather than a resurrected terminal surface owner.
    Updated terminal runtime wiring, controller tests, and alignment guard
    expectations to require the controller boundary while still rejecting the
    old surface-writer behavior-test names. Focused checks passed (`65
    passed`), the broader TUI owner regression group passed (`1395 passed`),
    the alignment guard passed (`28 passed`), and deleted adapter searches for
    `scrollback_runtime`, `terminal_surface`, and `terminal_frame` found no
    runtime/test source files.
  - Thinned `bottom_pane/terminal_controller.py` further by moving
    clear/render-pass request construction behind
    `terminal_projection.TerminalBottomPaneRequestRunner.run_clear(...)` and
    `run_render_pass(...)`. The controller no longer imports
    `TerminalBottomPaneRenderPassProtocol`,
    `TerminalBottomPaneRenderContextProtocol`,
    `terminal_bottom_pane_clear_request`, or
    `terminal_bottom_pane_render_request_for_pass`; it now only supplies
    terminal environment callbacks, bottom-pane owner state, and the
    resize/reflow render callback. `terminal_projection` remains the
    Python-only adapter that bridges bottom-pane requests to the
    `custom_terminal` live-viewport lifecycle, while `terminal_action` still
    owns the request builders. Focused checks passed (`57 passed`), the
    broader TUI owner regression group passed (`1395 passed`), and the
    alignment guard passed (`28 passed`).
  - Rehomed duplicate slash-popup and active-view behavior assertions out of
    `bottom_pane/tests/test_terminal_controller.py`. Tab completion, command
    popup navigation, and command-view opening are now guarded by the
    `bottom_pane::chat_composer` owner tests, while active-view navigation is
    guarded by `bottom_pane::BottomPane`/`view_stack` tests. Controller tests
    now stay focused on terminal glue: live-viewport external repaint, draft
    synchronization, cursor policy, active-view cursor hiding, and
    footprint/reflow callbacks. The product-path matrix and alignment guard now
    reject moving those owner behavior tests back into the controller layer.
    Focused checks passed (`91 passed`), the broader TUI owner regression group
    passed (`1394 passed`), and the alignment guard passed (`28 passed`).
  - Moved completed terminal prompt classification out of
    `tui/terminal_runtime.py` and into the Rust-aligned
    `chatwidget/slash_dispatch.py` owner via
    `run_terminal_prompt_dispatch(...)`. The runtime loop now consumes a typed
    prompt dispatch result (`skip`, `handled`, `exit`, or `submit`) instead of
    switching on blank input and local slash command return values itself.
    Added slash-dispatch owner tests for blank prompts, normal user prompt
    submission, local command handling, and exit handling; updated
    `tui_alignment.py` and the guard so this prompt/slash classification does
    not move back into the terminal runtime adapter. Focused checks passed
    (`78 passed`), the broader TUI owner regression group passed (`1398
    passed`), and the alignment guard passed (`28 passed`).
  - Moved completed terminal prompt dispatch callback packaging out of
    `tui/terminal_runtime.py` and into
    `chatwidget.slash_dispatch.TerminalPromptDispatcher`. Runtime now binds
    the local-command runner once and consumes
    `self._prompt_dispatch.dispatch(prompt)` in the loop instead of importing
    or directly calling `run_terminal_prompt_dispatch(...)`. Added
    slash-dispatch owner coverage and alignment guards so completed-prompt
    local command/user-turn classification remains with
    `codex-tui::chatwidget::slash_dispatch`.
  - Moved the remaining child-selection and CR-shaped Enter active-view
    behavior assertions out of `bottom_pane/tests/test_terminal_controller.py`
    and into `bottom_pane/tests/test_view_stack.py`, where the Rust
    `codex-tui::bottom_pane::BottomPane` owner contract lives. The controller
    test now stays focused on glue from `TerminalBottomPaneController` to
    the owner state/render lifecycle, while the alignment guard asserts the
    moved behavior stays with `view_stack`. Focused checks passed (`57
    passed`), the broader TUI owner regression group passed (`445 passed`),
    and the alignment guard passed (`28 passed`).
  - Deleted the temporary `bottom_pane/tests/test_terminal_bottom_pane_adapter.py`
    test module after moving its remaining coverage back to Rust-owner-aligned
    test files. `TerminalBottomPaneRequestRunner` coverage now lives with
    `bottom_pane/tests/test_terminal_projection.py`, bottom-pane writer/view
    glue coverage lives with `bottom_pane/tests/test_terminal_controller.py`,
    and live-status footprint/side-effect coverage lives with
    `chatwidget/tests/test_status_surfaces.py`. Updated `tui_alignment.py`
    and the alignment guard so this adapter test module, along with
    `scrollback_runtime.py`, `terminal_surface.py`, `terminal_frame.py`,
    `test_terminal_surface.py`, and `test_terminal_frame.py`, cannot return.
    Compile checks passed, the focused owner group passed (`103 passed`),
    the broader TUI owner regression group passed (`445 passed`), and the
    alignment guard passed (`28 passed`).
  - Renamed the stale `bottom_pane/tests/test_terminal_surface.py` test module
    to `bottom_pane/tests/test_terminal_bottom_pane_adapter.py` now that the
    `terminal_surface.py` runtime source is gone. Updated the alignment
    manifest and guard to use the adapter test path and to assert that
    `scrollback_runtime.py`, `terminal_surface.py`, `terminal_frame.py`,
    `test_terminal_surface.py`, and `test_terminal_frame.py` do not return.
    Also cleaned current Python test/source comments away from the old
    `terminal_surface` wording. Compile checks passed, the focused
    adapter/projection/controller/action/alignment group passed (`78 passed`),
    and the broader TUI owner regression group passed (`414 passed`).
  - Removed `bottom_pane/terminal_surface.py` as a runtime source file.
    `TerminalBottomPaneRequestRunner` now lives in
    `bottom_pane/terminal_projection.py`, beside the bottom-pane request to
    `custom_terminal` projection boundary it depends on. The controller imports
    the runner from `terminal_projection`, the alignment manifest no longer
    lists a separate terminal-surface adapter, and the guard now asserts that
    `terminal_surface.py` does not return. Compile checks passed, the focused
    projection/controller/alignment group passed (`71 passed`), and the broader
    TUI owner regression group passed (`407 passed`).
  - Added `custom_terminal.LiveViewportProjectionRequestRunner` and
    `create_live_viewport_projection_request_runner(...)` so generic
    request-to-projection lifecycle execution is owned by the Rust-aligned
    `codex-tui::custom_terminal` module. This first narrowed the old
    bottom-pane surface source to request-runner binding; the follow-up above
    then folded that binding into `terminal_projection.py` and deleted the
    surface source. The alignment guard rejects returning to a surface-local
    cycle runner. Focused compile/tests passed (`94 passed`), and the broader
    TUI owner regression group passed (`407 passed`).
  - Removed the remaining terminal-runtime history viewport repaint wrapper.
    `TerminalResizeCoordinator.repaint_history_viewport` and
    `TerminalAssistantStreamWriter.repaint_active_stream` now receive
    `TerminalResizeHistoryReplayer.repaint_viewport` directly, so retained
    history viewport repair and active-stream projection repaint stay under
    the Rust-aligned `codex-tui::app::resize_reflow` owner instead of a
    runtime helper. The alignment guard now rejects the wrapper returning.
    Focused compile/tests passed (`125 passed`), and the broader TUI owner
    regression group passed (`406 passed`).
  - Moved retained terminal history state assignment out of
    `tui/terminal_runtime.py` and into `insert_history.TerminalHistoryWriter`
    via `apply_state(...)`. Resize replay, assistant stream finalization, and
    `/clear` UI reset now delegate repaired history state storage to the
    Rust-aligned `codex-tui::insert_history` owner instead of a private
    runtime setter. The alignment guard now rejects
    `_apply_history_state(...)` returning to `terminal_runtime.py`. Focused
    compile/tests passed (`120 passed`), and the broader TUI owner regression
    group passed (`406 passed`).
  - Added `custom_terminal.live_viewport_requires_full_redraw(...)` so
    previous/current live-pane invalidation owns a Windows/ANSI hybrid
    compatibility rule: changed rows containing wide cells are cleared and
    redrawn as a full live-viewport repaint instead of emitted as isolated cell
    diffs. This keeps IME/wide-character prompt rendering under the
    Rust-aligned `codex-tui::custom_terminal` owner rather than leaking fixes
    into `event_stream`, `chat_composer`, or terminal surface adapters.
  - Strengthened custom-terminal and alignment tests around the wide-row
    redraw policy, including the prompt transition from `› 你` to `› 你好`.
    Focused input/runtime regressions passed (`107 passed`), bridge/custom
    terminal tests passed (`87 passed`), and the broader TUI owner regression
    group passed (`377 passed`).
  - Thinned `bottom_pane/terminal_controller.py` further by removing
    test-facing `active_view`, `view_stack`, `command_popup`, and
    `command_popup_visible` accessors plus the corresponding
    `BottomPaneView`/`CommandPopup` imports. Controller tests now observe
    slash-popup and active-view behavior through frame/render output, while
    `bottom_pane.view_stack` remains the owner for command-popup selection,
    active view navigation, and stack completion semantics.
  - Strengthened the alignment guard so `terminal_controller.py` cannot grow
    those low-level bottom-pane object exports back. The focused
    controller/surface/view-stack/alignment group passed (`83 passed`), and
    the broader TUI owner regression group passed (`377 passed`).
  - Tightened `TerminalBottomPaneSurfaceWriter` again so terminal callbacks and
    adapter dependencies (`writer`, TTY/layout probes, live status, footer,
    command-view callbacks, footprint repaint callback, and cursor policy) are
    private implementation details. Tests now keep their own writer handle and
    verify behavior through terminal output, while the alignment guard prevents
    those public dependency attributes from returning. The focused
    controller/surface/alignment group passed (`65 passed`), and the broader
    TUI owner regression group passed (`377 passed`).
  - Removed the `TerminalBottomPaneSurfaceWriter.draft` read-through property
    so the controller no longer exposes `view_stack` draft state as its own
    public state. `apply_draft(...)` remains the semantic test/render setup
    entrypoint, while `bottom_pane.view_stack` owns draft storage and render
    context projection. Focused controller/surface/alignment tests passed
    (`65 passed`), and the broader TUI owner regression group passed
    (`377 passed`).
  - Removed the `TerminalBottomPaneSurfaceWriter.show_selection_view(...)`
    proxy so active selection views cannot be opened by bypassing the shared
    slash command dispatch path. Terminal product tests now open active views
    through command dispatch and `open_command_view(command)` callbacks, while
    `bottom_pane.view_stack` remains the owner of view-stack mutation.
    Focused controller/surface/view-stack/alignment tests passed
    (`83 passed`), and the broader TUI owner regression group passed
    (`377 passed`).
  - Renamed the remaining controller draft mutation callback from
    `apply_draft(...)` to `sync_draft(...)` and wired
    `terminal_runtime.py`'s composer prompt loop to that narrower callback.
    `chat_composer` still receives an `apply_draft=` callback as its Rust-like
    prompt-loop contract, but the terminal controller now presents the action
    as synchronizing owner state rather than owning draft state itself.
    Focused controller/surface/runtime/alignment tests passed (`97 passed`),
    and the broader TUI owner regression group passed (`377 passed`).
  - Updated `tui_alignment.py` so the `terminal_controller.py` composer
    routing responsibility matches the current boundary: the controller
    synchronizes composer draft into `bottom_pane.view_stack` owner state, but
    does not expose draft state, create active views directly, or render
    terminal output. The alignment guard now checks this manifest wording.
    Standalone alignment passed (`25 passed`), focused
    controller/surface/runtime/alignment tests passed (`97 passed`), and the
    broader TUI owner regression group passed (`377 passed`).
  - Updated the `terminal_controller.py` footprint-reflow responsibility in
    `tui_alignment.py` so it no longer says the controller detects live-pane
    footprint changes. The manifest now records that the controller provides
    bottom-pane owner state, cursor callbacks, render callback, and external
    repaint runner to `app.resize_reflow`, while resize/reflow owns
    footprint-change detection, render-context acquisition, history viewport
    bounds, footprint timing, no-op detection, and external repaint dispatch.
    Alignment passed (`25 passed`), focused controller/surface/runtime/alignment
    tests passed (`97 passed`), and the broader TUI owner regression group
    passed (`377 passed`).
  - Added an alignment guard allowlist for
    `TerminalBottomPaneSurfaceWriter`'s public runtime-facing methods. The
    controller can expose only draft synchronization, composer key routing,
    history bottom-row lookup, clear/render lifecycle hooks, external repaint
    wrapping, and cursor restore; it cannot quietly grow public draft,
    active-view, slash-popup, or model-picker state proxies again. Standalone
    alignment passed (`25 passed`), focused controller/surface/runtime/alignment
    tests passed (`97 passed`), and the broader TUI owner regression group
    passed (`377 passed`).
  - Moved the terminal controller's command-view callback type boundary into
    `bottom_pane.view_stack` as `TerminalCommandViewFactory` and
    `TerminalSelectionEventHandler`. `terminal_controller.py` no longer imports
    `SelectionViewParams` directly or names a `/model`-specific view hook; it
    receives only view-stack owner callback types and delegates active-view
    transitions back to `view_stack`. The alignment manifest and guard now
    reject direct controller coupling to `SelectionViewParams`. Alignment
    passed (`25 passed`), and the focused
    view-stack/controller/surface/runtime/alignment group passed (`115 passed`);
    the broader TUI owner regression group passed (`377 passed`).
  - Generalized the terminal slash-command view-opening callback from the old
    model-specific hook to `open_command_view(command)`. `chat_composer` now
    emits an `open_command_view` action with the selected command name,
    `view_stack` owns the typed callback boundary, `terminal_controller.py`
    only wires that owner callback through, and `chatwidget.model_popups` owns
    the concrete `/model` view creation. This keeps terminal glue from growing
    a special `/model` branch while preserving the shared slash-command
    framework. Alignment passed (`25 passed`), focused
    chat-composer/view-stack/controller/surface/model-popup/runtime tests
    passed (`147 passed`), and the broader TUI owner regression group passed
    (`378 passed`).
  - Removed the remaining `/model` string decision from
    `bottom_pane.chat_composer`'s terminal popup action planner. Pressing Enter
    on any selected slash command now asks the shared
    `open_command_view(command)` boundary whether that command owns a
    bottom-pane view; commands without a view return `None` and fall through to
    normal slash/local-command submission. This mirrors the Rust split where
    `chat_composer` yields a command and `chatwidget::slash_dispatch` /
    command owners decide the effect. The alignment guard now rejects
    `command == "model"` in the composer owner. Focused
    chat-composer/view-stack/controller/surface/model-popup/runtime/alignment
    tests passed (`172 passed`), slash command/dispatch tests passed
    (`17 passed`), and the broader TUI owner regression group passed
    (`395 passed`).
  - Moved terminal slash-command view dispatch out of `model_popups` and into
    `chatwidget.slash_dispatch`. `TerminalSlashCommandViewDispatcher` now maps
    parsed slash commands to registered view-opening owners; runtime wires that
    dispatcher to bottom pane instead of passing `TerminalModelPopupController`
    methods directly. `model_popups` now owns only model/reasoning popup
    construction and selection-event interpretation. Alignment guards require
    runtime to use the slash-dispatch boundary and reject reintroducing
    `open_command_view(...)` on the model-popup owner. Focused
    slash-dispatch/model-popup/runtime/alignment tests passed (`83 passed`),
    and the broader TUI owner regression group passed (`395 passed`).
  - Moved terminal `/model` controller construction out of
    `terminal_runtime.py` and into `chatwidget.slash_dispatch`'s runtime
    factory. `terminal_runtime.py` now only wires
    `TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)` into the
    bottom-pane callbacks, while `chatwidget.model_popups` remains the
    concrete model/reasoning popup owner. The alignment guard now rejects
    runtime imports or state fields for `TerminalModelPopupController`.
    Focused slash-dispatch/runtime/alignment tests passed (`66 passed`), and
    the broader TUI owner regression group passed (`398 passed`).
  - Moved the stateful bottom-pane footprint lifecycle out of
    `terminal_controller.py` and into `app.resize_reflow` as
    `TerminalBottomPaneFootprintCycleRunner`. The controller no longer holds a
    raw `_footprint_tracker` or imports the low-level footprint clear/render
    cycle helpers; it now calls the resize/reflow-owned runner for clear and
    view-state render cycles. The runner also owns the terminal history bottom
    row calculation boundary, so the controller no longer imports
    `terminal_history_bottom_row_for_view_state(...)` directly. The manifest
    and alignment guard now require the runner boundary and reject tracker
    construction or direct history-bottom-row helper calls in the controller.
    Focused resize/controller/surface/alignment tests passed (`132 passed`),
    and the broader TUI owner regression group passed (`399 passed`).
  - Moved terminal-local slash command planning out of
    `tui/local_command.py` and into `chatwidget.slash_dispatch`. The terminal
    runtime now imports `TerminalLocalCommandDispatcher` from the
    slash-dispatch owner, while `/clear`, `/status`, `/quit`, and help
    planning live beside the other slash command categorization logic. The old
    `pycodex/tui/tui/local_command.py` and its `tui`-scoped tests were
    removed, with coverage migrated to `chatwidget/tests/test_slash_dispatch.py`.
    The alignment guard now rejects reintroducing the old `tui/local_command`
    owner shadow. Focused slash-dispatch/runtime/alignment tests passed
    (`73 passed`), and the broader TUI owner regression group passed
    (`406 passed`).
  - Rehomed terminal bottom-pane frame/buffer test evidence to the Rust owner
    layers instead of `bottom_pane/terminal_surface.py`. Popup row layout,
    frame clear rows, and ratatui-buffer content projection are now asserted
    in `chatwidget/tests/test_rendering.py`; bottom-pane frame-to-live-viewport
    diff behavior is asserted in `bottom_pane/tests/test_terminal_projection.py`.
    The alignment guard now rejects returning those owner-level frame
    projection contract tests to the terminal surface adapter. Focused
    rendering/projection/surface/alignment tests passed (`77 passed`), and the
    broader TUI owner regression group passed (`406 passed`).
  - Removed the remaining direct frame/projection helper tests from
    `bottom_pane/tests/test_terminal_surface.py`. Surface tests no longer
    import `terminal_bottom_pane_frame(...)`,
    `terminal_bottom_pane_frame_buffer(...)`,
    `terminal_bottom_pane_frame_live_viewport_update(...)`,
    `LiveViewportRenderer`, or `apply_live_viewport_update`; those contracts
    now live in `bottom_pane/tests/test_terminal_projection.py`. The alignment
    guard rejects reintroducing direct frame/projection/custom-terminal draw
    helpers into the surface test owner. Focused projection/surface/alignment
    tests passed (`68 passed`), and the broader TUI owner regression group
    passed (`406 passed`).
  - Moved terminal live-viewport request execution state out of
    `bottom_pane/terminal_controller.py` and into
    `bottom_pane/terminal_surface.py` as `TerminalBottomPaneRequestRunner`.
    The controller now calls a semantic request-runner boundary for terminal
    size, clear/render request execution, cursor restore, and external repaint
    lifecycle, while `custom_terminal.LiveViewportRenderer` remains the owner
    of previous/current buffer invalidation. The alignment guard now rejects
    direct controller imports of `create_live_viewport_renderer` or
    `run_terminal_bottom_pane_request`, and requires controller access through
    `_request_runner`. Focused controller/surface/alignment tests passed
    (`66 passed`), and the broader TUI owner regression group passed
    (`396 passed`).
  - Superseded the earlier projection-cycle runner boundary: the stateful
    cycle runner still lives in `custom_terminal`, but
    `bottom_pane/terminal_surface.py` no longer converts requests into cycles
    locally. It now supplies the bottom-pane projection callback to
    `custom_terminal.LiveViewportProjectionRequestRunner`, which owns the
    generic request lifecycle.
  - Removed the remaining public `run_terminal_bottom_pane_request(...)`
    compatibility entrypoint from `bottom_pane/terminal_surface.py`.
    Terminal surface callers now use only `TerminalBottomPaneRequestRunner`,
    which converts bottom-pane requests into owner-prepared projection cycles
    and delegates execution to the custom-terminal runner. Surface tests were
    updated to exercise the runner directly, and the alignment guard now
    rejects reintroducing the free function or exporting anything except the
    request-runner adapter. Focused surface/alignment tests passed
    (`63 passed`), and the broader TUI owner regression group passed
    (`397 passed`).
  - Added `custom_terminal.run_live_viewport_update_cycle` so resize-triggered
    frame invalidation, terminal-size lookup, and prepared live-viewport update
    application are owned by the Rust-aligned `codex-tui::custom_terminal`
    boundary.
  - Updated `bottom_pane/terminal_surface.py` to call that owner API instead
    of duplicating resize/size/apply sequencing for clear and render actions.
  - Added `custom_terminal.apply_live_viewport_update_with_cursor_move` so the
    optional compatibility cursor callback after a frame draw is also owned by
    the `custom_terminal` live-viewport boundary instead of being inspected in
    `terminal_surface.py`.
  - Added `custom_terminal.apply_live_viewport_projection` so
    `terminal_surface.py` no longer unpacks live-viewport projection
    `update` / `cursor_move` fields directly.
  - Added `custom_terminal.LiveViewportProjection` as the generic
    live-viewport projection envelope and removed the bottom-pane-specific
    `TerminalBottomPaneLiveViewportUpdate`; `terminal_projection.py` now
    returns the custom-terminal owner type instead of owning its own update
    wrapper.
  - Added `custom_terminal.sync_live_viewport_cursor_visibility` and moved the
    render-time cursor hide/show side effect out of
    `TerminalBottomPaneSurfaceWriter.render`; the controller now only computes
    the desired bottom-pane cursor policy.
  - Folded render-time cursor visibility synchronization into
    `custom_terminal.run_live_viewport_update_cycle`, so
    `terminal_surface.py` supplies the desired cursor policy to the
    custom-terminal lifecycle entrypoint instead of calling the cursor sync
    helper separately.
  - Added
    `bottom_pane.terminal_frame.terminal_bottom_pane_backend_cursor_position_enabled`
    and
    `terminal_bottom_pane_live_viewport_update_for_cursor_policy`, moving the
    backend-vs-compatibility cursor routing decision out of
    `terminal_surface.py` and into the Rust-aligned bottom-pane frame
    projection boundary.
  - Added `custom_terminal.run_live_viewport_projection_cycle` and updated
    `bottom_pane/terminal_surface.py` so the surface adapter no longer owns
    skip gating, resize/size/update sequencing, projection application,
    optional cursor movement, or flush policy; it now only creates the
    bottom-pane clear/render plan and projection factory consumed by the
    `custom_terminal` lifecycle owner.
  - Tightened `custom_terminal.run_live_viewport_update_cycle(...)` so the
    prepared update callback and lifecycle result are `bool` instead of
    arbitrary `Any`; the custom-terminal owner now reports only whether a live
    viewport update was applied, matching the terminal product path's draw
    lifecycle semantics.
  - Moved `TerminalBottomPaneFootprintTracker` and
    `TerminalBottomPaneFootprintReflowDecision` from
    `bottom_pane/terminal_frame.py` to `app/resize_reflow.py`, so grow/shrink
    repaint timing for active bottom-pane views is owned by the Rust-aligned
    `codex-tui::app::resize_reflow` boundary rather than the frame projection
    model.
  - Moved `TerminalBottomPaneFootprintTransition` and
    `bottom_pane_footprint_transition*` from `bottom_pane/terminal_frame.py`
    to `app/resize_reflow.py`; the frame module now supplies compact
    footprint values and row reservations, while resize/reflow owns transition
    comparison before retained-history repaint planning.
  - Moved the terminal history bottom-row calculation from
    `bottom_pane/terminal_frame.py` to `app/resize_reflow.py` as
    `terminal_history_bottom_row`; history insertion and resize/reflow now own
    the inline viewport boundary while the frame layer only supplies compact
    bottom-pane footprint values.
  - Added `app.resize_reflow.terminal_history_bottom_row_for_context(...)` and
    updated `bottom_pane/terminal_controller.py` to pass the
    bottom-pane-owned render context instead of reading popup height directly;
    the controller no longer owns the popup footprint input for history
    viewport bounds.
  - Added
    `app.resize_reflow.run_terminal_bottom_pane_footprint_external_repaint(...)`
    and updated `bottom_pane/terminal_controller.py` to delegate null-callback,
    no-op footprint, and external repaint wrapping decisions to the
    Rust-aligned resize/reflow owner.
  - Split compact bottom-pane footprint values out of
    `bottom_pane/terminal_frame.py` into
    `bottom_pane/terminal_footprint.py`; `terminal_frame.py` now consumes
    footprint rows through private projections while the new footprint module
    owns idle/status/popup row reservations and custom-terminal clear-request
    projection for the hybrid backend.
  - Split bottom-pane clear/render action planning and frame input state out of
    `bottom_pane/terminal_frame.py` into `bottom_pane/terminal_action.py`;
    `terminal_frame.py` now consumes prepared action/state objects while
    staying focused on Frame/Buffer content projection; the new
    `terminal_projection.py` adapter converts that frame output into
    `custom_terminal` live-viewport requests/updates.
  - Moved `TerminalBottomPaneCursorMove` and
    `terminal_bottom_pane_cursor_move(...)` from `terminal_frame.py` to
    `terminal_projection.py`, so the frame module no longer owns the
    terminal-specific compatibility cursor callback projection.
  - Moved `terminal_bottom_pane_frame_minimum_row_widths(...)`,
    `terminal_bottom_pane_frame_blank_rows(...)`, and
    `terminal_bottom_pane_frame_cursor_position(...)` from
    `bottom_pane/terminal_frame.py` to `bottom_pane/terminal_projection.py`;
    backend redraw metadata is now derived by the Python-only projection
    adapter instead of being owned by the side-effect-free Frame/Buffer content
    model.
  - Updated the TUI alignment manifest and guard tests so
    `bottom_pane/terminal_projection.py` explicitly owns custom-terminal
    backend metadata projection (minimum visible row widths, intentional blank
    rows, and zero-based ratatui cursor position) as part of its adapter
    responsibility; this prevents the metadata helpers from drifting back into
    `terminal_frame.py`.
  - Added a direct file-level TUI alignment entry for
    `pycodex/tui/chatwidget/rendering.py` against
    `codex-tui::chatwidget::rendering`, and promoted it into the critical
    terminal TUI module set. This gives the bottom-pane frame adapters a
    manifest-visible Rust owner for chatwidget render composition instead of
    relying only on package-level ownership.
  - Moved `TerminalBottomPaneFrame*` DTOs and
    `terminal_bottom_pane_frame_buffer(...)` from
    `bottom_pane/terminal_frame.py` to `chatwidget/rendering.py`, matching
    Rust `codex-tui::chatwidget::rendering` ownership of rendering content
    into a ratatui buffer. `terminal_frame.py` now assembles frame rows/writes
    only; buffer projection lives under the rendering owner, and alignment
    guards prevent the DTOs/projection from drifting back into the adapter.
  - Moved `terminal_bottom_pane_frame_projection(...)` out of
    `bottom_pane/terminal_frame.py` and into
    `bottom_pane/terminal_projection.py`; the frame module now exports only
    `terminal_bottom_pane_frame(...)`, while the projection adapter bridges the
    frame row/write owner with `chatwidget.rendering`'s buffer projection for
    `custom_terminal`.
  - Moved terminal popup row width clipping out of
    `bottom_pane/terminal_frame.py` into
    `bottom_pane/selection_popup_common.py` as
    `terminal_popup_line_for_width(...)`, matching Rust
    `codex-tui::bottom_pane::selection_popup_common` ownership of popup row
    width handling and selected-row presentation. `terminal_frame.py` now only
    places owner-prepared popup rows into frame writes.
  - Moved `terminal_bottom_pane_frame(...)` from
    `bottom_pane/terminal_frame.py` to `chatwidget/rendering.py`, so
    side-effect-free bottom-pane frame content generation sits with the
    Rust-aligned `codex-tui::chatwidget::rendering` owner, and
    `terminal_projection.py` consumes the chatwidget rendering owner directly.
  - Added `custom_terminal.create_live_viewport_renderer(...)` and
    `app.resize_reflow.create_terminal_bottom_pane_footprint_tracker(...)`;
    `bottom_pane/terminal_controller.py` now requests owner-managed live
    viewport and footprint tracker state instead of directly constructing
    custom-terminal or resize/reflow internals.
  - Migrated command-popup, terminal-surface, terminal-projection, and
    model-popup behavior tests to import `terminal_bottom_pane_frame(...)`
    from `chatwidget.rendering` directly.
  - Removed the obsolete `bottom_pane/terminal_frame.py` compatibility
    entrypoint and `bottom_pane/tests/test_terminal_frame.py`; frame
    construction proof now lives solely under `chatwidget.rendering`, and the
    alignment guard asserts the old path and imports stay absent.
  - Moved `custom_terminal.py`'s test-only helper assertions for buffer diff
    and cursor-style behavior into `tests/test_tui_custom_terminal.py`; the
    custom-terminal owner now exposes reusable terminal APIs only, while tests
    carry the Rust-derived assertions directly and alignment guards prevent
    those helper functions from returning to the product module.
  - Moved the remaining buffer-diff regression assertions out of
    `tests/test_tui_custom_terminal.py` and into
    `pycodex/tui/ratatui_bridge/tests/test_ratatui_bridge.py`; frame/buffer
    diff behavior is now tested at the minimal ratatui-like core boundary, and
    the alignment guard prevents `custom_terminal` tests from depending on the
    legacy local `Buffer` / `diff_buffers` model.
  - Updated `tests/test_tui_custom_terminal.py` writer-helper coverage to use a
    plain writer fixture instead of the legacy `CaptureBackend`, keeping that
    old backend fixture confined to the remaining legacy Terminal model tests
    while live-viewport helpers are verified through their actual writer
    contract.
  - Added `custom_terminal.set_cursor_style_ansi(...)` and
    `reset_cursor_style_ansi(...)` as direct writer-side cursor-style
    primitives mirroring Rust `custom_terminal::Terminal::{set_cursor_style,
    reset_cursor_style}`; cursor-style regression tests no longer instantiate
    the legacy local `Terminal/CaptureBackend` model.
  - Removed the legacy local `Terminal` / `CaptureBackend` / `Buffer` /
    `diff_buffers` test model from `custom_terminal.py`. The remaining
    viewport clear, visible-history row, and hard-clear cursor reset
    assertions now use small Rust-owner helpers under the
    `codex-tui::custom_terminal` boundary, while frame/buffer diff behavior
    remains owned and tested by `ratatui_bridge`.
  - Added `TerminalBottomPaneLayoutRows` and
    `terminal_bottom_pane_layout_rows(...)` under
    `bottom_pane/terminal_footprint.py`; concrete status/composer/popup/footer
    row assignment is now owned by the bottom-pane footprint/layout boundary.
    `terminal_frame.py` consumes those row assignments and only places
    owner-projected composer, popup, live-status, and footer text into the
    frame writes.
  - Tightened `bottom_pane/terminal_controller.py`'s owner wording and
    alignment guard: `TerminalBottomPaneSurfaceWriter` is now explicitly
    documented and tested as runtime glue that holds callbacks and owner state,
    while `view_stack`, `app.resize_reflow`, and `custom_terminal` own
    draft/popup/active-view semantics, footprint repaint decisions, and terminal
    side effects respectively.
  - Made `custom_terminal.LiveViewportRenderer`'s previous-buffer reset
    private (`_reset_buffer_state`) so terminal adapters cannot bypass the
    semantic `run_external_repaint(...)`, resize, clear, and render lifecycle
    entrypoints. Alignment guards now assert the public reset hook is absent.
  - Tightened `custom_terminal.LiveViewportBufferState` so `previous` is typed
    as a ratatui bridge `Buffer | None` and `update(...)` accepts a bridge
    `Buffer`, removing the last `Any` escape from the live-viewport
    previous/current buffer state wrapper.
  - Added an alignment guard that scans product TUI sources and rejects any
    reintroduced `textual`, `textual_runtime`, or `run_textual` marker. This
    keeps future TUI work on the Rust-aligned real-terminal framework instead
    of reviving a parallel Textual product path.
  - Added `TerminalBottomPaneFootprintRenderPass` and
    `TerminalBottomPaneFootprintTracker.render_with_reflow_passes(...)` in
    `pycodex/tui/app/resize_reflow.py`; resize reflow now owns the first
    render vs repaint-followup render pass parameters for bottom-pane
    footprint changes, so `terminal_controller.py` no longer duplicates the
    `render_after_repaint` sequencing or reaches into tracker state for
    `clear_popup_height` / `clear_live_status_active`.
  - Added
    `app.resize_reflow.run_terminal_bottom_pane_footprint_render_cycle(...)`;
    the controller now supplies the render callback, repaint callback, and
    external repaint lifecycle entrypoint to the resize-reflow owner instead of
    directly calling `TerminalBottomPaneFootprintTracker.render_with_reflow_passes(...)`
    or composing `_repaint_footprint(...)` itself.
  - Added
    `app.resize_reflow.run_terminal_bottom_pane_footprint_clear_cycle(...)`;
    `TerminalBottomPaneSurfaceWriter.clear()` now supplies the concrete clear
    callback to the resize-reflow owner instead of directly calling
    `clear_after_surface_clear()` on the footprint tracker.
  - Added `terminal_bottom_pane_popup_projection_for_size(...)` in
    `pycodex/tui/bottom_pane/view_stack.py`; bottom-pane now owns the terminal
    geometry to popup-row width mapping for command popup and active view
    rows, while `terminal_controller.py` only supplies the observed terminal
    size.
  - Added `TerminalBottomPaneSurfaceWriter.run_external_repaint(...)` as the
    runtime-facing lifecycle entrypoint for external terminal writes. History
    scrollback replay now goes through the `custom_terminal`
    `LiveViewportRenderer.run_external_repaint(...)` owner boundary instead of
    letting `terminal_runtime.py` call `reset_buffer_state()` directly.
  - Removed the raw `TerminalBottomPaneSurfaceWriter.reset_buffer_state()`
    escape hatch and moved replay-plan wrapping into
    `app.resize_reflow.TerminalResizeCoordinator`; the terminal runtime now
    supplies `replay_scrollback` and `run_external_repaint` callbacks without
    owning the composition.
  - Moved bottom-pane clear/render flush policy into
    `bottom_pane.terminal_action.TerminalBottomPaneActionPlan`; the terminal
    surface adapter now passes only the prepared action plan into the
    custom-terminal projection cycle instead of deciding `flush=True` itself.
  - Added `TerminalBottomPaneClearRequest` and
    `TerminalBottomPaneRenderRequest` in `bottom_pane.terminal_action`;
    `terminal_surface.py` now consumes those owner-prepared requests instead
    of accepting scattered `draft`, `footer_text`, `popup_lines`, and
    `live_status` semantic arguments or importing action-plan builders
    directly.
  - Added `terminal_bottom_pane_clear_request(...)` and
    `terminal_bottom_pane_render_request(...)` in
    `bottom_pane.terminal_action`; `terminal_controller.py` now passes the
    bottom-pane-owned render context to those helpers instead of directly
    unpacking `draft`, `popup_lines`, or `cursor_visible` into terminal-surface
    request constructors.
  - Added `terminal_bottom_pane_render_request_for_pass(...)` in
    `bottom_pane.terminal_action`; `terminal_controller.py` now passes the
    resize-owned render-pass object through that owner helper instead of
    unpacking `pass_state.check_resize`, `clear_popup_height`, or
    `clear_live_status_active` itself.
  - Tightened the terminal render-request builders in
    `bottom_pane.terminal_action` to consume explicit render-context and
    render-pass protocols instead of `Any` plus `getattr(...)` fallbacks; the
    request owner now directly reads the bottom-pane draft/popup/cursor fields
    and resize-owned pass fields.
  - Added
    `app.resize_reflow.run_terminal_bottom_pane_footprint_render_cycle_for_context(...)`;
    `terminal_controller.py` now passes the bottom-pane render context through
    the resize/reflow owner instead of reading `render_context.popup_height` or
    `render_context.popup_is_active_view` for footprint repaint decisions.
  - Tightened the resize/reflow bottom-pane context boundary with explicit
    `TerminalBottomPanePopupHeightContextProtocol` and
    `TerminalBottomPaneFootprintContextProtocol`; resize/reflow now reads
    `popup_height` and `popup_is_active_view` directly instead of using
    `getattr(bottom_pane_context, ...)` fallbacks.
  - Moved `truncate_display_width(...)` from
    `bottom_pane/terminal_frame.py` into `custom_terminal.py`; the bottom-pane
    frame model now consumes the custom-terminal display-width owner instead of
    exporting its own low-level terminal truncation helper.
  - Moved `status_row(...)`, `composer_row(...)`, and `footer_row(...)` from
    `bottom_pane/terminal_frame.py` into `bottom_pane/terminal_footprint.py`;
    the frame model now consumes the footprint owner for standard live-pane row
    reservations instead of defining row policy itself.
  - Added
    `bottom_pane.terminal_footprint.TerminalLiveStatusFootprintProtocol` and
    updated `TerminalBottomPaneFootprint.from_surface(...)` to consume the
    typed `footprint_active` status-surface contract directly instead of
    probing `live_status` with `Any` / `getattr(...)`.
  - Added `custom_terminal.live_viewport_buffer_area_for_rows(...)`;
    `terminal_frame.py` now asks the custom-terminal owner for the ratatui
    buffer area covering live-viewport rows instead of computing top/bottom
    row geometry locally.
  - Added `custom_terminal.live_viewport_minimum_row_widths_for_writes(...)`,
    `live_viewport_blank_rows(...)`, and `live_viewport_cursor_position(...)`;
    `terminal_projection.py` now delegates backend redraw metadata and
    zero-based cursor conversion to the custom-terminal owner instead of
    expanding those calculations locally.
  - Tightened those live-viewport metadata helpers with an explicit
    `LiveViewportWriteProtocol`; row-width and blank-row calculations now read
    structured `row` / `column` / `text` fields directly instead of accepting
    dict-like writes through a generic `_field(...)` fallback.
  - Removed the bottom-pane projection wrapper helpers for frame row widths,
    blank rows, and cursor position; `terminal_projection.py` now calls the
    custom-terminal metadata helpers directly when building
    `LiveViewportRenderRequest`, leaving no projection-level public API for
    those custom-terminal-owned calculations.
  - Added `custom_terminal.LiveViewportRenderRequest.from_writes(...)`;
    `terminal_projection.py` now passes frame writes, cursor coordinates, and
    blank-row policy into the custom-terminal owner instead of composing row
    widths, blank rows, and ratatui cursor positions across multiple helper
    calls inside the projection adapter.
  - Added
    `bottom_pane.terminal_projection.terminal_bottom_pane_request_live_viewport_update(...)`;
    `terminal_surface.py` now passes owner-prepared clear/render requests to
    that projection bridge instead of unpacking request cleanup fields such as
    `clear_popup_height`, `clear_live_status_active`, or
    `clear_external_blank_rows`.
  - Added
    `bottom_pane.terminal_projection.TerminalBottomPaneProjectionCycle` and
    `terminal_bottom_pane_live_viewport_projection_cycle(...)`; the projection
    owner now packages request gating, resize checks, cursor visibility, and
    the projection callback for `custom_terminal.run_live_viewport_projection_cycle`.
    `terminal_surface.py` no longer calls `request.action_plan()` or reads
    `request.cursor_visible` directly.
  - Added `bottom_pane.terminal_action.TerminalBottomPaneProjectionCleanup`
    and request-level `projection_cleanup(...)` helpers; the projection adapter
    now consumes owner-prepared cleanup metadata instead of inspecting
    clear/render request fields with `getattr(request, ...)`.
  - Added an explicit `ProjectionCleanupShape` protocol in
    `bottom_pane.terminal_projection`; the adapter still avoids importing the
    concrete bottom-pane cleanup dataclass, but it no longer accepts an
    unshaped `cleanup=None` parameter for prepared cleanup metadata.
  - Added request-level `projection_cursor_visible(...)` helpers in
    `bottom_pane.terminal_action`; `terminal_projection.py` now consumes the
    owner-provided cursor policy instead of checking the request type and
    reading `request.cursor_visible` directly.
  - Added `custom_terminal.LiveViewportProjectionCycle` and updated
    `bottom_pane.terminal_projection` to return that generic custom-terminal
    lifecycle object instead of defining a bottom-pane-specific
    `TerminalBottomPaneProjectionCycle`.
  - Shrank `bottom_pane.terminal_projection.__all__` to the runtime-facing
    `terminal_bottom_pane_live_viewport_projection_cycle(...)` entrypoint; the
    lower-level request/update helpers remain owner-test anchors but are no
    longer advertised as the adapter public surface.
  - Collapsed `bottom_pane/terminal_surface.py`'s public clear/render entry
    points into `run_terminal_bottom_pane_request(...)`; the surface adapter
    now accepts only owner-prepared bottom-pane requests and forwards their
    projection cycle through the custom-terminal live-viewport lifecycle.
    `terminal_controller.py` uses the same request runner for clear and render
    paths.
  - Added `bottom_pane.terminal_action.TerminalBottomPaneRequest` as the
    owner-defined request boundary for clear/render requests; terminal surface
    and projection adapters now consume that alias instead of spelling out the
    clear/render union themselves.
  - Tightened bottom-pane popup row typing around
    `selection_popup_common.TerminalPopupLine`; `view_stack` render context,
    popup projection, popup-lines helper, and chat-composer popup state now
    expose typed terminal popup rows instead of `Any` payloads.
  - Added `bottom_pane.view_stack.TerminalCommandPopupStateProtocol`; the
    view-stack owner now consumes command-popup visibility, row projection,
    draft sync, and hide behavior through a typed protocol instead of
    `getattr(command_popup_state, ...)` fallback probing. The alignment guard
    now prevents this cross-owner command-popup boundary from regressing back
    into reflection-based adapter logic.
  - Extended the Python `bottom_pane_view.BottomPaneView` protocol/defaults
    with the terminal-row projection used by the hybrid live-pane path, then
    updated `bottom_pane/view_stack.py` to call BottomPaneView trait helpers
    for terminal rows, completion, child-dismissal, and cancellation cleanup
    instead of `getattr(view, ...)` probing.
  - Routed active-view key handling through the same `BottomPaneView`
    contract: `ListSelectionView` now implements `handle_key_event(...)`,
    and `BottomPaneViewStack.handle_active_key(...)` calls the
    bottom-pane-view trait helper instead of importing the
    list-selection-specific key handler.
  - Superseded the earlier terminal-runtime history-viewport repaint callback
    tightening: runtime no longer keeps its own repaint forwarding helper and
    now wires directly to `TerminalResizeHistoryReplayer.repaint_viewport(...)`.
  - Added `tui.event_stream.TerminalTurnEventStreamProtocol` and updated
    `terminal_runtime.py` to consume that protocol in `_consume_events(...)`;
    submitted-turn event/idle/closed stream shape now belongs to the
    Rust-aligned `codex-tui::tui::event_stream` boundary instead of being
    accepted as an arbitrary `Any` object by the terminal runner.
  - Tightened the terminal turn-start history append boundary:
    `chatwidget.turn_runtime.run_terminal_turn_start(...)` and
    `run_terminal_turn_submission(...)` now accept an optional typed
    `Callable[[str], Any]` history callback, and `terminal_runtime.py` passes
    `TuiAppRuntime.append_message_history_entry` directly instead of probing
    the app runtime with `getattr(...)`.
  - Tightened `terminal_runtime.py` state-sink glue: history-state callbacks now
    pass through `_apply_history_state(...)`, and turn-submission exit-code
    updates pass through `_set_exit_code(...)` instead of anonymous
    `setattr(...)` lambdas. This keeps the runner's app/history mutation
    boundary explicit while preserving its event-loop/glue role.
  - Tightened the terminal controller's test-visible bottom-pane state
    boundary: `TerminalBottomPaneSurfaceWriter.active_view`,
    `view_stack`, and `command_popup` now expose `BottomPaneView` and
    `CommandPopup` owner types instead of `Any`, with the corresponding
    `TerminalBottomPaneViewState.command_popup` property typed at the
    bottom-pane owner layer.
  - Tightened selection action event plumbing so `view_stack` and
    `terminal_controller.py` carry selection events as opaque `object` values,
    while `chatwidget.model_popups` owns filtering and interpreting
    `ModelPopupEvent` actions. This keeps model-popup event semantics out of
    the terminal adapter without over-specializing generic selection views.
  - Tightened active-view completion plumbing so `ListSelectionView` now
    reports `ViewCompletion.ACCEPTED` / `ViewCompletion.CANCELLED` directly,
    matching Rust `bottom_pane_view.rs` and `list_selection_view.rs`, and
    `view_stack` no longer normalizes `"Submitted"` / string aliases when
    applying `BottomPane::pop_active_view_with_completion` rules.
  - Tightened `bottom_pane/terminal_controller.py` so its render callback now
    consumes the resize/reflow-owned
    `TerminalBottomPaneFootprintRenderPass` type directly instead of treating
    the pass as `Any`; the alignment guard now prevents the controller from
    weakening this app-resize owner boundary.
  - Added `custom_terminal.LiveViewportCursorMove`; bottom-pane projection now
    returns that generic custom-terminal cursor target instead of defining a
    bottom-pane-specific `TerminalBottomPaneCursorMove`.
  - Tightened live-viewport cursor movement so `LiveViewportProjection` and
    `apply_live_viewport_cursor_move(...)` consume `LiveViewportCursorMove`
    directly; tuple/dict cursor target compatibility and the
    `_coerce_live_viewport_cursor_move(...)` fallback were removed.
  - Added `custom_terminal.LiveViewportCursorMoveCallback` and updated
    cursor-move consumers to accept that protocol instead of
    `Callable[[int, int], Any]`; compatibility cursor movement is now a typed
    custom-terminal side-effect boundary rather than an arbitrary callback
    shape.
  - Added `custom_terminal.run_prepared_live_viewport_projection_cycle(...)`;
    the custom-terminal owner now unpacks prepared projection-cycle objects
    before running the live viewport lifecycle. `terminal_surface.py` now
    passes the cycle object directly instead of reading `cycle.should_run`,
    `cycle.check_resize`, `cycle.cursor_visible`, or `cycle.project`.
  - Tightened `run_prepared_live_viewport_projection_cycle(...)` to consume
    the typed `LiveViewportProjectionCycle` contract directly instead of
    using `getattr(cycle, ...)` compatibility probing; the alignment guard now
    rejects reintroducing reflection-based cycle unpacking.
  - Added `custom_terminal.LiveViewportProjectionPolicy`; the custom-terminal
    projection cycle now owns whether an external compatibility cursor callback
    is present, and `terminal_surface.py` consumes that policy instead of
    computing `move_cursor is not None`.
  - Updated `bottom_pane.terminal_projection` to consume the
    `LiveViewportProjectionPolicy` object directly; `terminal_surface.py` now
    forwards the policy whole and no longer reads cursor-policy fields.
  - Removed the thin
    `bottom_pane.terminal_projection.terminal_bottom_pane_backend_cursor_position_enabled(...)`
    wrapper; projection now calls
    `custom_terminal.live_viewport_backend_cursor_position_enabled(...)`
    directly when building the live-viewport update, leaving the cursor policy
    helper owned only by `custom_terminal`.
  - Tightened
    `bottom_pane.terminal_projection.terminal_bottom_pane_request_live_viewport_update(...)`
    so its public entrypoint no longer accepts adapter-level `plan` or
    `cleanup` overrides; owner metadata is now read from
    `TerminalBottomPaneRequest`, with precomputed values used only inside the
    private helper and prepared projection cycle.
  - Tightened `custom_terminal.LiveViewportProjectionCycle.project` and
    `run_live_viewport_projection_cycle(...)` so projection callbacks return
    `LiveViewportProjection | None` instead of `Any | None`; the
    custom-terminal lifecycle now owns a typed projection result all the way
    through the live-viewport draw path.
  - Tightened `custom_terminal.terminal_size(...)` so terminal sizing returns
    `os.terminal_size` instead of `Any`; the custom-terminal owner now exposes
    the same concrete size shape consumed by live-viewport draw, layout, and
    resize callbacks.
  - Tightened the custom-terminal live-viewport resize lifecycle so resize
    callbacks are `Callable[[], None]` instead of `Callable[[], Any]`; terminal
    resize is now explicitly a side-effect boundary rather than an arbitrary
    adapter return channel.
  - Added the typed `app.resize_reflow.TerminalExternalRepaintRunner` boundary
    and updated custom-terminal/controller external repaint wrappers to preserve
    callback result types through a `TypeVar` instead of exposing raw `Any`.
    Resize replay now calls `_run_replay_history_scrollback() -> None`, matching
    the replay-plan callback contract.
  - Tightened `app.resize_reflow.TerminalResizeCoordinator.current_size` to
    `Callable[[], os.terminal_size]`, matching the real terminal product path
    where `terminal_runtime.py` supplies `custom_terminal.terminal_size(...)`
    as the observed size source.
  - Tightened `app.resize_reflow` terminal size-change runtime state and
    planning APIs so `TerminalSizeChangeReflowPlan.last_terminal_size`,
    `TerminalResizeRuntimeState.last_terminal_size`,
    `plan_terminal_size_change_reflow(...)`,
    `run_terminal_layout_activation(...)`, and
    `run_terminal_size_change_reflow(...)` use `os.terminal_size` instead of
    accepting arbitrary size payloads.
  - Tightened `app.resize_reflow` bottom-pane footprint and history viewport
    size boundaries so footprint transitions, footprint render cycles,
    bottom-pane footprint reflow planning, and
    `terminal_history_bottom_row*` helpers consume `os.terminal_size` instead
    of arbitrary objects.
  - Added
    `bottom_pane.view_stack.terminal_bottom_pane_handle_composer_key(...)` so
    active-view-first key routing and slash-popup fallback now live behind the
    Rust-aligned `codex-tui::bottom_pane` owner boundary; the terminal
    controller no longer imports `terminal_bottom_pane_active_view_input` or
    `run_terminal_command_popup_input_action` directly.
  - Added `bottom_pane.view_stack.TerminalBottomPaneViewState`, which now owns
    the terminal product path's combined draft, command-popup state, active
    view stack, and selection-event queue. `terminal_controller.py` holds that
    owner object instead of independently composing `_view_stack`,
    `_command_popup_state`, and `selection_events`.
  - Added `bottom_pane.view_stack.TerminalBottomPaneRenderContext`; bottom-pane
    view state now projects draft text, popup rows/footprint source, and
    composer cursor visibility as one owner-produced render context. The
    terminal controller no longer separately queries popup projection and
    cursor policy before rendering.
  - Moved the terminal selected-popup-row style decision from
    `bottom_pane/terminal_frame.py` into
    `bottom_pane/selection_popup_common.py`, so the side-effect-free frame
    projection consumes the selection-popup owner helper instead of hardcoding
    the highlight style itself.
  - Removed the `composer_line_text` / `composer_cursor_column` facade exports
    from `bottom_pane/terminal_frame.py`; tests now consume
    `bottom_pane.chat_composer.terminal_composer_line_text(...)` directly, so
    composer text/cursor projection remains anchored to the Rust-aligned
    `codex-tui::bottom_pane::chat_composer` owner.
  - Updated the native comparison harness to resolve Windows Store Python
    app-execution aliases to the packaged interpreter before spawning child
    processes, so the `TERM=dumb` startup guard test exercises the TUI
    contract rather than failing in `CreateProcess`.
  - Updated the alignment guard so `terminal_surface.py` imports the lifecycle
    owner APIs and no longer imports `check_live_viewport_resize`,
    `apply_live_viewport_update`, or
    `apply_live_viewport_update_with_cursor_move` directly; the guard also
    prevents the controller from calling `LiveViewportRenderer`
    `sync_cursor_visibility` directly, prevents surface from importing the
    lower-level cursor sync helper, and prevents surface from owning the
    backend cursor-position policy expression or direct live-viewport update
    cycle/application APIs.
  - Verification: focused terminal action, footprint, frame, surface, and TUI
    alignment tests passed with `67 passed`; focused custom terminal,
    projection, frame, surface, and alignment tests passed with `98 passed`;
    focused custom terminal, bottom-pane projection/frame/surface/controller,
    terminal runtime, and TUI alignment tests passed with `133 passed`;
    focused resize reflow, controller, surface, and alignment tests passed with
    `114 passed`; focused custom terminal, insert history, resize reflow,
    terminal action, footprint, projection, frame, surface, controller, command
    popup, model popup, terminal runtime, and TUI alignment tests passed with
    `283 passed`; focused view-stack, terminal controller, and alignment tests
    passed with `33 passed`; focused view-stack, command popup, terminal
    controller, terminal surface, terminal runtime, and alignment tests passed
    with `111 passed`;
    focused custom terminal, insert history, resize reflow, terminal action,
    footprint, projection, frame, surface, controller, command popup, model
    popup, and TUI alignment tests passed with `250 passed`;
    focused terminal controller, terminal surface, terminal runtime, custom
    terminal, and TUI alignment tests passed with `125 passed`;
    focused resize reflow, terminal controller, terminal runtime, and TUI
    alignment tests passed with `110 passed`;
    focused resize reflow, terminal controller, terminal surface, terminal
    runtime, custom terminal, and TUI alignment tests passed with `183 passed`;
    focused terminal action, projection, surface, and TUI alignment tests
    passed with `58 passed`;
    focused resize reflow, terminal action, projection, frame, surface,
    controller, terminal runtime, custom terminal, and TUI alignment tests
    passed with `194 passed`;
    focused custom terminal, terminal surface, and TUI alignment tests passed
    with `89 passed`;
    focused terminal projection, terminal surface, and TUI alignment tests
    passed with `56 passed`;
    focused view-stack, terminal controller, and TUI alignment tests passed
    with `34 passed`;
    focused view-stack, chat-composer, command-popup, terminal controller,
    terminal surface, terminal runtime, custom terminal, and TUI alignment
    tests passed with `186 passed`;
    focused view-stack, terminal controller, and TUI alignment tests passed
    with `35 passed`;
    focused view-stack, chat-composer, command-popup, terminal controller,
    terminal surface, terminal runtime, custom terminal, and TUI alignment
    tests passed with `187 passed`;
    targeted renderable crash-stack reruns passed with `1 passed` and
    `15 passed` after one transient Windows access violation during a full
    suite attempt;
    focused view-stack, terminal controller, and TUI alignment tests passed
    with `35 passed`;
    focused view-stack, chat-composer, command-popup, terminal controller,
    terminal surface, terminal runtime, custom terminal, and TUI alignment
    tests passed with `187 passed`;
    broader `pycodex/tui` regression passed with `2243 passed, 59 skipped`;
    focused terminal frame/projection/alignment tests passed with `25 passed`;
    adjacent resize reflow, terminal frame/projection/surface/controller,
    terminal runtime, custom terminal, and TUI alignment tests passed with
    `193 passed`;
    broader `pycodex/tui` regression passed with `2244 passed, 59 skipped`;
    focused terminal projection/alignment guard tests passed with `22 passed`;
    adjacent resize reflow, terminal frame/projection/surface/controller,
    terminal runtime, custom terminal, and TUI alignment tests passed with
    `194 passed`;
    focused chatwidget rendering/alignment tests passed with `22 passed`;
    adjacent chatwidget rendering, resize reflow, terminal
    frame/projection/surface/controller, terminal runtime, custom terminal, and
    TUI alignment tests passed with `199 passed`;
    focused terminal controller/alignment tests passed with `20 passed`;
    adjacent resize reflow, view-stack, terminal controller/surface/runtime,
    custom terminal, and TUI alignment tests passed with `201 passed`;
    focused custom terminal/alignment tests passed with `53 passed`;
    adjacent resize reflow, terminal controller/surface/runtime, custom
    terminal, and TUI alignment tests passed with `185 passed`;
    focused TUI alignment, custom terminal, and terminal runtime tests passed
    with `86 passed`;
    adjacent resize reflow, view-stack, chat-composer, command-popup, terminal
    controller/projection/surface/runtime, custom terminal, and TUI alignment
    tests passed with `254 passed`;
    focused resize reflow, terminal controller, and TUI alignment tests passed
    with `82 passed`;
    adjacent resize reflow, view-stack, chat-composer, command-popup, terminal
    controller/projection/surface/runtime, custom terminal, and TUI alignment
    tests passed with `255 passed`;
    focused resize reflow, terminal controller, and TUI alignment tests passed
    with `83 passed`;
    adjacent resize reflow, view-stack, chat-composer, command-popup, terminal
    controller/projection/surface/runtime, custom terminal, and TUI alignment
    tests passed with `256 passed`;
    focused terminal action, terminal surface, terminal controller, and TUI
    alignment tests passed with `61 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal controller/projection/surface/runtime, custom
    terminal, and TUI alignment tests passed with `259 passed`;
    focused terminal action, terminal controller, terminal surface, and TUI
    alignment tests passed with `62 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal controller/projection/surface/runtime, custom
    terminal, and TUI alignment tests passed with `260 passed`;
    standalone TUI alignment guard passed with `18 passed`;
    focused terminal projection, terminal surface, and TUI alignment tests
    passed with `61 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal controller/projection/surface/runtime, custom
    terminal, and TUI alignment tests passed with `261 passed`;
    standalone TUI alignment guard passed with `18 passed`;
    focused terminal projection, terminal surface, and TUI alignment tests
    passed with `62 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal controller/projection/surface/runtime, custom
    terminal, and TUI alignment tests passed with `262 passed`;
    standalone TUI alignment guard passed with `18 passed`;
    focused custom terminal, terminal surface, and TUI alignment tests passed
    with `92 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal controller/projection/surface/runtime, custom
    terminal, and TUI alignment tests passed with `263 passed`;
    focused terminal action, terminal controller, and TUI alignment tests
    passed with `26 passed`;
    focused resize reflow, terminal controller, and TUI alignment tests passed
    with `84 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal controller/projection/surface/runtime, custom
    terminal, and TUI alignment tests passed with `264 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal controller/projection/surface/runtime, custom
    terminal, and TUI alignment tests passed with `265 passed`;
    focused custom terminal, terminal frame, and TUI alignment tests passed
    with `60 passed`;
    adjacent resize reflow, terminal action, view-stack, chat-composer,
    command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `270 passed`;
    focused terminal footprint, terminal frame, and TUI alignment tests passed
    with `26 passed`;
    adjacent resize reflow, terminal action, terminal footprint, view-stack,
    chat-composer, command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `274 passed`;
    focused custom terminal, terminal frame, and TUI alignment tests passed
    with `61 passed`;
    adjacent resize reflow, terminal action, terminal footprint, view-stack,
    chat-composer, command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `275 passed`;
    focused custom terminal, terminal projection, and TUI alignment tests passed
    with `65 passed`;
    adjacent resize reflow, terminal action, terminal footprint, view-stack,
    chat-composer, command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `276 passed`;
    focused terminal action, terminal projection, and TUI alignment tests passed
    with `30 passed`;
    adjacent resize reflow, terminal action, terminal footprint, view-stack,
    chat-composer, command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `276 passed`;
    focused terminal action, terminal projection, and TUI alignment tests passed
    with `30 passed`;
    adjacent resize reflow, terminal action, terminal footprint, view-stack,
    chat-composer, command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `276 passed`;
    focused custom terminal, terminal projection, and TUI alignment tests passed
    with `65 passed`;
    adjacent resize reflow, terminal action, terminal footprint, view-stack,
    chat-composer, command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `276 passed`;
    focused custom terminal, terminal projection, and TUI alignment tests passed
    with `65 passed`;
    adjacent resize reflow, terminal action, terminal footprint, view-stack,
    chat-composer, command-popup, terminal frame/controller/projection/surface/runtime,
    custom terminal, and TUI alignment tests passed with `276 passed`;
    focused view-stack, chat-composer, and TUI alignment tests passed with
    `74 passed`; adjacent resize reflow, terminal action/footprint,
    view-stack, chat-composer, command-popup, terminal
    frame/controller/projection/surface/runtime, custom terminal, and TUI
    alignment tests passed with `279 passed`;
    focused bottom-pane-view, view-stack, and TUI alignment tests passed with
    `43 passed`; adjacent resize reflow, bottom-pane-view, terminal
    action/footprint, view-stack, chat-composer, command-popup, terminal
    frame/controller/projection/surface/runtime, custom terminal, and TUI
    alignment tests passed with `286 passed`;
    focused bottom-pane-view, list-selection-view, view-stack, and TUI
    alignment tests passed with `53 passed`; adjacent resize reflow,
    bottom-pane-view, list-selection-view, terminal action/footprint,
    view-stack, chat-composer, command-popup, terminal
    frame/controller/projection/surface/runtime, custom terminal, and TUI
    alignment tests passed with `296 passed`;
    focused terminal runtime, resize reflow, and TUI alignment tests passed
    with `116 passed`; the same adjacent TUI regression group passed with
    `296 passed`;
    focused terminal controller, resize reflow, and TUI alignment tests passed
    with `86 passed`; the same adjacent TUI regression group passed with
    `279 passed`;
    standalone TUI alignment guard passed with `21 passed`;
    focused custom terminal, terminal projection/surface, and TUI alignment
    tests passed with `108 passed`; adjacent resize reflow, bottom-pane-view,
    list-selection-view, terminal action/footprint, view-stack, chat-composer,
    command-popup, terminal frame/controller/projection/surface/runtime,
    chatwidget model/turn runtime, custom terminal, and TUI alignment tests
    passed with `373 passed`; standalone TUI alignment guard passed with
    `24 passed`;
    focused terminal footprint and TUI alignment tests passed with `28 passed`;
    adjacent resize reflow, terminal footprint/frame/action/projection/surface/controller,
    view-stack, chatwidget model/turn runtime, terminal event/runtime, custom
    terminal, and TUI alignment tests passed with `311 passed`;
    focused terminal runtime and TUI alignment tests passed with `56 passed`;
    adjacent event stream, terminal runtime, turn runtime, history messages,
    resize reflow, terminal controller/surface/projection, custom terminal, and
    TUI alignment tests passed with `287 passed`;
    focused custom terminal and TUI alignment tests passed with `65 passed`;
    adjacent custom terminal, terminal projection/surface/controller/runtime,
    resize reflow, and TUI alignment tests passed with `206 passed`;
    focused custom terminal and TUI alignment tests passed with `65 passed`;
    adjacent custom terminal, terminal projection/surface/controller/runtime,
    resize reflow, and TUI alignment tests passed with `206 passed`;
    focused custom terminal and TUI alignment tests passed with `65 passed`;
    adjacent custom terminal, terminal projection/surface/controller/runtime,
    resize reflow, and TUI alignment tests passed with `206 passed`;
    terminal-size contract guard re-validated with focused custom terminal and
    TUI alignment tests at `65 passed`, plus the same adjacent TUI regression
    group at `206 passed`;
    live-viewport resize callback contract re-validated with focused custom
    terminal and TUI alignment tests at `65 passed`, plus the same adjacent TUI
    regression group at `206 passed`;
    external repaint runner typing re-validated with focused custom terminal,
    resize reflow, terminal controller, and TUI alignment tests at `131 passed`,
    plus the same adjacent TUI regression group at `206 passed`;
    terminal resize coordinator size-source typing re-validated with focused
    resize reflow, terminal controller, and TUI alignment tests at `90 passed`,
    plus the same adjacent TUI regression group at `206 passed`;
    terminal size-change runtime state typing re-validated with focused resize
    reflow and TUI alignment tests at `87 passed`, plus the same adjacent TUI
    regression group at `206 passed`;
    bottom-pane footprint/history viewport size typing re-validated with
    focused resize reflow and TUI alignment tests at `87 passed`, plus the same
    adjacent TUI regression group at `206 passed`;
    bottom-pane footprint repaint callbacks re-validated as side-effect-only
    resize/reflow owner hooks with focused resize reflow and TUI alignment
    tests at `87 passed`, plus the same adjacent TUI regression group at
    `206 passed`;
    active-view completion enum plumbing re-validated with focused
    bottom-pane-view, list-selection-view, view-stack, and TUI alignment tests
    at `57 passed`, plus the adjacent custom terminal, bottom-pane
    view/list-selection/view-stack, terminal projection/surface/controller,
    resize reflow, terminal runtime, and TUI alignment group at `239 passed`;
    selection-popup selected-row style ownership re-validated with focused
    selection-popup, terminal frame, command-popup, terminal surface, and TUI
    alignment tests at `84 passed`, plus the adjacent custom terminal,
    bottom-pane view/list-selection/view-stack, terminal
    projection/surface/controller, resize reflow, terminal runtime, and TUI
    alignment group at `239 passed`;
    composer projection ownership re-validated with focused chat-composer,
    terminal frame/projection/surface, and TUI alignment tests at `109 passed`,
    plus the adjacent custom terminal, bottom-pane view/list-selection/view-stack,
    chat-composer, terminal frame/projection/surface/controller, resize reflow,
    terminal runtime, and TUI alignment group at `281 passed`.
  - Added
    `app.resize_reflow.terminal_history_bottom_row_for_view_state(...)` and a
    typed `TerminalBottomPaneRenderContextProviderProtocol`; history viewport
    bottom-row calculation now composes bottom-pane owner state through the
    resize/reflow owner, so `terminal_controller.py` no longer builds a
    render context just to compute history bounds.
  - Added
    `app.resize_reflow.run_terminal_bottom_pane_footprint_render_cycle_for_view_state(...)`;
    terminal bottom-pane rendering now lets the resize/reflow owner fetch the
    bottom-pane render context for the footprint cycle and pass it into the
    render callback, so `terminal_controller.py` no longer calls
    `TerminalBottomPaneViewState.render_context_for_size(...)` directly.
  - Updated the TUI alignment manifest for
    `bottom_pane/terminal_controller.py` so its resize/reflow responsibility
    now records the current owner boundary: the controller passes bottom-pane
    owner state and cursor callbacks, while `app.resize_reflow` owns
    render-context acquisition, history viewport bounds, footprint timing, and
    external repaint dispatch.
  - Added `selection_popup_common.terminal_popup_lines_for_width(...)` and
    updated `bottom_pane/terminal_frame.py` to consume owner-prepared clipped
    popup rows instead of applying popup row width clipping one line at a time.
    Popup row width handling now stays at the
    `codex-tui::bottom_pane::selection_popup_common` boundary, while
    `terminal_frame.py` only places rows into the frame writes.
  - Re-validated this resize/reflow owner boundary with focused resize reflow,
    terminal controller, and TUI alignment tests at `91 passed`; standalone
    alignment guard at `25 passed`; focused selection-popup/frame/alignment
    tests at `41 passed`; adjacent resize reflow, terminal
    footprint/frame/projection/controller/surface/runtime, and TUI alignment
    tests at `176 passed`; adjacent selection-popup,
    terminal-footprint/frame/projection/controller/surface/runtime, and TUI
    alignment tests at `124 passed`; and the broader bottom-pane,
    chatwidget, ratatui bridge, custom terminal, terminal runtime, and TUI
    alignment slice at `358 passed`.
- Added a Rust-like terminal bottom-pane framework for the scrollback-first TUI
  path:
  - `pycodex/tui/bottom_pane/terminal_surface.py` now treats slash popup and
    model picker rows as the same bottom-pane active-view surface, rendering
    `CommandPopup` / `ListSelectionView` rows through the Rust-aligned
    `selection_popup_common` measurement and row styling helpers instead of
    hand-building terminal strings for each popup.
  - `/model` in the terminal product path now opens
    `chatwidget::model_popups` as a `SelectionViewParams` /
    `ListSelectionView` active view; Up/Down/Enter/Esc/Tab are handled before
    normal composer submission, so `/model` no longer becomes a user turn.
  - `ListSelectionView` now accepts model-popup event objects as well as
    callable actions, allowing terminal popups to reuse the same
    `ModelPopupEvent` flow as the Textual path.
  - Added terminal surface/runtime regressions for `/model` opening the bottom
    model picker, Down moving the highlighted model row, Enter confirming the
    selection, and `/model` not submitting a user turn.
  - Cleared two broader TUI regressions while validating the full suite:
    streaming test helpers now strip assistant bullet prefixes, and Textual
    token-usage updates refresh the idle footer using the Rust
    `token_usage` baseline percentage (`Context 53% left` for 100k / 200k).
  - Verification: `python -m pytest pycodex/tui -q` passes with
    2319 passed, 59 skipped, and one existing Textual teardown warning.
- Established the Rust-aligned TUI input-chain regression contract for the
  terminal product path:
  - `pycodex/tui/tui/event_stream.py` now maps Windows console key payloads,
    resize, paste, Enter, Tab, arrow keys, and non-ASCII characters such as
    Chinese IME output into a single `TerminalInputEvent` stream.
  - Windows terminal input now prefers `WindowsConsoleEventSource` /
    console-record key events; `LineTerminalInputSource` remains only as a
    degraded fallback when key-event initialization fails.
  - Added focused input-contract tests covering ASCII submit, Chinese submit,
    slash popup filtering, Down-highlight movement, Tab completion, and local
    command non-submission through the same terminal event path.
  - New rule for future TUI input edits: changes touching `event_stream.py`,
    `bottom_pane::chat_composer`, `bottom_pane::terminal_surface`, or
    `terminal_runtime.py` must run the input contract matrix, not only a
    single slash-command regression.
- Continued the scrollback-first terminal TUI decomposition after deleting
  `pycodex/tui/scrollback_runtime.py`:
  - Moved live bottom-pane terminal surface calculations/rendering into
    `pycodex/tui/bottom_pane/terminal_surface.py`, keeping
    `pycodex/tui/tui/terminal_runtime.py` as orchestration glue.
  - Added focused bottom-pane surface coverage in
    `pycodex/tui/bottom_pane/tests/test_terminal_surface.py`.
  - Verified the terminal product path still routes through
    `pycodex.tui.tui.run_terminal_tui`, with no remaining
    `scrollback_runtime` / `run_scrollback_tui` / `ScrollbackTuiRunner`
    imports in Python sources.
  - Confirmed `/model` and list-selection keyboard behavior remain covered by
    the existing `chatwidget` / `bottom_pane` tests rather than a private
    runner-specific picker state.
  - Moved real-terminal transcript cell wrapping/materialization helpers from
    `pycodex/tui/tui/terminal_runtime.py` into
    `pycodex/tui/insert_history.py`, matching the Rust
    `codex-tui::insert_history` ownership boundary more closely.
  - Moved finalized terminal history cell insertion planning into
    `pycodex/tui/insert_history.py` via `TerminalHistoryCellInsertPlan` and
    `terminal_history_cell_insert_plan`; `terminal_runtime.py` now consumes the
    prepared rows/projection state instead of deriving separator rows and
    retained projection cells itself.
  - Added `tests/test_tui_insert_history.py` coverage for terminal history
    prefix continuation rows, wide-character wrapping budgets, and product
    terminal wrap width.
  - Moved real-terminal retained transcript viewport repaint into
    `pycodex/tui/app/resize_reflow.py` via
    `repaint_terminal_history_viewport`, so resize/bottom-pane footprint
    changes now delegate the visible history tail projection to the Rust-aligned
    `app::resize_reflow` package instead of open-coding it in the runner.
  - Added `TerminalResizeReflowPlan` plus
    `plan_terminal_resize_reflow` / `plan_terminal_stream_finish_reflow` in
    `pycodex/tui/app/resize_reflow.py`, moving the scrollback product path's
    stream-time resize defer/repair decision out of the terminal runner.
  - Added `TerminalResizeHistoryReplayer` in
    `pycodex/tui/app/resize_reflow.py`; retained-history viewport repaint and
    scrollback replay callback wiring now lives with the Rust-aligned
    `app::resize_reflow` boundary instead of as private
    `terminal_runtime.py` methods.
  - Added `TerminalInputSourceProvider` in
    `pycodex/tui/tui/event_stream.py`; the active terminal input-source cache
    now lives with the Rust-aligned `tui::event_stream` boundary instead of as
    `_terminal_input_source` state on `TerminalTuiRunner`.
  - Added `TerminalClearUiExecutor` in `pycodex/tui/app/history_ui.py`; the
    terminal `/clear` command now delegates clear/reset sequencing and state
    sink application to the Rust-aligned `app::history_ui` boundary.
  - Added `TerminalLocalCommandDispatcher` in
    `pycodex/tui/tui/local_command.py`; prompt-to-local-command dispatch now
    lives with the terminal local-command module instead of private runner
    methods.
  - Removed terminal-runner-only forwarding wrappers for history writes,
    session header/startup notices, user prompt output, and `/status`; the
    runner now calls the already Rust-aligned `insert_history`,
    `app::history_ui`, `history_cell::*`, and `status::card` entrypoints
    directly where those effects are scheduled.
  - Removed terminal-runner-only resize/layout forwarding wrappers; terminal
    layout activation, deactivation, and resize checks now call
    `TerminalResizeCoordinator` directly from the scheduling sites.
  - Removed the last terminal-runner-only simple callback wrappers for history
    wrap width, bottom-pane footprint repaint, and history-state application;
    scheduling sites now pass direct callbacks into `insert_history` and
    `app::resize_reflow` instead of keeping private pass-through methods on
    `TerminalTuiRunner`.
  - Added a narrow Textual teardown guard for composer-control shortcut polling
    so status timer ticks after widget unmount do not fail the slash popup
    regression suite.
  - Restored Rust-like slash popup flow in the real-terminal product path:
    Windows TTY input now uses a key-by-key console source instead of the
    cooked-line adapter, `bottom_pane::chat_composer` routes popup keys before
    normal text handling, and `bottom_pane::terminal_surface` renders the
    `CommandPopup` below the composer with selected-row highlighting.
  - Added terminal-runtime regression coverage for typing `/m`, seeing
    `/model` / `/memories`, moving the highlighted row with Down, and
    completing the selected slash command with Tab without submitting a user
    turn.
  - Added `pycodex/tui/tui/local_command.py` to plan the lightweight terminal
    product path's local command subset (`/clear`, `/status`, `/help`, `/quit`
    and exit aliases) using the Rust-aligned `slash_command` definitions while
    leaving richer slash commands such as `/model` to the chatwidget/bottom-pane
    path.
  - Added `TerminalClearState` and `terminal_clear_state_after_clear` to
    `pycodex/tui/app/history_ui.py`; terminal `/clear` now applies the
    Rust-aligned history UI reset helper instead of open-coding transcript and
    pending-reflow state resets in the runner.
  - Added `TerminalClearApplicationState` and
    `terminal_clear_application_state` to `pycodex/tui/app/history_ui.py`;
    terminal `/clear` now receives prepared insert-history, assistant-stream,
    and resize-pending state from the Rust-aligned `app::history_ui` boundary
    instead of reconstructing those objects inside `terminal_runtime.py`.
  - Added `run_terminal_clear_ui_effects` in
    `pycodex/tui/app/history_ui.py`; terminal `/clear` effect ordering
    (layout deactivate, terminal clear/flush, clear-state application, header
    repaint, layout reactivate) now lives with the Rust-aligned
    `app::history_ui` boundary while the terminal runner supplies callbacks.
  - Moved the terminal scrollback product path's plain-text `/status` card
    shaping into `pycodex/tui/status/card.py` via `TerminalStatusCardData` and
    `terminal_status_card_text`, matching the Rust `codex-tui::status::card`
    ownership boundary while preserving the current terminal UI shape.
  - Added `terminal_status_card_data_from_runtime` and
    `run_terminal_status_card_render` in `pycodex/tui/status/card.py`;
    terminal `/status` now keeps runtime-field extraction, status-card data
    construction, plain-text card shaping, and history-cell write dispatch with
    the Rust-aligned `status::card` boundary while `terminal_runtime.py`
    supplies runtime provider callbacks.
  - Moved terminal session header text generation into
    `pycodex/tui/app/history_ui.py` via `TerminalSessionHeaderData` and
    `terminal_session_header_text`; startup and `/clear` header rendering now
    delegates to the Rust-aligned `app::history_ui` helper that wraps
    `history_cell::session::SessionHeaderHistoryCell`.
  - Added `terminal_session_header_data_from_runtime` and
    `run_terminal_session_header_render` in `pycodex/tui/app/history_ui.py`;
    terminal startup header runtime-field extraction and history-cell write
    dispatch now live with the Rust-aligned `app::history_ui` boundary while
    `terminal_runtime.py` supplies provider callbacks.
  - Moved terminal passive footer text formatting into
    `pycodex/tui/bottom_pane/footer.py` via `TerminalIdleFooterData` and
    `terminal_idle_footer_text`; the terminal runner now only supplies
    resolved model/cwd/fast state while `bottom_pane::footer` owns the visible
    footer line shape.
  - Added `terminal_idle_footer_data_from_runtime` and
    `run_terminal_idle_footer_text` in `pycodex/tui/bottom_pane/footer.py`;
    terminal idle footer runtime-field extraction and passive footer text
    dispatch now live with the Rust-aligned `bottom_pane::footer` boundary
    while `terminal_runtime.py` supplies provider callbacks.
  - Moved terminal startup notice text shaping into
    `pycodex/tui/history_cell/session.py` via `terminal_startup_notice_lines`;
    the terminal runner now only fetches startup tooltip/warnings while the
    Rust-aligned session/history-cell boundary owns tooltip markdown cleanup,
    warning de-duplication, and scrollback bullet formatting for this product
    path.
  - Added `run_terminal_startup_notices_render` in
    `pycodex/tui/history_cell/session.py`; startup tooltip/warning runtime
    extraction, notice write sequencing, and the trailing blank history line
    now live with the Rust-aligned session/history-cell boundary while
    `terminal_runtime.py` supplies provider callbacks.
  - Moved terminal user-prompt scrollback text shaping into
    `pycodex/tui/history_cell/messages.py` via `terminal_user_prompt_text`;
    the terminal runner now delegates the prompt line shape to the Rust-aligned
    `history_cell::messages` boundary instead of formatting it inline.
  - Added `run_terminal_user_prompt_output` in
    `pycodex/tui/history_cell/messages.py`; terminal user prompt output now
    keeps live-status clearing, prompt history-cell write, and terminal
    bottom-pane redraw sequencing with the Rust-aligned
    `history_cell::messages` boundary while the runner supplies side-effect
    callbacks.
  - Moved terminal command status scrollback text shaping into
    `pycodex/tui/exec_cell/render.py` via `terminal_command_status_text`,
    matching the Rust `exec_cell::render::command_display_lines` title
    contract for `Running` and `Ran` command summaries while preserving the
    current terminal product output.
  - Moved terminal assistant stream delta wrapping into
    `pycodex/tui/history_cell/messages.py` via
    `terminal_assistant_delta_text`; the terminal runner now delegates
    continuation-prefix, newline, carriage-return, wide-character, and tab
    column accounting to the Rust-aligned message history-cell boundary.
  - Moved terminal command notification text extraction into
    `pycodex/tui/chatwidget/command_lifecycle.py` via
    `command_text_from_notification`, following the Rust
    `chatwidget::protocol -> chatwidget::command_lifecycle` route for
    `ItemStarted` / `ItemCompleted` command execution notifications.
  - Moved `AgentMessageDelta` payload extraction into
    `pycodex/tui/chatwidget/protocol.py` via
    `agent_message_delta_from_notification`; the terminal runner no longer
    imports the Textual runtime's private `_event_delta` helper for assistant
    stream notifications.
  - Moved retryable `Error` notification live-status extraction into
    `pycodex/tui/chatwidget/protocol.py` via
    `retry_error_status_from_notification`; the terminal runner no longer
    imports the Textual runtime's private `_payload_field` helper inside its
    event loop.
  - Added `terminal_notification_action` in
    `pycodex/tui/chatwidget/protocol.py`, so the terminal scrollback product
    path receives a small Rust-protocol-aligned action plan for assistant
    deltas, command start/completion, retry errors, and turn completion instead
    of interpreting raw server notification variants directly in the runner.
  - Updated terminal command notification actions in
    `pycodex/tui/chatwidget/protocol.py` to carry the formatted
    `exec_cell::render` command-status history line (`Running` / `Ran`)
    directly; `terminal_runtime.py` now writes protocol-provided command
    status text instead of wrapping raw command strings itself.
  - Added `TerminalNotificationEffectPlan` and
    `terminal_notification_effect_plan` in
    `pycodex/tui/chatwidget/protocol.py`; the terminal runner now consumes the
    chatwidget-owned plan for turn-status suppression, live-status hide/clear
    conflict resolution, and active-stream finalization gating instead of
    owning those notification semantics itself.
  - Added `terminal_turn_close_effect_plan` in
    `pycodex/tui/chatwidget/protocol.py`; app-event-stream closed/error
    cleanup now reuses the chatwidget-owned terminal effect plan for clearing
    turn/live status and finalizing any active assistant stream instead of
    duplicating that lifecycle sequence in `terminal_runtime.py`.
  - Added `run_terminal_notification_effect_plan` in
    `pycodex/tui/chatwidget/protocol.py`; the terminal runner now supplies
    side-effect callbacks while the Rust-aligned protocol boundary owns the
    effect-plan execution order for turn-status, live-status, and assistant
    stream finalization effects.
  - Added `run_terminal_notification_action` in
    `pycodex/tui/chatwidget/protocol.py`; assistant delta, command
    start/completion, retry error, and turn-completed terminal action dispatch
    now lives with the Rust-aligned protocol boundary while the terminal runner
    supplies side-effect callbacks.
  - Added `run_terminal_notification` in
    `pycodex/tui/chatwidget/protocol.py`; terminal notification handling now
    executes action planning, effect-plan derivation, effect application, and
    action dispatch through the Rust-aligned protocol boundary while the
    terminal runner only forwards app-runtime notifications and supplies
    terminal side-effect callbacks.
  - Added `run_terminal_app_notification` in
    `pycodex/tui/chatwidget/protocol.py`; terminal event handling now
    synchronizes the app-runtime notification callback before executing
    terminal action/effect dispatch inside the Rust-aligned
    `chatwidget::protocol` boundary, including the compatibility behavior that
    app sync failures do not prevent terminal scrollback rendering.
  - Added `TerminalAssistantStreamDeltaPlan` and
    `terminal_assistant_stream_delta_plan` in
    `pycodex/tui/history_cell/messages.py`; assistant-stream open-prefix
    selection and delta state advancement now live with the Rust-aligned
    message history-cell boundary while the terminal runner only opens the
    terminal history stream and writes the prepared delta text.
  - Added `run_terminal_assistant_stream_delta_plan` in
    `pycodex/tui/history_cell/messages.py`; assistant-stream open/write/state
    sequencing now executes at the Rust-aligned message history-cell boundary
    while `terminal_runtime.py` supplies only open-stream and write-delta
    side-effect callbacks.
  - Added `run_terminal_assistant_stream_finalization` in
    `pycodex/tui/history_cell/messages.py`; assistant-stream finalization now
    sequences projection extraction, stream state reset, retained-history
    projection application, and stream-finish resize repair through the
    Rust-aligned message history-cell boundary while `insert_history` and
    `app::resize_reflow` still execute through callbacks.
  - Added `run_terminal_turn_start` in
    `pycodex/tui/chatwidget/turn_runtime.py`; submitted-turn startup now keeps
    prompt history append, turn timestamp application, assistant stream reset,
    turn-status clear, and initial status render sequencing with the
    Rust-aligned `chatwidget::turn_runtime` boundary while
    `terminal_runtime.py` supplies side-effect callbacks.
  - Added `run_terminal_turn_submission` in
    `pycodex/tui/chatwidget/turn_runtime.py`; terminal user-turn submission now
    keeps turn-start setup, app-runtime submission, event-stream consumption,
    and failure close/error/exit effects with the Rust-aligned chatwidget turn
    lifecycle boundary while `terminal_runtime.py` supplies callbacks.
  - Added `TerminalHistoryStreamFinishPlan` and
    `terminal_history_stream_finish_plan` in
    `pycodex/tui/insert_history.py`; assistant stream finalization now delegates
    optional projection-cell retention to the Rust-aligned insert-history
    boundary instead of branching on projection text in `terminal_runtime.py`.
  - Added `finish_history_stream_output_and_flush` in
    `pycodex/tui/insert_history.py`; terminal/plain assistant-stream output
    finalization now selects the correct output surface inside the Rust-aligned
    insert-history boundary instead of keeping a runner-local
    `_finish_history_output` wrapper.
  - Added `finish_history_stream_projection_and_flush` in
    `pycodex/tui/insert_history.py`; terminal/plain assistant-stream output
    finalization and retained projection-state advancement now execute together
    at the Rust-aligned insert-history boundary instead of being chained
    directly in `terminal_runtime.py`.
  - Added `run_terminal_history_cell_output_and_flush` in
    `pycodex/tui/insert_history.py`; finalized history-cell output now keeps
    terminal-active resize probing, bottom-row lookup, terminal/plain output
    selection, inline-output fallback, and writer flush inside the
    Rust-aligned `insert_history` boundary while `terminal_runtime.py` supplies
    only callbacks and the current history state.
  - Added `run_terminal_history_lines_output_and_flush` in
    `pycodex/tui/insert_history.py`; finalized pre-materialized history row
    insertion now keeps empty-row short-circuiting, terminal-active resize
    probing, bottom-row lookup, terminal/plain output selection, bottom-pane
    clear/render callbacks, and writer flush with the Rust-aligned
    `insert_history` boundary instead of `_insert_history_lines`.
  - Added `run_terminal_history_output_and_flush` in
    `pycodex/tui/insert_history.py`; terminal history output now selects
    finalized row insertion versus inline write inside the Rust-aligned
    `insert_history` boundary instead of branching inside the terminal runner.
  - Added `run_terminal_history_stream_open_and_flush` in
    `pycodex/tui/insert_history.py`; assistant streaming history-cell opening
    now keeps terminal-active resize probing, bottom-row lookup, optional gap
    insertion, terminal/plain prefix output, bottom-pane repaint, and stream
    write-marker advancement with the Rust-aligned `insert_history` boundary
    instead of `_open_assistant_stream_cell`.
  - Added `run_terminal_local_command_plan` in
    `pycodex/tui/tui/local_command.py`; the terminal runner now supplies
    clear/help/status side-effect callbacks while the local-command boundary
    owns `/clear`, `/status`, `/help`, and exit action dispatch.
  - Added `run_terminal_local_command` in
    `pycodex/tui/tui/local_command.py`; the lightweight terminal command
    boundary now owns prompt-to-plan plus dispatch for its local slash/exit
    subset while `terminal_runtime.py` supplies only side-effect callbacks.
  - Moved terminal assistant stream prefix, initial-column, and final
    scrollback projection text into `pycodex/tui/history_cell/messages.py` via
    `terminal_assistant_stream_prefix`,
    `terminal_assistant_stream_initial_column`, and
    `terminal_assistant_projection_text`; the terminal runner now only opens,
    writes, and finalizes the stream.
  - Moved terminal live/turn status text shaping and second-level redraw gating
    into `pycodex/tui/chatwidget/status_surfaces.py` via
    `terminal_live_status_text`, `terminal_turn_status_header`, and
    `should_render_terminal_turn_status`, leaving the runner responsible for
    terminal side effects rather than status-surface content rules.
  - Added `TerminalTurnStatusState` in
    `pycodex/tui/chatwidget/status_surfaces.py`; the terminal runner now stores
    one chatwidget-owned turn-status state object instead of separately
    mutating active/last-second/suppressed fields.
  - Added active-turn status refresh/clear/suppress helpers in
    `pycodex/tui/chatwidget/status_surfaces.py`; the terminal runner now
    delegates status tick refresh and state effects to the Rust-aligned
    `chatwidget::status_surfaces` boundary instead of calling state methods or
    checking refresh gates inline.
  - Replaced the terminal runner's ad hoc live-status active/text fields with
    `TerminalLiveStatusSurface` and `bottom_pane_footprint_transition` in
    `pycodex/tui/bottom_pane/terminal_surface.py`; bottom-pane now owns whether
    live status expands the terminal footprint and whether a status transition
    requires viewport repaint.
  - Added live-status show/hide transition helpers in
    `pycodex/tui/bottom_pane/terminal_surface.py`; the terminal runner now
    receives previous/current bottom-pane live-status states from the
    Rust-aligned bottom-pane boundary before applying repaint side effects.
  - Moved non-TTY inline live-status ANSI overwrite/clear sequences into
    `pycodex/tui/custom_terminal.py` via `write_inline_status_line` and
    `clear_inline_status_line`, keeping terminal control escape ownership in
    the Rust-aligned `custom_terminal` module instead of the runner.
  - Routed terminal `/clear` through
    `pycodex/tui/custom_terminal.py::clear_scrollback_and_visible_screen_ansi`,
    matching Rust `custom_terminal::Terminal::clear_scrollback_and_visible_screen_ansi`
    instead of keeping a shorter runner-local ANSI clear sequence.
  - Moved terminal size lookup into `pycodex/tui/custom_terminal.py` via
    `terminal_size`; terminal resize/layout callers now use the Rust-aligned
    terminal boundary instead of importing `shutil` in the runner.
  - Moved terminal history insertion scroll-region/cursor preparation into
    `pycodex/tui/insert_history.py` via `prepare_terminal_history_insert`;
    assistant stream opening now reuses the same Rust-aligned insertion
    preparation helper as finalized transcript insertion.
  - Let `pycodex/tui/bottom_pane/terminal_surface.py::render_bottom_pane`
    place the composer cursor by default through `custom_terminal.move_cursor`,
    removing the terminal runner's `_move_cursor` and
    `_set_history_scroll_region` wrappers.
  - Moved streaming history-output reset/repaint finalization into
    `pycodex/tui/insert_history.py` via `finish_terminal_history_output`;
    terminal runner no longer has a `_reset_scroll_region` wrapper and only
    calls `custom_terminal.reset_scroll_region` directly for layout/resize
    lifecycle resets.
  - Added `run_terminal_resize_reflow_plan` in
    `pycodex/tui/app/resize_reflow.py`, so app resize/reflow owns terminal
    resize plan action dispatch (`repaint_history_viewport` vs.
    `replay_history_scrollback`) while the runner only updates pending state
    and supplies terminal callbacks.
  - Added projection-cell level replay/repaint helpers in
    `pycodex/tui/app/resize_reflow.py`
    (`replay_terminal_history_projection_cells` and
    `repaint_terminal_history_projection_viewport`); the terminal runner no
    longer assembles retained history projection lines before resize repaint or
    scrollback replay.
  - Added `replay_terminal_history_scrollback_for_resize` in
    `pycodex/tui/app/resize_reflow.py`, moving the high-level resize replay
    sequence (clear terminal scrollback, replay retained projection cells,
    repaint bottom pane) out of the terminal runner.
  - Added `repaint_terminal_history_projection_viewport_and_flush` in
    `pycodex/tui/app/resize_reflow.py`, so retained history viewport repaint
    and writer flushing are owned by the app resize/reflow boundary while the
    terminal runner only supplies projection cells, wrapping, and viewport
    dimensions.
  - Added `TerminalSizeChangeReflowPlan` and
    `plan_terminal_size_change_reflow` in
    `pycodex/tui/app/resize_reflow.py`, moving the real-terminal
    first-observed-size/no-op/resize/defer decision out of
    `pycodex/tui/tui/terminal_runtime.py` and closer to Rust
    `App::handle_draw_size_change`.
  - Added `run_terminal_size_change_reflow` in
    `pycodex/tui/app/resize_reflow.py`; the app resize/reflow boundary now
    owns terminal resize execution order, recursive resize guard synchronization,
    scroll-region reset, and reflow-plan dispatch callbacks while
    `terminal_runtime.py` only supplies observed terminal size and side effects.
  - Added `run_terminal_history_state_scrollback_replay_for_resize_width` in
    `pycodex/tui/app/resize_reflow.py`; resize replay now resets stale
    insert-history write markers, clears/rebuilds terminal scrollback from
    retained projection cells, and redraws the bottom pane through the
    Rust-aligned `app::resize_reflow` boundary instead of open-coding the reset
    before replay in `terminal_runtime.py`.
  - Added
    `run_terminal_history_state_scrollback_replay_insert_for_resize_width` in
    `pycodex/tui/app/resize_reflow.py`; resize replay now owns reset/apply,
    replay insert reservation for an active live-status footprint, and final
    bottom-pane render sequencing while `terminal_runtime.py` supplies only the
    insert-history callback.
  - Added `run_terminal_history_state_viewport_repaint_for_width` in
    `pycodex/tui/app/resize_reflow.py`; retained history viewport repaint now
    keeps the terminal-active guard, bottom-row lookup, terminal width lookup,
    retained projection repaint, and writer flush inside the Rust-aligned
    `app::resize_reflow` boundary while `terminal_runtime.py` only supplies
    callbacks and current history state.
  - Added `run_terminal_bottom_pane_footprint_reflow` in
    `pycodex/tui/app/resize_reflow.py`; live-status bottom-pane footprint
    changes now keep the terminal-active guard, footprint-change planning,
    active-stream deferral, pending-state preservation, and reflow-plan dispatch
    inside the Rust-aligned `app::resize_reflow` boundary while
    `terminal_runtime.py` supplies only current surfaces and callbacks.
  - Added `run_terminal_layout_activation` and
    `run_terminal_layout_deactivation` in
    `pycodex/tui/app/resize_reflow.py`; terminal layout lifecycle now
    initializes/clears app-owned resize state and dispatches bottom-pane render
    or scroll-region reset through the Rust-aligned `app::resize_reflow`
    boundary instead of open-coding activation/deactivation in the runner.
  - Added `clear_bottom_pane_and_flush` and
    `render_bottom_pane_and_flush` in
    `pycodex/tui/bottom_pane/terminal_surface.py`, so real-terminal
    bottom-pane clear/render flushing is owned by the Rust-aligned
    `bottom_pane` surface helper instead of being open-coded after each call
    in the terminal runner.
  - Added `run_terminal_bottom_pane_clear` and
    `run_terminal_bottom_pane_render` in
    `pycodex/tui/bottom_pane/terminal_surface.py`; the bottom-pane terminal
    surface now owns clear/render plan creation, resize-before-draw ordering,
    and action-plan execution while `terminal_runtime.py` supplies only state
    and callbacks.
  - Added `insert_terminal_history_lines_and_flush` and
    `insert_plain_history_lines_and_flush` in
    `pycodex/tui/insert_history.py`; terminal history insertion and non-TTY
    fallback history output now own their writer flush inside the
    Rust-aligned `insert_history` boundary instead of open-coding line writes
    and flushes in the terminal runner.
  - Added `write_history_inline_output_and_flush`,
    `insert_history_lines_output_and_flush`, and
    `write_history_cell_output_and_flush` in `pycodex/tui/insert_history.py`;
    inline writes, finalized row insertion, and finalized transcript-cell
    output now advance `TerminalHistoryState` and choose terminal/plain output
    surfaces inside the Rust-aligned insert-history boundary instead of
    chaining plan objects and writer calls in the terminal runner.
  - Added `open_terminal_history_stream_and_flush` and
    `open_plain_history_stream_and_flush` in
    `pycodex/tui/insert_history.py`; assistant stream opening now delegates
    history-surface preparation, prefix emission, and writer flush to the
    Rust-aligned `insert_history` boundary while the terminal runner only
    updates stream lifecycle state.
  - Added `open_history_stream_output_and_flush` in
    `pycodex/tui/insert_history.py`; assistant stream opening now delegates
    optional separator row insertion plus terminal/plain prefix output to the
    Rust-aligned insert-history surface instead of branching directly in the
    terminal runner.
  - Added `open_history_stream_plan_output_and_flush` in
    `pycodex/tui/insert_history.py`; assistant stream opening now combines the
    insert-history stream-open plan, separator/prefix output, bottom-pane
    repaint callback, and history state advancement inside the Rust-aligned
    insert-history boundary.
  - Added `write_terminal_history_stream_delta_and_flush` in
    `pycodex/tui/insert_history.py`; assistant streaming delta terminal
    emission now keeps wrapping/column calculation in `history_cell::messages`
    while line writing and writer flushing live with the Rust-aligned
    `insert_history` terminal surface.
  - Added `finish_plain_history_output_and_flush` in
    `pycodex/tui/insert_history.py`; non-TTY assistant stream finalization now
    delegates newline emission and writer flush to the Rust-aligned
    `insert_history` output surface instead of open-coding it in
    `terminal_runtime.py`.
  - Added `terminal_history_cell_insert_lines` in
    `pycodex/tui/insert_history.py`; finalized history-cell gap insertion and
    wrap materialization are now planned inside the Rust-aligned
    `insert_history` boundary rather than in
    `pycodex/tui/tui/terminal_runtime.py`.
  - Added wrap-width aware resize replay/repaint helpers in
    `pycodex/tui/app/resize_reflow.py`
    (`replay_terminal_history_projection_cells_for_width`,
    `repaint_terminal_history_projection_viewport_for_width_and_flush`, and
    `replay_terminal_history_scrollback_for_resize_width`); resize reflow now
    uses `insert_history.terminal_history_cell_lines` directly instead of
    relying on a runner-owned wrapping callback.
  - Added terminal history write-state helpers in
    `pycodex/tui/insert_history.py`; finalized row insertion now advances the
    transcript gap/blank-line state through the Rust-aligned insert-history
    boundary instead of open-coding that state machine in the terminal runner.
  - Added `TerminalHistoryState` in `pycodex/tui/insert_history.py`; the
    terminal runner now stores one insert-history-owned state object for
    transcript write markers and retained projection cells instead of
    separately mutating runner-private history fields.
  - Added `make_terminal_input_source` in
    `pycodex/tui/tui/event_stream.py`; the terminal runner now delegates
    StringIO, Windows cooked-line, and select-based input source selection to
    the Rust-aligned `tui::event_stream` boundary.
  - Added `get_or_make_terminal_input_source` in
    `pycodex/tui/tui/event_stream.py`; terminal input source reuse/lazy
    creation now mirrors Rust `EventBrokerState::active_event_source_mut`
    inside the Rust-aligned event-stream boundary instead of a runner-private
    `_make_terminal_input_source` wrapper.
  - Added `TerminalAssistantStreamState` and stream state transition helpers in
    `pycodex/tui/history_cell/messages.py`; the terminal runner now holds one
    message-owned stream state object instead of separately managing assistant
    open/column/text fields.
  - Extended `TerminalNotificationAction` in
    `pycodex/tui/chatwidget/protocol.py` with terminal UI effect flags; the
    terminal runner now applies a protocol-owned action plan for suppressing
    turn status, clearing/hiding live status, finalizing active streams, and
    clearing turn status instead of duplicating those rules per notification
    branch.
  - Added `TerminalTurnStatusState` in
    `pycodex/tui/chatwidget/status_surfaces.py`; active-turn status refresh,
    suppression, and clear state transitions now live with the Rust-aligned
    status-surface boundary while the terminal runner performs only writes.
  - Added `TerminalTurnStatusRenderPlan`,
    `terminal_turn_elapsed_seconds`, and `terminal_turn_status_render_plan` in
    `pycodex/tui/chatwidget/status_surfaces.py`; active-turn elapsed/header
    calculation and state advancement now live with the Rust-aligned
    chatwidget status-surface boundary instead of the terminal runner.
  - Added `run_terminal_turn_status_render` in
    `pycodex/tui/chatwidget/status_surfaces.py`; the terminal runner now
    supplies only the live-status write callback while the Rust-aligned
    status-surface boundary owns active-turn render dispatch and state
    advancement.
  - Added `TerminalResizeRuntimeState` in
    `pycodex/tui/app/resize_reflow.py`; the terminal runner now observes
    terminal sizes and executes resize plans while the Rust-aligned
    `app::resize_reflow` boundary owns last-size tracking and the
    recursive-resize guard state.
  - Added terminal-history-state aware resize replay helpers in
    `pycodex/tui/app/resize_reflow.py`; the terminal runner no longer reaches
    into `TerminalHistoryState.projection_cells` or resets insert-history write
    markers directly when repainting/rebuilding the scrollback surface after
    resize.
  - Added `TerminalHistoryStreamOpenPlan` and
    `terminal_history_stream_open_plan` in `pycodex/tui/insert_history.py`;
    assistant-stream separator rows and history marker advancement before
    streaming output are now owned by the Rust-aligned `insert_history`
    boundary instead of being decided in the terminal runner.
  - Added `TerminalHistoryLinesInsertPlan` and
    `terminal_history_lines_insert_plan` in `pycodex/tui/insert_history.py`;
    ordinary terminal/plain history row insertion now receives prepared rows
    plus insert-history-owned write-marker advancement instead of mutating
    row-write state in `terminal_runtime.py`.
  - Added `TerminalHistoryInlineWritePlan` and
    `terminal_history_inline_write_plan` in `pycodex/tui/insert_history.py`;
    non-row history writes now receive insert-history-owned marker advancement
    instead of calling `TerminalHistoryState.after_write` from the terminal
    runner.
  - Added `TerminalLiveStatusActionPlan`,
    `terminal_live_status_show_plan`, `terminal_live_status_hide_plan`, and
    `run_terminal_live_status_action_plan` in
    `pycodex/tui/bottom_pane/terminal_surface.py`; live-status show/hide now
    receives bottom-pane-owned repaint/render/inline side-effect planning and
    execution instead of branching directly in `terminal_runtime.py`.
  - Added `run_terminal_live_status_show` and
    `run_terminal_live_status_hide` in
    `pycodex/tui/bottom_pane/terminal_surface.py`; the terminal runner now
    supplies resize/repaint/render callbacks while the Rust-aligned bottom-pane
    surface owns live-status state application order and action-plan execution.
  - Added `plan_terminal_bottom_pane_footprint_reflow` in
    `pycodex/tui/app/resize_reflow.py`; the terminal runner now delegates the
    bridge from bottom-pane live-status footprint changes to resize/repaint
    repair planning to the Rust-aligned `app::resize_reflow` boundary.
  - Added `TerminalBottomPaneActionPlan`,
    `TerminalBottomPaneState`, `terminal_bottom_pane_clear_plan`, and
    `terminal_bottom_pane_render_plan` in
    `pycodex/tui/bottom_pane/terminal_action.py`; terminal bottom-pane
    clear/render skip/check-resize/render-state decisions and prepared frame
    input state now live with the Rust-aligned bottom-pane action boundary
    instead of branching in the runner or frame projection layer.
  - Added `pycodex/tui/bottom_pane/terminal_projection.py`; bottom-pane
    frame-to-`custom_terminal` live-viewport request/update conversion,
    backend cursor-position policy handoff, and action-plan projection now
    live in an explicit adapter between `chatwidget::rendering` frame content
    and `custom_terminal` backend lifecycle. Frame/buffer content projection is
    owned by `chatwidget.rendering`.
  - Added live-status show/hide transition helpers in
    `pycodex/tui/bottom_pane/terminal_surface.py`; bottom pane now owns the
    previous/current live-status state transition used by terminal repaint
    planning.
  - Added `poll_terminal_turn_event` and
    `terminal_turn_event_stream_closed` in `pycodex/tui/tui/event_stream.py`;
    the terminal runner now consumes event/idle/closed poll states instead of
    probing app-runtime stream compatibility shapes directly.
  - Added `run_terminal_turn_idle_tick` in
    `pycodex/tui/tui/event_stream.py`; submitted-turn idle maintenance now
    keeps resize-before-status-refresh ordering with the Rust-aligned
    event-stream boundary while `terminal_runtime.py` supplies callbacks.
  - Added `run_terminal_turn_event_loop` in
    `pycodex/tui/tui/event_stream.py`; submitted-turn event polling,
    idle/closed dispatch, per-event resize tick, and `TurnCompleted` loop exit
    now live with the Rust-aligned `tui::event_stream` boundary while the
    terminal runner supplies callbacks.
  - Added terminal composer draft helpers in
    `pycodex/tui/bottom_pane/chat_composer`; the terminal runner now delegates
    CRLF normalization, text append, backspace, clear, and submit-line shaping
    to the Rust-aligned `bottom_pane::chat_composer` boundary.
  - Added terminal composer input-action planning in
    `pycodex/tui/bottom_pane/chat_composer`; the terminal runner now asks the
    Rust-aligned composer boundary how text/backspace/line/enter/eof/interrupt
    events affect the draft, and only performs polling, repaint, and return
    side effects.
  - Added terminal composer input-action dispatch in
    `pycodex/tui/bottom_pane/chat_composer`; the terminal runner now supplies
    render/submit/interrupt/eof callbacks while the Rust-aligned composer
    boundary owns interpretation of terminal input action variants.
  - Added `run_terminal_composer_submit`,
    `run_terminal_composer_eof`, and `run_terminal_composer_interrupt` in
    `pycodex/tui/bottom_pane/chat_composer`; terminal submit/eof/interrupt
    result effects now live with the Rust-aligned composer boundary instead of
    runner-private `_submit/_eof/_interrupt` wrappers.
  - Added `run_terminal_live_status_text_show` in
    `pycodex/tui/chatwidget/status_surfaces`; terminal live-status text
    construction and show dispatch now live with the Rust-aligned
    `chatwidget::status_surfaces` boundary while `bottom_pane::terminal_surface`
    still owns footprint/repaint terminal effects.
  - Added `run_terminal_composer_prompt_loop` in
    `pycodex/tui/bottom_pane/chat_composer`; terminal prompt polling now keeps
    draft initialization, resize-aware event consumption, action dispatch, and
    submit/eof/interrupt return sequencing with the Rust-aligned
    `bottom_pane::chat_composer` boundary while `terminal_runtime.py` only
    supplies the event source and terminal side-effect callbacks.
  - Added `run_terminal_composer_read_prompt` in
    `pycodex/tui/bottom_pane/chat_composer`; terminal prompt selection across
    active event-source input, blocking fallback input, and non-terminal line
    input now lives with the Rust-aligned composer lifecycle boundary while
    `terminal_runtime.py` only wires IO and repaint callbacks.
  - Added `run_terminal_composer_blocking_line_prompt` in
    `pycodex/tui/bottom_pane/chat_composer`; the terminal input-source fallback
    now keeps draft clearing, bottom-pane render, blocking line read, resize
    tick, and bottom-pane clear sequencing with the Rust-aligned composer
    boundary instead of a runner-private fallback method.
  - Removed stale terminal-runner-only wrappers for bottom-pane row aliases,
    cell-gap insertion, bottom-pane row calculation, and footer writing after
    those responsibilities had already moved to `bottom_pane` or
    `insert_history` aligned helpers.
  - Removed the stale `_write_live_footer` terminal-runner wrapper after
    bottom-pane rendering and footer shaping had moved to Rust-aligned
    bottom-pane helpers.

- Fixed startup prewarm cancellation/timeout consistency in `pycodex/core/session_startup_prewarm.py`:
  - Drains the prewarm task after `cancel()` so `resolve()` now reliably reports `task.cancelled()` on timeout or cancellation-token abort.
  - Kept telemetry and status tagging aligned with existing `startup_prewarm_resolve`/duration reporting behavior.

- Completed targeted core-slice approval/network parity fixes:
  - Fixed `canonicalize_command_for_approval` export alignment in `pycodex/core/__init__.py` so package-level export resolves to command canonicalization behavior.
  - Added missing `ConfigEdit` notice/migration setters in `pycodex/core/config_edit.py` and validated mapping values in `ConfigEdit.set_path`.
  - Tightened `pycodex/core/network_approval.py` request validation and cached-deny policy flow, including host/target casing consistency for policy-block paths.
- Aligned core model slug defaulting and messaging to upstream Rust expectations:
  - `gpt-5`/`gpt-5.3-Codex-Spark` usages in default local HTTP model selection were moved to `gpt-5.3-codex`.
  - Legacy/placeholder debug-model outputs and cyber fallback warning text were updated accordingly.
- Updated related regression assertions in CLI/runtime/compact tests for the same model slug.
- Fixed user-turn prompt lifecycle boundaries in `pycodex/core/turn_runtime.py`:
  - Defer user prompt lifecycle emission (`item_started`/`item_completed`) until after sampling succeeds.
  - Keep prompt recorded to history during request prep for context/compaction correctness, then emit prompt turn-item events from a dedicated post-sample path.
  - Prevented duplicate user message lifecycle/history behavior that was causing compact-history and terminal-error regression failures.
- Fixed unified exec snapshot timing in `pycodex/core/unified_exec.py` to better match Rust timing semantics for interactive sessions:
  - Added output-close tracking from the reader thread and deadline/post-exit draining behavior to `snapshot`.
  - Changed tty sessions to stop collecting after the first non-exit output chunk so short-lived interactive commands can defer late output until follow-up `write_stdin` calls.
  - Kept non-tty sessions collecting through command completion so immediate non-interactive calls still return final output and release sessions correctly.
- Tightened core auth and agent job parity behavior:
  - Made `run_chatgpt_login` resilient when the injected server object does not expose `serve_forever` (needed by login unit tests and test doubles).
  - Wrapped `report_agent_job_result` argument parsing so non-object `result` payloads and malformed invocation arguments are returned as `FunctionCallError`, matching handler contract.
  - Normalized Linux landlock command and path arguments to forward-slash strings for cross-platform test parity.
  - Restored `remove_snapshot_file` visibility as a built-in symbol after importing `pycodex.core` to keep existing tests that call it unqualified.
- Fixed a `doctor` CLI status-normalization regression:
  - Normalized status strings to treat upstream-style `"warning"` as CLI `"warn"` during summary aggregation.
  - Restored correct warning/fail count logic for `doctor --summary` / `--all` and kept exit code semantics aligned with Rust behavior.
- Added strict active-turn coverage for pending-input queue checks in the sampling path:
  - Added a focused regression test in `tests/test_core_turn_runtime.py` to ensure `has_pending_input` and `get_pending_input` are invoked with the active turn context when required by queue implementations.
  - This protects interactive follow-up behavior on custom queue adapters where the method signatures are `active_turn`-strict.
- Hardened input-queue method dispatch for keyword-only `active_turn` signatures:
  - `_call_input_queue_method` now supports `active_turn` passed as a keyword-only argument, improving robustness for alternate queue adapters.
  - Added `KeywordOnlyActiveTurnInputQueue` coverage so pending-input draining still records `session.active_turn` correctly without a positional signature.
- Hardened stop/after-agent hook compatibility for keyword-only and legacy signatures:
  - Updated `_run_turn_stop_hook` and `_call_after_agent_hook` to support `*, turn_context=...` style hooks without breaking existing positional-style hooks.
  - Kept positional fallback behavior for legacy 2/3-arg hook signatures so existing tests and users are not regressed.
  - Added regression coverage for:
    - keyword-only `after_agent` hook signature
    - keyword-only `run_turn_stop_hook` signature
    - follow-up continuation behavior under keyword-only stop hooks.
- Hardened user-prompt-submit hook compatibility with keyword-only signatures:
  - Updated `_call_user_prompt_submit_hook` to support `prompt=`-only and full keyword-only (`turn_context=`, `user_input=`, `prompt=`) hooks.
  - Added tests for:
    - keyword-only `prompt` signature that blocks input.
    - keyword-only full-signature hook including `turn_context/user_input/prompt`.
- Hardened tool-router hook dispatch for pre/post tool hooks:
  - Added signature-flexible invocation in `pycodex/core/tool_router.py` so `pre_tool_use_hook` and `post_tool_use_hook` accept keyword-only forms (e.g. `hook(payload=..., invocation=...)`, `hook(payload=..., result=...)`) as well as legacy positional calls.
  - Added regression tests in `tests/test_core_tool_router.py`:
    - `test_dispatch_pre_tool_use_hook_supports_keyword_only_signature`
    - `test_dispatch_post_tool_use_hook_supports_keyword_only_signature`.
- Extended tool dispatch trace compatibility for mapping-style trace contexts:
  - Updated `pycodex/core/tool_dispatch_trace.py` so `ToolDispatchTrace.start`, `record_completed`, and `record_failed` consume context access via mapping-safe lookup (`dict`/object support), and `is_enabled` honors mapping-backed flags.
  - Added mapping-path regression coverage in `tests/test_core_tool_dispatch_trace.py`:
    - `test_trace_facade_supports_mapping_trace_context`
    - `test_trace_facade_mapping_context_respects_disabled_flag`
- Widened personality migration to honor explicit profile override:
  - `maybe_migrate_personality` now applies `override_profile` to the effective config before personality/model-provider checks.
  - This prevents migration from overriding an explicitly configured profile personality when profile context is provided.
  - Added `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_personality_blocks_migration`.
  - Added `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_missing_profile_allows_migration_by_top_level_logic` to verify an unknown override falls back to normal migration flow.
  - Added `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_missing_profile_still_skips_without_sessions` to verify an unknown override keeps `SKIPPED_NO_SESSIONS` when no migration signal exists.
  - Added boundary coverage for malformed profile configuration:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_config_profile_with_non_mapping_profiles_returns_empty`
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_config_profile_with_non_mapping_profile_entry_returns_empty`
  - Added validation coverage for invalid `override_profile` type:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_non_string_override_profile_rejected`
  - Added coverage for override profile loading from `config.toml` on disk:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_from_disk_config_is_honored`
  - Added priority coverage for migration marker:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_marker_takes_precedence_even_with_override_profile`
  - Added explicit priority coverage for top-level personality over override profile:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_top_level_personality_blocks_even_with_override_profile`
  - Added coverage for empty profile entry fallback behavior:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_empty_profile_does_not_block_personality_migration`
  - Added coverage for blank override_profile fallback behavior:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_blank_override_profile_uses_top_level_profile_behavior`
  - Added disk-config explicit-priority coverage for override profile:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_from_disk_config_respects_disk_top_level_personality`
  - Added model-provider migration boundary coverage:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_model_provider_setting_does_not_block_migration_when_sessions_exist`
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_model_provider_setting_respects_no_sessions_path`
  - Added combined missing-override + model_provider migration coverage:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_missing_override_profile_respects_model_provider_with_sessions`
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_missing_override_profile_respects_model_provider_without_sessions`
  - Added explicit test for blank override with explicit top-level personality:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_top_level_personality_blocks_blank_override_profile`
  - Added marker short-circuit coverage without config input:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_marker_takes_precedence_even_without_config_argument`
  - Captured personality migration boundaries in the focused regression tests.
- Wired personality migration into non-interactive `exec` CLI startup flow:
  - `pycodex/cli/parser.py::_run_noninteractive_exec` now calls `maybe_migrate_personality` using `find_codex_home()` and `ExecCli.profile` override before building the bootstrap plan.
  - When migration is applied, `config_toml` is reloaded from disk so the injected top-level `personality` is visible for the same invocation.
  - Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_with_profile_triggers_personality_migration_reload` to assert that:
    - `maybe_migrate_personality` is invoked with profile override and an empty initial mapping,
    - migration-applied flow triggers a second `read_toml_mapping`,
    - and the second read (with `personality = pragmatic`) is what `build_exec_config_bootstrap_plan` receives.
  - Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_without_migration_applied_uses_original_config` to assert that:
    - `maybe_migrate_personality` returns non-APPLIED state,
    - only one `read_toml_mapping` is performed,
    - and bootstrap uses the original mapping unchanged.
- Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_prompt_without_subcommand_with_profile_triggers_noninteractive_migration_reload` to confirm implicit interactive `exec` fallback (`main(["--profile", ...])`) also exercises personality migration + config reload before bootstrap.
- Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_prompt_without_subcommand_with_profile_without_migration_uses_original_config` to confirm fallback `exec` path preserves existing config when migration is skipped.
- Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_with_profile_triggers_personality_migration_reload` and `...::test_main_review_without_migration_applied_uses_original_config` to confirm the same bootstrap behavior applies to `main(["review", ...])`.
- Stabilized `doctor` parser tests by stubbing network reachability in `TopLevelCliParserTests` setup/teardown:
  - Added a class-scoped `doctor_provider_reachability_check` mock in `tests/test_cli_parser.py` for all `test_main_doctor_*` cases to avoid external network flakiness.
  - Kept mocked behavior at warning status with a structured `reachability mode` detail so existing assertions for config-fallback and status aggregation remain valid.
- Preserved the production reachability behavior outside parser tests and
  documented the isolation decision in the focused regression coverage.

- Stabilized `doctor` parser tests in minimal environments by adding `TopLevelCliParserTests.setUp`/`tearDown` auth seeding:
  - `test_main_doctor_*` cases now get a temporary `OPENAI_API_KEY` when absent so `doctor` return-code checks are not flapped by missing credentials.
  - Kept parser-side `doctor` fail-on-no-auth semantics unchanged; this is explicitly a test environment compatibility fix while deciding final parity contract for strict auth failures.
- Aligned plugin/runtime prompt injection behavior in `pycodex/core/turn_runtime.py`:
  - `_build_plugin_injections` now resolves explicit plugin mentions against both `display_name` and authoritative `mcp_server_names`/`app_connector_ids` capability fields, and surfaces connector names (not IDs) for injected app labels.
  - `_response_item_skill_text` now only reads message-level `input_text` entries when collecting explicit app mentions from skill/plugin injections, reducing accidental matches from non-InputText content.
  - No behavioral changes were made to app/plugin extension ecosystems outside this core path.
- Aligned skill-injection warning propagation in `pycodex/core/turn_runtime.py`:
  - `_prepare_user_turn_skill_plugin_items` now emits warning events for `SkillInjections.warnings` returned by `build_skill_injections`, matching Rust behavior that forwards injected-skills warnings through event flow.
  - Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_forwards_skill_injection_warnings_as_events` and `...::test_run_user_turn_sampling_forwards_multiple_skill_injection_warnings_in_order` to ensure warning messages surface to the warning event stream and preserve order.
  - The focused tests document the event-ordering parity decision for warning handling.
- Added app/plugin analytics parity handling in `pycodex/core/turn_runtime.py`:
  - `_prepare_user_turn_skill_plugin_items` now emits app/plugin tracking calls matching Rust user-turn behavior:
    - `track_app_mentioned` for explicit app mentions (including skill-derived app ids),
    - `track_plugin_used` for explicit plugin mentions that expose `telemetry_metadata()`.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_explicit_app_and_plugin_mentions_for_analytics` to assert both calls are emitted with expected context/payload.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_does_not_track_plugins_without_telemetry_metadata` to confirm `track_plugin_used` stays silent when the plugin does not expose telemetry metadata, matching Rust `.filter_map(...telemetry_metadata)` behavior.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_prefixed_app_mentions_with_normalization` to assert `app://...`-prefixed explicit app mentions are normalized before analytics reporting.
  - Kept this as a minimal compatibility decision in the core slice.
- Added turn-config analytics parity in `pycodex/core/turn_runtime.py`:
  - `_prepare_user_turn_request_from_session` now dispatches `track_turn_resolved_config`-style analytics before model request dispatch.
  - Implemented resilient field extraction helpers for thread config snapshot values (`ephemeral`, `session_source`, `model_provider`, `approval_policy`, `service_tier`, `sandbox_network_access`, etc.), including optional first-turn resolution fallbacks.
  - Added silent failure guards so analytics transport errors cannot block user-turn execution.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_turn_resolved_config_for_analytics`.
  - Added payload assertions for `num_input_images`, `turn_id`, `thread_id`, `model_provider`, `session_source`, `reasoning_*`, `approval*`, `sandbox_network_access`, `collaboration_mode`, `personality`, and `is_first_turn`.
  - Recorded the scope through the resolved-config analytics regression assertions.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_turn_resolved_config_from_thread_attr_snapshot` to verify fallback resolution from `session.thread.thread_config_snapshot` for analytics tracking.
- Expanded thread-snapshot fallback coverage:
  - Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_turn_resolved_config_from_thread_callable_snapshot`, which verifies that callable `thread_config_snapshot` providers are resolved correctly for `track_turn_resolved_config`.
- Hardened connector analytics input handling for the core turn path by moving object-to-`AppInfo` coercion into `pycodex/core/connectors.py`:
  - `_coerce_app_info` now accepts non-mapping object connectors (including `SimpleNamespace`-style test doubles) by reading `to_mapping` or attribute fields before falling back to `AppInfo.from_mapping`.
  - Removed temporary object-normalization shim from `pycodex/core/turn_runtime.py::_available_connectors` so compatibility is handled centrally at the connector API boundary.
- Added regression coverage in `tests/test_core_connectors.py::ConnectorHelperTests::test_with_app_enabled_state_accepts_connector_objects` to assert `SimpleNamespace`-style connectors are accepted by `with_app_enabled_state`.

- Fine-tuned `turn_runtime` analytics resolved-config derivation for simplified Python runtime sessions:
  - `_build_turn_resolved_config_payload` now falls back to `thread_config` network-sandbox sources (`network_sandbox_policy` then `sandbox_policy`) when turn-context fields do not expose network strategy directly.
  - This aligns analytics `sandbox_network_access` derivation for backends where thread snapshot is the effective source of sandbox policy at turn creation time.

- Aligned `pycodex/core/session_runtime.py` sandbox-policy projection for session updates with upstream Rust behavior:
  - `InMemoryCodexSession.update_settings` now treats `sandbox_policy` changes as a source for deriving `permission_profile`, instead of only mutating policy fields directly.
  - Added shared projection logic to update `permission_profile`, `file_system_sandbox_policy`, and legacy `sandbox_policy` consistently from the same effective config.
  - Hardened snapshot/update ordering so `sandbox_policy` updates and snapshot generation remain coherent when only one field is supplied.
  - The session-runtime tests retain the sandbox-policy projection and fallback behavior as durable evidence.

- Added regression coverage for session sandbox-policy projection in `tests/test_core_session_runtime.py`:
  - `test_in_memory_session_update_settings_projects_sandbox_policy_to_permission_profile` verifies permission profile and file-system policy stay coherent when `sandbox_policy` is updated.
  - `test_in_memory_session_update_settings_preserves_deny_entries_when_projecting_sandbox_policy` verifies deny entries from prior `permission_profile` are preserved during projection.

- Added preview-path coverage in `tests/test_core_session_runtime.py` for the same core slice:
  - `test_in_memory_session_preview_settings_projects_sandbox_policy_to_permission_profile` asserts `preview_settings` returns a projected `permission_profile` and does not mutate session state.
  - `test_in_memory_session_preview_settings_preserves_deny_entries_when_projecting_sandbox_policy` asserts `preview_settings` preserves deny entries when projecting `sandbox_policy`.

- Added thread-snapshot consistency coverage for the same sandbox projection slice:
  - `test_in_memory_session_thread_config_snapshot_reflects_sandbox_projection` in `tests/test_core_session_runtime.py` verifies `thread_config_snapshot()` returns the same `permission_profile` projection used by `update_settings` and leaves session fields unchanged.
  - `test_in_memory_session_thread_config_snapshot_preserves_deny_entries_when_projecting_sandbox_policy` verifies deny entries are preserved in snapshotted projection after `sandbox_policy` updates.

- Extended turn-construction coverage in `tests/test_core_session_runtime.py`:
  - `test_in_memory_session_new_default_turn_reflects_sandbox_projection` verifies `new_default_turn()` uses the same projected sandbox permission state as `thread_config_snapshot()` (including deny-entry preservation).

- Added turn-runtime resolved-config guard test in `tests/test_core_turn_runtime.py`:
  - `test_run_user_turn_sampling_tracks_turn_resolved_config_from_turn_context_permission_profile` verifies analytics payload uses `turn_context.permission_profile` first and derives `sandbox_network_access` from that source before thread snapshot fallbacks.
  - `test_run_user_turn_sampling_tracks_turn_resolved_config_from_turn_context_network_sandbox_policy` verifies `turn_context.network_sandbox_policy` is preferred over thread config `sandbox_policy` when resolving `sandbox_network_access` for analytics payload.

- Added end-to-end sandbox-projection analytics coverage in `tests/test_core_session_runtime.py`:
  - `test_in_memory_session_run_user_turn_sampling_tracks_resolved_config_from_settings_projection` verifies `InMemoryCodexSession` `update_settings(sandbox_policy=...)` -> `thread_config_snapshot` -> `run_user_turn_sampling_from_session` propagates the projected `permission_profile` (mapping form) and enables `sandbox_network_access` in resolved analytics payload.
- Extended request-shape parity for that same in-memory session sampling path across both transport variants:
  - `test_in_memory_session_run_user_turn_sampling_tracks_resolved_config_from_settings_projection` now also asserts `run_user_turn_sampling_from_session` returns a `request_plan` whose `prompt.input` includes a developer permissions-instructions message containing `<permissions instructions>` and network access text, confirming sandbox policy context is actually passed to model prompt input.
  - `test_in_memory_session_runs_user_turn_http_sampling` now carries the same assertion for the HTTP sampling path, confirming request prompt-shape parity is transport-agnostic.
  - `test_in_memory_session_prompt_instructions_injection_consistent_between_sampling_variants` compares extracted permissions-prompt developer entries from both request constructors and verifies permissions-marker counts align across sampling and HTTP sampling.
- The session turn-runtime tests are the durable request-prompt parity evidence.

## Test Coverage Added/Run
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_debug_models_returns_supported_default_models`
- `python -m pytest -q tests/test_cli_parser.py -k "main_exec_allows_strict_config or main_exec_reads_stdin_prompt_when_no_prompt_argument or main_exec_dash_reads_forced_stdin_prompt or main_exec_prepares_noninteractive_plan"`
- `python -m pytest -q tests/test_cli_parser.py`
- `python -m unittest tests.test_cli_core_smoke_suite tests.test_exec_core_runtime_smoke_suite tests.test_core_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`
- `python -m pytest -q tests/test_core_network_approval.py`
- `python -m pytest -q tests/test_core_unified_exec.py::CoreUnifiedExecHeadTailBufferTests`
- `python -m pytest -q tests/test_core_unified_exec.py tests/test_core_unified_exec_handler.py`
- `python -m pytest -q tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_default_session_exec_command_then_write_stdin`
- `python -m pytest -q tests/test_core_config_edit.py tests/test_core_command_canonicalization.py`
- `python -m pytest tests/test_cli_parser.py tests/test_core_network_approval.py tests/test_core_compact.py tests/test_core_config_edit.py tests/test_core_command_canonicalization.py tests/test_exec_session.py tests/test_exec_local_runtime.py tests/test_exec_core_runtime.py tests/test_exec_core_runtime_smoke_suite.py tests/test_core_smoke_suite.py tests/test_cli_core_smoke_suite.py tests/test_local_http_core_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py`
- `python -m pytest -q tests/test_cli_parser.py::TopLevelCliParserTests::test_main_debug_models_returns_supported_default_models tests/test_cli_parser.py::TopLevelCliParserTests::test_main_prompt_without_subcommand_uses_local_http_exec_when_available tests/test_core_compact.py::CompactTests::test_collect_user_messages_filters_context_and_legacy_warnings tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_default_local_http_model_precedence`
- `python -m pytest -q tests/test_exec_core_runtime_smoke_suite.py tests/test_core_smoke_suite.py`
- `python -m pytest tests/test_core_session_runtime.py tests/test_core_turn_runtime.py`
- `python -m pytest -q tests/test_core_session_runtime.py -k "run_user_turn_sampling_tracks_resolved_config_from_settings_projection or runs_user_turn_http_sampling"`
- `python -m pytest -q tests/test_core_session_runtime.py -k "prompt_instructions_injection_consistent_between_sampling_variants"`
- `python -m pytest -q tests/test_cli_login.py tests/test_core_agent_jobs.py tests/test_core_shell_snapshot.py tests/test_core_spawn_landlock.py`
- `python -m pytest -q tests/test_core_session_startup_prewarm.py`
  - Result: 6 passed
- `python -m pytest -q tests/test_core_tool_router.py tests/test_core_tool_parallel.py tests/test_core_tool_dispatch_trace.py`
  - Result: 197 passed
- `python -m pytest -q tests/test_core_tool_dispatch_trace.py tests/test_core_tool_router.py`
  - Result: 68 passed
- `python -m pytest -q tests/test_core_tool_router.py`
  - Result: 56 passed
- `python -m pytest -q tests -k "not app_server and not sdk and not argument-comment-lint"`
- `python -m pytest -q tests -k "not app_server and not sdk and not argument-comment-lint"`
  - Result in this environment: 5086 passed, 7 skipped (260 deselected, 391 subtests), including all core-runtime/exec/CLI smoke slices.
- `python -m pytest -q`
  - Result in this environment: 5476 passed, 45 skipped
- `python -m pytest -q tests/test_cli_parser.py::TopLevelCliParserTests::test_main_doctor_summary_counts_warning_status_as_warning tests/test_cli_parser.py::TopLevelCliParserTests::test_main_doctor_all_requests_installation_path_details`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_empty_input_pending_input_uses_active_turn tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_empty_input_pending_input_uses_active_turn_with_keyword_only_queue`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py -k "keyword_only"`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py -k "user_prompt_submit_hook_keyword_only"`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py`
- `python -m pytest -q tests/test_core_turn_runtime.py`
  - Result: 88 passed
- `python -m pytest -q codex/sdk/python/tests`
  - Result: 46 passed (including app-server suites)

## Open Known Gaps
- `doctor` auth gating parity needs an explicit decision:
  - In unauthenticated environments, `doctor` currently includes `auth.credentials: fail` and returns non-zero.
  - A follow-up is needed to decide strict upstream parity (keep fail semantics) versus parser-level compatibility defaults for missing credentials in environment-based tests.
- Remaining failures are now concentrated in app-server, MCP/plugin tooling, and broader streaming/daemon-adjacent paths outside this focused core slice.
- Follow-up work should continue to expand from this slice only where it unblocks `exec -> context -> model request -> stream handling -> tool dispatch -> final answer`.

## 2026-06-05 canonical crate migration batch 1

Moved the first existing implementation batch into Rust-tree-aligned canonical Python package paths: `pycodex/features`, `pycodex/features/managed.py`, `pycodex/git_utils`, and `pycodex/network_proxy`. Updated project/test imports, validated the new paths, then deleted the legacy `pycodex/core/features.py`, `pycodex/core/managed_features.py`, `pycodex/core/git_info.py`, and `pycodex/core/network_proxy_loader.py` files without keeping long-term shims.
## 2026-06-05 canonical crate migration batch 2: rollout

Moved `pycodex/core/rollout.py` to the Rust-tree-aligned canonical package `pycodex/rollout`, updated project/test imports, validated the new path, and deleted the legacy core file without retaining a long-term shim. Kept `session_rollout_init_error.py` and `thread_rollout_truncation.py` under `pycodex/core` because their Rust anchors are `core/src/*`, not the `codex-rollout` crate.
## 2026-06-05 canonical crate migration batch 3: utils string and approval presets

Moved `pycodex/core/string_utils.py` to `pycodex/utils/string` and `pycodex/core/approval_presets.py` to `pycodex/utils/approval_presets`, updated imports/tests, validated the new paths, and deleted the legacy core files without retaining long-term shims. Deliberately left `pycodex/core/paths.py` in place because it mixes `utils/home-dir` and `state` source anchors and should be split deliberately later.
## 2026-06-05 canonical crate migration batch 4: split core paths

Split `pycodex/core/paths.py` into `pycodex/utils/home_dir` for `codex-utils-home-dir` behavior and `pycodex/state` for state runtime DB path helpers. Updated imports/tests, validated canonical paths, and deleted the legacy core file without retaining a long-term shim. Marked `codex-utils-home-dir` as implemented and `codex-state` as partial helper shim in the crate ledger.
## 2026-06-05 canonical crate migration batch 5: remove apply_patch and execpolicy legacy shims

Deleted the legacy `pycodex/core/apply_patch.py` and `pycodex/core/exec_policy.py` compatibility shims after moving imports/tests to `pycodex.apply_patch` and `pycodex.execpolicy`. Removed the corresponding `pycodex.core` facade re-exports and fixed cycle-prone imports by making apply-patch dependencies lazy or type-only. Validated the canonical paths before and after deleting the shims.
## 2026-06-05 canonical crate migration batch 6: remove root TOML shim and canonicalize TUI

Deleted `pycodex/_toml.py`, replaced the legacy `pycodex/tui.py` shim with the canonical `pycodex/tui` package, and deleted `pycodex/cli/tui.py`. Updated imports/docs/tests to use `pycodex.config.toml_compat` and `pycodex.tui` directly. Validated canonical imports and targeted config/TUI tests.
## 2026-06-05 canonical crate migration batch 7: core-skills package

- Created canonical package `pycodex/core_skills` for already-ported helpers from `codex/codex-rs/core-skills`.
- Mapped config rules, injections, invocation utilities, mention helpers, and rendering helpers out of `pycodex/core`.
- Updated production and focused test imports to use canonical `pycodex.core_skills.*` modules.
- Old `pycodex/core/skill_*` files are intentionally retained until the touched-slice validation passes, then they should be deleted in the same migration batch.
- Focused validation passed before deletion: `62 passed`, import smoke passed.
- Deleted old coordinates: `pycodex/core/skill_config_rules.py`, `pycodex/core/skill_injections.py`, `pycodex/core/skill_invocation_utils.py`, `pycodex/core/skill_mentions.py`, `pycodex/core/skill_rendering.py`.
- Post-deletion validation passed: `62 passed`, import smoke passed.
- Old `pycodex.core.skill_*` import residual check found no matches.

## 2026-06-05 canonical crate migration batch 8: linux-sandbox and tools helpers

- Prepared canonical package `pycodex/linux_sandbox` for Linux sandbox command-construction helpers.
- Prepared canonical package/module `pycodex/tools/original_image_detail.py` for image-detail helper behavior from the tools crate.
- Updated production and focused test imports away from `pycodex.core.landlock` and `pycodex.core.original_image_detail`.
- Old core files are retained until focused validation passes, then should be deleted in this batch.
- Focused validation before deletion passed: `12 passed`, import smoke passed.
- Deleted old coordinates: `pycodex/core/landlock.py`, `pycodex/core/original_image_detail.py`.
- Post-deletion validation passed: `12 passed`, import smoke passed.
- Old `pycodex.core.landlock` / `pycodex.core.original_image_detail` import residual check found no matches.

## 2026-06-05 canonical migration batch 9: utils/plugins mention syntax

- Prepared canonical package `pycodex/utils/plugins` for Rust `codex-rs/utils/plugins` mention syntax helpers.
- Updated imports away from `pycodex.core.mention_syntax` and removed the `pycodex.core` facade export for mention sigils.
- Old `pycodex/core/mention_syntax.py` is retained until focused validation passes, then should be deleted in this batch.
- Focused validation before deletion passed: `40 passed`, import smoke passed.
- Deleted old coordinate: `pycodex/core/mention_syntax.py`.
- Post-deletion validation passed: `40 passed`, import smoke passed.
- Old `pycodex.core.mention_syntax` import residual check found no matches.

## 2026-06-05 canonical migration batch 10: tools/tool_discovery

- Prepared canonical `pycodex/tools/tool_discovery.py` for Rust `codex-rs/tools/src/tool_discovery.rs`.
- Moved `AppInfo` protocol shape to `pycodex/app_server_protocol/apps.py`, matching Rust's `codex_app_server_protocol::AppInfo` source.
- Moved `ToolSearchSourceInfo` out of core tool-search entry and into tools/tool_discovery.
- Updated imports away from `pycodex.core.tool_discovery` and removed the matching `pycodex.core` facade exports.
- Old `pycodex/core/tool_discovery.py` is retained until focused validation passes, then should be deleted in this batch.
- Focused validation before deletion passed: `133 passed`, import smoke passed.
- Deleted old coordinate: `pycodex/core/tool_discovery.py`.
- Post-deletion validation passed: `133 passed`, import smoke passed.
- Old `pycodex.core.tool_discovery` import residual check found no matches.

## 2026-06-06 canonical migration batch 11: tools/request_plugin_install split

- Prepared canonical `pycodex/tools/request_plugin_install.py` for Rust `codex-rs/tools/src/request_plugin_install.rs` protocol helpers.
- Prepared `pycodex/app_server_protocol/elicitation.py` for MCP elicitation shapes used by request-plugin-install.
- Trimmed `pycodex/core/request_plugin_install.py` so core keeps handler/spec/persistence behavior and imports tools protocol helpers instead of defining them.
- Updated imports away from `pycodex.core` for moved request-plugin-install protocol symbols.
- Focused validation passed after split: `94 passed`, import smoke passed.
- Exact residual check found no imports of moved request-plugin-install protocol symbols from `pycodex.core` or `pycodex.core.request_plugin_install`.
- `pycodex/core/request_plugin_install.py` intentionally remains as the Rust core handler/spec/persistence adapter; this batch was a split, not full deletion.

## 2026-06-06 canonical migration batch 12: core/tools/tool_search_entry

- Prepared canonical `pycodex/core/tools/tool_search_entry.py` for Rust `codex-rs/core/src/tools/tool_search_entry.rs`.
- Added `pycodex/core/tools` as the Python coordinate for core-runtime tool behavior under Rust core's tools module tree.
- Updated production and focused test imports away from the old `pycodex.core.tool_search_entry` path.
- Removed the matching `pycodex.core` facade exports for tool-search entry conversion helpers.
- Focused validation before deletion passed: `87 passed`, import smoke passed.
- Deleted old coordinate: `pycodex/core/tool_search_entry.py`.
- Post-deletion validation passed: `87 passed`.
- Old `pycodex.core.tool_search_entry` import residual check found no matches.

## 2026-06-06 canonical migration batch 13: plugins, extension tools, remote skills, connectors split

- Moved remote skill API helpers from `pycodex/core/remote_skills.py` to `pycodex/core_skills/remote.py`, matching Rust `codex-rs/core-skills/src/remote.rs`.
- Moved extension tool adapter behavior from `pycodex/core/extension_tools.py` to `pycodex/core/tools/handlers/extension_tools.py`, matching Rust `codex-rs/core/src/tools/handlers/extension_tools.rs`.
- Moved explicit plugin/app mention behavior from `pycodex/core/plugin_mentions.py` to `pycodex/core/plugins/mentions.py`, matching Rust `codex-rs/core/src/plugins/mentions.rs`.
- Created `pycodex/connectors` for Rust `codex-rs/connectors`, with `accessible.py`, `merge.py`, and `metadata.py`.
- Trimmed `pycodex/core/connectors.py` so it keeps Rust `core/src/connectors.rs` policy/config behavior and calls `pycodex.connectors` through private aliases for external crate behavior.
- Removed `pycodex.core` facade exports for the moved remote-skill, extension-tool, plugin-mention, and connector-crate helpers.
- Deleted old coordinates: `pycodex/core/remote_skills.py`, `pycodex/core/extension_tools.py`, and `pycodex/core/plugin_mentions.py`.
- Focused validation after deletion passed: `180 passed`, `4 subtests passed`, import smoke passed.
- Old import residual check found no matches for `pycodex.core.remote_skills`, `pycodex.core.extension_tools`, or `pycodex.core.plugin_mentions`.
- Moved connector-crate helper residual check found no public old-coordinate imports; `pycodex/core/connectors.py` intentionally retains only private aliases for core-to-connectors calls.

## 2026-06-06 canonical migration batch 14: core-skills model split

- Created `pycodex/core_skills/model.py` for Rust `codex-rs/core-skills/src/model.rs` skill model types.
- Moved the defining coordinate for `SkillMetadata`, `SkillDependencies`, and `SkillToolDependency` out of `pycodex/core/mcp_skill_dependencies.py`.
- Updated core-skills modules and focused tests to import skill model types from `pycodex.core_skills.model`.
- Kept `pycodex/core/mcp_skill_dependencies.py` as the Rust `core/src/mcp_skill_dependencies.rs` behavior module; it now imports model types instead of defining them.
- Kept `pycodex/core/skills.py` as the Rust `core/src/skills.rs` facade; `pycodex.core.skills.SkillMetadata` re-exports the canonical core-skills model type.
- Removed root `pycodex.core` facade exports for the moved model definitions.
- Focused validation passed: `72 passed`, import smoke passed.
- Old model-definition residual check found the model classes only in `pycodex/core_skills/model.py`.

## 2026-06-06 canonical migration batch 15: simple core tool handlers

- Moved `pycodex/core/plan_handler.py` to `pycodex/core/tools/handlers/plan.py`, matching Rust `codex-rs/core/src/tools/handlers/plan.rs`.
- Moved `pycodex/core/request_user_input_handler.py` to `pycodex/core/tools/handlers/request_user_input.py`, matching Rust `codex-rs/core/src/tools/handlers/request_user_input.rs`.
- Moved `pycodex/core/request_permissions_handler.py` to `pycodex/core/tools/handlers/request_permissions.py`, matching Rust `codex-rs/core/src/tools/handlers/request_permissions.rs`.
- Moved `pycodex/core/test_sync_handler.py` to `pycodex/core/tools/handlers/test_sync.py`, matching Rust `codex-rs/core/src/tools/handlers/test_sync.rs`.
- Updated production imports and focused tests to use canonical handler coordinates instead of root `pycodex.core` or old top-level core modules.
- Removed root `pycodex.core` facade exports for the moved handler symbols.
- Deleted old coordinates after focused validation.
- Focused validation before and after deletion passed: `260 passed`, `1 skipped`.
- Old import residual check found no matches for the four old handler module paths or moved root-facade imports.

## 2026-06-06 canonical migration batch 16: view-image and tool-search handlers

- Moved `pycodex/core/view_image_handler.py` to `pycodex/core/tools/handlers/view_image.py`, matching Rust `codex-rs/core/src/tools/handlers/view_image.rs`.
- Moved `pycodex/core/tool_search_handler.py` to `pycodex/core/tools/handlers/tool_search.py`, matching Rust `codex-rs/core/src/tools/handlers/tool_search.rs`.
- Kept `ToolSearchOutput` in `pycodex/core/tool_context.py`, because it is a tool output context type rather than a handler implementation.
- Updated production imports and focused tests to use canonical handler coordinates.
- Removed root `pycodex.core` facade exports for the moved handler symbols.
- Deleted old coordinates after focused validation.
- Focused validation before and after deletion passed: `304 passed`.
- Old import residual check found no matches for the two old handler module paths or moved root-facade imports.

## 2026-06-06 canonical migration batch 17: goal and plugin-install handlers

- Moved `pycodex/core/goal_handler.py` to `pycodex/core/tools/handlers/goal/__init__.py`, matching Rust `codex-rs/core/src/tools/handlers/goal.rs` plus `goal/{create,get,update}_goal.rs` and `goal_spec.rs`.
- Moved `pycodex/core/request_plugin_install.py` to `pycodex/core/tools/handlers/request_plugin_install.py`, matching Rust `request_plugin_install.rs`, `request_plugin_install_spec.rs`, `list_available_plugins_to_install.rs`, and `list_available_plugins_to_install_spec.rs`.
- Updated production imports in `spec_plan`, connector policy/exposure helpers, and the root `pycodex.core` facade to use canonical handler coordinates.
- Updated focused tests to import the goal handler directly from the canonical handler package.
- Deleted old coordinates by moving the files; no root-level `pycodex/core/goal_handler.py` or `pycodex/core/request_plugin_install.py` handler files remain.
- Focused validation passed: `84 passed`.
- Old root handler import residual check found no matches for `pycodex.core.goal_handler` or `pycodex.core.request_plugin_install`.

## 2026-06-06 canonical migration batch 18: core/tools public layer

- Moved `pycodex/core/tool_context.py` to `pycodex/core/tools/context.py`, matching Rust `codex-rs/core/src/tools/context.rs`.
- Moved `pycodex/core/tool_registry.py` to `pycodex/core/tools/registry.py`, matching Rust `codex-rs/core/src/tools/registry.rs`.
- Moved `pycodex/core/tool_router.py` to `pycodex/core/tools/router.py`, matching Rust `codex-rs/core/src/tools/router.rs`.
- Moved `pycodex/core/spec_plan.py` to `pycodex/core/tools/spec_plan.py`, matching Rust `codex-rs/core/src/tools/spec_plan.rs`.
- Moved `pycodex/core/tool_runtimes.py` to `pycodex/core/tools/runtimes/__init__.py`, matching Rust `codex-rs/core/src/tools/runtimes/mod.rs` plus runtime submodules.
- Updated production and focused test imports away from the old root `pycodex.core.tool_*` and `pycodex.core.spec_plan` module paths.
- Deleted old coordinates by moving the files; no root-level public tools module files remain for this batch.
- Focused public-tools validation passed: `573 passed`, `2 skipped`.
- Import smoke for the five canonical modules passed.
- Old import residual check found no matches for moved root paths.
- Wider adjacent validation including `turn_runtime` and `session_runtime` reported 6 failures in sandbox/settings assertions; these were recorded as adjacent risk, not treated as a blocker for this coordinate migration because the failed assertions are outside the moved import/registry/router behavior.

## 2026-06-06 adjacent runtime bug convergence: settings snapshots and analytics

- Resolved the adjacent failures discovered after batch 18.
- Updated `ThreadConfigSnapshot.sandbox_policy()` to mirror Rust `core/src/codex_thread.rs`: derive the compatibility `SandboxPolicy` from `PermissionProfile.to_legacy_sandbox_policy(cwd)` instead of returning the file-system sandbox policy.
- Added `file_system_sandbox_policy` to the Python snapshot object so the in-memory runtime can expose the projected split policy needed by Python-side session tests and turn context assembly.
- Updated `InMemoryCodexSession.update_settings` to reuse the already-computed snapshot permission profile and file-system policy, preventing value-equivalent but object-distinct projections.
- Updated turn resolved-config analytics to fall back from turn context to config/thread snapshot for `reasoning_effort`, `reasoning_summary`, `collaboration_mode`, and `personality` when using lightweight session mocks.
- Adjusted one Python test expectation from `preview.sandbox_policy` to `preview.sandbox_policy()` to match the Rust method contract.
- Focused runtime validation passed: `192 passed`.
- Original adjacent validation set passed: `765 passed`, `2 skipped`.

## 2026-06-06 canonical migration batch 19: remaining core/tools support layer

- Moved `pycodex/core/tool_dispatch_trace.py` to `pycodex/core/tools/tool_dispatch_trace.py`, matching Rust `codex-rs/core/src/tools/tool_dispatch_trace.rs`.
- Moved `pycodex/core/tool_lifecycle.py` to `pycodex/core/tools/lifecycle.py`, matching Rust `codex-rs/core/src/tools/lifecycle.rs`.
- Moved `pycodex/core/tool_parallel.py` to `pycodex/core/tools/parallel.py`, matching Rust `codex-rs/core/src/tools/parallel.rs`.
- Moved `pycodex/core/tool_orchestrator.py` to `pycodex/core/tools/orchestrator.py`, matching Rust `codex-rs/core/src/tools/orchestrator.rs`.
- Moved `pycodex/core/tool_sandboxing.py` to `pycodex/core/tools/sandboxing.py`, matching Rust `codex-rs/core/src/tools/sandboxing.rs`.
- Updated production and focused test imports away from old root `pycodex.core.tool_*` module paths.
- Deleted old coordinates by moving the files; no root-level support-layer tool files remain for this batch.
- Focused validation passed: `634 passed`, `2 skipped`.
- Import smoke for the five canonical support-layer modules passed.
- Old import residual check found no matches for moved root paths.

## 2026-06-06 canonical migration batch 20: hosted/network/hook/events tool modules

- Moved `pycodex/core/hosted_spec.py` to `pycodex/core/tools/hosted_spec.py`, matching Rust `codex-rs/core/src/tools/hosted_spec.rs`.
- Moved `pycodex/core/network_approval.py` to `pycodex/core/tools/network_approval.py`, matching Rust `codex-rs/core/src/tools/network_approval.rs`.
- Moved `pycodex/core/hook_names.py` to `pycodex/core/tools/hook_names.py`, matching Rust `codex-rs/core/src/tools/hook_names.rs`.
- Moved `pycodex/core/tool_events.py` to `pycodex/core/tools/events.py`, matching Rust `codex-rs/core/src/tools/events.rs`.
- Updated production and focused test imports away from old root module paths.
- Deleted old coordinates by moving the files.
- Focused validation passed: `662 passed`, `2 skipped`.
- Import smoke for the four canonical modules passed.
- Old import residual check found no matches for moved root paths.

## 2026-06-06 canonical migration batch 21: code-mode tool subtree

- Moved `pycodex/core/code_mode.py` to `pycodex/core/tools/code_mode/__init__.py`, matching Rust `codex-rs/core/src/tools/code_mode/mod.rs`.
- Confirmed Rust code mode is a subtree with `execute_handler.rs`, `execute_spec.rs`, `wait_handler.rs`, `wait_spec.rs`, and `response_adapter.rs`.
- Kept the Python implementation as one package module for this batch; no internal behavior split was attempted.
- Updated production and focused test imports away from `pycodex.core.code_mode`.
- Deleted the old root coordinate by moving the file.
- Focused validation passed: `349 passed`.
- Import smoke for `pycodex.core.tools.code_mode` passed.
- Old import residual check found no matches for `pycodex.core.code_mode`.

## 2026-06-06 canonical migration batch 22: shell and unified-exec handlers

- Moved `pycodex/core/shell_handler.py` to `pycodex/core/tools/handlers/shell.py`, matching Rust `codex-rs/core/src/tools/handlers/shell.rs`.
- Moved `pycodex/core/shell_spec.py` to `pycodex/core/tools/handlers/shell_spec.py`, matching Rust `codex-rs/core/src/tools/handlers/shell_spec.rs`.
- Moved `pycodex/core/unified_exec_handler.py` to `pycodex/core/tools/handlers/unified_exec.py`, matching Rust `codex-rs/core/src/tools/handlers/unified_exec.rs`.
- Updated production and focused test imports away from old root module paths.
- Reduced `pycodex/core/tools/handlers/__init__.py` to a light package initializer to avoid eager-import cycles when importing a single handler submodule.
- Deleted old coordinates by moving the files.
- Focused validation passed: `354 passed`, `2 skipped`.
- Import smoke for the three canonical handler modules passed.
- Old import residual check found no matches for moved root paths.

## 2026-06-06 canonical migration batch 23: dynamic tool handler

- Moved `pycodex/core/dynamic_tool_handler.py` to `pycodex/core/tools/handlers/dynamic.py`, matching Rust `codex-rs/core/src/tools/handlers/dynamic.rs`.
- Updated production and focused test imports away from `pycodex.core.dynamic_tool_handler`.
- Deleted the old root coordinate by moving the file.
- Focused validation passed: `235 passed`.
- Import smoke for `pycodex.core.tools.handlers.dynamic` passed.
- Old import residual check found no matches for the moved root path.

## 2026-06-06 canonical migration batch 24: MCP handlers

- Moved `pycodex/core/mcp_tool_handler.py` to `pycodex/core/tools/handlers/mcp.py`, matching Rust `codex-rs/core/src/tools/handlers/mcp.rs`.
- Moved `pycodex/core/mcp_resource_handler.py` to `pycodex/core/tools/handlers/mcp_resource.py`, matching Rust `codex-rs/core/src/tools/handlers/mcp_resource.rs` and `mcp_resource_spec.rs`.
- Updated production and focused test imports away from old root module paths.
- Deleted old coordinates by moving the files.
- Focused validation passed: `151 passed`.
- Import smoke for the two canonical MCP handler modules passed.
- Old import residual check found no matches for moved root paths.
- Scope note: this was coordinate-only MCP shim preservation, not deep MCP feature expansion.

## 2026-06-06 - canonical migration batch 25: agent and multi-agent handlers

- Rust anchors:
  - `codex/codex-rs/core/src/tools/handlers/agent_jobs.rs`
  - `codex/codex-rs/core/src/tools/handlers/agent_jobs_spec.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents_common.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents_spec.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents_v2.rs`
- Python targets:
  - `pycodex/core/tools/handlers/agent_jobs.py`
  - `pycodex/core/tools/handlers/multi_agents_common.py`
  - `pycodex/core/tools/handlers/multi_agents_spec.py`
  - `pycodex/core/tools/handlers/multi_agents.py`
  - `pycodex/core/tools/handlers/multi_agents_v2.py`
- Change:
  - Moved the previously core-level agent job and multi-agent handler modules into the Rust-aligned `core/tools/handlers` coordinate.
  - Rewrote imports to the new canonical paths.
  - Removed the old root-level module files instead of leaving compatibility aliases, matching the current no-duplicate-coordinate policy.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - Import smoke for the new handler modules: passed.
  - `python -m pytest tests/test_core_agent_jobs.py tests/test_core_multi_agents_common.py tests/test_core_multi_agents_spec.py tests/test_core_multi_agents_v1_handler.py tests/test_core_multi_agents_v2_handler.py tests/test_core_tool_registry.py tests/test_core_spec_plan.py tests/test_core_session_runtime.py`: `195 passed`.
- Scope note:
  - Deep multi-agent orchestration remains deprioritized as an extension area; this batch preserves and relocates the existing shim/handler behavior under the upstream handler coordinate.

## 2026-06-06 - canonical migration batch 26: agent/config/context/state core subpackages

- Rust anchors:
  - `codex/codex-rs/core/src/agent/agent_resolver.rs`
  - `codex/codex-rs/core/src/agent/control.rs`
  - `codex/codex-rs/core/src/agent/registry.rs`
  - `codex/codex-rs/core/src/agent/status.rs`
  - `codex/codex-rs/core/src/config/agent_roles.rs`
  - `codex/codex-rs/core/src/config/edit.rs`
  - `codex/codex-rs/core/src/context/mod.rs`
  - `codex/codex-rs/core/src/context/permissions_instructions.rs`
  - `codex/codex-rs/core/src/state/auto_compact_window.rs`
- Python targets:
  - `pycodex/core/agent/agent_resolver.py`
  - `pycodex/core/agent/control.py`
  - `pycodex/core/agent/registry.py`
  - `pycodex/core/agent/status.py`
  - `pycodex/core/config/agent_roles.py`
  - `pycodex/core/config/edit.py`
  - `pycodex/core/context/__init__.py`
  - `pycodex/core/context/permissions_instructions.py`
  - `pycodex/core/state/auto_compact_window.py`
- Change:
  - Moved selected root-level Python modules into Rust-aligned core subpackages.
  - Converted `pycodex/core/context.py` into the `pycodex.core.context` package initializer so `context/permissions_instructions.py` can live under the Rust-aligned context coordinate without a Python module/package name conflict.
  - Updated imports and top-level `pycodex.core` re-exports to the new canonical paths.
  - Removed old root-level files instead of leaving compatibility aliases.
- Validation:
  - New canonical module import smoke: passed.
  - Old selected file path check: old files absent, new files present.
  - Residual old import search: no old module-path leakage; one harmless top-level re-export import false positive (`agent_status_from_event`).
  - `python -m pytest tests/test_core_agent_control.py tests/test_core_agent_registry.py tests/test_core_agent_resolver.py tests/test_core_agent_roles.py tests/test_core_agent_status.py tests/test_core_auto_compact_window.py tests/test_core_config_edit.py tests/test_core_context.py tests/test_core_context_updates.py tests/test_core_permissions_instructions.py tests/test_core_realtime_context.py tests/test_core_request_permissions_handler.py tests/test_core_request_plugin_install_handler.py tests/test_core_session_runtime.py`: `266 passed, 1 skipped`.
- Scope note:
  - This batch is coordinate consolidation plus import preservation. It does not expand deep agent orchestration beyond the behavior already implemented.

## 2026-06-06 - canonical migration batch 27: unified_exec package coordinate

- Rust anchors:
  - `codex/codex-rs/core/src/unified_exec/mod.rs`
  - `codex/codex-rs/core/src/unified_exec/errors.rs`
  - `codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
  - `codex/codex-rs/core/src/unified_exec/process.rs`
  - `codex/codex-rs/core/src/unified_exec/process_manager.rs`
  - `codex/codex-rs/core/src/unified_exec/process_state.rs`
- Python target:
  - `pycodex/core/unified_exec/__init__.py`
- Change:
  - Converted the old root-level `pycodex/core/unified_exec.py` module into the Rust-aligned `pycodex/core/unified_exec/` package initializer.
  - Kept the public import path `pycodex.core.unified_exec` stable, so existing callers did not need import rewrites.
  - Removed the old root-level file coordinate instead of keeping a duplicate alias.
- Validation:
  - New package import smoke: passed.
  - Old file absent and new package initializer present.
  - `python -m pytest tests/test_core_unified_exec.py tests/test_core_unified_exec_handler.py tests/test_core_exec.py tests/test_exec_local_runtime.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_core_code_mode.py`: `540 passed, 2 skipped`.
- Scope note:
  - This batch is a coordinate conversion only. It does not yet split Python `unified_exec` internals into the Rust submodules (`errors`, `head_tail_buffer`, `process`, `process_manager`, `process_state`).

## 2026-06-06 - canonical migration batch 28: handler utils and tools crate tool definition

- Rust anchors:
  - `codex/codex-rs/core/src/tools/handlers/mod.rs`
  - `codex/codex-rs/tools/src/tool_definition.rs`
- Python targets:
  - `pycodex/core/tools/handlers/utils.py`
  - `pycodex/tools/tool_definition.py`
- Change:
  - Moved the old root-level `pycodex/core/handler_utils.py` into the Rust-aligned handler helper coordinate.
  - Moved the old root-level `pycodex/core/tool_definition.py` into `pycodex/tools/`, matching the upstream `codex-rs/tools` crate instead of the core crate.
  - Rewrote imports to the new canonical paths and preserved the top-level `pycodex.core.ToolDefinition` re-export.
  - Removed old root-level file coordinates instead of keeping duplicate aliases.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - New canonical module import smoke: passed.
  - `python -m pytest tests/test_core_handler_utils.py tests/test_core_tool_definition.py tests/test_core_apply_patch.py tests/test_core_request_permissions_handler.py tests/test_core_unified_exec_handler.py tests/test_core_session_runtime.py tests/test_exec_local_runtime.py tests/test_core_tool_registry.py tests/test_core_spec_plan.py tests/test_core_code_mode.py`: `514 passed, 3 skipped`.
- Scope note:
  - This batch is coordinate consolidation only. It preserves existing behavior while removing misleading root-level coordinates.

## 2026-06-06 - canonical migration batch 29: session and turn runtime package coordinates

- Rust anchors:
  - `codex/codex-rs/core/src/session/mod.rs`
  - `codex/codex-rs/core/src/session/session.rs`
  - `codex/codex-rs/core/src/session/turn.rs`
  - `codex/codex-rs/core/src/session/turn_context.rs`
  - `codex/codex-rs/core/src/codex_thread.rs`
- Python targets:
  - `pycodex/core/session/runtime.py`
  - `pycodex/core/session/turn/prompt.py`
  - `pycodex/core/session/turn/request.py`
  - `pycodex/core/session/turn/runtime.py`
  - `pycodex/core/session/turn/sampler.py`
- Change:
  - Moved the old root-level session/turn runtime files into Rust-aligned `core/session` coordinates.
  - Rewrote imports from the old `pycodex.core.session_runtime` and `pycodex.core.turn_*` paths to the new canonical package paths.
  - Removed old root-level file coordinates instead of keeping duplicate aliases.
  - Repaired a Windows encoding side effect in `tests/test_exec_local_runtime.py` where multibyte UTF-8 string literals had been damaged during path rewrite.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - New canonical module import smoke: passed.
  - `python -m pytest tests/test_core_session_runtime.py tests/test_core_turn_prompt.py tests/test_core_turn_request.py tests/test_core_turn_runtime.py tests/test_core_turn_sampler.py tests/test_core_http_transport.py tests/test_exec_local_runtime.py tests/test_core_codex_thread.py tests/test_core_codex_thread_unittest.py tests/test_core_compact_remote.py tests/test_core_compact_remote_v2.py`: `527 passed`.
- Scope note:
  - This batch keeps the Python session/turn implementation as coarse runtime modules for now. It does not yet split `turn/runtime.py` internally into all Rust `turn.rs` sub-concepts.

## 2026-06-06 - canonical migration batch 30: plugin rendering and context manager updates

- Rust anchors:
  - `codex/codex-rs/core/src/plugins/render.rs`
  - `codex/codex-rs/core/src/context_manager/updates.rs`
- Python targets:
  - `pycodex/core/plugins/render.py`
  - `pycodex/core/context_manager/updates.py`
- Change:
  - Moved the old root-level `pycodex/core/app_plugin_rendering.py` into the Rust-aligned plugin rendering coordinate.
  - Moved the old root-level `pycodex/core/context_updates.py` into the Rust-aligned context manager updates coordinate.
  - Created `pycodex/core/context_manager/__init__.py` for the new package coordinate.
  - Rewrote imports to the new canonical paths.
  - Removed old root-level file coordinates instead of keeping duplicate aliases.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - New canonical module import smoke: passed.
  - `python -m pytest tests/test_core_context_updates.py tests/test_core_context.py tests/test_core_plugin_mentions.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_core_http_transport.py`: `286 passed`.
- Scope note:
  - This batch is coordinate consolidation only. `http_transport.py` remains at `pycodex/core/http_transport.py` because no direct Rust coordinate exists and it functions as a Python stdlib transport adapter.

## 2026-06-06 - canonical migration batch 31: http transport adapter package

- Functional Rust anchors:
  - `codex/codex-rs/core/src/client.rs`
  - `codex/codex-rs/core/src/client_common.rs`
  - `codex/codex-rs/core/src/responses_retry.rs`
  - `codex/codex-rs/core/src/session/turn.rs`
  - `codex/codex-rs/protocol/src/protocol.rs`
- Python target:
  - `pycodex/core/http_transport/__init__.py`
  - `pycodex/core/http_transport/README.md`
- Change:
  - Converted the old root-level `pycodex/core/http_transport.py` module into a dedicated `pycodex/core/http_transport/` package.
  - Preserved the public import path `pycodex.core.http_transport`.
  - Added a package README documenting why this Python adapter has no single Rust file coordinate and which Rust behavior slices it corresponds to.
  - Removed the old root-level file coordinate.
- Validation:
  - Package import smoke: passed.
  - Old file absent, new package initializer and README present.
  - `python -m pytest tests/test_core_http_transport.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_exec_local_runtime.py`: `454 passed`.
- Scope note:
  - This package is intentionally documented as a Python stdlib HTTP/SSE compatibility adapter spanning client, retry, protocol, and turn sampling behavior.

## 2026-07-05 - TUI terminal runtime decomposition: insert-history writer state

- Rust anchors:
  - `codex/codex-rs/tui/src/tui.rs`
  - `codex/codex-rs/tui/src/insert_history.rs`
  - `codex/codex-rs/tui/src/app/resize_reflow.rs`
- Python targets:
  - `pycodex/tui/tui/terminal_runtime.py`
  - `pycodex/tui/insert_history.py`
  - `tests/test_tui_insert_history.py`
- Change:
  - Added `TerminalHistoryWriter` to `pycodex/tui/insert_history.py` as a small stateful adapter for the real-terminal scrollback product path.
  - Moved retained history state ownership, generic history output, finalized history-cell output, replayed row insertion, assistant stream open/delta/finalization, and wrap-width calculation out of `TerminalTuiRunner`.
  - Kept terminal runtime responsible only for environment callbacks such as active-terminal state, terminal columns, resize checks, bottom-pane clearing/rendering, and history-bottom-row calculation.
  - Removed runner-private `_history_state`, `_insert_history_lines`, and `_open_assistant_stream_cell` glue.
- Validation:
  - `python -m py_compile pycodex/tui/insert_history.py tests/test_tui_insert_history.py pycodex/tui/tui/terminal_runtime.py`: passed.
  - `python -m pytest tests/test_tui_insert_history.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `81 passed`.
  - Broader TUI regression group: `565 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 528.
- Scope note:
  - The terminal product path is much closer to the Rust-aligned boundary split, but the overall goal is not complete yet. `terminal_runtime.py` still owns the main loop plus provider glue, status/live-pane orchestration, resize dispatch hooks, and command/turn wiring.

## 2026-07-05 - TUI terminal runtime decomposition: status-surface writer state

- Rust anchors:
  - `codex/codex-rs/tui/src/chatwidget/status_surfaces.rs`
  - `codex/codex-rs/tui/src/chatwidget/status_controls.rs`
  - `codex/codex-rs/tui/src/bottom_pane/mod.rs`
- Python targets:
  - `pycodex/tui/chatwidget/status_surfaces.py`
  - `pycodex/tui/tui/terminal_runtime.py`
  - `pycodex/tui/chatwidget/tests/test_status_surfaces.py`
- Change:
  - Added `TerminalStatusSurfaceWriter` to `chatwidget/status_surfaces.py` as a small stateful adapter for terminal live-status and active-turn status state.
  - Moved live-status text show/hide, turn-status render/refresh, turn-start timestamp, clear/suppress state effects, and apply-before-repaint ordering out of `TerminalTuiRunner`.
  - Removed runner-owned `_live_status`, `_turn_status`, `_turn_started_at`, and thin status wrapper methods.
  - Kept runner-owned environment callbacks for terminal activity, resize checks, bottom-pane render, and resize reflow.
- Validation:
  - `python -m py_compile pycodex/tui/chatwidget/status_surfaces.py pycodex/tui/chatwidget/tests/test_status_surfaces.py pycodex/tui/tui/terminal_runtime.py`: passed.
  - `python -m pytest pycodex/tui/chatwidget/tests/test_status_surfaces.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `38 passed`.
  - Broader TUI regression group: `568 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 481.
- Scope note:
  - `terminal_runtime.py` is thinner, but the overall goal remains active. Remaining non-main-loop responsibilities include provider glue, clear/header/status-card adapters, resize dispatch hooks, input/composer glue, event handling glue, and shutdown wiring.

## 2026-07-05 - TUI terminal runtime decomposition: resize coordinator state

- Rust anchors:
  - `codex/codex-rs/tui/src/app/resize_reflow.rs`
  - `codex/codex-rs/tui/src/app.rs`
  - `codex/codex-rs/tui/src/tui.rs`
- Python targets:
  - `pycodex/tui/app/resize_reflow.py`
  - `pycodex/tui/tui/terminal_runtime.py`
  - `pycodex/tui/app/tests/test_resize_reflow.py`
- Change:
  - Added `TerminalResizeCoordinator` to `app/resize_reflow.py` as a small stateful adapter for terminal layout activation, deactivation, size-change repair, bottom-pane footprint repair, and stream-finish replay dispatch.
  - Moved `_layout_active`, `_resize_state`, `_resize_reflow_pending`, recursive resize guard application, stream-finish pending replay, and resize plan dispatch out of `TerminalTuiRunner`.
  - Kept runner-owned callbacks for observed terminal size, active assistant stream state, scroll-region reset, bottom-pane render, retained-history viewport repaint, and scrollback replay.
- Validation:
  - `python -m py_compile pycodex/tui/app/resize_reflow.py pycodex/tui/app/tests/test_resize_reflow.py pycodex/tui/tui/terminal_runtime.py`: passed.
  - `python -m pytest pycodex/tui/app/tests/test_resize_reflow.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `70 passed`.
  - Broader TUI regression group: `571 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 445.
- Scope note:
  - The resize/layout state boundary is now in `app::resize_reflow`. The overall goal remains active because runner still contains provider glue, clear/header/status-card wiring, composer/input glue, event dispatch glue, assistant-delta/finalization glue, and shutdown behavior.

## 2026-07-05 - TUI terminal runtime decomposition: assistant stream writer state

- Rust anchors:
  - `codex/codex-rs/tui/src/history_cell/messages.rs`
  - `codex/codex-rs/tui/src/chatwidget/streaming.rs`
  - `codex/codex-rs/tui/src/chatwidget/protocol.rs`
- Python targets:
  - `pycodex/tui/history_cell/messages.py`
  - `pycodex/tui/tui/terminal_runtime.py`
  - `pycodex/tui/history_cell/tests/test_messages.py`
- Change:
  - Added `TerminalAssistantStreamWriter` to `history_cell/messages.py` as a small stateful adapter for terminal assistant stream state.
  - Moved assistant stream active state, reset/apply-state behavior, delta open/write dispatch, projection finalization, and stream-finish reflow callback sequencing out of `TerminalTuiRunner`.
  - Kept runner-owned callbacks for wrap width, insert-history stream open/delta/final projection, resize-reflow stream finish repair, and protocol event dispatch.
- Validation:
  - `python -m py_compile pycodex/tui/history_cell/messages.py pycodex/tui/history_cell/tests/test_messages.py pycodex/tui/tui/terminal_runtime.py`: passed.
  - `python -m pytest pycodex/tui/history_cell/tests/test_messages.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `45 passed`.
  - Broader TUI regression group: `574 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 433.
- Scope note:
  - Assistant stream state is now owned by `history_cell::messages`. The overall goal remains active because runner still contains provider glue, clear/header/status-card wiring, composer/input glue, protocol effect dispatch glue, and shutdown behavior.

## 2026-07-05 - TUI terminal runtime decomposition: provider-backed display adapters

- Rust anchors:
  - `codex/codex-rs/tui/src/app/history_ui.rs`
  - `codex/codex-rs/tui/src/history_cell/session.rs`
  - `codex/codex-rs/tui/src/bottom_pane/footer.rs`
  - `codex/codex-rs/tui/src/status/card.rs`
- Python targets:
  - `pycodex/tui/app/history_ui.py`
  - `pycodex/tui/history_cell/session.py`
  - `pycodex/tui/bottom_pane/footer.py`
  - `pycodex/tui/status/card.py`
  - `pycodex/tui/tui/terminal_runtime.py`
- Change:
  - Added provider-backed terminal adapters in the owning display modules:
    `run_terminal_session_header_from_runtime`,
    `run_terminal_startup_notices_from_runtime`,
    `run_terminal_idle_footer_text_from_runtime`, and
    `run_terminal_status_card_from_runtime`.
  - Removed direct private `textual_runtime` provider imports for header,
    startup notices, idle footer, and `/status` card from `TerminalTuiRunner`.
  - Kept the runner responsible only for invoking these boundaries with
    app-runtime and history-writer callbacks.
- Validation:
  - `python -m py_compile pycodex/tui/app/history_ui.py pycodex/tui/history_cell/session.py pycodex/tui/bottom_pane/footer.py pycodex/tui/status/card.py pycodex/tui/tui/terminal_runtime.py pycodex/tui/app/tests/test_history_ui.py pycodex/tui/history_cell/tests/test_session.py pycodex/tui/bottom_pane/tests/test_footer.py pycodex/tui/status/tests/test_card.py`: passed.
  - `python -m pytest pycodex/tui/app/tests/test_history_ui.py pycodex/tui/history_cell/tests/test_session.py pycodex/tui/bottom_pane/tests/test_footer.py pycodex/tui/status/tests/test_card.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `74 passed`.
  - Broader TUI regression group: `578 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 398.
- Scope note:
  - Provider-backed display assembly is now owned by Rust-aligned display
    modules. The overall goal remains active because `terminal_runtime.py`
    still contains main-loop glue plus composer/input callbacks, bottom-pane
    clear/render callbacks, resize history replay callbacks, protocol effect
    dispatch, clear command sequencing, and shutdown behavior.

## 2026-07-05 - TUI terminal runtime decomposition: bottom-pane surface writer

- Rust anchors:
  - `codex/codex-rs/tui/src/bottom_pane/mod.rs`
  - `codex/codex-rs/tui/src/bottom_pane/chat_composer.rs`
  - `codex/codex-rs/tui/src/bottom_pane/footer.rs`
  - `codex/codex-rs/tui/src/tui.rs`
- Python targets:
  - `pycodex/tui/bottom_pane/terminal_surface.py`
  - `pycodex/tui/tui/terminal_runtime.py`
  - `pycodex/tui/bottom_pane/tests/test_terminal_surface.py`
- Change:
  - Added `TerminalBottomPaneSurfaceWriter` to the bottom-pane terminal
    surface boundary.
  - Moved terminal composer draft storage, live-pane history-bottom-row
    calculation, bottom-pane clear, and bottom-pane render callback assembly
    out of `TerminalTuiRunner`.
  - Kept the runner responsible for supplying terminal state, resize callback,
    live-status state, and footer runtime provider.
- Validation:
  - `python -m py_compile pycodex/tui/bottom_pane/terminal_surface.py pycodex/tui/tui/terminal_runtime.py`: passed.
  - `python -m pytest pycodex/tui/bottom_pane/tests/test_terminal_surface.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `40 passed`.
  - Broader TUI regression group: `579 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 370.
- Scope note:
  - Bottom-pane terminal surface state is now owned by `bottom_pane`.
    The overall goal remains active because `terminal_runtime.py` still
    contains main-loop glue plus event-stream/protocol effect dispatch,
    resize history replay callbacks, clear command state application, and
    shutdown behavior.

## 2026-07-05 - TUI terminal runtime decomposition: protocol event dispatcher

- Rust anchors:
  - `codex/codex-rs/tui/src/chatwidget/protocol.rs`
  - `codex/codex-rs/tui/src/chatwidget/streaming.rs`
  - `codex/codex-rs/tui/src/tui/event_stream.rs`
- Python targets:
  - `pycodex/tui/chatwidget/protocol.py`
  - `pycodex/tui/chatwidget/tests/test_protocol.py`
  - `pycodex/tui/tui/terminal_runtime.py`
- Change:
  - Added `TerminalProtocolEventDispatcher` to the protocol boundary.
  - Moved terminal notification effect-plan application and turn-close cleanup
    dispatch out of `TerminalTuiRunner`.
  - Kept runner-owned wiring limited to passing status, live-status, assistant
    stream, history writer, and app-runtime notification callbacks into the
    dispatcher.
- Validation:
  - `python -m py_compile pycodex/tui/chatwidget/protocol.py pycodex/tui/tui/terminal_runtime.py`: passed.
  - `python -m pytest pycodex/tui/chatwidget/tests/test_protocol.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `43 passed`.
  - Broader TUI regression group: `580 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 357.
- Scope note:
  - Terminal server-notification action/effect sequencing is now owned by
    `chatwidget::protocol`. The overall goal remains active because
    `terminal_runtime.py` still contains main-loop glue plus resize replay
    callbacks, clear command state application, input-source storage, local
    command callbacks, and shutdown behavior.

## 2026-07-05 - TUI terminal runtime decomposition: clear state applicator

- Rust anchors:
  - `codex/codex-rs/tui/src/app/history_ui.rs`
  - `codex/codex-rs/tui/src/app.rs`
- Python targets:
  - `pycodex/tui/app/history_ui.py`
  - `pycodex/tui/app/tests/test_history_ui.py`
  - `pycodex/tui/tui/terminal_runtime.py`
- Change:
  - Added `run_terminal_clear_application_state` to the app/history-ui
    boundary.
  - Moved clear-state application ordering for history state, assistant-stream
    state, and resize-pending state out of `TerminalTuiRunner`.
  - Kept runner-owned wiring limited to passing the concrete state sinks.
- Validation:
  - `python -m py_compile pycodex/tui/app/history_ui.py pycodex/tui/app/tests/test_history_ui.py pycodex/tui/tui/terminal_runtime.py`: passed.
  - `python -m pytest pycodex/tui/app/tests/test_history_ui.py pycodex/tui/tui/tests/test_terminal_runtime.py -q`: `35 passed`.
  - Broader TUI regression group: `581 passed`.
  - `rg "scrollback_runtime|run_scrollback_tui|ScrollbackTuiRunner" pycodex tests --glob "*.py" --glob "!**/__pycache__/**"`: no matches.
  - `pycodex/tui/tui/terminal_runtime.py` line count after this slice: 356.
- Scope note:
  - Clear-state reset semantics are now fully in `app::history_ui`. The
    overall goal remains active because `terminal_runtime.py` still contains
    main-loop glue plus resize replay callbacks, input-source storage, local
    command callbacks, and shutdown behavior.

## 2026-07-12 - TUI user-input and MCP form approval product path

- Fixed Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Added canonical app-server parameter conversion for
  `ToolRequestUserInput` and `McpServerElicitationRequest` in
  `chatwidget::protocol_requests`.
- Connected both request types through `chatwidget::tool_requests`, owner
  projectors, the shared `BottomPaneView` stack, typed `AppCommand` responses,
  and `app::app_server_requests` correlation.
- User-input responses now use the turn id and canonical typed response, append
  `user_note:` exactly as fixed Rust does, and insert one
  `RequestUserInputResultCell`.
- Same-type user-input and MCP form requests queue FIFO in their owning views;
  external resolution and resume replay preserve item/request identity.
- Approval-related owner modules are now explicit critical entries in
  `tui_alignment.py`; the guard prohibits terminal-runtime request branches.
- Validation: focused owner/product suite `150 passed`; terminal product tests
  `45 passed`; alignment guard `31 passed`.
- Follow-up connected valid MCP URL elicitation through the Rust-owned
  `AppLinkView`, `OpenUrlInBrowser` app event, and typed elicitation resolution.
- Remaining: side-thread/open-thread actions, global interrupt arbitration, and
  Milestone 5 snapshot/ConPTY/manual parity.
## 2026-07-12 - TUI guardian and auto-review product closure

- Fixed Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Connected guardian app-server notifications to the product
  `chatwidget::protocol_requests -> tool_requests` dynamic path.
- Replaced guardian-only status/history DTO projection with shared status
  state, canonical denial storage, and typed approval history cells.
- Registered `/approve` through the shared slash-command view dispatcher and
  routed one-shot denial retry through typed
  `AppCommand::ApproveGuardianDeniedAction` into core model history.
- Covered parallel review aggregation and Approved, Denied, TimedOut, and
  Aborted terminal states without exposing hidden chain-of-thought.
- Validation: focused owner/product tests `95 passed`; alignment guard `31
  passed`; full TUI suite `2366 passed, 59 skipped`.
- Approval alignment remains in progress: waiting/title, complete human audit
  history, footprint stability, and ConPTY visual parity are still open.
- Follow-up connected `BottomPaneView` action-required state to the managed OSC
  terminal title, routed canonical approval notifications through the existing
  BEL/OSC backend, and added fixed-Rust typed exec/network plus plain
  permissions decision history. The second full TUI regression run passed:
  `2369 passed, 59 skipped`.

## 2026-07-12 - TUI inactive-thread approval routing

- Fixed Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Routed app-server requests through `app::app_server_events` and
  `app::thread_routing` before chatwidget projection.
- Inactive exec, patch, permissions, and MCP requests retain their source
  thread identity and use Rust-owned interactive views with thread labels.
- Added bottom-pane pending-thread approval rows and typed
  `SelectAgentThread` execution; non-eager user-input requests replay once
  after selecting their source thread.
- Fixed `ThreadEventStore` coercion so chatwidget `ServerRequest.id` survives
  as the canonical replay/correlation request id.
- Aligned MCP Esc/Ctrl+C behavior: text Ctrl+C clears the draft first, while
  cancellation closes the queued overlay instead of advancing it.
- Added app-server/thread-routing/thread-events/event-dispatch and pending-row
  owners to `tui_alignment.py`; alignment guard passes (`31 passed`).
- Remaining: active side-parent suppression/discard, global interrupt
  arbitration, and Milestone 5 snapshot/ConPTY/manual parity.
- Follow-up connected both remaining Milestone 4 routing gaps: active side
  conversations suppress inactive request overlays until return/switch,
  successful switches close the side runtime and replay the target request,
  and turn-time Ctrl+C/Esc now use fair server/input arbitration with deferred
  ordinary input replay. Focused owner/product tests passed (`242 passed`).

## 2026-07-13 - TUI permission status uses the canonical profile

- Fixed Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Aligned `codex-tui::status::card::status_permission_summary`: `/status` now
  derives its sandbox summary from the current canonical `PermissionProfile`,
  matching Rust, rather than preferring a stale legacy startup
  `sandbox_mode`.
- Aligned built-in profile IDs with Rust constants (`:read-only`,
  `:workspace`, and `:danger-full-access`) while retaining legacy aliases at
  the display boundary.
- Added a regression for the Read Only -> Default transition where the
  canonical profile is workspace-write but the legacy startup field remains
  read-only. The expected status is `Workspace (on-request)`.
- Validation: status/permissions/app/terminal owner group `162 passed`;
  alignment and sandbox-summary group `32 passed`.

## 2026-07-13 - Shell tool feature selection follows the Rust resolver

- Fixed Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Reconnected `codex-tools::tool_config::shell_type_for_model_and_features`
  to the Python `core::tools::spec_plan` product path. The planner no longer
  reads the nonexistent `config.use_unified_exec` field and silently defaults
  to unified exec.
- `--disable unified_exec` now exposes the legacy `shell_command` schema with
  its hard `timeout_ms` contract; unified exec still exposes `exec_command`
  and `write_stdin`, and disabling `shell_tool` exposes neither family.
- Removed the second, conflicting shell-family decision in
  `exec::local_runtime::LocalHttpShellToolRouter`. The real session Responses
  request now consumes the same model/feature result as core `spec_plan`
  instead of unconditionally reinserting `exec_command` and `write_stdin`.
- Closed the remaining interactive TUI gap: the exec session feature facade
  now preserves canonical CLI features, and the core default environment tool
  builder delegates to the same Rust-aligned shell-family selector instead of
  unconditionally registering unified exec.
- This restores a valid Windows Job Object descendant-termination acceptance
  path without adding a TUI or command-specific workaround.
- Validation: the local HTTP request and the core request used by interactive
  TUI turns both contain `shell_command` and `timeout_ms` with no unified-exec
  companions. The root CLI feature-propagation test and the broader
  core/TUI/alignment group pass (`502 passed`); the earlier local-runtime and
  CLI/features/config/tools group remains `915 passed, 2 skipped, 105 subtests
  passed`.

## 2026-07-14 - TUI active command completion clears its previous footprint

- Fixed Rust baseline: `1c7832ffa37a3ab56f601497c00bfce120370bf9`.
- Confirmed the `chatwidget::command_lifecycle` contract against
  `exec_history_cell_shows_working_then_completed`: command start remains a
  mutable active cell, while completion takes that cell and inserts exactly
  one finalized history cell.
- Fixed the Python hybrid backend transition where `app::resize_reflow`
  remembered the old active-tail footprint but dropped it when constructing
  the bottom-pane clear request. The stale live command could therefore remain
  visible beside the finalized `Ran` history cell.
- Clear requests now carry the previous popup, active-tail, composer, and live
  status footprint through bottom-pane projection into `custom_terminal`.
  This is a shared live-viewport lifecycle fix, not a command-specific branch.
- Validation: footprint/action/projection/terminal product group `164 passed`;
  command lifecycle and alignment guard group `49 passed`.

## 2026-07-14 - Evidence consolidation and current completion snapshot

- Removed the per-turn migration log as an active evidence system. Historical
  details remain available in Git history; current claims must cite Rust
  source/tests, Python owner tests, module `README.md` files, or focused
  alignment documents.
- TUI parity remains pinned to Rust commit
  `1c7832ffa37a3ab56f601497c00bfce120370bf9`; `tui_alignment.py` and its guard
  enforce that immutable coordinate.
- The real terminal TUI follows the module-owner path `event_stream -> tui/app
  runtime -> chat_composer/BottomPaneView -> Frame/Buffer -> custom_terminal ->
  scrollback + live viewport`. Approval, typed command history, shell-command
  projection, and active-to-final command footprint transitions are connected
  through their shared owners rather than terminal-specific branches.
- Windows Sandbox native enforcement, permission/status projection, approval
  recovery, network-profile isolation, timeout/cancellation, and Job Object
  descendant termination passed the recorded Windows Terminal acceptance.
- The canonical evidence for these claims is maintained in
  `pycodex/tui/APPROVAL_ALIGNMENT.md`, `WINDOWS_SANDBOX_ALIGNMENT.md`,
  `WINDOWS_SANDBOX_PARITY_EVIDENCE.md`,
  `WINDOWS_SANDBOX_MANUAL_ACCEPTANCE.md`, and the Rust-derived regression
  tests named by those documents.
