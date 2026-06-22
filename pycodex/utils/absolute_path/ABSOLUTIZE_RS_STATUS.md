# codex-utils-absolute-path src/absolutize.rs status

Rust coordinate: `codex/codex-rs/utils/absolute-path/src/absolutize.rs`

Python coordinate: `pycodex/utils/absolute_path/__init__.py`

Status: `complete`

Behavior contract:

- absolute paths are normalized without consulting a base path.
- `.` components are removed.
- `..` components pop a prior normal component.
- relative paths are resolved against a base path through the public `AbsolutePathBuf` entrypoints.
- parent traversal above root stays at root.
- empty relative paths resolve to the base path.

Evidence:

- `tests/test_utils_absolute_path_absolutize.py` maps the Rust `src/absolutize.rs` Unix behavior tests to Python.
- Actual test execution is deferred until `src/lib.rs` is certified.
