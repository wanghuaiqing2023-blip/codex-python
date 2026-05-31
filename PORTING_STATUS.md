# Codex Python Porting Status

This file tracks progress toward the project mission: port OpenAI Codex from the
upstream `codex/` tree into Python with behavior and logic preserved as closely
as possible, while preferring the Python standard library and avoiding complex
third-party runtime dependencies.

The upstream source of truth is the checked-in `codex/` submodule.

## Snapshot

Last inspected workspace state:

| Area | Current evidence |
| --- | --- |
| Upstream tree | `codex/` is present and expanded. |
| Main upstream Rust tree | `codex/codex-rs/` is present. |
| Python package | `pycodex/` is present. |
| Python test suite | `tests/` contains 106 `test_*.py` files. |

This is not a completion certificate. It is a working migration map. A module is
only "ported" when the Python implementation is traceable to upstream files and
has parity-oriented tests or equivalent behavioral evidence.

## High-level Estimate

Current project state is best described as an early-to-mid foundation port:

| Layer | Approximate status | Notes |
| --- | ---: | --- |
| Repository structure and migration rules | Partial | Python package, tests, and rules exist. |
| CLI parsing and top-level command surface | Partial | Many commands parse; several command bodies remain placeholders. |
| Protocol dataclasses/enums and serialization | Partial to substantial | Many protocol modules exist in Python. |
| Non-interactive `exec` surface | Partial | Argument/config/event-processing pieces exist; full client/runtime parity remains. |
| Core helper modules | Partial | Many isolated helpers are ported; full session/agent loop is not complete. |
| Interactive TUI | Minimal | Command is recognized but not implemented. |
| MCP server | Minimal | Command is recognized but not implemented. |
| Cloud/browser flows | Minimal | Command surface is parsed but behavior is not implemented. |
| Full Codex runtime parity | Not complete | Agent loop, tool orchestration, TUI, server, and integration behavior remain large work items. |

Practical estimate: roughly 15% to 25% of the full "one-to-one Codex in Python"
goal is represented in the current tree. The exact number should be refined by
file-by-file parity checks against upstream.

Recent core-runtime progress:

- Added router-level coverage that post-tool-use hooks receive Rust-style hook matcher aliases: the `spawn_agent` payload now has focused coverage showing the `Agent` matcher alias survives through `PostToolUsePayload`.
- Added router-level coverage for Rust's default post-tool-use stop feedback: when a post hook returns `should_stop=true` without feedback or stop reason, the model-visible output becomes `PostToolUse hook stopped execution` while the original code-mode result remains available.
- Strengthened base sandbox telemetry coverage beyond disabled profiles: router tests now lock external profiles to `sandbox=external` / `sandbox_policy=external-sandbox` and workspace-write profiles to `sandbox_policy=workspace-write`, matching Rust `sandbox_tags.rs` categories.
- Exposed Rust-style tool-result failure text in lightweight telemetry events: router telemetry now includes `error_message` alongside the preserved error object, giving recorders the message string Rust passes into `tool_result_with_tags` while keeping success events at `None`.
- Corrected incompatible-payload memory metric ordering: Python no longer emits `codex.memories.usage` for payload kind mismatches because Rust returns before handler execution and before the later `emit_metric_for_tool_read(&invocation, success)` boundary.
- Added lightweight tool-result duration telemetry: missing/incompatible tool branches now record zero duration like Rust's direct `tool_result_with_tags` calls, while handler execution records a standard-library `perf_counter()` duration before post-tool-use hooks run.
- Added handler output log-preview capture to tool-result telemetry: router events now include `output.log_preview()` for successful handler results before post-tool-use feedback replacement, matching Rust's `log_tool_result_with_tags` closure boundary.
- Added the Rust tool-result log-payload boundary to lightweight telemetry events: router telemetry now includes `invocation.payload.log_payload()` alongside the flat tool name, call id, success flag, tags, output, and error.
- Confirmed Rust does not emit tool-result telemetry for pre-tool-use hook blocked/rewrite failures, and repaired the handler `FunctionCallError` branch so shell/exec memory-read attempts again emit `codex.memories.usage` with `success=false` just like the generic exception branch.
- Added Rust-style base tool-result telemetry tags when turn permission context is available: router telemetry now prefixes `sandbox` and `sandbox_policy` tags derived from the turn permission profile before tool-specific tags, matching Rust's `base_tool_result_tags` ordering without requiring a full telemetry runtime.
- Added unsupported-tool telemetry parity: router dispatch now records a failed tool-result telemetry event for unknown tools before raising the model-visible unsupported-tool error, using the Rust-style flat tool name and empty tool/trace tags.
- Aligned tool-result telemetry tool names with Rust's legacy flat-name boundary: router telemetry events now record `flat_tool_name(invocation.tool_name)` so namespaced tools keep their namespace prefix instead of collapsing to the bare tool name.
- Made tool-result telemetry session fallback mapping-aware: router dispatch now discovers `tool_result_with_tags` through the shared object-or-dict accessor, so dict-shaped session state can observe Rust-style tool-result telemetry just like object-shaped session state.
- Extended memory-read usage metric parity to handler failures: router dispatch now emits `codex.memories.usage` with `success=false` when a shell/exec memory read fails inside the handler, matching Rust's single post-handler `emit_metric_for_tool_read(&invocation, success)` boundary for both Ok and Err results.
- Wired Rust-style memory-read usage metrics into tool dispatch: after handler output success is computed and tool-result telemetry is recorded, Python now calls the existing `emit_metric_for_tool_read(...)` helper with session telemetry/shell context when available, preserving the Rust `emit_metric_for_tool_read(&invocation, success)` side effect before post-tool-use feedback replacement.
- Corrected tool-result telemetry ordering around post hooks: success telemetry now records the original handler output before post-tool-use feedback replacement, matching Rust's log_tool_result_with_tags boundary around handle_any_tool rather than the later model-visible replacement result.
- Added a lightweight tool-result telemetry boundary in router dispatch: handlers' 	elemetry_tags() are now collected, mcp_server / mcp_server_origin are split into extra trace fields like Rust, and optional recorders can observe success and failure tool-result telemetry without adding a full otel runtime.
- Made tool dispatch trace discovery mapping-aware: router trace setup now reads services.rollout_thread_trace, thread ids, and turn ids through the shared object-or-mapping accessor, so dict-shaped runtime state can produce complete Rust-style trace invocations.
- Corrected active-turn mapping support from the previous tool-call accounting slice: _increment_active_turn_tool_calls(...) now reads top-level ctive_turn through the shared object-or-mapping accessor, so dict-shaped session state actually participates in Rust-style tool-call counting.
- Added active-turn tool-call accounting before tool lookup: router dispatch now increments ctive_turn.turn_state.tool_calls with Rust-style u64 saturation when that state is present, so missing/incompatible tool calls are counted just like Rust's pre-dispatch active-turn accounting.
- Tightened post-tool-use additional-context recording around ToolInvocation: the router now records hook-provided contexts through invocation session/turn fallback as well as explicit stores, preserving Rust's ecord_additional_contexts(&invocation.session, &invocation.turn, ...) shape for high-level ToolRouter dispatch.
- Wired tool dispatch rollout trace into the router path: Python now starts optional ToolDispatchTrace contexts, records missing/incompatible/pre-hook/handler failures, and records completed direct responses with Rust-style execution status while remaining disabled when no trace context exists.
- Applied Rust-style goal-runtime accounting after claimed tool completion: tool dispatch now calls goal_runtime_apply({ type: 'tool_completed', ... }) only when finish notification is unclaimed/owned by this path, and warning-only failures no longer disturb tool results.
- Recorded post-tool-use additional contexts before feedback replacement: Python now converts hook-provided additional context strings into developer response items and forwards them through a lightweight recorder/session/turn boundary before replacing model-visible tool output, matching Rust's ecord_additional_contexts ordering.
- Split websocket metadata subagent insertion from provider-facing header filtering:
  `build_ws_client_metadata()` now inserts subagent metadata directly like Rust's
  `HashMap<String, String>` path, while `build_subagent_headers()` continues to
  filter `x-openai-subagent` for HeaderMap-style request headers.`r`n- Repaired header-helper test edits with line-level insertion: the core client
  test import list now includes `build_session_headers()`, invalid Responses
  header tests are inserted by line position, and glued status bullets were
  normalized without relying on fragile block replacements.- Clarified websocket metadata versus header filtering boundaries: current
  Python metadata construction already matches Rust's HashMap-style direct
  metadata insertion while turn metadata remains parsed, so this turn repaired
  the missing core-client helper import and invalid header-value test coverage
  instead of over-filtering websocket metadata.
- Repaired core client header-helper test imports and invalid-value coverage:
  `tests/test_core_client.py` now imports `build_session_headers()` where it is
  used and includes stable invalid-value assertions for both session/thread and
  Responses beta/turn-state/turn-metadata headers.
- Reconciled helper implementation with the shared insertion path: `build_session_headers()` now
  delegates `session-id` and `thread-id` insertion to `insert_header_if_valid()`,
  the helper-level invalid-value assertions are present, and recent progress
  bullets were separated after prior record writes glued entries together.
- Routed subagent identity headers through the shared Rust-style insertion
  helper: `build_subagent_headers()` now skips invalid `x-openai-subagent`
  values and inserts memgen request metadata through `insert_header_if_valid()`,
  with coverage for an invalid `SubAgentSource.other_source` label.
- Centralized Responses header insertion behind Rust-style value filtering:
  Python now exposes `insert_header_if_valid()` and uses it for client request
  id, installation id, websocket beta/timing headers, identity window headers,
  and stdlib HTTP originator/timing headers, with coverage for invalid identity
  values being omitted.
- Extended Rust-style header value filtering to `build_responses_headers()`:
  Python now skips invalid beta-feature, turn-state, and turn-metadata header
  values with the same CR/LF boundary used for session headers, matching Rust's
  `HeaderValue::from_str` omission behavior more closely.
- Matched Rust header-value safety for `build_session_headers()`: Python now
  skips session/thread header values containing CR or LF, mirroring Rust's
  `HeaderValue::from_str` failure path closely enough for the stdlib transport,
  and core client tests cover the invalid-value omission cases.
- Added direct Rust-semantic coverage for `build_session_headers()`: core client
  tests now assert the helper emits `session-id` and `thread-id` only when the
  corresponding optional values are present, matching `codex-api`'s
  `build_session_headers` behavior.
- Forced the remaining Responses session-header drift through regex-based block
  replacement after exact-string replacements missed the live code: websocket and
  stdlib HTTP request construction now route through `build_session_headers()`
  for Rust-style `session-id` / `thread-id`, with transport and resume coverage
  updated at the matching abstraction points.
- Cleaned remaining Responses header-name drift: both Python websocket and
  stdlib HTTP Responses paths now call `build_session_headers()` for Rust-style
  `session-id` / `thread-id`, stdlib HTTP inserts `x-codex-installation-id`, and
  transport/resume tests assert the corrected header names.
- Repaired actual wiring for the Responses session-header helper: Python now
  uses `build_session_headers()` from both websocket and stdlib HTTP Responses
  request construction, emits Rust-style `session-id` / `thread-id`, includes
  the installation id header in stdlib HTTP config, and strengthens transport
  and resume assertions around the real header names.
- Aligned Responses session/thread header names with Rust `build_session_headers`:
  Python now exposes a `build_session_headers()` helper that emits `session-id`
  and `thread-id`, uses it from websocket and stdlib HTTP Responses paths, and
  updates transport/resume coverage away from realtime-only `x-session-id` /
  `x-thread-id` names.
- Repaired and grounded local HTTP identity header parity against Rust evidence:
  stdlib HTTP transport now actually inserts `x-codex-installation-id` before
  session/thread headers, the transport config test asserts the full identity
  header family, and an accidental prompt-cache assertion was removed from the
  raw send helper where no `ModelClient` request construction occurs.
- Added local HTTP installation identity header parity: stdlib HTTP transport
  now sends `x-codex-installation-id` from `ModelClientState` alongside
  session/thread headers, matching Rust client header construction where
  provider-facing requests carry Codex installation identity metadata.
- Added transport-level evidence for local HTTP identity parity: the core HTTP
  transport test now asserts `x-client-request-id`, `x-session-id`, and
  `x-thread-id` are derived from `ModelClientState`, while the sampler path
  asserts the Responses request body uses the thread-derived `prompt_cache_key`.
- Added local HTTP Responses identity headers for session parity: stdlib HTTP
  transport now sends `x-client-request-id`, `x-session-id`, and `x-thread-id`
  from `ModelClientState` before merging Codex identity headers, matching the
  websocket path and making resumed session identity visible to the provider
  request as well as local CLI summaries.
- Extended local HTTP resume CLI coverage for restored session identity: the
  local HTTP `exec resume --last` CLI test now models alignment of both
  `session_id` and `thread_id` before config-summary emission and asserts that
  the human summary reports the resumed session id, not the fresh local client
  id.
- Aligned local HTTP resume session identity with the resumed rollout thread:
  resume identity setup now updates both `session_id` and `thread_id` from the
  target rollout's `session_meta.id`, avoiding a split-brain local client state
  where request headers and prompt cache follow the resumed thread while other
  session-scoped diagnostics still reference a fresh local session id.
- Bound local HTTP resume execution to the rollout resolved for CLI summary:
  the CLI now passes the pre-resolved rollout path from summary-time identity
  alignment into the resume runner, avoiding a second latest/name lookup that
  could otherwise make summary and execution target different session files.
- Moved local HTTP resume identity alignment before CLI summary emission:
  the CLI now resolves the target rollout and updates the model client thread id
  before printing the non-interactive config summary, so user-visible summary
  thread ids match the resumed rollout and the later Responses request headers.
- Aligned local HTTP resume request identity with the resumed rollout thread:
  the resume runner now updates the model client thread id from the target
  rollout's `session_meta.id` before sending the Responses request, so
  `x-thread-id`, `x-client-request-id`, prompt cache key, and rollout append
  all refer to the resumed thread instead of a fresh local client thread.
- Preserved prompt-visible shell tool ordering in local HTTP rollout history:
  when multi-round shell-tools results include raw Responses payloads, rollout
  persistence now reconstructs model output, tool output, and follow-up output
  in chronological prompt order instead of appending all tool outputs after all
  assistant responses.
- Persisted prompt-visible shell tool outputs in local HTTP rollout history:
  rollout append payload generation now includes `tool_response_items` alongside
  model response items, so shell-tools resume turns do not drop
  `function_call_output` history needed by later resumed requests.
- Added local HTTP `exec resume` support for shell-tools loops: resume runner
  can now preload rollout history into the first shell-tools model request,
  execute tool follow-up rounds with the existing stdlib shell loop, and append
  the merged result back to the original rollout while the CLI passes through
  shell tool loop limits.
- Added guarded named-session local HTTP `exec resume` support through the
  rollout session index: non-UUID `resume SESSION_ID PROMPT` values now resolve
  by thread name, honor cwd filtering unless `--all` is set, preload the matched
  rollout history, and append the completed turn back to the named session file.
- Wired guarded local HTTP `codex exec resume` CLI support for true resume
  primitives: the local HTTP branch can now route `exec resume --last` and
  direct thread-id resumes through the resume runner that loads rollout history
  and appends back to the same file, while shell-tool resume remains explicitly
  rejected until its Rust parity semantics are implemented.
- Added a controlled local HTTP resume runner helper: Python can now resolve an
  existing rollout by thread id or latest-session selection, recover its
  `ResponseItem` history, seed the in-memory session before the current user
  turn, run local HTTP sampling, and append the completed turn back to the same
  rollout file without creating a new session.
- Wired local HTTP user-turn sampling to accept preloaded resume history:
  `run_exec_user_turn_http_sampling` can now seed an in-memory session with
  rollout-recovered `ResponseItem` history before adding the current user turn,
  and focused request-body coverage proves prior user/assistant messages appear
  before the new prompt in the Responses API input.
- Added a rollout response-item history reader for future true resume request
  preparation: Python can now recover persisted `response_item` records from a
  session JSONL in prompt order as `ResponseItem` objects, skipping malformed
  lines, which provides the missing foundation for injecting prior conversation
  history before enabling local HTTP `exec resume`.
- Added a local HTTP resume rollout append helper without enabling fake CLI
  resume: completed local HTTP resumed turns can now append user inputs,
  assistant response items, and current cwd context to an existing session
  rollout by thread id or latest-session selection, while the CLI remains
  guarded until historical conversation injection is implemented.
- Wired initial local HTTP exec persistence into turn-context rollout records:
  successful non-ephemeral local exec runs now persist the current cwd as a
  `turn_context` item alongside the user and assistant response items, so
  session listing and future resume cwd selection see the same current-turn
  context shape used by resumed turns.
- Added latest-turn cwd tracking for rollout resume selection: resumed-turn
  appends can now persist a `turn_context` record with the current cwd, and
  thread summaries reverse-scan for the latest observed turn context cwd before
  cwd-filtered `resume --last` selection, matching the Rust cross-directory
  resume behavior more closely.
- Added latest-session resumed-turn append support for local rollout files:
  Python can now select the newest CLI session by `updated_at`, optionally
  filter by current cwd, honor an `include_all` mode, and append the resumed
  turn to the selected existing JSONL file.
- Added a thread-id based resumed-turn append helper: Python can now locate an
  existing session rollout by thread id and append a full turn to that same
  JSONL, matching the file-layer behavior required by Rust
  `exec_resume_by_id_appends_to_existing_file`.
- Refactored local HTTP exec rollout persistence to reuse the full-turn append
  primitive, so initial exec persistence and future resume append logic share
  the same user-plus-response JSONL write path.
- Added a resumed-turn rollout append primitive: Python can now append a full
  turn's user message plus response payloads to an existing session JSONL,
  preserving the same-file marker and last-user-image evidence used by Rust
  `resume.rs`.
- Wired local HTTP exec user input persistence into rollout JSONL: successful
  local runs now persist the user `response_item` before assistant output, so
  resume-suite evidence such as last-user-image-count can observe image inputs
  from the actual local exec path.
- Wired local HTTP exec rollout persistence beyond metadata: successful local
  HTTP `codex exec` now appends returned response items to the same rollout
  JSONL after materializing session metadata, so marker scans can find the
  assistant output while `--ephemeral` still skips persistence.
- Added a rollout append primitive for resume parity: Python can now append a
  persisted `response_item` payload to an existing rollout JSONL and verify it
  through the same marker-scan evidence used by Rust `resume.rs`, preparing the
  actual resume append path.
- Strengthened Rust resume-suite CLI parity coverage: `codex exec resume --last`
  now has explicit Python parser evidence for accepting global flags after the
  subcommand, including repeated `--config`, `--json`, `--model`, dangerous
  bypass, git-check skip, config isolation, and the resumed prompt.
- Added a resume-suite image evidence helper: Python can now scan a rollout
  JSONL and return the number of `input_image` entries in the last persisted
  user message, matching the Rust `resume.rs` helper used to verify resumed
  image inputs.
- Added a resume-suite rollout scan helper: Python can now locate the session
  rollout whose persisted assistant `response_item` message content contains a
  marker, matching the Rust `resume.rs` evidence pattern used to prove resume
  appends to the same JSONL file.
- Aligned workspace-write sandbox permission profiles with repeated `--add-dir`:
  exec session config now builds the `PermissionProfile` from the full runtime
  workspace roots, not just `cwd`, so additional writable roots are reflected in
  the actual sandbox permission model.
- Wired local HTTP `codex exec` success into rollout materialization: the
  default local runtime can now create a persisted session rollout under
  `CODEX_HOME`, while `--ephemeral` keeps the file count unchanged, moving the
  Python path closer to the Rust `ephemeral.rs` default-vs-ephemeral behavior.
- Added a stdlib rollout materialization helper for exec persistence parity:
  default sessions can now create an initial `session_meta` JSONL under
  `<codex_home>/sessions`, while ephemeral sessions explicitly skip creation,
  moving closer to the Rust `ephemeral.rs` 1-file vs 0-file behavior.
- Added a rollout persistence counting helper matching the Rust exec
  `ephemeral.rs` suite's objective check: Python can now count
  `<codex_home>/sessions/**/*.jsonl` files with stdlib filesystem traversal,
  giving the exec ephemeral/default persistence path a reusable parity gate.
- Added Rust-suite parity coverage for repeated `codex exec --add-dir` flags:
  multiple additional writable roots now have explicit evidence that they are
  preserved in harness overrides and projected into runtime workspace roots for
  workspace-write execution.
- Added Rust-suite parity for exec API-key environment auth: local HTTP exec
  auth now accepts `CODEX_API_KEY` after `OPENAI_API_KEY`, preserving existing
  precedence while matching the upstream `auth_env.rs` expectation that Codex
  API-key env auth yields a bearer Authorization header.
- Added run-loop parity coverage for final app-server `error` notifications:
  a non-retry server error for the active turn is preserved as `error_seen` and
  yields exec exit code 1, matching the Rust server-error exit expectation.
- Added Rust-suite parity for exec Responses API originator metadata:
  stdlib HTTP transport now sends `Originator: codex_exec` by default and
  honors `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`, matching the exec originator
  suite's default and override behavior.
- Strengthened Rust-suite parity coverage for `codex exec resume --output-schema`:
  resumed user-turn preparation now has explicit coverage that the full schema,
  including `required` and `additionalProperties: false`, is preserved.
- Added Rust-suite parity coverage for `codex exec --output-schema` preparation:
  full JSON schema contents, including `required` and
  `additionalProperties: false`, are preserved in the user-turn run plan before
  the app-server/request layers wrap them for model output formatting.
- Completed Rust parity coverage for model-reroute exec JSON output: model
  reroute notifications now have explicit test coverage for the completed
  `error` item wrapper, synthetic id, and upstream-style reason debug name.
- Added Rust parity coverage for turn completion final-message recovery:
  a completed turn with an agent message only in final turn items emits the
  terminal `turn.completed` event and restores `final_message` from those items.
- Added Rust parity coverage for exec JSON token usage flow: a
  `thread/tokenUsage/updated` notification stores usage without emitting JSONL
  events, and the subsequent `turn.completed` event carries the four public
  usage fields.
- Added Rust parity coverage for the full exec JSON todo-list lifecycle from
  `turn/plan/updated`: first update emits `item.started`, subsequent update
  emits `item.updated` with the same id, and `turn/completed` closes the running
  todo-list with `item.completed` before the terminal turn event.
- Added Rust parity coverage for two exec JSON basics after agent messages:
  completed reasoning items use fresh synthetic exec ids, and warnings are
  emitted as completed `error` items with the warning text.
- Added Rust parity coverage for agent-message exec JSON lifecycle basics:
  completed agent-message notifications emit an `agent_message` item and update
  final-message state, while started agent-message notifications are ignored.
- Added Rust parity coverage for file-change exec JSON notification mapping:
  completed patch items map add/delete/update change kinds into exec JSON shape,
  and declined patch status is surfaced as failed on the JSONL item payload.
- Added Rust parity coverage for raw collab-agent spawn tool-call exec JSON
  lifecycle: started/completed notifications reuse ids and preserve sender,
  receiver, prompt, agents state, tool, and status payload shape.
- Added Rust parity coverage for raw MCP tool-call exec JSON lifecycle shims:
  started/completed events reuse ids and preserve payload shape, failures emit
  failed status with error message, and null arguments plus structured content
  round-trip through the JSONL item payload.
- Added Rust parity coverage for web-search item lifecycle in exec JSON:
  `item/started` with empty query and no action emits `other`, and the matching
  `item/completed` with a `search` action reuses the same synthetic exec id.
- Added Rust parity coverage for exec JSON reasoning and web-search payloads:
  reasoning completions emit summary text instead of raw reasoning content, and
  typed web-search completions preserve query plus `search` action fields.
- Added Rust parity coverage for foundational exec JSON filtering/id rules:
  empty completed reasoning items are ignored, and unsupported completed items
  such as plan items do not consume synthetic exec ids before the next emitted
  item.
- Added Rust parity coverage for exec JSON final-message lifecycle rules:
  completed turns overwrite stale streamed answers from final turn items,
  preserve streamed answers when final turn items are empty, clear stale answers
  on failed turns, fall back to final plan text, and reuse structured backend
  errors for failed turns without their own error payload.
- Added parity coverage for two upstream Rust exec JSON lifecycle behaviors:
  turn completion reconciles started-but-uncompleted items from final turn items,
  and a plan update after turn completion starts a fresh todo-list item with a
  new exec id.
- Direct `codex exec --json` app-server item mapping now preserves Rust-style
  lazy item id allocation for typed-but-unsupported v2 items and empty reasoning
  items, avoiding id-sequence drift when protocol bridges can parse items that
  exec JSON intentionally does not emit.
- `codex exec --json` typed turn-completion handling now closes any running
  todo-list item before emitting the terminal turn event, matching the
  notification-path and Rust JSONL behavior for `turn/plan/updated` followed by
  `turn/completed`.
- `codex exec` typed turn-completion helpers now normalize status aliases before
  branching, matching notification-path behavior. `JsonEventProcessor` and
  `HumanEventProcessor` now accept app-server/Rust-style status spellings such
  as `Completed` / `Failed` in addition to the snake_case strings already used
  by focused tests.
- `codex exec` human typed turn-completion handling now mirrors the
  notification path for user-visible shutdown diagnostics: typed failed turns
  can print `ERROR: ...`, and typed interrupted turns print `turn interrupted`
  while clearing final-message state.
- `codex exec` human processor typed item lifecycle now mirrors the notification
  path more closely: `HumanEventProcessor.collect_item_started(...)` renders
  typed started items, and `collect_item_completed(...)` now renders typed
  command/file-change/MCP/web-search/reasoning/context-compaction completions
  through the shared human item helpers instead of only handling agent messages.
- Exec event-processor coverage now keeps protocol-level collab shim imports
  aliased away from exec JSON collab enums, avoiding accidental test namespace
  shadowing between app-server v2 `CollabAgentStatus` /
  `CollabAgentToolCallStatus` and exec JSON's snake_case enums.
- `codex exec` human started-item rendering now accepts typed `TurnItem`
  values through the shared app-server mapping bridge before rendering, matching
  the completed-item helper and keeping Python closer to Rust's strongly typed
  `ThreadItem` human renderer.
- `codex exec --json` notification item mapping now applies the raw app-server
  boundary before `TurnItem` parsing for `webSearch` and `collabAgentToolCall`.
  Real `item/started` / `item/completed` notifications therefore keep Rust's
  JSONL behavior for v2 camelCase web-search actions instead of being
  accidentally promoted to core snake_case actions by the protocol bridge.
- `codex exec --json` started/completed lifecycle mapping now preserves Rust's
  lazy item-id allocation for unsupported typed `TurnItem` variants. Items such
  as `dynamicToolCall` no longer consume an exec `item_N` id before being
  dropped, keeping subsequent emitted item ids aligned with Rust's JSONL
  processor.
- `codex exec --json` raw app-server `fileChange` status mapping now matches
  Rust's JSONL boundary for known v2 statuses: `declined` is emitted as exec
  JSON `failed`, because the exec `PatchApplyStatus` enum has no declined
  variant, while unknown raw statuses such as `paused` remain preserved.
- `codex exec --json` typed `CollabAgentToolCall` turn items now map to exec
  JSON `collab_tool_call` items as Rust's JSONL processor does, including the
  upstream `ResumeAgent` to `wait` tool normalization and agent-state
  normalization, while still avoiding multi-agent runtime implementation.
- `codex exec --json` now preserves the raw app-server `collabAgentToolCall`
  boundary even after adding the protocol-level v2 `TurnItem` bridge. Mapping
  form collab items are converted to exec JSON `collab_tool_call` before
  `TurnItem` parsing, avoiding a regression where the lightweight protocol shim
  would parse the item and then produce no exec output.
- App-server v2 `TurnItem` compatibility now includes a lightweight
  `collabAgentToolCall` bridge. Python can parse and re-serialize the v2
  thread-history item shape, including `senderThreadId`, `receiverThreadIds`,
  optional `prompt`/`model`/`reasoningEffort`, and `agentsStates`, while keeping
  legacy/runtime behavior empty so multi-agent orchestration remains outside the
  current core-first implementation scope.
- App-server v2 `mcpToolCall` serialization now keeps `pluginId: null` when no
  plugin id is present, matching Rust's v2 `ThreadItem::McpToolCall` where
  `plugin_id` is an `Option` field without `skip_serializing_if`; only
  `mcpAppResourceUri` remains omitted when absent.
- App-server v2 `webSearch` thread-item parsing now accepts the Rust v2
  optional `action` field. Missing or explicit `null` actions are bridged to
  core `WebSearchAction.other()` instead of failing Python `TurnItem` parsing,
  while typed core web-search actions still serialize back to v2 action shapes.
- App-server v2 `TurnItem` compatibility now includes lightweight
  `dynamicToolCall`, `enteredReviewMode`, and `exitedReviewMode` bridges. These
  protocol-only shims preserve raw thread-history item parsing and serialization
  without implementing dynamic-tool or review-mode runtime behavior, matching
  the current core-first migration boundary.
- `codex exec --json` web search action mapping now mirrors Rust's boundary
  between core snake_case `WebSearchAction` and raw app-server v2 camelCase
  actions: typed core actions stay snake_case, while raw mapping-form
  app-server `webSearch` items are routed through the raw exec boundary before
  `TurnItem` parsing so unsupported camelCase action tags fall back to `other`.
- `codex exec --json` file-change status/kind mapping now preserves unknown
  values instead of silently classifying them as `in_progress` or `update`,
  while keeping known Rust/app-server aliases mapped to the JSONL enums.
- `codex exec --json` command and MCP status mapping now preserves unknown
  status names instead of silently classifying them as `in_progress`, while
  keeping known app-server/Rust in-progress aliases mapped to `in_progress`.
- `codex exec --json` collab tool-call status mapping now preserves unknown
  status names instead of silently classifying them as `in_progress`, while
  keeping known app-server/Rust in-progress aliases mapped to `in_progress`.
- `codex exec --json` collab tool mapping now preserves unknown tool names
  instead of silently classifying them as `wait`; the special Rust mapping from
  `ResumeAgent` to JSONL `wait` remains intact.
- `codex exec --json` command execution and todo-list item shapes were
  rechecked against Rust `exec_events.rs` / `event_processor_with_jsonl_output.rs`;
  the current Python fields and todo completion rule match the upstream JSONL
  structures, so no code change was made for that slice.
- `codex exec --json` MCP result output keeps absent `structured_content` as
  `null`, matching Rust `McpToolCallItemResult` where `_meta` is skipped when
  absent but `structured_content` is not marked `skip_serializing_if`.
- `codex exec` human item rendering now relies on the shared
  `TurnItem.to_app_server_mapping()` path for typed `McpToolCall` items instead
  of carrying a separate stale hand-written MCP fallback in the event processor.
- App-server v2 `TurnItem` compatibility now includes a lightweight
  `mcpToolCall` bridge so typed MCP items in thread history serialize with the
  Rust v2 field names without expanding MCP runtime behavior; focused coverage
  now checks semantic round-trip fields instead of treating v2 `durationMs` and
  result projection as identical to the internal core item object, and parser
  coverage rejects non-integer `durationMs` wire values while serializer
  coverage rejects non-duration/non-integer internal duration values.
- Protocol item coverage no longer carries the stale expectation that `Plan`
  lacks an app-server v2 mapping; focused tests now treat `plan` as a supported
  `TurnItem` bridge shape alongside command execution and file changes.
- `codex exec` `turn/completed` backfill now serializes recovered typed
  `TurnItem` values through the shared app-server v2 `TurnItem` bridge before
  inserting them into the notification, while preserving unknown raw payloads.
- `codex exec` event notification normalization now accepts `kind` as well as
  `method`/`type`, so Rust-style notification variant names such as
  `TurnCompleted` are routed through the same output processor aliases.
- `codex exec` last-message write-failure diagnostics now format the path as a
  quoted path string instead of Python's `Path(...)` repr, closer to Rust's
  `{path:?}` debug output.
- `codex exec` last-message handling now preserves Rust's two diagnostic paths
  when no final agent message exists and the last-message file write also
  fails: it reports the write failure and still emits the no-last-message
  warning.
- `codex exec` last-message file writing now matches Rust's failure behavior:
  write errors are reported to stderr and do not crash final-output handling.
- `codex exec` thread start/resume parameter building now omits empty
  instruction `config` payloads, keeping the default request shape closer to
  Rust's `config: None` while preserving the Python shim for non-empty resolved
  project instructions and startup warnings.
- `codex exec` remote unsupported-request diagnostics now normalize known
  Rust/Python alias method names before formatting the JSON-RPC `-32601`
  message, so legacy names such as `apply_patch_approval` surface as the
  canonical app-server method `applyPatchApproval`.
- `codex exec` server-request method normalization now accepts `kind` as well
  as `method`/`type`, so Rust-style variant names such as
  `PermissionsRequestApproval` are routed through the same exec-mode rejection
  table instead of falling back to `unknown`.
- `codex exec resume` now exposes a Rust-shaped
  `resume_thread_id_lookup_request(...)` helper that uses fixed request id `0`
  for pre-start `thread/list` lookup requests, matching upstream's
  `RequestId::Integer(0)` resume resolution path without consuming the main
  exec request-id sequence.
- `codex exec resume` local state-db thread matching now honors cwd when the
  candidate thread carries cwd metadata, unless `--all` is active, mirroring
  Rust's state-db lookup call that receives `cwd` only for non-`--all` resume.
- `codex exec resume` cwd recovery now treats invalid UTF-8 rollout files like
  unreadable/missing files and falls back to the thread cwd, matching Rust's
  `read_to_string(...).ok()?` behavior in `parse_latest_turn_context_cwd`.
- `codex exec` turn-completion backfill now clones recovered turn items from
  `thread/read` responses before inserting them into the completion
  notification, matching Rust's `turn.items.clone()` behavior and avoiding
  accidental mutation of the source thread response.
- `codex exec` initial-operation response parsing now rejects unsupported
  methods instead of treating every non-review response as `turn/start`,
  matching Rust's closed `InitialOperation` branch set more closely.
- `codex exec` `turn/start` request parameters now include the app-server
  `additionalContext` protocol field, matching Rust's `TurnStartParams`
  surface while preserving omission when the value is `None`.
- `codex exec` startup planning now includes Rust's trusted-directory git
  safety gate: non-git directories are rejected unless `--skip-git-repo-check`
  or dangerous bypass is active, with the upstream user-facing error text
  preserved for the eventual runner; the new `ensure_exec_trusted_directory`
  helper and `ExecRuntimeRequestSequence.trusted_bootstrap_request()` provide
  the Rust-shaped abort point before the startup `thread/start` request.
- `codex exec` now exposes Rust's exec OTEL defaults in the Python exec
  planning layer: analytics defaulting to enabled, the upstream stderr log
  filter string, and a small `build_exec_otel_provider(...)` helper that feeds
  the exec default into the existing Python OTEL provider mapping.
- `codex exec --output-schema` loading now treats invalid UTF-8 as a
  read-file error, matching Rust `std::fs::read_to_string` behavior instead of
  letting Python `UnicodeDecodeError` escape from the core exec preparation
  path.
- Doctor command-runner failures without stderr now report
  `exited with status exit status N`, closer to Rust `ExitStatus` formatting
  for curl/npm diagnostics than the previous bare numeric return code.
- Doctor update version-cache reads now treat invalid UTF-8 as a
  `version cache read: ...` diagnostic instead of letting Python's
  `UnicodeDecodeError` escape, matching Rust `read_to_string` error handling.
- Update version parsing now rejects components that Rust `u64::parse` would
  reject, including negative signs, explicit plus signs, per-component
  whitespace, and values above `u64::MAX`, while still ignoring extra version
  components after the first three like Rust's `parse_version`.
- Doctor update latest-version HTTP fetching now mirrors Rust's
  `http_get_json` command shape by invoking `curl -fsSL --max-time 5 <url>`
  through the existing command runner instead of using Python `urllib` for this
  update probe.
- Added `doctor_updates_check_from_config(...)` so `updates.status` reads
  `check_for_update_on_startup` inside the doctor update helper boundary,
  moving another piece of Rust `updates_check(config)` behavior out of the CLI
  parser.
- `doctor_updates_check(...)` now owns the `version.json` cache path derivation
  from `codex_home`, matching Rust `updates_check(config)` and removing the
  parser-side `codex_home / "version.json"` handoff for `updates.status`.
- Added a Rust-shaped `doctor_updates_check(...)` helper that derives the update
  action from the current executable and install context before building the
  update diagnostic, so the CLI parser no longer owns `detect_update_action`
  for `updates.status`.
- `build_doctor_update_check` now owns the latest-version probe by default,
  calling `fetch_latest_version(update_action)` after npm target inspection just
  like Rust `updates_check`, while keeping explicit `latest_version` /
  `latest_error` injection for focused tests and callers.
- `build_doctor_update_check` now performs npm global-root inspection itself
  when the launch is npm-managed and no injected `NpmRootCheck` is supplied,
  matching Rust `updates_check` where the update diagnostic owns its npm target
  probe instead of receiving a precomputed parser result.
- CLI npm mismatch coverage now patches installation and updates npm-root probes
  at their actual module boundaries, preserving the Rust-like independence after
  `doctor_installation_check` gained native npm inspection.
- `doctor_installation_check` now performs npm global-root inspection itself when
  the launch is npm-managed and no injected `NpmRootCheck` is supplied, matching
  Rust `installation_check` behavior outside the CLI wrapper path.
- Doctor check timing now overwrites any preexisting `duration_ms` value in the
  CLI path, matching Rust `run_sync_check`/`run_async_check`, which assigns the
  measured elapsed time after each check completes.
- CLI doctor JSON coverage now asserts npm global-root inspection runs once for
  `installation` and once for `updates.status`, matching Rust's independent
  check boundaries instead of sharing one precomputed result.
- `installation` duration timing now includes npm global-root inspection inside
  its own timed check helper, matching Rust's `installation_check` boundary
  instead of reusing a precomputed npm result from outside the check.
- `updates.status` timing now also includes update-action detection and the npm
  global-root check, matching Rust's `updates_check` boundary more closely
  instead of precomputing those inputs outside the timed check.
- `updates.status` duration timing now includes the latest-version probe, matching
  Rust's `updates_check` boundary where `fetch_latest_version` runs inside the
  timed check rather than before it.
- `_run_doctor` now records per-check elapsed milliseconds with a lightweight
  timing wrapper, feeding Rust-shaped `durationMs` values through the existing
  support-report normalization instead of defaulting every CLI-built check to 0.
- Doctor summary/exit-code aggregation now normalizes raw check statuses through
  a Rust-shaped CLI status helper, so both internal `warn` and JSON-facing
  `warning` count as warning before computing overall status.
- Doctor JSON report coverage now pins the default Rust timestamp format for
  `generatedAt` (`<seconds>s since unix epoch`), preventing drift back to ISO
  timestamps or other Python-native datetime strings.
- Doctor JSON top-level report tests now pin Rust `JsonDoctorReport` field
  order: `schemaVersion`, `generatedAt`, `overallStatus`, `codexVersion`, then
  `checks`, preserving snapshot and pretty-printed JSON comparability.
- Doctor JSON issue coverage now pins Rust's `JsonDoctorIssue` schema for
  optional fields: missing `measured`, `expected`, and `remedy` serialize as
  `null`, while `fields` remains present as an empty array.
- Doctor JSON detail-value coverage now pins Rust's `JsonDetailValue` shape:
  first occurrences serialize as scalar strings, while repeated detail labels
  serialize as arrays preserving all values.
- Doctor JSON helper coverage now pins Rust's `JsonDoctorCheck` serde behavior
  for empty optional arrays: empty `issues` and `notes` are omitted, while
  `remediation: null` and `durationMs` remain present.
- Helper-level doctor JSON coverage now confirms the Python internal
  `background_server` check key serializes to Rust's outer
  `app_server.status` id and `app-server` category, matching the CLI-level guard.
- Doctor JSON config-failure assertions now follow Rust's
  `structured_json_details` rule: free-form error details such as
  `home missing` and `broken config` are emitted as `notes`, not as structured
  `details` fields.
- Doctor JSON config-failure tests now pin Rust's `config.load` remediation
  text (`Fix the reported config error, then rerun codex doctor.`) and preserve
  the underlying config/CODEX_HOME error detail in the redacted support report.
- Doctor JSON config-failure coverage now distinguishes Rust's two fallback
  state cases: unresolved CODEX_HOME yields warning `state.paths`, while a
  resolved CODEX_HOME with broken config still yields ok `state.paths` with
  `CODEX_HOME was resolved without config`.
- The new Rust-parity `default_reachability_plan()` helper is exported through
  `pycodex.cli`, keeping the package-level helper surface consistent with the
  existing doctor reachability helpers used by tests and callers.
- Config-failure doctor fallback now uses an explicit Python
  `default_reachability_plan()` equivalent to Rust's `default_reachability_plan`,
  forcing ChatGPT reachability instead of allowing ambient API-key environment
  variables to switch the fallback report to API-key probing.
- Doctor JSON tests now pin the upstream app-server check id spelling
  `app_server.status` from Rust `doctor/background.rs`, guarding against the
  tempting but incorrect hyphenated `app-server.status` JSON key.
- `codex doctor --json` now follows Rust's config-load failure shape more
  closely: setup-independent checks (`system`, `installation`, `runtime`,
  `search`) still run, while the fallback set is limited to Rust's
  `config.load`, `network.env`, `terminal.env`, `git.environment`,
  `state.paths`, and `network.provider_reachability` instead of emitting
  Python-only unavailable placeholders for auth, sandbox, updates, MCP,
  websocket, app-server, title, and thread inventory.
- `codex doctor --json` no longer emits the Python-port-only `environment` and
  `runtime.python` checks. The report now follows Rust's `build_report` check
  set more closely, where system/runtime/search are represented by upstream
  checks rather than Python interpreter self-diagnostics.
- `codex doctor --json` no longer emits Python's temporary `codex_home`
  pseudo-check; CODEX_HOME diagnostics now flow only through the Rust-shaped
  `state.paths` check, avoiding duplicate outer check ids after support-report
  normalization.
- Doctor JSON check identity metadata now aligns more of Python's core checks
  with upstream Rust ids: `system.environment`, `runtime.provenance`,
  `runtime.search`, and `git.environment`, with CLI assertions updated to read
  those Rust-shaped outer `checks` keys.
- CLI-level doctor JSON tests now assert the Rust-shaped support report
  contract: check ids as outer keys, structured detail maps, `overallStatus`,
  normalized `warning`, and no Python-only top-level summary object.
- `codex doctor --json` now always emits pretty-printed JSON with two-space
  indentation, matching Rust's `serde_json::to_string_pretty` output instead
  of only pretty-printing when Python's `--ascii` flag was present.
- `codex doctor --json` status normalization now trims surrounding whitespace
  before mapping into Rust's `CheckStatus` JSON vocabulary, so Python caller
  noise such as `" FAIL "` still serializes as `fail` rather than falling back
  to `warning`.
- `codex doctor --json` now saturates oversized `durationMs` values at
  `u64::MAX`, matching Rust's elapsed-millisecond conversion fallback instead
  of allowing arbitrary Python big integers into the support report.
- `codex doctor --json` now stringifies top-level `generatedAt` and
  `codexVersion` report fields before serialization, matching Rust's
  `JsonDoctorReport` `String` fields and keeping unexpected Python caller
  values inside the Rust-shaped JSON schema.
- Doctor JSON redaction coverage now mirrors Rust's support-report fixture more
  closely for issue remedies, asserting URL credential/query stripping without
  introducing a query parameter name that Rust's broad secret-key heuristic
  would redact as an entire secret-bearing detail.
- `codex doctor --json` status serialization now always emits Rust's
  `CheckStatus` JSON vocabulary (`ok`, `warning`, `fail`), mapping unexpected
  Python diagnostic statuses to `warning` instead of leaking schema-invalid
  values.
- `codex doctor --json` now stringifies check `id`, `category`, and `summary`
  values before serialization, matching Rust's `String` fields and avoiding
  Python-only non-string JSON types in the fixed check schema.
- `codex doctor --json` now normalizes check `durationMs` to a non-negative
  integer before serialization, matching Rust's `u64` duration field more
  closely and avoiding string/negative Python diagnostic values in JSON.
- `codex doctor --json` check field insertion order now follows Rust's
  `JsonDoctorCheck` struct order (`id`, `category`, `status`, `summary`,
  `details`, optional `issues`, optional `notes`, `remediation`, `durationMs`),
  improving snapshot and byte-level report comparability.
- `codex doctor --json` check payloads now stop copying arbitrary Python-only
  extra fields into JSON, matching Rust's fixed `JsonDoctorCheck` schema and
  avoiding an unredacted escape hatch for unexpected diagnostic data.
- `codex doctor --json` check payloads now always include the `remediation`
  field, using `null` when no remediation is present, matching Rust's
  non-skipped `Option<String>` serialization for `JsonDoctorCheck`.
- The Python doctor JSON report builder no longer accepts aggregate count
  parameters that Rust's `JsonDoctorReport` cannot serialize, reducing a
  Python-only compatibility seam after the top-level `summary` field removal.
- `codex doctor --json` now keys the outer `checks` map by each check's
  Rust-style `id` and sorts those keys, matching Rust's `BTreeMap` support
  report shape more closely than the previous Python-only short keys.
- `codex doctor --json` top-level report fields now match Rust's
  `JsonDoctorReport` more closely by omitting Python's previous compatibility
  `summary` field; aggregate counts remain available in the human summary path.
- `codex doctor --json` structured detail fields now use deterministic
  lexicographic key ordering, matching Rust's `BTreeMap`-backed support report
  output while preserving repeated-key arrays and freeform notes.
- `codex doctor --json` check identity metadata now uses more of Rust's
  upstream check ids for existing Python checks, including `auth.credentials`,
  `sandbox.helpers`, `terminal.env`, and `network.websocket_reachability`,
  while preserving Python's outer compatibility keys for now.
- `codex doctor --json` now normalizes serialized status values to Rust's
  `CheckStatus` vocabulary, so Python's internal `warn` becomes JSON
  `warning` for both per-check status fields and the top-level
  `overallStatus`, while internal summary accounting remains unchanged.
- `codex doctor --json` now serializes structured check `issues` through the
  same support-report redaction path as Rust: issue severity is normalized,
  cause/measured/expected/remedy/fields are sanitized, and empty/non-structured
  issue payloads are omitted instead of leaking raw extra data.
- `codex doctor --json` check entries now include Rust-shaped `id`,
  `category`, and `durationMs` fields. Python-internal check keys are mapped to
  stable Rust-style identities such as `network.provider_reachability`,
  `state.rollout_db_parity`, and `app_server.status` while preserving explicit
  identity fields when a check supplies them.
- `codex doctor --json` now emits a Rust-shaped top-level support report with
  `schemaVersion`, `generatedAt`, `overallStatus`, `codexVersion`, and
  structured redacted `checks`, replacing the earlier Python-only `status`
  top-level shape for the JSON path.
- `codex doctor` default human output now reuses the same redacted check mapping
  as `--json`, so secret-looking detail values and URL credentials/query strings
  are not printed raw in the compact terminal report path.
- `codex doctor --json` now uses a Rust-shaped redacted support-report mapping:
  detail lines are sanitized for secret keys and URL credentials/query strings,
  `label: value` details become structured JSON fields, duplicate labels become
  arrays, and freeform detail lines are preserved as notes.
- `codex doctor` thread-inventory rollout parsing now treats unreadable,
  invalid, and empty rollout JSONL files as scan errors instead of falling back
  to filename-derived thread ids, matching Rust's `RolloutThreadId::Unusable`
  behavior more closely.
- `codex doctor` thread-inventory summaries now match Rust's source/provider
  aggregation more closely: source values are normalized into Rust-style
  categories such as `subagent:review`, `internal:memory_consolidation`, and
  `unparsable`, while count summaries sort by descending count then name and
  collapse entries beyond eight categories into `other=N across M categories`.
- `codex doctor` thread-inventory scanning now reads rollout JSONL
  `session_meta` records and prefers the session metadata thread id over the
  filename-derived id, moving closer to Rust's `RolloutRecorder` +
  `builder_from_items` path while retaining a filename fallback for partially
  parseable local fixtures.
- `codex doctor` now has a Python thread-inventory parity diagnostic and CLI
  report wiring for rollout/state DB consistency. It scans active and archived
  `rollout-*.jsonl` files, reads the `state_5.sqlite` `threads` inventory,
  reports missing state rows, stale DB rows, archive-flag mismatches, duplicate
  rollout thread ids, duplicate DB paths, provider/source summaries, missing DB
  behavior, and Rust-shaped OK/warning summaries using only the Python standard
  library.
- `codex doctor` now has a Python background app-server status diagnostic and
  CLI report wiring that mirrors Rust's passive daemon check: it reports the
  daemon state directory, settings/pid/update-loop pid file state, control
  socket path, not-running/running/stale status, app-server version detail when
  a bounded probe succeeds, persistent/ephemeral mode, and stale-socket
  remediation without starting or stopping the daemon.
- `codex doctor` now has a lightweight Python MCP configuration diagnostic and
  CLI report wiring, matching Rust's extension-area shim boundary: it reports
  no-server OK state, configured/disabled/transport counts, stdio command/cwd/env
  input issues, streamable HTTP token/header env issues, HEAD-then-GET HTTP
  reachability, optional warnings, required failures, and Rust-shaped summaries
  without implementing the full MCP runtime.
- `codex doctor` provider reachability CLI wiring now derives its
  `ReachabilityPlan` from the loaded Python config and stored auth/env state,
  rather than always probing a hard-coded ChatGPT/OpenAI default. The helper
  now reads provider id/name/base URL/query params/auth requirements and
  ChatGPT base URL from config before invoking the Rust-shaped probe logic.
- `codex doctor` provider reachability now performs standard-library HTTP
  probes for planned provider endpoints: base URLs use `HEAD`, OpenAI-compatible
  `/models` route probes use `GET`, and the Python status/summary classification
  now mirrors Rust's OK/warning/fail outcomes for reachable endpoints, route
  warnings, missing routes, and transport failures.
- `codex doctor` now has Python provider reachability plan helpers and static
  CLI report wiring for API key, ChatGPT, and provider-auth endpoint planning,
  including OpenAI-compatible `/models` route-probe URL construction.
- `codex doctor` now has a Python fallback state diagnostic for config-load
  failure paths, preserving a usable report when `config.toml` cannot be read or
  parsed.
- `codex doctor` now has a Python Responses WebSocket static diagnostic and CLI
  report wiring for provider metadata, proxy env details, disabled-provider OK
  behavior, and a Rust-shaped warning/remediation for the not-yet-ported
  handshake probe.
- `codex doctor` now has a Python terminal-title diagnostic and CLI report
  wiring for default/configured/disabled title items, item aliases, invalid item
  warnings, activity/project-name details, and Rust-shaped project title
  truncation.
- `codex doctor` now has a Rust-aligned Python Git environment diagnostic and
  CLI report wiring for selected Git, PATH candidates, Git metadata, repo root,
  `.git` entry summaries, branch/fsmonitor details, and Git availability/old
  Windows Git warnings.
- `codex doctor` now has a Python sandbox diagnostic and CLI report wiring for
  approval policy, filesystem sandbox, network sandbox, sandbox helper paths,
  and missing Linux helper warnings.
- `codex doctor` now has a Python network environment diagnostic and CLI report
  wiring that mirrors Rust proxy env var summaries and custom CA file checks for
  `CODEX_CA_CERTIFICATE` and `SSL_CERT_FILE`.
- `codex doctor` now has a Rust-aligned Python auth credential diagnostic that
  covers auth env vars, provider-specific auth env requirements, stored
  `auth.json` modes, incomplete credential issues, missing credentials,
  remediations, and CLI report wiring as the structured `auth` check.
- `codex doctor` now has a Python config diagnostic helper and CLI report
  wiring that covers cwd/model/provider/log/sqlite/MCP summaries, feature flag
  details, `config.toml` read/parse state via `tomllib`, and startup warning
  aggregation.
- `codex doctor` now has a Python state diagnostic helper covering
  `CODEX_HOME`, log/sqlite homes, runtime DB readiness, SQLite
  `PRAGMA integrity_check` via the standard library, rollout file statistics,
  state DB failure remediation, and CLI report wiring as the `state` check.
- `codex doctor` terminal diagnostics now include Windows console detail rows
  for code pages and stdout/stderr console modes, using Python standard-library
  `ctypes` and preserving Rust's diagnostic-only behavior.
- `codex doctor` terminal diagnostics now carry tmux detail rows, including
  client term metadata and key tmux options, with probe failures kept non-fatal
  like Rust.
- `codex doctor` terminal diagnostics now inspect `TERMINFO` and
  `TERMINFO_DIRS` with standard-library path readiness checks, matching Rust's
  failing terminal issue when terminfo paths are missing or unreadable.
- `Op.user_input` turn-scoped `environments` now flow through the lightweight
  request runtime into `SessionSettingsUpdate` and the next
  `InMemoryTurnContext` as a one-shot override, matching the upstream Rust path
  that applies environment selections before constructing a new turn without
  rewriting sticky thread environments.
- Default turns now overlay the current session cwd onto sticky primary
  environment selections while explicit turn-local environment overrides keep
  their selected cwd and become the turn cwd, matching Rust turn-context
  construction.
- Initial environment context prompt rendering now reads turn environments,
  including multi-environment `<environments>` output with environment ids,
  rather than always falling back to a legacy single cwd.
- Subsequent settings/environment update messages also build environment
  context from turn environments, matching Rust's
  `EnvironmentContext::from_turn_context` path.
- Tool planning now has turn-context environment helpers that mirror Rust
  `ToolEnvironmentMode::from_count`: no environments omit environment-backed
  tools, one environment hides `environment_id`, and multiple environments add
  `environment_id` to `exec_command`, `apply_patch`, and `view_image` specs.
- The default user-turn runtime now builds an environment-backed tool router
  from the turn context when no test/custom router is injected, so ordinary
  request construction can expose `exec_command`, `apply_patch`, and
  `view_image` consistently with selected environments.
- Environment-backed router dispatch now keeps runtime-only objects on
  `ToolInvocation` while forwarding only lifecycle stores to extension-style
  notifications, allowing routed `exec_command` calls to execute with selected
  turn environments.
- The lightweight user-turn sampling runtime now executes model-emitted tool
  calls through the built turn router and records their tool output items back
  into conversation history, moving the Python agent loop closer to Rust's
  sample -> tool dispatch -> follow-up-input path.
- User-turn sampling now continues with follow-up model requests after tool
  outputs are recorded, up to a bounded `max_tool_followups` limit, so one
  Python user turn can progress from model tool call to tool result to final
  assistant response.
- The `codex exec` local HTTP shell-tool path now preserves tool output items
  on the returned sampling result and emits tool-call/tool-output JSON events
  from the complete local loop instead of only the final model payload.
- Local HTTP `codex exec` usage extraction now sums usage across all raw
  sampling payloads in a shell-tool loop, so turn completion usage reflects the
  full user turn instead of only the final follow-up response.
- Local HTTP `codex exec` shell-tool loop results now keep the full model
  response history across multiple tool rounds while final-output rendering
  selects the last assistant-visible message, preserving follow-up context
  without printing intermediate tool-planning text as the final answer.
- Local HTTP `codex exec` JSON event rendering now emits tool call and matching
  tool output events in call-id order, preserving the visible turn timeline
  (`call -> output -> next call -> output`) for multi-round shell-tool loops.
- Tool timeline item ids are now allocated in emitted event order for local
  HTTP `codex exec`, so multi-round tool events have monotonic `item_N`
  identifiers that match the visible timeline.
- Local HTTP shell-tool wrapping now preserves async base `built_tools`
  builders, matching the core turn runtime's awaitable tool-planning boundary
  instead of dropping existing model-visible specs when a base builder is async.
- Local HTTP `exec_command` model-visible schema now includes the `cwd`
  compatibility alias already accepted by its parser, keeping visible tool
  arguments aligned with the stdlib local exec helper.
- Default environment tool routing now reads `Feature.EXEC_PERMISSION_APPROVALS`
  and model `supports_image_detail_original` through the existing Python ports,
  aligning exec approval and original image detail tool schemas with Rust
  capability checks.
- Protocol `ImageDetail` now includes Rust's full `auto`, `low`, `high`, and
  `original` variants so original-image-detail normalization preserves all
  non-original detail values.
- Public tool invocation wrappers now expose Rust-style `is_direct` and
  `is_code_mode` helpers, normalize string tool names to `ToolName`, and
  `tool_search_output` rejects string/non-sequence `tools` values.
- `Op.user_input` `final_output_json_schema` now updates the next turn context
  before request construction and clears like Rust's per-turn
  `Option<Option<Value>>` setting instead of acting as sticky session state.

## Crate-to-package Map

| Upstream area | Approx. upstream Rust files inspected | Python target | Current Python files inspected | Status |
| --- | ---: | --- | ---: | --- |
| `codex/codex-rs/cli` | 28 | `pycodex.cli` | 5 | Partial |
| `codex/codex-rs/core` | 342 | `pycodex.core` | 77 | Partial |
| `codex/codex-rs/protocol` | 30 | `pycodex.protocol` | 26 | Partial to substantial |
| `codex/codex-rs/exec` | 12 | `pycodex.exec` | 8 | Partial |
| `codex/codex-rs/shell-command` | 11 | `pycodex.shell_command` | 3 | Partial |
| `codex/codex-rs/login` | 19 | `pycodex.login` | 1 | Early partial |
| `codex/codex-rs/sandboxing` | 11 | `pycodex.sandboxing` | 1 | Early partial |
| `codex/codex-rs/tui` | 325 | `pycodex.tui` | 1 | Placeholder |
| `codex/codex-rs/mcp-server` | 8 | TBD | 0 | Not started |
| `codex/codex-rs/apply-patch` | 7 | `pycodex.core.apply_patch` and related modules | Included under core | Partial |
| `codex/codex-rs/execpolicy` | 10 | `pycodex.core.exec_policy` and related modules | Included under core | Partial |
| `codex/codex-rs/file-system` | 1 | TBD | 0 | Not started or folded into helpers |
| `codex/codex-rs/git-utils` | 8 | `pycodex.core.git_info` and related modules | Included under core | Partial |
| `codex/codex-rs/rollout` | 15 | `pycodex.core.rollout` and related modules | Included under core | Partial |

## Protocol Status

Upstream protocol files currently visible:

| Upstream file | Python target | Status |
| --- | --- | --- |
| `account.rs` | `pycodex.protocol.account` | Ported foundation; plan wire names, workspace helpers, auth-plan conversion type checks, and provider account enum-shape invariants aligned |
| `agent_path.rs` | `pycodex.protocol.agent_path` | Ported foundation; root/morpheus semantics, name/join/resolve validation, reserved names, path error messages, and string input boundaries aligned |
| `approvals.rs` | `pycodex.protocol.approvals` | Partial; exec-policy amendments, network approval aliases/context, network policy amendments, escalation permission enum shapes, guardian event timestamp/string bounds, file changes, and apply-patch approval event field invariants tightened |
| `auth.rs` | `pycodex.protocol.auth` | Ported foundation; known/unknown plan enum-shape invariants, alias parsing, workspace helpers, and refresh-token error field types aligned |
| `config_types.rs` | `pycodex.protocol.config_types` | Partial to substantial |
| `dynamic_tools.rs` | `pycodex.protocol.dynamic_tools` | Ported foundation |
| `error.rs` | `pycodex.protocol.error` | Partial; Cloudflare status formatting and sandbox UI cases checked against upstream |
| `exec_output.rs` | `pycodex.protocol.exec_output` | Ported foundation |
| `items.rs` | `pycodex.protocol.items` | Partial |
| `mcp.rs` | `pycodex.protocol.mcp` | Partial; request id i64 bounds, MCP string field/type checks, lossy resource size behavior, camelCase aliases, and call result shape checks aligned |
| `mcp_approval_meta.rs` | `pycodex.protocol.mcp_approval_meta` | Ported constants; all upstream approval metadata constants are exposed through the package API and covered by parity tests |
| `memory_citation.rs` | `pycodex.protocol.memory_citation` | Ported foundation |
| `models.rs` | `pycodex.protocol.models` | Partial; `FileSystemPermissions` legacy read/write serialization and entries/type/non-zero invariants, filesystem access/special/path serde/object bounds, entry/policy kind/depth/entries bounds, network sandbox enum bounds, legacy sandbox policy input/object/unknown-field bounds, filesystem permission deny-unknown-fields behavior, managed filesystem tagged enum bounds/object invariants, permission tagged enum type/field checks, `PermissionProfile` enum object invariants, `NetworkPermissions.enabled`, `AdditionalPermissionProfile`, and active profile field type invariants aligned |
| `network_policy.rs` | `pycodex.protocol.network_policy` | Ported foundation; decision/source wire names, optional protocol parsing, ask-from-decider helper, optional string fields, and u16 port boundaries aligned |
| `num_format.rs` | `pycodex.protocol.num_format` | Ported foundation; en-US fallback grouping, SI suffix rounding/examples, negative clamp behavior, and i64 input boundaries aligned |
| `openai_models.rs` | `pycodex.protocol.openai_models` | Partial; model metadata defaults, personality templates, service tiers, input modalities, bool/string list boundaries, i32/i64 numeric bounds, and effective context percent default behavior aligned |
| `parse_command.rs` | `pycodex.protocol.parse_command` | Ported foundation |
| `permissions.rs` | `pycodex.protocol.models` and permission helpers | Partial |
| `plan_tool.rs` | `pycodex.protocol.plan_tool` | Ported foundation |
| `protocol.rs` | `pycodex.protocol.protocol` | Partial |
| `request_permissions.rs` | `pycodex.protocol.request_permissions` | Ported foundation; profile conversion, profile deny-unknown-fields behavior, args, response, scope enum, event field invariants, signed i64-bounded event timestamps, cwd input bounds, and event mapping type checks aligned |
| `request_user_input.rs` | `pycodex.protocol.request_user_input` | Ported foundation |
| `session_id.rs` | `pycodex.protocol.ids` | Ported foundation; UUID generation/parsing/display, session-thread conversion, non-zero defaults, and direct UUID field boundaries aligned |
| `shell_environment.rs` | `pycodex.protocol.shell_environment` | Ported foundation; inherit/default-exclude/include/set/thread-id ordering, platform core vars, PATHEXT fallback, policy field types, and environment pair boundaries aligned |
| `thread_id.rs` | `pycodex.protocol.ids` | Ported foundation; UUID generation/parsing/display, non-zero defaults, JSON string serialization, and direct UUID field boundaries aligned |
| `tool_name.rs` | `pycodex.protocol.tool_name` | Ported foundation |
| `user_input.rs` | `pycodex.protocol.user_input` | Ported foundation; tagged user input variants, byte-range usize boundaries, text element placeholder/range behavior, image detail parsing, path/string field boundaries, and serde shape checks aligned |

Next protocol work should focus on closing gaps in `protocol.rs`, `items.rs`,
`models.rs`, `permissions.rs`, and parity with upstream protocol tests.

## Core Status

`codex/codex-rs/core/src` is the largest non-UI migration target currently
visible. Python already contains many matching helper modules, including command
canonicalization, config editing, environment selection, exec policy, features,
goals, MCP tool helpers, network policy decisions, permissions instructions,
rollout, safety, shell helpers, skill rendering, tool registry/router, turn
metadata/timing, string utilities, and web search helpers.

Recent core helper parity work tightened `pycodex.core.string_utils` against
`codex/codex-rs/utils/string`: UTF-8 boundary truncation, approximate token
math, UUID scanning, markdown hash suffix normalization, metric tag
sanitization, ASCII JSON serialization, and string/usize input boundaries have
targeted tests.

`pycodex.core.session_rollout_init_error` is aligned with
`core/src/session_rollout_init_error.rs` for permission denied, missing storage,
already exists, invalid data/input, unexpected path type, generic fallback, cause
chain scanning, and public argument type boundaries.

Turn 199 continued request-permissions/session parity by documenting the
strict-auto-review bridge from in-memory turn grants into the session-aware tool
orchestrator plan helper. The added coverage confirms a turn-scoped strict grant
drives guardian-backed requested approval planning while preserving the
standard-library-first Python surface. Validation remains pending because no
test run was requested.

Turn 200 closed a smaller strict-auto-review edge case from
`core/src/session/mod.rs`: empty request-permissions responses are returned and
ignored before grant recording, so an empty turn-scoped response with
`strict_auto_review` does not enable strict review state. Coverage now documents
that behavior both at the shared helper layer and through `InMemoryCodexSession`.
Validation remains pending because no test run was requested.

Turn 201 moved the Python `request_permissions` handler closer to
`core/src/tools/handlers/request_permissions.rs` by deriving `call_id` and
`turn.cwd` from a full `ToolInvocation` when explicit Python compatibility
arguments are not supplied. This preserves the existing direct payload helper
surface while making routed tool invocations resolve relative filesystem
requests from the active turn cwd, as Rust does. Validation remains pending
because no test run was requested.

Turn 202 tightened the model-visible `request_permissions` tool spec against
`core/src/tools/handlers/shell_spec.rs` by adding the explicit
`output_schema: None` field that Rust carries on `ResponsesApiTool`. The schema
coverage now checks the field alongside `strict`, `defer_loading`, required
parameters, and permission-profile properties. Validation remains pending
because no test run was requested.

Turn 203 tightened the Python `RequestPermissionsHandler` dispatch shape to
match `core/src/tools/handlers/request_permissions.rs`: only function payloads
are considered a supported kind. The handler already rejects non-function
payloads at execution time; the route-time `matches_kind` predicate now agrees
and no longer advertises `tool_search` compatibility. Validation remains
pending because no test run was requested.

Turn 204 moved `RequestPermissionsHandler` closer to the Rust runtime path by
falling back to `invocation.session.request_permissions_for_cwd(...)` when no
compatibility callback is supplied. The Python tool router already awaits
awaitable handler results, so routed invocations can now pass the active turn,
call id, requested permissions, cwd, and cancellation token through the session
object, matching the shape of `session.request_permissions(&turn, call_id,
args, cancellation_token)` in Rust. Validation remains pending because no test
run was requested.

Turn 205 tightened the cancellation edge case for that session fallback:
awaitable session responses that resolve to `None` now produce the same
`request_permissions was cancelled before receiving a response` model-facing
error as Rust's `ok_or_else(...)` branch, instead of falling through to response
coercion. Validation remains pending because no test run was requested.

Turn 206 connected the request-permissions session fallback to the routed core
tool path. The registry-side `ToolInvocation` now carries optional
`session`, `turn`, `cancellation_token`, and `tracker` fields, and
`ToolRouter.dispatch_tool_call_with_terminal_outcome()` populates them from its
store arguments when constructing an invocation. This lets a routed
`RequestPermissionsHandler` call the session fallback with the same contextual
shape Rust passes through `ToolInvocation`. Validation remains pending because
no test run was requested.

Turn 207 removed a duplicate-schema drift in the Python shell tool spec: the
`pycodex.core.shell_spec.create_request_permissions_tool()` helper now also
emits explicit `output_schema: None`, matching Rust's `ResponsesApiTool` shape
and the dedicated request-permissions handler spec. Validation remains pending
because no test run was requested.

Turn 208 added parity coverage for the on-request permissions instruction
composition path from `core/src/context/permissions_instructions.rs`: when
exec permission approvals, the `request_permissions` tool, and approved command
prefixes are all present, Python now documents the Rust ordering of permission
request guidance, request-permissions tool guidance, then approved prefixes.
Validation remains pending because no test run was requested.

Turn 209 added a Python spec-planning helper for the Rust
`Feature::RequestPermissionsTool` gate in `core/src/tools/spec_plan.rs`.
`add_request_permissions_tool(...)` now adds `RequestPermissionsHandler` only
when the feature flag is enabled, producing both a model-visible
`request_permissions` spec and a dispatch registry entry. Validation remains
pending because no test run was requested.

Turn 210 locked the feature metadata side of that gate: Python coverage now
asserts `request_permissions_tool` resolves to `Feature.REQUEST_PERMISSIONS_TOOL`,
is known to the feature registry, remains under development, and is disabled by
default. This documents the intended default-off behavior that keeps the tool
out of model-visible planning unless explicitly enabled. Validation remains
pending because no test run was requested.

Turn 211 added a focused Python context-update helper for the permissions
instructions branch in `core/src/context_manager/updates.rs`. The helper emits
no update for first-context or feature-only changes, and when permission profile
or approval policy changes it renders `PermissionsInstructions` using both
`ExecPermissionApprovals` and `RequestPermissionsTool` feature flags from the
next context. Validation remains pending because no test run was requested.

Turn 212 tightened that helper's approval-policy comparison by unwrapping
cell-like previous approval policy values before comparing them to the next
context's effective policy. This keeps Python's focused context update helper
compatible with both direct enum fields and Rust-like `.value()` wrappers.
Validation remains pending because no test run was requested.

Turn 213 exported the focused permissions context-update helper through the
public `pycodex.core` API and switched its coverage to import from that surface.
This keeps the new helper aligned with the rest of the core porting helpers and
makes it available for later session/context-manager integration without
reaching into the module directly. Validation remains pending because no test
run was requested.

Turn 214 added the neighboring collaboration-mode update branch from
`core/src/context_manager/updates.rs`. The new helper respects the
`include_collaboration_mode_instructions` config flag, emits nothing without a
previous context, skips unchanged modes, and preserves Rust's behavior of
omitting updates when the next collaboration mode has empty developer
instructions. Validation remains pending because no test run was requested.

Turn 215 added the realtime update branch from
`core/src/context_manager/updates.rs`. Python now has focused helpers for
regular and initial realtime updates that render realtime start instructions,
custom realtime start instructions, and inactive end instructions according to
the previous context, previous turn settings, and next realtime state.
Validation remains pending because no test run was requested.

Turn 216 added the personality update branch from
`core/src/context_manager/updates.rs`. Python now mirrors the feature gate,
previous-context requirement, same-model requirement, changed-personality
requirement, and non-empty model personality message filter before rendering
`PersonalitySpecInstructions`. Validation remains pending because no test run
was requested.

Turn 217 added the model-instructions update branch from
`core/src/context_manager/updates.rs`. Python now emits model-switch
instructions only when previous turn settings exist, the model slug changes,
and the next model returns non-empty model instructions for the current
personality. Validation remains pending because no test run was requested.

Turn 218 added the text-message construction helpers from
`core/src/context_manager/updates.rs`. Python now mirrors the developer and
contextual-user update item builders: empty section lists emit no message, while
non-empty sections become a single `ResponseItem::Message` with one input-text
content item per section. Validation remains pending because no test run was
requested.

Turn 219 added a focused settings-update assembler mirroring the ordering in
`core/src/context_manager/updates.rs`: model-switch instructions first, then
permissions, collaboration mode, realtime, and personality sections in one
developer message, followed by an optional contextual-user update item. The
environment diff itself remains a future slice, but the model-visible ordering
and message packing are now represented. Validation remains pending because no
test run was requested.

Turn 220 added the legacy single-environment contextual-user update branch from
`core/src/context_manager/updates.rs`. Python now skips updates when environment
context injection is disabled, when no previous item exists, or when only the
shell changes, and emits an `EnvironmentContext` diff response item when the
next cwd/date/timezone/network context changes. Validation remains pending
because no test run was requested.

`pycodex.core.installation_id` is aligned with
`core/src/installation_id.rs` for creating the Codex home, generating UUIDv4
installation ids, canonicalizing existing UUID contents, rewriting invalid
contents, Unix mode repair, file locking, fsync persistence, and public argument
type boundaries.

`pycodex.core.paths` is aligned with `utils/home-dir` and the runtime DB path
slice of `codex-state`: `CODEX_HOME` validation/canonicalization, default
`~/.codex` fallback, state/logs/goals/memories SQLite filenames, runtime DB
path ordering, and public path argument boundaries have targeted tests.

`pycodex.core.approval_presets` is aligned with
`utils/approval-presets`: built-in preset order, labels/descriptions, approval
policies, active permission profile ids, concrete permission profiles, built-in
profile lookup behavior, and structure field type boundaries have targeted
tests.

However, the full core runtime is not done. Large or sensitive areas still need
systematic parity work:

| Upstream area | Current priority | Notes |
| --- | --- | --- |
| Session and turn orchestration | High | Needed for real Codex runtime behavior. |
| Agent loop and tool orchestration | High | Core user-visible behavior depends on this. |
| MCP runtime integration | High | Many helper types exist; full server/tool lifecycle remains. |
| Unified exec and sandbox integration | High | Needed for safe command execution parity. |
| Config loading/building | High | Existing pieces should be reconciled with upstream `core/config`. |
| Guardian/approval flow | High | Permission and approval behavior must match closely. |
| Realtime conversation paths | Medium | Important but can follow non-interactive runtime parity. |
| Plugin and skill loading | Medium | Many helper modules exist; integration should be audited. |
| State/thread storage | Medium | Needed for persistence parity. |
| Windows/macOS/Linux sandbox details | Medium | Platform differences should stay isolated. |

## Known Placeholders

The current Python command surface intentionally acknowledges several upstream
features without implementing them yet:

| Feature | Current state |
| --- | --- |
| Interactive TUI | Recognized, not implemented. |
| `mcp-server` | Recognized, not implemented. |
| Cloud browser flows | Parsed, not implemented. |
| `update` | Not implemented. |
| Miscellaneous command bodies | Some commands are recognized but still placeholder-only. |

## Recommended Next Milestones

1. Make this status file stricter by adding one row per upstream source file for
   `protocol`, then `exec`, then `shell-command`.
2. Close protocol gaps first, because they are relatively small and unlock core
   parity tests.
3. Port the non-interactive `exec` runtime path end-to-end before attempting the
   interactive TUI.
4. Build a minimal but faithful core session/turn loop using standard-library
   primitives before adding advanced integrations.
5. Leave `tui` until the core runtime has enough parity to drive it.

## Rules for Updating This File

When a module is advanced:

1. Record the exact upstream source file or directory used as the reference.
2. Record the Python file that implements the behavior.
3. Mark whether the work is a foundation, partial port, substantial port, or
   parity-complete.
4. Add the test file or verification evidence.
5. Do not mark a module parity-complete only because imports or smoke tests pass.

- Aligned pycodex.core.agent_status with Rust core/src/agent/status.rs by dropping task_* alias status transitions and rejecting non-event/non-matching payload shapes instead of coercing arbitrary objects.
- Expanded agent-status tests for strict event payloads, invalid field types, and ignored legacy task aliases.

- Tightened pycodex.core.session_prefix to match Rust session_prefix.rs signatures: agent references must be strings, notification statuses must be AgentStatus, and nicknames must be string-or-None.
- Updated session-prefix tests to use AgentStatus values directly and cover rejected non-Rust input shapes.

- Tightened pycodex.core.hook_names HookToolName construction around Rust-like string fields and tuple-only matcher aliases, removing implicit alias iterable coercion.
- Expanded hook-name tests for non-Rust direct construction shapes.

- Aligned pycodex.core.original_image_detail with codex_tools image_detail.rs: non-original Auto/Low/High details are preserved, original is gated by model support, and non-Rust input shapes are rejected.
- Expanded original-image-detail tests for Auto/Low preservation and strict model/detail/support flag inputs.

- Tightened pycodex.core.sandbox_tags around Rust-like typed inputs for sandbox flags, permission profiles, Windows sandbox levels, filesystem policies, network policies, and cwd path values.
- Expanded sandbox-tags tests for rejected non-Rust input shapes while preserving existing platform/policy tag behavior.

- Tightened pycodex.core.turn_timing around Rust-like ResponseEvent, ResponseItem, TurnItem, and monotonic timestamp inputs; output-item events now require a ResponseItem payload.
- Expanded turn-timing tests for rejected non-Rust event/item/timestamp shapes while keeping TTFT/TTFM behavior intact.

- Tightened pycodex.core.permissions_instructions around Rust-like typed inputs for approval config, reviewer enums, boolean permission flags, sandbox/network enums, writable roots, and approved command prefixes without changing prompt text.
- Expanded permissions-instructions tests for rejected non-Rust coercion shapes across prompt config, sandbox text, approval text, writable roots, and command prefix policy.

- Tightened pycodex.core.auto_compact_window around Rust u64/i64 numeric boundaries, TokenUsage inputs, non-negative stored prefill tokens, and saturating ordinal increments.
- Expanded auto-compact-window tests for rejected bool/float/out-of-range/non-protocol inputs while preserving server-observed-over-estimated behavior.

- Added mention-syntax coverage asserting pycodex.core sigil constants match codex_utils_plugins/core re-exports for tool ($) and plugin-text (@) mentions.

- Tightened pycodex.core.review_format around Rust-like ReviewFinding/ReviewOutputEvent and bool selection inputs without changing rendered review text.
- Expanded review-format tests for rejected non-Rust formatting inputs.

- Tightened pycodex.core.environment_selection to match Rust slice-based TurnEnvironmentSelection inputs, string environment ids, path cwd values, manager method requirements, and typed resolved TurnEnvironment containers.
- Updated environment-selection tests to use explicit TurnEnvironmentSelection values and cover rejected dict/non-selection/non-manager input shapes.

- Aligned pycodex.exec.event_processor human reasoning rendering with Rust exec/src/event_processor_with_human_output.rs: when raw agent reasoning is enabled and raw content exists, human output now renders raw content instead of concatenating summary plus raw content; when raw content is absent it falls back to summary text.
- Updated exec event-processor tests for raw-reasoning preference and summary fallback behavior.

- Added pycodex.exec.cli effective sandbox projection mirroring exec/src/lib.rs precedence: removed `--full-auto` maps to `workspace-write`, dangerous bypass maps to `danger-full-access`, otherwise the explicit sandbox flag is preserved.
- Reused that projection from pycodex.exec.config_plan and expanded exec CLI tests for the runtime-facing sandbox behavior.

- Added exec entrypoint parity guards for root `-c` override ordering from exec/src/main.rs and explicit `ephemeral: false` thread/start request serialization from exec/src/lib.rs.
- Expanded exec CLI/session tests to lock those Rust-facing contracts before deeper runner integration work.

- Added exec bootstrap-to-session config projection so Python's exec config planning can feed the thread/start request builder the same runtime-facing values Rust derives through ConfigBuilder: model/provider, cwd, workspace roots, user instructions, approval policy, sandbox-derived permission profile, and ephemeral mode.
- Expanded exec config-plan tests for the new bridge from CLI/config bootstrap state to ExecSessionConfig.

- Added exec runtime startup composition helper that combines config bootstrap planning, session config projection, and initial run operation preparation into one pre-agent startup object.
- Expanded exec config-plan tests for the CLI-to-startup-plan path, giving future runner integration a single tested preparation sequence before the real agent loop starts.

- Added startup-plan-to-thread-bootstrap request bridge for exec so the prepared runtime startup state can produce the existing thread/start or thread/resume request shape without duplicating session request construction logic.
- Expanded exec config-plan tests to cover the CLI/config/startup path through thread bootstrap request generation.

- Added startup-plan-to-initial-operation request bridge for exec so the same prepared runtime startup state can produce the first turn/review request after thread bootstrap.
- Expanded exec config-plan tests to cover the CLI/config/startup path through initial operation request generation.

- Added startup-plan helper for the post-bootstrap initial operation request path, using the actual thread id from ThreadBootstrapResult and the shared RequestIdSequencer.
- Expanded exec config-plan tests for the Rust-like sequence of thread bootstrap response followed by initial turn request generation.

- Added startup-plan helpers for composing the final ExecSessionStartupResult after the initial operation response, bridging prepared startup state, ThreadBootstrapResult, and InitialOperationResult into the event-loop-ready state object.
- Expanded exec config-plan tests for the Rust-like startup sequence through initial operation response handling.

- Added exec runtime request sequence object that owns startup state, request id sequencing, the first thread bootstrap request, and post-bootstrap helpers for initial operation request and startup result composition.
- Expanded exec config-plan tests for the request id sequence `thread/start` then `turn/start`, moving the Python exec startup path closer to a runner-consumable control flow.

- Added startup processor-action bridge on the exec runtime request sequence so the event processor actions after startup can be produced from the same startup state and ExecSessionStartupResult.
- Expanded exec config-plan tests for config summary and non-JSON startup warning action generation.

- Added exec runtime request sequence bridge into the first event-loop step, reusing startup loop state, the shared request id sequencer, and session-layer exec_loop_step.
- Expanded exec config-plan tests for processing a post-startup turn/completed notification through the sequence object.

- Added exec runtime request sequence action conversion for post-startup events, delegating loop step results to the session-layer exec_loop_actions_from_step helper.
- Expanded exec config-plan tests for converting a post-startup turn/completed event directly into runner-consumable process_notification actions.

- Added exec runtime request sequence helper for applying thread/read backfill responses to pending loop events, closing the empty turn/completed items branch through process_notification actions once full turn items are available.
- Expanded exec config-plan tests for the backfill path from empty turn/completed notification to thread/read response to completed notification processing.

- Tightened pycodex.core.command_canonicalization around Rust &[String] argv inputs, rejecting string-as-command and non-string argv tokens before canonicalization.
- Expanded command-canonicalization tests for rejected non-Rust command shapes.

- Tightened pycodex.core.app_plugin_rendering to match Rust slice inputs for AppInfo, PluginCapabilitySummary, and string MCP/app capability names, removing dict/object/string coercion in render helpers.
- Expanded app/plugin rendering tests for rejected non-Rust input shapes while keeping rendered instruction text stable.

- Tightened pycodex.core.tool_context ToolPayload around Rust enum-variant invariants: function/custom/tool_search payloads now require their own typed field and reject mixed or missing variant data.
- Expanded tool-context tests for rejected non-Rust ToolPayload shapes without changing output rendering behavior.
- Tightened pycodex.core.user_shell_command entrypoints around Rust parameter shapes for command strings, exec outputs, and truncation policy configs.
- Added user-shell-command boundary tests while preserving the existing rendered record and timeout/truncation behavior.
- Tightened pycodex.core.network_policy_decision parsing and amendment helpers to match Rust's deny/ask-only decision parsing and explicit protocol/action handling.
- Added network-policy-decision boundary tests for non-string decisions, direct BlockedRequest construction, and amendment input shapes.
- Tightened pycodex.core.turn_metadata client metadata merging to preserve Rust's reserved-key filtering for session/thread/turn/timing/fork/request/compaction/window fields.
- Added turn-metadata boundary tests for reserved client metadata and Rust-shaped string/i64 setter inputs.
- Tightened pycodex.core.agent_roles around Rust-shaped role metadata: descriptions/names remain strings, config files remain Paths, nickname candidates must be string iterables, and spawn-tool role maps reject malformed values.
- Added agent-role boundary tests for nickname candidate inputs, role config construction, spawn-tool maps, and nickname reset counts.
- Tightened pycodex.core.hosted_spec ToolSpec variants so image-generation, custom/freeform, and web-search specs reject mixed or malformed Rust enum shapes.
- Added hosted-spec boundary tests for image output formats, mixed ToolSpec variants, and WebSearchToolOptions inputs.
- Tightened pycodex.core.stream_events_utils pure helpers around Rust-shaped path/string/bool/ResponseItem/ResponseInputItem inputs without changing visible text stripping or image artifact behavior.
- Added stream-events-utils boundary tests for image artifact inputs, base64 payload typing, item typing, and plan-mode typing.
- Tightened pycodex.core.tool_definition so ToolDefinition name/description/defer_loading and renamed/from_mapping inputs retain Rust String/bool shapes instead of implicit Python coercions.
- Added tool-definition boundary tests for malformed scalar fields and deferred-loading mapping input.
- Tightened pycodex.core.git_info around Rust-shaped Path/String/GitSha/i64/usize inputs for git metadata helpers, command arguments, remote parsing, commit entries, and diff metadata.
- Added git-info boundary tests for remote URL parsing, recent commit limits, and git metadata dataclass construction.
- Tightened pycodex.core.goals pure helpers to keep Rust-shaped ModeKind, Option<i64>, TokenUsage, ThreadGoal, and String inputs instead of parsing or coercing broader Python values.
- Added goals boundary tests for mode handling, goal budget i64 limits, prompt inputs, token usage inputs, and XML escaping inputs.
- Tightened pycodex.core.apply_patch data structures around Rust enum/struct shapes for parse errors, hunks, update chunks, patch args, file changes, actions, file updates, and freeform-tool environment flags.
- Added apply-patch boundary tests for malformed variants, mixed fields, non-string line data, mapping-key shapes, and include_environment_id typing.
- Tightened pycodex.core.plugin_mentions around Rust-shaped string/path/message/sigil/user-input/connector fields, preserving mapping compatibility while removing broad str(...) coercions.
- Added plugin-mentions boundary tests for non-string paths, messages, sigils, user-input text/path fields, and connector names.
- Tightened pycodex.core.config_lock around Rust-shaped u32 lock versions, bool replay options, path-like public inputs, mutable config maps, string labels, and lock layer Path/profile fields.
- Added config-lock boundary tests for codex_version typing, replay option typing, u32 version bounds, mutable config controls, lock layer shapes, and TOML label typing.
- Tightened `pycodex.core.config_edit` helper inputs toward Rust `config/edit.rs`: string/bool/path/count/map boundaries now reject implicit coercions, and added focused tests for those edge cases.
- Tightened `pycodex.core.code_mode` request/definition dataclasses toward Rust `code-mode` structs by rejecting implicit string/bool/integer coercions and non-string runtime store keys.
- Aligned `pycodex.core.managed_features` with current Rust profile scope and tightened feature requirement source/key/bool inputs to avoid implicit coercions.
- Aligned `pycodex.core.personality_migration` with current Rust top-level `ConfigToml` semantics: profile personality no longer blocks migration, and path/string inputs reject implicit coercions.
- Tightened `pycodex.core.safety` patch safety inputs and `SafetyCheck` variants to match Rust enum/typed-argument boundaries without changing approval semantics.
- Tightened `pycodex.core.exec_env` core wrapper to match Rust `Option<ThreadId>` and `(String, String)` env-pair inputs instead of accepting implicit string/value coercions.
- Fixed `pycodex.core.thread_rollout_truncation` to match Rust suffix truncation semantics by dropping startup prefix before the first fork turn, and tightened usize count inputs.
- Tightened `pycodex.core.shell_snapshot` helper inputs toward Rust `AbsolutePathBuf`/`ShellType`/`ThreadId` string boundaries, rejecting implicit Path and shell-type coercions.
- Tightened `pycodex.core.tool_dispatch_trace` requester/payload/result dataclasses to enforce Rust enum variant shapes and JSON result boundaries.
- Tightened `pycodex.core.tool_dispatch_trace` toward Rust `ToolDispatchTrace`: added a callback-friendly start/completed/failed facade, disabled-context no-op behavior, completed status derivation, and silent skipping for unmappable result payloads while leaving rollout writer persistence injectable.
- Tightened `pycodex.core.tool_search_entry` loadable-spec and source-info inputs to match Rust string/list struct boundaries instead of implicit coercions.
- Tightened `pycodex.core.tool_search_entry` namespace-tool parity: loadable namespace specs now require every child tool to be a function, matching Rust's `ResponsesApiNamespaceTool::Function`-only conversion boundary.
- Tightened `pycodex.core.tool_discovery` discoverable connector/plugin metadata, request-plugin-install entries, list fields, bool/string inputs, and `ToolSearchSourceInfo` export to match Rust `tools/src/tool_discovery.rs` boundaries.
- Tightened `pycodex.core.tool_discovery` client-filter boundary: `filter_request_plugin_install_discoverable_tools_for_client` now requires `app_server_client_name` to be `str` or `None`, matching Rust's `Option<&str>` contract instead of accepting arbitrary Python values.
- Tightened `pycodex.core.tool_search_handler` around Rust `tool_search` handler/spec slice inputs, `usize` limits, query strings, payload typing, and result-entry typing while preserving the standard-library BM25 implementation.
- Tightened `pycodex.core.request_plugin_install` Rust-overlapping args/result/meta, elicitation request ids, connector/plugin completion checks, and handler payload matching to avoid implicit Python coercions.
- Tightened the list-available-plugin install handler path inside `pycodex.core.request_plugin_install` to match Rust entry-vector and char-boundary truncation input shapes.
- Tightened `pycodex.core.request_plugin_install` handler edge coverage for Rust model-visible rejection branches: unsupported install actions, missing Python elicitation callback boundary, and non-negative char-boundary truncation limits.
- Tightened `pycodex.core.tool_router` FunctionCallError variants, ToolCall field boundaries, router construction inputs, and build-tool-call item typing toward Rust `tools/src/function_call_error.rs` and `core/src/tools/router.rs`.
- Tightened `pycodex.core.tool_registry` registration, exposure override, tool invocation/source, hook payload, and runtime trait-return boundaries toward Rust `core/src/tools/registry.rs`.
- Added `pycodex.core.plan_handler` for Rust `core/src/tools/handlers/plan.rs` and `plan_spec.rs`: update-plan spec, argument parsing, Plan-mode rejection, callback boundary for plan events, and model-visible "Plan updated" output.
- Restored `pycodex.core.plan_handler` runtime matching parity: update-plan now accepts function and tool-search payload kinds for dispatch matching, mirroring Rust's default `CoreToolRuntime::matches_kind` behavior.
- Added `pycodex.core.request_user_input_handler` for Rust `core/src/tools/handlers/request_user_input.rs` and spec helpers: question schema, available-mode text/errors, option normalization, root-thread guard, callback response boundary, and serialized success output.
- Tightened `pycodex.core.request_user_input_handler` with a Rust-shaped available-mode helper: default availability is Plan mode only, while the default-mode feature path returns Default or Plan and drives the same description/unavailable-message behavior as upstream.
- Tightened `pycodex.core.request_user_input_handler` runtime/error parity: request-user-input keeps Rust default dispatch matching for function/tool-search payload kinds and maps option-normalization failures to `FunctionCallError.respond_to_model`, matching Rust handler behavior.
- Added `pycodex.core.request_permissions_handler` for Rust `core/src/tools/handlers/request_permissions.rs` and shell-spec helpers: request-permissions schema/description, argument parsing, empty-permission rejection, callback response boundary, cancellation message, and serialized success output.
- Tightened `pycodex.core.request_permissions_handler` toward Rust `parse_arguments_with_base_path`: filesystem read/write permission paths can now be resolved against an absolute cwd during parsing while absolute paths remain unchanged.
- Added `pycodex.core.test_sync_handler` for Rust `core/src/tools/handlers/test_sync.rs` and `test_sync_spec.rs`: internal test-sync spec, sleep fields, barrier args/default timeout, participant/timeout errors, timeout behavior, and "ok" success output using only standard-library threading primitives.
- Tightened `pycodex.core.test_sync_handler` barrier parity: timed-out waits no longer poison the registered barrier, allowing later calls with the same id/participant count to rendezvous like the Rust Tokio barrier guarded by `timeout()`.
- Tightened `pycodex.core.request_plugin_install` list-available handler parity: unsupported payloads now raise the shared fatal `FunctionCallError`, matching Rust's internal protocol-error boundary instead of surfacing as a generic value error.
- Tightened `pycodex.core.request_plugin_install` request handler parity: unsupported or malformed non-function payloads now use the shared fatal `FunctionCallError`, matching Rust's `request_plugin_install` handler boundary.
- Tightened `pycodex.core.request_plugin_install` model-error parity: argument parse failures and request validation failures now raise `FunctionCallError.respond_to_model`, matching Rust's recoverable model-visible error boundary.
- Tightened `pycodex.core.request_plugin_install` response-shaping parity: callback results now contribute only completion/confirmation state while the handler reconstructs tool type, action, id, name, and trimmed reason from validated request/discoverable-tool data like Rust.
- Tightened `pycodex.core.request_plugin_install` runtime matching parity: list-available and request-plugin-install handlers now accept function and tool-search payload kinds for dispatch matching, mirroring Rust's default `CoreToolRuntime::matches_kind` behavior while keeping function-only `handle` validation.
- Added `pycodex.core.view_image_handler` for Rust `core/src/tools/handlers/view_image.rs` and `view_image_spec.rs`: view-image tool metadata, argument/detail validation, local-file data URL loading, code-mode image output shaping, and basic filesystem error reporting with stdlib-only helpers.
- Tightened `pycodex.core.view_image_handler` image processing parity: data URL creation now performs lightweight stdlib image-signature validation so files with image extensions but invalid bytes are rejected before being returned to the model.
- Added `pycodex.core.goal_handler` for Rust `core/src/tools/handlers/goal.rs` and `goal_spec.rs`: get/create/update goal specs, strict argument parsing, JSON response shaping with remaining-token and completion-budget report fields, terminal-status enforcement, and a stdlib in-memory store mirroring the session goal methods used by the Rust handlers.
- Tightened `pycodex.core.goal_handler` response shaping to match Rust `GoalToolResponse::new`: completion budget report text is now emitted only for completed goals, even when the include-report mode is requested and budget/time fields are present.
- Tightened `pycodex.core.goal_handler` parallel-dispatch parity: get/create/update goal handlers now inherit Rust's default non-parallel tool behavior instead of advertising goal state reads/writes as parallel-safe.
- Tightened `pycodex.core.goal_handler` runtime matching parity: get/create/update goal handlers now accept function and tool-search payload kinds for dispatch matching, mirroring Rust's default `CoreToolRuntime::matches_kind` behavior.
- Added `pycodex.core.mcp_resource_handler` for Rust `core/src/tools/handlers/mcp_resource.rs` and `mcp_resource_spec.rs`: list/read MCP resource specs, optional/default argument parsing, cursor/server normalization, all-server sorting, read-result flattening, and stdlib provider-backed list/read handlers.
- Tightened `pycodex.core.mcp_resource_handler` read-resource argument parsing to match Rust `parse_args`: empty or `null` arguments now surface the model-visible `expected value` error, while non-object JSON surfaces an `expected object` parse error.
- Tightened `pycodex.core.mcp_resource_handler` runtime matching parity: list/read MCP resource handlers now accept function and tool-search payload kinds for dispatch matching, mirroring Rust's default `CoreToolRuntime::matches_kind` behavior while keeping function-only `handle` validation.
- Added `pycodex.core.extension_tools` for Rust `core/src/tools/handlers/extension_tools.rs`: extension executor adapter metadata proxying, function-payload matching, invocation-to-extension-call conversion, turn context/history forwarding, and strict stdlib-only executor boundary checks.
- Tightened `pycodex.core.extension_tools` adapter parity: `handle()` now passes payloads through to the extension call without revalidating kind, leaving function-only filtering to `matches_kind` like the Rust `CoreToolRuntime` implementation.
- Added `pycodex.core.agent_jobs` for Rust `core/src/tools/handlers/agent_jobs.rs` and `agent_jobs_spec.rs`: spawn/report tool specs, strict argument parsing, CSV parsing/escaping/rendering, instruction template substitution, item-id/source-id construction, concurrency/runtime normalization, prepare-only CSV job setup, and stdlib in-memory result reporting/cancellation.
- Tightened `pycodex.core.agent_jobs` around Rust worker prompt construction: Python now renders the full per-row worker instruction with job/item ids, rendered CSV-row task text, pretty row JSON, optional output schema, and the mandatory `report_agent_job_result` call contract.
- Added `pycodex.core.multi_agents_spec` for Rust `core/src/tools/handlers/multi_agents_spec.rs`: v1 namespace and v2 direct multi-agent tool specs, spawn/send/followup/resume/wait/list/close schemas, output schemas, model override description rendering, metadata-hiding behavior, collab input item schema, and wait-timeout parameter generation.
- Added `pycodex.core.multi_agents_common` for pure Rust `core/src/tools/handlers/multi_agents_common.rs` helpers: function-payload extraction, JSON/code-mode/response-item output shaping, wait-agent status ordering with receiver metadata, collab message/items validation, and full-history fork override rejection.
- Added `pycodex.core.shell_spec` for Rust `core/src/tools/handlers/shell_spec.rs`: exec_command/write_stdin/shell_command/request_permissions tool specs, unified-exec output schema, approval/additional-permission schemas, Windows shell guidance text, environment-id variant, and strict command option typing.
- Added `pycodex.core.unified_exec_handler` for Rust `core/src/tools/handlers/unified_exec`: argument defaults/parsing, environment args, write_stdin args, command resolution including zsh-fork mode, exec/write_stdin handler specs, Bash pre/post hook payloads, and hook command rewriting. Real process execution remains outside the stdlib port.
- Added `pycodex.core.shell_handler` for the pure Rust `shell_command` handler boundary: shell-command params, backend config mapping, login-shell rejection/defaulting, base shell command construction, Bash pre/post hook payloads, hook command rewriting, spec exposure, parallel support, and runtime-cancellation flag. Shell runtime/orchestrator execution remains outside this stdlib-only slice.
- Tightened `pycodex.core.shell_handler` model-error parity: disallowed login-shell requests and shell-command hook-input rewrite failures now raise `FunctionCallError.respond_to_model`, matching Rust `ShellCommandHandler` recoverable error boundaries.
- Added `pycodex.core.multi_agents_v2_handler` for pure MultiAgentV2 and adjacent resume-agent handler boundaries: list/close/send/followup/spawn/wait/resume argument parsing with unknown-field rejection where Rust applies it, text-message validation, delivery-mode trigger shaping, fork-turn parsing, full-history override rejection, wait-timeout bounds, UUID id parsing, spawn/list/close/wait/resume result serialization, tool specs/search metadata, function-payload matching, and optional callback-backed handlers.
- Added `pycodex.core.multi_agents_v1_handler` for pure MultiAgentV1 spawn_agent/send_input/close_agent/wait_agent boundaries: namespaced tool names, agent-id parsing, non-empty target validation, collab input validation reuse, interrupt and fork_context flag parsing, full-history override rejection, v1 wait timeout clamp semantics, spawn/send/close/wait result serialization, tool specs/search metadata, and callback-backed handler facades.
- Tightened `pycodex.core.mcp_tool_handler` around Rust MCP handler hook behavior: legacy `mcp__` prefix helpers, namespace/name joining, hook input JSON-or-raw parsing, MCP pre/post hook payload shaping, hook input rewriting, and exports/tests for the pure handler boundary.
- Tightened `pycodex.core.mcp_tool_handler` model-error parity: unsupported payloads, JSON parse failures, missing Python callback boundaries, and hook-input rewrite failures now raise `FunctionCallError.respond_to_model`, matching Rust MCP handler recoverable error behavior.
- Tightened `pycodex.core.mcp_tool_handler` runtime matching parity: MCP tool handlers now accept function and tool-search payload kinds for dispatch matching, mirroring Rust's default `CoreToolRuntime::matches_kind` behavior while keeping function-only `handle` validation.
- Tightened `pycodex.core.dynamic_tool_handler` with pure dynamic-tool request/response event builders matching Rust `request_dynamic_tool`: request events carry call/turn/tool namespace/name/arguments/timestamp, response events encode successful content items or the cancellation error shape without needing async session plumbing.
- Tightened `pycodex.core.dynamic_tool_handler` model-error parity: unsupported payloads, JSON argument parse failures, and missing/cancelled dynamic responses now raise the shared `FunctionCallError.respond_to_model`, matching Rust's dynamic handler boundary.
- Tightened `pycodex.core.dynamic_tool_handler` runtime matching parity: dynamic tool handlers now accept function and tool-search payload kinds for dispatch matching, mirroring Rust's default `CoreToolRuntime::matches_kind` behavior while keeping function-only `handle` validation.
- Tightened `pycodex.core.dynamic_tool_handler` parallel-dispatch parity: dynamic tool handlers now explicitly expose Rust's default non-parallel `ToolExecutor` behavior.
- Tightened `pycodex.core.tool_search_handler` error-boundary parity: unsupported payloads now raise fatal `FunctionCallError`, while empty queries and zero limits raise model-visible `FunctionCallError.respond_to_model`, matching Rust `tool_search` handler behavior.
- Added `pycodex.core.handler_utils` for shared Rust `tools/handlers/mod.rs` helper logic: model-facing JSON parse errors, function-argument rewriting, hook command updates, workdir/environment resolution, additional-permission feature gate validation, implicit sticky grants, grant merging, and preapproved-permission checks.
- Tightened `pycodex.core.spec_plan` around Rust code-mode planning: explicit planner flags now prepend `exec`/`wait` runtimes when code mode is enabled, hide nested tools from model-visible specs under code-mode-only while preserving registry dispatch, augment nested specs for code-mode prompts, and collect namespace descriptions for code-mode executor construction.
- Tightened `pycodex.core.spec_plan` hosted-tool planning against Rust `hosted_model_tool_specs`: provider web-search support now adds the hosted web-search spec unless a standalone `web.run` executor is available, and image generation is gated on Codex backend auth, provider support, feature enablement, and image-input model support before adding the PNG image-generation hosted spec.
- Added `pycodex.core.tool_lifecycle` for Rust `tools/lifecycle.rs` and extension-api lifecycle payloads: direct/code-mode extension source mapping, completed/blocked/failed/aborted outcomes, start/finish input shaping, and stdlib sync/async contributor notification helpers.
- Tightened `pycodex.core.tool_lifecycle` toward Rust's parts-based finish path: added finish-input and notification helpers that accept call id, tool name, source, and outcome directly, including aborted notifications without requiring a synthetic `ToolInvocation`.
- Tightened `pycodex.core.tool_context.telemetry_preview` to preserve Rust's line-boundary newline behavior before appending the telemetry truncation notice.
- Tightened MCP image content conversion in `pycodex.core.tool_context` so `_meta.codex/imageDetail` accepts Rust's full `auto`/`low`/`high`/`original` set before original-detail sanitization.
- Added `pycodex.core.tool_context` context-shell parity for Rust `tools/context.rs`: trait-like `ToolOutput` boundary checking, `boxed_tool_output`, `SharedTurnDiffTracker`, `ToolCallSource` direct/code-mode variants, and `ToolInvocation` runtime context wrapping.
- Tightened `pycodex.core.tool_context.ToolInvocation` tool-name parity toward Rust `ToolInvocation { tool_name: ToolName }`: context invocations now normalize string names to plain `ToolName` and reject non-tool-name shapes.
- Aligned `pycodex.core.tool_context.ToolCallSource::CodeMode` field constraints with Rust: `cell_id` and `runtime_tool_call_id` must be strings but are not required to be non-empty.
- Tightened `pycodex.protocol.tool_name` with a centralized `from_value` constructor for Rust `From<&str>`/`From<String>` parity while preserving existing `ToolName` instances.
- Routed `ToolName.from_value` through tool runtime boundaries: `ToolInvocation` and registry handler-name extraction now share the same Rust-like string-to-plain-tool-name conversion path.
- Routed `ToolName.from_value` through `pycodex.core.spec_plan` runtime-name extraction so model-visible planning, registry construction, and invocation contexts share Rust's string-to-plain-`ToolName` conversion semantics.
- Routed code-mode nested tool-name coercion through `ToolName.from_value`/`from_mapping`, preserving Rust string and serde-object inputs while rejecting implicit integer-to-string conversions.
- Routed extension executor tool-name extraction through `ToolName.from_value`, keeping extension adapters aligned with the shared Rust string-to-plain-`ToolName` conversion boundary.
- Routed runtime flat tool-name conversion through `ToolName.from_value`, preserving existing non-empty approval-key validation while sharing the same Rust-like string/`ToolName` normalization path.
- Tightened `pycodex.core.extension_tools` extension-call parity so `ExtensionTurnContext` always supplies a concrete truncation policy, matching Rust `codex_tools::ToolCall`'s non-optional `TruncationPolicy` field.
- Locked extension adapter payload-through tests to assert Rust-like default extension call metadata: empty turn id, concrete default truncation policy, and empty conversation history.
- Tightened `pycodex.protocol.items.HookPromptItem.from_fragments` to match Rust `Option<&String>` semantics: only `None` generates a UUID, while an explicit empty string id is preserved.
- Tightened `pycodex.protocol.items.McpToolCallItem` status validation to match Rust's camelCase `McpToolCallStatus` enum values instead of accepting arbitrary strings.
- Tightened `pycodex.protocol.items` Reasoning turn-item parsing so bare strings no longer get split into character tuples before constructor validation, matching Rust `Vec<String>` deserialization boundaries.
- Tightened `pycodex.protocol.items` turn-item parsers so invalid optional `ImageGeneration.saved_path` and `FileChange.auto_approved` values are rejected by constructors instead of being silently dropped.
- Tightened `pycodex.protocol.items` MCP result/error turn-item parsing so provided optional values must be Rust-shaped mappings instead of being silently ignored.
- Tightened `pycodex.protocol.items` required-field parsing for Rust item structs: `FileChange.changes`, `McpToolCall.arguments`, and `McpToolCall.status` are no longer defaulted when absent.
- Tightened `pycodex.protocol.items.FileChangeItem` changes input to require a mapping shape, matching Rust `HashMap<PathBuf, FileChange>` deserialization instead of accepting arbitrary `dict(...)` coercions.
- Tightened `pycodex.protocol.items` MCP camelCase optional string parsing so explicit empty `mcpAppResourceUri`/`pluginId` values are preserved instead of falling through to compatibility aliases.
- Tightened `pycodex.protocol.items` required-field parsing for additional Rust item structs: `UserMessage.content`, `AgentMessage.content`, `HookPrompt.fragments`, and `WebSearch.action` are no longer synthesized when absent.
- Tightened `pycodex.protocol.items.AgentMessageItem.phase` to use the Rust `MessagePhase` enum boundary, and added explicit `memory_citation` type validation.
- Tightened `pycodex.protocol.items` Reasoning turn-item parsing so Rust's required `summary_text: Vec<String>` field is no longer defaulted, while `raw_content` remains defaultable.
- Tightened `pycodex.protocol.items.WebSearchItem.action` to normalize mapping input into `WebSearchAction` and reject arbitrary non-action values, matching Rust's `WebSearchAction` field boundary while preserving serde-style unknown-action fallback.
- Tightened `pycodex.protocol.models.ResponseItem.from_mapping` required-field parsing for existing Rust variants: message content, tool-search call arguments/execution, function/custom-tool output payloads, and tool-search output status/execution/tools are no longer defaulted when absent.
- Aligned `pycodex.protocol.models.ResponseItem` tool-search output parsing with Rust's optional `call_id: Option<String>` instead of requiring it on input.
- Added `pycodex.protocol.models.ResponseItem.from_mapping` coverage for Rust reasoning, image-generation, compaction alias, compaction-trigger, and context-compaction variants, including reasoning summary/content tagged parsers.
- Added lightweight `LocalShellStatus`, `LocalShellAction`, and `LocalShellExecAction` protocol models plus `ResponseItem.from_mapping` support for Rust `local_shell_call` payloads, including command/env/timeout field boundaries.
- Preserved Rust optional status fields for `ResponseItem` tool-search and custom-tool call variants instead of dropping them during Python construction/from-mapping.
- Tightened those optional `ResponseItem` status fields to reject non-string present values, matching Rust `Option<String>` deserialization instead of silently treating bad values as absent.
- Tightened `pycodex.protocol.models.ResponseItem.from_mapping` optional string fields across message/reasoning/local-shell/function/tool-search/custom-tool/web-search/image/context-compaction variants so present non-string values no longer disappear as `None`.
- Tightened `pycodex.protocol.models.ResponseItem.from_mapping` optional `MessagePhase` and `WebSearchAction` fields so present malformed values now flow through enum/action parsing errors instead of being silently dropped.
- Tightened `pycodex.protocol.models.WebSearchAction.from_mapping` optional query/url/pattern/queries fields to match Rust `Option<String>` and `Option<Vec<String>>` deserialization instead of dropping malformed values.
- Tightened direct `WebSearchAction` constructors with the same string/list-of-string boundaries so callers cannot bypass the Rust-shaped action invariants.
- Tightened `pycodex.protocol.models` content item constructors and parsers so `ContentItem` and `FunctionCallOutputContentItem` enforce Rust tagged-variant string/detail fields instead of filling invalid or missing payloads with empty strings.
- Tightened `pycodex.protocol.models.SearchToolCallParams` so `query` must be a string and optional `limit` follows Rust `usize` boundaries instead of accepting broad Python `int(...)` coercions.
- Added `pycodex.protocol.models.ShellCommandToolCallParams` for Rust shell-command function arguments, including command/workdir/login/timeout alias/sandbox/prefix/additional-permissions/justification field boundaries.
- Tightened `pycodex.protocol.models.FunctionCallOutputPayload` and body construction to match Rust's string-or-content-item-array wire shape, reject object payload shims, enforce body variant fields, and require `success` to be bool/None.
- Tightened `pycodex.core.tool_registry` around Rust `waits_for_runtime_cancellation`: core runtimes, registered tools, exposure overrides, and registry queries now expose the cancellation-wait metadata used by parallel dispatch.
- Added `pycodex.core.tool_parallel` for the pure Rust `tools/parallel.rs` boundaries: runtime dispatch decisions, cancellation terminal-outcome flagging, Rust-matched aborted messages, payload-specific failure responses, aborted tool results, pre-cancelled lifecycle notification, and router cancellation-wait queries. Tokio/task orchestration remains outside this stdlib-only slice.
- Tightened `pycodex.core.tool_parallel` aborted lifecycle dispatch to use the Rust-shaped parts notification path directly, preserving explicit direct/code-mode sources without constructing a synthetic invocation.
- Tightened `pycodex.core.tool_router` around Rust `dispatch_tool_call_with_terminal_outcome`: router dispatch now builds `ToolInvocation`, rejects missing/incompatible tools with Rust-shaped `FunctionCallError`s, invokes stdlib handlers, wraps outputs as `ToolCallResult`, records post-tool-use payloads, and emits start/finish lifecycle notifications with terminal-outcome claiming.
- Tightened post-tool-use result boundaries against Rust `AnyToolResult` and `PostToolUseFeedbackOutput`: Python tool-call results now expose `code_mode_result()`, while post-tool feedback can replace only the model-visible response and preserve the original output's logging, success, and code-mode payload.
- Added `apply_post_tool_use_feedback` to mirror the Rust registry step that wraps successful tool results when PostToolUse hooks provide feedback or stop text, preserving the original output for telemetry/code-mode while replacing the model-visible response.
- Added `pycodex.core.hook_runtime` for the pure outcome semantics from Rust `hook_runtime.rs`: pre-tool-use continue/block decisions and Rust-matched block messages, post-tool-use replacement-text priority, pre/post compact stop outcomes, hook runtime additional-context records, and conversion of additional contexts into ordered developer messages.
- Tightened router dispatch hook integration: stdlib dispatch now accepts optional pre/post hook callbacks, applies pre-tool block and updated-input decisions before handler execution, emits blocked/failed lifecycle outcomes for hook-controlled exits, and applies PostToolUse replacement feedback to successful tool results while preserving code-mode output.
- Tightened `pycodex.core.hook_runtime` request boundaries: added stdlib dataclasses/builders for `PreToolUseRequest`, `PostToolUseRequest`, and `PermissionRequestRequest`, shared hook request context, matcher-alias propagation, subagent/transcript/model/permission-mode fields, and Rust's `never -> bypassPermissions` hook permission-mode mapping.
- Extended `pycodex.core.hook_runtime` to cover the remaining Rust hook request shapes: session-start targets and requests, user-prompt-submit requests, stop/subagent-stop targets and stop requests, pre/post compact requests, compact trigger label normalization, and the root/subagent transcript-path split used by stop hooks.
- Tightened `pycodex.core.tool_sandboxing` against Rust `tools/sandboxing.rs`: permission request payloads and exec approval requirements now reject invalid variant shapes, proposed exec-policy amendments expose a Rust-method-style alias without shadowing the dataclass field, and the default `Approvable` approval-bypass/no-sandbox-approval decisions are available as pure helpers.
- Added the remaining pure runtime boundary structs from Rust `tools/sandboxing.rs`: `ToolCtx`, `ToolError`, and `SandboxAttempt`, including typed option validation for permission profiles, Windows sandbox level, Linux sandbox executable path, legacy Landlock flag, private desktop flag, and network-denial cancellation token without pretending to implement real sandbox manager transforms.
- Tightened `pycodex.core.network_approval` around Rust active/deferred approval lifecycle: added `ActiveNetworkApproval`, `DeferredNetworkApproval`, `begin_network_approval`, immediate finish, and deferred finish-once helpers, preserving cancellation tokens and service outcome consumption without implementing session/guardian/network-proxy integrations.
- Tightened `pycodex.core.network_approval` around Rust inline review decisions: added pure `ReviewDecision` resolution for allow-once, allow-for-session, policy amendment allow/deny, abort/deny, and timeout, plus helpers that update pending host approvals and session approved/denied host caches.
- Tightened `pycodex.core.network_approval` around Rust inline network policy request preflight: added cache-hit decisions, pending-host owner/waiter planning, managed-profile/approval-policy denial gates, exact target/prompt/approval-id shaping, and single-active-call policy outcome recording without faking Session, hook, Guardian, or proxy integration.
- Added `pycodex.core.windows_sandbox_read_grants` for Rust `windows_sandbox_read_grants.rs`: validates non-elevated read-root grants as absolute existing directories, canonicalizes the root, and delegates the setup refresh through an explicit injectable boundary instead of faking Windows sandbox setup in stdlib Python.
- Added `pycodex.core.attestation` for Rust `attestation.rs`: exposes the `x-oai-attestation` header constant, typed attestation request context, provider protocol boundary, async header-generation wrapper, and strict header value normalization for the later client integration.
- Added `pycodex.core.memory_usage` for Rust `memory_usage.rs` and the memory-read usage classifier it delegates to: extracts shell/exec commands from function tool invocations, classifies safe reads/searches of memory files into telemetry tags, and emits `codex.memories.usage` counters through an injected telemetry sink.
- Added `pycodex.core.responses_retry` for Rust `responses_retry.rs`: captures Responses stream retry/fallback decisions, stream retry-after delay handling, first-websocket-retry notification suppression, fallback warning text, and request-kind log message shaping without performing sleeps or client/session side effects.
- Added `pycodex.core.mcp_openai_file` for Rust `mcp_openai_file.rs`: rewrites declared Apps SDK `openai/fileParams` MCP arguments at execution time, supports scalar and array local-file path fields, preserves undeclared/non-object/non-string shapes, emits the uploaded-file payload expected by downstream Apps tools, and keeps the actual OpenAI upload as an injected boundary.
- Added `pycodex.core.client_common` for the pure pieces of Rust `client_common.rs`: loads review prompt/template constants from the mirrored Rust sources, models `Prompt` defaults and formatted-input cloning, and provides a stdlib async `ResponseStream` wrapper that cancels its consumer-dropped token when closed or exhausted.
- Added `pycodex.core.network_proxy_loader` for the portable helper slice of Rust `network_proxy_loader.rs`: models network proxy domain allow/deny overlays, exec-policy network rule application, network constraint overlays, config-layer source classification, config layer mtime tracking, and reload-needed detection without pretending to build the real network proxy runtime.
- Added `pycodex.core.compact` for the pure helper slice of Rust `compact.rs`: loads compaction prompt/template constants, joins textual content items, collects non-contextual user messages, detects compaction summaries, builds token-limited compacted replacement history, inserts refreshed initial context at the Rust-prescribed boundary, and exposes remote-compaction provider selection without running model/session side effects.
- Added `pycodex.core.compact_remote` for the pure post-processing slice of Rust `compact_remote.rs`: filters compacted history to user/assistant/compaction items, reinserts refreshed initial context through the compact helper, and captures compact-request logging byte estimates without running remote model/session side effects.
- Added `pycodex.core.realtime_conversation` for the pure helper slice of Rust `realtime_conversation.rs`: handoff transcript extraction, realtime delegation XML wrapping/escaping, and realtime request-header construction are ported without pretending to implement websocket/audio/session orchestration.
- Added `pycodex.core.shell_detect` for Rust `shell_detect.rs`: recursively detects known shell types from bare names, executable paths, and executable stems while reusing the existing `ShellType` enum.
- Added `pycodex.core.mcp_tool_approval_templates` for Rust `mcp_tool_approval_templates.rs`: loads the bundled consequential-tool template JSON, matches connector/server/tool triples, renders connector-name prompts, orders labeled and remaining tool parameters, and rejects display-name collisions with stdlib-only data structures.
- Added `pycodex.core.review_prompts` for Rust `review_prompts.rs`: renders uncommitted/base-branch/commit/custom review prompts, preserves user-facing hint semantics, and keeps merge-base discovery as an injectable stdlib boundary for later runtime integration.
- Added `pycodex.core.compact_remote_v2` for the pure retained-history slice of Rust `compact_remote_v2.rs`: filters v2 retained prompt items, appends the compaction output, estimates message text tokens, truncates newest-first under a token budget, and preserves image content without implementing async model/session compaction.
- Added `pycodex.core.windows_sandbox` for the pure configuration slice of Rust `windows_sandbox.rs`: resolves explicit and legacy Windows sandbox modes, maps feature flags to `WindowsSandboxLevel`, preserves private-desktop defaults, models setup modes/requests, and keeps real platform setup/preflight/metrics as external boundaries.
- Added `pycodex.core.spawn` and `pycodex.core.landlock` for the pure request-construction slices of Rust `spawn.rs`, `core/src/landlock.rs`, and `sandboxing/src/landlock.rs`: models spawn requests/stdio policy/sandbox env flags, constructs Linux sandbox helper args from permission profiles, preserves the helper argv0 rule, and leaves real process spawning/sandbox execution as runtime boundaries.
- Added `pycodex.core.otel_init` for the pure configuration-mapping slice of Rust `otel_init.rs`: models OTEL exporter kinds, HTTP protocol, TLS settings, provider settings, analytics-gated metrics exporter selection, runtime metrics feature detection, codex export filtering, and no-op telemetry install/process-start boundaries without initializing an OTEL SDK.
- Added `pycodex.core.mcp` for the thin manager boundary in Rust `mcp.rs`: converts config objects into MCP config through `to_mcp_config`, delegates configured/effective server and tool-plugin provenance collection through injectable callables, and provides mapping-only stdlib fallbacks without implementing the full MCP runtime.
- Added `pycodex.core.state_db_bridge` for Rust `state_db_bridge.rs`: preserves the async state DB initialization bridge and `StateDbHandle` boundary through injectable sync/async rollout initializers without inventing a database implementation.
- Added `pycodex.core.session_startup_prewarm` for the task-resolution boundary of Rust `session_startup_prewarm.rs`: models prewarm handles/resolutions, ready/failed/timed-out/cancelled transitions, startup telemetry records, cancellable resolution, and injected prewarm scheduling without implementing prompt/tool/websocket warmup internals.
- Added `pycodex.core.prompt_debug` for Rust `prompt_debug.rs`: preserves the debug prompt-input construction flow with ephemeral config marking, injectable session/thread factory, context update recording, user-input conversation item recording, prompt-history extraction, injectable tool building, prompt construction, and thread shutdown/removal boundaries.
- Added `pycodex.core.skills` for the facade/helper layer in Rust `skills.rs`: re-exports the existing Python skill metadata/rendering/injection/invocation helpers, builds `SkillsLoadInput` from config, and mirrors implicit skill invocation telemetry/analytics emission with duplicate suppression and injectable session boundaries.
- Added `pycodex.core.thread_manager` boundary port for Rust `thread_manager.rs`: test-mode flag, `NewThread`, `ForkSnapshot`, `ThreadShutdownReport`, injectable startup, in-memory thread registry, created-thread subscribers, metadata updates, and shutdown categorization.
- Added `pycodex.core.codex_delegate` boundary port for Rust `codex_delegate.rs`: injectable delegated Codex startup, child event forwarding, approval/input/permission interception, cancellation-aware fallbacks, MCP approval answer selection, and parent-session notification helpers. Also removed a stale `SkillRenderSideEffects` import from the skills facade.
- Added `pycodex.core.exec` boundary helpers for Rust `exec.rs`: exec constants, capture policy, expiration/cancellation handling, exec params, Windows filesystem override shape, capped append, stdout/stderr aggregation, sandbox-denial heuristics, and timeout/denied/signal finalization.
- Added `pycodex.core.client` state-layer port for Rust `client.rs`: client/header constants, session-scoped `ModelClient`, turn-scoped `ModelClientSession`, websocket cache/fallback state, prompt cache keys, window generation, subagent/parent-thread headers, turn-state headers, websocket metadata stamping, and incremental request delta selection.
- Added `pycodex.core.codex_thread` wrapper port for Rust `codex_thread.rs`: `ThreadConfigSnapshot`, `CodexThreadSettingsOverrides`, settings update derivation, Codex/runtime delegation methods, rollout/config/history/MCP forwarding hooks, response-item injection boundaries, running-state accessors, and out-of-band elicitation pause-count behavior.
- Added `pycodex.core.agent_resolver` for Rust `agent/agent_resolver.rs`: registers the current session root, accepts direct `ThreadId` targets, delegates named references through `agent_control.resolve_agent_reference`, and maps resolution failures to a tool-facing model response error.
- Added `pycodex.core.function_tool` for Rust `function_tool.rs` / `codex_tools::FunctionCallError`: shared `RespondToModel` and `Fatal` variants with Rust-compatible display behavior, now reused by `agent_resolver`.
- Unified `pycodex.core.tool_router` on the shared `pycodex.core.function_tool.FunctionCallError` re-export, preserving the previous Python type/variant validation while matching Rust's single `function_tool.rs` error boundary.
- Extended `pycodex.core.stream_events_utils` toward Rust `stream_events_utils.rs`: added `OutputItemResult` and the `FunctionCallError::RespondToModel` conversion path that produces an empty-call-id `function_call_output` response item and marks the turn as needing follow-up, while fatal tool errors continue upward.
- Extended `pycodex.core.stream_events_utils` with the non-tool finalize boundary from Rust `stream_events_utils.rs`: `FinalizedTurnItem`, `FinalizedTurnItemFacts`, assistant hidden-markup stripping through `parse_turn_item`, last-agent-message extraction, commentary mailbox behavior, and image-generation deferral facts.
- Extended `pycodex.core.stream_events_utils` with a Python `handle_output_item_done` bridge mirroring Rust's routing order: tool calls accept mailbox delivery, record the completed item, and queue an injected runtime future; non-tool items emit started/completed turn items and return finalized facts; model-visible `FunctionCallError` values record an empty-call-id tool output follow-up.
- Extended `pycodex.core.tool_parallel` toward Rust `tools/parallel.rs`: added the public `ToolCallRuntime.handle_tool_call` wrapper that dispatches through the router, converts successful tool outputs into `ResponseInputItem`, maps model-visible function-call errors into failure responses, and escalates fatal tool errors.
- Tightened `pycodex.core.tool_parallel` result boundaries so `ToolCallResult.post_tool_use_payload` now accepts only the Rust `PostToolUsePayload` equivalent or `None`.
- Added `pycodex.core.tool_events` for the pure data/event-shaping slice of Rust `tools/events.rs`: tool event context/stage/failure variants, exec begin/end event builders, exec result status mapping, apply-patch file-change begin/end items, turn-diff tracker update policy, and shell/apply_patch/unified_exec emitter facades with runtime delivery left injectable.
- Added `pycodex.core.tool_orchestrator` for the pure decision layer of Rust `tools/orchestrator.rs`: approval-step classification, initial sandbox override planning, review-decision rejection mapping, stable sandbox-denial retry reasons, no-sandbox retry gating, guardian/hook retry approval flags, and a combined run-plan boundary while leaving async approval prompts, sandbox manager execution, and network approval lifecycle injectable.
- Added `pycodex.core.tool_runtimes` for the shared pure helpers in Rust `tools/runtimes/mod.rs`: sandbox command construction, managed-proxy env cleanup on explicit escalation, elevated Windows PowerShell `-NoProfile` rewriting, shell snapshot `-lc` wrapping, shell block joining, shell variable validation, and POSIX single-quote escaping without implementing real process execution.
- Tightened `pycodex.core.tool_runtimes` error boundaries by wrapping Rust-style `ToolError` results in `ToolRuntimeError`, preserving the original tool error while using Python exception semantics for helper failures.
- Extended `pycodex.core.tool_runtimes` toward Rust `tools/runtimes/apply_patch.rs`, `shell.rs`, and `unified_exec.rs`: request/output and approval-key structs, apply-patch permission payloads and no-sandbox approval policy, shell/unified-exec permission payloads, immediate vs deferred network approval specs, flat tool-name boundaries, and explicit-escalation network suppression.
- Extended `pycodex.core.tool_runtimes` with the pure zsh-fork/unix-escalation helpers from Rust `tools/runtimes/shell/unix_escalation.rs`: approval sandbox-permission downgrading, execve prompt rejection reasons for global/granular approval policies, wrapped shell-script extraction, intercepted argv normalization, and `ExecResult` to `ExecToolCallOutput` mapping with timeout/denial surfaced through `ToolRuntimeError`.
- Tightened apply-patch runtime parity in `pycodex.core.tool_runtimes`: no-sandbox approval now respects granular sandbox approval flags, permission hook payloads use the canonical `apply_patch` hook name plus `Write`/`Edit` aliases, sandbox cwd is exposed from the patch action, and active sandbox attempts can produce a filesystem sandbox context with effective additional permissions.
- Tightened unified-exec runtime parity in `pycodex.core.tool_runtimes`: added trusted sandbox-cwd extraction, default shell-tool exec options with network-denial cancellation composition, and Rust-shaped empty command mapping to the model-facing `missing command line for PTY` rejection.
- Tightened `pycodex.core.tool_registry` runtime hook parity: core runtimes now expose default pre/post hook payload methods and exposure overrides delegate handler-specific hook payload overrides, matching Rust `CoreToolRuntime` and `ExposureOverride`.
- Tightened `pycodex.core.tool_router` hook/error parity: client tool-search parse failures now surface as model-visible `FunctionCallError`s, and dispatch uses handler-specific pre/post hook payload methods instead of bypassing runtime overrides.
- Tightened `pycodex.core.tool_router` runtime hook type boundaries so handler-specific pre/post hook payload overrides must return the Rust trait-equivalent payload structs or `None`.
- Tightened `pycodex.core.tool_router` `ToolCall.function_arguments()` parity so function payloads return their exact argument string and malformed/mismatched payloads remain fatal, matching `codex_tools::ToolCall`.
- Tightened `pycodex.protocol.models.ResponseInputItem` toward Rust `ResponseInputItem`: message content/tool-search tools now preserve required empty arrays, output variants require string call IDs and payloads, phases and optional names keep Rust shapes, and structured function/custom outputs reuse the canonical function-output payload wire encoding.
- Tightened direct `pycodex.protocol.models.LocalShellAction` construction so only the Rust `exec` tagged variant with a `LocalShellExecAction` payload is accepted, matching the `from_mapping` wire boundary.
- Tightened direct `pycodex.protocol.models.WebSearchAction` construction so each Rust tagged variant accepts only its own optional fields, preserves string-list `queries`, and rejects unknown or mixed action shapes outside the serde `other` parse path.
- Tightened direct `pycodex.protocol.models` reasoning tagged variants so `ReasoningItemReasoningSummary` only accepts `summary_text` with string text and `ReasoningItemContent` only accepts Rust's `reasoning_text`/`text` variants with string payloads.
- Tightened `pycodex.protocol.user_input.UserInput` direct variant construction and serialization toward Rust `UserInput`: each tagged variant now rejects fields from other variants, required strings are emitted without empty-string fallbacks, and text inputs preserve required empty `text_elements`.
- Tightened `ResponseInputItem.from_user_inputs` toward Rust `From<Vec<UserInput>>`: remote images now emit direct `input_image` items without XML tags, mixed remote/local image numbering uses a shared counter, skill/mention inputs are skipped for later injection, malformed item containers are rejected, and local images use standard-library data URLs or Rust-shaped placeholder text.
- Aligned the Python local-image conversion order with Rust by reading the file before MIME/type classification, so missing files consistently surface the Rust-shaped read-error placeholder even when their extension is unsupported.
- Tightened local-image invalid-byte handling without third-party libraries: Python now checks common image magic headers before emitting data URLs, so bad `.png`/`.jpg`-style inputs surface a Rust-shaped invalid-image placeholder instead of being treated as successful attachments.
- Tightened `pycodex.core.client.ModelClient.build_responses_request` request construction parity: reasoning is built once for both request and include selection, and verbosity now follows Rust's state override then `model_info.default_verbosity` fallback when the model supports verbosity.
- Aligned Python Responses API text controls with Rust `create_text_param_for_request`: absent verbosity/schema now yields no text controls, output schemas are wrapped as named `json_schema` formats with strict/schema fields, and malformed `output_schema_strict` values are rejected.
- Added `serialize_responses_request` to mirror Rust `ResponsesApiRequest` serde skip rules for outbound JSON: empty instructions and `None` service tier, prompt cache key, text controls, and client metadata are omitted while non-skipped fields such as `reasoning: None` remain explicit.
- Wired WebSocket request preparation through `serialize_responses_request`, so both full and incremental Python WebSocket payloads use the Rust-shaped outbound request view before adding delta-specific fields.
- Added a matching HTTP request preparation boundary that returns the same Rust-shaped serialized Responses request view, keeping the future HTTP transport path aligned with WebSocket payload preparation.
- Confirmed and locked `pycodex.core.client_common.Prompt.get_formatted_input` parity with Rust `Prompt::get_formatted_input`: the method remains a shallow clone of prompt input without hidden insertion/filtering, with a focused regression test documenting the contract.
- Aligned Python Responses API tool serialization with Rust `create_tools_json_for_responses_api`: request construction now converts `ToolSpec`-like objects through `to_mapping()` while preserving plain mapping tools, so outbound `tools` contain JSON objects instead of Python dataclass instances.
- Added Rust-compatible `response_create_client_metadata` handling to `pycodex.core.client`: existing Responses API client metadata is copied, W3C `traceparent`/`tracestate` values are inserted under the websocket request metadata keys with trace values taking precedence, empty metadata collapses to `None`, and non-string metadata/trace values are rejected.
- Aligned Python WebSocket request wire shape with Rust `ResponsesWsRequest`: added `response_create_ws_request` and `response_processed_ws_request` tagged-enum helpers, wrapped full and incremental prepared WebSocket payloads with `type: response.create`, preserved incremental `previous_response_id`/delta input behavior, and made stream-start timestamp stamping ignore `response.processed` requests.
- Extended `pycodex.core.compact_remote` with the Rust `trim_function_call_history_to_fit_context_window` pure boundary: Python can now identify Codex-generated remote-compact tail items, remove trailing developer/tool-output history while estimated tokens exceed the context window, remove matching call counterparts for deleted outputs, and report the Rust-style deleted item count without requiring a full async `ContextManager`.
- Extended `pycodex.core.compact_remote_v2` with the Rust remote-compaction-v2 sampling prompt boundary: Python now appends a `compaction_trigger` item to cloned prompt input, preserves tools/parallel-tool/base-instruction/personality settings in a `Prompt`, and can build the Rust-shaped trace-attempt payload containing model, instructions, input, and `parallel_tool_calls`.
- Extended `pycodex.core.compact_remote_v2` with the Rust `collect_compaction_output` stream reduction boundary: Python now scans output-item-done events until response completion, accepts unrelated extra output items, requires exactly one compaction output, returns the completed response id, and raises Rust-shaped stream/output errors for missing completion or incorrect compaction counts.
- Added the remote-compaction-v2 `response.processed` feature gate boundary: Python now mirrors Rust's `ResponsesWebsocketResponseProcessed` decision by returning a tagged `response.processed` request only when the feature is enabled, otherwise preserving the no-op path.
- Added a pure remote-compaction-v2 install-plan boundary: Python now packages the Rust install artifacts for compacted history replacement, including `new_history`, optional reference-context item for mid-turn injection, an empty-message `CompactedItem` with `replacement_history`, and the compaction checkpoint payload containing input and replacement history mappings.
- Added a remote-compaction-v2 success-plan composition helper that mirrors Rust's post-stream success path by turning `(prompt_input, compaction_output)` into retained compacted history, applying compacted-history post-processing and initial-context injection, then producing the install plan/checkpoint payload in one stdlib-only step.
- Added remote-compaction-v2 retry policy helpers: Python now mirrors Rust's `provider.stream_max_retries().min(MAX_REMOTE_COMPACTION_V2_STREAM_RETRIES)` cap and delegates retry/fallback decisions through the shared Responses retry helper using the `RemoteCompactionV2` request kind.
- Added a remote-compaction-v2 request outcome planner mirroring Rust's `run_remote_compaction_request_v2` result match: successful compaction results return a success outcome, non-retryable `CodexErr` values fail immediately, and retryable errors delegate to the capped remote-compaction-v2 retry/fallback decision.
- Added the ordinary sampling-turn `response.processed` decision boundary: Python now mirrors Rust `session/turn.rs` by producing a `response.processed` WebSocket request only when `ResponsesWebsocketResponseProcessed` is enabled, the turn outcome succeeded, and a completed response id is present.
- Added an ordinary sampling-turn tail-action planner mirroring Rust `session/turn.rs`: token count emission is planned before cancellation handling, cancellation produces a turn-aborted action and suppresses turn diff emission, and turn diff emission only occurs for non-cancelled turns with a captured unified diff.
- Added `get_last_assistant_message_from_turn` parity for ordinary turn result extraction: Python now scans response items from newest to oldest and reuses `last_assistant_message_from_item` with `plan_mode=False`, matching Rust's final assistant-message lookup semantics.
- Exposed `get_last_assistant_message_from_turn` through the `pycodex.core` aggregation boundary alongside the existing stream-event helpers, keeping the Python public helper surface aligned for ordinary sampling turn result extraction.
- Exposed the expanded remote-compaction-v2 helper surface through `pycodex.core`: prompt construction, stream output collection, processed notification decisions, retry policy/outcome planning, success/install planning, and v2 error/plan types now share the same public aggregation boundary as the earlier retained-history helpers.
- Exposed the expanded Responses client helper surface through `pycodex.core`: text/tool request serialization, response-create/response-processed WebSocket shapes, client metadata trace merging, sampling `response.processed` decisions, tail-action planning, and outbound request serialization now use the same public aggregation boundary as the rest of the model client helpers.
- Added a completed response-item recording planner for stream events: Python now mirrors the Rust `record_completed_response_item_with_finalized_facts` decision boundary by combining finalized facts, mailbox deferral fallback, memory-citation carry-through, and external-context memory-pollution detection before the async session side effects run.
- Extended completed response-item recording side effects: Python now applies the Rust-aligned recording plan after conversation persistence by deferring mailbox delivery, marking memory mode polluted when external context is present, and recording memory citation usage for the current turn through session-compatible hooks.
- Added automatic memory-citation detection for completed assistant response items: Python now parses Rust-shaped `<oai-mem-citation>` markup into `MemoryCitation`, uses it when finalized facts are absent, records stage1 output usage through session state-db hooks, and marks the current turn as having a memory citation.
- Added the Rust turn-item contributor lifecycle boundary for completed non-tool response items: Python can now parse a response item into a `TurnItem`, run session/extension contributors before hidden-markup normalization, ignore failed contributors like Rust's warning-only path, and route `handle_output_item_done` through the async contributor-aware finalization path.
- Aligned completed image-generation response handling with Rust stream events: contributor-aware non-tool finalization now saves generated image bytes under the Codex home artifact path, attaches the saved path to the `ImageGenerationItem`, and records the Rust-shaped `ImageGenerationInstructions` contextual developer message for future turns.
- Added a Rust-aligned tool-call lifecycle plan for `handle_output_item_done`: Python now captures tool name, payload log preview, thread id, mailbox/current-item recording intent, emits the plan through an optional session hook, and passes a child cancellation token to the tool runtime.
- Added a Rust-aligned tool-call error handling plan for `handle_output_item_done`: model-visible `RespondToModel` errors now record the original completed item, append the generated function-call output response item, and request a follow-up, while fatal tool-router errors raise immediately without adding model-visible recovery output.
- Added an explicit unexpected tool-output branch for stream events: Python now recognizes completed function/custom/tool-search output items that arrive from the stream, records a Rust-aligned no-turn-item/no-follow-up plan through an optional hook, and still persists the completed response item.
- Added a sampling output aggregation state mirroring Rust `session/turn.rs`: Python can now fold each `OutputItemResult` by appending tool futures to the in-flight queue, replacing the last agent message when present, and OR-ing `needs_follow_up`.
- Added the ordinary sampling mailbox-preemption decision boundary: Python now mirrors Rust's commentary-assistant/reasoning item filter and returns the early follow-up plan with the current last agent message when pending mailbox input should preempt the sampling request.
- Added the ordinary sampling `OutputItemAdded` planning boundary: Python now mirrors Rust's custom-tool argument diff consumer setup, function-call diff reset, skip-contributor non-tool parsing, and provisional turn-item emit/defer decision for streamed items.
- Extended the ordinary sampling `OutputItemAdded` plan with assistant text seeding: Python now captures seeded item ids and visible text from raw assistant output, initializes non-plan provisional messages with the visible text, and initializes plan-mode provisional messages with empty content plus a seeded parsed payload.
- Added the ordinary sampling `OutputTextDelta` planning boundary: Python now maps streamed assistant deltas through the hidden-markup stripping path for active agent messages, preserves raw content deltas for other streamed turn items, and skips deltas when no active item is streaming to the client.
- Added the ordinary sampling `ToolCallInputDelta` planning boundary: Python now mirrors Rust's active call-id filtering, inherits the active call id when the stream omits one, invokes the active argument diff consumer, and returns the produced event for sending.
- Added the ordinary sampling reasoning-delta planning boundary: Python now mirrors Rust's `ReasoningSummaryDelta`, `ReasoningSummaryPartAdded`, and `ReasoningContentDelta` event planning, including active-item streaming gates and typed indices.
- Added the ordinary sampling assistant-text flush planning boundary: Python now mirrors Rust's active agent-message parser flush point by finishing the assistant stream parser only for streamed agent messages and returning the parsed tail for runtime event emission.
- Added the ordinary sampling `OutputItemDone` transition planning boundary: Python now mirrors Rust's pre-handle state reset by finishing the active tool diff consumer, preserving the previously streamed item only when it was client-streamed, clearing active streaming state, and planning assistant text parser flushes for streamed agent messages.
- Added the ordinary sampling metadata-event planning boundary: Python now mirrors Rust's `ServerModel`, `ModelVerifications`, `ServerReasoningIncluded`, `RateLimits`, and `ModelsEtag` side-effect decisions, including one-shot emission gates and deferred token-count emission for rate limits.
- Added the ordinary sampling `Completed` event planning boundary: Python now mirrors Rust's final response branch by requiring assistant-text flush-all, token-usage recording, token-count and turn-diff emission flags, completed response id capture, and `end_turn=false` follow-up forcing.
- Added the plan-mode assistant item-done planning boundary: Python now mirrors Rust's `handle_assistant_item_done_in_plan_mode` decision to intercept completed assistant messages, complete proposed plan text, finalize/record the response item, update last-agent-message only when present, and drop whitespace-only agent messages.
- Added the plan-mode proposed-plan segment planning boundary: Python now mirrors Rust's `handle_plan_segments` split between buffered leading whitespace, deferred agent-message starts, visible assistant deltas, plan-item start, and plan delta emission while preserving completed-plan no-op behavior.
- Added the plan-mode proposed-plan completion planning boundary: Python now mirrors Rust's `maybe_complete_plan_item_from_message` by extracting finalized `<proposed_plan>` text from assistant messages, stripping memory citations from the plan body, starting the plan item if needed, and completing it unless it was already completed.
- Added the plan-mode deferred agent-message planning boundary: Python now mirrors Rust's pending-agent start and `emit_agent_message_in_plan_mode` behavior, including one-shot pending starts, fallback empty start items, whitespace-only message drops, completed-message emission, and started/pending set cleanup.
- Added the ordinary sampling in-flight tool-drain planning boundary: Python now mirrors Rust's `drain_in_flight` result handling by converting successful `ResponseInputItem` values into response items, planning conversation recording, marking external-context memory pollution when configured, and surfacing failed tool futures through the error-or-panic path.
- Added the ordinary sampling post-drain tail planning boundary: Python now makes Rust's final ordering explicit by sending token counts before cancellation, returning turn-aborted before reading turn diffs, and only emitting a turn diff for non-cancelled turns with a captured unified diff.
- Added the turn event realtime-text extraction boundary: Python now mirrors Rust's `agent_message_text` and `realtime_text_for_event` behavior by concatenating complete agent-message text and exposing realtime text only for full `AgentMessage`/completed-agent-message events while ignoring deltas, plan events, reasoning events, and other status/tool events.
- Added the assistant-text flush-all planning boundary: Python now mirrors Rust's `flush_assistant_text_segments_all` loop by draining all finished assistant stream parsers and packaging each `(item_id, parsed)` tail as a flush plan for runtime emission.
- Added the streamed assistant parsed-text planning boundary: Python now mirrors Rust's `emit_streamed_assistant_text_delta` split by ignoring empty parsed chunks, retaining citations locally, routing plan-mode segments through the plan-segment planner, and emitting visible assistant text only outside plan mode.
- Added the plan-mode turn-item emission planning boundary: Python now mirrors Rust's `emit_turn_item_in_plan_mode` match by delegating `AgentMessage` items to the plan-mode agent-message path while emitting started/completed decisions for non-agent turn items based on whether an item was already active.
- Extended the plan-mode assistant item-done planning boundary: Python now carries the Rust `maybe_complete_plan_item_from_message` result and the nested `emit_turn_item_in_plan_mode` plan directly in `SamplingPlanModeAssistantDonePlan`, making the assistant-done handler a closer structural match to Rust's composition.
- Added the ordinary sampling stream-event dispatch planning boundary: Python now mirrors the top-level Rust `ResponseEvent` branch table for created, output item added/done, text/tool/reasoning deltas, metadata, and completed events by routing each event type to the existing focused planning helper.
- Added the ordinary sampling output-item-added apply planning boundary: Python now mirrors Rust's post-add state application by deciding whether to emit a started item immediately, store a plan-mode pending agent message, route seeded assistant parsed text through the streamed-text planner, and update active streaming state.
- Added the ordinary sampling output-text-delta apply planning boundary: Python now mirrors Rust's `OutputTextDelta` post-parse split by routing agent-message parsed deltas through streamed assistant text planning and non-agent streamed items through raw content delta emission.
- Added the ordinary sampling tool-call-input-delta apply planning boundary: Python now mirrors Rust's final `ToolCallInputDelta` send step by turning a matched diff-consumer result into an explicit event-to-emit plan while preserving the skip path when no event is produced.
- Added the ordinary sampling reasoning-delta apply planning boundary: Python now mirrors Rust's reasoning summary delta, reasoning section break, and raw reasoning content delta send steps by converting each `SamplingReasoningDeltaPlan` into an explicit event-to-emit shape.
- Added the ordinary sampling completed-event apply planning boundary: Python now mirrors Rust's `Completed` branch side effects by planning assistant-text flush-all, token-usage recording, token-count and turn-diff emission, completed response id capture, and the final sampling request result.
- Added the ordinary sampling metadata-event apply planning boundary: Python now mirrors Rust's `ServerModel`, `ModelVerifications`, `ServerReasoningIncluded`, `RateLimits`, and `ModelsEtag` side-effect targets by converting metadata plans into explicit runtime action fields.
- Added the ordinary sampling output-item-done apply planning boundary: Python now mirrors Rust's `OutputItemDone` composition by combining transition cleanup, assistant-text flush routing, plan-mode assistant interception, output-result aggregation, and mailbox preemption planning.
- Added the ordinary sampling single-event apply planning boundary: Python now connects `SamplingStreamEventDispatchPlan` to the branch-specific apply planners for created, output item added/done, text/tool/reasoning deltas, metadata, and completed events, forming a higher-level Rust `match event` processing skeleton.
- Added the ordinary sampling loop-tail planning boundary: Python now mirrors Rust's post-stream ordering by combining optional websocket `response.processed`, mandatory in-flight drain, and post-drain token-count/cancellation/turn-diff planning into `SamplingLoopTailPlan`.
- Added the ordinary sampling request aggregate planning boundary: Python now collects event apply plans, loop-tail cleanup, outcome status, completed response id, final follow-up state, and turn-aborted derivation into `SamplingRequestPlan`, giving the Rust sampling request skeleton a higher-level request-shaped container.
- Added the ordinary sampling request state-machine planning boundary: Python now folds event apply plans into request-level outcome state, completed response id, token-count and turn-diff flags, mailbox follow-up state, loop-tail cleanup, and turn-aborted derivation through `sampling_request_state_machine_plan`.
- Added the ordinary sampling request runtime-contract planning boundary: Python now expands `SamplingRequestPlan` into ordered runtime steps and required hook names for applying event plans, sending websocket response processed, draining in-flight futures, sending token counts and turn diffs, and returning either a sampling result or turn-aborted outcome.

- Added the ordinary sampling request runtime executor adapter boundary: Python now maps SamplingRequestRuntimePlan steps onto hook methods, records each step result, and captures final sampling result versus turn-aborted return without binding to real websocket/session IO.

- Added the sampling request runtime hook adapter boundary: runtime steps can now map onto websocket/session callbacks for response.processed, drain, token count, turn diff, normal sampling result, turn aborted, and unknown tail actions while preserving Rust-style no-op behavior when optional IO is absent.

- Added structured apply-event-plan summarization for the sampling runtime hook adapter: Python now recognizes SamplingStreamEventApplyPlan child branches and surfaces completed, metadata, and output-done effects when no real event applier callback is installed.

- Added a sampling runtime event application state and completed/metadata apply support: the hook adapter can now persist completed response ids, final sampling result hints, token usage flags, token count/turn diff flags, rate limits, server reasoning, and models etag metadata instead of only summarizing apply plans.

- Added output-item-done support to the sampling runtime event application state: Python now preserves continue-loop, mailbox-preemption, output-result, state-after-output-result, and mailbox-preemption result flow from SamplingOutputItemDoneApplyPlan.

- Added output-item-added and output-text-delta support to the sampling runtime event application state: Python now preserves active item streaming state, tool argument diff consumer state, seeded/streamed assistant text deltas, and raw content deltas from the corresponding apply plans.

- Added tool-call-input-delta and reasoning-delta support to the sampling runtime event application state: Python now records tool argument deltas, reasoning delta events, and emitted stream events from their apply plans.

- Connected sampling runtime event application state to the final sampling result path: return_sampling_result can now derive needs_follow_up and last_agent_message from executed runtime state instead of only using static runtime-plan step values.

- Added runtime-state-derived sampling loop tail planning: Python can now derive response.processed, token count, turn diff, drain, and cancellation tail behavior from SamplingRuntimeEventApplicationState while reusing the existing tail-plan rules.
- Added runtime-state-derived runtime tail planning: Python can now convert `SamplingRuntimeEventApplicationState` into executable tail steps for `response.processed`, drain, token count, turn diff, turn aborted, and final sampling result hooks.
- Added state-derived runtime tail execution: Python can now build and execute the tail runtime plan directly from `SamplingRuntimeEventApplicationState`, moving the sampling loop closer to the Rust flow where applied event state drives post-stream actions.
- Added state-driven sampling runtime execution: Python can now apply event plans into `SamplingRuntimeEventApplicationState` and then execute the tail runtime plan derived from that same state, moving closer to Rust's event-state-tail loop structure.
- Tightened state-driven runtime execution state binding: adapter hooks without an event state now bind to the provided `SamplingRuntimeEventApplicationState`, and adapters already bound to another state are rejected so event application and tail execution cannot silently diverge.
- Added state-driven runtime phase tracing: combined sampling runtime execution now reports separate event-apply and tail phase summaries while preserving the existing step-level execution result shape for non-composed plans.
- Documented and covered aborted state-driven runtime phase tracing: cancellation now has an explicit Python test intent for the Rust-like order of event apply, drain, token count, and turn-aborted return with tail phase abort metadata.
- Enriched state-driven runtime phase tracing: event-apply and tail phase summaries now include step type sequences and a compact sampling state summary so the Python trace explains how applied events drive tail decisions.
- Expanded phase state summaries across stream surfaces: state-driven runtime traces now include loop/preemption flags and counts for metadata, output item, text delta, tool input delta, reasoning delta, and emitted stream events without embedding heavyweight event objects.
- Added per-event state summaries to state-driven runtime traces: event apply now executes and records each event plan separately, preserving combined step results while exposing how each stream event advances the lightweight sampling state summary.
- Covered output item and text-delta events in per-event runtime traces: state-driven execution now has explicit test intent for output item added, output text delta, and output item done summaries as assistant output state advances.
- Added metadata-state summaries to state-driven runtime traces: phase summaries now expose token-usage presence, server reasoning inclusion, rate-limit presence, and model etag refresh state, with per-event coverage for completed and metadata events.
- Added follow-up/mailbox state summaries to state-driven runtime traces: phase summaries now expose whether output done produced output result, state-after-output, mailbox preemption, follow-up, and final assistant tail message decisions.
- Connected state-driven sampling runtime to the session boundary: `ModelClientSession` can now build websocket-session-bound runtime hook adapters, and a session-level state-driven execution helper can use the session connection for response.processed and drain behavior.
- Persisted completed state-driven session responses: successful session-level sampling runtime execution now records `LastResponse` from the applied runtime state so later websocket requests can reuse the existing incremental response lifecycle.
- Conservatively connected session `LastResponse.items_added`: state-driven session execution now records response items only when the runtime state already carries concrete `ResponseItem` objects, avoiding unsafe conversion from `TurnItem` runtime state.
- Connected state-driven session execution to `last_request`: session-level runtime execution now accepts an optional request mapping and caches it alongside `LastResponse` after successful completion, allowing the existing incremental item baseline logic to operate.
- Added a prepare+execute session lifecycle helper: state-driven session execution can now first prepare a websocket request using the existing incremental request machinery, then execute the runtime plan and refresh session last request/response state.
- Added websocket outcome/fallback metadata to the prepare+execute lifecycle helper: lifecycle results now record stream vs fallback outcomes and include a serialized HTTP request when the modeled outcome is `FALLBACK_TO_HTTP`.
- Wired modeled HTTP fallback into client state: prepare+execute lifecycle fallback now calls `ModelClient.force_http_fallback()`, records whether fallback was activated, and disables future websocket use just like the existing client fallback path.
- Validated syntax after verification was allowed: `pytest` is not installed in the current Python environment, so standard-library `compileall` was used instead; fixed a syntax error in `tests/test_core_tool_router.py`, and full `compileall pycodex tests` now succeeds.
- Connected fallback telemetry through the prepare+execute lifecycle helper: modeled websocket-to-HTTP fallback now forwards session telemetry and model info into `ModelClient.force_http_fallback(...)`, preserving the existing fallback counter path at the session lifecycle boundary.
- Exposed runtime state summaries at the session lifecycle boundary: prepare+execute results now include the final compact sampling state summary, so callers can observe completed response ids, applied event types, follow-up state, metadata state, and stream-event counts without digging through phase traces.
- Aligned untraced warmup response markers in session execution: state-driven session completion can now mark the completed `LastResponse` as coming from an untraced warmup request, and prepare+execute lifecycle results expose that marker alongside the previous-response warmup source flag.
- Exposed websocket connection reuse at the session lifecycle boundary: prepare+execute results now capture the session's `connection_reused` flag for the modeled websocket request, matching the Rust path where this value is passed into websocket streaming and request telemetry.
- Added websocket connection lifecycle state transitions: Python can now model Rust's new-vs-reused websocket connection branch by resetting incremental websocket state on new connections and preserving it while marking `connection_reused=true` for existing connections.
- Connected websocket connection lifecycle transitions to prepare+execute: the modeled session request path can now apply new-vs-reused connection state before preparing the websocket request, resetting incremental baselines for new connections and preserving `previous_response_id` deltas for reused connections.
- Stamped websocket request start metadata in prepare+execute: modeled websocket requests now receive `x-codex-ws-stream-request-start-ms` after request preparation and before runtime execution, matching Rust's pre-stream `stamp_ws_stream_request_start_ms(...)` ordering.
- Modeled inference trace started-request selection: prepare+execute lifecycle results now choose the compressed websocket request for normal sends and the full logical request when `previous_response_id` came from an untraced warmup, matching Rust rollout trace replay semantics.
- Recorded websocket last_request before runtime execution: prepare+execute now stores the logical request and warmup marker immediately after trace-start selection, matching Rust's pre-`stream_request(...)` session update and preserving the attempted request even when runtime returns turn-aborted.
- Modeled websocket stream request attempt inputs: prepare+execute lifecycle results now expose the request object and connection reuse flag that would be passed into Rust's `stream_request(ws_request, connection_reused)` call, plus whether a websocket connection is present.
- Modeled websocket stream attempt availability outcomes: prepare+execute now reports a ready stream attempt when a connection exists and a Rust-like blocked outcome with `websocket connection is unavailable` when no connection is present.
- Modeled websocket last-response receiver registration: ready stream attempts now set a pending last-response marker on the Python websocket session, mirroring Rust's `last_response_rx = Some(...)`, and the marker is cleared when the next websocket request consumes the last response.
- Modeled websocket stream request failures: prepare+execute can now represent a ready stream attempt whose `stream_request(...)` fails, record a Rust-like inference trace failure summary, and avoid registering the pending last-response marker.
- Modeled websocket stream success mapping: prepare+execute lifecycle results now distinguish blocked/failed attempts from successful Rust-like `map_response_stream(...)` output, including whether the stream was mapped and a last-response receiver was registered.
- Modeled websocket completed-response delivery through the pending receiver: successful mapped stream lifecycles now expose the `LastResponse` payload that would be delivered through Rust's `last_response_rx`, including response id, added items, and pending receiver state.
- Aligned websocket completed item accumulation with Rust `map_response_events`: output-item-done plans can now carry the completed `ResponseItem`, session `LastResponse.items_added` prefers those completed items, and lifecycle delivery exposes the same completed-item payload.
- Modeled websocket stream closure before `response.completed`: mapped streams can now report Rust's `stream closed before response.completed` failure, clear the pending last-response receiver, preserve accumulated completed items in the failed trace, and avoid delivering a `LastResponse`.
- Modeled websocket consumer-dropped cancellation: mapped streams can now represent Rust's `response stream dropped before provider terminal event` cancellation path separately from failures, preserving accumulated completed items and clearing the pending last-response receiver without delivering `LastResponse`.
- Modeled mapped websocket stream API errors: after a stream is mapped, Python can now represent an upstream event error as a Rust-like failed trace with accumulated completed items, clear the pending last-response receiver, and avoid delivering `LastResponse`.
- Connected websocket completed token usage telemetry: successful mapped streams now translate completed-event token usage into a Rust-like `session_telemetry.sse_event_completed(...)` call and expose the recorded token counters in the lifecycle result.
- Connected mapped websocket stream failure telemetry: upstream event errors now call a Rust-like `session_telemetry.see_event_completed_failed(...)` side effect and expose the failed telemetry summary separately from failed trace data.
- Modeled websocket feedback tags: mapped stream lifecycles can now expose Rust-like `last_model_request_id` and successful completed `last_model_response_id` tags for request/response correlation.
- Aligned mapped stream error request id propagation: upstream event errors can now use a Rust-like debug-context request id for failed trace `request_id` and `last_model_request_id` feedback tags when no upstream request id is available.
- Modeled websocket inference trace completion: successful mapped streams now expose a Rust-like `record_completed` summary with response id, upstream request id, token usage, and completed output items alongside telemetry and last-response delivery.
- Propagated upstream request ids into non-completed stream traces: consumer-dropped cancellations and stream-closed-before-completed failures now carry the upstream request id in trace summaries and feedback tags, matching Rust's `record_cancelled`/`record_failed` inputs.
- Prevented `stream_request(...)` failures from caching completed websocket state: modeled request-send failures now clear any runtime-written `LastResponse`, keeping the session from recording a completed response when Rust would never enter mapped stream consumption.
- Stopped applying stream events after `stream_request(...)` failure: modeled request-send failures now execute the runtime with no stream event plans, so runtime summaries no longer show a false completed response when Rust would not consume mapped events.
- Stopped applying stream events for blocked websocket attempts: connection-unavailable attempts now skip runtime stream events and avoid caching `LastResponse`, matching Rust's inability to consume websocket events without a usable connection.
- Preserved HTTP fallback response consumption while isolating websocket state: fallback-to-HTTP lifecycles now still apply response event plans through the HTTP-modeled runtime path, but clear websocket `LastResponse`/pending receiver state so fallback completions do not become websocket incremental baselines.
- Exposed websocket `response.processed` tail effects at the prepare+execute lifecycle boundary: lifecycle results now include the generated `response.processed` request and the adapter send result, making Rust's post-processing websocket acknowledgement observable from session-level tests.
- Made websocket `response.processed` sending best-effort: Python now catches sender failures and returns a failed send summary instead of raising, matching Rust's debug-and-continue behavior when the acknowledgement cannot be sent.
- Reset the active websocket session on HTTP fallback: prepare+execute fallback now clears the current session connection, request/response baselines, warmup marker, pending receiver, and reuse flag, matching Rust's `try_switch_fallback_transport(...)` replacement with a default `WebsocketSession`.
- Modeled websocket connect-timeout reset semantics: new-connection lifecycles now clear stale connections when no replacement is available, clear pending last-response state, and prepare+execute can record a connect timeout that resets the active websocket session before the stream attempt is treated as blocked.
- Added Rust-like websocket `needs_new` inference: sessions can now decide whether a websocket connection needs replacement from missing connections or `is_closed` state, and prepare+execute applies that lifecycle automatically when the caller does not provide an explicit decision.
- Added a session-level websocket preconnect model: Python can now represent Rust's best-effort preconnect path that only installs a connection when websockets are enabled and no connection is already present, without sending prompt payloads or marking the connection as reused.
- Added a session-level websocket prewarm model: Python now skips warmup when websockets are disabled or a last request already exists, otherwise delegates to the state-driven websocket execution path with `warmup=True` so completed warmup responses are marked as untraced baselines.
- Made websocket prewarm completion reasons explicit: prewarm summaries now distinguish completed warmups from fallback-to-HTTP and streams that do not reach a completed response, matching Rust's wait-for-`ResponseEvent::Completed` success condition.
- Separated websocket prewarm stream errors from missing completion: prewarm summaries now report failed and cancelled stream terminal states distinctly, aligning with Rust's `Err(err) => return Err(err)` warmup behavior instead of treating errors as ordinary missing-completed streams.
- Covered websocket prewarm stream cancellation explicitly: tests now assert consumer-dropped warmup streams report `stream_cancelled` and carry the Rust-like cancellation trace instead of being grouped with missing completions.
- Enforced `generate=false` for websocket prewarm requests: the Python prewarm entrypoint now stamps both payload and logical request with `generate=False`, matching Rust's `ws_payload.generate = Some(false)` instead of relying on callers to remember the warmup flag.
- Added websocket-specific payload metadata construction: `ModelClient.build_websocket_payload(...)` now mirrors Rust's websocket request path by replacing HTTP request metadata with websocket client metadata and W3C trace context before `response.create` serialization.
- Wired websocket-specific payload metadata into prewarm: `prewarm_websocket(...)` now builds its warmup payload through `build_websocket_payload(...)`, preserving Rust's websocket metadata/trace behavior while keeping the logical cached request separate.
- Wired websocket-specific payload metadata into normal prepare+execute: ordinary websocket lifecycle execution can now accept trace and turn metadata, build websocket-specific payload metadata before incremental compression, and keep the logical cached request separate from transport metadata.
- Made websocket payload metadata the default prepare+execute path: normal and prewarm websocket lifecycles now route through a single metadata construction point, so installation/window metadata are present even when no trace or turn metadata is supplied.
- Guarded websocket metadata against breaking incremental compression: tests now prove trace/turn transport metadata still preserves `previous_response_id` deltas because logical request comparison remains separate from websocket payload metadata.
- Recorded ignored model verbosity diagnostics: when a configured model verbosity is omitted because the target model does not support verbosity, Python now keeps the outgoing request shape unchanged while exposing a Rust-like ignored-verbosity diagnostic for callers/tests.
- Guarded request diagnostics against cross-request leakage: tests now prove ignored verbosity diagnostics are cleared before the next request build, so diagnostics describe only the most recent request construction.
- Pinned reasoning/include request linkage: tests now prove `reasoning.encrypted_content` is included exactly when Rust would build a reasoning payload, and omitted when reasoning summaries are unsupported.
- Pinned reasoning defaults and None-summary behavior: tests now prove Python request construction uses the model default reasoning effort when no explicit effort is supplied and maps a None summary to Rust's omitted reasoning summary semantics.
- Restored app/plugin rendering imports: `app_plugin_rendering` now imports `AppInfo` from the Python tool-discovery protocol model, unblocking `pycodex.core` package import during request-construction validation.
- Restored multi-agent spec module initialization: integer validation helpers now exist before dataclass default instances call them, matching Rust's eager static tool-spec availability without breaking Python package import.
- Restored skills facade imports: `skills.py` now re-exports explicit skill mention collection from the Python skill-mentions module while keeping injection loading separate, matching Rust's facade split.
- Restored available-skills facade import: `skills.py` now re-exports `build_available_skills` from the skill rendering module while keeping mention counting in the mention parser module.
- Verified core package import and compile stability: `pycodex.core`, top-level `pycodex`, key core facade exports, and all `pycodex/core` modules now pass lightweight import/compile probes after the recent facade and initialization fixes.
- Improved common CLI help surfaces: `python -m pycodex exec --help`, `review --help`, and `features --help` now expose option/subcommand guidance instead of a placeholder usage line, making the Python entrypoint closer to Rust/Clap discoverability while staying stdlib-only.
- Fixed local `apply` help dispatch: the Python CLI now handles `codex apply --help` and missing task ids locally instead of treating `--help` as a Cloud task id or failing before the dispatcher can show help.
- Improved resume/fork CLI help surfaces: `python -m pycodex resume --help` and `fork --help` now describe session id, prompt, image, `--last`, and `--all` behavior instead of returning placeholder usage lines.
- Improved nested exec help surfaces: `python -m pycodex exec resume --help` and `exec review --help` now dispatch to subcommand-specific help instead of always returning the top-level exec help text.
- Improved MCP/plugin CLI help surfaces: `python -m pycodex mcp --help` and `plugin --help` now expose subcommands and common options, with nested help for MCP add and plugin marketplace flows instead of placeholder usage lines.
- Verified read-only MCP/plugin management commands: `mcp list`, `mcp list --json`, `mcp get <name>`, `mcp get <name> --json`, `plugin list`, and `plugin list --marketplace default` now provide a working baseline for later state-read/write parity work.
- Fixed TOML scalar serialization for config writes: the stdlib TOML writer now quotes strings, lowercases booleans, serializes arrays/inline tables, and escapes control characters so `mcp add` writes a config that `tomllib` can read back.
- Verified plugin marketplace JSON-state write loop: using a temporary `CODEX_HOME`, `plugin marketplace add/list/upgrade/remove` works when the literal marketplace source key is used; local path display/name normalization remains a follow-up parity point.
- Verified ordinary plugin JSON-state write loop: using a temporary `CODEX_HOME`, `plugin add/list/remove` works for both `plugin@marketplace` selectors and explicit `--marketplace` selectors, including marketplace-filtered listing.
- Verified MCP command-mode write loop: using a temporary `CODEX_HOME`, `mcp add <name> --env KEY=VALUE -- command args...`, `mcp get --json`, `mcp remove`, and `mcp list --json` now round-trip command, args arrays, and env inline-table values through the stdlib TOML writer.
- Verified MCP login/logout local state loop: using a temporary `CODEX_HOME`, `mcp login <name> --scopes ...` writes `mcp-state.json` login metadata and `mcp logout <name>` clears it without removing the configured server.
- Verified feature-flag config write loop: using a temporary `CODEX_HOME`, `features list`, `features enable web_search`, and `features disable web_search` round-trip through `config.toml`, proving boolean TOML serialization remains readable after the scalar writer fix.
- Verified root feature-toggle override semantics: `--enable web_search` and `--disable web_search` affect `features list` without writing `config.toml`, and matching Rust's fold order, disables are appended after enables so a repeated enable+disable conflict resolves to disabled.
- Verified root `-c` plus feature-toggle precedence: explicit `-c features.<key>=...` values are followed by folded `--enable/--disable` overrides, so the later toggle wins for the same concrete feature key; legacy alias interactions such as `web_search` versus `web_search_request` remain a follow-up parity point.

## 2026-05-29 21:15 - feature legacy alias precedence baseline
- Verified root feature override parity for legacy alias interactions: when the same concrete key is toggled, later toggle overrides earlier values; when legacy `web_search` and concrete `web_search_request` coexist, both Rust `BTreeMap` ordering and Python sorted-map application process `web_search` before `web_search_request`, so the concrete key wins regardless of original CLI order.
- No production edit was needed for this point; Python behavior matches the Rust legacy alias materialization model.

## 2026-05-29 21:17 - plugin marketplace local manifest-name alignment
- Aligned Python `plugin marketplace add <local-dir>` with Rust's local marketplace naming behavior: the Python CLI now reads `.agents/plugins/marketplace.json` and uses its non-empty `name` field as the configured marketplace key instead of using the raw source path.
- Added a basename fallback for local directories without a manifest and for non-local marketplace sources, including stripping a trailing `.git` suffix for git-like sources.
- Improved Windows robustness by reading marketplace manifests with `utf-8-sig`, so BOM-prefixed JSON written by PowerShell is accepted.
- Validated `pycodex/cli/parser.py` compilation and a temp `CODEX_HOME` local marketplace add/list/remove loop where manifest name `debug` is listed and removed by name.

## 2026-05-29 21:19 - plugin marketplace config.toml storage alignment
- Moved Python `plugin marketplace add/list/upgrade/remove` behavior closer to Rust by storing configured marketplaces in `CODEX_HOME/config.toml` under `[marketplaces.<name>]` instead of the Python-only `plugin-state.json` marketplace map.
- Added marketplace config helpers that read/write the same core fields Rust records: `last_updated`, `source_type`, `source`, optional `ref`, and optional `sparse_paths`.
- Local directory sources now write `source_type = "local"` and a resolved absolute `source`; git-like sources write `source_type = "git"` and preserve `ref`/`sparse_paths`.
- `plugin marketplace list`, targeted `upgrade`, and `remove` now operate on the TOML marketplace table. Removing the last marketplace removes the `marketplaces` table.
- Validated parser compilation plus local TOML add/list/remove and git-like add/list/upgrade/remove loops with temp `CODEX_HOME`.

## 2026-05-29 21:21 - plugin installed config.toml alignment
- Moved Python `plugin add/list/remove` installed-plugin state toward Rust's `CODEX_HOME/config.toml` `[plugins."<plugin>@<marketplace>"]` representation instead of the Python-only `plugin-state.json` plugins map.
- `plugin add` now requires a configured marketplace name in TOML, writes `enabled = true` under the plugin key, and emits Rust-style marketplace-aware output.
- `plugin remove` now clears the TOML plugin entry while leaving marketplace configuration intact, matching Rust's ability to remove a plugin after its marketplace source is removed.
- `plugin list` now reads configured plugin keys from TOML and still supports `--marketplace` filtering.
- Validated parser compilation, configured marketplace + plugin add/list/remove TOML loop, unconfigured marketplace rejection, and Rust-style add/remove output.
- Remaining gap: Python still does not copy/install actual plugin cache roots from marketplace manifests; this turn aligned the user config persistence layer first.

## 2026-05-29 21:24 - local plugin cache installation alignment
- Added a first Python implementation of Rust-like local marketplace plugin installation: `plugin add <plugin>@<marketplace>` now reads the configured local marketplace source, parses `.agents/plugins/marketplace.json`, resolves local plugin source paths, reads `.codex-plugin/plugin.json`, and copies the plugin root into `CODEX_HOME/plugins/cache/<marketplace>/<plugin>/<version>`.
- Kept user TOML aligned with Rust: `[plugins."<plugin>@<marketplace>"]` records `enabled = true` only; plugin version is inferred from cache/manifest and is not persisted into user config.
- `plugin add` now prints `Installed plugin root: ...` after successful local install, matching Rust CLI shape.
- `plugin remove` now clears the plugin TOML entry and removes the installed cache root for that plugin while preserving marketplace config.
- Validated parser compilation, local manifest-driven cache installation, TOML `enabled = true`, plugin remove cache cleanup, and the Rust-covered boundary that removing a marketplace leaves cache present but prevents re-adding from that unconfigured marketplace.
- Remaining gaps: git marketplace plugin installation, full marketplace plugin listing table/status/version rendering, and stricter manifest/schema validation.

## 2026-05-29 21:25 - plugin list marketplace table alignment
- Reworked Python `plugin list` from printing configured plugin keys to rendering Rust-style marketplace sections for configured local marketplaces.
- `plugin list` now reads marketplace manifests, prints `Marketplace `<name>``, the marketplace manifest path, and `PLUGIN / STATUS / VERSION / PATH` columns.
- Local marketplace plugins now show `not installed` before plugin install, and `installed, enabled` plus the installed version after `plugin add` creates the cache root.
- `plugin list --marketplace <name>` now filters by marketplace and prints `No plugins found in marketplace `<name>`.` when no configured marketplace matches.
- Validated parser compilation, not-installed table output, installed table output with version `1.2.3`, and empty marketplace filter output.
- Remaining gaps: git marketplace/plugin source list rendering, explicit disabled plugin state commands, richer manifest schema validation, and exact Rust spacing/format edge cases.

## 2026-05-29 21:30 - plugin marketplace list table alignment
- Aligned Python `plugin marketplace list` output with Rust's table shape: it now prints `MARKETPLACE  ROOT` followed by marketplace names padded to the `MARKETPLACE` column width and the configured root/source path.
- Local marketplace rows now validate the configured source by reading `.agents/plugins/marketplace.json` before printing, so missing or malformed local marketplace snapshots fail instead of showing stale config-only names.
- The failure path now validates all rows before printing the table header, avoiding partial stdout on load failure.
- Validated parser compilation, normal local marketplace list output, and missing-manifest failure after a marketplace source is removed.

## 2026-05-29 21:33 - plugin and marketplace segment validation alignment
- Added Python-side plugin/marketplace segment validation matching Rust `validate_plugin_segment`: segments must be non-empty and contain only ASCII letters, digits, `_`, and `-`.
- Applied validation to command-line plugin selectors, marketplace names derived from local manifests/source fallbacks, marketplace list rows, plugin lookup, and plugin list rendering.
- Invalid manifest marketplace names such as `bad/name` are now rejected on `plugin marketplace add` instead of being accepted into config/cache paths.
- Invalid plugin selectors such as `../../etc@debug` are now rejected with a Rust-like error mentioning the offending plugin key.
- Validated parser compilation, a legal `debug-market` / `sample_plugin` install/list flow, invalid marketplace manifest-name rejection, and invalid plugin selector rejection.
- Remaining gap: direct hand-edited config entries with invalid marketplace keys should be covered by a cleaner regression check later; the runtime validation path is implemented, but the ad hoc PowerShell config mutation validation was not completed cleanly.

## 2026-05-29 21:36 - plugin store manifest validation alignment
- Added Python local plugin install validation matching Rust `PluginStore::install`: `.codex-plugin/plugin.json` `name` must be a valid plugin segment and must match the marketplace plugin name being installed.
- Added plugin version segment validation matching Rust rules: version must be non-empty, cannot be `.` or `..`, and may only contain ASCII letters, digits, `.`, `+`, `_`, and `-`.
- Local plugin install now rejects mismatched manifest names and path-traversal versions before copying into `CODEX_HOME/plugins/cache/...`.
- Validated parser compilation, a successful matching-name install, rejection of `plugin.json name `different-name` does not match marketplace plugin name `sample``, and rejection of version `..` as path traversal.

## 2026-05-29 21:38 - plugin default version alignment
- Aligned Python local plugin install default version with Rust `DEFAULT_PLUGIN_VERSION`: missing `version` in `.codex-plugin/plugin.json` now installs under cache version `local` instead of the previous Python-only `0.0.0`.
- Matched Rust's version parsing errors: non-string `version` now fails with `invalid plugin version in plugin.json: expected string`, and blank string versions fail with `invalid plugin version in plugin.json: must not be blank`.
- Kept existing Rust-style version segment validation for `.`, `..`, and illegal characters before copying plugin files into cache.
- Validated parser compilation, missing-version install to `plugins/cache/<marketplace>/<plugin>/local`, non-string version rejection, and blank version rejection.

## 2026-05-29 21:41 - plugin cache active version and cleanup alignment
- Added Python helpers mirroring Rust plugin cache version behavior: `local` is active whenever present; otherwise the active version is the highest semver-like version, falling back to lexical comparison when needed.
- `plugin list` now uses the active plugin version rule instead of naive lexicographic directory sorting.
- Local plugin install now removes old valid version directories after copying the new version, matching Rust's cache replacement behavior for ordinary upgrades.
- Added an error path matching Rust when an old version that would remain active cannot be removed.
- Validated parser compilation, `1.0.0 -> 2.0.0` upgrade removes the old `1.0.0` cache and lists `2.0.0`, and `local` remains active even when a higher numeric version directory exists.

## 2026-05-29 22:03 - project priority AGENTS.md
- Added root `AGENTS.md` as project-level agent guidance.
- Clarified that the mission remains a Python port of Rust Codex, but current priority is the common/core Codex experience: `exec`, core agent loop, model request/response handling, context assembly, file/shell/patch tools, safety/approval behavior, and app-server protocol/event model only where needed by CLI/core runtime.
- Explicitly deprioritized MCP, plugin marketplace/runtime, marketplace backend, multi-agent, cloud tasks, telemetry/update checks, and app-server daemon/remote/proxy/schema-generation until the core agent loop is useful and stable.
- Established compatibility guidance for extension areas: keep lightweight shims and avoid regressions, but do not continue deep implementation unless explicitly requested or required by core runtime.

## 2026-05-29 22:07 - exec bootstrap AGENTS.md context alignment
- Shifted implementation focus back to the core `exec` path per root `AGENTS.md` guidance.
- Extended `pycodex.exec.config_plan.ExecConfigBootstrapPlan` to carry resolved `user_instructions`, `instruction_sources`, and `startup_warnings` so the future in-process agent loop can receive AGENTS.md/project-doc context without reworking the bootstrap boundary.
- `build_exec_config_bootstrap_plan` now resolves AGENTS.md instructions using the existing `pycodex.core.agents_md` port, including root/global `codex_home` support, configured `user_instructions`, `project_doc_max_bytes`, fallback filenames, project root markers, and `child_agents_md` flags from supplied config TOML data.
- Validated compilation and confirmed the current root `AGENTS.md` appears in both `userInstructions` and `instructionSources` in the exec bootstrap mapping.

## 2026-05-29 22:10 - exec session user instructions alignment

- Continued the core/common Codex path after the AGENTS.md priority pivot.
- Extended `ExecSessionConfig` so resolved project/user instructions from `AGENTS.md` do not stop at bootstrap planning.
- Added `user_instructions`, `instruction_sources`, and `startup_warnings` to the session config mapping used by exec loop summaries.
- Added instruction config propagation into `thread/start` and `thread/resume` request params when instruction data exists.
- Wired `_build_exec_session_config` to copy the resolved instruction fields from `ExecConfigBootstrapPlan`.
- Added a narrow regression test proving thread start/resume params and session config mappings carry resolved instructions.
- Validation: `python -m compileall -q pycodex\exec\session.py pycodex\cli\parser.py`; `python -m unittest tests.test_exec_session.ExecSessionRequestBuilderTests.test_thread_params_carry_resolved_user_instructions`.

## 2026-05-29 22:15 - model-visible user instructions alignment

- Continued the core/common path after carrying AGENTS.md instructions into exec session config.
- Inspected the Python model request construction boundary and Rust session prompt assembly points.
- Added prompt-debug model-visible input injection for `turn_context.user_instructions` using the already ported `UserInstructions` contextual fragment renderer.
- The injected AGENTS.md/user instruction message is inserted before the current user input, matching the Rust intent that project instructions are contextual user content rather than base/system instructions.
- Fixed a core protocol bug in `ResponseInputItem.__post_init__`: message `phase` parsing used reversed helper arguments and could break normal `UserInput.text_input()` conversion.
- Validation: `python -m compileall -q pycodex\core\prompt_debug.py pycodex\protocol\models.py`; `python -m unittest tests.test_core_prompt_debug.PromptDebugTests.test_build_prompt_input_from_session_injects_user_instructions_before_user_input tests.test_core_prompt_debug.PromptDebugTests.test_build_prompt_input_from_session_records_user_input_and_formats_prompt`.

## 2026-05-29 22:18 - core turn prompt assembly extraction

- Continued moving AGENTS.md/user instruction handling from debug-only behavior toward reusable core session/turn prompt assembly.
- Added `pycodex.core.turn_prompt` with `build_turn_prompt`, `input_with_user_instructions`, and `render_turn_user_instructions`.
- The new module centralizes the Rust-style ordering: contextual AGENTS.md/user instructions are model-visible user content and appear before the current user input.
- Updated `prompt_debug` to reuse the shared assembly helper on the default path while still giving custom prompt builders an already-injected input list.
- Added focused tests for rendering, insertion order, and tool/base-instruction propagation.
- Validation: `python -m compileall -q pycodex\core\turn_prompt.py pycodex\core\prompt_debug.py`; `python -m unittest tests.test_core_turn_prompt tests.test_core_prompt_debug.PromptDebugTests.test_build_prompt_input_from_session_injects_user_instructions_before_user_input tests.test_core_prompt_debug.PromptDebugTests.test_build_prompt_input_from_session_records_user_input_and_formats_prompt`.

## 2026-05-29 22:19 - turn Responses request assembly

- Continued the core session/turn/model request path after extracting reusable prompt assembly.
- Added `pycodex.core.turn_request` as a thin bridge from turn prompt assembly to `ModelClient.build_responses_request()`.
- Added `TurnResponsesRequestPlan` to return both the assembled `Prompt` and the Responses API request payload.
- The helper preserves the Rust-style sequence: visible history and contextual AGENTS.md/user instructions become a `Prompt`, then provider/model settings turn that prompt into a request.
- Added focused tests proving user instructions remain before the current user input in the final request input, while base instructions, tools, model slug, and service tier are carried through.
- Validation: `python -m compileall -q pycodex\core\turn_request.py pycodex\core\turn_prompt.py`; `python -m unittest tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:21 - user turn runtime request skeleton

- Continued the core session/turn/model-request path after adding `turn_request`.
- Added `pycodex.core.turn_runtime` as a session-like user-turn runtime skeleton.
- The new helper advances a session-like object through: `new_default_turn`, context update recording, user input recording, history cloning, tool lookup, base instruction lookup, prompt assembly, and Responses request construction.
- It performs no network I/O and does not fake model output; it stops at the same transport-independent boundary needed before sampling.
- Added focused tests proving the skeleton records the user input, preserves existing developer context, inserts AGENTS.md/user instructions before the current user input, and carries tools/base instructions/service tier/model into the request.
- Validation: `python -m compileall -q pycodex\core\turn_runtime.py pycodex\core\turn_request.py pycodex\core\turn_prompt.py`; `python -m unittest tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:23 - user turn sampling runtime boundary

- Continued the core user-turn runtime after building request construction from session-like state.
- Extended `pycodex.core.turn_runtime` with an injectable sampling boundary.
- Added `UserTurnSamplingRequest` and `UserTurnSamplingResult`.
- Added `run_user_turn_sampling_from_session()`, which builds the request plan, calls a caller-provided sampler, normalizes returned response items, and records them back into session history.
- The implementation still performs no network I/O and does not fake model output; it creates the seam where real HTTP/WebSocket sampling can later be connected.
- Added focused tests proving the sampler receives session/turn/request context and that assistant response items are recorded into session history.
- Validation: `python -m compileall -q pycodex\core\turn_runtime.py pycodex\core\turn_request.py pycodex\core\turn_prompt.py`; `python -m unittest tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:24 - ModelClientSession sampler adapter

- Continued from the injected sampling seam toward a real model-client preparation boundary.
- Added `pycodex.core.turn_sampler` with a `ModelClientSession`-based HTTP preparation adapter.
- Added `PreparedSamplingRequest` and `PreparedSamplingResult` to separate prepared payloads from transport execution and normalized response items.
- `sample_with_model_client_session()` now uses `ModelClientSession.prepare_http_request()` before handing the payload to an injected transport.
- This keeps turn runtime free of network details while aligning the seam with the existing Rust-like model client session boundary.
- Added a focused integration-style unit test that runs user-turn sampling through the new adapter, verifies prepared request fields, returns assistant output from the injected transport, and records it into session history.
- Validation: `python -m compileall -q pycodex\core\turn_sampler.py pycodex\core\turn_runtime.py pycodex\core\turn_request.py pycodex\core\turn_prompt.py`; `python -m unittest tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:26 - stdlib HTTP transport for prepared sampling

- Continued from the ModelClientSession sampler adapter toward a real transport boundary.
- Added `pycodex.core.http_transport` using only the Python standard library (`urllib.request`, `json`).
- Added `HttpTransportConfig`, `send_prepared_http_sampling_request()`, and `response_items_from_responses_payload()`.
- The transport accepts a `PreparedSamplingRequest`, posts the prepared JSON payload, parses a Responses API-like payload, and returns `PreparedSamplingResult` with normalized `ResponseItem` values.
- Tests use an injected fake opener and do not perform network I/O.
- Validation: `python -m compileall -q pycodex\core\http_transport.py pycodex\core\turn_sampler.py pycodex\core\turn_runtime.py`; `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:28 - combined ModelClient HTTP sampler

- Continued from the stdlib HTTP transport toward an end-to-end reusable user-turn sampler.
- Added `model_client_http_sampler()` in `pycodex.core.http_transport`.
- The helper combines `ModelClientSession.prepare_http_request()` with `send_prepared_http_sampling_request()` and returns a sampler callable suitable for `run_user_turn_sampling_from_session()`.
- Fixed HTTP transport request serialization so `ResponseItem` and other `to_mapping()` values are recursively converted to JSON-compatible mappings before `json.dumps()`.
- Added an integration-style unit test covering user input through turn runtime, ModelClientSession preparation, stdlib HTTP transport with fake opener, response item normalization, and history recording.
- Validation: `python -m compileall -q pycodex\core\http_transport.py pycodex\core\turn_sampler.py pycodex\core\turn_runtime.py`; `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:29 - HTTP provider/auth config assembly

- Continued from the combined ModelClient HTTP sampler toward real provider/auth wiring.
- Added `http_transport_config_from_provider()` in `pycodex.core.http_transport`.
- The helper resolves a Responses endpoint from provider `responses_endpoint`, `responses_url`, `endpoint`, or `base_url + /responses`.
- It combines `ModelClient` headers (`x-codex-window-id`, beta features, turn metadata, timing metrics) with auth headers.
- Auth header handling supports bearer token strings, mappings with `headers`, `api_key`, or `bearer_token`, objects with `to_auth_headers()` or `add_auth_headers()`, and simple token attributes.
- Added focused tests proving endpoint construction, Authorization header, beta feature header, turn metadata, window id, and timing metrics header are assembled.
- Validation: `python -m compileall -q pycodex\core\http_transport.py pycodex\core\turn_sampler.py pycodex\core\turn_runtime.py`; `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:31 - user-turn HTTP sampling entrypoint

- Continued from provider/auth HTTP config assembly toward a directly usable core HTTP user-turn path.
- Added `run_user_turn_http_sampling_from_session()` in `pycodex.core.http_transport`.
- The helper creates `HttpTransportConfig` from provider/auth/client state, creates a `ModelClientSession` HTTP sampler, and delegates to `run_user_turn_sampling_from_session()`.
- This gives callers a single core entrypoint for: session-like user input, model request preparation, stdlib HTTP POST, Responses output parsing, and session history recording.
- Added focused tests using a fake opener to prove endpoint resolution, Authorization header, Codex window header, request body model, response parsing, and history recording work through the full helper.
- Validation: `python -m compileall -q pycodex\core\http_transport.py pycodex\core\turn_sampler.py pycodex\core\turn_runtime.py`; `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:33 - in-memory core session runtime

- Continued from the high-level HTTP user-turn entrypoint toward a real reusable Python session-like object.
- Added `pycodex.core.session_runtime` with `InMemoryCodexSession`, `InMemoryTurnContext`, and `InMemoryHistory`.
- The in-memory session implements the methods required by the core user-turn runtime: `new_default_turn`, `record_context_updates_and_set_reference_context_item`, `record_conversation_items`, `clone_history`, and `get_base_instructions`.
- It stores cwd, model info, user instructions, base instructions, conversation history, recorded batches, and context-update count.
- Added an end-to-end-style unit test that runs `InMemoryCodexSession` through `run_user_turn_http_sampling_from_session()` using a fake opener.
- The test proves developer context, AGENTS.md/user instructions, current user input, base instructions, HTTP request body, assistant response parsing, and history recording all work together.
- Validation: `python -m compileall -q pycodex\core\session_runtime.py pycodex\core\http_transport.py pycodex\core\turn_runtime.py`; `python -m unittest tests.test_core_session_runtime tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

## 2026-05-29 22:35 - exec local runtime bridge

- Continued from the in-memory session runtime toward `codex exec` integration.
- Added `pycodex.exec.local_runtime` with `run_exec_user_turn_http_sampling()`.
- The bridge accepts `ExecSessionConfig`, `ExecRunPlan`, `ModelClient`, provider, and model info, then runs user-turn operations through the in-memory core HTTP sampling path.
- Review operations are explicitly rejected for now because this bridge targets the common/core user-turn path first.
- Extended core prompt/request/runtime helpers to carry `output_schema` into `Prompt` and then into the Responses request `text.format` payload.
- Added focused tests proving exec config user instructions, model base instructions, user input, HTTP response, and output schema all flow through the local runtime bridge.
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py pycodex\core\turn_prompt.py pycodex\core\turn_request.py pycodex\core\turn_runtime.py pycodex\core\http_transport.py`; `python -m unittest tests.test_exec_local_runtime tests.test_core_session_runtime tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_prompt`.

### Turn 204 - exec local HTTP runtime 瀵归綈

- 鏂板 pycodex/exec/local_runtime.py锛屾妸 ExecSessionConfig + ExecRunPlan 鎺ュ埌 in-memory session 鍜?HTTP Responses sampling 閾捐矾銆?
- output schema 宸蹭粠 exec operation 閫忎紶鍒?Prompt / Responses request / HTTP runtime锛岃鐩?codex exec --output-schema 杩欎竴绫绘牳蹇冨父鐢ㄨ兘鍔涖€?
- 瀵归潪 user_turn operation 鏆傛椂鏄惧紡鎷掔粷锛岄伩鍏嶄吉瀹炵幇 review/resume 绛夋湭瀹屾垚鑳藉姏銆?
- 鏂板 	ests/test_exec_local_runtime.py锛岀敤 fake opener 楠岃瘉 base instructions銆乽ser instructions銆乽ser input銆乷utput schema銆乤ssistant response 鐨勫畬鏁撮摼璺€?
- 绐勯獙璇侀€氳繃锛歝ompileall 浠ュ強 14 涓浉鍏?unittest 鍧?OK銆?

### Turn 205 - CLI exec local HTTP 鍏ュ彛瀵归綈

- 鏂板鏄惧紡寮€鍏?PYCODEX_EXEC_LOCAL_HTTP=1锛岃 fresh codex exec user turn 鍙互涓嶄緷璧?app-server锛岀洿鎺ヨ蛋 Python 鏈湴 HTTP Responses sampling銆?
- 鎵╁睍 pycodex/exec/local_runtime.py锛屽姞鍏ラ粯璁?OpenAI provider/model/auth 瑙ｆ瀽銆佹渶缁堟枃鏈彁鍙栧拰榛樿鏈湴 HTTP runtime銆?
- 鎵╁睍 pycodex/cli/parser.py锛屽湪闈炰氦浜?exec 涓帴鍏ユ湰鍦?HTTP runtime锛屽苟淇 event processor 鐨?last_message_path 鍙傛暟鍚嶃€?
- 鎵╁睍 	ests/test_exec_local_runtime.py锛岄獙璇?env provider/model/API key銆佺己灏?API key 鎶ラ敊銆乤ssistant 鏂囨湰鎻愬彇銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK銆?

### Turn 206 - local HTTP exec events 瀵归綈

- 鏂板 emit_local_http_exec_result(...)锛岃鏈湴 HTTP codex exec 缁撴灉閫氳繃鐜版湁 HumanEventProcessor / JsonEventProcessor 杈撳嚭銆?
- Human 妯″紡澶嶇敤 final output 鍐崇瓥锛汮SON 妯″紡杈撳嚭 	urn.started銆乮tem.completed(agent_message)銆?urn.completed銆?
- CLI 鏈湴 HTTP exec 鍒嗘敮涓嶅啀鐩存帴鎵撳嵃 final text锛岃€屾槸璧?exec processor 妗ユ帴銆?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 human stdout 鍜?JSONL event 褰㈢姸銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK銆?

### Turn 207 - local HTTP exec error events 瀵归綈

- 鏂板 emit_local_http_exec_error(...)锛岃鏈湴 HTTP codex exec 澶辫触璺緞澶嶇敤 exec event processor銆?
- JSON 妯″紡杈撳嚭 	urn.started 鍜?	urn.failed锛沨uman 妯″紡杈撳嚭 ERROR: ...銆?
- CLI 鏈湴 HTTP 鍒嗘敮鎹曡幏 ValueError / OSError / RuntimeError 鏃舵敼璧伴敊璇簨浠舵ˉ鎺ワ紝鍚屾椂淇濈暀杩斿洖鐮佽涔夈€?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 human/json 閿欒杈撳嚭銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK銆?

### Turn 208 - local HTTP exec usage 瀵归綈

- 鏂板 usage_from_local_http_exec_result(...)锛屼粠鏈湴 HTTP sampling 鐨?raw Responses payload 涓彁鍙?token usage銆?
- JSON 妯″紡涓?	urn.completed 鐜板湪鎼哄甫 usage锛沨uman 妯″紡涓嬪鐢?	okens used 杈撳嚭閫昏緫銆?
- 鏀寔澶氬眰 
aw_result 瑙ｅ寘锛岄€傞厤褰撳墠 HTTP sampling adapter 鐨勫祵濂楃粨鏋滅粨鏋勩€?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 usage 瀛楁鏄犲皠銆丣SONL usage銆乭uman blended total 杈撳嚭銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK锛? 涓祴璇曢€氳繃銆?

### Turn 209 - local HTTP exec reasoning events 瀵归綈

- 鏂板 
easoning_texts_from_local_http_exec_result(...)锛屼粠鏈湴 HTTP Responses payload 涓彁鍙?reasoning 鎽樿銆?
- JSON 妯″紡涓嬫垚鍔熻矾寰勭幇鍦ㄤ細杈撳嚭 item.completed(reasoning)锛屽啀杈撳嚭 item.completed(agent_message) 鍜?	urn.completed銆?
- 鍏煎 reasoning payload 鐨?	ext銆乧ontent銆乻ummary 浠ュ強 summary 鍒楄〃缁撴瀯銆?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 reasoning 鏂囨湰鎻愬彇鍜?JSONL 浜嬩欢椤哄簭銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK锛? 涓祴璇曢€氳繃銆?

### Turn 210 - local HTTP exec config summary 瀵归綈

- 鏂板 default_local_http_exec_model(...) 鍜?local_http_exec_config_summary(...)銆?
- 鏈湴 HTTP codex exec 鍒嗘敮鍦ㄨ姹傚墠澶嶇敤鐜版湁 processor 杈撳嚭 config summary銆?
- Human 妯″紡杈撳嚭 Codex 鏍囧噯澶撮儴锛汮SON 妯″紡杈撳嚭 	hread.started銆?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 model/env/provider/cwd/session id summary 鍜?human summary 鏂囨湰銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK锛? 涓祴璇曢€氳繃銆?

### Turn 211 - local HTTP exec runtime ids 瀵归綈

- local_http_exec_config_summary(...) 鏀寔鐙珛 session_id / 	hread_id銆?
- CLI 鏈湴 HTTP exec 鍒嗘敮鍏堟瀯閫?runtime锛岀敤鍚屼竴涓?ModelClient 鐨勭湡瀹?session/thread UUID 杈撳嚭 summary 骞舵墽琛岃姹傘€?
- 閬垮厤 summary 浣跨敤 local-http 鍗犱綅 id锛屽悓鏃堕伩鍏嶈姹傛椂閲嶆柊鐢熸垚鍙︿竴濂?runtime id銆?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 request metadata銆亀indow id銆乮nstallation id銆乻ummary id銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK锛? 涓祴璇曢€氳繃銆?

### Turn 212 - local HTTP exec tool call events 瀵归綈

- 鏂板 	ool_call_items_from_local_http_exec_result(...)锛屾妸 Responses unction_call / custom_tool_call / mcp_tool_call 鍙鏄犲皠涓?exec mcp_tool_call item銆?
- JSON 妯″紡鎴愬姛璺緞鐜板湪鍙互灞曠ず妯″瀷璇锋眰鐨勫伐鍏疯皟鐢紝浣嗕笉浼氭墽琛屽伐鍏枫€?
- 鏀寔 JSON 瀛楃涓?arguments 瑙ｆ瀽涓哄璞°€?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 function_call payload銆乼ool arguments銆丣SONL 浜嬩欢椤哄簭銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK锛? 涓祴璇曢€氳繃銆?

### Turn 213 - local HTTP exec tool output events 瀵归綈

- 鏂板 	ool_output_items_from_local_http_exec_result(...)锛屾妸 Responses unction_call_output / custom_tool_call_output / mcp_tool_call_output 鍙鏄犲皠涓?completed exec mcp_tool_call item銆?
- JSON 妯″紡鎴愬姛璺緞鐜板湪鍙互灞曠ず宸ュ叿璋冪敤缁撴灉锛屼絾涓嶄細鎵ц宸ュ叿鎴栬繘鍏ヤ笅涓€杞ā鍨嬪惊鐜€?
- 鎵╁睍 runtime 娴嬭瘯瑕嗙洊 function_call_output payload銆乺esult/status銆丣SONL 浜嬩欢椤哄簭銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK锛? 涓祴璇曢€氳繃銆?

### Turn 214 - CLI local HTTP exec test 瀵归綈

- 鏂板 CLI 灞傛祴璇曪紝璇佹槑 PYCODEX_EXEC_LOCAL_HTTP=1 鏃?codex exec 浼氳繘鍏ユ湰鍦?HTTP 鍒嗘敮銆?
- 娴嬭瘯浣跨敤 fake async sampler锛屼笉瑙﹀彂鐪熷疄缃戠粶銆?
- 楠岃瘉 human 妯″紡浼氳緭鍑?config summary銆乸rovider銆佸畬鎴愭彁绀哄拰鏈€缁?assistant message銆?
- 绐勯獙璇侀€氳繃锛氭柊澧?CLI 娴嬭瘯鍔?	ests.test_exec_local_runtime 鍏?10 涓祴璇?OK銆?

### Turn 215 - CLI local HTTP exec JSON test 瀵归綈

- 鏂板 CLI JSON 妯″紡娴嬭瘯锛岃瘉鏄?PYCODEX_EXEC_LOCAL_HTTP=1 鏃?codex exec --json 浼氳繘鍏ユ湰鍦?HTTP 鍒嗘敮銆?
- 娴嬭瘯浣跨敤 fake async sampler锛屼笉瑙﹀彂鐪熷疄缃戠粶銆?
- 楠岃瘉 stdout JSONL 杈撳嚭 	hread.started銆?urn.started銆乮tem.completed(agent_message)銆?urn.completed(usage)銆?
- 绐勯獙璇侀€氳繃锛氫袱涓?CLI 鏈湴 HTTP 娴嬭瘯鍔?	ests.test_exec_local_runtime 鍏?11 涓祴璇?OK銆?

### Turn 216 - CLI local HTTP exec error tests 瀵归綈

- 鏂板 CLI human/json 閿欒鍒嗘敮娴嬭瘯锛岃鐩?PYCODEX_EXEC_LOCAL_HTTP=1 浣嗙己灏?API key 鐨勬儏鍐点€?
- Human 妯″紡楠岃瘉 ERROR: OPENAI_API_KEY is required...锛汮SON 妯″紡楠岃瘉 	urn.started 鍜?	urn.failed銆?
- 娴嬭瘯涓嶈Е缃戯紝鍙?patch 
ead_auth_json 骞舵帶鍒剁幆澧冨彉閲忋€?
- 绐勯獙璇侀€氳繃锛? 涓?CLI 鏈湴 HTTP 娴嬭瘯鍔?	ests.test_exec_local_runtime 鍏?13 涓祴璇?OK銆?

### Turn 217 - HTTP transport error body 瀵归綈

- pycodex/core/http_transport.py 鎹曡幏 HTTPError / URLError 骞惰浆涓哄彲璇?RuntimeError銆?
- HTTPError 浼氳鍙?body锛屼紭鍏堟彁鍙?JSON error.message 鎴栭《灞?message銆?
- 鎵╁睍 runtime 娴嬭瘯锛岀敤 fake opener 鎶?HTTP 400锛岄獙璇侀敊璇秷鎭寘鍚?HTTP 400: bad schema銆?
- 绐勯獙璇侀€氳繃锛歝ompileall 鍜?	ests.test_exec_local_runtime 鍧?OK锛?0 涓祴璇曢€氳繃銆?

### Turn 218 - CLI local HTTP provider error tests 瀵归綈

- 鏂板 CLI provider error human/json 娴嬭瘯锛岃瘉鏄?transport 椋庢牸 RuntimeError 鑳介€氳繃鏈湴 HTTP exec 鍒嗘敮杈撳嚭銆?
- Human 妯″紡楠岃瘉 ERROR: Responses API request failed with HTTP 400: bad schema銆?
- JSON 妯″紡楠岃瘉 	hread.started銆?urn.started銆?urn.failed銆?
- 绐勯獙璇侀€氳繃锛歱rovider error銆乵issing API key銆乺untime 娴嬭瘯鍏?14 涓祴璇?OK銆?

### Turn 219 - CLI local HTTP output-last-message 瀵归綈

- 鏂板 CLI 鏈湴 HTTP --output-last-message 娴嬭瘯锛岃瘉鏄?final assistant message 浼氬啓鍏ユ寚瀹氭枃浠躲€?
- 浣跨敤 fake sampler锛屼笉瑙﹀彂鐪熷疄缃戠粶銆?
- 淇娴嬭瘯涓渶鍒濊鍐欑殑閫夐」鍚嶏紝褰撳墠 CLI surface 鏄?-o / --output-last-message銆?
- 绐勯獙璇侀€氳繃锛氭湰鍦?HTTP CLI success/json 鐩稿叧娴嬭瘯鍔?	ests.test_exec_local_runtime 鍏?13 涓祴璇?OK銆?

### Turn 220 - CLI local HTTP JSON output-last-message 瀵归綈

- 鏂板 CLI 鏈湴 HTTP --json --output-last-message 娴嬭瘯銆?
- 楠岃瘉 stdout 淇濇寔 JSONL 杈撳嚭锛屽悓鏃?last-message 鏂囦欢鍐欏叆鏈€缁?assistant message銆?
- 娴嬭瘯浣跨敤 fake sampler锛屼笉瑙﹀彂鐪熷疄缃戠粶銆?
- 绐勯獙璇侀€氳繃锛歨uman/json output-last-message 鐩稿叧娴嬭瘯鍔?	ests.test_exec_local_runtime 鍏?13 涓祴璇?OK銆?

### Turn 221 - CLI local HTTP auth.json 瀵归綈

- 鏂板 CLI 鏈湴 HTTP auth.json API key 娴嬭瘯銆?
- 楠岃瘉娌℃湁 OPENAI_API_KEY 鐜鍙橀噺鏃讹紝
ead_auth_json() 杩斿洖鐨?AuthDotJson(openai_api_key=...) 浼氫紶缁欐湰鍦?HTTP sampler銆?
- 娴嬭瘯涓嶈Е缃戯紝浣跨敤 fake sampler 杩斿洖 assistant message銆?
- 绐勯獙璇侀€氳繃锛歛uth.json銆乵issing key銆乭uman success銆乺untime 鐩稿叧娴嬭瘯鍏?13 涓?OK銆?

### Turn 222 - local HTTP auth precedence 瀵归綈

- 鏂板 default_local_http_exec_auth(...)锛岄泦涓В鏋愭湰鍦?HTTP exec 鐨?API key 鏉ユ簮銆?
- 璁よ瘉浼樺厛绾ф槑纭负 OPENAI_API_KEY 鐜鍙橀噺浼樺厛锛宎uth.json API key 浣滀负 fallback銆?
- CLI 鏈湴 HTTP exec 鍒嗘敮鏀逛负澶嶇敤璇?helper銆?
- 鏂板 CLI 鍜?runtime 娴嬭瘯瑕嗙洊 auth.json fallback 涓?env 浼樺厛绾с€?
- 绐勯獙璇侀€氳繃锛氱浉鍏?CLI 娴嬭瘯鍔?	ests.test_exec_local_runtime 鍏?14 涓祴璇?OK銆?

### Turn 223 - local HTTP runtime model/base_url 瀵归綈

- 鏂板 default_local_http_exec_base_url(...)锛岄泦涓В鏋愭湰鍦?HTTP exec 鐨?provider base URL銆?
- uild_default_local_http_exec_runtime(...) 鏀逛负澶嶇敤 base_url helper銆?
- 琛ユ祴璇曢攣瀹?model 浼樺厛绾э細config.model -> PYCODEX_EXEC_MODEL -> OPENAI_MODEL -> 榛樿 gpt-5銆?
- 琛ユ祴璇曢攣瀹?base_url 浼樺厛绾э細OPENAI_BASE_URL -> 榛樿 https://api.openai.com/v1銆?
- 绐勯獙璇侀€氳繃锛?ests.test_exec_local_runtime 鍏?13 涓祴璇?OK銆?

### Turn 224 - exec config.toml bootstrap 瀵归綈

- _run_noninteractive_exec(...) 鐜板湪璇诲彇 CODEX_HOME/config.toml 骞朵紶缁?uild_exec_config_bootstrap_plan(...)銆?
- 澶嶇敤宸叉湁 
ead_toml_mapping(...)銆丆ONFIG_TOML_FILE銆?ind_codex_home()锛屼笉鏂伴€犻厤缃鍙栭€昏緫銆?
- 鏂板 CLI 鏈湴 HTTP 娴嬭瘯锛岃瘉鏄?config.toml 鐨?user_instructions 浼氳繘鍏?ExecSessionConfig銆?
- 娴嬭瘯鍚屾椂鍙戠幇骞朵繚鐣?AGENTS.md/project-doc 浼氳拷鍔犺繘 user instructions 鐨勭幇鏈夎涓恒€?
- 绐勯獙璇侀€氳繃锛氱浉鍏?CLI/config/runtime 娴嬭瘯鍏?23 涓?OK銆?

### Turn 225 - local HTTP config model/provider/base_url 瀵归綈

- exec_config_plan 鐜板湪浼氫粠 config.toml 璇诲彇鍩虹 model 鍜?model_provider銆?
- 鏈湴 HTTP runtime 鍙帴鏀?config_toml锛屽苟浠?model_providers.<id>.base_url 瑙ｆ瀽 provider base URL銆?
- CLI 鏈湴 HTTP exec 鍒嗘敮浼氭妸宸茶鍙栫殑 config_toml 浼犲叆 runtime 鏋勯€犮€?
- 琛ユ祴璇曡鐩?config model/provider銆乺untime model fallback銆乸rovider base_url fallback銆?
- 绐勯獙璇侀€氳繃锛氱浉鍏?config/runtime/CLI 娴嬭瘯鍏?24 涓?OK銆?

### Turn 226 - local HTTP config provider env_key 瀵归綈

- 鏈湴 HTTP exec 鐨?auth 瑙ｆ瀽鐜板湪鏀寔 `config.toml` 鐨?`model_providers.<id>.env_key`銆?
- `OPENAI_API_KEY` 浠嶄繚鎸佹渶楂樹紭鍏堢骇锛沺rovider `env_key` 鍦ㄦ病鏈?OpenAI key 鏃跺彲浣滀负鑷畾涔?provider 鐨勭幆澧冨彉閲忔潵婧愶紱auth.json 缁х画浣滀负 fallback銆?
- CLI 鏈湴 HTTP exec 鍒嗘敮鏀逛负鎶?auth.json 浜ょ粰 runtime 缁熶竴瑙ｆ瀽锛岄伩鍏嶆彁鍓嶈В鏋愬鑷?provider env_key 澶辨晥銆?
- 琛ュ厖 runtime 鍜?CLI 绐勮寖鍥存祴璇曪紝瑕嗙洊 provider env_key銆乥ase_url銆乸rovider id 鍜?auth 浼犻€掋€?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py pycodex\cli\parser.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`; `python -m unittest tests.test_exec_local_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_uses_config_provider_env_key`锛?7 tests OK銆?

### Turn 227 - local HTTP shell tool output helper 瀵归綈

- 鏂板 `shell_tool_outputs_from_local_http_exec_result(...)`锛屼粠 Responses function_call/custom_tool_call 鎻愬彇 shell/local_shell/exec 鍛戒护銆?
- helper 浣跨敤 `subprocess.run` 鍜?`ExecSessionConfig.cwd` 鎵ц鍛戒护锛屽苟鐢熸垚 Responses 椋庢牸 `function_call_output` mapping銆?
- 褰撳墠涓嶅湪 CLI 璺緞鑷姩鎵ц锛岀瓑寰呭鎵?娌欑绛栫暐鎺ュ叆鍚庡啀缁勬垚瀹屾暣宸ュ叿闂幆銆?
- 琛ュ厖 fake runner 娴嬭瘯锛岃鐩?command/cwd/timeout/call_id/output 鏍煎紡銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?7 tests OK銆?

### Turn 228 - local HTTP tool output follow-up 瀵归綈

- 鏂板 `response_items_from_local_http_tool_outputs(...)`锛屾妸 Responses tool output mapping 杞负 prompt-visible `ResponseItem`銆?
- 鏂板 `run_exec_tool_output_http_sampling(...)`锛屾妸涓婁竴杞ā鍨嬭緭鍑哄拰宸ュ叿杈撳嚭鍐欏叆 in-memory history 鍚庡彂璧蜂笅涓€杞?HTTP sampling銆?
- 璇ヨ矾寰勪繚鎸?`function_call_output` 鍗忚璇箟锛屾病鏈夋妸宸ュ叿缁撴灉浼鎴愭櫘閫氱敤鎴锋秷鎭€?
- 琛ュ厖娴嬭瘯瑕嗙洊 shell call銆乫unction_call_output銆乫ollow-up request input 缁撴瀯銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?8 tests OK銆?

### Turn 229 - local HTTP shell tool loop helper 瀵归綈

- 鏂板 `run_exec_user_turn_with_shell_tools_http_sampling(...)`锛屾妸鏅€?user turn銆乻hell tool output 鎵ц鍜?follow-up sampling 涓叉垚鍗曡疆宸ュ叿寰幆銆?
- helper 榛樿鏈€澶氭墽琛?1 杞伐鍏峰洖鐏岋紝骞舵牎楠?`max_tool_rounds` 涓洪潪璐熸暣鏁般€?
- 璇?helper 鏆備笉鎺?CLI 鑷姩鎵ц锛岀瓑寰呭鎵?娌欑绛栫暐鎺ュ叆鍚庡啀寮€鏀剧粰鐢ㄦ埛璺緞銆?
- 琛ュ厖娴嬭瘯瑕嗙洊绗竴杞?tool call銆佺浜岃疆 function_call_output 鍜屾渶缁?assistant answer銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?9 tests OK銆?

### Turn 230 - local HTTP shell approval gate 瀵归綈

- 鏂板 `local_http_shell_tool_auto_execute_allowed(...)` 鍜?`local_http_shell_tool_approval_required_output(...)`銆?
- `shell_tool_outputs_from_local_http_exec_result(...)` 鐜板湪鍙湁 `AskForApproval.NEVER` 鎵嶄細鑷姩鎵ц shell 鍛戒护銆?
- 鍏跺畠瀹℃壒绛栫暐杩斿洖 `approval_required` 鐨?`function_call_output`锛屼笉璋冪敤 runner銆?
- 琛ュ厖娴嬭瘯瑕嗙洊 `AskForApproval.ON_REQUEST` 涓?runner 涓嶆墽琛屻€?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?0 tests OK銆?

### Turn 231 - CLI local HTTP shell tool loop flag 瀵归綈

- 鏂板 `PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS=1` 寮€鍏冲拰 `local_http_exec_shell_tools_enabled(...)`銆?
- CLI 鏈湴 HTTP exec 鍒嗘敮鍦ㄨ寮€鍏冲惎鐢ㄦ椂璋冪敤 `run_exec_user_turn_with_shell_tools_http_sampling(...)`銆?
- 榛樿 `PYCODEX_EXEC_LOCAL_HTTP=1` 琛屼负涓嶅彉锛屼粛璧版櫘閫氭湰鍦?HTTP sampling銆?
- 琛ュ厖 CLI 娴嬭瘯瑕嗙洊宸ュ叿寰幆 helper 鍏ュ彛锛屾祴璇曚笉瑙︾綉銆佷笉璺戠湡瀹?shell銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py pycodex\cli\parser.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`; `python -m unittest tests.test_exec_local_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop`锛?1 tests OK銆?

### Turn 232 - CLI local HTTP max tool rounds 瀵归綈

- 鏂板 `PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS` 鍜?`local_http_exec_max_tool_rounds(...)`銆?
- shell tools 寮€鍏冲惎鐢ㄦ椂锛孋LI 浼氭妸鏈€澶у伐鍏疯疆鏁颁紶缁?`run_exec_user_turn_with_shell_tools_http_sampling(...)`銆?
- 榛樿鍊间粛涓?1锛屽厑璁告樉寮?0锛岄潪娉曞€艰繑鍥炴竻鏅伴敊璇€?
- 琛ュ厖 runtime 鍜?CLI 娴嬭瘯瑕嗙洊瑙ｆ瀽銆佷紶鍙傚拰閿欒鍒嗘敮銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py pycodex\cli\parser.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`; `python -m unittest tests.test_exec_local_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_rejects_invalid_max_rounds`锛?3 tests OK銆?

### Turn 233 - local HTTP shell workdir timeout args 瀵归綈

- 鏂板 `LocalHttpShellInvocation` 鍜?shell invocation 鍙傛暟瑙ｆ瀽銆?
- shell helper 鐜板湪鏀寔 `workdir`/`cwd`锛岀浉瀵硅矾寰勪細鍩轰簬 session cwd 瑙ｆ瀽銆?
- shell helper 鐜板湪鏀寔 `timeout_ms`/`timeout`锛屾寜姣杞浼犵粰 runner銆?
- 琛ュ厖 fake runner 娴嬭瘯瑕嗙洊 command/workdir/timeout 鍙傛暟浼犻€掋€?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?2 tests OK銆?

### Turn 234 - local HTTP shell login arg 瀵归綈

- `LocalHttpShellInvocation` 鏂板 `login` 瀛楁銆?
- shell helper 鐜板湪璇嗗埆 arguments 涓殑 bool `login` 鍙傛暟銆?
- 榛樿 `subprocess.run` 涓嶆帴鏀?`login` kwarg锛岃嚜瀹氫箟 runner 浼氭敹鍒拌鍙傛暟銆?
- 琛ュ厖 fake runner 娴嬭瘯瑕嗙洊 `login=true` 浼犻€掋€?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?3 tests OK銆?

### Turn 235 - local HTTP shell approval metadata 瀵归綈

- `LocalHttpShellInvocation` 鏂板 `sandbox_permissions` 鍜?`justification`銆?
- shell helper 鍦ㄩ潪 `never` 瀹℃壒绛栫暐涓嬩笉鎵ц鍛戒护锛屼絾 approval-required output 浼氫繚鐣欒繖浜涘鎵逛笂涓嬫枃瀛楁銆?
- `local_http_shell_tool_approval_required_output(...)` 鍏煎鏃х殑 command 瀛楃涓茶緭鍏ャ€?
- 琛ュ厖 fake response/fake runner 娴嬭瘯瑕嗙洊 metadata 淇濈暀涓?runner 涓嶆墽琛屻€?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?4 tests OK銆?

### Turn 236 - local HTTP shell prefix_rule metadata 瀵归綈

- `LocalHttpShellInvocation` 鏂板 `prefix_rule`銆?
- shell helper 瑙ｆ瀽 list/tuple of str 鐨?`prefix_rule`锛岄潪瀛楃涓插簭鍒椾細蹇界暐銆?
- approval-required output 鐜板湪浠?JSON 鏁扮粍鏍煎紡淇濈暀 prefix rule銆?
- 琛ュ厖 fake response/fake runner 娴嬭瘯瑕嗙洊 prefix rule 淇濈暀涓?runner 涓嶆墽琛屻€?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`锛?5 tests OK銆?

### Turn 237 - local HTTP shell output truncation 瀵归綈

- 鏂板 `PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS` 鍜?`local_http_exec_tool_output_max_chars(...)`銆?
- shell helper 鏀寔 `output_max_chars`锛屾甯歌緭鍑哄拰 timeout 杈撳嚭閮戒細鎴柇銆?
- CLI shell tools 璺緞浼氭妸璇ラ厤缃紶缁欏伐鍏峰惊鐜?helper銆?
- 琛ュ厖 runtime/CLI 娴嬭瘯瑕嗙洊瑙ｆ瀽銆佹埅鏂€佷紶鍙傚拰闈炴硶鍊奸敊璇€?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py pycodex\cli\parser.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`; `python -m unittest tests.test_exec_local_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_rejects_invalid_output_max_chars`锛?9 tests OK銆?


### Turn 238 - local HTTP shell success 瀵归綈

- 鏄惧紡鏈湴 HTTP exec 鐨?shell `function_call_output` 鐜板湪鎼哄甫 `success`锛宺eturncode 0 涓?true锛岄潪 0銆乼imeout銆乤pproval-required 涓?false銆?
- `FunctionCallOutputPayload.success` 鐜板湪浼氫粠鍗忚瀵硅薄搴忓垪鍖栧洖 Responses input锛屽苟鍦?`ResponseItem.from_mapping()` 涓弽搴忓垪鍖栦繚鐣欍€?
- follow-up sampling request 鐜板湪鑳芥妸宸ュ叿鎵ц鎴愬姛/澶辫触鐘舵€佷氦杩樼粰妯″瀷锛岄伩鍏嶅け璐ュ懡浠よ璇綋鎴愭櫘閫氭垚鍔熸枃鏈€?
- 琛ュ厖 runtime 娴嬭瘯瑕嗙洊鎴愬姛銆佸け璐ャ€佽秴鏃躲€佸鎵规嫆缁濆拰 follow-up request success 瀛楁銆?
- Validation: `python -m compileall -q pycodex\protocol\models.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`.


### Turn 239 - local HTTP shell tool spec 瀵归綈

- 鏄惧紡鏈湴 HTTP shell tool loop 鐜板湪浼氶粯璁ゅ悜 Responses request 澹版槑 `shell` function tool銆?
- 鏂板杞婚噺 `LocalHttpShellToolRouter` 鍜?`local_http_shell_tools_built_tools(...)`锛屽湪淇濈暀璋冪敤鏂瑰凡鏈?tool specs 鐨勫熀纭€涓婅拷鍔?shell spec銆?
- 棣栬疆 user turn 鍜?tool-output follow-up turn 閮戒細鎼哄甫鐩稿悓 shell 宸ュ叿澹版槑锛岃妯″瀷鑳芥寔缁骇鐢?shell function_call銆?
- 琛ュ厖娴嬭瘯瑕嗙洊 shell spec shape銆佸凡鏈夊伐鍏蜂繚鐣欙紝浠ュ強 shell loop 涓よ疆璇锋眰涓殑 tools 瀛楁銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`.


### Turn 240 - local HTTP apply_patch tool 瀵归綈

- 鏄惧紡鏈湴 HTTP shell/tool loop 鐜板湪浼氬０鏄?`apply_patch` custom tool锛屽苟淇濈暀宸叉湁宸ュ叿澹版槑銆?
- `shell_tool_outputs_from_local_http_exec_result(...)` 鐜板湪鑳芥墽琛?`apply_patch` tool call锛氬鐢?`parse_patch` 鍜?`verify_apply_patch_args`锛岄獙璇佹垚鍔熷悗钀界洏鍐欏叆 add/update/delete/move銆?
- apply_patch 鎵ц娌跨敤鏈湴宸ュ叿瀹℃壒 gate锛涢潪 `never` 瀹℃壒绛栫暐杩斿洖 approval-required output锛屼笉淇敼鏂囦欢銆?
- 琛ュ厖娴嬭瘯瑕嗙洊 apply_patch spec銆佹垚鍔熷啓鏂囦欢銆佸鎵规嫆缁濅笉鍐欐枃浠讹紝浠ュ強宸ュ叿寰幆涓よ疆璇锋眰鎸佺画鎼哄甫 apply_patch銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`.


### Turn 241 - local HTTP apply_patch parity 瀵归綈

- apply_patch custom tool output 鐜板湪淇濈暀 `name: apply_patch`锛屽苟鍦?follow-up ResponseItem 鍥炵亴鏃剁户缁繚鐣欒鍚嶇О銆?
- 琛ュ厖娴嬭瘯璇佹槑鏈湴 HTTP apply_patch 钀界洏 helper 涓嶅彧鏀寔 add锛屼篃鏀寔 update銆乨elete 鍜?move銆?
- approval-required 鍒嗘敮鐜板湪涔熼攣瀹?custom output 鐨?apply_patch 鍚嶇О锛岄伩鍏嶅悗缁簨浠?妯″瀷鍥炵亴涓㈠け宸ュ叿韬唤銆?
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`.

### Turn 242 - local HTTP exec_command spec 对齐

- 显式本地 HTTP shell/tool loop 的默认模型可见工具从简化 shell 推进为 Rust 核心更接近的 exec_command。
- exec_command schema 现在以 cmd 为 required 参数，并补充 workdir、shell、	ty、yield_time_ms、max_output_tokens 等 Rust spec 常见字段。
- 工具分发继续兼容 shell、shell_command、local_shell、exec，避免旧形状回归。
- 单测新增 exec_command + cmd 参数调用覆盖，并更新默认工具声明断言。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，35 tests OK。



### Turn 243 - exec_command output schema 对齐

- 新增 local_http_exec_command_output_schema()，让显式本地 HTTP exec_command 声明携带 Rust unified exec 风格输出 schema。
- LocalHttpShellInvocation 增加 shell、	ty、yield_time_ms、max_output_tokens 字段，为后续 PTY/session 对齐留出协议承载。
- 本地 shell helper 现在解析 max_output_tokens，并在无三方 tokenizer 的前提下以约 4 字符/token 的方式与全局输出上限取更严格截断。
- 单测覆盖输出 schema 与 max_output_tokens 截断行为。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，35 tests OK。



### Turn 244 - write_stdin protocol entry 对齐

- 新增 local_http_write_stdin_tool_spec()，声明 Rust Codex write_stdin companion tool 的参数和输出 schema。
- 显式本地 HTTP tool router 现在默认暴露 exec_command、write_stdin、pply_patch。
- tool loop 现在识别 write_stdin 调用；审批不允许时返回 approval-required，允许执行但尚无 session runtime 时返回明确 unavailable。
- 单测覆盖 write_stdin schema、默认工具声明，以及 write_stdin 调用不再被静默忽略。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，37 tests OK。



### Turn 245 - local exec session runtime 初步对齐

- 新增 LocalHttpExecSession 与 LocalHttpExecSessionManager，用 stdlib subprocess.Popen、	hreading、queue 支撑最小本地会话执行。
- exec_command 在带 yield_time_ms 或 	ty=true 时会启动 session 并返回 session_id；普通路径仍保留一次性 runner。
- write_stdin 现在可以向活跃 session 写入 stdin 并返回近期输出，未知 session 返回明确错误。
- 单测覆盖启动子进程、读取初始输出、写入 stdin、收到后续输出的最小闭环。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，38 tests OK。



### Turn 246 - exec session structured output 对齐

- LocalHttpExecSession.snapshot() 现在生成包含 wall_time_seconds、exit_code、session_id、original_token_count、output 的结构化 payload。
- 新增 local_http_exec_output_text(...)，把结构化 payload 渲染成当前 FunctionCallOutputPayload 可安全回灌的文本。
- session exec_command 与 write_stdin tool output 现在同时携带文本 output 和内部 structured_output，为后续协议层进一步结构化对齐留接口。
- unknown session 分支也改为结构化 payload 后再渲染。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，39 tests OK。



### Turn 247 - exec session timeout lifecycle 对齐

- LocalHttpExecSession 现在支持 timeout deadline，session snapshot 会在超过 	imeout_ms 后终止进程。
- 超时 session 会返回结构化 	imed_out: true 和 exit_code: timeout，并且不再暴露 session_id。
- session manager 在超时/结束后清理 session 和管道，避免后续 write_stdin 写入已结束进程。
- 单测新增真实子进程 sleep 超时场景，覆盖 timeout 清理和文本渲染。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，40 tests OK。



### Turn 248 - write_stdin poll semantics 对齐

- `LocalHttpExecSessionManager.write(...)` 现在只有 `chars` 非空时才写入 stdin。
- `write_stdin(chars="")` 现在按 Rust companion tool 语义只等待并轮询近期输出。
- 新增真实子进程测试：先输出 `first`，延迟输出 `second`，随后通过空 `chars` poll 拿到 `second`。
- 测试覆盖进程完成后不再返回 `session_id`。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，41 tests OK。


### Turn 249 - exec session chunk_id 对齐

- `LocalHttpExecSession` 新增 per-session chunk counter。
- session `snapshot()` 现在会在结构化 payload 中携带 `chunk_id`，形如 `session_id:chunk_number`。
- `write_stdin` 和空 chars poll 的后续输出会递增 chunk id；unknown session 使用 `session_id:unknown`。
- `local_http_exec_output_text(...)` 现在会渲染 `chunk_id`。
- 单测覆盖首块、第二块、poll、timeout 和文本渲染。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，41 tests OK。


### Turn 250 - exec_command shell parameter 对齐

- `LocalHttpExecSessionManager.start(...)` 新增 `shell` 参数，并传给 `subprocess.Popen(..., executable=...)`。
- session `exec_command` 路径现在会把 `invocation.shell` 传给 session manager。
- `_run_shell_tool_command_result(...)` 新增 `shell_binary` 参数，并传给 `subprocess.run(..., executable=...)`。
- 一次性 runner 路径和 session 路径都补充了 shell 参数传递测试。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，43 tests OK。


### Turn 251 - exec_command tty request metadata 对齐

- `LocalHttpExecSession` 新增 `tty_requested` 状态，保留模型对 `exec_command(tty=true)` 的请求语义。
- session `exec_command` 路径现在会把 `invocation.tty` 传入 session manager，并在结构化 payload 中返回 `tty_requested: true`。
- `local_http_exec_output_text(...)` 现在会渲染 `tty_requested: true`，让当前文本 tool output 也能反映该请求状态。
- 单测覆盖 `tty=true` 在没有 `yield_time_ms` 时仍触发 session，并保留结构化/文本 metadata。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，44 tests OK。


### Turn 252 - unified exec default yield time 对齐

- 对照 Rust `default_exec_yield_time_ms() = 10_000` 和 `default_write_stdin_yield_time_ms() = 250`。
- Python 本地 HTTP `exec_command` 现在省略 `yield_time_ms` 时默认等待 10 秒窗口，保持 unified exec 的 session/poll 模型。
- Python 本地 HTTP `write_stdin` 现在省略 `yield_time_ms` 时默认等待 250ms。
- `LocalHttpExecSession.snapshot(...)` 改为在进程提前退出时不无谓睡满 yield 窗口，避免短命令被默认 10 秒延迟拖慢。
- 单测覆盖 exec_command/write_stdin 默认 yield 时间。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，46 tests OK。


### Turn 253 - exec_command additional_permissions metadata 对齐

- 对照 Rust `ExecCommandArgs.additional_permissions` 字段，Python 本地 HTTP `exec_command` schema 新增 `additional_permissions` object。
- `LocalHttpShellInvocation` 现在保留 `additional_permissions` 映射。
- approval-required tool output 现在会回显 compact JSON 形式的 `additional_permissions`，避免模型请求的安全/权限 metadata 被丢弃。
- 单测覆盖 schema 声明与 approval-required metadata 输出。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，46 tests OK。


### Turn 254 - unified exec tool metadata 对齐

- 对照 Rust `ResponsesApiTool`，Python 本地 HTTP `exec_command` tool spec 现在显式声明 `strict: false`。
- Python 本地 HTTP `exec_command` tool spec 现在显式声明 `defer_loading: null`。
- `write_stdin` tool spec 同步补齐 `strict: false` 与 `defer_loading: null`。
- 单测覆盖两个 tool spec 的顶层 metadata。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，46 tests OK。


### Turn 255 - unified exec timeout exit code 对齐

- 对照 Rust `EXEC_TIMEOUT_EXIT_CODE = 124` 与 unified exec output schema 的 `exit_code: number`。
- Python 本地 HTTP session timeout 现在返回数字 `exit_code: 124`，不再在结构化 payload 中使用字符串 `timeout`。
- 文本 tool output 仍保留 `timed_out: true`，方便人类/日志识别超时。
- 单测更新 timeout 断言，覆盖数字退出码与文本提示。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，46 tests OK。


### Turn 256 - unified exec response text 对齐

- 对照 Rust `ExecCommandToolOutput.response_text()`，Python 本地 HTTP exec 文本输出改为 `Chunk ID:`、`Wall time: ... seconds`、`Process exited with code ...`、`Process running with session ID ...`、`Original token count:`、`Output:` 风格。
- `wall_time_seconds` 文本渲染现在按 Rust 使用 4 位小数。
- 保留 Python 当前辅助提示 `timed_out: true` 与 `tty_requested: true`，不影响结构化 payload。
- 单测更新本地 exec 文本输出断言和 timeout 文本断言。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，46 tests OK。


### Turn 257 - unified exec response text auxiliary lines 对齐

- 对照 Rust `ExecCommandToolOutput.response_text()`，Python 本地 HTTP exec 文本输出不再渲染 `timed_out: true` 和 `tty_requested: true` 辅助行。
- `timed_out` 与 `tty_requested` 仍保留在内部 `structured_output`，供 Python runtime 状态判断和测试使用。
- timeout 文本现在只通过 `Process exited with code 124` 体现超时退出码，贴近 Rust 输出。
- 单测更新为断言辅助状态留在结构化 payload、但不进入 model-facing 文本。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，46 tests OK。


### Turn 258 - write_stdin unknown session error 对齐

- 对照 Rust `write_stdin` handler：未知 process id 会返回 `write_stdin failed: Unknown process id ...`，不是 unified exec output payload。
- Python `LocalHttpExecSessionManager.write(...)` 现在未知 session 时抛出 `KeyError`，由 tool 分发层转成普通失败文本。
- unknown session 不再返回带字符串 `exit_code: "unknown_session"` 的 `structured_output`，避免破坏 unified exec output schema。
- 单测更新为断言普通失败文本和无 `structured_output`。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，46 tests OK。


### Turn 259 - unified exec chunk_id generation 对齐

- 对照 Rust `generate_chunk_id()`：chunk id 是 6 位十六进制随机串。
- Python 本地 HTTP session 不再使用 `session_id:chunk_number` 这类调试格式。
- 新增 `local_http_generate_chunk_id()`，使用标准库 `secrets.token_hex(3)` 生成 6 位 hex id。
- session `exec_command` 和 `write_stdin` 输出现在都使用不透明 chunk id。
- 单测更新为断言 6 位 hex 形状和连续 chunk id 不相同。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，47 tests OK。


### Turn 260 - unified exec yield_time clamp 对齐

- 对照 Rust `MIN_YIELD_TIME_MS = 250`、`MIN_EMPTY_YIELD_TIME_MS = 5000`、`MAX_YIELD_TIME_MS = 30000`、`DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS = 300000`。
- Python 本地 HTTP `exec_command.yield_time_ms` 现在 clamp 到 `250ms..30000ms`。
- Python 本地 HTTP 非空 `write_stdin.yield_time_ms` 现在 clamp 到 `250ms..30000ms`。
- Python 本地 HTTP 空 `write_stdin(chars="")` 现在 clamp 到 `5000ms..300000ms`，更接近 Rust background poll 语义。
- 单测覆盖 exec_command、非空 write_stdin、空 poll 的上下限 clamp。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，49 tests OK。


### Turn 261 - unified exec default max output tokens 对齐

- 对照 Rust `DEFAULT_MAX_OUTPUT_TOKENS = 10_000` 与 `resolve_max_tokens(None)`。
- Python 本地 HTTP shell output 现在省略 `max_output_tokens` 时默认按约 `10_000 tokens * 4 chars` 截断。
- 显式 `max_output_tokens` 与环境变量 `PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS` 仍取更严格上限。
- 单测覆盖省略 `max_output_tokens` 时的大输出默认截断。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，50 tests OK。


### Turn 262 - unified exec output hard cap 对齐

- 对照 Rust `UNIFIED_EXEC_OUTPUT_MAX_BYTES = 1024 * 1024` 与 `HeadTailBuffer` 的 head/tail 保留策略。
- Python 本地 HTTP session output drain 现在在超过 `LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES` 时保留稳定 head 和 tail，丢弃中间内容。
- 新增 `local_http_retain_head_tail_output(...)` helper，保持标准库实现。
- 单测覆盖 head/tail 保留策略和 1MiB 常量。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，52 tests OK。


### Turn 263 - unified exec output hard cap byte semantics 对齐

- 对照 Rust `HeadTailBuffer` 的 byte-oriented 输出收集语义。
- `local_http_retain_head_tail_output(...)` 现在按 UTF-8 bytes 判断和切分，而不是用 Python 字符数近似。
- head/tail 切分时使用 UTF-8 decode `errors="ignore"` 丢弃边界上的半个字符，避免生成非法文本。
- 新增多字节文本测试，覆盖中文输出在 12 bytes 上限下的 head/tail 保留。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，53 tests OK。


### Turn 264 - unified exec incremental HeadTailBuffer 对齐

- 对照 Rust `HeadTailBuffer::push_chunk(...)`：输出 chunk 写入时先填 head budget，再维护有界 tail budget。
- Python 新增 `LocalHttpHeadTailBuffer`，使用标准库 `deque` 保存 head/tail bytes、retained byte count 和 omitted byte count。
- `LocalHttpExecSession` reader 线程现在直接写入有界 buffer，`_drain_output()` 只 drain retained bytes，不再先将所有输出放入无限 queue。
- `local_http_retain_head_tail_output(...)` 改为复用 `LocalHttpHeadTailBuffer`，避免 helper 和 session 语义分叉。
- 单测覆盖 Rust `fills_head_then_tail_across_multiple_chunks` 的核心例子。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，54 tests OK。


### Turn 265 - unified exec bytes pipe reader 对齐

- 对照 Rust unified exec 对 stdout/stderr bytes chunk 的处理方式。
- Python `LocalHttpExecSessionManager.start(...)` 现在用 binary pipes：`text=False`、`bufsize=0`。
- 真实 subprocess stdout 现在通过 `os.read(fd, 8192)` 按 bytes chunk 写入 `LocalHttpHeadTailBuffer`，避免 `readline()` 在无换行长输出上形成大块读取。
- `write_stdin` 真实路径现在将文本按 UTF-8 bytes 写入 stdin；测试 fake text stream 仍保留 TypeError fallback。
- 单测覆盖 session Popen 使用 binary pipe 参数。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，54 tests OK。


### Turn 266 - HeadTailBuffer observable API 对齐

- 对照 Rust `HeadTailBuffer::to_bytes()`、`snapshot_chunks()`、`omitted_bytes()` 和 `drain_chunks()`。
- Python `LocalHttpHeadTailBuffer` 现在提供 `omitted_bytes()` 方法，内部 omitted byte counter 改为私有字段。
- 新增 `to_bytes()` 和 `snapshot_chunks()`，可在不清空 buffer 的情况下查看 retained 输出。
- `drain_chunks()` 复用 `snapshot_chunks()` 后重置 retained/omitted 状态，贴近 Rust drain 语义。
- 单测补齐 zero budget drops everything、large chunk replaces tail end、drain resets state 等 Rust 对应边界。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，56 tests OK。


### Turn 267 - exec formatted truncation 对齐

- 对照 Rust `codex_utils_output_truncation::formatted_truncate_text(...)`：截断输出会带 `Total output lines: N` 前缀。
- Python `_truncate_shell_tool_output(...)` 不再只保留前缀并追加 `[truncated ...]`。
- 新增 `_truncate_middle_shell_tool_output(...)`，在当前近似 char/token budget 内保留 head 和 tail，中间写入 `... N chars truncated ...` 标记。
- 本轮仍沿用 Python 当前 token 近似策略：`max_output_tokens * 4 chars`，没有引入 tokenizer 或三方依赖。
- 单测更新为断言行数前缀、middle truncation 标记和 tail 内容保留。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，56 tests OK。


### Turn 268 - exec truncation byte budget 对齐

- 对照 Rust `formatted_truncate_text(...)` 的 `content.len() <= policy.byte_budget()` 判断；Rust `str::len()` 是 UTF-8 bytes。
- Python `_truncate_shell_tool_output(...)` 现在用 `len(output.encode("utf-8"))` 判断是否超过预算，而不是 Python 字符数。
- `_truncate_middle_shell_tool_output(...)` 现在按 UTF-8 byte budget 切分 head/tail，并用 `errors="ignore"` 避免半个 codepoint 进入输出。
- 截断标记继续使用 ASCII `... N chars truncated ...`，报告被省略的字符数。
- 单测覆盖中文多字节输出：字符数未超预算但 UTF-8 bytes 超预算时仍触发 formatted truncation。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，57 tests OK。


### Turn 269 - approx token count byte semantics 对齐

- 对照 Rust `codex_utils_string::approx_token_count(...)`：`APPROX_BYTES_PER_TOKEN = 4`，并使用 `text.len()` 的 UTF-8 bytes 长度。
- Python `_approx_token_count(...)` 现在使用 `len(text.encode("utf-8"))` 计算近似 token 数，而不是 Python Unicode 字符数。
- `original_token_count` 对中文等多字节输出会更接近 Rust。
- 单测覆盖 ASCII 与中文多字节文本的 token 近似差异。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，58 tests OK。


### Turn 270 - approx bytes for tokens 对齐

- 对照 Rust `APPROX_BYTES_PER_TOKEN = 4` 和 `approx_bytes_for_tokens(tokens) = tokens * 4`。
- Python 新增 `LOCAL_HTTP_APPROX_BYTES_PER_TOKEN = 4`。
- Python 新增 `_approx_bytes_for_tokens(...)`，用于把 `max_output_tokens` 转为 byte budget。
- `_approx_token_count(...)` 和 `_effective_shell_output_max_chars(...)` 现在共享同一个 bytes-per-token 常量，避免散落 `* 4`。
- 单测覆盖常量、0 tokens 和普通 token 到 bytes 的换算。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，59 tests OK。


### Turn 271 - unified exec max output tokens constant 对齐

- 对照 Rust `UNIFIED_EXEC_OUTPUT_MAX_TOKENS = UNIFIED_EXEC_OUTPUT_MAX_BYTES / 4`。
- Python 新增 `LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS`，由 `LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES // LOCAL_HTTP_APPROX_BYTES_PER_TOKEN` 派生。
- `LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS` 加入 `__all__`，供后续 core/session 对齐复用。
- 单测覆盖派生常量和 `_approx_bytes_for_tokens(...)` 的反向换算。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，60 tests OK。


### Turn 272 - unified exec max process pruning 对齐

- 对照 Rust `MAX_UNIFIED_EXEC_PROCESSES = 64` 与 `prune_processes_if_needed(...)`。
- Python 新增 `LOCAL_HTTP_MAX_UNIFIED_EXEC_PROCESSES = 64`。
- Python 新增 `LOCAL_HTTP_UNIFIED_EXEC_PROTECTED_RECENT_PROCESSES = 8`，对应 Rust pruning 时保护最近 8 个 process。
- `LocalHttpExecSessionManager` 现在记录 session last-used，启动新 session 前达到上限会优先 prune 已退出且非保护 session，否则 prune 最老的非保护 session。
- 被 prune 的仍在运行 session 会先 terminate process tree，再 close pipes。
- 单测覆盖 `max_sessions=2` 时启动第三个 session 会 prune 最老 session。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，61 tests OK。


### Turn 273 - unified exec exited-priority pruning 覆盖

- 对照 Rust `process_id_to_prune_from_meta(...)`：达到上限时，在非保护集合中优先选择已退出 process。
- Python 当前 pruning 实现已经包含该分支，本轮补测试锁住行为，避免后续退化为纯 LRU。
- 新增测试构造 10 个 session：最近 8 个受保护，非保护集合中最老 session 仍运行、较新的 session 已退出。
- 调用 `_prune_sessions_if_needed()` 后应 prune 已退出 session，而不是最老运行 session。
- 测试同时断言运行中的 session 不会被 terminate，已退出 session 只 close。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，62 tests OK。


### Turn 274 - unified exec schema output payload 对齐

- 对照 Rust unified exec output schema：`additionalProperties: false`，字段仅包含 `chunk_id`、`wall_time_seconds`、`exit_code`、`session_id`、`original_token_count`、`output`。
- Python 新增 `local_http_exec_schema_output_payload(...)`，从内部 exec payload 过滤出 schema-visible 字段。
- `shell_tool_outputs_from_local_http_exec_result(...)` 现在把 `structured_output` 设为 schema-clean payload。
- Python 内部诊断字段 `timed_out`、`tty_requested` 保留在新增的 `internal_output` 中，避免丢失 runtime/test 状态。
- timeout/tty 单测更新为断言 schema output 不含内部字段、internal output 仍保留内部状态。
- Validation: `python -m compileall -q pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`; `python -m unittest tests.test_exec_local_runtime`，63 tests OK。



### Turn 114 - exec runtime shutdown actions

- Added `ExecRuntimeRequestSequence.exec_loop_shutdown_actions(...)` as a semantic bridge for the Rust `initiate_shutdown` processor path.
- Locked the shutdown loop behavior with coverage that processes the final notification, sends `thread/unsubscribe`, and breaks the loop.
- This keeps the Python exec startup/loop sequence aligned with Rust control flow while continuing to avoid MCP/plugin expansion.


### Turn 115 - exec startup client request sequence

- Added `ExecRuntimeRequestSequence.startup_client_requests_from_bootstrap_result(...)` so runner code can consume the ordered startup request pair directly.
- Locked the core startup request order as `thread/start` followed by `turn/start`, with request ids `1` and `2` and the prompt carried into the initial turn input.
- This moves the Python exec bridge closer to a real CLI runner while staying focused on core/common behavior.


### Turn 116 - exec startup response bridge

- Added response-side helpers on `ExecRuntimeRequestSequence` so runner code can parse `thread/start` responses, combine them with the already-sent initial operation request, and produce startup processor actions.
- Preserved request-id discipline by requiring the already-created initial operation request instead of regenerating it while handling responses.
- Added coverage for deriving startup processor actions from the startup response pair, including the initial config summary action.


### Turn 117 - exec bootstrap-to-initial request plan

- Added `ExecRuntimeInitialRequestPlan` to carry parsed bootstrap state and the next initial operation request for runner startup.
- Added `ExecRuntimeRequestSequence.initial_request_plan_from_bootstrap_response(...)` and `initial_client_request_from_bootstrap_response(...)` so a real runner can turn the first server response directly into the next request.
- Covered the bridge with request id, method, and thread id propagation assertions.


### Turn 118 - exec startup exchange bridge

- Added `ExecRuntimeStartupExchange` to package the parsed initial request plan, startup result, and startup processor actions for a real runner.
- Added `ExecRuntimeRequestSequence.startup_exchange_from_responses(...)` so runner code can complete the startup handshake from the two server responses in one disciplined path.
- Covered the exchange with request id, method, prompt, and session-configured thread id assertions.


### Turn 119 - exec loop event exchange bridge

- Added `ExecRuntimeEventExchange` to package a single event-loop step and the runner actions derived from it.
- Added `ExecRuntimeRequestSequence.exec_loop_exchange(...)` so a real runner can convert one server event into both decision state and executable actions through one core path.
- Covered normal server notification handling after startup exchange, including state thread id, no-break status, and `process_notification` action generation.


### Turn 120 - exec loop shutdown exchange bridge

- Added `ExecRuntimeRequestSequence.exec_loop_shutdown_exchange(...)` to expose the shutdown event-loop path as a full exchange with both step state and executable actions.
- Covered the post-startup shutdown path where `turn/start` has consumed request id `2`, so `thread/unsubscribe` correctly uses request id `3`.
- Locked the runner-facing action order as `process_notification`, `send_request`, then `break`.


### Turn 121 - exec runner action summary

- Added `ExecRuntimeActionSummary` and `exec_runtime_action_summary(...)` to distill runner work from raw `ExecLoopAction` tuples.
- Added `action_summary` properties on startup and event exchanges so runner code can directly inspect outgoing client requests, notifications, warnings, and break decisions.
- Covered shutdown and startup summaries, including unsubscribe request id `3` after the startup exchange path.


### Turn 122 - exec action summary config output

- Extended `ExecRuntimeActionSummary` with `config_summaries` so runner code can directly discover startup configuration output work.
- The summary now extracts `print_config_summary` action mappings alongside client requests, notifications, warnings, and break state.
- Added coverage for startup config summary prompt/thread propagation and for shutdown exchanges having no config summaries.


### Turn 123 - exec action summary server requests

- Extended `ExecRuntimeActionSummary` with `server_requests` so runner code can distinguish server-originated work from outgoing client requests.
- `exec_runtime_action_summary(...)` now extracts `handle_server_request` actions alongside client requests, notifications, config summaries, warnings, and break state.
- Added focused coverage for server-request extraction without expanding MCP/plugin behavior.


### Turn 124 - exec runner transcript aggregation

- Added `ExecRuntimeRunnerTranscript` and `exec_runtime_runner_transcript(...)` to aggregate startup and event exchanges into a runner-facing execution trace.
- The transcript exposes aggregated action summaries, client/server requests, notifications, config summaries, warnings, and break state.
- Added coverage for combining startup config output with a shutdown unsubscribe event exchange.


### Turn 125 - exec runner transcript from responses

- Added `ExecRuntimeEventInput` to describe one runner event-loop input with its processor status and optional thread-read backfill response.
- Added `ExecRuntimeRequestSequence.runner_transcript_from_responses(...)` to build a complete runner transcript from startup responses plus a tuple of event inputs.
- Covered the startup-to-shutdown path in one sequence-level test, preserving request ids `2` for the initial turn and `3` for unsubscribe.


### Turn 126 - exec runner transcript incremental append

- Added `ExecRuntimeRunnerTranscript.with_event_exchange(...)` so runner transcripts can be advanced immutably one event at a time.
- Added `ExecRuntimeRequestSequence.append_event_input_to_runner_transcript(...)` to convert a new event input into an event exchange and return the updated transcript.
- Covered the incremental startup-to-shutdown path, preserving request id `3` for unsubscribe and leaving the original transcript unchanged.


### Turn 127 - exec runner transcript append until break

- Added `ExecRuntimeRequestSequence.append_event_inputs_to_runner_transcript(...)` to advance a runner transcript across multiple event inputs until the transcript reaches break state.
- This captures the core runner loop rule that no further server events should be processed after shutdown/break has been requested.
- Added coverage showing a late event after shutdown is ignored, preserving only the first shutdown notification and unsubscribe request id `3`.


### Turn 128 - exec runner transcript one-shot stop-on-break

- Updated `ExecRuntimeRequestSequence.runner_transcript_from_responses(...)` to reuse the incremental append-until-break path.
- This keeps one-shot transcript construction consistent with the real runner loop: events after shutdown/break are ignored and do not consume further request ids.
- Added coverage showing a late event after an `initiate_shutdown` event is not processed by the one-shot transcript builder.


### Turn 129 - exec runner transcript startup requests

- Added `startup_client_requests` and `all_client_requests` views on `ExecRuntimeRunnerTranscript`.
- The transcript now distinguishes startup initial requests from action-derived client requests while still offering a combined ordered request view for runner auditing.
- Added coverage for `turn/start` request id `2` and shutdown `thread/unsubscribe` request id `3` appearing in order.


### Turn 130 - exec runner transcript bootstrap requests

- Extended `ExecRuntimeRunnerTranscript` with `bootstrap_client_requests` and `initial_client_requests` views.
- `startup_client_requests` now reflects the complete startup request order when the transcript is constructed from a sequence: `thread/start` followed by `turn/start`.
- `all_client_requests` now audits the full startup-to-shutdown request order as request ids `1`, `2`, and `3`.


### Turn 131 - exec runner transcript mapping output

- Added `to_mapping()` on `ExecRuntimeActionSummary` and `ExecRuntimeRunnerTranscript` so runner execution traces can be audited or compared without inspecting internal dataclass fields.
- The transcript mapping preserves bootstrap, initial, action-derived, and full client request order, plus notifications, config summaries, warnings, break state, and action summaries.
- Added coverage for the startup-to-shutdown mapping showing request ids `1`, `2`, and `3` in order.


### Turn 132 - exec runner transcript agent messages

- Added agent-message extraction to `ExecRuntimeActionSummary` from processed turn notifications.
- Added `ExecRuntimeRunnerTranscript.agent_messages` and `final_agent_message` so runner code can discover final answer text without reparsing raw notifications.
- Extended mapping output and tests to include `agentMessages` and `finalAgentMessage`, preserving the final message from multiple agent-message items.


### Turn 133 - exec runner result final message

- Added `ExecRuntimeRunnerResult` and `exec_runtime_runner_result(...)` to package a transcript into a final runner-facing result.
- Added `ExecRuntimeRequestSequence.runner_result_from_responses(...)` so startup responses and event inputs can produce a result with `final_message`, completion state, request count, and full transcript mapping.
- Added coverage for final answer extraction and request trace order `thread/start`, `turn/start`, `thread/unsubscribe`.


### Turn 134 - exec runner final message output plan

- Added `ExecRuntimeFinalMessageOutputPlan` and `ExecRuntimeRunnerResult.final_message_output_plan(...)` to model stdout/TTY/last-message-file decisions for the final answer.
- The output plan reuses existing final-message terminal rules instead of duplicating Rust behavior ad hoc.
- Added coverage for redirected stdout output, TTY output when not already rendered, suppression after rendering, and last-message contents.


### Turn 135 - exec runner final message CLI output plan

- Extended `ExecRuntimeFinalMessageOutputPlan` with `last_message_path` and `should_write_last_message` so CLI output-last-message behavior can be represented without doing file I/O.
- Added `ExecRuntimeRunnerResult.final_message_output_plan_from_cli(...)` to derive final-message output decisions from `ExecCli.last_message_file`.
- Added coverage for suppressing duplicate TTY output while still capturing last-message file contents and path.


### Turn 136 - exec final message output apply helper

- Added `apply_exec_runtime_final_message_output_plan(...)` to execute a final-message output plan against stdout, stderr/TTY, and an optional last-message file.
- The helper delegates last-message file writing to the existing `handle_last_message(...)` path to preserve current exec event-processor behavior.
- Added coverage with in-memory stdout/stderr streams and a temporary last-message file.


### Turn 137 - exec runner apply final message from CLI

- Added `ExecRuntimeRunnerResult.apply_final_message_output_from_cli(...)` to combine CLI-derived output planning with final-message output application.
- The helper returns the applied output plan so runner code can still audit stdout/TTY/file decisions after side effects.
- Added coverage using in-memory stdout/stderr streams and a temporary `--output-last-message` target.


### Turn 138 - exec runner final message fallback parity

- Updated runner transcript final-message extraction to reuse `final_message_from_notification_items(...)`, matching the existing event-processor behavior for agent messages and plan-text fallback.
- Added `final_messages` and `final_message` transcript views while preserving narrower `agent_messages` and `final_agent_message` views.
- `ExecRuntimeRunnerResult.final_message` now follows the broader final-message rule, and coverage verifies plan-text fallback when no agent message is present.


### Turn 139 - exec runner failed turn clears final message

- Updated transcript-level final-message aggregation to be status-aware, matching event-processor behavior where failed/interrupted turns clear stale final output.
- Action summaries still expose raw agent messages for audit, but `ExecRuntimeRunnerResult.final_message` now clears after failed or interrupted turn notifications.
- Added coverage where a completed turn produces a stale answer and a later failed turn clears the final result.


### Turn 140 - exec failed final message output does not overwrite

- Changed final-message output planning so `--output-last-message` is not written when the runner result has no final message.
- This preserves Rust behavior where failed/interrupted turns do not overwrite a previous last-message file with empty output.
- Added coverage proving a failed turn leaves an existing last-message file unchanged and produces no stdout/stderr output.


### Turn 141 - exec runner turn status result

- Added transcript-level `turn_statuses` and `terminal_turn_status` derived from event exchange notifications.
- Added runner result `terminal_turn_status` and `succeeded` so CLI result handling can distinguish loop break/completion from turn success.
- Added coverage for completed turns reporting success and failed turns reporting non-success, with mapping output updated accordingly.


### Turn 142 - exec runner result exit code

- Added `ExecRuntimeRunnerResult.exit_code` to expose CLI-ready success/failure process semantics from the turn status.
- Successful completed turns now map to exit code `0`; failed/interrupted/non-success states map to `1`.
- Extended result mapping and status tests to include exit-code output.


### Turn 143 - exec runner interrupted turn result

- Added result-level coverage for interrupted turns, matching the failed-turn path for success, exit-code, and final-message clearing semantics.
- The runner result now has explicit regression coverage showing interrupted terminal status maps to `succeeded = False`, `exit_code = 1`, and no final message.
- This keeps future CLI runner work from treating interrupted turns as successful loop completion.


### Turn 144 - exec runner result outcome

- Added `ExecRuntimeRunnerResult.outcome` to normalize terminal turn status into CLI-friendly result categories.
- Outcomes now map completed turns to `success`, failed turns to `failed`, interrupted turns to `interrupted`, and missing/unknown terminal status to `incomplete`.
- Extended result mapping and tests so CLI callers can use outcome without reinterpreting raw protocol status values.


### Turn 145 - exec runner CLI completion result

- Added `ExecRuntimeCliCompletion` to package a runner result, applied final-message output plan, normalized outcome, and exit code for CLI callers.
- Added `ExecRuntimeRunnerResult.apply_cli_completion(...)` so final-message output can be applied and returned together with the process-facing result metadata.
- Added coverage for successful completion writing stdout and `--output-last-message` while returning exit code `0` and outcome `success`.


### Turn 146 - exec sequence CLI completion from responses

- Added `ExecRuntimeRequestSequence.cli_completion_from_responses(...)` to combine response/event transcript construction, runner result derivation, final-message output application, and CLI completion packaging.
- The method provides a runner-facing one-step bridge from startup responses and event inputs to `ExecRuntimeCliCompletion`.
- Added coverage for stdout output, `--output-last-message` file writing, success outcome, and exit code `0`.


### Turn 147 - exec CLI completion direct result properties

- Added direct `completed`, `succeeded`, `final_message`, and `terminal_turn_status` properties on `ExecRuntimeCliCompletion`.
- Extended CLI completion mapping so callers can read final process-facing result fields without drilling into the nested runner result.
- Added coverage for success and failed completions, including failed completion preserving an existing last-message file.


### Turn 148 - exec CLI completion JSON payload

- Added `ExecRuntimeCliCompletion.json_payload` as a compact, JSON-mode-friendly completion payload.
- The payload exposes outcome, exit code, success/completion booleans, terminal turn status, final message, and output plan without requiring callers to inspect nested result/transcript structures.
- Extended success and failure completion coverage to assert JSON payload shape and values.


### Turn 149 - exec CLI completion JSON payload text

- Added `ExecRuntimeCliCompletion.json_payload_text()` to serialize the compact JSON payload with Python standard-library `json`.
- The output uses `ensure_ascii=False` and compact separators so future `codex exec --json` code can print a stable one-line JSON payload.
- Added coverage proving the text is parseable JSON and preserves outcome, exit code, final message, success state, and output-plan data.


### Turn 150 - exec CLI completion JSON payload apply

- Added `ExecRuntimeCliCompletion.apply_json_payload_output(...)` to write the compact JSON payload as one stdout line and return the written text.
- This gives future `codex exec --json` CLI code a small standard-library-only output boundary.
- Added coverage proving stdout receives exactly the JSON payload plus newline and that the payload remains parseable.


### Turn 151 - exec sequence JSON CLI completion

- Added `ExecRuntimeRequestSequence.cli_json_completion_from_responses(...)` for JSON-mode CLI completion.
- The helper suppresses normal final-message stdout/TTY output, applies any `--output-last-message` file write, and writes exactly one JSON payload line to stdout.
- Added coverage proving JSON stdout is parseable and exclusive while last-message file output still occurs.


### Turn 152 - exec sequence completion dispatch

- Added `ExecRuntimeRequestSequence.completion_from_responses(...)` to dispatch between normal and JSON CLI completion paths using `ExecCli.json`.
- The helper gives future CLI runner code one response/event-to-completion entry point while preserving separate normal and JSON output semantics.
- Added coverage for non-JSON final-message stdout output and JSON one-line payload output.


### Turn 153 - exec JSON completion failed path

- Added coverage for `ExecRuntimeRequestSequence.completion_from_responses(...)` when `ExecCli.json` is true and the turn fails.
- The JSON failure path now has regression coverage proving stdout receives exactly one JSON payload line, exit code is `1`, final message is null, and existing `--output-last-message` contents are preserved.
- This keeps JSON-mode failure behavior separate from normal final-message stdout output.


### Turn 154 - exec CLI completion ready-to-exit

- Added `ExecRuntimeCliCompletion.ready_to_exit` to expose whether the completion represents a terminal event-loop state suitable for returning from the CLI process.
- The property mirrors `completed`, keeping it distinct from `succeeded`, `outcome`, and `exit_code`.
- Added coverage for a startup-only incomplete completion where no break has occurred, producing `ready_to_exit = False` and outcome `incomplete`.


### Turn 155 - exec JSON payload ready-to-exit

- Added `readyToExit` to `ExecRuntimeCliCompletion.json_payload` so JSON-mode CLI output exposes terminal loop readiness directly.
- Extended existing success and failure JSON payload assertions to cover `readyToExit`.
- This keeps compact JSON output aligned with the fuller completion mapping.

### Turn 156 - exec CLI completion terminal readiness

- Refined `ExecRuntimeCliCompletion.ready_to_exit` so CLI completion is ready whenever a terminal turn status is present, covering failed and interrupted terminal outcomes as well as successful completion.
- Kept non-terminal/no-break completions pending, preserving runner-loop behavior for in-progress transcripts.
- Validated with `python -m unittest tests.test_exec_config_plan tests.test_exec_session`.

### Turn 157 - local HTTP write_stdin output names

- Preserved the `write_stdin` tool name on local HTTP shell-tool output mappings for approval-required, unknown-session, successful session write, and unavailable-session branches.
- This keeps local runtime trace/JSON metadata aligned with the named `apply_patch` output path without changing Responses function-call-output conversion semantics.
- Validated with `python -m unittest tests.test_exec_local_runtime`.

### Turn 158 - unified exec numeric bounds

- Tightened unified exec argument parsing around Rust numeric types: `yield_time_ms` now must fit `u64`, `max_output_tokens` must fit `usize`, and `write_stdin.session_id` must fit `i32`.
- Added regression coverage for negative and overflowing unified exec/write_stdin arguments.
- Made unified exec shell-path expectations platform-aware, matching the existing shell tests' `Path` rendering behavior on Windows.
- Validated with `python -m unittest tests.test_core_unified_exec_handler` and `python -m unittest tests.test_core_shell`.

### Turn 159 - shell spec defer-loading parity

- Added explicit `defer_loading: None` to core shell function tool specs, matching Rust `ResponsesApiTool { defer_loading: None }` and the existing local HTTP tool specs.
- Extended shell spec coverage for `defer_loading` and `additionalProperties: False` on exec, write_stdin, and request_permissions tools.
- Validated with `python -m unittest tests.test_core_shell_spec` and `python -m unittest tests.test_core_unified_exec_handler`.

### Turn 160 - request_permissions tool spec and filesystem helper parity

- Added explicit `defer_loading: None` to the core `request_permissions` handler tool spec, matching the Rust shell-spec-backed `ResponsesApiTool` shape.
- Fixed `request_profile_with_file_system(...)` to construct current protocol `FileSystemPermissions` via `FileSystemSandboxEntry` values instead of stale `read`/`write` constructor kwargs.
- Made the relative-path normalization test use a platform-absolute cwd so it validates correctly on Windows as well as POSIX.
- Validated with `python -m unittest tests.test_core_request_permissions_handler` and `python -m unittest tests.test_core_shell_spec`.

### Turn 161 - request_permissions normalization parity

- Implemented the request-permissions normalization step that Rust performs via `normalize_additional_permissions`: empty nested network/file-system profiles are dropped, duplicate file-system entries are removed, and non-deny glob permissions are rejected.
- Added regression coverage for empty nested profiles, duplicate file-system entries, and invalid glob read grants.
- Validated with `python -m unittest tests.test_core_request_permissions_handler`.
- Note: an exploratory adjacent run of `python -m unittest tests.test_protocol_permission_models` still has unrelated protocol-model failures around legacy access parsing and sandbox policy roundtrips; this turn did not change that layer.

### Turn 162 - permission model legacy parsing cleanup

- Fixed `FileSystemSandboxEntry.from_mapping(...)` so non-string `access` values surface the Rust-shaped type error instead of being coerced through `str(...)`.
- Fixed `FileSystemSandboxPolicy.from_mapping(...)` so omitted `entries` for restricted policies preserves the dataclass default root-read entry, while explicit `entries: []` still remains empty.
- This resolves the adjacent protocol permission model failures found while tightening request-permissions normalization.
- Validated with `python -m unittest tests.test_protocol_permission_models` and `python -m unittest tests.test_core_request_permissions_handler`.

### Turn 163 - request_permissions path canonicalization

- Extended request-permissions normalization to canonicalize plain absolute file-system permission paths when possible, while preserving logical paths that pass through nested symlink ancestors and preserving paths when normalization fails.
- This mirrors the Rust `normalize_additional_permissions` use of `canonicalize_preserving_symlinks` closely enough for the Python stdlib implementation.
- Added regression coverage for ordinary path canonicalization through `..` segments.
- Validated with `python -m unittest tests.test_core_request_permissions_handler` and `python -m unittest tests.test_protocol_permission_models`.

### Turn 164 - request_permissions canonicalization regression coverage

- Added regression coverage proving request-permissions normalization deduplicates file-system permission entries after path canonicalization.
- Added symlink-aware coverage for preserving logical paths underneath nested symlink ancestors, matching Rust's `canonicalize_preserving_symlinks` intent.
- This turn only tightened coverage around the existing normalization implementation.

### Turn 165 - request_permissions glob and special normalization coverage

- Added regression coverage proving request-permissions normalization preserves deny glob entries and special filesystem paths unchanged, matching Rust `normalize_additional_permissions` behavior.
- Fixed the test import surface for `FileSystemSpecialPath`.
- Validated with `python -m unittest tests.test_core_request_permissions_handler tests.test_protocol_permission_models`.

### Turn 166 - effective filesystem policy merge parity

- Tightened `effective_file_system_sandbox_policy(...)` so additional filesystem permissions only merge into restricted filesystem policies, matching Rust `merge_file_system_policy_with_additional_permissions`.
- Added regression coverage for deduplicating additional filesystem entries and for leaving unrestricted/external sandbox policies unchanged.
- Cleaned adjacent tool-runtime test imports and platform-aware shell path expectations needed by this parity slice.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 167 - effective glob scan depth parity

- Ported Rust's `merge_glob_scan_max_depth` semantics into the Python tool runtime filesystem-policy transform.
- Additional filesystem permissions now merge deny-glob scan depths only when deny glob entries are present, preserve unbounded scans when either side is unbounded, and choose the larger bound when both sides are bounded.
- Added regression coverage for bounded-depth merging and unbounded-depth preservation.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 168 - permission profile glob depth merge parity

- Applied the same Rust `merge_glob_scan_max_depth` semantics to `merge_permission_profiles(...)` in the shared handler helpers.
- Permission-profile filesystem merges now ignore depths without deny-glob entries, preserve unbounded deny-glob scans, and use the larger bound only when both sides are bounded.
- Added handler-helper regression coverage for bounded and unbounded deny-glob depth merges.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 169 - permission profile intersection foundation

- Added a Python `intersect_permission_profiles(...)` helper to the shared handler utilities, following the Rust policy-transform shape for network intersection and core filesystem grant filtering.
- Implemented standard-library-only path grant coverage checks, cwd-dependent project-root/glob materialization, constraining deny-entry retention, and deny-glob scan-depth carryover for the accepted intersection.
- Re-exported the helper from `pycodex.core` and added regression coverage for accepting child-path grants under a requested cwd and dropping broader cwd grants for narrower child requests.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 170 - intersection deny-glob regression coverage

- Added handler-helper regression coverage for rejecting concrete filesystem grants matched by requested deny glob permissions.
- Added coverage proving relative deny glob permissions are materialized against the request cwd before being reused later, matching Rust's `materialize_cwd_dependent_entry` behavior.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 171 - deny glob direct-child matching parity

- Adjusted the Python deny-glob matcher used by `intersect_permission_profiles(...)` so `**/` also matches zero directory levels, matching the Rust regression expectation for patterns such as `**/*.env`.
- This keeps concrete grants like `cwd/token.env` constrained by requested deny globs after cwd-relative pattern resolution.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 172 - intersection glob scan depth coverage

- Added end-to-end handler-helper coverage proving `intersect_permission_profiles(...)` carries the granted bounded deny-glob scan depth when retained deny globs constrain accepted grants.
- Added matching coverage for granted unbounded deny-glob scans, ensuring the intersected permission profile remains unbounded.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 173 - preapproved permissions intersection parity

- Updated `permissions_are_preapproved(...)` to match Rust's intersection-based comparison: materialize effective permissions via self-intersection, then require the effective/granted intersection to match that materialized profile.
- Added regression coverage proving relative deny-glob grants remain preapproved after materialization and merge, matching the Rust handler test.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 174 - request_permissions response normalization parity

- Added `normalize_request_permissions_response(...)` to the shared handler helpers, mirroring Rust session response normalization for request-permissions grants.
- Strict auto-review responses with session scope now normalize to an empty turn-scoped grant, and non-empty responses are intersected with the originally requested permissions before recording/use.
- Re-exported the helper from `pycodex.core` and added regression coverage for strict session-scope rejection and requested/granted intersection.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 175 - request_permissions handler response normalization

- Wired `normalize_request_permissions_response(...)` into the Python `RequestPermissionsHandler` so callback/client responses are normalized before being serialized back to the model.
- Added handler-level coverage proving a broader filesystem grant is removed when it exceeds the originally requested filesystem permission, while matching network permission remains.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 176 - delegate request_permissions response normalization

- Wired `normalize_request_permissions_response(...)` into the delegated sub-agent request-permissions bridge so parent-session responses are normalized before being submitted back to the child Codex.
- Added delegate-level coverage proving broader filesystem grants from the parent response are removed while matching network grants survive.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 177 - strict auto-review response entrypoint coverage

- Added request-permissions handler coverage proving strict auto-review responses cannot remain session scoped and normalize to an empty turn grant at the actual tool-handler entrypoint.
- Added matching delegated sub-agent coverage for the same strict auto-review/session-scope normalization path.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 178 - request_permissions grant recording helper

- Added `record_granted_request_permissions(...)` to shared handler helpers, mirroring Rust's scope-based recording behavior for normalized request-permissions responses.
- Turn-scoped grants now record onto a provided turn state and enable strict auto-review when requested; session-scoped grants record onto the provided session.
- Re-exported the helper from `pycodex.core` and added regression coverage for turn strict-auto-review recording and session-scope recording.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 179 - async grant-recording fallback parity

- Tightened the fallback path in `record_granted_request_permissions(...)` so async `granted_permissions()` accessors are awaited before merging a new grant.
- Added regression coverage for merging a session-scoped response with an existing async session grant when no explicit `record_granted_permissions(...)` method is available.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 180 - in-memory session grant state

- Extended `InMemoryCodexSession` with session-scoped and turn-scoped granted permission state plus strict auto-review state, matching the Rust session/turn-state split used by request-permissions grants.
- Added async accessors and recorders for session and turn grants, using the existing Rust-shaped permission merge helper.
- Updated `record_granted_request_permissions(...)` so turn-scoped writes prefer a `record_granted_turn_permissions(...)` target method before falling back to generic recording.
- Added runtime coverage for recording session grants, turn grants, and strict auto-review on the in-memory session.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 181 - in-memory turn grant lifecycle

- Updated `InMemoryCodexSession.new_default_turn()` to clear turn-scoped granted permissions and strict auto-review state while preserving session-scoped grants.
- Added runtime coverage proving new turns reset turn-local permission state but keep session grants available.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 182 - in-memory request_permissions flow

- Added an injectable `request_permissions_callback` and `request_permissions_for_cwd(...)` method to `InMemoryCodexSession`, matching the session-like API used by delegated request-permissions handling.
- The in-memory session now normalizes callback responses with `normalize_request_permissions_response(...)`, records normalized grants by scope, and returns the normalized response.
- Added runtime coverage proving a callback response is intersected with the original request and recorded as a session grant.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 183 - in-memory turn-scoped request_permissions coverage

- Added runtime coverage proving `InMemoryCodexSession.request_permissions_for_cwd(...)` records turn-scoped grants into turn state rather than session state.
- The same coverage verifies strict auto-review activation for turn-scoped request-permissions responses.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 184 - in-memory strict session response coverage

- Added runtime coverage proving `InMemoryCodexSession.request_permissions_for_cwd(...)` normalizes strict auto-review session-scoped responses to an empty turn grant.
- The coverage verifies no session grant, turn grant, or strict auto-review state is recorded for that rejected response.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 185 - in-memory async mapping response coverage

- Added runtime coverage proving `InMemoryCodexSession.request_permissions_for_cwd(...)` accepts an async callback that returns a JSON-like response mapping.
- The mapping response is parsed, normalized, recorded as a turn grant, and activates strict auto-review when requested.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 186 - in-memory grant application coverage

- Added runtime coverage proving grants recorded on `InMemoryCodexSession` are consumed by `apply_granted_turn_permissions(...)` for later shell-like commands.
- The coverage verifies recorded session grants automatically switch default sandbox permissions to `with_additional_permissions` and surface the granted permission profile.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 187 - in-memory turn grant application coverage

- Added runtime coverage proving turn-scoped grants recorded on `InMemoryCodexSession` are consumed by `apply_granted_turn_permissions(...)` for later shell-like commands in the same turn.
- The coverage verifies the helper upgrades default sandbox permissions to `with_additional_permissions`, surfaces the turn grant, and does not require a session-scoped grant.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 188 - in-memory turn grant expiry coverage

- Added runtime coverage proving turn-scoped grants recorded on `InMemoryCodexSession` stop affecting `apply_granted_turn_permissions(...)` after `new_default_turn()`.
- The coverage verifies later shell-like commands return to default sandbox permissions once the turn-local grant state is cleared.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 189 - in-memory session grant persistence coverage

- Added runtime coverage proving session-scoped grants recorded on `InMemoryCodexSession` continue to affect `apply_granted_turn_permissions(...)` after `new_default_turn()`.
- This mirrors the turn-grant expiry coverage and preserves Rust's distinction between session state and active turn state.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 190 - in-memory empty request_permissions response coverage

- Added runtime coverage proving `InMemoryCodexSession.request_permissions_for_cwd(...)` returns an empty turn-scoped response and records no grants when no request-permissions callback is configured.
- The coverage also verifies strict auto-review remains disabled for the empty response path.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 191 - in-memory cancelled request_permissions response coverage

- Added runtime coverage proving `InMemoryCodexSession.request_permissions_for_cwd(...)` treats a callback returning `None` as an empty response.
- The coverage verifies no session grant, turn grant, or strict auto-review state is recorded for that cancelled/empty response path.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 192 - in-memory request_permissions cwd fallback parity

- Updated `InMemoryCodexSession.request_permissions_for_cwd(...)` to compute an effective cwd before invoking the callback, falling back to the session cwd when the caller passes `None`.
- The same effective cwd is used for callback invocation and response normalization.
- Added runtime coverage proving callbacks receive the session cwd when no explicit cwd is supplied.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 193 - in-memory preapproved inline grant coverage

- Added runtime coverage proving recorded session grants can preapprove matching explicit inline additional permissions through `apply_granted_turn_permissions(...)`.
- The coverage verifies sandbox permissions remain `with_additional_permissions`, the effective permission profile is preserved, and `permissions_preapproved` is set.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 194 - in-memory broader inline grant rejection coverage

- Added runtime coverage proving a recorded narrower grant does not preapprove a broader explicit inline filesystem permission request.
- The coverage verifies `apply_granted_turn_permissions(...)` preserves the requested profile but leaves `permissions_preapproved` false when the recorded grant does not cover it.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 195 - in-memory deny-glob preapproval coverage

- Added runtime coverage proving a recorded session grant with project-root write plus relative deny-glob constraints can preapprove a matching explicit inline additional-permissions request.
- This carries the Rust relative deny-glob materialization/preapproval behavior through the in-memory session grant recording and later permission-application path.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 196 - in-memory strict auto-review accessor

- Added an async `strict_auto_review()` accessor to `InMemoryCodexSession` so orchestration code can read turn-local strict auto-review state through a session-like method.
- Extended runtime coverage to prove strict state is readable after a strict turn grant and clears through `new_default_turn()`.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 197 - strict auto-review session resolver

- Added `session_strict_auto_review(...)` to shared handler helpers so tool orchestration code can read strict auto-review state from either an async `strict_auto_review()` method or a simple `strict_auto_review_enabled` attribute.
- Re-exported the resolver from `pycodex.core` and added regression coverage for async-method, bool-attribute, and missing-session cases.
- Validation pending explicit user approval; no tests were run in this turn.

### Turn 198 - session-aware orchestrator plan helper

- Added `build_tool_orchestrator_plan_for_session(...)`, an async wrapper that reads strict auto-review state from a session-like object and passes it into the existing pure `ToolOrchestratorPlan.build(...)` logic.
- Re-exported the helper from `pycodex.core` and added orchestrator coverage proving session strict-auto-review state turns a normally skipped approval requirement into a guardian-backed requested approval.
- Validation pending explicit user approval; no tests were run in this turn.

## Turn 221 - settings update environment integration

- Integrated environment-context diff generation into `build_settings_update_items` when a shell is supplied, while preserving the explicit `contextual_user_message` override path.
- Added unit coverage for the settings-update aggregator emitting a contextual user environment update from previous and next turn context.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 222 - context update parity flags

- Matched Rust `build_permissions_update_item` behavior by honoring `next.config.include_permissions_instructions` before comparing permission profile or approval policy changes.
- Completed the settings-update aggregator parity path so passing `shell` lets `build_settings_update_items` emit the environment contextual user item itself, preserving explicit contextual user overrides.
- Extended context-update tests for the permissions include flag and shell-driven environment update assembly; adjusted path assertions to use platform-rendered `Path` strings.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 223 - in-memory session context update integration

- Integrated `build_settings_update_items` into `InMemoryCodexSession.record_context_updates_and_set_reference_context_item`, so the lightweight core session now records model-visible context update items before refreshing its reference context.
- Added minimal turn-context fields, defaults, feature/config shims, approval-policy wrapping, and `TurnContextItem` construction to support Rust-like settings diffs without third-party dependencies.
- Added session-runtime coverage for establishing a first reference context and emitting an environment contextual user update when the next turn changes cwd.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 224 - session reference context accessor

- Added `InMemoryCodexSession.reference_context_item()` so the lightweight session exposes the stored reference `TurnContextItem` through the same shape expected by thread-level injection code.
- Added session-runtime coverage for the reference context lifecycle: initially absent, then populated after recording context updates for a default turn.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 225 - in-memory no-new-turn injection surface

- Added `InMemoryCodexSession.inject_no_new_turn` to mirror the Rust session path that records injected response items without starting a new active turn, creating a default turn context when none is supplied.
- Added `InMemoryCodexSession.flush_rollout` with a lightweight flush counter so thread-level code can drive the same session method shape.
- Added session-runtime coverage for mapping-based no-new-turn injection, history recording, and rollout flush counting.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 226 - thread injection integration coverage

- Added thread-level coverage proving `CodexThread.inject_response_items` works against the real `InMemoryCodexSession` surface rather than only a dummy session.
- The integration case now exercises reference-context initialization, no-new-turn item recording, and rollout flush counting through the same method names used by the Rust thread/session path.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 227 - initial context injection in in-memory session

- Changed `InMemoryCodexSession.record_context_updates_and_set_reference_context_item` to inject a minimal full initial context when no reference context exists, matching Rust's first-turn behavior instead of treating the first turn as a diff-only update.
- The initial context slice now records permissions instructions as a developer message and environment context as a contextual user message; user instructions remain handled by the existing turn prompt insertion path to avoid duplicate AGENTS.md rendering in the current Python request builder.
- Updated session-runtime expectations for first-turn prompt ordering and for subsequent cwd diff emission after the initial baseline is established.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 228 - initial context model-switch instructions

- Reused `build_model_instructions_update_item` inside the in-memory session initial context builder so a missing reference context still prepends model-switch guidance when previous turn settings indicate a model change.
- Added lightweight async `previous_turn_settings` and `set_previous_turn_settings` accessors to mirror Rust session state used by resume/rollback and initial context injection paths.
- Added session-runtime coverage for initial-context model-switch ordering before permissions instructions.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 229 - initial context realtime instructions

- Reused `build_initial_realtime_item` inside the in-memory session initial context builder so missing-reference full-context injection now includes realtime start/end developer guidance.
- Preserved Rust developer-section ordering for this core slice: model-switch guidance, realtime guidance, then permissions instructions.
- Added session-runtime coverage for initial realtime start and for realtime end derived from stored previous turn settings when no reference context exists.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 230 - initial context developer ordering and collaboration mode

- Corrected the in-memory session initial developer-section ordering to match the Rust core slice: model-switch guidance first, permissions instructions before collaboration/realtime updates.
- Added initial collaboration-mode developer instructions when enabled and non-empty, reusing `CollaborationModeInstructions` instead of duplicating rendering logic.
- Updated session-runtime coverage for realtime ordering and added coverage for collaboration instructions appearing after permissions.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 231 - initial developer instructions in in-memory session

- Added `developer_instructions` to the in-memory session and turn-context snapshot so core developer policy can flow through the same first-context path as Rust.
- Initial context injection now places non-empty developer instructions after permissions instructions and before collaboration/realtime guidance.
- Added session-runtime coverage for developer-instructions ordering relative to permissions and collaboration mode.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 232 - initial personality spec in in-memory session

- Added a `personality_feature_enabled` switch to the in-memory session and wired initial full-context injection to render personality spec instructions when enabled, a personality is set, and the current model has not baked the personality into base instructions.
- Reused `personality_message_for` and `PersonalitySpecInstructions` so rendering matches existing context-update behavior.
- Added session-runtime coverage for personality spec injection and for skipping the extra personality spec when model instructions already bake it into base instructions.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 233 - in-memory reference context replacement surface

- Added `InMemoryCodexSession.set_reference_context_item` so lightweight session state can clear or restore the current `TurnContextItem` baseline, matching the state operation used by Rust resume/rollback/compaction paths.
- Added `InMemoryCodexSession.replace_history` to replace prompt-visible history while setting the associated reference context item.
- Added session-runtime coverage for clearing the reference baseline and replacing history with a restored baseline.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 234 - in-memory compacted history replacement

- Added `InMemoryCodexSession.replace_compacted_history` to mirror Rust's compaction install surface: replace prompt-visible history, restore the reference context baseline, and retain the persisted `CompactedItem` record.
- Added `compacted_items` state and normalization for `CompactedItem` mappings so remote compaction install plans can feed the in-memory session directly.
- Added session-runtime coverage for compacted-history replacement with a mapping-shaped compacted item.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 235 - remote compaction v2 install application

- Corrected `RemoteCompactionV2InstallPlan.reference_context_item` to use `TurnContextItem`, matching Rust's `turn_context.to_turn_context_item()` baseline instead of a prompt `ResponseItem`.
- Added `apply_remote_compaction_v2_install_plan` to apply a generated install plan to any session exposing `replace_compacted_history`.
- Exported the helper from `pycodex.core` and added coverage showing a remote compaction v2 plan installs into `InMemoryCodexSession`, replacing history, restoring the baseline, and retaining the compacted item.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 236 - remote compaction install application

- Added `RemoteCompactionInstallPlan`, `build_remote_compaction_install_plan`, and `apply_remote_compaction_install_plan` for the non-v2 remote compaction path, paralleling the v2 install/apply surface.
- The install plan uses `TurnContextItem` as the restored reference baseline, matching Rust's `turn_context.to_turn_context_item()` behavior for before-last-user-message injection.
- Exported the helpers from `pycodex.core` and added coverage applying a remote compaction install plan into `InMemoryCodexSession`.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 237 - remote compaction success plan

- Added `build_remote_compaction_success_plan` for the non-v2 remote compaction path, combining compacted-history filtering, optional initial-context injection, and install-plan construction into one Rust-shaped helper.
- Exported the helper from `pycodex.core` and covered the success path that drops stale developer/trigger items, injects refreshed context before the latest real user message, and prepares checkpoint/compacted replacement payloads.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 238 - session personality diff integration

- Aligned `InMemoryCodexSession.record_context_updates_and_set_reference_context_item` with Rust `build_settings_update_items` by passing the session personality feature flag through existing-reference settings diffs instead of disabling personality updates.
- Added session-runtime coverage proving a personality change after the reference baseline emits a developer `PersonalitySpecInstructions` update when the model slug is unchanged.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 239 - in-memory session feature propagation

- Added an injectable `features` field to `InMemoryCodexSession` so lightweight session turns can carry the same feature-gate object used by Rust turn context construction.
- Updated `new_default_turn` to preserve supplied features and fall back to `_NoFeatures` only when the session has no feature state.
- Added session-runtime coverage proving a new turn inherits the session feature object.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 240 - in-memory turn id baseline

- Added `turn_id` to `InMemoryCodexSession` and `InMemoryTurnContext`, then persisted it into the generated `TurnContextItem` baseline.
- This moves the lightweight session closer to Rust `TurnContext::to_turn_context_item`, which stores the turn sub-id in persisted rollout/context metadata.
- Added session-runtime coverage proving the reference context preserves the session turn id.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 241 - in-memory reasoning baseline

- Added `reasoning_effort` and `reasoning_summary` to `InMemoryCodexSession` and `InMemoryTurnContext`.
- Persisted both fields into generated `TurnContextItem` baselines, matching the Rust `TurnContext::to_turn_context_item` shape where `effort` and `summary` are stored with rollout/context metadata.
- Added session-runtime coverage proving the reference context preserves reasoning effort and summary values.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 242 - in-memory sandbox baseline

- Added injectable `sandbox_policy` and `file_system_sandbox_policy` fields to `InMemoryCodexSession` and `InMemoryTurnContext`.
- Stopped hardcoding generated `TurnContextItem` baselines to `danger_full_access`; the baseline now preserves the turn sandbox policy and optional split filesystem sandbox policy.
- Added session-runtime coverage proving reference context snapshots retain both sandbox policy fields.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 243 - in-memory network baseline normalization

- Normalized generated `TurnContextItem.network` values to `TurnContextNetworkItem` instead of passing arbitrary session network-like objects through unchanged.
- Preserved the existing environment-context rendering path, which still converts network data to `NetworkContext` for model-visible context.
- Added session-runtime coverage proving a network-like object is stored in the reference context as a protocol `TurnContextNetworkItem`.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 244 - in-memory approvals reviewer propagation

- Added injectable `approvals_reviewer` state to `InMemoryCodexSession`, defaulting to `ApprovalsReviewer.USER`.
- Updated `new_default_turn` to carry the session reviewer into turn config instead of hardcoding user review.
- Added session-runtime coverage proving `ApprovalsReviewer.AUTO_REVIEW` survives turn construction.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 245 - in-memory custom realtime start config

- Added `experimental_realtime_start_instructions` to `InMemoryCodexSession` and carried it into per-turn config.
- This lets initial and diff context updates render `RealtimeStartWithInstructions` through the same helper path Rust uses when custom realtime start instructions are configured.
- Added session-runtime coverage proving initial realtime context includes custom start instructions.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 246 - collaboration mode baseline jsonification

- Added lightweight JSON-shape normalization for collaboration-mode values stored in generated `TurnContextItem` baselines.
- The in-memory session still passes the original collaboration-mode object to context rendering, but persisted baseline metadata now avoids leaking arbitrary Python objects such as `SimpleNamespace`.
- Added session-runtime coverage proving a namespace-shaped collaboration mode is stored as a JSON-like mapping in the reference context.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 247 - session reasoning request fallback

- Updated the user-turn runtime request builder to fall back to `turn_context.reasoning_effort` and `turn_context.reasoning_summary` when explicit sampling arguments are not provided.
- This lets reasoning settings carried by `InMemoryCodexSession.new_default_turn` affect the actual Responses API request, not only the persisted `TurnContextItem` baseline.
- Added HTTP sampling coverage proving session reasoning settings populate the request `reasoning` payload.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 248 - session service tier request fallback

- Added `service_tier` to `InMemoryCodexSession` and `InMemoryTurnContext`.
- Updated the user-turn runtime request builder to fall back to `turn_context.service_tier` when no explicit sampling service tier is provided.
- Added HTTP sampling coverage proving a session service tier reaches the Responses API request payload.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 249 - per-turn config service tier propagation

- Added `service_tier` to the in-memory per-turn config object produced by `InMemoryCodexSession.new_default_turn`.
- This mirrors the Rust path where `per_turn_config.service_tier` is populated from session configuration and later read via `turn_context.config.service_tier`.
- Added session-runtime coverage proving `turn.config.service_tier` inherits the session service tier.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 250 - per-turn config reasoning propagation

- Added `model_reasoning_effort` and `model_reasoning_summary` to the in-memory per-turn config object produced by `InMemoryCodexSession.new_default_turn`.
- This mirrors the Rust path where `per_turn_config.model_reasoning_effort` and `per_turn_config.model_reasoning_summary` are populated from session configuration.
- Added session-runtime coverage proving `turn.config` inherits the session reasoning settings.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 251 - request fallback prefers turn config settings

- Updated the user-turn runtime request builder to prefer `turn_context.config.model_reasoning_effort`, `turn_context.config.model_reasoning_summary`, and `turn_context.config.service_tier` before falling back to top-level Python compatibility attributes.
- This aligns the lightweight request path with Rust's per-turn config shape while preserving existing callers that still attach settings directly to the turn context.
- Added turn-runtime coverage proving config-sourced reasoning and service tier defaults reach the built Responses API request.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 252 - HTTP enum request serialization

- Updated stdlib HTTP request serialization to convert Python `Enum` values to their wire strings before `json.dumps`.
- This keeps protocol enums such as `ReasoningEffort.HIGH` compatible with Rust serde's string-valued request payloads.
- Added HTTP transport coverage proving enum-valued reasoning settings serialize to JSON strings.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 253 - core request enum serialization

- Updated `serialize_responses_request` to recursively convert nested Python `Enum` values to their wire strings while preserving existing skip rules.
- This extends Rust-serde-like enum output to WebSocket/prepared request serialization, not only the stdlib HTTP transport edge.
- Added client coverage proving nested enum-valued reasoning settings serialize to JSON-compatible strings.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 254 - service tier request value normalization

- Updated `ModelClient` request construction to normalize service tier inputs before model support filtering.
- `ServiceTier.FAST` and legacy string `"fast"` now become the Rust request value `"priority"`; custom string tiers still pass through unchanged for model-specific support checks.
- Added client coverage proving enum and legacy fast service tier inputs produce `"priority"` in the Responses API request payload.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 255 - session service tier protocol values

- Relaxed `InMemoryCodexSession.service_tier` to accept protocol enum/request-value objects in addition to raw strings.
- This lets session state carry `ServiceTier.FAST` through per-turn config and rely on the existing `ModelClient` request-value normalization to emit `"priority"`.
- Added HTTP sampling coverage proving a session-level `ServiceTier.FAST` reaches the request payload as `"priority"`.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 256 - tool JSON enum serialization

- Updated `create_tools_json_for_responses_api` to recursively normalize tool mappings through the shared request-value serializer.
- Plain mapping tools with nested protocol enums now produce JSON-compatible wire strings instead of leaking Python enum objects into outbound tool specs.
- Added client coverage proving nested enum values inside tool metadata serialize to strings.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 257 - reasoning summary none enum handling

- Updated `build_reasoning` to inspect enum `.value` when deciding whether a reasoning summary setting represents `none`.
- This matches Rust's explicit `ReasoningSummary::None` branch and avoids depending on Python enum `str(...)` formatting.
- Added client coverage proving `ReasoningSummary.NONE` yields a request reasoning payload with `summary: None`.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 258 - session reasoning summary protocol values

- Relaxed `InMemoryCodexSession.reasoning_summary` to accept protocol enum values in addition to strings.
- This keeps Rust-like session configuration values accepted by Python session state while later request-building paths can normalize protocol values for outbound payloads.
- The `TurnContextItem.summary` compatibility field is documented separately below because Rust writes it as a fixed `auto` value.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 259 - session reasoning effort enum baseline

- Normalized `InMemoryCodexSession` reference-context `effort` through the same wire-value helper used for reasoning summaries.
- This keeps protocol enum inputs such as `ReasoningEffort.HIGH` persisted in `TurnContextItem` as Rust-compatible wire strings like `"high"` instead of Python enum objects.
- Added session-runtime coverage for enum reasoning effort baseline persistence.
- Validation not run this turn, per instruction to avoid extra verification unless explicitly requested.

## Turn 260 - turn context summary compatibility field

- Corrected generated `TurnContextItem.summary` baselines to always write `"auto"`, matching Rust's `TurnContext::to_turn_context_item` compatibility-only field.
- Kept reasoning summary on the session/config/request path rather than treating the legacy rollout baseline field as the source of truth.
- Updated session-runtime coverage so enum reasoning summaries prove the baseline writes the Rust-compatible `"auto"` value.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 261 - default collaboration mode baseline

- Added a Rust-like default `CollaborationMode` for in-memory turns when the session does not provide one explicitly.
- The generated default uses `ModeKind.DEFAULT` and the active model slug, so `TurnContextItem.collaboration_mode` is now present in baseline rollout metadata like Rust's `Some(self.collaboration_mode.clone())`.
- Added session-runtime coverage proving a default session writes the expected collaboration-mode JSON shape.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 262 - collaboration-mode reasoning effort inheritance

- Updated `InMemoryCodexSession.new_default_turn` to derive the effective reasoning effort from `collaboration_mode.settings.reasoning_effort` when no explicit session-level `reasoning_effort` is set.
- Default collaboration modes now carry the session reasoning effort in their settings, matching Rust's consolidation of model/reasoning under `SessionConfiguration.collaboration_mode`.
- Added session-runtime coverage proving an explicit collaboration-mode reasoning effort flows into both the turn context and per-turn config.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 263 - collaboration-mode model inheritance

- Added a lightweight model-info slug override for in-memory turns when `collaboration_mode.settings.model` differs from the current `model_info.slug`.
- The override preserves all other model-info attributes and methods by delegation while making the effective turn model, request model, and `TurnContextItem.model` follow the collaboration mode.
- Added session-runtime coverage proving the inherited collaboration model updates the turn slug and baseline while preserving existing model metadata.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 264 - turn request effective model info

- Updated the user-turn request runtime to build Responses API payloads with `turn_context.model_info` when the turn provides one.
- This makes collaboration-mode model inheritance affect the actual request model, not only prompt modality selection and `TurnContextItem` baseline metadata.
- Added turn-runtime coverage proving a stale caller-supplied `model_info` no longer overrides the effective turn model.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 265 - per-turn config effective model

- Added `model` to the in-memory per-turn config produced by `InMemoryCodexSession.new_default_turn`.
- The field is populated from the effective turn model info, so collaboration-mode model inheritance is visible through `turn.config.model` as well as request construction and rollout metadata.
- Extended session-runtime coverage to assert the inherited collaboration model reaches `turn.config.model`.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 266 - thread settings collaboration fallback

- Updated `CodexThread.thread_settings_update` to synthesize a default protocol `CollaborationMode` when the wrapped session does not expose Rust's callable `collaboration_mode()` surface.
- The fallback derives the model from the override, session-configured event, or session `model_info.slug`, then applies model/effort overrides through `CollaborationMode.with_updates`.
- Added thread-wrapper coverage proving `InMemoryCodexSession` can receive model/reasoning overrides as a protocol collaboration-mode update.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 267 - thread settings collaboration field access

- Extended the thread wrapper's optional call helper so no-argument lookups can read non-callable attributes as well as methods.
- This lets `CodexThread.thread_settings_update` use `InMemoryCodexSession.collaboration_mode` directly when present, preserving the current mode's model and developer instructions while applying model/reasoning overrides.
- Added thread-wrapper coverage proving dataclass-style collaboration-mode state is updated through the same protocol `with_updates` path.
- Validation not run; per workflow, tests remain pending until explicitly requested.

## Turn 268 - in-memory settings preview and grant preapproval

- Added `preview_settings` and `update_settings` to `InMemoryCodexSession`, returning Rust-like `ThreadConfigSnapshot` values for model, provider, service tier, reasoning, personality, cwd, approval, and permission state.
- `update_settings` now applies common thread settings into the lightweight session, including collaboration mode, reasoning summary, service tier, and personality.
- Corrected `CodexThread.thread_settings_update` so absent model/effort overrides are omitted from protocol `CollaborationMode.with_updates(...)`, preserving Rust's "None means keep current" behavior instead of accidentally writing `"None"` or clearing developer instructions.
- Corrected granted-permission application so existing grants can preapprove matching inline permissions but do not broaden the inline request's effective permission profile.
- Added/updated session-runtime coverage for settings preview/update and grant preapproval behavior.
- Validation run: `python -m unittest tests.test_core_session_runtime` passed 51 tests.
- Validation note: `python -m pytest tests/test_core_session_runtime.py tests/test_core_codex_thread.py` and `python -m unittest tests.test_core_codex_thread` could not run `test_core_codex_thread.py` because `pytest` is not installed in the current Python environment; a direct stdlib script validated the touched `CodexThread.thread_settings_update` behavior.

## Turn 269 - in-memory thread config snapshot

- Added `InMemoryCodexSession.thread_config_snapshot`, returning the current lightweight session settings through the same `ThreadConfigSnapshot` shape used by preview settings.
- Updated `CodexThread.config_snapshot` to fall back to `session.thread_config_snapshot()` when the wrapped codex object does not expose `thread_config_snapshot()` directly.
- Added session-runtime coverage proving current collaboration mode, model provider, reasoning summary, service tier, and reasoning effort appear in the snapshot.
- Validation run: `python -m unittest tests.test_core_session_runtime` passed 52 tests.
- Validation run: direct stdlib `python -c` script verified `CodexThread.config_snapshot()` fallback with `InMemoryCodexSession`.

## Turn 270 - settings service tier normalization

- Normalized service tier values in `InMemoryCodexSession.preview_settings` and `update_settings`.
- Protocol enum values such as `ServiceTier.FAST` and legacy string `"fast"` now become the Rust request value `"priority"` before being shown in snapshots or stored on the lightweight session.
- Added session-runtime coverage for preview/apply normalization.
- Validation run: `python -m unittest tests.test_core_session_runtime` passed 53 tests.

## Turn 271 - workspace roots settings snapshots

- Added `workspace_roots`, `profile_workspace_roots`, and `active_permission_profile` state to `InMemoryCodexSession`.
- `preview_settings`, `update_settings`, and `thread_config_snapshot` now include those fields in `ThreadConfigSnapshot`.
- When cwd changes without an explicit workspace-roots override, the lightweight session mirrors Rust's common retargeting behavior by replacing the old cwd root with the new cwd root.
- Added session-runtime coverage for preview/apply workspace-root snapshots and active permission profile propagation.
- Validation run: `python -m unittest tests.test_core_session_runtime` passed 54 tests.

## Turn 272 - explicit default service tier settings

- Added a shared settings unset sentinel to the core thread wrapper so `service_tier` can distinguish "no update" from "explicitly set default".
- `SessionSettingsUpdate()` now leaves service tier unchanged, while `SessionSettingsUpdate(service_tier=None)` stores Rust's explicit default request value `"default"`.
- Updated in-memory settings preview/update service-tier handling to use the shared sentinel and preserve the existing normalized `"priority"`/`"default"` semantics.
- Extended session-runtime coverage for unchanged versus explicit-default service-tier updates.
- Validation run: `python -m unittest tests.test_core_session_runtime` passed 54 tests.
- Validation run: direct stdlib `python -c` script verified `CodexThread.thread_settings_update()` preserves the unset sentinel for absent service-tier overrides and passes explicit `None` through for defaulting.

## Turn 273 - explicit effort clear settings

- Updated `CodexThreadSettingsOverrides.effort` to use the shared settings unset sentinel, matching Rust's nested-option behavior for thread settings updates.
- `CodexThread.thread_settings_update()` now preserves the current collaboration-mode reasoning effort when no effort override is provided, while still allowing `effort=None` to explicitly clear it.
- Added a protocol-to-core bridge for `ThreadSettingsOverrides` so double-option `effort` and `service_tier` values keep their omitted versus explicit-null meaning when converted to `CodexThreadSettingsOverrides`.
- Added stdlib thread-wrapper coverage for absent-effort preservation, explicit-effort clearing, and protocol double-option conversion.
- Validation run: `python -m unittest tests.test_core_codex_thread_unittest tests.test_core_session_runtime tests.test_protocol_protocol` passed 100 tests.

## Turn 274 - in-memory thread settings overrides

- Added an in-memory session bridge for protocol/core thread settings overrides.
- `InMemoryCodexSession.thread_settings_update()` now mirrors Rust's session handler by converting thread settings overrides into a `SessionSettingsUpdate` while preserving collaboration-mode model/reasoning updates and double-option `service_tier` semantics.
- Added `preview_thread_settings_overrides()` and `apply_thread_settings_overrides()` helpers so lightweight runtime callers can preview or apply protocol `ThreadSettingsOverrides` directly.
- Extended session-runtime coverage for preserving omitted settings and applying explicit-null effort/service-tier updates through protocol thread settings.
- Validation run: `python -m unittest tests.test_core_session_runtime tests.test_core_codex_thread_unittest` passed 58 tests.

## Turn 275 - turn runtime thread settings

- Added `thread_settings` support to the lightweight user-turn runtime request path.
- `build_user_turn_responses_request_from_session()`, `run_user_turn_sampling_from_session()`, and the HTTP wrapper now apply non-default protocol `ThreadSettingsOverrides` before creating the turn context, matching Rust's `user_input_or_turn_inner` ordering.
- The runtime reuses session-level `apply_thread_settings_overrides()` when available, or falls back to `thread_settings_update()` plus `update_settings()`.
- Added turn-runtime coverage proving thread settings are applied before turn creation and affect the current request model, reasoning effort, and service tier.
- Validation run: `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport tests.test_core_session_runtime` passed 67 tests.

## Turn 276 - user input op turn runtime

- Added lightweight runtime entrypoints for protocol `Op.user_input` values.
- `build_user_input_op_responses_request_from_session()` and `run_user_input_op_sampling_from_session()` now extract `items`, `thread_settings`, and `final_output_json_schema` from the protocol op and reuse the existing turn runtime path.
- This reduces the gap with Rust's `Op::UserInput` handler and prevents upper layers from accidentally dropping per-turn thread settings while manually unpacking user input.
- Added turn-runtime coverage for building and sampling directly from `Op.user_input`, including thread settings propagation.
- Validation run: `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport` passed 14 tests.

## Turn 277 - user input op client metadata

- Added `responsesapi_client_metadata` support to the lightweight user-turn runtime.
- Direct turn-runtime calls can pass client metadata, and `Op.user_input` entrypoints now extract the protocol field automatically.
- When the turn context exposes `turn_metadata_state.set_responsesapi_client_metadata(...)`, the runtime records the metadata before prompt/context recording, matching the Rust handler's turn-metadata path for accepted user input.
- Added turn-runtime coverage proving `Op.user_input(... responsesapi_client_metadata=...)` reaches the turn metadata state.
- Validation run: `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport` passed 15 tests.

## Turn 278 - user input op additional context

- Added protocol preservation for `Op.user_input(additional_context=...)`.
- Added lightweight turn-runtime handling for `additional_context` from direct calls and protocol `Op.user_input` entrypoints.
- Additional context entries are recorded before the current user input, sorted by key like Rust's `BTreeMap`: `untrusted` entries become user `<external_key>...</external_key>` messages, and `application` entries become developer `<key>...</key>` messages.
- Added protocol and turn-runtime coverage for preserving and prompt-recording additional context.
- Validation run: `python -m unittest tests.test_core_turn_runtime tests.test_protocol_protocol` passed 53 tests.

## Turn 279 - user input additional context roundtrip

- Updated protocol `Op.from_mapping()` so `user_input` payloads preserve `additional_context` while deserializing.
- This closes the protocol round-trip gap from the previous additional-context slice: client JSON with `additional_context` now survives through `Op.from_mapping(...).to_mapping()`.
- Extended protocol coverage for `Op.user_input(additional_context=...)` round-tripping.
- Validation run: `python -m unittest tests.test_protocol_protocol tests.test_core_turn_runtime` passed 53 tests.

## Turn 280 - additional context merge dedup

- Added lightweight session-state deduplication for turn-runtime `additional_context`.
- The runtime now mirrors Rust's `AdditionalContextStore.merge(...)`: entries are normalized, compared against the previous session values, only changed keys are injected as messages, and the current map replaces the prior map.
- Repeated identical additional context no longer reappears in later prompts, while changed values are injected again.
- Added turn-runtime coverage for unchanged versus changed additional-context entries.
- Validation run: `python -m unittest tests.test_core_turn_runtime` passed 11 tests.

## Turn 281 - additional context empty clears

- Updated lightweight turn-runtime additional-context state to treat an absent/empty user-input additional context as an empty map.
- This matches Rust's `AdditionalContextStore.merge(...)` behavior where every `Op::UserInput` replaces the stored map; a later request without additional context clears the prior values.
- After a clear, the same additional-context value is injected again if it reappears in a later user input.
- Added turn-runtime coverage for clear-then-reinject behavior.
- Validation run: `python -m unittest tests.test_core_turn_runtime` passed 12 tests.

## Turn 292 - view_image turn environment resolution

- Aligned the Python `view_image` handler with Rust's environment-aware tool execution path.
- `resolve_tool_environment()` now handles both resolved environment containers with `primary()` and tuple/list-style turn environment collections, so omitted `environment_id` selects the primary environment and explicit ids search the active turn environments.
- `ViewImageHandler.handle()` now uses the invocation turn's selected environment `cwd` when available, instead of always reading from the handler construction cwd.
- Added coverage for selecting a non-primary environment by `environment_id` and surfacing Rust-matching unknown-environment errors.
- Validation run: `python -m unittest tests.test_core_view_image_handler` passed 7 tests.

## Turn 293 - unified exec environment invocation resolution

- Added a pure `resolve_exec_command_invocation()` helper that mirrors the Rust `ExecCommandHandler` front half: parse environment arguments, resolve the selected turn environment, compute cwd from that environment plus optional `workdir`, parse command args, and resolve shell command argv.
- This prepares the Python unified exec path for a faithful process-manager bridge without baking environment selection into later runtime code.
- Added coverage for explicit non-primary `environment_id`, primary-environment defaulting, environment-relative `workdir`, and no-environment unavailability.
- Validation run: `python -m unittest tests.test_core_unified_exec_handler` passed 13 tests.
- Follow-up: exported `ResolvedExecCommandInvocation` and `resolve_exec_command_invocation()` through `pycodex.core`; direct import smoke check printed `ok`.

## Turn 294 - apply_patch environment invocation resolution

- Added a pure `resolve_apply_patch_invocation()` helper that mirrors the Rust `ApplyPatchHandler` front half: parse custom patch input, enforce the multi-environment gate for `*** Environment ID:`, resolve the selected turn environment, and expose the selected cwd for later verification/runtime layers.
- Added `require_apply_patch_environment_id()` with Rust-matching model-facing error text when environment selection is unavailable for the turn.
- Exported the new apply_patch environment-resolution helpers through `pycodex.core`.
- Added coverage for explicit non-primary environment selection, primary-environment defaulting, no-environment unavailability, and disabled environment selection errors.
- Validation run: `python -m unittest tests.test_core_apply_patch` passed 34 tests.

## Turn 295 - apply_patch handler disk execution slice

- Added a stdlib-only `ApplyPatchHandler.handle()` path for the local/core case: resolve the selected turn environment, verify patch arguments against that environment cwd, apply add/update/delete changes to disk, and return an `ApplyPatchToolOutput`.
- Added `apply_patch_action_to_disk()` and `apply_patch_summary()` helpers with Rust-style `Success. Updated the following files:` output grouped as added, modified, then deleted.
- Exported the new apply_patch disk execution helpers through `pycodex.core`.
- Added coverage proving handler execution writes to the selected non-primary environment, leaves the other environment untouched, deletes files, returns the Rust-style summary, and reports verification errors to the model.
- Validation run: `python -m unittest tests.test_core_apply_patch` passed 36 tests.

## Turn 296 - apply_patch move summary parity

- Corrected the Python apply_patch disk execution summary for move updates to match Rust `apply_hunks_to_files`: moved updates are reported under the original hunk path in the modified list, while the new content is still written to the move destination and the original file is removed.
- Added coverage for `*** Move to:` updates that create missing destination parents, delete the source file, and return `M <original path>` in the Rust-style summary.
- Validation run: `python -m unittest tests.test_core_apply_patch` passed 37 tests.

## Turn 297 - exec_command local handler execution slice

- Added a stdlib-only `ExecCommandHandler.handle()` path for local/core execution: resolve the selected turn environment/workdir, choose the session shell when available, run the command with `subprocess.run`, capture stdout/stderr, preserve non-zero exit codes, and return `ExecCommandToolOutput`.
- The handler now uses the selected environment cwd plus optional `workdir`, so model-visible multi-environment exec calls can execute in the intended directory instead of stopping at schema/hook behavior.
- Added coverage for executing in a non-primary selected environment workdir and for returning non-zero command output without raising.
- Validation run: `python -m unittest tests.test_core_unified_exec_handler` passed 15 tests.

## Turn 298 - exec_command apply_patch interception

- Added `intercept_exec_apply_patch()` so Python `exec_command` can recognize apply_patch invocations before spawning a shell, verify them with the existing apply_patch parser, apply the patch to disk, and return the Rust-style summary output.
- `ExecCommandHandler.handle()` now calls this interception path before `subprocess.run`, matching Rust's `intercept_apply_patch` placement in the unified exec handler.
- Exported `intercept_exec_apply_patch()` through `pycodex.core`.
- Added coverage for direct apply_patch tuple interception without shell spawning, plus a portable shell heredoc handler test that runs when `sh` is available.
- Validation run: `python -m unittest tests.test_core_unified_exec_handler tests.test_core_apply_patch` passed 54 tests with 1 shell-availability skip.

## Turn 299 - write_stdin unified exec manager forwarding

- Added `WriteStdinRequest` and an async `WriteStdinHandler.handle()` that matches Rust's handler boundary: parse function arguments, build a write-stdin request with process id, chars, yield timeout, max output tokens, and turn truncation policy, then forward it to `session.services.unified_exec_manager.write_stdin(...)`.
- Manager errors are now wrapped as model-facing `write_stdin failed: ...` messages.
- Updated the unified exec handler module description to reflect that lightweight local execution now exists while full PTY/session management remains delegated to a unified exec manager.
- Exported `WriteStdinRequest` through `pycodex.core`.
- Validation run: `python -m unittest tests.test_core_unified_exec_handler` passed 19 tests with 1 shell-availability skip.

## Turn 300 - unified exec model-facing parse errors

- Tightened `exec_command` and `write_stdin` handler error boundaries so argument parsing and validation failures are returned as model-facing `FunctionCallError.respond_to_model(...)` values instead of leaking ordinary Python exceptions.
- Added shared `_parse_or_validation_error()` formatting with `failed to parse function arguments: ...`, matching the Rust handler intent that malformed tool arguments remain recoverable tool-call errors.
- Added coverage for bad `exec_command` and `write_stdin` argument shapes.
- Validation run: `python -m unittest tests.test_core_unified_exec_handler` passed 21 tests with 1 shell-availability skip.

## Turn 301 - unified exec/router invocation boundary and parse-error tests

- Confirmed the current tool router uses the registry `ToolInvocation` shape expected by the unified exec handlers, so default router dispatch will not fail on the duplicate context/registry invocation class boundary.
- Tightened unified exec handler argument-error coverage: bad `exec_command` and `write_stdin` arguments now assert model-facing `failed to parse function arguments: ...` errors.
- Fixed a misplaced assertion in `tests/test_core_tool_router.py` where the invalid tool_search error assertions had drifted into the parallel-support test, causing a `caught` NameError when the related router suite was run.
- Validation run: `python -m unittest tests.test_core_unified_exec_handler tests.test_core_tool_router` passed 46 tests with 1 shell-availability skip.

## Turn 312 - local HTTP timeout alias schema

- Exposed the existing `timeout` compatibility alias in the local HTTP `exec_command` model-visible schema, keeping it aligned with the parser that already accepts `timeout_ms` and `timeout` millisecond values.
- Added schema coverage so model-visible planning cannot regress by hiding an alias that runtime execution still supports.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 313 - write_stdin max output coverage

- Tightened local HTTP `write_stdin` parity coverage against Rust's unified exec handler/spec boundary.
- The schema shape test now locks `yield_time_ms` and `max_output_tokens` as visible write_stdin parameters.
- Added behavior coverage proving model-supplied `max_output_tokens` is converted into the session manager output cap for interactive output truncation.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 314 - Windows exec_command guidance

- Aligned the local HTTP `exec_command` model-visible description with Rust Codex on Windows by appending the Windows shell safety guidance.
- The guidance now warns against cross-shell destructive filesystem composition, requires resolved-path checks before recursive delete/move operations, and preserves the `Start-Process -WindowStyle Hidden` background-helper rule.
- Added schema coverage so the Windows-specific guidance remains visible in the local HTTP exec path.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 315 - additional permissions schema

- Aligned the local HTTP `exec_command` `additional_permissions` schema with Rust Codex's permission profile shape.
- The schema now exposes `network.enabled` plus `file_system.read` and `file_system.write` absolute-path grants, with `additionalProperties: false` at the profile and nested object levels.
- Added schema coverage so model-visible permission requests remain structured instead of falling back to an opaque object.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 316 - exec approval parameter descriptions

- Aligned the local HTTP `exec_command` approval-parameter descriptions with Rust Codex's shell spec.
- `sandbox_permissions` now advertises `with_additional_permissions`, `require_escalated`, and the default `use_default` behavior.
- `justification` now explains that escalation requests should be phrased as a user-facing approval question, and `prefix_rule` now documents the suggested-prefix examples.
- Added schema coverage for the key model-visible approval guidance.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 317 - login shell description

- Aligned the local HTTP `exec_command.login` schema description with Rust Codex's shell spec.
- The model-visible description now explains that `login` controls `-l/-i` shell semantics and defaults to true.
- Added schema coverage for the key `login` guidance.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 318 - unified exec output schema coverage

- Confirmed the local HTTP unified exec output schema already matches Rust's `unified_exec_output_schema` shape for required fields and schema-visible output metadata.
- Strengthened schema coverage for `additionalProperties: false`, `chunk_id`, `exit_code`, `session_id`, `original_token_count`, and the truncated-output description.
- Added equivalent `write_stdin` output-schema coverage because it reuses the unified exec output schema.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 319 - additional permissions approval output

- Updated local HTTP approval-required coverage to use Rust Codex's current `additional_permissions` profile shape.
- The approval metadata fixture now pairs `sandbox_permissions: with_additional_permissions` with `additional_permissions.network.enabled` instead of the stale `network_access` shape.
- The assertion now verifies the model-facing approval-required output preserves the structured Rust-style permission request.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 320 - additional permissions output normalization

- Normalized local HTTP approval-required `additional_permissions` output through the protocol `AdditionalPermissionProfile` and core `normalize_additional_permissions` helper when the request uses the Rust profile shape.
- Empty nested permission sections are now removed from the model-facing approval-required output, matching Rust's normalized profile behavior more closely.
- Invalid or legacy permission mappings still fall back to raw metadata output to avoid breaking compatibility in the local helper.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 321 - local additional permissions auto-exec guard

- Added a local HTTP shell-tool guard so `additional_permissions` requests are not auto-executed by the helper when approval policy is `never`.
- The guard returns model-facing Rust-style errors for unsupported local additional-permission requests, missing profiles, and profiles supplied without `sandbox_permissions: with_additional_permissions`.
- Added coverage proving the command runner is not invoked for a local `with_additional_permissions` request.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 322 - invalid additional permissions auto-exec coverage

- Added local HTTP coverage for the remaining additional-permission auto-exec guard branches.
- The helper now has tests proving commands are not run when `with_additional_permissions` omits `additional_permissions`, or when an `additional_permissions` profile is supplied without `sandbox_permissions: with_additional_permissions`.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 323 - empty additional permissions guard

- Tightened the local HTTP additional-permissions auto-exec guard for empty Rust-style permission profiles.
- The guard now parses and normalizes `additional_permissions` when possible and returns a Rust-style model-facing invalid-permission error if the normalized profile has no `network` or `file_system` requests.
- Added coverage proving an empty `network` plus empty `file_system` profile is rejected before the command runner can execute.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 324 - require_escalated auto-exec guard

- Extended the local HTTP shell-tool auto-exec guard to reject `sandbox_permissions: require_escalated` before running commands.
- This mirrors Rust's non-`OnRequest` sandbox override guard for explicit escalation requests and prevents the local helper from silently executing a command that asked to run outside sandbox restrictions.
- Added coverage proving the runner is not invoked for a `require_escalated` request when approval policy is `never`.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 325 - invalid sandbox_permissions guard

- Added local HTTP validation for unknown `sandbox_permissions` values before approval handling or command execution.
- This mirrors Rust's `SandboxPermissions` enum parsing boundary so invalid values cannot pass through as ordinary metadata and run locally.
- Added coverage proving the command runner is not invoked for an unknown sandbox permission value.
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 326 - local request_permissions tool spec

- Added a local HTTP exec `request_permissions` tool spec that reuses the existing core Rust-shaped permission tool schema and description.
- The local shell-tool router now deduplicates and exposes `request_permissions` alongside `exec_command`, `write_stdin`, and `apply_patch`, matching the core Rust shell spec surface more closely.
- Added a model-facing unsupported output for local HTTP `request_permissions` calls because this exec helper does not provide interactive permission grants.
- Added schema coverage for the request-permission profile shape (`network.enabled`, `file_system.read`, and `file_system.write`).
- Validation run: `python -m unittest tests.test_exec_local_runtime`.

## Turn 327 - execpolicy check justification parity

- Compared Rust's `codex execpolicy check` CLI tests with the Python parser/runner implementation.
- Confirmed the Python runner already renders `prefixRuleMatch.justification` for matched rules when present.
- Added a parity test matching Rust's `execpolicy_check_includes_justification_when_present` behavior for a forbidden `git push` rule.
- Validation run: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_execpolicy_check_includes_justification_when_present`.
- Broader `python -m unittest tests.test_cli_parser` still has unrelated pre-existing failures across remote/app/cloud/parser paths.

## Turn 328 - execpolicy tokenizer parse errors

- Tightened Python `execpolicy check` parse-error handling so tokenizer failures from malformed rules are converted into the same user-facing `failed to parse policy at ...` error path as AST syntax errors.
- This prevents malformed policy files from escaping as raw `tokenize.TokenError` exceptions and restores CLI-style error code handling for that core safety-policy command.
- Validation run: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_execpolicy_check_reports_parse_error`.

## Turn 329 - execpolicy command --help argument handling

- Aligned `execpolicy check` help handling with command parsing semantics so `--help` only opens execpolicy help while option parsing is still active.
- Absolute host executable commands can now be checked with `--help` as the command argument when `--resolve-host-executables` is enabled.
- This fixes the host-executable parity test path without treating command arguments as Codex CLI flags.
- Normalized execpolicy string tokens that Python would otherwise reject as escape sequences, preserving Windows backslash paths in rule files.
- Validation run: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_execpolicy_check_resolve_host_executables`.

## Turn 330 - root remote rejection before subcommand parsing

- Moved non-interactive root `--remote`/`--remote-auth-token-env` rejection ahead of subcommand-specific parsing.
- This restores upstream-style precedence for commands such as `codex --remote ... execpolicy check`, which should report that remote mode is only for interactive TUI commands instead of falling into `execpolicy check` argument validation.
- Added the same remote-mode rejection boundary to `ParsedCli.exec_cli()` so parsed `codex exec` invocations fail before constructing non-interactive exec plans when root remote options are present.
- Converted `CliParseError` from non-interactive exec plan construction into normal CLI exit code 2 output, matching existing exec parse-error handling.
- Validation run: `python -m unittest -k execpolicy tests.test_cli_parser`.
- Additional validation run: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_exec_cli_rejects_root_remote_like_upstream_noninteractive_dispatch tests.test_cli_parser.TopLevelCliParserTests.test_main_remote_rejects_execpolicy_check_with_subcommand_context`.
- Additional validation run: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_remote_rejects_exec_with_prompt tests.test_cli_parser.TopLevelCliParserTests.test_main_rejects_remote_auth_token_env_for_noninteractive_subcommand tests.test_cli_parser.TopLevelCliParserTests.test_exec_cli_rejects_root_remote_like_upstream_noninteractive_dispatch`.

## Turn 331 - review alias remote rejection and preparation boundary

- Added root remote rejection for top-level `codex review` before it is translated into the exec review alias.
- Stopped the current Python review alias path after successful non-interactive review plan preparation, matching the existing porting boundary instead of attempting an app-server connection.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_remote_rejects_review_with_context tests.test_cli_parser.TopLevelCliParserTests.test_main_remote_auth_rejects_review_with_context tests.test_cli_parser.TopLevelCliParserTests.test_main_review_alias_runs_exec_plan_preparation tests.test_cli_parser.TopLevelCliParserTests.test_main_review_inherits_root_exec_shared_options`.
- Regression validation passed: `python -m unittest -k execpolicy tests.test_cli_parser`.
- Regression validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_remote_rejects_exec_with_prompt tests.test_cli_parser.TopLevelCliParserTests.test_main_rejects_remote_auth_token_env_for_noninteractive_subcommand tests.test_cli_parser.TopLevelCliParserTests.test_exec_cli_rejects_root_remote_like_upstream_noninteractive_dispatch`.

## Turn 332 - resume command hint helper parity

- Added `pycodex.utils_cli.resume_command` with `resume_command()` and `resume_hint()` mirroring Rust `codex_utils_cli::resume_command`.
- Preserved Rust user-facing resume hints for named threads, direct thread-id resumes, leading-dash targets, whitespace quoting, apostrophe quoting, and missing-thread-id suppression.
- Validation passed: `python -m unittest tests.test_utils_cli_resume_command`.

## Turn 333 - TokenUsage display formatting parity

- Added Python `TokenUsage.__str__()` formatting to mirror Rust TUI `Display for TokenUsage`: blended total, non-cached input, optional cached-input suffix, raw output tokens, optional reasoning suffix, and separator formatting.
- Covered zero usage, cached/reasoning usage, and negative input/output clamping behavior.
- Validation passed: `python -m unittest tests.test_protocol_token_usage_display`.

## Turn 334 - CLI app exit message formatting parity

- Added `pycodex.cli.app_exit` with `AppExitInfo` and `format_exit_messages()`, mirroring Rust CLI `format_exit_messages` for token-usage output plus resume continuation hints.
- Reused the previously ported `TokenUsage.__str__()` and `resume_hint()` helpers so the composed CLI exit messages follow the same upstream formatting boundary.
- Covered empty exits, token-only exits, named-thread resume hints, id-only resume commands, output ordering, and colorized resume-command wrapping.
- Validation passed: `python -m unittest tests.test_cli_app_exit`.

## Turn 335 - CLI app exit reason handling parity

- Extended `pycodex.cli.app_exit` with Rust-like `ExitReason`, `AppExitInfo.fatal()`, and `handle_app_exit()` boundaries.
- Matched Rust fatal exit handling by printing `ERROR: ...` to stderr and raising process exit code 1, while user-requested exits print formatted summary lines normally.
- Added an injectable `run_update_action` callback boundary so update actions can be sequenced after summary output without pretending the full Rust updater is implemented in this slice.
- Validation passed: `python -m unittest tests.test_cli_app_exit`.

## Turn 336 - update action command formatting parity

- Added `pycodex.cli.update_action.UpdateAction` with Rust-like update action variants and `command_args()`/`command_str()` helpers.
- Ported npm, bun, Homebrew cask, standalone Unix installer, and standalone Windows installer command formatting from Rust `tui/src/update_action.rs`.
- Kept this slice to command formatting only; install-context detection and actual updater process execution remain outside this turn.
- Validation passed: `python -m unittest tests.test_cli_update_action`.

## Turn 337 - update action run boundary

- Added `pycodex.cli.app_exit.run_update_action()` to mirror Rust CLI update-action output sequencing: leading blank line, `Updating Codex via ...`, failure status error, and successful restart prompt.
- Kept external process execution behind a required injectable runner callback so the port preserves the command/status boundary without accidentally running installer commands in tests or partial CLI wiring.
- Validation passed: `python -m unittest tests.test_cli_app_exit`.

## Turn 338 - update available raw notice parity

- Added `pycodex.cli.update_notice.update_available_raw_lines()` mirroring Rust TUI `UpdateAvailableHistoryCell::raw_lines`.
- Preserved the known-action update command path, the fallback install-options path, version transition line, blank separator, and release-notes URL.
- Kept this slice to raw transcript/plain-text lines only; ratatui display styling, borders, wrapping, and hyperlinks remain out of scope for this Python helper.
- Validation passed: `python -m unittest tests.test_cli_update_notice`.

## Turn 339 - update version helper parity

- Added `pycodex.cli.update_versions` with `parse_version()`, `is_newer()`, `extract_version_from_latest_tag()`, and `is_source_build_version()` mirroring Rust TUI update-version helpers.
- Preserved plain three-part version parsing, whitespace trimming, prerelease rejection via `None`, `rust-v` latest-tag prefix handling, and `0.0.0` source-build detection.
- Validation passed: `python -m unittest tests.test_cli_update_versions`.

## Turn 340 - doctor update action label parity

- Added `pycodex.cli.update_action.update_action_label()` mirroring Rust doctor update labels for npm, bun, Homebrew, standalone installer, and manual/unknown update sources.
- Mapped the existing Python `UpdateAction` variants to the same user-facing label strings while using `None` for the current Python-side manual/unknown boundary until install-context detection is ported.
- Validation passed: `python -m unittest tests.test_cli_update_action`.

## Turn 341 - doctor version cache detail parity

- Added `pycodex.cli.doctor_updates` with `VersionInfo`, `cached_version_details()`, and `push_cached_version_details()` mirroring Rust doctor version-cache detail formatting.
- Preserved user-facing detail lines for cache path, missing cache, parse/read errors, cached latest version, last checked timestamp, and dismissed version.
- Kept this slice local-file only; latest-version network probes and full doctor update check assembly remain outside this turn.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.

## Turn 342 - doctor command local update cache details

- Wired the local version-cache detail helper into the Python `doctor` command as an `updates` check.
- The command now reports local `version.json` cache details in normal and JSON doctor output without performing network latest-version probes or npm root checks.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details`.
- Regression validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.

## Turn 343 - doctor update config detail parity

- Extended the Python `doctor` command's `updates` check with Rust-like leading detail lines for `check for update on startup` and `update action`.
- Reads `check_for_update_on_startup` from `CODEX_HOME/config.toml`, defaulting to Rust's `true` behavior when unset or not a boolean, and uses the current manual/unknown update-action boundary until install-context detection is ported.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details`.
- Regression validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.

## Turn 344 - doctor latest version detail parity

- Added `latest_version_details()` and `push_latest_version_details()` to mirror Rust doctor update detail lines after a successful latest-version probe.
- Preserved Rust's `is_newer(...) == Some(true)` behavior: only a definitely newer plain version reports `newer version is available`; equal, older, malformed, or prerelease comparisons report `current version is not older`.
- Kept this slice as pure formatting/comparison logic; no network latest-version probe was added.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.

## Turn 345 - doctor latest-version probe error detail parity

- Added `latest_version_probe_error_details()` and `push_latest_version_probe_error_details()` mirroring Rust doctor's failed latest-version probe detail line.
- Preserved the user-facing `latest version probe: ...` text while keeping this slice pure formatting only; no network latest-version probe is performed.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.

## Turn 346 - doctor update check builder parity

- Added `DoctorUpdateCheck` and `build_doctor_update_check()` to combine the ported update config, action label, local cache, latest-version success, and probe-error detail helpers.
- Matched Rust's local summary/status shape for update diagnostics, including warning status when a latest-version probe error is supplied.
- Rewired Python `doctor` to use the builder for its local `updates` check while still avoiding network latest-version probes.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.

## Turn 347 - doctor latest-version fetch parity

- Added stdlib-only latest-version probe helpers in `pycodex.cli.doctor_updates`, mirroring Rust's GitHub release and Homebrew cask JSON parsing boundaries.
- Preserved Rust's install-channel routing: Homebrew actions read the cask API `version`, while npm, bun, standalone, and manual/unknown paths read GitHub `tag_name` values with the required `rust-v` prefix.
- Kept the doctor command itself on the existing no-network local boundary for this slice; tests inject JSON getters so the parsing and URL selection behavior is deterministic.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.

## Turn 348 - doctor latest-version probe wiring parity

- Rewired Python `doctor` updates diagnostics to call `fetch_latest_version(None)` and pass either the fetched latest version or the probe error into `build_doctor_update_check()`.
- Matched Rust's doctor behavior where latest-version probe failures degrade the updates row to `warn` with a `latest version probe: ...` detail instead of aborting doctor.
- Updated doctor CLI tests to patch the probe boundary explicitly, keeping unit validation deterministic while exercising the success and warning wiring.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_warns_on_latest_version_probe_error`.

## Turn 349 - doctor npm update target parity

- Added Rust-like npm-managed install detection and npm global root comparison helpers, including inherited cargo-binary environment suppression, `CODEX_MANAGED_PACKAGE_ROOT`, `npm root -g`, root normalization, mismatch, missing-root, and npm-unavailable outcomes.
- Extended `build_doctor_update_check()` with npm root check handling so match, mismatch, missing package root, and npm command failures produce Rust-like details, status, summary, and remediation.
- Rewired Python `doctor` to run the npm root check only when `doctor_managed_by_npm()` is true, while tests patch the environment/check boundary to stay deterministic.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_warns_on_latest_version_probe_error tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_npm_root_mismatch_remediation`.

## Turn 350 - doctor update action detection parity

- Added a Python `detect_update_action()` helper mirroring Rust install-context-to-update-action mapping for npm, bun, Homebrew, standalone Unix/Windows, and manual/unknown installs.
- Preserved Rust's ordering and doctor behavior: inherited cargo target binaries suppress managed npm/bun env, npm/bun env wins before path detection, standalone release/package layouts are detected under `CODEX_HOME/packages/standalone/releases`, and macOS Homebrew prefixes map to brew updates.
- Rewired Python `doctor` to use the detected update action for both the `update action: ...` detail and the latest-version probe routing.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_warns_on_latest_version_probe_error tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_npm_root_mismatch_remediation tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_routes_latest_probe_by_detected_update_action`.

## Turn 351 - doctor installation context details parity

- Added Rust-like install-context description helpers for npm/bun/brew/other package layouts and standalone release/package layouts, including `none` formatting for absent optional resource/path directories.
- Added a Python `doctor_installation_check()` that reports current executable, install context, ignored inherited package-manager launch env, npm/bun managed flags, and managed package root details.
- Rewired Python `doctor` JSON/normal output to include an `installation` check alongside `updates`, matching Rust's split between install consistency and update diagnostics.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_version_cache_details tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_warns_on_latest_version_probe_error tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_npm_root_mismatch_remediation tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_routes_latest_probe_by_detected_update_action tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_installation_check`.

## Turn 352 - doctor PATH codex entries parity

- Added `codex_path_entries()` mirroring Rust's platform-specific `where codex` / `which -a codex` lookup, including empty-output filtering and suppressing lookup errors to an empty list.
- Extended `doctor_installation_check()` with Rust-like PATH diagnostics: report `PATH codex entries: N` and enumerate `PATH codex #i: ...` when multiple Codex executables are found, and enumerate a single entry only when detailed output is requested.
- Rewired `codex doctor --all` to request detailed installation PATH entries.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_installation_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_all_requests_installation_path_details tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_routes_latest_probe_by_detected_update_action`.

## Turn 353 - doctor installation npm root parity

- Extended `doctor_installation_check()` with Rust-like npm root check handling, separate from the updates check, including match details, mismatch failure, missing provenance warning, npm-unavailable warning, and remediation text.
- Preserved Rust's installation-specific summaries, including `npm install -g @openai/codex would update a different install`, `npm-managed launch is missing package-root provenance`, and `npm-managed launch could not inspect npm global root`.
- Rewired Python `doctor` to pass the npm root check result into both `updates` and `installation`, matching Rust's independent diagnostics over the same npm provenance boundary.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_npm_root_mismatch_remediation tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_installation_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.

## Turn 354 - doctor env path detail parity

- Aligned Python installation diagnostics with Rust's `push_env_path_detail()` behavior for `CODEX_MANAGED_PACKAGE_ROOT`.
- `doctor_installation_check()` now always includes `managed package root: ...`, using `managed package root: not set` when the environment variable is absent.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_installation_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.

## Turn 355 - doctor fail exit status parity

- Aligned Python doctor command exit behavior with Rust: any `fail` check now returns process exit code 1, while warnings without failures still return 0.
- Added explicit top-level JSON `status: fail` and `summary.failed` counts when fail checks are present.
- Updated human summary output to distinguish `ok`, `warn`, and `fail`, including passed, warning, and failed counts.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_npm_root_mismatch_remediation tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_summary_returns_nonzero_on_fail tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_warns_on_latest_version_probe_error`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_installation_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_all_requests_installation_path_details`.

## Turn 356 - doctor system check parity

- Added Python `SystemCheckInputs` and `doctor_system_check()` mirroring Rust `doctor/system.rs` detail construction for OS string, OS type, OS version, OS language, and locale environment variables.
- Preserved Rust summary behavior: `OS language <value>` when available and `OS language unavailable` otherwise.
- Rewired Python `doctor` to include a `system` check before local config/update checks.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_system_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_installation_check`.

## Turn 357 - doctor runtime check parity

- Added Python `doctor_runtime_check()` mirroring Rust `doctor/runtime.rs` process provenance details: version, platform, install method description, build commit, and current executable.
- Preserved Rust's install-method summary shape (`running <method> on <platform>`) for local build, npm, bun, brew, and standalone-derived update actions.
- Rewired Python `doctor` to include a `runtime` check in both normal and JSON output.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_runtime_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_system_check`.

## Turn 358 - doctor search check parity

- Added Python `doctor_search_check()` mirroring Rust `doctor/runtime.rs` search diagnostics for selected ripgrep command, provider, readiness, warning status, and remediation.
- Preserved Rust's system-vs-bundled split: path-like commands are checked as files, while bare commands run `<rg> --version` and record the first stdout line.
- Rewired Python `doctor` to include a `search` check in normal and JSON output.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_search_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_runtime_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.

## Turn 359 - doctor terminal check core parity

- Added Python `TerminalCheckInputs` and `doctor_terminal_check()` covering Rust terminal metadata details, color-output summary, effective locale detection, remote terminal presence markers, and core issue severity aggregation.
- Preserved Rust's key terminal outcomes: `TERM=dumb` fails with remediation, narrow terminal dimensions warn, declared narrow `COLUMNS`/`LINES` warn, and non-UTF-8 locale warns.
- Rewired Python `doctor` to include a `terminal` check and pass the `--no-color` flag into terminal diagnostics.
- Validation passed: `python -m unittest tests.test_cli_doctor_updates`.
- Validation passed: `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_terminal_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_json_includes_search_check tests.test_cli_parser.TopLevelCliParserTests.test_main_doctor_reports_status`.
- Exec event notification normalization now accepts more Rust `ServerNotification` enum variant names as aliases for their upstream wire methods, including thread lifecycle, thread goal/name/settings updates, guardian approval review notifications, and raw response item completion, while preserving the official `method` + `params` JSON-RPC notification shape.
- Exec event notification method normalization now covers the rest of Rust's current `ServerNotification` variant-to-wire-method aliases, including account/app, MCP status/progress, command/process output deltas, reasoning deltas, realtime thread notifications, file-change updates, windows sandbox notifications, and warning/context/skills notifications as lightweight protocol shims.
- Exec session-loop notification method handling now reuses the centralized event-processor normalization helper, so remote/app-server `ServerNotification` envelopes with Rust-style `kind` variant names share the same alias coverage as normal exec event processing.
- Exec event notification method normalization now includes the missing Rust `ThreadUnarchived` / `thread_unarchived` aliases for the `thread/unarchived` wire method, closing a lifecycle notification coverage gap from the upstream `ServerNotification` list.
- Exec JSON event processing now formats `model/rerouted` reasons with Rust-style enum debug names (for example `highRiskCyberActivity` -> `HighRiskCyberActivity`) when emitting the reroute error item, matching upstream `EventProcessorWithJsonOutput` text.
- Exec warning/deprecation event processing now preserves Rust's `summary`/`details` primary shape while falling back to legacy-compatible `message` payloads, preventing remote/session warning envelopes from producing empty JSON or human warning text.
- Exec error-notification exit-code handling now has regression coverage for Rust-style typed `kind: Error` plus `payload` envelopes, preserving the existing parity rule that only same-thread same-turn non-retrying errors mark the exec loop as failed.
- Exec output-schema loading now has regression coverage for Rust's invalid-JSON error branch, preserving the existing `Output schema file ... is not valid JSON` behavior alongside the read-error branch.
- Exec prompt stdin decoding now has regression coverage for Rust's invalid UTF-16 BOM branch, preserving the `input looked like UTF-16LE but could not be decoded` user-facing error alongside existing UTF-8/UTF-32 decoding coverage.
- Exec review request construction now has regression coverage for the Rust `review -` path: custom review instructions are read from stdin and trimmed before creating the custom review target.
- Exec initial-operation construction now has regression coverage for Rust's review branch: `codex exec --output-schema ... review ...` constructs a review operation without loading the output schema, while schema loading remains limited to user-turn exec/resume paths.
- Exec resume initial-operation preparation now has regression coverage for Rust's `resume --last <single positional>` semantics: the single positional becomes the prompt text and no explicit session id is set.
- Exec initial-operation construction now has regression coverage for Rust's resume user-turn branch loading `--output-schema`, complementing the review branch coverage that deliberately skips schema loading.
- Exec human final-message state now has regression coverage for Rust's interrupted-turn cleanup rule: stale final messages are cleared and not emitted after an interrupted turn.
- Exec final-message extraction now has regression coverage for Rust's precedence rule: the latest agent message wins, with plan text used only as a fallback.

- Exec JSON event mapping now has regression coverage for Rust's command-execution declined status on app-server item notifications, preserving the existing declined enum mapping while typed protocol CommandExecution items remain a future gap. (turn-198)

- Protocol and exec JSONL mapping now include a typed CommandExecutionItem path, allowing TurnItem.command_execution(...) to map into Rust-compatible command_execution JSONL items while retaining Rust app-server protocol fields on the typed item. (turn-199)

- Human exec rendering now preserves typed CommandExecutionItem fields through the app-server-like mapping, so typed command execution completions render status, exit code, and aggregated output like Rust-compatible app-server items. (turn-200)

- CommandExecutionItem is now included in the public pycodex.protocol export list, with protocol coverage for parsing Rust app-server CommandExecution thread-item fields through TurnItem.from_mapping. (turn-201)

- Core tool events now include Rust-style builders that convert legacy ExecCommandBegin/End events into typed CommandExecution turn items, preserving command quoting, app-server source/status names, output, exit code, and duration milliseconds. (turn-202)

- Core tool events now include a lightweight Rust-style command execution server-notification bridge for exec_command_begin, exec_command_end, and exec_command_output_delta, wrapping begin/end as typed CommandExecution items and output deltas as item/commandExecution/outputDelta notifications. (turn-203)

- Command execution server-notification bridge now emits plain app-server-style CommandExecution item dictionaries instead of embedding Python TurnItem objects, preserving JSON-serializable camelCase payloads for begin/end notifications. (turn-204)

- CommandExecutionItem now exposes an app-server-compatible to_mapping() serializer, and the command execution notification bridge reuses it for JSON-shaped begin/end item payloads. (turn-205)

- Core tool events now include a lightweight guardian command/execve assessment bridge that can synthesize typed CommandExecution items and map guardian in-progress/denied/aborted/timed-out statuses to app-server command execution statuses. (turn-206)

- Guardian command/execve assessments can now be converted directly into app-server-style CommandExecution item mappings, completing the lightweight transcript-item bridge while leaving guardian review notification metadata for a later slice. (turn-207)

- Core tool events now include a lightweight guardian auto-approval review notification helper for item/autoApprovalReview started/completed payloads, including turn-id fallback and app-server-style review/action field mapping. (turn-208)

- Exec JSON event processor coverage now pins Rust-compatible ignore behavior for guardian auto-approval review started/completed notifications, including explicit alias coverage for ItemGuardianApprovalReviewStarted. (turn-209)

- CommandExecutionItem now validates status against Rust app-server CommandExecutionStatus values and exports protocol CommandExecutionStatus constants. (turn-210)

- CommandExecutionItem now validates source against Rust app-server CommandExecutionSource values and exports protocol CommandExecutionSource constants. (turn-211)

- CommandExecutionItem now accepts string cwd values and normalizes them to Path, matching Rust app-server JSON path inputs and adjacent Python protocol item behavior. (turn-212)

- CommandExecutionItem numeric fields now reject bool values for exit_code and duration_ms, including the TurnItem.from_mapping alias parser path. (turn-213)

- CommandExecutionItem numeric fields now enforce Rust app-server ranges: exit_code must fit i32 and duration_ms must fit i64, including direct construction and mapping parse coverage. (turn-214)

- CommandExecutionItem now validates command_actions/commandActions as list-or-tuple input, preventing non-array values such as strings from being silently split during parsing. (turn-215)

- TurnItem now exposes tagged to_mapping() serialization, including a CommandExecution round trip through TurnItem.to_mapping()/from_mapping for app-server-compatible protocol shapes. (turn-216)

- Guardian-derived CommandExecution items now parse denied/timed-out execve argv through the existing Python shell-command parser and convert recognized ParsedCommand entries into app-server-style commandActions instead of always using a single unknown action. Added focused coverage for cat README.md producing a read action rooted at the assessment cwd. (turn-217)

- Normal exec_command begin/end to CommandExecution item conversion now maps ParsedCommand entries into app-server-style commandActions via the same helper used for guardian execve (`read`, `listFiles`, `search`, `unknown`), matching Rust `CommandAction::from_core_with_cwd` more closely than the previous raw parsed_cmd passthrough. Updated core tool-event coverage to use real ParsedCommand values. (turn-218)

- Exec approval request parsing now accepts app-server v2 camelCase fields (`itemId`, `approvalId`, `turnId`, `startedAtMs`, `networkApprovalContext`, `commandActions`, `availableDecisions`, etc.) in addition to the existing internal snake_case event shape. App-server commandActions are converted back into `ParsedCommand` entries, and app-server approval decisions (`accept`, `acceptForSession`, `acceptWithExecpolicyAmendment`, `applyNetworkPolicyAmendment`, `Cancel`) now map to internal `ReviewDecision` variants. (turn-219)

- Added an explicit response-side bridge for app-server v2 command execution approvals: internal `ReviewDecision` values can now be converted to `CommandExecutionRequestApprovalResponse` JSON decision shapes (`accept`, `acceptForSession`, `acceptWithExecpolicyAmendment`, `applyNetworkPolicyAmendment`, `decline`, `cancel`) without changing the existing internal `Op.exec_approval` rollout shape. (turn-220)

- File-change/apply-patch approval parsing now accepts app-server v2 camelCase fields (`itemId`, `turnId`, `startedAtMs`, `grantRoot`) and tolerates the v2 shape's absence of inline `changes`, since Rust sends the patch details through the associated file-change item. Added a response-side bridge from internal `ReviewDecision` to `FileChangeRequestApprovalResponse` decision shapes (`accept`, `acceptForSession`, `decline`, `cancel`). (turn-221)

- Request-permissions approval parsing now accepts app-server v2 camelCase fields (`itemId`, `turnId`, `startedAtMs`) and request permission profiles with `fileSystem` as well as internal `file_system`. Added an app-server response bridge for `PermissionsRequestApprovalResponse`, emitting `permissions`, `scope`, and optional `strictAutoReview` while preserving the internal snake_case rollout shape. (turn-222)

- Added a FileChange item app-server v2 mapping bridge: `FileChangeItem.to_app_server_mapping()` now emits `type: FileChange`, sorted `changes: [{path, kind, diff}]`, and v2-style status, matching Rust `ThreadItem::FileChange` / `convert_patch_changes` without changing the existing internal `TurnItem.to_mapping()` rollout shape. (turn-223)

- FileChange item parsing now accepts Rust app-server v2 `changes` list entries (`{path, kind, diff}`) in addition to the existing internal path-keyed mapping. Update entries with `kind: {type: update, movePath}` strip the app-server `Moved to: ...` display suffix back out of the internal unified diff while preserving `move_path`. (turn-224)

- Corrected FileChange v2 PatchChangeKind JSON shape using generated app-server TypeScript evidence: `kind` now emits tagged objects such as `{"type": "add"}` / `{"type": "delete"}` / `{"type": "update", "move_path": ...}` rather than bare strings or camelCase `movePath`. The parser remains tolerant of the earlier permissive forms. (turn-225)

- Tightened CommandAction v2 output against generated app-server TypeScript: `listFiles` now always includes `path` (nullable) and `search` now always includes both `query` and `path` (nullable), matching Rust serde/TS shapes instead of omitting `None` fields. (turn-226)

- FileChange item parsing now bridges Rust v2 `PatchApplyStatus::InProgress` to Python's internal in-progress representation (`status=None`), while continuing to emit `inProgress` through `to_app_server_mapping()`. (turn-227)

- TurnItem now has an explicit app-server v2 output bridge for the supported `commandExecution` and `fileChange` thread-item variants, including lower-camel Rust `ThreadItem` type tags and lower-camel parse aliases for those incoming app-server shapes. Unsupported item variants intentionally raise instead of pretending to have v2 parity. (turn-228)

- Command execution item lifecycle notifications now reuse `TurnItem.to_app_server_mapping()` for their `ThreadItem` payload, so `item/started`, `item/completed`, and guardian-derived command execution item mappings emit Rust app-server v2 `commandExecution` type tags instead of the Python-internal `CommandExecution` tag. (turn-229)

- Added a file-change lifecycle notification bridge for apply-patch `TurnItem` values: `FileChange` items now wrap into Rust app-server v2 `item/started` when status is in progress and `item/completed` for terminal patch statuses, with the payload produced by `TurnItem.to_app_server_mapping()` and the v2 `fileChange` tag. (turn-230)

- Added a generic `turn_item_lifecycle_notification(...)` helper for supported app-server v2 `ThreadItem` lifecycle payloads, currently covering `commandExecution` and `fileChange`. Command execution event wrapping now calls the shared `TurnItem.to_app_server_mapping()` path directly, and focused tool-event coverage now uses the real `TurnItem.item` field for patch items instead of a stale `.payload` alias. (turn-231)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `agentMessage`: Python's internal multi-part `AgentMessageContent::Text` list now concatenates into v2 `text`, `phase` is emitted as nullable `MessagePhase`, and internal memory citation `rollout_ids` bridge to v2 `threadIds` while preserving the internal model on parse. (turn-232)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `reasoning`: Python's internal `summary_text` and `raw_content` now bridge to v2 `summary` and `content`, matching Rust `ThreadItem::from(CoreTurnItem::Reasoning)` without changing the internal protocol item model. (turn-233)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `plan`: Python's internal `PlanItem(id, text)` now round-trips through the lower-camel `plan` `ThreadItem` shape used by app-server v2. (turn-234)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `contextCompaction`: Python's internal `ContextCompactionItem(id)` now round-trips through the lower-camel `contextCompaction` `ThreadItem` shape. (turn-235)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `userMessage`: Python's internal `UserInput` variants now bridge to v2 `text`, `image` (`url`), `localImage`, `skill`, and `mention` shapes, including `TextElement.byteRange` conversion while preserving the internal `image_url` / `local_image` / `byte_range` model on parse. (turn-236)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `hookPrompt`: Python's internal `HookPromptItem(id, fragments)` now round-trips through lower-camel `hookPrompt`, reusing the existing `HookPromptFragment` `hookRunId` serializer. (turn-237)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `webSearch`: Python's internal `WebSearchItem` now emits lower-camel `webSearch`, and `WebSearchAction` variants bridge internal `open_page` / `find_in_page` to v2 `openPage` / `findInPage` while preserving parse round trips. (turn-238)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `imageView`: Python's internal `ImageViewItem(id, path)` now round-trips through lower-camel `imageView` with a string path payload. (turn-239)

- Extended `TurnItem.to_app_server_mapping()` and parsing aliases to cover Rust app-server v2 `imageGeneration`: Python's internal `ImageGenerationItem` now emits lower-camel `imageGeneration`, bridges `revised_prompt` to `revisedPrompt`, and preserves optional `savedPath` parsing/serialization. (turn-240)

- Exec event processing now reuses `TurnItem.to_app_server_mapping()` when normalizing typed Python `TurnItem` values into app-server-style notification items, replacing older hand-written mappings for supported core variants and allowing lower-camel app-server v2 notification items to parse through the shared protocol bridge. (turn-241)

- Exec file-change item normalization now understands Rust app-server v2 `PatchChangeKind` objects such as `{"type": "add"}` / `{"type": "delete"}` / `{"type": "update", ...}` when rendering human output or JSON thread items, so v2 `fileChange` payloads no longer collapse non-update changes to the default `update` label. (turn-242)

- Added a protocol-level `turn_to_app_server_mapping(...)` helper for Rust app-server v2 `Turn` payloads, aggregating supported `TurnItem.to_app_server_mapping()` outputs with validated `itemsView`, `status`, `error`, `startedAt`, `completedAt`, and `durationMs` fields for future `turn/started` and `turn/completed` notification reuse. (turn-243)

- Added protocol-level Rust app-server v2 turn notification envelope helpers: `turn_started_notification(...)` produces `method: "turn/started"` with an in-progress `Turn`, and `turn_completed_notification(...)` produces `method: "turn/completed"` with a terminal `Turn`, both reusing `turn_to_app_server_mapping(...)`. (turn-244)

- Added exec-facing turn lifecycle notification wrappers, `exec_turn_started_notification(...)` and `exec_turn_completed_notification(...)`, which reuse the protocol-level Rust app-server v2 turn envelope helpers and are consumable by the existing exec event processors. (turn-245)

- Local exec HTTP failure rendering now uses the exec-facing Rust app-server v2 `exec_turn_completed_notification(...)` helper instead of hand-writing a partial `turn/completed` envelope, keeping this local-runtime error path aligned with the shared v2 `Turn` payload shape. (turn-246)









