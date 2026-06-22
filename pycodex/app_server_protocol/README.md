# pycodex.app_server_protocol

Canonical Python package for selected protocol types ported from:

- Rust crate: `codex/codex-rs/app-server-protocol`
- Current modules: selected `protocol/v2/*.rs` protocol shapes

This package currently contains selected app-server protocol shapes used by connector and tool-discovery paths.

## Module correspondence

| Rust module | Python module |
| --- | --- |
| `lib.rs` | `pycodex/app_server_protocol/__init__.py` |
| `experimental_api.rs` | `pycodex/app_server_protocol/experimental_api.py` |
| `protocol/event_mapping.rs` | `pycodex/app_server_protocol/event_mapping.py` |
| `protocol/common.rs` | `pycodex/app_server_protocol/common.py` |
| `export.rs` | `pycodex/app_server_protocol/export.py` |
| `jsonrpc_lite.rs` | `pycodex/app_server_protocol/jsonrpc_lite.py` |
| `schema_fixtures.rs` | `pycodex/app_server_protocol/schema_fixtures.py` |
| `protocol/item_builders.rs` | `pycodex/app_server_protocol/item_builders.py` |
| `protocol/thread_history.rs` | `pycodex/app_server_protocol/thread_history.py` |
| `protocol/v1.rs` | `pycodex/app_server_protocol/v1.py` |
| `protocol/v2/mod.rs` | `pycodex/app_server_protocol/__init__.py` |
| `protocol/v2/account.rs` | `pycodex/app_server_protocol/account.py` |
| `protocol/v2/apps.rs` | `pycodex/app_server_protocol/apps.py` |
| `protocol/v2/attestation.rs` | `pycodex/app_server_protocol/attestation.py` |
| `protocol/v2/collaboration_mode.rs` | `pycodex/app_server_protocol/collaboration_mode.py` |
| `protocol/v2/command_exec.rs` | `pycodex/app_server_protocol/command_exec.py` |
| `protocol/v2/config.rs` | `pycodex/app_server_protocol/config.py` |
| `protocol/v2/environment.rs` | `pycodex/app_server_protocol/environment.py` |
| `protocol/v2/experimental_feature.rs` | `pycodex/app_server_protocol/experimental_feature.py` |
| `protocol/v2/feedback.rs` | `pycodex/app_server_protocol/feedback.py` |
| `protocol/v2/fs.rs` | `pycodex/app_server_protocol/fs.py` |
| `protocol/v2/hook.rs` | `pycodex/app_server_protocol/hook.py` |
| `protocol/v2/item.rs` | `pycodex/app_server_protocol/item.py` |
| `protocol/v2/mcp.rs` | `pycodex/app_server_protocol/mcp.py` |
| `protocol/v2/model.rs` | `pycodex/app_server_protocol/model.py` |
| `protocol/v2/notification.rs` | `pycodex/app_server_protocol/notification.py` |
| `protocol/v2/permissions.rs` | `pycodex/app_server_protocol/permissions.py` |
| `protocol/v2/plugin.rs` | `pycodex/app_server_protocol/plugin.py` |
| `protocol/v2/process.rs` | `pycodex/app_server_protocol/process.py` |
| `protocol/v2/realtime.rs` | `pycodex/app_server_protocol/realtime.py` |
| `protocol/v2/remote_control.rs` | `pycodex/app_server_protocol/remote_control.py` |
| `protocol/v2/review.rs` | `pycodex/app_server_protocol/review.py` |
| `protocol/v2/shared.rs` | `pycodex/app_server_protocol/shared.py` |
| `protocol/v2/thread.rs` | `pycodex/app_server_protocol/thread.py` |
| `protocol/v2/thread_data.rs` | `pycodex/app_server_protocol/thread_data.py` |
| `protocol/v2/turn.rs` | `pycodex/app_server_protocol/turn.py` |
| `protocol/v2/windows_sandbox.rs` | `pycodex/app_server_protocol/windows_sandbox.py` |
| MCP elicitation compatibility structs used by older imports | `pycodex/app_server_protocol/elicitation.py` |

## `lib.rs`

`pycodex.app_server_protocol.__init__` mirrors the crate-root re-export
surface for modules already ported in Python: `experimental_api`, `export`,
`jsonrpc_lite`, selected `protocol/v2::*`, and `schema_fixtures`.

The Rust crate root also re-exports `protocol::common`, `event_mapping`, and
`thread_history`. Python keeps them as separate Rust module boundaries rather
than folding their behavior into the `lib.rs` mapping.

## `experimental_api.rs`

`pycodex.app_server_protocol.experimental_api` mirrors the crate-level
experimental API helpers: the `ExperimentalApi` protocol, `ExperimentalField`
metadata, `experimental_fields()`, `experimental_required_message()`, and
nested `experimental_reason()` traversal for optional values, lists/tuples, and
maps.

Rust uses derive macros and `inventory` to collect experimental fields. Python
uses explicit `register_experimental_field()` and `clear_experimental_fields()`
helpers instead, which keeps the same protocol contract without depending on a
macro/plugin system.

## `export.rs`

`pycodex.app_server_protocol.export` mirrors the schema export module's
Python-carryable behavior: generation options and public entrypoints,
TypeScript header/index generation, top-level TypeScript union/interface
filtering, experimental field/method pruning for TypeScript and JSON schema
trees, namespace/reference rewrites, schema bundle flattening for v2, and
deterministic file helpers.

Rust's actual schema emission is driven by `ts-rs` and `schemars` derive
macros. Python keeps the public `generate_*` entrypoints but requires injected
generator callbacks and raises `NotImplementedError` when macro-owned emission
is requested without one.

## `jsonrpc_lite.rs`

`pycodex.app_server_protocol.jsonrpc_lite` mirrors the crate-level lite
JSON-RPC envelope types: `RequestId`, `JSONRPCRequest`,
`JSONRPCNotification`, `JSONRPCResponse`, `JSONRPCErrorError`,
`JSONRPCError`, `JSONRPCMessage`, and the `JSONRPC_VERSION` constant.

The Rust module intentionally does not emit or require a top-level
`jsonrpc: "2.0"` field. Python preserves that lighter app-server wire shape,
keeps request ids as untagged string-or-i64 values, and omits optional
`params`, `trace`, and error `data` fields when absent.

## `schema_fixtures.rs`

`pycodex.app_server_protocol.schema_fixtures` mirrors schema fixture file-tree
helpers: reading `typescript/` and `json/` fixture subtrees, normalizing
TypeScript line endings and generated headers, canonicalizing JSON object and
selected schema-array ordering, emptying output directories, and exposing
`SchemaFixtureOptions`.

Actual TypeScript/JSON schema generation is still owned by the Rust
`ts-rs`/`schemars` derive path. Python keeps the fixture write entrypoints and
requires injected generator callbacks through the export-module boundary.

## `protocol/item_builders.rs`

`pycodex.app_server_protocol.item_builders` mirrors the shared builders that
project core approval, command execution, patch-apply, and guardian assessment
events into presentation-oriented v2 `ThreadItem` values. The module accepts
the already-ported core event dataclasses as well as mapping/duck-typed payloads
from neighboring modules.

`protocol/common.rs::ServerNotification` is a separate module boundary, so this
module carries a small `ServerNotification` facade for typed payloads emitted by
builder/event-mapping modules. Its wire method lookup now delegates to
`pycodex.app_server_protocol.common` when available.

## `protocol/common.rs`

`pycodex.app_server_protocol.common` mirrors the Rust common protocol layer:
`AuthMode` re-export, client/server request and notification method registries,
JSON-RPC request/notification conversion helpers, client request serialization
scopes, and fuzzy file search params/responses/session notifications.

Python keeps neighboring v1/v2 request payloads as JSON-compatible values at
this boundary, while preserving Rust's method names and keyed serialization
scope behavior for thread, command exec, process, fuzzy-search, fs-watch,
global, shared-read, and MCP OAuth families.

## `protocol/event_mapping.rs`

`pycodex.app_server_protocol.event_mapping` mirrors the Rust stateless
`item_event_to_server_notification` helper. It maps selected core `EventMsg`
variants into v2 app-server notification payloads for dynamic tool responses,
collaboration tool calls, streaming agent/plan/reasoning deltas, item
lifecycle events, patch updates, command execution lifecycle/output deltas, and
terminal interactions.

The full `ServerNotification` enum and JSON-RPC method serialization still
belong to `protocol/common.rs`; until that module is ported, this mapping
returns the existing lightweight notification facade.

## `protocol/thread_history.rs`

`pycodex.app_server_protocol.thread_history` mirrors the rollout replay reducer
that reconstructs v2 `Turn` values from persisted `RolloutItem` and `EventMsg`
entries. It exposes `build_turns_from_rollout_items` and
`ThreadHistoryBuilder`, preserving active-turn snapshots, explicit turn
boundaries, rollback truncation, compaction-only turn retention, item upsert by
id, and late turn-scoped item routing.

The module reuses `item_builders` and `event_mapping` for exec, patch,
guardian, dynamic-tool, and collaboration projections so those behaviors are
not duplicated across app-server protocol modules.

## `protocol/v1.rs`

`pycodex.app_server_protocol.v1` mirrors the legacy app-server v1 protocol
payloads re-exported by the Rust crate root: initialize request/response
types, conversation summary and git metadata shapes, auth status payloads,
approval request/response payloads, one-off command params, saved config,
tools, sandbox settings, and interrupt response.

Python reuses the existing core protocol value objects for thread ids, review
decisions, file changes, parsed commands, sandbox policy, session source, and
config enums rather than duplicating those adjacent crate contracts.

## `protocol/v2/mod.rs`

Rust `protocol/v2/mod.rs` declares every v2 protocol submodule and re-exports
their public items with `pub use ...::*`. Python mirrors that aggregation in
`pycodex.app_server_protocol.__init__`: each completed v2 protocol module is
imported and listed in `__all__` so callers can use the package as the v2
protocol surface.

The Rust `#[cfg(test)] mod tests` declaration is tracked separately from this
aggregation boundary. Runtime JSON schema generation/export helpers also live
outside `protocol/v2/mod.rs` and remain separate crate-level work.

## `protocol/v2/account.rs`

`pycodex.app_server_protocol.account` mirrors the account protocol payloads:
tagged account variants, login start/cancel/response shapes, auth-token
refresh, add-credits nudge, get-account, rate-limit snapshots, and account
notifications.

The module preserves Rust's tagged `type` variants such as `apiKey`,
`chatgpt`, `chatgptDeviceCode`, `chatgptAuthTokens`, and `amazonBedrock`.
False default booleans such as `codex_streamlined_login` and `refresh_token`
are omitted from serialized mappings. `PlanType` is reused from
`pycodex.protocol.account` for the stable plan wire values.

## `protocol/v2/apps.rs`

`pycodex.app_server_protocol.apps` mirrors the Rust v2 app-list contract:
`AppsListParams`, `AppBranding`, `AppReview`, `AppScreenshot`,
`AppMetadata`, `AppInfo`, `AppSummary`, `AppsListResponse`, and
`AppListUpdatedNotification`.

Python keeps snake_case attribute names and the existing snake_case
`to_mapping()` compatibility surface, while `from_mapping()` also accepts
Rust serde camelCase keys and `to_camel_mapping()` emits Rust wire names.
`AppInfo.is_enabled` follows Rust's `default_enabled` behavior and defaults
to `True` when omitted.

## `protocol/v2/attestation.rs`

`pycodex.app_server_protocol.attestation` mirrors the client attestation
request/response pair: an empty `AttestationGenerateParams` object and
`AttestationGenerateResponse` containing the opaque `token` string.

## `protocol/v2/collaboration_mode.rs`

`pycodex.app_server_protocol.collaboration_mode` mirrors the experimental
collaboration mode list API shapes: `CollaborationModeListParams`,
`CollaborationModeMask`, and `CollaborationModeListResponse`.

The Rust module converts from `codex_protocol::config_types`
`CollaborationModeMask`; Python mirrors this with
`CollaborationModeMask.from_core_mask()` and `to_core_mask()`, preserving the
Rust/Python three-state `reasoning_effort` behavior: field absent, explicit
`None`, or a concrete `ReasoningEffort`.

## `protocol/v2/command_exec.rs`

`pycodex.app_server_protocol.command_exec` mirrors the standalone command
execution protocol payloads: terminal sizing, command exec params/response,
stdin writes, terminate and PTY resize params/responses, output stream labels,
and output delta notifications.

Boolean defaults with Rust `skip_serializing_if` such as `tty`,
`stream_stdin`, `stream_stdout_stderr`, `disable_output_cap`,
`disable_timeout`, and `close_stdin` are omitted from serialized mappings when
false. `sandbox_policy` is kept as a SandboxPolicy-compatible mapping/object
because `SandboxPolicy` is owned by a neighboring module and is outside this
module's implementation boundary.

## `protocol/v2/config.rs`

`pycodex.app_server_protocol.config` mirrors the v2 app-server config protocol
surface: layer sources and precedence, effective config payloads, config
layers/origins, read/write params and responses, managed requirements,
external-agent migration payloads, config edits, text ranges, and warning
notifications.

The module stays at the app-server protocol layer. It preserves Rust serde
shapes such as camelCase layer tags, snake_case config fields, flattened
analytics/apps maps, default-enabled app config fields, singleton-or-list
ChatGPT workspace IDs, PascalCase managed hook buckets, and config layer source
precedence. It intentionally bridges only to already-existing shared protocol
enums where those enums own stable wire values.

## `protocol/v2/environment.rs`

`pycodex.app_server_protocol.environment` mirrors the environment add protocol
pair: `EnvironmentAddParams` with `environment_id` and `exec_server_url`, plus
the empty `EnvironmentAddResponse`.

## `protocol/v2/experimental_feature.rs`

`pycodex.app_server_protocol.experimental_feature` mirrors the experimental
feature list and enablement-set protocol types, including
`ExperimentalFeatureStage`, feature metadata, pagination params/response, and
string-to-bool enablement maps.

## `protocol/v2/feedback.rs`

`pycodex.app_server_protocol.feedback` mirrors the feedback upload protocol
pair. `FeedbackUploadParams` preserves the Rust defaults and serde behavior:
`include_logs` defaults to `False` and is omitted from serialized mappings
when false, while `extra_log_files` accepts path strings or `Path` values and
serializes them as path strings. `FeedbackUploadResponse` contains the returned
`thread_id`.

## `protocol/v2/fs.rs`

`pycodex.app_server_protocol.fs` mirrors the filesystem RPC protocol payloads:
read/write file, create directory, metadata, read directory entries, remove,
copy, watch/unwatch, and change notifications.

All path fields follow Rust's `AbsolutePathBuf` contract and must be absolute
when parsed or constructed. `FsCopyParams.recursive` mirrors Rust's default
false plus `skip_serializing_if` behavior by omitting the field from serialized
mappings unless it is true.

## `protocol/v2/hook.rs`

`pycodex.app_server_protocol.hook` mirrors hook run protocol types: hook event,
handler, execution mode, scope, source, trust status, run status, output entry
kind, output entries, run summaries, and hook started/completed notifications.

`HookRunSummary.source` follows Rust's `default_hook_source()` and defaults to
`unknown` when omitted. `source_path` follows the Rust `AbsolutePathBuf`
contract and must be absolute.

## `protocol/v2/item.rs`

`pycodex.app_server_protocol.item` mirrors the v2 item protocol surface:
thread item tagged payloads, command/file approval decisions, parsed command
actions, memory citations, guardian review payloads, web-search actions,
command/file/MCP/dynamic/collab statuses, file patch changes, item lifecycle
notifications, approval request/response payloads, dynamic tool-call payloads,
and request-user-input payloads.

The module preserves Rust's tagged `type` and camelCase wire names while
staying at the protocol boundary. Complex payloads owned by neighboring
modules or by core runtime models are accepted and emitted as JSON-compatible
mappings. This keeps `item.py` aligned with `protocol/v2/item.rs` without
expanding into event processing or runtime conversion behavior.

## `protocol/v2/mcp.rs`

`pycodex.app_server_protocol.mcp` mirrors the v2 MCP app-server protocol
payloads: server inventory/status listing, resource read params/responses,
tool-call params/results/errors, refresh and OAuth login pairs, tool-call
progress and server status notifications, and elicitation request/response
shapes.

The module stays at the protocol boundary. MCP tools, resources, resource
templates, content blocks, structured content, and metadata are kept as JSON
values rather than implementing the MCP runtime. Elicitation schemas preserve
Rust wire names such as `$schema`, `requestedSchema`, `elicitationId`,
`toolsAndAuthOnly`, `structuredContent`, `isError`, and `_meta`.

## `protocol/v2/model.rs`

`pycodex.app_server_protocol.model` mirrors the v2 model catalog and capability
protocol shapes: provider capability read params/response, paginated model list
params/response, model availability NUX, model upgrade info, reasoning effort
options, service tiers, model records, reroute notifications, and verification
notifications.

Python preserves Rust wire names through `from_mapping()` camelCase support and
`to_camel_mapping()`. Defaults mirror Rust serde defaults for input modalities
(`text`, `image`), personality support, additional speed tiers, service tiers,
default service tier, and model `is_default`.

## `protocol/v2/notification.rs`

`pycodex.app_server_protocol.notification` mirrors the simple app-server
notification payloads: deprecation notices, warnings, guardian warnings, turn
error notifications, and server-request resolution notifications.

`ServerRequestResolvedNotification` reuses the existing protocol `RequestId`
wrapper so Rust's untagged string-or-integer request id shape is preserved.
`ErrorNotification.error` is kept as a TurnError-compatible mapping/object
because `TurnError` is owned by `protocol/v2/thread_data.rs` and is outside this
module's implementation boundary.

## `protocol/v2/permissions.rs`

`pycodex.app_server_protocol.permissions` mirrors the v2 app-server permission
protocol types: network approval contexts, additional network/filesystem
permission overlays, request/granted permission profiles, filesystem path and
sandbox entries, permission profile list payloads, active profiles, v2
`SandboxPolicy`, exec/network policy amendments, and permission approval
params/responses.

The module preserves Rust v2 wire shapes, including camelCase sandbox policy
variants such as `dangerFullAccess`, `readOnly`, `externalSandbox`, and
`workspaceWrite`, the legacy `current_working_directory` alias for
`project_roots`, transparent array serialization for exec policy amendments,
and rejection of restricted legacy read-only access fields. It also provides
focused `from_core()`/`to_core()` bridges to the existing `pycodex.protocol`
permission and sandbox models.

## `protocol/v2/plugin.rs`

`pycodex.app_server_protocol.plugin` mirrors the v2 plugin, marketplace, skill,
and hook protocol payloads: skill and hook list params/responses, marketplace
add/remove/upgrade payloads, plugin list/read/install/uninstall payloads,
plugin sharing payloads, plugin/marketplace summaries, skill metadata, skill
dependencies, plugin sources, and skills-changed notifications.

This module is intentionally a compatibility protocol layer. It preserves Rust
wire names, enum values, defaults such as `PluginAvailability.AVAILABLE`, and
legacy ignored fields such as removed `forceRemoteSync` request fields, while
leaving plugin discovery, marketplace sync, sharing, installation, hook
execution, and skill scanning runtime behavior outside this module boundary.

## `protocol/v2/process.rs`

`pycodex.app_server_protocol.process` mirrors the standalone process protocol
payloads: terminal sizing, spawn params/response, stdin writes, kill and PTY
resize params/responses, output stream deltas, and process exit notifications.

`ProcessSpawnParams.output_bytes_cap` and `timeout_ms` preserve Rust's
double-option serde shape: omitted means server default, explicit `None` means
JSON `null`, and an integer supplies a concrete cap/timeout. Boolean defaults
such as `tty`, `stream_stdin`, `stream_stdout_stderr`, and `close_stdin` are
omitted from serialized mappings when false.

## `protocol/v2/realtime.rs`

`pycodex.app_server_protocol.realtime` mirrors the experimental thread
realtime protocol payloads: audio chunks, start transport/params/response,
append audio/text, stop, list voices, started/item/transcript/audio/SDP/error
and closed notifications.

The module reuses core protocol realtime enums and voice-list types where the
Rust module does. `ThreadRealtimeStartParams.prompt` preserves Rust's
double-option serde shape: omitted means no prompt field, explicit `None`
means JSON `null`, and a string supplies prompt text.

## `protocol/v2/review.rs`

`pycodex.app_server_protocol.review` mirrors the review start protocol shapes:
review delivery mode, tagged review targets, start params, and start response.

`ReviewTarget` preserves Rust's tagged `type` variants for uncommitted changes,
base branch, commit, and custom instructions. `ReviewStartResponse.turn` is kept
as a Turn-compatible mapping/object because `Turn` is owned by
`protocol/v2/thread_data.rs` and is outside this module's boundary.

## `protocol/v2/shared.rs`

`pycodex.app_server_protocol.shared` mirrors shared v2 protocol enums and
helpers: `default_enabled`, `NonSteerableTurnKind`, `CodexErrorInfo`,
`AskForApproval`, `GranularAskForApproval`, `ApprovalsReviewer`, and
`SandboxMode`.

`CodexErrorInfo` preserves Rust's external enum JSON shape with camelCase unit
variants and object variants such as `responseTooManyFailedAttempts` and
`activeTurnNotSteerable`. `ApprovalsReviewer` serializes `AUTO_REVIEW` as the
legacy wire value `guardian_subagent` and accepts the `auto_review` alias.
`GranularAskForApproval` preserves Rust's missing optional flags defaulting to
false.

## `protocol/v2/thread_data.rs`

`pycodex.app_server_protocol.thread_data` mirrors the shared thread data
payloads used by the v2 app-server protocol: `SessionSource`, `ThreadSource`,
`GitInfo`, `Thread`, `Turn`, `TurnItemsView`, and `TurnError`.

The module preserves Rust wire names for session sources (`cli`, `vscode`,
`exec`, `appServer`, `custom`, `subAgent`, `unknown`), snake_case
`ThreadSource` values, default `TurnItemsView.full`, thread/turn timestamp
fields, and `TurnError` display behavior. `Thread.status`, `Turn.status`,
`ThreadItem`, and `CodexErrorInfo` are treated as neighboring protocol
constraints; already-ported `ThreadItem` values are accepted directly, while
status/error-info payloads remain JSON-compatible.

## `protocol/v2/thread.rs`

`pycodex.app_server_protocol.thread` mirrors the v2 thread API protocol
surface: thread start/resume/fork/settings/archive/unsubscribe/goal/memory
params and responses, thread listing/search/read payloads, turn listing and
item listing payloads, token usage payloads, thread status variants, dynamic
tool specs, and thread lifecycle notifications.

The module preserves Rust tagged and untagged wire shapes such as
`ThreadStatus.active`, `ThreadListCwdFilter`, `ThreadStartSource`,
`ThreadSourceKind`, `ThreadMemoryMode`, `ThreadGoalStatus`, and
`DynamicToolSpec.deferLoading`. Runtime session storage, subscription
management, command execution, and goal orchestration are intentionally kept
outside this module; neighboring thread data, turn, item, and config/runtime
types are accepted as already-ported protocol objects or JSON-compatible
payloads.

## `protocol/v2/turn.rs`

`pycodex.app_server_protocol.turn` mirrors the v2 turn protocol surface:
turn status, start/steer/interrupt params and responses, turn-scoped
environment params, additional context entries, byte ranges, text elements,
user input variants, started/completed/diff/plan notifications, usage counts,
and plan step payloads.

The module preserves Rust tagged user-input variants (`text`, `image`,
`localImage`, `skill`, `mention`), camelCase fields such as
`responsesapiClientMetadata`, `runtimeWorkspaceRoots`, `serviceTier`,
`byteRange`, and `textElements`, and the double-option service tier behavior
through an `UNSET` sentinel. Runtime config/model types owned by neighboring
modules remain JSON-compatible protocol values.

## `protocol/v2/remote_control.rs`

`pycodex.app_server_protocol.remote_control` mirrors the remote-control
connection status protocol types and the conversion from
`RemoteControlStatusChangedNotification` into enable/disable responses.

## `protocol/v2/windows_sandbox.rs`

`pycodex.app_server_protocol.windows_sandbox` mirrors the Windows sandbox
setup/readiness protocol types, including `WindowsSandboxSetupMode`,
`WindowsSandboxReadiness`, setup start/response notifications, readiness
response, and world-writable warning notifications. `cwd` follows the Rust
`AbsolutePathBuf` contract and must be absolute when present.
