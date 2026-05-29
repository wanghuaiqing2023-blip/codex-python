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


