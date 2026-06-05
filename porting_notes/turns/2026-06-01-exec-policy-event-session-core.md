# Exec Policy, Event Processor, And Session Loop Core

## Scope

- Continued the graph-guided core runtime path around command approval, `exec --json` event projection, remote exec loop handling, and turn request construction.
- Kept the work inside the common CLI/runtime flow and avoided expanding MCP/plugin internals beyond JSON compatibility needed by the exec event stream.

## Upstream graph/source slice

- Graph-guided files used:
  - `codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs`
  - `codex-rs/protocol/src/approvals.rs`
  - `codex-rs/protocol/src/items.rs`
  - `codex-rs/exec/src/event_processor.rs`
  - `codex-rs/core/src/session/turn.rs`
- Rust source confirmed:
  - Intercepted exec policy has an explicit shell-wrapper parsing toggle; when disabled, the outer intercepted program/argv remains the policy command.
  - Shell escalation chooses `TurnDefault`, `Unsandboxed`, or a resolved permission-profile escalation from the request sandbox permission mode, with additional permissions already normalized into the first-attempt policy.
  - `unified_exec_options` starts from `ExecExpiration::DefaultTimeout` and converts it to timeout-or-cancellation only when a network-denial cancellation token is attached.
  - Unix shell escalation wire values use path display strings and framed socket payloads; fd passing is Unix-specific, so Python keeps a lightweight compatibility path for Windows-hosted tests.
  - `ExecPolicyAmendment` is a token vector, not a string-like iterable.
  - Turn request input ordering is prompt input as-is; project/user instructions are carried by initial context rather than injected into each turn's input list.
  - `codex exec --json` event items preserve explicit null fields where clients depend on the stable item schema, while app-server raw items should not be reparsed and reserialized unnecessarily during backfill.

## Python changes

- `pycodex/core/exec_policy.py`
  - Added a default `enable_shell_wrapper_parsing=True` for intercepted exec policy helper calls.
- `pycodex/core/__init__.py`
  - Stopped the lower-level tool-runtime helper from overwriting the exported exec-policy helper with the same name.
  - Exported the shell socket length-prefixed payload helper used by the low-level shell runtime boundary tests.
- `pycodex/core/exec.py`
  - Made `ExecExpiration.default_timeout()` pass an explicit `None` cancellation so the Python classmethod name does not leak into the dataclass field default.
- `pycodex/core/tool_runtimes.py`
  - Emitted POSIX-style paths for shell escalation session/request wire data and local execv callbacks.
  - Kept client-side split super-exec callbacks high-level when no socket client is involved, while socket-client exchanges send the Rust-style length-prefixed JSON payload.
  - Added lightweight fd-passing constant fallbacks for Windows hosts and tightened stream send/receive behavior around short writes, fd transfer chunks, and length-prefixed result parsing.
  - Defaulted shell escalation request environment capture to an empty mapping unless a caller supplies an environment, avoiding host-environment leakage into synthetic client exchanges.
- `pycodex/protocol/models.py`
  - Allowed `FileSystemPermissions.from_read_write_roots()` to accept the compatibility keywords `read_roots` and `write_roots`.
- `pycodex/protocol/approvals.py`
  - Tightened `ExecPolicyAmendment.new()` so strings are rejected before tuple conversion.
- `pycodex/exec/events.py`
  - Preserved explicit `None` values in JSON event item payloads.
  - Avoided web-search raw ids overwriting exec-generated item ids.
  - Emitted POSIX-style paths for JSON event file-change/path payloads.
- `pycodex/exec/event_processor.py`
  - Added a compatibility `.status` property on `CodexStatus` for callers that handle collected results and raw statuses uniformly.
  - Kept typed command failure rendering user-friendly while preserving existing app-server notification rendering.
  - Preserved raw MCP app-server payload omission semantics where fields were absent.
- `pycodex/exec/session.py`
  - Preserved raw thread-read JSON items during turn-completed backfill and only serialized actual `TurnItem` objects to app-server v2 shape.
  - Included empty instruction config for resume bootstrap requests where the app-server shape expects it.
  - Treated final non-retry server error notifications as loop-terminal so websocket closure after the error is not reported as a second run-loop failure.
- Tests were adjusted where prior expectations contradicted the Rust-aligned prompt/context behavior or had a typo around an undefined `stderr` capture.

## Validation

- `python -m unittest tests.test_protocol_approvals tests.test_protocol_protocol`
  - 66 tests passed.
- `python -m unittest tests.test_exec_event_processor`
  - 76 tests passed.
- `python -m unittest tests.test_core_client_common tests.test_core_turn_request tests.test_core_turn_metadata tests.test_core_turn_timing tests.test_core_turn_sampler tests.test_core_http_transport tests.test_core_context tests.test_core_exec_policy tests.test_core_exec_env tests.test_exec_cli tests.test_exec_session tests.test_exec_event_processor tests.test_exec_websocket`
  - 283 tests passed.
- `python -m unittest tests.test_protocol_auth_account tests.test_protocol_approvals tests.test_protocol_agent_path tests.test_protocol_ids_tool_user_input tests.test_protocol_exec_output tests.test_protocol_error tests.test_protocol_config_types tests.test_protocol_models_content tests.test_protocol_mcp_dynamic_tools tests.test_protocol_items tests.test_protocol_network_policy tests.test_protocol_num_format tests.test_protocol_user_input tests.test_protocol_token_usage_display tests.test_protocol_small_modules tests.test_protocol_shell_environment tests.test_protocol_protocol tests.test_protocol_permission_models tests.test_protocol_parse_command_plan_tool tests.test_protocol_openai_models tests.test_core_client_common tests.test_core_turn_request tests.test_core_turn_metadata tests.test_core_turn_timing tests.test_core_turn_sampler tests.test_core_http_transport tests.test_core_context tests.test_core_exec_policy tests.test_core_exec_env tests.test_exec_cli tests.test_exec_session tests.test_exec_event_processor tests.test_exec_websocket tests.test_core_tool_router tests.test_core_stream_events_utils`
  - 741 tests passed.
- `python -m unittest tests.test_core_tool_runtimes`
  - 110 tests passed.
- `python -m unittest discover -s tests -p "test_protocol_*.py"`
  - 300 tests passed.
- `python -m unittest tests.test_core_client_common tests.test_core_turn_request tests.test_core_turn_metadata tests.test_core_turn_timing tests.test_core_turn_sampler tests.test_core_http_transport tests.test_core_context tests.test_core_exec_policy tests.test_core_exec_env tests.test_core_tool_runtimes tests.test_exec_cli tests.test_exec_session tests.test_exec_event_processor tests.test_exec_websocket tests.test_core_tool_router tests.test_core_stream_events_utils`
  - 551 tests passed.

## Follow-up debt

- Broader whole-suite discovery still needs a pass once unrelated modified files in the workspace settle.
- `tests.test_core_client` remains pytest-only in this workspace because pytest is not installed.
