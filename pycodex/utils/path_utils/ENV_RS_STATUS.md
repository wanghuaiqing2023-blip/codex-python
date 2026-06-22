# codex-utils-path src/env.rs status

Rust coordinate: `codex/codex-rs/utils/path-utils/src/env.rs`

Python coordinate: `pycodex/utils/path_utils/__init__.py`

Status: `complete`

Behavior contract:

- `is_wsl` returns `False` on non-Linux platforms.
- on Linux, `WSL_DISTRO_NAME` in the environment returns `True`.
- otherwise, `/proc/version` content containing `microsoft` case-insensitively returns `True`.
- unreadable `/proc/version` returns `False`.

Evidence:

- `tests/test_utils_path_utils.py::PathUtilsTests::test_is_wsl_uses_linux_env_then_proc_version` covers the public behavior using injected environment, platform, and proc-version path test doubles.
- With `src/lib.rs` already certified, this completes the `codex-utils-path` crate module set.
