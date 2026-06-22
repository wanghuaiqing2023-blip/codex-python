# codex-exec-server src/remote.rs Status

Rust source: `codex/codex-rs/exec-server/src/remote.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Scope

This slice covers the remote environment registry, configuration behavior, and
the dependency-injected runtime loop projection owned by `src/remote.rs`:

- `RemoteEnvironmentConfig.new(...)` trims and validates environment ids and
  fills the Rust default name `codex-exec-server`.
- `EnvironmentRegistryClient.new(...)` normalizes the registry base URL and
  redacts auth provider details in debug output.
- `EnvironmentRegistryClient.register_environment(...)` POSTs to the Rust
  `/cloud/environment/{environment_id}/register` endpoint with auth-provider
  headers and disables redirect following.
- Registry success responses decode to
  `EnvironmentRegistryRegistrationResponse`.
- Auth and HTTP error helpers parse nested `{error:{code,message}}` bodies,
  preview malformed bodies, and preserve Rust-shaped authentication messages.
- `run_remote_environment(...)` creates a registry client and connection
  processor, registers the configured environment id on every iteration,
  writes the Rust registration message to stderr, connects to the returned
  rendezvous URL through the default standard-library websocket connector or
  an injectable connector, serves successful websocket connections through an
  injectable multiplexed relay loop, resets backoff on connect success, doubles
  failed-connect backoff up to 30 seconds, and propagates registration errors
  before connect or sleep.

## Evidence

- Rust tests:
  - `register_environment_posts_with_auth_provider_headers`
  - `register_environment_does_not_follow_redirects_with_auth_headers`
  - `debug_output_redacts_auth_provider`
- Python tests:
  - `tests/test_exec_server_remote_rs.py`
  - `tests/test_exec_server_remote_rs.py::test_run_remote_environment_default_connector_uses_stdlib_websocket`

## Validation

```powershell
python -m pytest tests/test_exec_server_remote_rs.py -q --tb=short
python -m pytest tests/test_exec_server_remote_rs.py tests/test_exec_server_remote_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_rs.py
```

Latest completion validation on 2026-06-21:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_rs.py
python -m pytest tests/test_exec_server_remote_rs.py -q --tb=short
9 passed
python -m pytest tests/test_exec_server_remote_rs.py tests/test_exec_server_remote_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_client_transport_rs.py -q --tb=short
77 passed
python -m pytest $files -q --tb=short
253 passed, 1 skipped
```

Non-blocking runtime notes for this module: exact reqwest/TLS behavior, rustls
provider installation, exact tokio-tungstenite frame/timing parity, live
`wss://` rendezvous service integration, and unbounded live process
orchestration remain optional operational checks outside the injectable loop
projection.
