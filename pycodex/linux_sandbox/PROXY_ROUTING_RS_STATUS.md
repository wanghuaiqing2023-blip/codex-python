# codex-linux-sandbox src/proxy_routing.rs status

Rust module: `codex/codex-rs/linux-sandbox/src/proxy_routing.rs`

Python module: `pycodex/linux_sandbox/proxy_routing.py`

Status: `complete`

Implemented behavior:

- Proxy environment key recognition, case-insensitive.
- Loopback proxy endpoint parsing with default ports.
- Proxy route planning that includes only parseable loopback endpoints while
  remembering whether proxy configuration was present.
- Proxy URL rewriting to a local loopback port.
- Proxy route spec JSON serialization that omits original proxy URLs.
- Proxy socket directory owner-pid parsing and stale directory cleanup.
- Owner pid liveness treats platform pid conversion overflow as a dead pid,
  matching Rust's `pid_t::try_from(pid)` failure branch.
- `prepare_host_proxy_route_spec()` preserves Rust's fail-closed planning
  errors before the bridge runtime boundary: missing proxy variables and proxy
  variables without parseable loopback endpoints produce the same user-facing
  messages as the Rust integration path.
- Valid loopback proxy configuration passes the Rust-aligned preflight and
  reaches the Python bridge runtime boundary.

Runtime boundary:

- Host/local bridge process creation, namespace activation, loopback interface
  mutation, and bidirectional socket proxying are OS/network runtime boundaries
  in the Python port.

Validation:

- `python -m py_compile pycodex/linux_sandbox/proxy_routing.py tests/test_linux_sandbox_proxy_routing_rs.py`
  (passed)
- `python -c "from pycodex.linux_sandbox.proxy_routing import is_pid_alive; print(is_pid_alive(2**32-1))"`
  returned `False`, covering the Windows overflow regression seen during
  crate-focused validation.
- 2026-06-20 direct test-function runner with a minimal local `pytest.raises`
  / `monkeypatch` shim executed all 13
  `tests/test_linux_sandbox_proxy_routing_rs.py` test functions successfully
  under the available Python 3.11.4 runtime.

Focused pytest for `tests/test_linux_sandbox_proxy_routing_rs.py` reported
`10 passed` on 2026-06-20 before the local PTY runner injected a teardown
`KeyboardInterrupt`; crate-level validation is recorded in `TEST_ALIGNMENT.md`.
