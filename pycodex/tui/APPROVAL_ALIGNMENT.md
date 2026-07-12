# Terminal TUI Approval Alignment

## Purpose

This document is the implementation and acceptance baseline for interactive
approval behavior in the Python terminal TUI. It is intentionally narrower
than `AGENTS.md` and `PORTING_PROJECT_PRINCIPLES.md`: those files define the
project methodology, while this file records the approval-specific ownership
map, product-path gaps, implementation order, and parity evidence.

The only Rust behavior baseline is commit:

```text
1c7832ffa37a3ab56f601497c00bfce120370bf9
```

Do not update `codex/` or use newer upstream behavior as parity evidence for
this work.

## Completion Rule

A Python approval module is not aligned merely because its DTOs, helper
functions, or isolated unit tests exist. Approval parity requires the complete
interactive terminal session path:

```text
policy decision
  -> typed approval request
  -> chatwidget request owner
  -> active BottomPaneView
  -> task-time keyboard input
  -> AppEvent / AppCommand response
  -> pending operation resume
  -> typed audit history
```

Use these status markers throughout this document:

- `[ ]` missing
- `[~]` partial, semantic-only, or disconnected from the product path
- `[x]` aligned on the real terminal product path
- `[!]` intentionally out of scope or blocked

No row may move to `[x]` without a product-path test. Owner-level unit tests
alone are necessary evidence, but not sufficient acceptance evidence.

## Rust Ownership Map

| Responsibility | Rust owner | Python owner | Current status |
| --- | --- | --- | --- |
| Approval request protocol types | `codex-protocol::approvals` and app-server protocol | `pycodex.protocol.approvals`, `pycodex.tui.approval_events` | `[x]` Exec, patch, permissions, and guardian notifications use canonical protocol types on the terminal product path. |
| Server request routing | `codex-tui::chatwidget::protocol_requests` | `pycodex.tui.chatwidget.protocol_requests` | `[x]` CoreExec and app-server-shaped requests share the typed ChatWidget owner boundary. |
| Request lifecycle and deferral | `codex-tui::chatwidget::tool_requests` | `pycodex.tui.chatwidget.tool_requests`, `interrupts` | `[x]` The product ChatWidget composes the owner, active views, pending replay, external resolution, interruption, and guardian lifecycle. |
| Approval UI and decisions | `codex-tui::bottom_pane::approval_overlay` | `pycodex.tui.bottom_pane.approval_overlay` | `[x]` The product overlay is a generic active view and emits typed app commands. |
| Selection and key routing | `codex-tui::bottom_pane::list_selection_view` | `pycodex.tui.bottom_pane.list_selection_view`, `view_stack` | `[x]` Approval navigation, highlight, and Enter use the shared list/view stack. |
| App event conversion | `codex-tui::app_event_sender`, `app_command` | `pycodex.tui.app_event_sender`, `app_command` | `[x]` Exec, patch, and permissions selections return through typed app commands. |
| Submitted-turn input | `codex-tui::tui::event_stream`, `app::input` | `pycodex.tui.tui.event_stream`, `terminal_runtime` | `[x]` The active-view path multiplexes the shared terminal input source with turn events. |
| Pending request replay | `codex-tui::app::pending_interactive_replay` | `pycodex.tui.app.pending_interactive_replay` | `[x]` Snapshot replay restores only unresolved typed requests through the normal active-view queue and deduplicates request ids. |
| Approval status and audit history | `chatwidget::tool_requests`, `history_cell`, terminal title | `chatwidget.tool_requests`, `status_surfaces`, `history_cell` | `[x]` Guardian and human decisions reach their fixed-Rust typed/plain history projections; requires-action title is product-connected. |

Python-only terminal adapters may translate Windows, ANSI, input-source, and
hybrid scrollback details. They must not decide whether an operation needs
approval, choose approval options, interpret decisions, or own request queue
semantics.

## Confirmed Product-Path Gaps

### P0: Requests cannot reach an interactive view

- `[x]` The CoreExec path installs an exec approval callback and blocks on a
  pending decision.
- `[x]` The callback emits a Rust-like typed
  `CommandExecutionRequestApproval` request; the Python-only
  `ExecApprovalRequested` notification has been removed.
- `[x]` `chatwidget.protocol_requests` parses exec, patch, and permissions
  requests into canonical protocol events and routes them through the product
  `ChatWidgetProtocolRuntime` tool-request owner.
- `[x]` The product ChatWidget projection pushes an `ApprovalOverlay` onto the active
  bottom-pane view stack.

### P0: No keyboard input while a turn is waiting

- `[x]` The submitted-turn loop polls the shared terminal input source while an
  active view requires input, alongside model/server events and idle ticks.
- `[x]` Up/Down, Enter, approval shortcuts, Esc, and Ctrl+C route through the
  active bottom-pane view while the agent turn remains active.
- `[x]` Input arbitration is guarded by active-view presence, so normal
  streaming does not consume future composer input.

### P0: Decisions do not resume the pending operation

- `[x]` Approval selection routes through `AppEventSender`, `AppCommand`, and
  `TuiAppRuntime` to the pending CoreExec operation.
- `[x]` Exec, patch, and permissions each have typed pending-request resolution
  and same-turn resume tests.
- `[x]` Command/file decisions use core `ReviewDecision`; incremental
  permissions use `RequestPermissionsResponse`.
- `[x]` Session-scoped command and patch approvals use the shared
  `tools::sandboxing::ApprovalStore` contract with Rust-shaped keys; incremental
  permissions persist their merged session profile across turns.
- `[x]` Multi-turn tests prove matching-key reuse, different-key prompting,
  denial non-caching, and fresh-store isolation for a new session runtime.

### P1: Approval overlay behavior is incomplete

- `[x]` The Python overlay composes the shared `ListSelectionView`.
- `[x]` Selected-row state, Up/Down navigation, highlighting, and Enter use the
  shared list owner.
- `[x]` Key-name normalization follows the terminal composer/view-stack path.
- `[x]` Shortcuts, cancellation, LIFO queueing, external-resolution dismissal,
  and action-required terminal-title lifecycle are active.
- `[x]` Full-screen approval uses the static alternate-screen pager, and
  inactive-thread approvals emit typed `SelectAgentThread` through the app
  executor.
- `[x]` Queue ordering, current-request replacement, external resolution, and
  interruption have Rust-derived product tests.

### P1: Request categories are uneven

| Category | Request production | Interactive view | Decision round trip | Audit history |
| --- | --- | --- | --- | --- |
| Command execution | `[x]` typed callback | `[x]` | `[x]` | `[x]` typed user decision |
| File change | `[x]` local tool callback | `[x]` | `[x]` | `[!]` fixed Rust emits no patch decision cell |
| Incremental permissions | `[x]` core callback | `[x]` | `[x]` | `[x]` fixed-Rust plain decision cell |
| Network access | `[x]` typed core-session producer preserves context, amendments, decisions, and additional permissions | `[x]` | `[x]` | `[x]` typed exec/network decision |
| Guardian/auto-review | `[x]` canonical notification | `[x]` `/approve` denial view | `[x]` typed exact-action retry | `[x]` typed terminal result |
| MCP elicitation | `[x]` canonical app-server params | `[x]` form/approval and URL app-link views | `[x]` typed decision and request-id correlation | `[!]` fixed Rust emits no elicitation decision cell |
| Tool user input | `[x]` canonical thread/turn/item request | `[x]` shared product view and FIFO queue | `[x]` typed answer and request-id correlation | `[x]` typed result cell |

MCP form and URL elicitation now use their Rust-owned product views and the
shared app-server correlation path. URL opening is an app event; terminal
runtime contains no MCP request branch.

### P1: Request payload fidelity

The product request must preserve all Rust-owned fields where applicable:

- effective approval id and call id
- thread id and turn id
- command tokens and cwd
- reason
- available decisions
- exec-policy amendment
- network approval context
- network-policy amendments
- additional permission profile
- patch changes and grant root
- requested permission profile and grant scope

`ExecSessionConfig` now installs the core-session command and patch approval
callbacks. The typed command bridge preserves distinct call/approval ids,
argv tokens, cwd, reason, network context, allow/deny network amendments,
additional permissions, and supplied decisions before projecting one canonical
app-server request. Patch and permissions retain their category-specific typed
payloads and correlation ids. Product tests exercise this bridge rather than a
custom terminal notification.

### P2: User-visible lifecycle and recovery

- `[x]` Approval-required desktop notification and terminal-title action state.
- `[!]` Fixed Rust uses the ambient-pet `Waiting` state plus the action-required
  terminal title, not a synthetic `Waiting` footer. The title and notification
  product paths are connected. Python's hybrid terminal has no ambient-pet
  surface, so this optional presentation is intentionally not synthesized in
  the terminal adapter and is not an approval lifecycle gap.
- `[x]` Auto-review terminal results and exec accepted, session, denied, and
  cancelled decisions use typed history cells. Permissions use the fixed-Rust
  plain decision messages. Patch and MCP intentionally emit no decision cell
  at this commit.
- `[x]` Multiple-request LIFO queue behavior.
- `[x]` Dismissal when another client resolves the current or queued request.
- `[x]` Turn interruption aborting every pending request category exactly once.
- `[x]` Resume/replay restoring only unresolved interactive requests.
- `[x]` Inactive-thread requests are stored under their source thread, approval
  views carry Rust labels, the bottom pane lists pending approval threads, and
  `o` switches through typed `SelectAgentThread`. Active side-parent requests
  remain buffered until return/switch, and successful switching closes and
  discards the side thread before replaying the target's pending requests.
- `[x]` Resize and scrollback stability while approval footprint changes;
  product tests preserve prompt identity through modal growth and physical
  resize, then assert one completed decision and no stale overlay.

## Permission-Mode Contract

The absence of an approval prompt is not always a defect. Product tests must
first establish the effective approval policy and permission profile:

- Full Access, YOLO, or `approval_policy=never` normally suppresses prompts.
- Default permits normal workspace writes but may require approval for risky
  commands, writes outside allowed roots, network access, or additional
  permissions.
- Read Only must not silently grant writes.
- Auto-review may resolve a request without a human prompt, but its status,
  result, denial record, and retry behavior must still match Rust.

A policy test proves whether a request should be produced. A TUI test proves
that a produced request can be displayed and resolved. Do not combine these
into one ambiguous assertion.

## Implementation Milestones

### Milestone 1: Typed request boundary

- [x] Replace the custom exec-only terminal notification with a shared typed
  interactive request envelope.
- [x] Route exec, patch, and permissions requests through the corresponding
  `chatwidget` owner.
- [x] Preserve the full request payload and fixed-Rust default decisions.
- [x] Add an alignment guard forbidding approval display semantics in terminal
  runtime adapters.

Exit gate: complete. Deterministic owner/product-boundary tests prove typed
requests reach the ChatWidget owner without becoming normal notifications or
user turns. Focused approval/protocol/runtime/alignment tests passed (`195
passed`), and the complete TUI regression group passed (`2437 passed, 59
skipped`).

### Milestone 2: Task-time input and active view

- [x] Multiplex submitted-turn server events, terminal input, resize, and idle
  ticks through one Rust-like event loop.
- [x] Add a public framework-level API for pushing a generic
  `BottomPaneView`.
- [x] Rebuild `ApprovalOverlay` on `ListSelectionView` and the shared view
  stack.
- [x] Route Up/Down, Enter, shortcuts, Esc, and Ctrl+C to the active view.

Exit gate: complete. A real terminal product test pauses an active turn, moves
the shared-list highlight, selects the command decision, emits
`AppCommand::ExecApproval`, and resumes to `TurnCompleted`.

### Milestone 3: Decision round trip

- [x] Convert overlay decisions through `AppEventSender` and `AppCommand`.
- [x] Resolve exec, patch, and permissions pending requests exactly once.
- [x] Resume the blocked tool operation after acceptance and terminate it
  correctly after decline, cancel, timeout, or interruption.
- [x] Apply session-scoped grants only to the intended session. Shell keys
  include command/cwd/sandbox/additional permissions, patch keys include local
  environment and absolute path, and a new runtime receives a fresh store.

Exit gate: complete. Same-turn accept/cancel mechanics are covered for all
three categories, and session grant persistence/cache isolation is covered
across turns and fresh runtimes.

### Milestone 4: Queue, replay, status, and history

- [x] Connect request deferral, queue ordering, external resolution dismissal,
  resume replay, and turn interruption.
  The terminal bottom-pane owner now offers new approval requests to the active
  view before pushing another overlay, so `ApprovalOverlay` owns Rust's LIFO
  queue across exec, patch, and permissions. `TuiAppRuntime` now owns
  `PendingAppServerRequests`, preserves typed request ids, correlates
  `ServerRequestResolved` to the semantic approval identity, and dismisses the
  current or queued request through the bottom-pane owner. Thread snapshots now
  rebuild `ThreadEventStore`, filter resolved interactive requests, suppress
  duplicate request-id projection, replay pending requests through the normal
  chatwidget path into one ApprovalOverlay queue, and clear both replay and
  app-server correlation state on outbound decisions. Tool user-input and MCP
  form requests now pass through canonical protocol DTOs, their Rust-owned
  active views, same-type FIFO consumption, external dismissal, replay
  suppression, and typed AppCommand correlation. Local Core interruption
  now wakes exec, patch, and permissions waiters, emits one request-resolution
  notification per pending id before interrupted TurnCompleted, clears the
  active overlay through the standard dismiss path, and permits a subsequent
  turn. Approval-specific Exec/Patch `ReviewDecision::Abort` now follows fixed
  Rust `core::session::handlers` into that same turn-interruption path instead
  of becoming an ordinary failed tool response. The interrupted-turn notice is
  a typed error cell submitted through `HistoryProjectionSink`, not an internal
  semantic-only list. Inactive-thread approval/MCP requests now surface through
  the app thread-routing owner with source labels, while user-input is replayed once
  after its source thread becomes active. Pending-thread rows use
  `bottom_pane::pending_thread_approvals`; request coercion preserves the
  original app-server request id. Turn-time input now gives ready server events
  a fair dispatch slot, active views receive `BottomPaneView::on_ctrl_c`,
  Ctrl+C/Esc submit typed Interrupt only after bottom-pane/side-return refusal,
  and non-interrupt keys consumed during a turn replay into the next composer.
- [x] Connect guardian/auto-review status and denial retry behavior.
  App-server guardian notifications now enter the canonical protocol event,
  `chatwidget::tool_requests`, shared guardian status state, typed approval
  history cells, and the shared recent-denial store. `/approve` is registered
  through `chatwidget::slash_dispatch`; selecting a denial emits typed
  `AppCommand::ApproveGuardianDeniedAction`, consumes it once, and injects the
  fixed-Rust exact-action developer approval into the core model history.
  Product tests cover parallel reviews plus Approved, Denied, TimedOut, and
  Aborted terminal states. Hidden chain-of-thought is never projected.
- [x] Add waiting status, terminal-title action state, notification behavior,
  and typed audit history.
  Approval views now project `BottomPaneView::terminal_title_requires_action`
  to the managed `[ ! ] Action Required` OSC title and restore the title when
  the view completes, is cancelled, is externally resolved, or the TUI shuts
  down. Exec/edit/elicitation requests use canonical notification values and
  the existing BEL/OSC backend. Exec/network and permissions decisions now
  enter canonical history before their typed response, with Cancel mapped to
  Rust `ReviewDecision::Abort`. Tool user-input completion inserts the fixed-Rust
  `RequestUserInputResultCell`; patch and MCP intentionally insert no decision
  cell at this commit. Optional ambient-pet presentation remains outside the
  terminal adapter.
- [x] Verify footprint changes do not erase or duplicate scrollback.

Exit gate: complete. Multiple and resumed requests preserve order and identity,
the transcript records one stable decision result per request where the fixed
Rust commit owns such a cell, and completion/cancellation/external resolution
clear the managed action-required title. Owner and product-path approval tests
pass (`406 passed` across the latest focused approval, protocol, replay,
runtime, composer-input, and core-session groups), and the complete TUI suite
passes (`2401 passed, 64 skipped`).

### Milestone 5: Visual and ConPTY parity

- [x] Align command highlighting, reason text, permission detail, patch diff,
  network target, selected-row styling, and footer hints with Rust snapshots.
- [x] Compare raw VT, normalized text, current screen, and decision outcome in
  fixed Rust/Python interactive ConPTY sessions.

Exit gate: complete for automated parity. Snapshot-derived tests cover exec,
patch, permissions, network, selected rows, footer hints, narrow Chinese text,
and multi-file patch history. Fixed-commit Rust/Python ConPTY fixtures cover
exec acceptance, exec cancellation with modal resize and next-turn Chinese
recovery, apply-patch acceptance, request-permissions acceptance, and a
session-scoped permission grant reused by an identical additional-permission
profile in a later turn without a second decision key. They verify modal
display, keyboard decisions, blocked-operation recovery or cancellation,
typed history, action-required title cleanup, post-modal input, and final turn
completion. The five fixtures pass together and save raw VT, normalized text,
and current-screen artifacts. The session-reuse comparison also exposed and
closed a shared `bottom_pane::chat_composer` parity gap: Python now flushes an
expired `PasteBurst` held character before every newly readable key, matching
fixed Rust `ChatComposer::handle_input_basic_with_time` and preventing ordinary
ASCII prefixes from disappearing after a modal. A final human Windows Terminal
smoke remains a project Goal acceptance step, not a reason to weaken this
automated gate.

## Required Regression Matrix

Every approval-framework change must cover the touched category plus an
adjacent category:

- Exec: accept once, accept for session where offered, amendment, decline,
  cancel, Ctrl+C.
- Patch: accept, accept for session, decline, cancel, multi-file diff.
- Permissions: grant for turn, strict auto-review, grant for session, deny.
- Network: accept once, accept for session, allow amendment, cancel.
- Queue: two requests, externally resolved current request, interruption,
  resume with only unresolved requests.
- Input: Up/Down, Enter, shortcuts, Esc, resize, IME text preservation.
- Product regressions: streaming, footer/composer stability, scrollback,
  slash popup, model/reasoning picker, and transcript overlay.

Each parity test must cite the fixed Rust source, test, or snapshot that owns
the behavior. Tests that only exercise Python DTOs or helper methods must be
labelled owner-level rather than product-path parity tests.

## Prohibited Shortcuts

- Do not add an exec-only polling branch to `terminal_runtime.py`.
- Do not make `/permissions` selections directly decide tool approvals.
- Do not render approval choices as terminal strings outside bottom-pane
  owners.
- Do not read keyboard input from a second competing input source.
- Do not mark `approval_overlay` complete while its product-path gate fails.
- Do not infer approval parity from isolated module tests.
- Do not change the fixed Rust baseline to make a Python behavior appear
  aligned.

## Current Baseline

At the time of this audit:

- Protocol and semantic coverage: complete for the fixed-commit approval scope.
- Real terminal product-path coverage: complete for automated fixed-commit
  approval fixtures; final human smoke is pending.
- Overall status: `[~]` only because final human Windows Terminal acceptance
  remains open. The automated implementation covers interactive core, session grants, queue/replay,
  interruption, guardian retry, user-input, MCP form, title/history, and
  footprint stability, MCP form/URL flows, inactive-thread labels, pending
  thread rows, open-thread selection, and full-screen approval are connected;
  visual/ConPTY parity are automated and passing; final human Windows Terminal
  acceptance remains open.

Milestones 1 through 5 are complete under automated evidence. Milestone 4 has active-overlay queue
consumption, app-server resolution, pending replay, interruption,
guardian/auto-review closure, typed result history, action-required title, and
footprint stability, MCP form/URL elicitation, full-screen approval, and
inactive-thread request routing, side-parent suppression/discard, and global
interrupt arbitration. Milestone 5 is backed by fixed-Rust snapshots plus five
interactive ConPTY round trips.

Interactive startup defaults are also aligned with the fixed Rust config
owner. With no explicit permission setting, the TUI resolves the active
project from cwd/Git root, derives approval policy from project trust, and
selects the built-in permission profile using the configured Windows sandbox
level. Explicit CLI or `config.toml` permission settings remain authoritative;
this trust-based fallback does not replace a user's `approval_policy`,
`sandbox_mode`, or `default_permissions`. Non-interactive exec retains its
separate `never` approval default.

## Final Human Windows Terminal Acceptance

The project Goal remains active until these checks pass in a real interactive
Python terminal session. Run them in one session so recovery and session-state
behavior are exercised rather than testing isolated startup states.

Automated ConPTY evidence already covers accept, Esc cancellation, modal
80/120-column resize, no cancelled-command side effect, action-required title
cleanup, post-modal Chinese input, and a session-scoped permission grant
reused in a later turn without another approval keystroke. The checklist below
remains manual so a human still confirms the actual Windows Terminal
presentation and feel.

### Reproducible manual runbook

Run the Python product path from a new Windows Terminal tab. Keep this one
process alive for the complete checklist:

```powershell
cd C:\Users\27605\codex-python
Remove-Item -LiteralPath .tmp\approval-manual-accept.txt -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .tmp\approval-manual-cancel.txt -Force -ErrorAction SilentlyContinue
python -m pycodex --no-alt-screen -C C:\Users\27605\codex-python -s read-only -a on-request --enable request_permissions_tool --enable exec_permission_approvals --enable unified_exec
```

Keep all three feature flags enabled for this checklist. At fixed Rust commit
`1c7832ffa37a3ab56f601497c00bfce120370bf9`, `request_permissions_tool`
registers the permission-request tool, while the separate
`exec_permission_approvals` gate adds `additional_permissions` and
`with_additional_permissions` to the model-visible `exec_command` schema.
Enabling only the former therefore cannot validate session-grant reuse.

Use these prompts in order. They name the tool and payload deliberately so the
manual gate measures the TUI approval lifecycle instead of model tool-choice
variability:

1. `请仅使用 apply_patch 创建 .tmp/approval-manual-accept.txt，内容为 APPROVAL_ACCEPTED。等待我处理任何审批，不要改用 shell 写文件。`
   Accept the edit once. Confirm the file exists, contains exactly one line,
   and the stable patch/history entry appears once.
2. `请仅使用 apply_patch 创建 .tmp/approval-manual-cancel.txt，内容为 APPROVAL_CANCELLED。等待我处理任何审批，不要改用 shell 写文件。`
   While the modal is open, shrink the terminal to about 80 columns, then grow
   it past 120 columns. Press Esc. Confirm the file does not exist and the same
   request, selection, history, composer, and footer survive the resize.
3. `调用 request_permissions，请求 permissions.network.enabled=true，reason 为 manual session grant verification。等待我选择审批范围。`
   Choose `a`, the fixed-Rust session option. Confirm the stable decision says
   the permission was granted for this session.
4. `调用 exec_command 执行 echo APPROVAL_SESSION_REUSED；sandbox_permissions 使用 use_default，并携带 additional_permissions.network.enabled=true。不要再次调用 request_permissions。`
   Confirm it completes without another approval modal. A read request is not
   a valid different-profile check because the base `read-only` sandbox
   already permits reads. Instead submit:

   `调用 exec_command 执行 Set-Content -LiteralPath '.tmp/approval-different-profile.txt' -Value 'SHOULD_NOT_EXIST'；sandbox_permissions 使用 with_additional_permissions，并请求 additional_permissions.file_system.write=["C:\\Users\\27605\\codex-python\\.tmp"]。`

   Confirm a new exec approval modal appears. Press Esc and confirm
   `.tmp/approval-different-profile.txt` does not exist.
5. Submit `approval recovery english`, then `审批恢复中文`. Confirm both prompts
   remain intact and both receive normal responses.

During every modal, confirm the terminal tab title indicates action is required
and returns to its ordinary title after accept, Esc, or completion. Do not use
`Full Access` for this run: it would bypass the approval behavior under test.

Record results here or report the same fields back in the task:

| Check | Result | Screenshot/trace | Notes |
|---|---|---|---|
| Accept and resume | pending | - | - |
| Reject/cancel | pending | - | - |
| Resize while pending | pending | - | - |
| Session decision scope | pending | - | - |
| Permission request | pending | - | - |
| Post-modal English/Chinese | pending | - | - |
| Action-required title cleanup | pending | - | - |

- [ ] **Accept and resume:** choose Read Only, request an `apply_patch` write
  to a disposable workspace file, accept once, and confirm the file is written
  exactly once and one stable history result is shown.
- [ ] **Reject/cancel:** request a second disposable write, cancel with Esc or
  choose the deny option, and confirm the file is not created and the prompt
  becomes usable immediately.
- [ ] **Resize while pending:** open an approval modal, shrink and enlarge the
  Windows Terminal window before deciding, and confirm the same request,
  selected row, history, composer, and footer remain visible without duplicate
  rows or a stale overlay.
- [ ] **Session decision scope:** where the modal offers a session decision,
  accept it and repeat the same operation; confirm the matching request is
  reused without a second prompt while a materially different request still
  asks.
- [ ] **Permission request:** exercise a request for additional permissions,
  verify its decision message and footer/status update, and confirm the next
  turn observes the new permission state.
- [ ] **Post-modal input:** after acceptance and rejection, submit ordinary
  English and Chinese IME text and confirm both receive normal responses.
- [ ] **Action-required cleanup:** confirm the terminal title indicates action
  while a request is pending and returns to its normal state after accept,
  reject, Esc, or interruption.

Record the observed result and any screenshot or trace next to this checklist
before changing the overall status from `[~]` to `[x]`. A failed item reopens
the owning module contract; it must not be patched in terminal runtime glue.
