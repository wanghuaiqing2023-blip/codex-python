# codex-linux-sandbox src/proxy_routing.rs status

Rust module: `codex/codex-rs/linux-sandbox/src/proxy_routing.rs`

Python module: `pycodex/linux_sandbox/proxy_routing.py`

Status: `complete_candidate`

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

Focused pytest for `tests/test_linux_sandbox_proxy_routing_rs.py` was attempted
after crate functional modules were present, but the process was interrupted by
automatic continuation before a result was available.
