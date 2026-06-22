# codex-bwrap src/main.rs status

Rust coordinate: `codex/codex-rs/bwrap/src/main.rs`

Python coordinate: `pycodex/bwrap/__init__.py`

Status: `complete`

Behavior contract:

- preserve cfg-gated behavior for Linux+available, Linux+unavailable, and non-Linux builds.
- validate argv for CString compatibility before invoking the available branch.
- surface the same panic messages for unsupported and unavailable builds.
- model Rust `bwrap_main(argc, argv)` as an explicit Python runner hook.

Evidence:

- `tests/test_bwrap_main_rs.py` covers branch selection, panic messages, runner forwarding, and embedded-NUL argv rejection.
