# codex-shell-escalation test alignment

Rust crate: `codex-shell-escalation`

Python package: `pycodex/shell_escalation`

Status: `complete`

Certified modules:

- `codex/codex-rs/shell-escalation/src/lib.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/bin/main_execve_wrapper.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/unix/escalate_client.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/unix/escalate_protocol.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/unix/escalate_server.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/unix/escalation_policy.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/unix/execve_wrapper.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/unix/socket.rs` -> `pycodex/shell_escalation/__init__.py`
- `codex/codex-rs/shell-escalation/src/unix/stopwatch.rs` -> `pycodex/shell_escalation/__init__.py`

Remaining Rust modules: none.

Validation:

- `python -m pytest tests/test_shell_escalation_crate.py -q` (`6 passed, 3 skipped`)
- `python -m py_compile pycodex/shell_escalation/__init__.py tests/test_shell_escalation_crate.py` (passed)
