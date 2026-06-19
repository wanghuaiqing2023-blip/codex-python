# codex-app-server-test-client src/lib.rs status

Rust module: `codex/codex-rs/app-server-test-client/src/lib.rs`

Python module: `pycodex/app_server_test_client/__init__.py`

Status: `complete`

## Covered Contract

This pass maps the public facade and pure routing/helper behavior from Rust
`src/lib.rs`:

- constants:
  - `NOTIFICATIONS_TO_OPT_OUT`
  - `DEFAULT_ANALYTICS_ENABLED`
  - `OTEL_SERVICE_NAME`
  - `TRACE_DISABLED_MESSAGE`
- endpoint resolution:
  - `resolve_endpoint(...)`
  - `resolve_shared_websocket_url(...)`
- dynamic tool argument handling:
  - `parse_dynamic_tools_arg(...)`
  - `ensure_dynamic_tools_unused(...)`
- shell quoting helper
- trace and multiline output helpers:
  - `trace_url_from_context(...)`
  - `current_span_w3c_trace_context(...)`
  - `trace_summary_capture(...)`
  - `print_trace_summary(...)`
  - `print_multiline_with_prefix(...)`
- tracing provider and live client command wrapper:
  - `TestClientTracing.initialize(...)`
  - `with_client(...)`
- protocol-shaped `model_list_params(...)` and `thread_list_params(...)`
  builders
- protocol-shaped thread/turn construction helpers:
  - `dynamic_tool_spec_to_json(...)`
  - `text_user_input(...)`
  - `read_only_sandbox_policy(...)`
  - `danger_full_access_sandbox_policy(...)`
  - `thread_start_params(...)`
  - `turn_start_params(...)`
- helper-order predicate
- public `send_message_v2(...)` facade, with transport execution delegated to
  the default live runner or an injectable runner
- stdio client construction and payload transport:
  - `StdioTransport.spawn(...)`
  - `StdioTransport.write_payload(...)`
  - `StdioTransport.read_payload(...)`
  - `CodexClient.connect(...)` for `SpawnCodex`
- websocket client construction and payload transport:
  - `WebSocketTransport.connect(...)` through the real
    `pycodex.exec.websocket.StdlibWebSocket` interface
  - `WebSocketTransport.write_payload(...)`
  - `WebSocketTransport.read_payload(...)`
  - `CodexClient.connect(...)` for `ConnectWs`
- background app-server helper:
  - `BackgroundAppServer.spawn(...)`
  - `BackgroundAppServer.close(...)`
- serve launcher helpers:
  - `serve_command_line(...)`
  - `kill_listeners_on_same_port(...)`
  - `serve(...)`
- client-interface message orchestration helpers:
  - `send_message_v2_with_policies(...)`
  - `trigger_cmd_approval(...)`
  - `trigger_patch_approval(...)`
  - `no_trigger_cmd_approval(...)`
  - `send_follow_up_v2(...)`
  - `resume_message_v2(...)`
  - `trigger_zsh_fork_multi_cmd_approval(...)`
- client-interface command orchestration helpers:
  - `test_login(...)`
  - `get_account_rate_limits(...)`
  - `model_list(...)`
  - `thread_list(...)`
  - `watch(...)`
  - `thread_resume_follow(...)`
  - `thread_elicitation_params(...)`
  - `thread_increment_elicitation(...)`
  - `thread_decrement_elicitation(...)`
- `run(...)` command parser and dispatch for the full Rust `CliCommand`
  inventory, with transport/live execution handled by `DefaultClientRunner` or
  an injectable runner
- default live command runner wiring:
  - `DefaultClientRunner.send_message_v2_endpoint(...)`
  - `DefaultClientRunner.send_message(...)`
  - `DefaultClientRunner.resume_message_v2(...)`
  - `DefaultClientRunner.thread_resume_follow(...)`
  - `DefaultClientRunner.watch(...)`
  - `DefaultClientRunner.trigger_cmd_approval(...)`
  - `DefaultClientRunner.trigger_patch_approval(...)`
  - `DefaultClientRunner.no_trigger_cmd_approval(...)`
  - `DefaultClientRunner.send_follow_up_v2(...)`
  - `DefaultClientRunner.trigger_zsh_fork_multi_cmd_approval(...)`
  - `DefaultClientRunner.test_login(...)`
  - `DefaultClientRunner.get_account_rate_limits(...)`
  - `DefaultClientRunner.model_list(...)`
  - `DefaultClientRunner.thread_list(...)`
  - `DefaultClientRunner.thread_increment_elicitation(...)`
  - `DefaultClientRunner.thread_decrement_elicitation(...)`
  - `DefaultClientRunner.live_elicitation_timeout_pause(...)`
  - `DefaultClientRunner.serve(...)`
- live elicitation timeout harness:
  - `default_live_elicitation_script_path(...)`
  - `live_elicitation_timeout_pause(...)`
- in-memory `CodexClient` JSON-RPC core:
  - payload read/write
  - request write and response wait
  - notification caching
  - initialize handshake request plus `initialized` notification
  - command/file approval server-request auto responses
  - helper-output completion marker tracking
  - account login request helpers for ChatGPT browser and device-code flows
  - account login completion notification wait loop
  - default model/thread list requests using Rust protocol camelCase params
  - `stream_turn(...)` notification loop state updates for command-output
    deltas, command execution item start/completion, aggregated command output,
    turn completion status/error capture, and helper-completion ordering guard
  - `stream_turn(...)` live output side effects for thread/turn start,
    assistant deltas, command-output deltas, terminal stdin echo, item
    start/completion, turn completion/errors, MCP progress, and unknown
    notifications
  - bounded `stream_notifications_forever(...)` helper for deterministic
    in-memory validation

## Remaining Contract

No local `src/lib.rs` public facade/API, command orchestration, live client
wrapper, transport, stream-turn, live elicitation, or trace-summary behavior is
currently tracked as pending for this crate module.

Python keeps the actual OTEL provider construction dependency-light and
injectable; this preserves the module boundary without vendoring `codex-core`
OTEL internals into this package.

## Evidence

- Rust source: `codex/codex-rs/app-server-test-client/src/lib.rs`
- Python source: `pycodex/app_server_test_client/__init__.py`
- Python test: `tests/test_app_server_test_client_lib_rs.py`

Focused validation passed:

```text
python -m pytest -q tests/test_app_server_test_client_lib_rs.py tests/test_app_server_test_client_main_rs.py
45 passed
```
