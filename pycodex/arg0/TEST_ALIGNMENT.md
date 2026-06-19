# codex-arg0 Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/arg0/src/lib.rs`

Python module:

- `pycodex/arg0/__init__.py`

Parity evidence:

- `tests/test_arg0_lib_rs.py`

Rust-derived coverage:

- `linux_sandbox_exe_path` prefers `codex-linux-sandbox` alias before falling back to current executable.
- `janitor_cleanup` skips directories without `.lock`, skips held locks, and removes unlocked stale directories.
- `set_filtered` and `load_dotenv` reject environment keys whose uppercase form starts with `CODEX_`.
- `prepend_path_entry_for_codex_aliases` creates CODEX_HOME-scoped helper aliases, retains a guard, and prepends PATH.
- `arg0_dispatch` branches on special argv0/argv1 aliases before regular startup, using injected handlers for neighboring process modes.

Validation:

- `python -m pytest tests\test_arg0_lib_rs.py -q` -> `8 passed`
- `python -m py_compile pycodex\arg0\__init__.py tests\test_arg0_lib_rs.py` -> passed

Known adaptations:

- Python uses injected handlers for apply-patch, fs-helper, Linux sandbox, and execve-wrapper process branches. The concrete process bodies remain owned by their corresponding Python modules instead of being duplicated here.

