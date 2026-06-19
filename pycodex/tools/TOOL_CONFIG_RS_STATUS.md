# codex-tools `src/tool_config.rs` alignment

Status: `complete_candidate`

Rust owner:

- Crate: `codex-tools`
- Module: `codex/codex-rs/tools/src/tool_config.rs`

Python owner:

- Module: `pycodex/tools/tool_config.py`
- Reused runtime types:
  - `pycodex.core.tools.ToolUserShellType`
  - `pycodex.core.tools.handlers.shell.ShellCommandBackendConfig`
  - `pycodex.core.tools.handlers.unified_exec.UnifiedExecShellMode`
  - `pycodex.core.tools.handlers.unified_exec.ZshForkConfig`

Behavior covered:

- `request_user_input_available_modes(...)` mirrors the Rust
  `DefaultModeRequestUserInput` feature gate by returning Plan only by default
  and Default plus Plan when the feature is enabled.
- `shell_command_backend_for_features(...)` returns zsh fork only when both
  `ShellTool` and `ShellZshFork` are enabled.
- `shell_type_for_model_and_features(...)` mirrors Rust precedence for disabled
  shell tool, zsh fork forcing shell-command mode, unified-exec feature gating,
  conpty support fallback, and model default/local normalization.
- `unified_exec_shell_mode_for_session(...)` mirrors the Rust zsh-fork session
  guard: Unix platform, zsh backend, zsh user shell, and absolute zsh/wrapper
  paths are all required; otherwise direct mode is used.
- `ToolEnvironmentMode.from_count(...)` and `has_environment()` mirror the Rust
  count-to-mode helper.

Rust tests:

- `codex/codex-rs/tools/src/tool_config_tests.rs`

Python tests:

- Deferred by current crate automation rule until `codex-tools` functional
  module code is complete.
- Existing adjacent coverage remains in:
  - `tests/test_core_request_user_input_handler.py`
  - `tests/test_core_shell_handler.py`
  - `tests/test_core_unified_exec_handler.py`
  - `tests/test_core_tools_root.py`

Notes:

- The Python module is a canonical `codex-tools` package boundary wrapper and
  intentionally reuses the already aligned core handler dataclasses/enums
  rather than duplicating runtime implementations.
