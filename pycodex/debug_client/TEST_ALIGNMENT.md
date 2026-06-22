# codex-debug-client test alignment

Rust crate: `codex-debug-client`

Python package: `pycodex/debug_client`

Status: `complete`

Module mapping:

- `codex/codex-rs/debug-client/src/commands.rs` ->
  `pycodex/debug_client/commands.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/output.rs` ->
  `pycodex/debug_client/output.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/state.rs` ->
  `pycodex/debug_client/state.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/reader.rs` ->
  `pycodex/debug_client/reader.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/client.rs` ->
  `pycodex/debug_client/client.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/main.rs` ->
  `pycodex/debug_client/main.py` and `pycodex/debug_client/__main__.py`
  (`complete_candidate`)

Rust behavior prepared in `tests/test_debug_client_commands_rs.py`:

- message parsing for non-command input
- `:help` and `:h`
- `:quit`, `:q`, and `:exit`
- `:new`
- `:resume <thread-id>`
- `:use <thread-id>`
- `:refresh-thread`
- empty input and empty command handling
- missing `thread-id` parse errors
- unknown command parse error and message text

Rust behavior prepared in `tests/test_debug_client_output_rs.py`:

- `server_json_line_writes_to_configured_file`
- filtered server JSON line behavior without an output file
- prompt clear/redraw around server output
- client stderr output and prompt clearing
- `set_prompt` state update without writing
- ANSI label formatting for all `LabelColor` variants

Rust behavior prepared in `tests/test_debug_client_state_rs.py`:

- `State` default field values
- `PendingRequest` variants
- public mutation of state fields
- `ReaderEvent::ThreadReady`
- `ReaderEvent::ThreadList`

Rust behavior prepared in `tests/test_debug_client_reader_rs.py`:

- `send_response` JSON-RPC response line serialization
- command execution approval auto-response
- file change approval auto-response
- `thread/start`, `thread/resume`, and `thread/list` response state/event handling
- no-op behavior for responses without matching pending requests
- filtered `item/completed` agent-message rendering
- filtered plan multiline rendering
- filtered command execution, file change, and MCP tool call rendering
- `write_multiline` helper formatting
- raw server JSON logging before response dispatch and invalid JSON ignore behavior

Rust behavior prepared in `tests/test_debug_client_client_rs.py`:

- compact JSON writes through `send_with_stdin`
- JSON-RPC response wrapping through `send_jsonrpc_response`
- thread start/resume parameter builders
- initialize request/response/initialized flow
- synchronous start/resume thread response handling and known-thread memory
- asynchronous thread start/resume/list pending request tracking
- plain-text `turn/start` request construction
- active thread switching with known/unknown reporting
- response-loop raw JSON logging, invalid JSON ignore behavior, and default
  decline handling for approval requests
- client-local approval request handling
- reader stdout ownership and shutdown behavior

Rust behavior covered in `tests/test_debug_client_main_rs.py`:

- CLI defaults and repeated `--config` collection
- approval policy alias parsing and rejection message
- help text output
- thread-ready and thread-list event draining
- command dispatch for help, quit, new thread, resume, use, and refresh-thread
- main startup flow for new and resumed threads
- stdin message dispatch, parse error reporting, reader startup, and shutdown

Validation:

- `python -m pytest tests/test_debug_client_commands_rs.py tests/test_debug_client_output_rs.py tests/test_debug_client_state_rs.py tests/test_debug_client_reader_rs.py tests/test_debug_client_client_rs.py tests/test_debug_client_main_rs.py -q`
  passed on 2026-06-19 with `61 passed`.
- `python -m py_compile pycodex/debug_client/__init__.py pycodex/debug_client/__main__.py pycodex/debug_client/main.py pycodex/debug_client/client.py pycodex/debug_client/commands.py pycodex/debug_client/output.py pycodex/debug_client/state.py pycodex/debug_client/reader.py tests/test_debug_client_commands_rs.py tests/test_debug_client_output_rs.py tests/test_debug_client_state_rs.py tests/test_debug_client_reader_rs.py tests/test_debug_client_client_rs.py tests/test_debug_client_main_rs.py`
  (passed)
