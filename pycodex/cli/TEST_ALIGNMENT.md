# codex-cli test alignment

This ledger records Rust module-scoped behavior contracts for `codex-cli` that are aligned in Python.

## complete

### `src/debug_sandbox.rs` backend and child launch path strings

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete`
- Evidence: Rust `spawn_debug_sandbox_child` and backend argv adapters preserve Unix-style program/cwd strings when launching Seatbelt/Landlock helpers. Python now renders debug-sandbox path arguments through a module-local helper so POSIX paths such as `/usr/bin/sandbox-exec`, `/opt/codex-linux-sandbox`, `/workspace`, and `/tmp` are not rewritten with Windows separators during parity validation.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-17 with `61 passed`.

## complete_slice

### `src/exit_status.rs` return-code/signal mapping

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/exit_status.rs`
- Python module: `pycodex/cli/exit_status.py`
- Python tests: `tests/test_cli_exit_status.py`
- Status: `complete_slice`
- Evidence: Rust `handle_exit_status` preserves normal exit codes, maps Unix signal termination to `128 + signal`, and falls back to exit code `1` when no code/signal is available. Python mirrors this as a pure return-code mapper for subprocess-style statuses.
- Focused validation: `python -m pytest tests/test_cli_exit_status.py -q` passed on 2026-06-16 with `1 passed`.
### `src/wsl_paths.rs` Windows-to-WSL path mapping

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/wsl_paths.rs`
- Python module: `pycodex/cli/wsl_paths.py`
- Python tests: `tests/test_cli_wsl_paths.py`
- Status: `complete_slice`
- Evidence: Rust `win_path_to_wsl` converts absolute Windows drive paths such as `C:\Temp\codex.zip` and `D:/Work/codex.tgz` to `/mnt/<drive>/...`, rejects non-drive/UNC-style inputs, and `normalize_for_wsl` only maps when running under WSL. Python mirrors these branches with an explicit test flag for deterministic validation.
- Focused validation: `python -m pytest tests/test_cli_wsl_paths.py -q` passed on 2026-06-16 with `2 passed`.
### `src/app_cmd.rs` app workspace path canonicalization

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/app_cmd.rs`
- Python module: `pycodex/cli/app_cmd.py`
- Python tests: `tests/test_cli_app_cmd.py`
- Status: `complete_slice`
- Evidence: Rust `AppCommand` defaults `path` to `.` and keeps `download_url_override` optional; `run_app` canonicalizes existing workspace paths but preserves the original path when canonicalization fails. Python mirrors this contract through `AppCommand` and `workspace_for_app_command`, and `pycodex.cli.parser` uses the helper before launching platform-specific app behavior.
- Focused validation: `python -m pytest tests/test_cli_app_cmd.py -q` passed on 2026-06-16 with `3 passed`.
### `src/state_db_recovery.rs` lock contention detection

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `lock_failures_skip_repair` proves details containing `database is locked` or `database is busy` are treated as lock contention while malformed database details are not. Python mirrors the case-insensitive detection branch.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `1 passed`.
### `src/state_db_recovery.rs` SQLite sidecar path expansion

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `sqlite_paths` returns the database path plus `-wal` and `-shm` sidecar paths. Python mirrors this as `sqlite_paths`, exported for CLI callers as `state_db_sqlite_paths`.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `2 passed`.
### `src/state_db_recovery.rs` repair backup path sequencing

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `backup_path` builds backup names as `.<repair_suffix>.<sequence>.bak`, skips occupied sequence numbers, renames the original file to the first free candidate, and returns that backup path. Python mirrors this as `backup_path`, exported for CLI callers as `state_db_backup_path`.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `3 passed`.
### `src/state_db_recovery.rs` blocking sqlite_home repair

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `repair_replaces_blocking_sqlite_home_file` backs up a non-directory file occupying sqlite_home, creates sqlite_home as a directory, and returns the backup path. Python mirrors this through `repair_files`, exported for CLI callers as `state_db_repair_files`.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `4 passed`.
### `src/state_db_recovery.rs` owned runtime DB backup repair

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `repair_backs_up_owned_database_files` backs up existing owned SQLite runtime database files and SQLite sidecars during safe local state repair. Python covers state/logs/goals DB files plus the state WAL sidecar through `state_db_repair_files`.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `5 passed`.
### `src/state_db_recovery.rs` locked guidance stderr output

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `print_locked_guidance` emits lock-contention guidance followed by technical details (`Location` and `Cause`) to stderr. Python mirrors this as `print_locked_guidance`, exported for CLI callers as `state_db_print_locked_guidance`.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `6 passed`.
### `src/state_db_recovery.rs` diagnostic guidance stderr output

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `print_diagnostic_guidance` emits damaged local database guidance, `codex doctor` next-step guidance, and technical details (`Location` and `Cause`) to stderr. Python mirrors this as `print_diagnostic_guidance`, exported for CLI callers as `state_db_print_diagnostic_guidance`.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `7 passed`.
### `src/state_db_recovery.rs` repair backups stderr output

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `print_repair_backups` emits the backup summary header, each backup path indented by two spaces, and the retry message to stderr. Python mirrors this as `print_repair_backups`, exported for CLI callers as `state_db_print_repair_backups`.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `8 passed`.
### `src/state_db_recovery.rs` repair confirmation guidance

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `confirm_repair` prints damaged-database safe-repair guidance and technical details, then delegates to `crate::confirm` with `Repair Codex local data now? [y/N]: `. Python mirrors this as `confirm_repair`, exported for CLI callers as `state_db_confirm_repair`, with an injectable confirm callback for focused parity tests.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `9 passed`.
### `src/state_db_recovery.rs` startup error extraction

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `startup_error` unwraps an embedded `LocalStateDbStartupError` from an outer `std::io::Error`. Python mirrors the boundary through `startup_error`, exported for CLI callers as `state_db_startup_error`, by checking the exception and its cause/context for the local state DB startup error interface.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `10 passed`.
### `src/state_db_recovery.rs` empty repair guard

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/state_db_recovery.rs`
- Python module: `pycodex/cli/state_db_recovery.py`
- Python tests: `tests/test_cli_state_db_recovery.py`
- Status: `complete_slice`
- Evidence: Rust `repair_files` returns an error when the scan finds no repairable Codex local data files. Python mirrors this by raising `OSError("no repairable Codex local data files were found")` when no backups were created.
- Focused validation: `python -m pytest tests/test_cli_state_db_recovery.py -q` passed on 2026-06-16 with `11 passed`.
### `src/debug_sandbox.rs` managed requirements mode

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `ManagedRequirementsMode::for_profile_invocation` returns `Ignore` only when an explicit permissions profile is present and managed config is not included; otherwise it returns `Include`. Python mirrors this as `ManagedRequirementsMode.for_profile_invocation`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `1 passed`.
### `src/debug_sandbox.rs` legacy sandbox override detection

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `cli_overrides_use_legacy_sandbox_mode` returns true only when a CLI override key exactly equals `sandbox_mode`. Python mirrors this as `cli_overrides_use_legacy_sandbox_mode`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `2 passed`.
### `src/debug_sandbox.rs` permission profile config probe

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `config_uses_permission_profiles` checks the effective config for `default_permissions`. Python mirrors this as `config_uses_permission_profiles` against the config layer stack facade.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `3 passed`.
### `src/debug_sandbox.rs` legacy read-only default decision

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `load_debug_sandbox_config_with_codex_home` returns the loaded config unchanged when permission profiles are active or a legacy `sandbox_mode` CLI override is present; otherwise it rebuilds with read-only sandbox defaults. Python mirrors this decision as `should_default_legacy_config_to_read_only`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `4 passed`.
### `src/debug_sandbox.rs` permissions profile override append

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `load_debug_sandbox_config_with_codex_home` appends `("default_permissions", TomlValue::String(profile))` when `permissions_profile` is present. Python mirrors this as `with_permissions_profile_override`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `5 passed`.
### `src/debug_sandbox.rs` managed requirements loader override

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `build_debug_sandbox_config_with_loader_overrides` sets `loader_overrides.ignore_managed_requirements = true` when `ManagedRequirementsMode::Ignore` is active, and otherwise leaves loader overrides unchanged. Python mirrors this as `loader_overrides_with_managed_requirements_mode`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `6 passed`.
### `src/debug_sandbox.rs` sandbox platform availability guards

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust non-macOS `run_command_under_seatbelt` returns `Seatbelt sandbox is only available on macOS`, and non-Windows sandbox execution returns `Windows sandbox is only available on Windows`. Python mirrors these platform boundary strings as `sandbox_unavailable_error` without spawning a sandbox.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `7 passed`.
### `src/debug_sandbox.rs` child network-disabled env marker

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `spawn_debug_sandbox_child` injects `CODEX_SANDBOX_NETWORK_DISABLED=1` into the child environment when `NetworkSandboxPolicy::is_enabled()` is false. Python mirrors this spawn-preparation behavior as `debug_sandbox_child_env` using the shared core spawn env-var constant.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `8 passed`.
### `src/debug_sandbox.rs` seatbelt env marker

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust Seatbelt debug sandbox spawn `apply_env` inserts `CODEX_SANDBOX=seatbelt` into the child environment before spawning `sandbox-exec`. Python mirrors this spawn-preparation behavior as `debug_sandbox_seatbelt_env` using the shared core spawn env-var constant.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `9 passed`.
### `src/debug_sandbox.rs` unix child arg0 selection

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `spawn_debug_sandbox_child` sets Unix `arg0` to the explicit arg0 when present, otherwise to the program path string; non-Unix builds do not set arg0. Python mirrors this spawn-preparation decision as `debug_sandbox_child_arg0`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `10 passed`.
### `src/debug_sandbox.rs` windows stdin forward chunks

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `windows_stdio_bridge::spawn_input_forwarder` reads stdin into `STDIN_FORWARD_CHUNK_SIZE = 8 * 1024` byte chunks and forwards each chunk in order until EOF. Python mirrors the chunking contract as `windows_stdin_forward_chunks`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `11 passed`.
### `src/debug_sandbox.rs` windows output forward bytes

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/debug_sandbox.rs`
- Python module: `pycodex/cli/debug_sandbox.py`
- Python tests: `tests/test_cli_debug_sandbox.py`
- Status: `complete_slice`
- Evidence: Rust `windows_stdio_bridge::spawn_output_forwarder` writes every received output chunk to the destination writer in receive order and flushes after each write. Python mirrors the stable byte-order contract as `windows_output_forward_bytes`.
- Focused validation: `python -m pytest tests/test_cli_debug_sandbox.py -q` passed on 2026-06-16 with `12 passed`.
### `src/login.rs` API key status masking

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `safe_format_key` masks API keys for `codex login status`: keys of length 13 or less render as `***`; longer keys render as the first 8 characters, `***`, then the last 5 characters. Python mirrors this as `safe_format_key`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `13 passed`.
### `src/login.rs` local server start stderr message

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `print_login_server_start` emits the local login server URL, fallback auth URL, and remote/headless device-auth guidance to stderr with stable blank-line formatting. Python mirrors this as `print_login_server_start`, and the ChatGPT login flow uses the helper.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `14 passed`.
### `src/login.rs` forced login method disabled messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust login entry points reject incompatible forced login methods with fixed stderr messages: ChatGPT/device-code flows are disabled by forced API login, API-key flow is disabled by forced ChatGPT login, and access-token flow is disabled by forced API login. Python mirrors the message decision as `login_disabled_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `15 passed`.
### `src/login.rs` stdin secret trim and empty guard

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `read_stdin_secret` trims stdin content before using it as a secret and exits with fixed empty messages for API key/access token login when the trimmed secret is empty. Python mirrors the stable text behavior as `stdin_secret_from_text`, with API-key and access-token wrappers.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `16 passed`.
### `src/login.rs` login status auth-mode messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `run_login_status` maps API key auth to `Logged in using an API key - {masked}`, ChatGPT and ChatGPT auth tokens to `Logged in using ChatGPT`, agent identity to `Logged in using access token`, and missing auth to `Not logged in`. Python mirrors this stable message contract as `login_status_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `17 passed`.
### `src/login.rs` logout status messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `run_logout` maps successful logout to `Successfully logged out`, no existing login to `Not logged in`, and errors to `Error logging out: {err}`. Python mirrors this stable message contract as `logout_status_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `18 passed`.
### `src/login.rs` login flow result messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust login flow result branches print `Successfully logged in` on success, `Error logging in: {err}` for browser/API-key errors, `Error logging in with access token: {err}` for access-token errors, and `Error logging in with device code: {err}` for device-code errors. Python mirrors this stable message contract as `login_result_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `19 passed`.
### `src/login.rs` device-code fallback message

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `run_login_with_device_code_fallback_to_browser` prints `Device code login is not enabled; falling back to browser login.` only when device-code login fails with `ErrorKind::NotFound`. Python mirrors this stable message decision as `device_code_fallback_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `20 passed`.
### `src/login.rs` stdin secret prompt messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `read_api_key_from_stdin` and `read_access_token_from_stdin` pass fixed terminal, reading, and empty messages into `read_stdin_secret`. Python mirrors these stable message triples as `stdin_secret_messages`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `21 passed`.
### `src/login.rs` config error messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `load_config_or_exit` prints `Error parsing -c overrides: {err}` when CLI override parsing fails and `Error loading configuration: {err}` when config loading fails. Python mirrors this stable message contract as `login_config_error_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `22 passed`.
### `src/login.rs` login log file path

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `init_login_file_logging` writes the direct login tracing layer to `codex-login.log` under the resolved log directory. Python mirrors this stable path contract as `login_log_file_path`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `23 passed`.
### `src/login.rs` login log warning messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `init_login_file_logging` emits stable warning messages for log directory resolution, directory creation, log file open, and tracing subscriber initialization failures. Python mirrors this warning text contract as `login_log_warning_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `24 passed`.
### `src/login.rs` login log default filter

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `init_login_file_logging` falls back to `codex_cli=info,codex_core=info,codex_login=info` when `EnvFilter::try_from_default_env()` fails. Python mirrors the stable fallback value as `login_log_default_filter`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `25 passed`.
### `src/login.rs` login log unix file mode

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `init_login_file_logging` configures `OpenOptionsExt::mode(0o600)` under `#[cfg(unix)]` before opening `codex-login.log`, and has no equivalent Unix mode branch on non-Unix platforms. Python mirrors this stable mode decision as `login_log_unix_file_mode`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `26 passed`.
### `src/login.rs` stdin read error message

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `read_stdin_secret` maps stdin read failures to `Failed to read stdin: {err}` before exiting; Python exposes the same message contract through `stdin_secret_read_error_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `27 passed`.
### `src/login.rs` status error messages

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `run_login_status` reports API-key retrieval errors as `Unexpected error retrieving API key: {e}` and auth status checks as `Error checking login status: {e}`; Python exposes the same message contract through `login_status_error_message`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `28 passed`.
### `src/login.rs` log open options

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/login.rs`
- Python module: `pycodex/cli/login.py`
- Python tests: `tests/test_cli_login.py`
- Status: `complete_slice`
- Evidence: Rust `init_login_file_logging` opens the direct login log with `create(true)` and `append(true)`, adding Unix mode `0o600`; Python exposes the same option contract through `login_log_open_options`.
- Focused validation: `python -m pytest tests/test_cli_login.py -q` passed on 2026-06-16 with `29 passed`.
### `src/doctor/updates.rs` update action labels

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/updates.rs`
- Python module: `pycodex/cli/update_action.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `update_action_label` maps npm, bun, brew, standalone, and unknown/manual install contexts to fixed user-facing update commands/labels; Python `update_action_label` preserves the same labels for the corresponding `UpdateAction` values and `None`.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `125 passed, 5 subtests passed`.
### `src/doctor/title.rs` project config fallback

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/title.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `terminal_title_reports_project_config_fallback` confirms configured `project` aliases to `project-name` and reports `project config` source/value when project root comes from config; Python `doctor_terminal_title_check` preserves that behavior.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `126 passed, 5 subtests passed`.
### `src/doctor/title.rs` project omission when not selected

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/title.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `terminal_title_omits_project_when_project_item_is_not_selected` confirms configured non-project items do not emit project source/value details even when a project root is available; Python `doctor_terminal_title_check` preserves that behavior.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `127 passed, 5 subtests passed`.
### `src/doctor/title.rs` all-invalid configured items

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/title.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `terminal_title_warns_when_all_configured_items_are_invalid` confirms all-invalid configured title items produce warning status, `terminal title items: none`, invalid item details, and no project details; Python `doctor_terminal_title_check` preserves that behavior.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `128 passed, 5 subtests passed`.
### `src/doctor/title.rs` terminal title aliases

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/title.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `terminal_title_item_id` maps aliases such as `spinner`, `status`, `thread`, `context-usage`, `session-id`, and `model-name` to canonical terminal-title item ids; Python `_TERMINAL_TITLE_ITEM_ALIASES` preserves the same canonicalization through `doctor_terminal_title_check` details.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `129 passed, 5 subtests passed`.
### `src/doctor/git.rs` Windows Git version parser

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `parses_git_for_windows_version` confirms `parse_git_version` strips `.windows.N` suffixes and preserves major/minor/patch; Python `_parse_git_version` preserves the same parsing contract.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `130 passed, 5 subtests passed`.
### `src/doctor/git.rs` msysgit warning

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `classifies_old_windows_git` gives version strings containing `msysgit` a dedicated `old msysgit installation may corrupt Windows TUI rendering` warning; Python `doctor_git_check` preserves that branch.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `131 passed, 5 subtests passed`.
### `src/doctor/git.rs` detached HEAD branch normalization

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `normalized_branch` maps `HEAD` to `detached HEAD` before adding Git branch details; Python `doctor_git_check` preserves that displayed branch value.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `132 passed, 5 subtests passed`.
### `src/doctor/git.rs` empty core.fsmonitor omission

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust filters empty `core.fsmonitor` values before pushing optional Git details; Python `doctor_git_check` preserves the same omission behavior.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `133 passed, 5 subtests passed`.
### `src/doctor/git.rs` empty branch omission

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `normalized_branch` treats empty branch strings as absent before pushing optional Git details; Python `doctor_git_check` preserves the same omission behavior.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `134 passed, 5 subtests passed`.
### `src/doctor/git.rs` command output text

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `command_output_text` returns `None` on failed/empty output and otherwise trims non-empty stdout lines joined by `; `; Python `_git_command_output_text` mirrors that private helper contract.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `135 passed, 5 subtests passed`.
### `src/doctor/git.rs` git entry summary

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `git_entry_summary` reports `.git` as `missing`, `directory`, or `file -> {path}` for gitfiles with a `gitdir:` prefix; Python `_git_entry_summary` preserves those summaries.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `136 passed, 5 subtests passed`.
### `src/doctor/git.rs` plain gitfile summary

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `git_entry_summary` returns `file` when `.git` is a file that does not contain a `gitdir:` pointer; Python `_git_entry_summary` preserves that branch.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `137 passed, 5 subtests passed`.
### `src/doctor/git.rs` no-git no-repo summary

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/git.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `git_summary`/`git_check_from_inputs` reports `git executable not found` with ok status when no Git executable and no repo root are detected; Python `doctor_git_check` preserves the same summary/details contract.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `138 passed, 5 subtests passed`.
### `src/doctor/system.rs` locale env ordering

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/system.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `system_check_from_inputs` iterates `LOCALE_ENV_VARS` in fixed order when appending locale details; Python `doctor_system_check` preserves `LC_ALL`, `LC_CTYPE`, `LANG` ordering.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `139 passed, 5 subtests passed`.
### `src/doctor/progress.rs` progress visibility

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/progress.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `should_show_progress` is quiet for JSON output, non-TTY stderr, and `TERM=dumb`, while showing transient progress for human TTY output; Python `_should_show_doctor_progress` mirrors that selection contract.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `140 passed, 5 subtests passed`.
### `src/doctor/output.rs` ASCII status markers

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `status_marker` maps ASCII display statuses to `[ok]`, `[up]`, `[!!]`, `[XX]`, and `[--]`; Python `_doctor_output_ascii_status_marker` preserves that marker table without implementing the full renderer.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `141 passed, 5 subtests passed`.
### `src/doctor/output.rs` ASCII separator width

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust human output uses `SEPARATOR_WIDTH = 61`; Python `_doctor_output_ascii_separator` preserves the same ASCII separator width.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `142 passed, 5 subtests passed`.
### `src/doctor/output.rs` column widths

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust human output uses `NAME_WIDTH = 12` and `DETAIL_LABEL_WIDTH = 24`; Python `_doctor_output_column_widths` preserves those presentation constants.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `143 passed, 5 subtests passed`.
### `src/doctor/output/detail.rs` number formatters

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `format_bytes` formats B/KB/MB/GB thresholds with two decimals above bytes, and `format_count` inserts comma groups; Python `_doctor_detail_format_bytes` and `_doctor_detail_format_count` preserve those contracts.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `144 passed, 5 subtests passed`.
### `src/doctor/output/detail.rs` rollout summary

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `rollout_summary` parses `N files, B total bytes, A average bytes` and renders count/byte human summaries; Python `_doctor_detail_rollout_summary` preserves the same behavior using the Rust-derived byte/count formatters.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `145 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` list/path limits

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `LIST_LIMIT` and `PATH_LIMIT` are internal detail rendering limits; Python `_doctor_detail_list_limit` and `_doctor_detail_path_limit` expose the same values for downstream detail formatting behavior.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `146 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` format_bytes thresholds

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `format_bytes` switches display units at KiB, MiB, and GiB thresholds; Python `_doctor_detail_format_bytes` is now covered at byte, KB, MB, and GB boundaries.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `147 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` format_count grouping

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `format_count` renders decimal counts with comma grouping; Python `_doctor_detail_format_count` is covered for zero, sub-thousand, thousand, and multi-group values.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `148 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` format_bytes precision

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `format_bytes` renders KB/MB/GB values with two decimal places; Python `_doctor_detail_format_bytes` is covered for fractional KB, MB, and GB cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `149 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` rollout summary parse failures

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `rollout_summary` uses integer parsing with `ok()?`, so non-numeric file, total byte, or average byte fields produce no summary; Python `_doctor_detail_rollout_summary` is covered for the same failure branches.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `150 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` rollout summary zero values

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `rollout_summary` parses unsigned integer fields, including zero, and formats a valid count/byte summary; Python `_doctor_detail_rollout_summary` is covered for the zero-value success path.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `151 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` humanize_timestamp

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `humanize_timestamp` accepts long `Z`-terminated timestamp-like strings with `T`, keeps the date, takes the first five time characters, and renders `UTC`; Python `_doctor_detail_humanize_timestamp` mirrors that behavior and rejection path.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `152 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` looks_like_path

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `looks_like_path` recognizes `/`, `~/`, `./`, and `../` prefixes before applying path-specific humanization; Python `_doctor_detail_looks_like_path` mirrors those accepted and rejected cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `153 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` middle_truncate

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `middle_truncate` leaves values at or below the limit unchanged and otherwise keeps a head/tail split around an ellipsis; Python `_doctor_detail_middle_truncate` mirrors the same character-count behavior for odd and even limits.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `154 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` home_shortened_path

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `home_shortened_path` converts an exact `$HOME` path to `~`, converts `$HOME/...` to `~/...`, and leaves non-child or unavailable-home paths unchanged; Python `_doctor_detail_home_shortened_path` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `155 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` shorten_path_prefix

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `shorten_path_prefix` splits optional ` (suffix)` text, applies HOME shortening and middle truncation to the path prefix only, then reattaches the suffix; Python `_doctor_detail_shorten_path_prefix` mirrors that composition.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `156 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` humanize_value dispatch

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `humanize_value` applies path shortening first, then timestamp humanization, then returns the original value; Python `_doctor_detail_humanize_value` mirrors that dispatch order over the previously ported helpers.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `157 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` display_label

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `display_label` remaps selected raw detail labels to human-facing labels and otherwise returns the original label; Python `_doctor_detail_display_label` mirrors those mapped and fallback cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `158 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` yes_no

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `yes_no` maps only the exact string `true` to `yes` and maps all other values to `no`; Python `_doctor_detail_yes_no` mirrors those exact-string semantics.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `159 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` list_items

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `list_items` returns an empty list for falsy detail values and otherwise splits comma-separated values, trims whitespace, and drops empty items; Python `_doctor_detail_list_items` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `160 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` override_names

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `override_names` maps `name=value` entries to `name` and leaves entries without `=` unchanged; Python `_doctor_detail_override_names` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `161 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` rollout_files_and_bytes

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `rollout_files_and_bytes` parses the file count and total byte count from rollout stat strings, ignores the trailing average text, and returns no value for malformed or non-numeric fields; Python `_doctor_detail_rollout_files_and_bytes` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `162 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` parsed_details split_once

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `parsed_details` splits each redacted detail only on the first `": "`; details without that exact delimiter become freeform values with an empty label. Python `_doctor_detail_parse_detail` mirrors those delimiter semantics.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `163 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` is_falsy

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `is_falsy` treats blank, `false`, `none`, `not set`, `unknown`, `missing`, `absent`, `no`, and `-` values as empty detail values; Python `_doctor_detail_is_falsy` is covered for those cases and non-falsy fallbacks.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `164 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` numbered_values

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `numbered_values` filters parsed detail rows by label prefix and returns matching values in their original order; Python `_doctor_detail_numbered_values` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `165 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` value

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `value` returns the first parsed detail value whose label exactly equals the requested label, without prefix matching or later duplicate selection; Python `_doctor_detail_value` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `166 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` push_list_row

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `push_list_row` joins visible list items, limits default output to `LIST_LIMIT`, appends the full-list hint when truncated, and expands all items with `--all`; Python `_doctor_detail_push_list_row_value` mirrors those value-generation cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `167 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` push_database_row

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `push_database_row` renders a database path alone when integrity is absent and appends `integrity <value>` when the paired integrity detail exists; Python `_doctor_detail_database_row_value` mirrors those value-generation cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `168 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` push_feature_flags summary

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `push_feature_flags` builds the summary as `<enabled> enabled �� <overrides> overridden`, defaults invalid enabled counts to zero, counts parsed override list items, and appends the full-list hint only when default output hides enabled flags. Python `_doctor_detail_feature_flags_summary_value` mirrors those value-generation cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `169 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` install managed-by row

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `install_details` renders the `managed by` row from npm/bun booleans via `yes_no` and displays a dash for falsy package-root values; Python `_doctor_detail_managed_by_value` mirrors those value-generation cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `170 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` config model row

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `config_details` renders the model row as the model alone when provider is absent and as `model �� provider` when provider is present; Python `_doctor_detail_model_row_value` mirrors those value-generation cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `171 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` issue_remedies

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `issue_remedies` filters issue remedies, skips absent remedies, and uses first-seen de-duplication while preserving issue order; Python `_doctor_detail_issue_remedies` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `172 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` issue_expected_for_label

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `issue_expected_for_label` searches issues in order, matches either `display_label(field)` or the raw field against the row label, and returns the first matching issue expected value; Python `_doctor_detail_issue_expected_for_label` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `173 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` attach_issue_metadata

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `attach_issue_metadata` only augments row details, keeps an existing expected value, and otherwise asks `issue_expected_for_label` for matching issue metadata; Python `_doctor_detail_attach_issue_expected` mirrors those expected-value merge cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `174 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` generic_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `generic_details` renders parsed details with an empty label as bullets and labeled details as rows using `display_label`; Python `_doctor_detail_generic_kind_and_label` mirrors those classification cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `175 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` push_remaining

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `push_remaining` skips consumed labels, consumed prefixes, and the inherited package-manager launch-env noise detail, then renders remaining rows/bullets through generic detail classification; Python `_doctor_detail_remaining_details` mirrors those filtering cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `176 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` PATH entries

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `install_details` and `git_details` render PATH entry groups with a first row labelled by total count, continuation rows for additional visible entries, default truncation at 3 entries, and a full-list hint when hidden; Python `_doctor_detail_path_entry_values` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `177 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` system_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `system_details` emits `os`, `OS language`, and locale env rows in a fixed display order, consumes raw system fields, and emits unconsumed details through generic remaining-detail handling; Python `_doctor_detail_system_rows` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `178 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` runtime_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `runtime_details` emits `version`, `install method`, `commit`, and `current executable` as `executable` in a fixed order, consumes runtime-only fields, and emits unconsumed details through remaining-detail handling; Python `_doctor_detail_runtime_rows` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `179 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` title_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `title_details` emits terminal-title source, items, activity, project source, and project value rows in fixed display order, then emits unconsumed details through remaining-detail handling; Python `_doctor_detail_title_rows` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `180 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` state_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `state_details` emits state path rows, database rows with optional integrity, active/archived rollout summaries with raw fallback, and unconsumed details through remaining-detail handling; Python `_doctor_detail_state_rows` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `181 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` git_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `git_details` emits selected git, version, exec path, repo details, branch, fsmonitor, PATH git entries, and unconsumed remaining details in fixed human order; Python `_doctor_detail_git_rows` mirrors those ordering, grouping, and filtering cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `182 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` install_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `install_details` emits install context, inherited package-manager launch-env bullet, managed-by row, PATH codex entries, and unconsumed remaining details in fixed human order; Python `_doctor_detail_install_rows` mirrors those ordering, grouping, and filtering cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `183 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` config_details

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `config_details` emits model/provider, cwd, config.toml parse/read, MCP server, feature flag summary, legacy alias rows, and unconsumed details in fixed human order; Python `_doctor_detail_config_rows` mirrors those ordering and filtering cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `184 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` detail_lines category dispatch

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `detail_lines` dispatches parsed details by category to system, runtime, install, git, title, config, state, or generic detail renderers; Python `_doctor_detail_rows_for_category` mirrors that category selection and generic fallback over the previously ported helpers.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `185 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` detail_value

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `detail_value` parses/redacts raw check details and returns the first value whose parsed label exactly matches the requested label; Python `_doctor_detail_value_from_details` mirrors that raw-detail lookup behavior.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `186 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` humanize_detail

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `humanize_detail` applies `humanize_value` to row, continuation, and bullet values while leaving remedy values unchanged; Python `_doctor_detail_humanize_detail` mirrors those kind-dispatch cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `187 passed, 5 subtests passed`.

### `src/doctor/output/detail.rs` detail_lines pipeline

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output/detail.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `detail_lines` parses/redacts raw details, dispatches by category, attaches issue expected metadata, humanizes row/continuation/bullet values, and appends de-duplicated remedies in issue order; Python `_doctor_detail_lines_for_check` mirrors that pipeline using the previously ported helpers.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `188 passed, 5 subtests passed`.

### `src/doctor/output.rs` GROUPS

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `GROUPS` defines the human doctor report group titles and category ordering; Python `_doctor_output_groups` mirrors that table exactly, including Environment, Configuration, Updates, Connectivity, and Background Server groups.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `189 passed, 5 subtests passed`.

### `src/doctor/output.rs` display_status

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `display_status` maps check statuses to human display statuses and treats an ok `app-server` check with `status: not running` detail as `Idle`; Python `_doctor_output_display_status` mirrors that mapping and special case.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `190 passed, 5 subtests passed`.

### `src/doctor/output.rs` overall_status_label

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `overall_status_label` maps overall check status `Ok`, `Warning`, and `Fail` to the human summary labels `ok`, `degraded`, and `failed`; Python `_doctor_output_overall_status_label` mirrors those mappings.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `191 passed, 5 subtests passed`.

### `src/doctor/output.rs` issue_summary

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `issue_summary` returns the check summary for no issues, the sole issue cause for one issue, and `<n> issues - <first>; <second>` for multiple issues; Python `_doctor_output_issue_summary` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `192 passed, 5 subtests passed`.

### `src/doctor/output.rs` row_description

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `row_description` uses issue summaries first for warning/fail checks, then remediation text with ASCII/Unicode dash, and otherwise falls back to the normal summary; Python `_doctor_output_row_description` mirrors that priority order.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `193 passed, 5 subtests passed`.

### `src/doctor/output.rs` update_note

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `update_note` emits an updates note only when latest-version status reports a newer version, prefers `latest version` over `cached latest version`, falls back to `newer version`, and includes non-falsy dismissed versions; Python `_doctor_output_update_note_summary` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `194 passed, 5 subtests passed`.

### `src/doctor/output.rs` rollout_note

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `rollout_note` emits no note below both thresholds, emits a warning note when active rollout files reach 1000 or disk usage reaches 1 GiB, and formats the summary with Rust count/byte helpers; Python `_doctor_output_rollout_note_summary` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `195 passed, 5 subtests passed`.

### `src/doctor/output.rs` sandbox_note

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `sandbox_note` suppresses notes only when filesystem and network sandboxes are both `restricted`, and otherwise summarizes both values; Python `_doctor_output_sandbox_note_summary` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `196 passed, 5 subtests passed`.

### `src/doctor/output.rs` auth_reachability_note

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `auth_reachability_note` emits a warning note only when websocket auth mode contains ChatGPT and reachability mode contains API key, using case-insensitive checks; Python `_doctor_output_auth_reachability_note_summary` mirrors those cases and summary text.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `197 passed, 5 subtests passed`.

### `src/doctor/output.rs` notes_for_report ordering

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `notes_for_report` appends notes in update, rollout, sandbox, non-ok, then auth-reachability order; Python `_doctor_output_notes_order` fixes that aggregation order over category presence.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `198 passed, 5 subtests passed`.

### `src/doctor/output.rs` write_footer

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `write_footer` renders different footer guidance for detailed output versus summary output; Python `_doctor_output_footer_lines` mirrors those line-content cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `199 passed, 5 subtests passed`.

### `src/doctor/output.rs` header_suffix

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `header_suffix` renders `v<codex_version>` and appends the runtime `platform` detail when available; Python `_doctor_output_header_suffix` mirrors those cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `200 passed, 5 subtests passed`.

### `src/doctor/output.rs` summary_line

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/output.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `summary_line` always renders ok/warn/fail counts, conditionally inserts idle and notes counts, chooses ASCII or Unicode separators, and appends the overall status label; Python `_doctor_output_summary_line_text` mirrors those text-composition cases.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed on 2026-06-16 with `201 passed, 5 subtests passed`.

### src/doctor/output.rs checks_for_group

- Rust anchor: `codex-cli/src/doctor/output.rs` `checks_for_group`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_checks_for_group` mirrors Rust grouping by iterating requested group keys first and preserving report check order within each category.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_checks_for_group_matches_rust_order`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 202 passed, 5 subtests passed.

### src/doctor/output.rs actionable_note_summary

- Rust anchor: `codex-cli/src/doctor/output.rs` `actionable_note_summary`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_actionable_note_summary` mirrors Rust text precedence: issue summary overrides remediation, remediation appends with ` - `, and plain summaries remain unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_actionable_note_summary_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 203 passed, 5 subtests passed.

### src/doctor/output.rs non_ok_notes

- Rust anchor: `codex-cli/src/doctor/output.rs` `non_ok_notes`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_non_ok_notes` mirrors Rust warning/fail filtering and composes each note from display status plus actionable summary text.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_non_ok_notes_matches_rust_filtering`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 204 passed, 5 subtests passed.

### src/doctor/output.rs status_marker_slot ascii

- Rust anchor: `codex-cli/src/doctor/output.rs` `status_marker_slot`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_ascii_status_marker_slot` mirrors the ASCII-output branch by appending a trailing space to the Rust-aligned ASCII status marker.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_ascii_status_marker_slot_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 205 passed, 5 subtests passed.

### src/doctor/output.rs detail_marker ascii

- Rust anchor: `codex-cli/src/doctor/output.rs` `detail_marker`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_ascii_detail_marker` mirrors the ASCII-output branch: issue detail rows use `>`, while non-issue rows reserve a single blank marker cell.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_ascii_detail_marker_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 206 passed, 5 subtests passed.

### src/doctor/output.rs style_update_note_summary no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_update_note_summary`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_update_note_summary_no_color` mirrors the `!options.color_enabled` branch by returning the summary unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_update_note_summary_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 207 passed, 5 subtests passed.

### src/doctor/output.rs count_label no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `count_label`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_count_label_no_color` mirrors the color-disabled text output by formatting `{count} {label}` for known display statuses.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_count_label_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 208 passed, 5 subtests passed.

### src/doctor/output.rs styled_overall_status no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `styled_overall_status`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_styled_overall_status_no_color` mirrors the `!options.color_enabled` branch by returning the label unchanged for known overall statuses.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_styled_overall_status_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 209 passed, 5 subtests passed.

### src/doctor/output.rs style_note_summary update/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_note_summary`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_update_note_summary_from_note_no_color` mirrors the update-status dispatch into `style_update_note_summary` under disabled color output, returning the summary unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_note_summary_update_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 210 passed, 5 subtests passed.

### src/doctor/output.rs highlight_actions no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `highlight_actions`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_highlight_actions_no_color` mirrors the `!options.color_enabled` branch by returning text unchanged, preserving code spans and flag-like tokens.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_highlight_actions_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 211 passed, 5 subtests passed.

### src/doctor/output.rs highlight_flags no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `highlight_flags`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_highlight_flags_no_color` mirrors the color-disabled visible behavior by preserving flag-like tokens, punctuation, and whitespace unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_highlight_flags_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 212 passed, 5 subtests passed.

### src/doctor/output.rs is_safe_presence_value

- Rust anchor: `codex-cli/src/doctor/output.rs` `is_safe_presence_value`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_is_safe_presence_value` mirrors Rust trim plus lowercase whitelist matching for safe presence values.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_is_safe_presence_value_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 213 passed, 5 subtests passed.

### src/doctor/output.rs redact_url_token

- Rust anchor: `codex-cli/src/doctor/output.rs` `redact_url_token` and direct helper `redact_url_path`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_url_token` mirrors Rust single-token URL redaction by stripping URL userinfo, redacting paths after the first segment, preserving scheme/host and trailing punctuation/whitespace, and leaving non-URLs unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_url_token_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 214 passed, 5 subtests passed.

### src/doctor/output.rs redact_urls

- Rust anchor: `codex-cli/src/doctor/output.rs` `redact_urls`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_urls` mirrors Rust split-inclusive whitespace token handling by applying `_doctor_output_redact_url_token` to each whitespace-inclusive token and preserving separators.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_urls_matches_rust_split_inclusive`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 215 passed, 5 subtests passed.

### src/doctor/output.rs redact_detail env-var branch

- Rust anchor: `codex-cli/src/doctor/output.rs` `redact_detail` label contains `env var` branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail_env_var_branch` mirrors Rust by delegating such details to URL redaction only, without replacing the entire value.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_env_var_branch_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 216 passed, 5 subtests passed.

### src/doctor/output.rs redact_detail safe-presence branch

- Rust anchor: `codex-cli/src/doctor/output.rs` `redact_detail` safe-presence value branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail_safe_presence_branch` mirrors Rust `split_once(": ")` behavior and delegates safe presence values to URL redaction rather than full secret redaction.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_safe_presence_branch_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 217 passed, 5 subtests passed.

### src/doctor/output.rs redact_detail secret-key branch

- Rust anchor: `codex-cli/src/doctor/output.rs` `redact_detail` secret-key branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail_secret_key_branch` mirrors Rust lowercased substring matching for secret key names and formats the first colon-delimited name as `name: <redacted>`.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_secret_key_branch_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 218 passed, 5 subtests passed.

### src/doctor/output.rs redact_detail fallback branch

- Rust anchor: `codex-cli/src/doctor/output.rs` `redact_detail` fallback branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail_fallback_branch` mirrors Rust's final branch for details that are not env-var labels, not safe-presence values, and not secret-key matches, delegating to URL redaction only.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_fallback_branch_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 219 passed, 5 subtests passed.

### src/doctor/output.rs StatusCounts::from_report counting

- Rust anchor: `codex-cli/src/doctor/output.rs` `StatusCounts::from_report`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_status_counts_from_display_statuses` mirrors Rust count initialization and display-status classification: external note count is preserved, ok/idle/warning/fail are counted, and update/note statuses are ignored.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_status_counts_from_display_statuses_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 220 passed, 5 subtests passed.

### src/doctor/output.rs bold no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `bold`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_bold_no_color` mirrors the `!options.color_enabled` branch by returning text unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_bold_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 221 passed, 5 subtests passed.

### src/doctor/output.rs dim no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `dim`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_dim_no_color` mirrors the `!options.color_enabled` branch by returning text unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_dim_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 222 passed, 5 subtests passed.

### src/doctor/output.rs detail_value no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `detail_value`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_detail_value_no_color` mirrors the `!options.color_enabled` branch by returning text unchanged before any detail-text styling is attempted.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_detail_value_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 223 passed, 5 subtests passed.

### src/doctor/output.rs color256 no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `color256`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_color256_no_color` mirrors the `!options.color_enabled` branch by returning text unchanged while accepting an xterm color code argument.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_color256_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 224 passed, 5 subtests passed.

### src/doctor/output.rs green no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `green`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_green_no_color` mirrors the wrapper's no-color behavior by delegating to the color256 no-color helper with Rust's xterm code 10.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_green_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 225 passed, 5 subtests passed.

### src/doctor/output.rs amber no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `amber`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_amber_no_color` mirrors the wrapper's no-color behavior by delegating to the color256 no-color helper with Rust's xterm code 220.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_amber_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 226 passed, 5 subtests passed.

### src/doctor/output.rs orange no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `orange`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_orange_no_color` mirrors the wrapper's no-color behavior by delegating to the color256 no-color helper with Rust's xterm code 214.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_orange_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 227 passed, 5 subtests passed.

### src/doctor/output.rs red no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `red`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_red_no_color` mirrors the wrapper's no-color behavior by delegating to the color256 no-color helper with Rust's xterm code 196.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_red_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 228 passed, 5 subtests passed.

### src/doctor/output.rs cyan no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `cyan`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_cyan_no_color` mirrors the wrapper's no-color behavior by delegating to the color256 no-color helper with Rust's xterm code 117.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_cyan_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 229 passed, 5 subtests passed.

### src/doctor/output.rs very_dim no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `very_dim`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_very_dim_no_color` mirrors the wrapper's no-color behavior by delegating to the color256 no-color helper with Rust's xterm code 238.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_very_dim_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 230 passed, 5 subtests passed.

### src/doctor/output.rs detail_label no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `detail_label`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_detail_label_no_color` mirrors the wrapper's no-color behavior by delegating to the color256 no-color helper with Rust's xterm code 240.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_detail_label_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 231 passed, 5 subtests passed.

### src/doctor/output.rs looks_copyable

- Rust anchor: `codex-cli/src/doctor/output.rs` `looks_copyable`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_looks_copyable` mirrors Rust's copyable URL/path prefix predicate for `http://`, `https://`, `wss://`, `~/`, `/`, `./`, and `../`.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_looks_copyable_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 232 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_token plain/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_token`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_token_plain_no_color` mirrors Rust plain-token handling by separating trailing whitespace, preserving terminal punctuation, and reconstructing unstyled bare tokens unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_token_plain_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 233 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_plain_text plain/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_plain_text`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_plain_text_plain_no_color` mirrors Rust split-inclusive whitespace aggregation over plain unstyled detail tokens.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_plain_text_plain_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 234 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_text plain/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_text`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_text_plain_no_color` mirrors Rust backtick splitting and alternating code/plain segments under disabled color output; this slice also preserves Rust's whitespace-only token reconstruction through `style_detail_token`.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_text_plain_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 235 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token unit/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` unit-token branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_unit_no_color` mirrors Rust handling of `B`, `KB`, `MB`, `GB`, `TB`, `files`, and `file` by delegating to dim styling; with color disabled, visible text is unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_unit_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 236 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token ok/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` `ok` branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_ok_no_color` mirrors Rust by delegating the `ok` token to green styling; with color disabled, visible text remains unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_ok_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 237 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token flag/copyable no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` flag/copyable branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_copyable_no_color` mirrors Rust by delegating bare tokens that start with `--` or satisfy `looks_copyable` to cyan styling; with color disabled, visible text remains unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_copyable_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 238 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token empty

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` empty-token branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_empty` mirrors Rust by returning an empty string when the bare token is empty.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_empty_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 239 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token redacted/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` `<redacted>` branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_redacted_no_color` mirrors Rust's `<redacted>` branch through color256 code 244; with color disabled, visible text remains unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_redacted_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 240 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token falsy/missing no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` falsy and `(missing)` branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_falsy_no_color` mirrors Rust by routing tokens containing `(missing)` or matching `detail::is_falsy` through color256 code 240; with color disabled, visible text remains unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_falsy_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 241 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token label:falsy no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` `label:value` falsy-value branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_label_falsy_no_color` mirrors Rust by splitting once at `:`, applying color256 code 240 only to falsy values, and preserving visible text when color is disabled.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_label_falsy_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 242 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token fallback no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` fallback branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_fallback_no_color` mirrors Rust's final branch by returning the bare token unchanged after excluding all earlier styled-token branches.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_fallback_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 243 passed, 5 subtests passed.

### src/doctor/output.rs style_description ok/idle no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_description` Ok/Idle branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_description_ok_idle_no_color` mirrors Rust by applying highlight_actions then dim for Ok/Idle descriptions; with color disabled, visible text remains unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_description_ok_idle_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 244 passed, 5 subtests passed.

### src/doctor/output.rs style_description update no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_description` Update branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_description_update_no_color` mirrors Rust by applying highlight_actions then amber for Update descriptions; with color disabled, visible text remains unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_description_update_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 245 passed, 5 subtests passed.

### src/doctor/output.rs style_description note/warning/fail no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_description` Note/Warning/Fail branch.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_description_note_warning_fail_no_color` mirrors Rust by returning highlighted text directly for Note, Warning, and Fail descriptions; with color disabled, visible text remains unchanged.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_description_note_warning_fail_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 246 passed, 5 subtests passed.

### src/doctor/output.rs style_note_summary non-update no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_note_summary` non-Update path.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_note_summary_non_update_no_color` mirrors Rust by delegating non-Update note summaries to `style_description`; with color disabled, visible text remains unchanged according to the already-aligned style_description branches.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_note_summary_non_update_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 247 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_bare_token no-color dispatcher

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_bare_token` branch order.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_bare_token_no_color` mirrors Rust branch ordering across empty, redacted, missing/falsy, label:falsy, `ok`, flag/copyable, unit, and fallback bare tokens under disabled color output.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_bare_token_no_color_matches_rust_order`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 248 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_token full no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_token`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_token_no_color` mirrors Rust token trimming, terminal punctuation separation, suffix preservation, and full no-color `style_detail_bare_token` dispatch.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_token_no_color_matches_rust_dispatch`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 249 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_plain_text full no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_plain_text`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_plain_text_no_color` mirrors Rust whitespace-inclusive token aggregation over the full no-color `style_detail_token` dispatcher.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_plain_text_no_color_matches_rust_dispatch`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 250 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_text full no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_text`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_text_no_color` mirrors Rust backtick splitting and alternating code/plain dispatch over the full no-color detail plain-text styling path.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_text_no_color_matches_rust_dispatch`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 251 passed, 5 subtests passed.

### src/doctor/output.rs redact_detail dispatcher

- Rust anchor: `codex-cli/src/doctor/output.rs` `redact_detail` branch order.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail` mirrors Rust's branch order: env-var labels, safe presence values, secret-key matches, then URL-redaction fallback.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_matches_rust_branch_order`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 252 passed, 5 subtests passed.

### src/doctor/output.rs style_detail_token whitespace/no-color

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_detail_token` whitespace-only token path.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_detail_token_no_color` preserves whitespace-only tokens by routing an empty bare token through the empty branch and then reattaching the original suffix.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_detail_token_whitespace_no_color_matches_rust`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 253 passed, 5 subtests passed.

### src/doctor/output.rs style_description no-color dispatcher

- Rust anchor: `codex-cli/src/doctor/output.rs` `style_description` branch order.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_style_description_no_color` mirrors Rust display-status dispatch across Ok/Idle, Update, and Note/Warning/Fail under disabled color output.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_style_description_no_color_matches_rust_dispatch`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` -> 254 passed, 5 subtests passed.

### src/doctor/output.rs redact_detail secret URL path segments

- Rust anchor: `codex-cli/src/doctor/output.rs` test `redact_detail_sanitizes_secret_url_path_segments`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail` preserves the first URL path segment and replaces subsequent secret path segments with `<redacted>`.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_sanitizes_secret_url_path_segments_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs redact_detail URL sanitization

- Rust anchor: `codex-cli/src/doctor/output.rs` test `redact_detail_sanitizes_urls`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail` strips URL userinfo, query, and fragment while preserving scheme, host, first path segment, and surrounding diagnostic text.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_sanitizes_urls_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs redact_detail env var names preservation

- Rust anchor: `codex-cli/src/doctor/output.rs` test `redact_detail_preserves_env_var_names`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail` preserves env-var names in labels containing `env var`/`env vars` instead of treating key-like names as secret values.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_preserves_env_var_names_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs redact_detail secret presence booleans

- Rust anchor: `codex-cli/src/doctor/output.rs` test `redact_detail_preserves_secret_presence_booleans`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_redact_detail` treats safe presence boolean values such as `true` and `false` as non-secret and preserves them even when the label contains token-like words.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_redact_detail_preserves_secret_presence_booleans_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs detailed_no_color_unicode_options

- Rust anchor: `codex-cli/src/doctor/output.rs` test fixture helper `detailed_no_color_unicode_options`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_detailed_no_color_unicode_options` returns the same fixture fields: details enabled, all disabled, unicode output, and color disabled.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_detailed_no_color_unicode_options_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary_no_color_unicode_options

- Rust anchor: `codex-cli/src/doctor/output.rs` test fixture helper `summary_no_color_unicode_options`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_summary_no_color_unicode_options` returns the same fixture fields: details disabled, all disabled, unicode output, and color disabled.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_summary_no_color_unicode_options_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs detailed_all_no_color_unicode_options

- Rust anchor: `codex-cli/src/doctor/output.rs` test fixture helper `detailed_all_no_color_unicode_options`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_detailed_all_no_color_unicode_options` returns the same fixture fields: details enabled, all enabled, unicode output, and color disabled.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_detailed_all_no_color_unicode_options_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs detailed_color_unicode_options

- Rust anchor: `codex-cli/src/doctor/output.rs` test fixture helper `detailed_color_unicode_options`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_detailed_color_unicode_options` returns the same fixture fields: details enabled, all disabled, unicode output, and color enabled.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_detailed_color_unicode_options_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs sample_report check metadata

- Rust anchor: `codex-cli/src/doctor/output.rs` test fixture helper `sample_report`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_check_metadata` mirrors the lightweight fixture metadata: schema/version/overall status and check id/category/status ordering.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_check_metadata_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs sample_report detail/remediation metadata

- Rust anchor: `codex-cli/src/doctor/output.rs` test fixture helper `sample_report` detail/remediation calls.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_detail_metadata` mirrors detail rows and remediation text attached to the Rust sample report checks.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_detail_metadata_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs sample_report StatusCounts

- Rust anchor: `codex-cli/src/doctor/output.rs` `sample_report` plus `StatusCounts::from_report`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_status_counts` derives sample report display statuses and applies the already-aligned StatusCounts counting rules.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_status_counts_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs sample_report non-ok notes

- Rust anchor: `codex-cli/src/doctor/output.rs` `sample_report` plus `non_ok_notes`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_non_ok_notes` mirrors warning/fail note extraction from the Rust sample report, including remediation appending for the failing auth check.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_non_ok_notes_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs sample_report summary_line

- Rust anchor: `codex-cli/src/doctor/output.rs` `sample_report`, `StatusCounts::from_report`, and `summary_line`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_line` derives counts from sample_report metadata and formats the summary line with Rust's overall fail label.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_line_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode footer advice

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` footer lines.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_summary_mode_footer_lines` mirrors the summary-mode final advice and option hint lines.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_summary_mode_footer_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report notes block

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` Notes block.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_notes_lines` mirrors the sample_report summary Notes section header and warning/fail note rows.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_notes_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report section headings

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` section headings.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_section_headings` mirrors the sample_report summary-mode section heading order: Environment, Configuration, Updates, Connectivity, Background Server.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_section_headings_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report Environment rows

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` Environment section rows.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_environment_lines` mirrors the compact Environment rows for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_environment_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report Updates rows

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` Updates section rows.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_updates_lines` mirrors the compact Updates row for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_updates_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report Connectivity rows

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` Connectivity section rows.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_connectivity_lines` mirrors the compact Connectivity rows for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_connectivity_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report Background Server rows

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` Background Server section rows.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_background_server_lines` mirrors the compact Background Server row for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_background_server_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report Configuration rows

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` Configuration section rows.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_configuration_lines` mirrors the compact auth failure row for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_configuration_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report section blocks

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` summary section ordering and grouped rows.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_section_blocks` mirrors the five compact section blocks for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_section_blocks_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report title line

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` title line.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_title_line` mirrors the compact report title for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_title_line_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary-mode sample_report footer summary line

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` footer summary line.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_footer_summary_line` mirrors the compact footer counts/status line for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_footer_summary_line_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary/no-color sample_report full snapshot

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_summary_output_without_color` full expected snapshot.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_no_color_rendered` mirrors the complete compact no-color human output for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_no_color_rendered_matches_rust`.
- Notes: corrected the sample title row separator to Rust's `default �� project codex` while adding full snapshot coverage.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary Environment threads row

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_includes_threads_row_in_environment`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_summary_environment_threads_row` mirrors the rendered `threads` warning row for `state.rollout_db_parity`.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_summary_environment_threads_row_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs detailed state health summary with memories DB

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_includes_memories_db_in_state_health_summary`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_state_health_summary_with_memories_db_lines` mirrors the detailed state health summary row and memories DB integrity detail.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_state_health_summary_with_memories_db_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs summary/ascii sample_report full snapshot

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_supports_ascii_output` full expected snapshot.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_summary_ascii_rendered` mirrors the complete compact ASCII human output for the Rust sample report.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_summary_ascii_rendered_matches_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs detailed redacted credential detail

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_includes_redacted_details`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_sample_report_redacted_detail_lines` mirrors the detailed sample report credential presence detail line.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_sample_report_redacted_detail_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs terminal warning issue rendering

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_explains_terminal_warning_issue`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_terminal_warning_issue_lines` and `_doctor_output_terminal_warning_issue_forbidden_summary` mirror the detailed warning issue output and forbidden summary behavior.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_terminal_warning_issue_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### src/doctor/output.rs promoted notes without status changes

- Rust anchor: `codex-cli/src/doctor/output.rs` test `render_human_report_promotes_notes_without_changing_statuses`.
- Python parity: `pycodex.cli.doctor_updates._doctor_output_promoted_notes_without_status_change_lines` mirrors promoted notes, unchanged status rows, idle app-server output, auth warning, and degraded summary counts.
- Evidence: `tests/test_cli_doctor_updates.py::test_doctor_output_promoted_notes_without_status_change_lines_match_rust`.
- Validation: intentionally not run per acceleration instruction.

### `src/doctor/thread_inventory.rs` rollout/state DB parity summary

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/thread_inventory.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `thread_inventory_check_for_roots` compares rollout JSONL files with state DB thread rows, reports missing/stale/archive-mismatched rows, reads rollout `session_meta` ids before filename fallback, classifies malformed/empty JSONL scans, summarizes model providers and structured session sources, and caps `count_summary` output after 8 categories. Python mirrors these contracts in `doctor_thread_inventory_check` and focused helpers.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k thread_inventory -q` passed on 2026-06-16 with `8 passed, 278 deselected`.
### `src/doctor/background.rs` background server passive status

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/background.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `background_server_check` passively reports daemon state files, not-running/running/stale socket status, persistent vs ephemeral mode, app-server version details, warning remediation, and concise probe-error sanitization/truncation. Python mirrors these contracts through `doctor_background_server_check`, `_background_server_mode`, the default version probe, and `_concise_probe_error`.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k background_server -q` passed on 2026-06-16 with `6 passed, 281 deselected`.
### `src/doctor/runtime.rs` runtime provenance and search readiness

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor/runtime.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `runtime_check` reports process provenance, version, platform, install method, commit, and current executable; Rust `search_check` verifies bundled path readiness or runs system `rg --version`, uses `rg version unknown` when stdout has no first line, and adds repair remediation on warnings. Python mirrors these contracts through `doctor_runtime_check`, `doctor_search_check`, and install/search provider helpers.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_runtime_check or doctor_search_check" -q` passed on 2026-06-16 with `7 passed, 281 deselected`.
### `src/doctor.rs` overall status aggregation

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `overall_status` promotes any failing doctor check above warnings, preserving fail as the overall report status when mixed warning/fail rows are present. Python mirrors this through `_doctor_overall_status` and Rust-derived coverage for `overall_status_prefers_fail`.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k overall_status_prefers_fail -q` passed on 2026-06-16 with `1 passed, 288 deselected`.
### `src/doctor.rs` check progress orchestration

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `run_sync_check` and `run_async_check` notify doctor progress with `begin <label>` before execution and `finish <label> <status>` after the check resolves. Python mirrors these contracts with `_doctor_run_sync_check` and `_doctor_run_async_check`, including Rust-style status labels (`Ok`, `Warning`, `Fail`).
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_run_sync_check or doctor_run_async_check or overall_status_prefers_fail" -q` passed on 2026-06-16 with `3 passed, 288 deselected`.
### `src/doctor.rs` npm package root comparison

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `compare_npm_package_roots` resolves the expected npm package root as `<npm root>/@openai/codex`, reports `NpmRootCheck::Match` when it equals the running package root, and reports `NpmRootCheck::Mismatch` with both roots otherwise. Python mirrors this through `compare_npm_package_roots` and direct Rust-derived tests.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k "compare_npm_package_roots_detects" -q` passed on 2026-06-16 with `2 passed, 291 deselected`.
### `src/doctor.rs` startup warning counts

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `push_startup_warning_counts` emits the total startup warning count and known source buckets for skills, hooks, plugins, MCP, and deprecated settings. Python mirrors this through `_push_startup_warning_counts` and a direct Rust-derived `startup_warning_counts_group_known_sources` test.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k startup_warning_counts_group_known_sources -q` passed on 2026-06-16 with `1 passed, 293 deselected`.
### `src/doctor.rs` interactive config override bridge

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `config_overrides_from_interactive` preserves interactive global CLI options for model, local provider, cwd, approval policy, sandbox mode, OSS raw-reasoning, additional writable roots, and arg0 executable paths. Python mirrors this with `doctor_config_overrides_from_interactive`, fed by `parse_args` interactive root options and arg0 path mappings.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k config_overrides_from_interactive_preserves_global_options -q` passed on 2026-06-16 with `1 passed, 294 deselected`.
### `src/doctor.rs` redacted JSON report structure

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `redacted_json_report` serializes checks as an object, redacts secret values, URL credentials, query strings, issue fields, remediation URLs, preserves repeated detail keys as arrays, and moves freeform detail lines into notes. Python mirrors this through `redacted_doctor_report_mapping`, `redacted_doctor_check_mapping`, and redaction helpers with direct Rust-derived coverage.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k redacted_json_report_structures_and_sanitizes_details -q` passed on 2026-06-16 with `1 passed, 295 deselected`.
### `src/doctor.rs` provider-specific auth checks

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `provider_specific_auth_check` returns an OK provider-specific auth check when the active provider does not require OpenAI auth and has no env-key requirement, and returns a failing check with provider instructions when a required provider env var is missing. Python mirrors this through `_provider_specific_auth_check` and direct Rust-derived coverage.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_specific_auth_allows_non_openai_provider_without_env_key or provider_specific_auth_fails_when_provider_env_key_is_missing" -q` passed on 2026-06-16 with `2 passed, 296 deselected`.
### `src/doctor.rs` stored auth validation

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `stored_auth_issues` reports missing API keys for API-key auth unless an API key env var is present, and reports missing token data plus refresh metadata for default ChatGPT auth. Python mirrors this through `_stored_auth_issues` and direct Rust-derived coverage.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_rejects_missing_api_key or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed on 2026-06-16 with `2 passed, 298 deselected`.
### `src/doctor.rs` provider reachability auth mode

- Rust owner: `codex-cli`
- Rust module: `codex/codex-rs/cli/src/doctor.rs`
- Python module: `pycodex/cli/doctor_updates.py`
- Python tests: `tests/test_cli_doctor_updates.py`
- Status: `complete_slice`
- Evidence: Rust `provider_auth_reachability_mode_from_auth` selects API-key reachability when OpenAI auth is required and either stored auth is API-key mode with a key or `OPENAI_API_KEY` is present in the environment. Python mirrors this through `provider_auth_reachability_mode_from_auth` and direct Rust-derived coverage.
- Focused validation: `python -m pytest tests/test_cli_doctor_updates.py -k provider_reachability_mode_uses_api_key_auth -q` passed on 2026-06-16 with `1 passed, 300 deselected`.
### src/doctor.rs provider reachability active endpoint

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_uses_active_provider_endpoint`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_uses_active_provider_endpoint` verifies provider-auth reachability uses the active provider base URL as the required endpoint and does not attach an OpenAI-compatible route probe for the Azure-style provider URL.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k provider_reachability_uses_active_provider_endpoint -q` passed (`1 passed, 301 deselected`).
### src/doctor.rs provider reachability route probe

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls` verifies provider-auth reachability keeps the configured provider endpoint and attaches an OpenAI-compatible `/models` route probe with query parameters.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls -q` passed (`1 passed, 302 deselected`).
### src/doctor.rs provider reachability Bedrock route probe

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_skips_route_probe_for_bedrock`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_skips_route_probe_for_bedrock` verifies Amazon Bedrock OpenAI-compatible provider endpoints skip the `/models` route probe while remaining configured provider endpoints.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k provider_reachability_skips_route_probe_for_bedrock -q` passed (`1 passed, 303 deselected`).
### src/doctor.rs provider reachability API-key endpoint

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_api_key_does_not_require_chatgpt`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_api_key_does_not_require_chatgpt` verifies API-key reachability uses the OpenAI API base endpoint with a `/models` route probe instead of a ChatGPT endpoint.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k provider_reachability_api_key_does_not_require_chatgpt -q` passed (`1 passed, 304 deselected`).
### src/doctor.rs provider reachability outcome

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_outcome_reports_required_failures`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_outcome_reports_required_failures` verifies provider reachability warning and required-failure outcomes match Rust status and summary text.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k provider_reachability_outcome_reports_required_failures -q` passed (`1 passed, 305 deselected`).
### src/doctor.rs provider reachability route 401

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_route_401_keeps_reachability_ok`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_route_401_keeps_reachability_ok` verifies a `/models` route probe returning HTTP 401 is treated as route existence and keeps reachability status `ok`, even when the base URL probe returns HTTP 404.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k provider_reachability_route_401_keeps_reachability_ok -q` passed (`1 passed, 306 deselected`).
### src/doctor.rs provider reachability route 404

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_route_404_fails_bad_base_url_path`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now emits optional structured `issues` metadata for provider route-probe HTTP 404 failures, and `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_route_404_fails_bad_base_url_path` verifies fail status plus the Rust base_url remedy.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_404_fails_bad_base_url_path or doctor_provider_reachability_check_fails_for_missing_models_route" -q` passed (`2 passed, 306 deselected`).
### src/doctor.rs rollout stats nested files

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `collect_rollout_stats_counts_nested_rollout_files`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_collect_rollout_stats_counts_nested_rollout_files` verifies `_collect_rollout_stats` recurses nested session directories, counts only `rollout-*.jsonl`, preserves total bytes, and `_push_rollout_stats_detail` reports the Rust average-bytes detail format.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "collect_rollout_stats_counts_nested_rollout_files or doctor_state_check_reports_paths_rollouts" -q` passed (`2 passed, 307 deselected`).
### src/doctor.rs HTTP probe status handling

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `http_probe_treats_http_status_as_reachable`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_http_probe_treats_http_status_as_reachable` verifies `_default_http_status_probe` returns HTTP error statuses such as 405 as probe statuses instead of treating them as transport failures.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k http_probe_treats_http_status_as_reachable -q` passed (`1 passed, 309 deselected`).
### src/doctor.rs color enable inputs

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `should_enable_color_respects_terminal_inputs`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_should_enable_color_respects_terminal_inputs` verifies `_color_output_summary` enables color only when `--no-color` and `NO_COLOR` are absent, `TERM` is not `dumb`, stdout is a terminal, and color support is detected.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k should_enable_color_respects_terminal_inputs -q` passed (`1 passed, 310 deselected`).
### src/doctor.rs terminal declared narrow columns

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_check_warns_for_declared_narrow_terminal`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_check_warns_for_declared_narrow_terminal` verifies `doctor_terminal_check` reports `COLUMNS=60` as the Rust warning summary, includes the detail row, and records the affected `COLUMNS` field through structured issue metadata.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "terminal_check_warns_for_declared_narrow_terminal or doctor_terminal_check_warns_for_narrow_terminal_and_locale or doctor_terminal_check_fails_for_dumb_terminal or doctor_terminal_check_fails_for_missing_terminfo" -q` passed (`4 passed, 308 deselected`).
### src/doctor.rs terminal non-UTF8 locale

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_check_warns_for_non_utf8_locale`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_check_warns_for_non_utf8_locale` verifies `LANG=C` warns with the Rust summary, includes `effective locale: C`, and records the UTF-8 locale remedy plus `effective locale` field metadata.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "terminal_check_warns_for_non_utf8_locale or doctor_terminal_check_warns_for_narrow_terminal_and_locale" -q` passed (`2 passed, 311 deselected`).
### src/doctor.rs terminal TERMINFO path

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_check_warns_for_unreadable_terminfo_path`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_check_warns_for_unreadable_terminfo_path` verifies a missing `TERMINFO` path fails with the Rust summary, emits a `(missing)` detail, and records the TERMINFO remedy plus field metadata.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "terminal_check_warns_for_unreadable_terminfo_path or doctor_terminal_check_fails_for_missing_terminfo" -q` passed (`2 passed, 312 deselected`).
### src/doctor.rs terminal remote indicators

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_check_reports_remote_indicators_as_present_only`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_check_reports_remote_indicators_as_present_only` verifies `doctor_terminal_check` reports `SSH_CONNECTION` as present without leaking the raw remote address value.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k terminal_check_reports_remote_indicators_as_present_only -q` passed (`1 passed, 314 deselected`).
### src/doctor.rs terminal Windows console details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_check_includes_windows_console_details`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_check_includes_windows_console_details` verifies `doctor_terminal_check` appends collected Windows console diagnostics to terminal details.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "terminal_check_includes_windows_console_details or doctor_terminal_check_includes_windows_console_details" -q` passed (`2 passed, 314 deselected`).
### src/doctor.rs terminal tmux nonfatal probes

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_check_keeps_tmux_probe_failures_non_fatal`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_check_keeps_tmux_probe_failures_non_fatal` verifies `doctor_terminal_check` remains `ok` when tmux is detected but tmux probe details are unavailable.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "terminal_check_keeps_tmux_probe_failures_non_fatal or doctor_terminal_check_includes_tmux_details_without_changing_status" -q` passed (`2 passed, 315 deselected`).
### src/doctor.rs color disabled reasons

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `color_output_summary_reports_disabled_reasons`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_color_output_summary_reports_disabled_reasons` verifies `_color_output_summary` reports disabled reasons for `--no-color`, `NO_COLOR`, `TERM=dumb`, non-TTY stdout, and missing terminal color support.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "color_output_summary_reports_disabled_reasons or should_enable_color_respects_terminal_inputs" -q` passed (`2 passed, 316 deselected`).
### src/doctor.rs MCP HTTP probe fallback

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_http_probe_falls_back_to_get_when_head_times_out`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_mcp_http_probe_falls_back_to_get_when_head_times_out` verifies `_mcp_http_probe` retries with `GET` when the initial `HEAD` probe fails and returns the GET HTTP status.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k mcp_http_probe_falls_back_to_get_when_head_times_out -q` passed (`1 passed, 318 deselected`).
### src/doctor.rs MCP required missing stdio command

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_check_fails_required_missing_stdio_command`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_mcp_check_fails_required_missing_stdio_command` verifies `doctor_mcp_check` fails required stdio MCP servers whose command cannot be resolved, with Rust-style double-quoted command detail text.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_check_fails_required_missing_stdio_command or doctor_mcp_check_fails_required_remote_stdio_env_var" -q` passed (`2 passed, 318 deselected`).
### src/doctor.rs MCP disabled servers

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_check_ignores_disabled_servers`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_mcp_check_ignores_disabled_servers` verifies disabled MCP servers are counted but do not leak disabled env-var names or perform reachability validation.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_check_ignores_disabled_servers or doctor_mcp_check_ignores_disabled_servers" -q` passed (`2 passed, 319 deselected`).
### src/doctor.rs MCP optional HTTP reachability

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_check_warns_for_optional_http_reachability`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_mcp_check_warns_for_optional_http_reachability` verifies optional streamable HTTP MCP reachability failures produce warning status and `optional reachability failed` detail rather than failing the check.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_check_warns_for_optional_http_reachability or doctor_mcp_check_warns_for_optional_http_reachability" -q` passed (`2 passed, 320 deselected`).
### src/doctor.rs MCP required remote env vars

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_check_fails_required_remote_stdio_env_var`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_mcp_check_fails_required_remote_stdio_env_var` verifies required stdio MCP servers fail when an `env_vars` entry uses `source = "remote"`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_check_fails_required_remote_stdio_env_var or doctor_mcp_check_fails_required_remote_stdio_env_var" -q` passed (`2 passed, 321 deselected`).
### src/doctor.rs stdio command cwd resolution

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stdio_command_resolves`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_stdio_command_resolves_relative_path_against_cwd` verifies `_stdio_command_resolves` resolves commands with path components relative to the configured server `cwd`, matching Rust source behavior.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stdio_command_resolves_relative_path_against_cwd or mcp_check_fails_required_missing_stdio_command" -q` passed (`2 passed, 322 deselected`).
### src/doctor.rs stdio command PATH resolution

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stdio_command_resolves`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_stdio_command_resolves_server_env_path_override` verifies `_stdio_command_resolves` honors the MCP server-provided `PATH` when resolving bare command names.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stdio_command_resolves_server_env_path_override or stdio_command_resolves_relative_path_against_cwd" -q` passed (`2 passed, 323 deselected`).
### src/doctor.rs stdio command empty PATH behavior

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stdio_command_resolves`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_stdio_command_resolves_empty_server_path_does_not_check_cwd_for_bare_command` verifies a server-provided `PATH`, including an empty one, controls bare command lookup and does not fall back to `cwd / command`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stdio_command_resolves_empty_server_path_does_not_check_cwd_for_bare_command or stdio_command_resolves_server_env_path_override or stdio_command_resolves_relative_path_against_cwd" -q` passed (`3 passed, 323 deselected`).
### src/doctor.rs path readiness

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `path_readiness`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_path_readiness_reports_dir_file_and_missing` verifies `_push_path_readiness` emits Rust-style details for directory, file, and missing paths.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "path_readiness_reports_dir_file_and_missing or doctor_state_check_reports_paths_rollouts" -q` passed (`2 passed, 325 deselected`).
### src/doctor.rs push path detail

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `push_path_detail`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_push_path_detail_reports_path_or_none` verifies `_push_optional_path_detail` emits a path when present and `none` when absent.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k push_path_detail_reports_path_or_none -q` passed (`1 passed, 327 deselected`).
### src/doctor.rs push env path detail

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `push_env_path_detail`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_push_env_path_detail_reports_path_or_not_set` verifies `_push_env_path_detail` emits the env path when set and `not set` when absent.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "push_env_path_detail_reports_path_or_not_set or push_path_detail_reports_path_or_none" -q` passed (`2 passed, 327 deselected`).
### src/doctor.rs env var present

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `env_var_present`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_env_var_present_rejects_empty_values` verifies `_env_var_present` treats empty env var values as absent, matching Rust `env::var_os(...).is_some_and(|value| !value.is_empty())`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "env_var_present_rejects_empty_values or provider_reachability_mode_uses_api_key_auth or provider_specific_auth_fails_when_provider_env_key_is_missing" -q` passed (`3 passed, 327 deselected`).
### src/doctor.rs human output options

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `human_output_options`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_human_output_options_maps_command_flags` verifies `_human_output_options_from_flags` maps summary/all/ascii flags and terminal color inputs to `show_details`, `show_all`, `ascii`, and `color_enabled`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "human_output_options_maps_command_flags or color_output_summary_reports_disabled_reasons" -q` passed (`2 passed, 329 deselected`).
### src/doctor.rs standalone release cache

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `standalone_release_cache_details`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_standalone_release_cache_details_counts_entries` verifies `_push_standalone_release_cache_details` counts readable release cache entries and skips missing directories.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "standalone_release_cache_details_counts_entries or doctor_state_check_reports_paths_rollouts" -q` passed (`2 passed, 330 deselected`).
### src/doctor.rs terminal path readiness

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_path_readiness`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_path_readiness_reports_file_dir_and_missing` verifies `_terminal_path_readiness` returns Rust status text and warning flags for directory, file, and missing paths.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "terminal_path_readiness_reports_file_dir_and_missing or terminal_check_warns_for_unreadable_terminfo_path" -q` passed (`2 passed, 331 deselected`).
### src/doctor.rs effective locale

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `effective_locale`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_effective_locale_uses_rust_env_var_order` verifies `_effective_locale` follows Rust `LOCALE_ENV_VARS` order: `LC_ALL`, then `LC_CTYPE`, then `LANG`, returning `None` when no locale value exists.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k effective_locale_uses_rust_env_var_order -q` passed (`1 passed, 333 deselected`).
### src/doctor.rs is non UTF-8 locale

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `is_non_utf8_locale`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_is_non_utf8_locale_matches_rust_substring_detection` verifies `_is_non_utf8_locale` accepts both `utf-8` and `utf8` substrings after case folding, while plain `C` and ISO-8859 locales remain non-UTF-8.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k is_non_utf8_locale_matches_rust_substring_detection -q` passed (`1 passed, 334 deselected`).
### src/doctor.rs terminal size issues

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_size_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_terminal_size_issues` now mirrors Rust measured text and field metadata for terminal dimensions and `COLUMNS`/`LINES` warnings; `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_size_issues_match_rust_measured_fields` locks the contract.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "terminal_size_issues_match_rust_measured_fields or terminal_check_warns_for_declared_narrow_terminal" -q` passed (`2 passed, 334 deselected`).
### src/doctor.rs read probe file

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `read_probe_file`.
- Python parity: `pycodex/cli/doctor_updates.py::_read_probe_file` mirrors Rust's open-and-read-one-byte probe and `_terminal_path_readiness` now reuses it for file readiness checks; `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_read_probe_file_opens_and_reads_one_byte` locks readable empty-file success and missing-file error propagation.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "read_probe_file_opens_and_reads_one_byte or terminal_path_readiness_reports_file_dir_and_missing" -q` passed (`2 passed, 335 deselected`).
### src/doctor.rs executable path exists

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `executable_path_exists`.
- Python parity: `pycodex/cli/doctor_updates.py::_executable_path_exists` now mirrors Rust file checks, including non-file rejection and Unix executable-bit enforcement, and `_stdio_command_resolves` uses it for absolute, relative, and PATH candidates.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_executable_path_exists_matches_rust_file_checks` plus existing stdio command resolution tests.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "executable_path_exists_matches_rust_file_checks or stdio_command_resolves_relative_path_against_cwd or stdio_command_resolves_server_env_path_override or stdio_command_resolves_empty_server_path_does_not_check_cwd_for_bare_command" -q` passed (`4 passed, 334 deselected`).
### src/doctor.rs display optional path

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `display_optional_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_display_optional_path` mirrors Rust optional path display behavior, returning path text for present paths and the literal `none` for absent paths.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_display_optional_path_matches_rust_none_text`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "display_optional_path_matches_rust_none_text or describe_install_context_matches_method_and_package_layout_text" -q` passed (`2 passed, 337 deselected`).
### src/doctor.rs describe method with package layout

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `describe_method_with_package_layout`.
- Python parity: `pycodex/cli/doctor_updates.py::_describe_method_with_package_layout` mirrors Rust output for absent package layouts and for present layouts whose optional resources/path directories are absent.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_describe_method_with_package_layout_matches_rust_optional_layout`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "describe_method_with_package_layout_matches_rust_optional_layout or display_optional_path_matches_rust_none_text" -q` passed (`2 passed, 338 deselected`).
### src/doctor.rs normalize path for compare

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `normalize_path_for_compare`.
- Python parity: `pycodex/cli/doctor_updates.py::normalize_path_for_compare` mirrors Rust canonicalize-or-fallback behavior, normalizes backslashes to `/`, and preserves Windows case-folding semantics.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_normalize_path_for_compare_matches_rust_canonical_fallback`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "normalize_path_for_compare_matches_rust_canonical_fallback or compare_npm_package_roots_detects" -q` passed (`3 passed, 338 deselected`).
### src/doctor.rs display list

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `display_list`.
- Python parity: `pycodex/cli/doctor_updates.py::_display_list` mirrors Rust list formatting for empty and non-empty value lists.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_display_list_matches_rust_none_and_join_text`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "display_list_matches_rust_none_and_join_text or doctor_terminal_title_check_reports_disabled_configuration" -q` passed (`2 passed, 340 deselected`).
### src/doctor.rs feature flag details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `feature_flag_details`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_feature_flag_details` now mirrors Rust legacy feature flag usage detail rows in addition to enabled feature and override summaries.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_feature_flag_details_reports_legacy_usage`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "feature_flag_details_reports_legacy_usage or doctor_config_check_reports_core_config_details" -q` passed (`1 passed, 342 deselected`).
### src/doctor.rs config TOML details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `config_toml_details`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_config_toml_details` mirrors Rust path reporting, missing-file handling, parse success, and parse-error details for `config.toml`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_config_toml_details_reports_missing_ok_and_parse_errors`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "config_toml_details_reports_missing_ok_and_parse_errors or doctor_config_check_reports_core_config_details" -q` passed (`1 passed, 343 deselected`).
### src/doctor.rs terminal env names

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `terminal_env_names`.
- Python parity: `pycodex/cli/doctor_updates.py::_terminal_env_names` mirrors Rust's sorted, de-duplicated terminal environment name set derived from terminal, color, dimension, terminfo, locale, remote, and tmux variables.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_terminal_env_names_match_rust_sorted_union`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k terminal_env_names_match_rust_sorted_union -q` passed (`1 passed, 344 deselected`).
### src/doctor.rs collect env snapshot

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `collect_env_snapshot`.
- Python parity: `pycodex/cli/doctor_updates.py::_collect_env_snapshot` mirrors Rust's split between present environment names and trimmed non-empty values; `doctor_terminal_check` now uses the helper when building live terminal inputs.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_collect_env_snapshot_trims_values_and_tracks_presence`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "collect_env_snapshot_trims_values_and_tracks_presence or terminal_env_names_match_rust_sorted_union" -q` passed (`2 passed, 344 deselected`).
### src/doctor.rs push terminal env values

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `push_terminal_env_values`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_terminal_env_values` mirrors Rust value/present/absent env detail behavior; `doctor_terminal_check` now uses it for terminal dimension and color env rows.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_push_terminal_env_values_reports_present_without_value`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "push_terminal_env_values_reports_present_without_value or collect_env_snapshot_trims_values_and_tracks_presence" -q` passed (`2 passed, 345 deselected`).
### src/doctor.rs push presence env values

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `push_presence_env_values`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_presence_env_values` mirrors Rust presence-only env detail behavior; `doctor_terminal_check` now uses it for remote/GUI terminal indicator rows.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_push_presence_env_values_reports_only_present_names`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "push_presence_env_values_reports_only_present_names or push_terminal_env_values_reports_present_without_value" -q` passed (`2 passed, 346 deselected`).
### src/doctor.rs push terminfo details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `push_terminfo_details`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_terminfo_details` now mirrors Rust's TERMINFO/TERMINFO_DIRS presence behavior: `TERMINFO` has no present-only row, `TERMINFO_DIRS` does, and path lists skip empty entries.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_push_terminfo_details_matches_rust_presence_and_split_paths`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "push_terminfo_details_matches_rust_presence_and_split_paths or terminal_check_warns_for_unreadable_terminfo_path" -q` passed (`2 passed, 347 deselected`).
### src/doctor.rs non empty trimmed

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `non_empty_trimmed`.
- Python parity: `pycodex/cli/doctor_updates.py::_non_empty_trimmed` mirrors Rust tmux probe trimming semantics: empty-after-trim values return `None`, non-empty values return trimmed text.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_non_empty_trimmed_matches_rust_helper`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "non_empty_trimmed_matches_rust_helper or terminal_check_keeps_tmux_probe_failures_non_fatal" -q` passed (`2 passed, 348 deselected`).
### src/doctor.rs tmux probe helpers

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchors: `tmux_display_message`, `tmux_option_value`.
- Python parity: `pycodex/cli/doctor_updates.py::_tmux_display_message` and `_tmux_option_value` mirror Rust tmux argv shapes, trim non-empty output through `_non_empty_trimmed`, and return `None` on runner failures.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_tmux_probe_helpers_match_rust_commands_and_trim_output`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "tmux_probe_helpers_match_rust_commands_and_trim_output or non_empty_trimmed_matches_rust_helper" -q` passed (`2 passed, 349 deselected`).
### src/doctor.rs tmux diagnostic details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `tmux_diagnostic_details`.
- Python parity: `pycodex/cli/doctor_updates.py::_tmux_diagnostic_details` mirrors Rust output ordering: available display-message details first, then one row for every tmux option with `unavailable` fallback.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_tmux_diagnostic_details_matches_rust_order_and_fallbacks`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "tmux_diagnostic_details_matches_rust_order_and_fallbacks or tmux_probe_helpers_match_rust_commands_and_trim_output" -q` passed (`2 passed, 350 deselected`).
### src/doctor.rs is rollout file

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `is_rollout_file`.
- Python parity: `pycodex/cli/doctor_updates.py::_is_rollout_file` mirrors Rust's rollout filename predicate: `.jsonl` extension and `rollout-` filename prefix; `_collect_rollout_stats` now uses the helper.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_is_rollout_file_matches_rust_name_and_extension_predicate`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "is_rollout_file_matches_rust_name_and_extension_predicate or collect_rollout_stats_counts_nested_rollout_files" -q` passed (`2 passed, 351 deselected`).
### src/doctor.rs push rollout stats detail

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `push_rollout_stats_detail`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_rollout_stats_detail` mirrors Rust rollout stats detail formatting for successful scans, zero-file average handling, and scan error reporting.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_push_rollout_stats_detail_reports_error_and_zero_average`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "push_rollout_stats_detail_reports_error_and_zero_average or collect_rollout_stats_counts_nested_rollout_files" -q` passed (`2 passed, 352 deselected`).
### src/doctor.rs rollout stats details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `rollout_stats_details`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_rollout_stats_details` mirrors Rust's active/archived rollout root mapping and labels.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_rollout_stats_details_reports_active_and_archived_roots`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "rollout_stats_details_reports_active_and_archived_roots or push_rollout_stats_detail_reports_error_and_zero_average" -q` passed (`2 passed, 353 deselected`).
### src/doctor.rs sqlite integrity detail

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `sqlite_integrity_detail`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_sqlite_integrity_detail` mirrors Rust missing-database skip behavior and ok integrity reporting for valid SQLite databases.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_sqlite_integrity_detail_reports_missing_and_ok`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "sqlite_integrity_detail_reports_missing_and_ok or doctor_state_check_reports_paths_rollouts" -q` passed (`2 passed, 354 deselected`).
### src/doctor.rs fallback state check

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `fallback_state_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_fallback_state_check` mirrors Rust fallback CODEX_HOME resolution: success returns ok with `CODEX_HOME` detail; failure returns warning with the error detail.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_fallback_state_check_uses_resolver_success_and_error_paths`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "fallback_state_check_uses_resolver_success_and_error_paths or doctor_fallback_state_check_reports" -q` passed (`3 passed, 354 deselected`).
### src/doctor.rs provider auth CODEX env

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` mirrors Rust handling for `CODEX_API_KEY`, `CODEX_ACCESS_TOKEN`, and provider-auth-not-required mode.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_mode_handles_codex_env_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_handles_codex_env_auth or provider_reachability_mode_uses_api_key_auth" -q` passed (`2 passed, 356 deselected`).
### src/doctor.rs provider default API-key route

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_plan_from_parts`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_reachability_plan_from_parts` mirrors Rust API-key default endpoint behavior when no provider base URL is configured, including the default OpenAI API URL and `/models` route probe.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_plan_uses_default_api_key_endpoint_and_route_probe`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_plan_uses_default_api_key_endpoint_and_route_probe or provider_reachability_plan_adds_models_route_probe" -q` passed (`2 passed, 357 deselected`).
### src/doctor.rs stored auth external ID token

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` now mirrors Rust external ChatGPT auth account-id validation by accepting either `tokens.account_id` or `tokens.id_token.chatgpt_account_id`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_stored_auth_validation_accepts_external_id_token_account_id`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_accepts_external_id_token_account_id or stored_auth_validation_rejects_missing_api_key or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed (`3 passed, 357 deselected`).
### src/doctor.rs stored auth empty API-key mode

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_mode` now mirrors Rust's mode inference where a present stored `OPENAI_API_KEY` field selects API-key auth even when the value is empty; `_stored_auth_issues` still reports the trimmed empty key as missing.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_stored_auth_mode_infers_api_key_from_empty_stored_key`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_mode_infers_api_key_from_empty_stored_key or stored_auth_validation_rejects_missing_api_key or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed (`3 passed, 358 deselected`).
### src/doctor.rs provider URL for path

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_url_for_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_url_for_path` is covered against Rust slash trimming, empty-path, and query separator behavior.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_url_for_path_matches_rust_slash_and_query_rules`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_url_for_path_matches_rust_slash_and_query_rules or provider_reachability_plan_adds_models_route_probe" -q` passed (`2 passed, 360 deselected`).
### src/doctor.rs websocket probe warning

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `websocket_probe_warning`.
- Python parity: `pycodex/cli/doctor_updates.py::_websocket_probe_warning` is covered against Rust warning shape: existing details are preserved, the error detail is appended, and WebSocket remediation text is fixed.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_websocket_probe_warning_matches_rust_shape`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "websocket_probe_warning_matches_rust_shape or doctor_websocket_check_reports_timeout" -q` passed (`2 passed, 361 deselected`).
### src/doctor.rs DNS address family details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `dns_address_family_details`.
- Python parity: `pycodex/cli/doctor_updates.py::_dns_address_family_details` is covered against Rust empty successful lookup output and lookup-failure detail shape.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_dns_address_family_details_matches_rust_empty_and_failure_shapes`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "dns_address_family_details_matches_rust_empty_and_failure_shapes or doctor_websocket_check_reports_dns_family_details" -q` passed (`2 passed, 362 deselected`).
### src/doctor.rs stored auth agent identity

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` is covered against Rust agent identity auth validation, including missing, whitespace-only, and present token cases.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_stored_auth_validation_rejects_missing_agent_identity_token`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_rejects_missing_agent_identity_token or stored_auth_validation_accepts_external_id_token_account_id or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed (`3 passed, 362 deselected`).
### src/doctor.rs provider auth non-API stored modes

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` is covered against Rust mapping for stored `chatgptAuthTokens`, `agentIdentity`, absent stored auth, and empty stored auth: all use ChatGPT reachability when OpenAI auth is required and no API-key/CODEX token env overrides are present.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_mode_treats_non_api_stored_auth_as_chatgpt`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_treats_non_api_stored_auth_as_chatgpt or provider_reachability_mode_handles_codex_env_auth or provider_reachability_mode_uses_api_key_auth" -q` passed (`3 passed, 363 deselected, 4 subtests passed`).
### src/doctor.rs provider auth no base URL

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_plan_from_parts`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_reachability_plan_from_parts` is covered against Rust provider-auth mode with no provider base URL, which returns an empty endpoint list.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_reachability_plan_omits_endpoint_when_provider_auth_has_no_base_url`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_plan_omits_endpoint_when_provider_auth_has_no_base_url or provider_reachability_uses_active_provider_endpoint" -q` passed (`2 passed, 365 deselected`).
### src/doctor.rs should probe models route

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `should_probe_models_route`.
- Python parity: `pycodex/cli/doctor_updates.py::_should_probe_models_route` is covered against Rust provider filters: skip Bedrock, skip Azure Responses providers, and probe ordinary OpenAI-compatible base URLs.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_should_probe_models_route_matches_rust_provider_filters`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "should_probe_models_route_matches_rust_provider_filters or provider_reachability_skips_route_probe_for_bedrock or provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls" -q` passed (`3 passed, 365 deselected`).
### src/doctor.rs auth env covers incomplete stored auth

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust status selection where incomplete stored credentials become a warning when an auth environment variable is present.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_doctor_auth_check_warns_when_env_auth_covers_incomplete_stored_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_warns_when_env_auth_covers_incomplete_stored_auth or doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth or doctor_auth_check_reports_environment_auth_and_multiple_env_warning" -q` passed (`3 passed, 366 deselected`).
### src/doctor.rs auth read error

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust stored-auth read failure behavior: fail status, `stored credentials could not be read` summary, error detail, and auth-storage remediation.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_doctor_auth_check_fails_when_stored_auth_cannot_be_read`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_fails_when_stored_auth_cannot_be_read or doctor_auth_check_fails_when_no_credentials_are_available or doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth" -q` passed (`3 passed, 367 deselected`).
### src/doctor.rs provider-specific auth present env

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_specific_auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_specific_auth_check` is covered against Rust present provider-env-key behavior and the `requires_openai_auth=true` no-short-circuit branch.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_provider_specific_auth_uses_present_provider_env_key_and_skips_openai_required`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_specific_auth_uses_present_provider_env_key_and_skips_openai_required or provider_specific_auth_allows_non_openai_provider_without_env_key or provider_specific_auth_fails_when_provider_env_key_is_missing" -q` passed (`3 passed, 368 deselected`).
### src/doctor.rs network CA missing path

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `network_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_network_check` is covered against Rust custom CA env var handling for unreadable/missing paths.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_doctor_network_check_warns_for_missing_custom_ca_path`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_network_check_warns_for_missing_custom_ca_path or doctor_network_check_warns_for_custom_ca_directory or doctor_network_check_reports_proxy_env_presence_and_readable_ca_file" -q` passed (`3 passed, 369 deselected`).
### src/doctor.rs network CA unreadable file

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `network_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_network_check` is covered against Rust custom CA env var handling for existing files that cannot be read.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_doctor_network_check_warns_for_unreadable_custom_ca_file`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_network_check_warns_for_unreadable_custom_ca_file or doctor_network_check_warns_for_missing_custom_ca_path or doctor_network_check_warns_for_custom_ca_directory or doctor_network_check_reports_proxy_env_presence_and_readable_ca_file" -q` passed (`4 passed, 369 deselected`).
### src/doctor.rs proxy env details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `push_proxy_env_details`.
- Python parity: `pycodex/cli/doctor_updates.py::_push_proxy_env_details` is covered against Rust proxy env var order and empty-value filtering.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_push_proxy_env_details_matches_rust_order_and_empty_filter`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "push_proxy_env_details_matches_rust_order_and_empty_filter or doctor_network_check_reports_proxy_env_absence or doctor_network_check_reports_proxy_env_presence_and_readable_ca_file" -q` passed (`3 passed, 371 deselected`).
### src/doctor.rs human output color guards

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `human_output_options` / `should_enable_color`.
- Python parity: `pycodex/cli/doctor_updates.py::_human_output_options_from_flags` is covered against Rust color guards for `NO_COLOR`, `TERM=dumb`, non-terminal stdout, and missing stream color support.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_human_output_options_disables_color_for_rust_terminal_guards`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "human_output_options_disables_color_for_rust_terminal_guards or human_output_options_maps_command_flags or should_enable_color_respects_terminal_inputs" -q` passed (`3 passed, 372 deselected, 4 subtests passed`).
### src/doctor.rs sandbox execve wrapper info

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `sandbox_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_sandbox_check` is covered against Rust helper validation behavior: missing `codex-linux-sandbox` warns, while the execve wrapper path is informational only.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_doctor_sandbox_check_does_not_warn_for_missing_execve_wrapper`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_sandbox_check_does_not_warn_for_missing_execve_wrapper or doctor_sandbox_check_warns_for_missing_linux_helper or doctor_sandbox_check_reads_simple_config_values" -q` passed (`3 passed, 373 deselected`).
### src/doctor.rs installation Bun marker

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `installation_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_installation_check` is covered against Rust `CODEX_MANAGED_BY_BUN` presence semantics, including an empty marker value.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_doctor_installation_check_treats_bun_marker_presence_as_managed`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_installation_check_treats_bun_marker_presence_as_managed or doctor_installation_check_reports_core_installation_details or doctor_installation_check_reports_unset_managed_package_root" -q` passed (`3 passed, 374 deselected`).
### src/doctor.rs generated_at

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `generated_at`.
- Python parity: `pycodex/cli/doctor_updates.py::_doctor_generated_at` is covered against Rust integer Unix-epoch seconds formatting and `unknown` fallback on clock failure.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdatesTests::test_doctor_generated_at_matches_rust_epoch_format_and_unknown_fallback`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_generated_at_matches_rust_epoch_format_and_unknown_fallback or redacted_doctor_report_mapping_defaults_generated_at_like_rust" -q` passed (`2 passed, 376 deselected`).
### src/doctor.rs CheckStatus JSON wire values

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `CheckStatus` / `redacted_json_check`.
- Python parity: `pycodex/cli/doctor_updates.py::_doctor_json_status` is covered against Rust doctor JSON status wire values (`ok`, `warning`, `fail`), with the local `warn` alias normalized to `warning` and unknown statuses conservatively downgraded to `warning`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_json_status_matches_rust_check_status_wire_values`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_json_status_matches_rust_check_status_wire_values or doctor_overall_status_prefers_fail or redacted_doctor_check_mapping_normalizes_unknown_status_to_warning" -q` passed (`3 passed, 376 deselected`).
### src/doctor.rs DoctorCheck optional field mapping

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `DoctorCheck::new` / `DoctorCheck::remediation` / `DoctorCheck::issue`.
- Python parity: `pycodex/cli/doctor_updates.py::DoctorUpdateCheck.to_mapping` is covered against Rust doctor check optional-field semantics: absent remediation/issues are omitted, while present remediation and issues are emitted as structured mapping fields.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_update_check_mapping_matches_rust_optional_fields`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_update_check_mapping_matches_rust_optional_fields or doctor_json_status_matches_rust_check_status_wire_values or doctor_run_sync_check_notifies_progress" -q` passed (`3 passed, 377 deselected`).
### src/doctor.rs load_config web_search override

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `load_config`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_cli_overrides_for_load_config` mirrors Rust doctor `load_config` override merging by preserving root CLI overrides and appending `web_search=live` when interactive `--search`/`web_search` is enabled.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_load_config_web_search_appends_live_override`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "load_config_web_search_appends_live_override or config_overrides_from_interactive_preserves_global_options" -q` passed (`2 passed, 379 deselected`).
### src/doctor.rs HTTP probe error text

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `http_probe_url_with_timeout` / `http_get_probe_status_with_timeout`.
- Python parity: `pycodex/cli/doctor_updates.py::_http_probe_error_text` now mirrors Rust HTTP probe error classification for timeout, connect, and request-builder failures, including `URLError` wrappers around timeout/connect exceptions.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_http_probe_error_text_matches_rust_error_classes`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "http_probe_error_text_matches_rust_error_classes or doctor_provider_reachability_check_reports_required_failure or mcp_http_probe_falls_back_to_get_when_head_times_out" -q` passed (`2 passed, 380 deselected`).
### src/doctor.rs MCP HTTP probe combined failure

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_http_probe_url_with_timeout`.
- Python parity: `pycodex/cli/doctor_updates.py::_mcp_http_probe` is covered against Rust's combined failure text when both HEAD and GET probe attempts fail: `HEAD {head_err}; GET {get_err}`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_mcp_http_probe_reports_head_and_get_failures`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_http_probe_reports_head_and_get_failures or mcp_http_probe_falls_back_to_get_when_head_times_out or http_probe_error_text_matches_rust_error_classes" -q` passed (`3 passed, 380 deselected`).
### src/doctor.rs provider route-probe transport error

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now mirrors Rust route-probe transport-error handling by failing reachability and adding structured issue metadata for the failed `/models` probe.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_probe_transport_error_reports_issue`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_probe_transport_error_reports_issue or provider_reachability_route_404_fails_bad_base_url_path or provider_reachability_route_401_keeps_reachability_ok" -q` passed (`3 passed, 381 deselected`).
### src/doctor.rs provider route-probe warning status

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_route_probe_url` / `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` is covered against Rust route-probe classification where non-2xx, non-401/403, non-404 HTTP statuses warn rather than fail reachability.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_probe_unexpected_status_warns`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_probe_unexpected_status_warns or provider_reachability_route_probe_transport_error_reports_issue or provider_reachability_route_404_fails_bad_base_url_path or provider_reachability_route_401_keeps_reachability_ok" -q` passed (`4 passed, 381 deselected`).
### src/doctor.rs provider reachability no endpoint

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` is covered against Rust's empty-plan branch: no endpoints returns ok, reports `active provider endpoint: none configured`, and omits remediation/issues.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_check_ok_when_no_endpoint_to_probe`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_check_ok_when_no_endpoint_to_probe or provider_reachability_plan_omits_endpoint_when_provider_auth_has_no_base_url or provider_reachability_uses_active_provider_endpoint" -q` passed (`3 passed, 383 deselected`).
### src/doctor.rs provider optional base failure

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` is covered against Rust optional endpoint behavior: base probe failures are counted as warnings, not required failures, and do not add structured issues.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_optional_base_failure_warns`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_optional_base_failure_warns or provider_reachability_check_ok_when_no_endpoint_to_probe or provider_reachability_outcome_reports_required_failures" -q` passed (`3 passed, 384 deselected`).
### src/doctor.rs provider route 403 success

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_route_probe_url` / `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` is covered against Rust route-probe success classification for `HTTP 403`: authenticated-denied `/models` responses prove route reachability and keep the check ok with no issues/remediation.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_403_keeps_reachability_ok`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_403_keeps_reachability_ok or provider_reachability_route_401_keeps_reachability_ok or provider_reachability_route_404_fails_bad_base_url_path or provider_reachability_route_probe_unexpected_status_warns" -q` passed (`4 passed, 384 deselected`).
### src/doctor.rs provider route 204 success

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_route_probe_url` / `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` is covered against Rust route-probe success classification for 2xx statuses beyond 200: `HTTP 204` `/models` responses prove route reachability and keep the check ok with no issues/remediation.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_204_keeps_reachability_ok`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_204_keeps_reachability_ok or provider_reachability_route_403_keeps_reachability_ok or provider_reachability_route_401_keeps_reachability_ok or provider_reachability_route_404_fails_bad_base_url_path" -q` passed (`4 passed, 385 deselected`).
### src/doctor.rs provider auth not-required stored auth

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` is covered against Rust's early `NotRequired` branch: providers that do not require OpenAI auth choose provider reachability even when stored API-key, ChatGPT-token, or agent-identity auth is present.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_mode_not_required_ignores_stored_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_not_required_ignores_stored_auth or provider_reachability_mode_handles_codex_env_auth or provider_reachability_mode_uses_api_key_auth or provider_reachability_mode_treats_non_api_stored_auth_as_chatgpt" -q` passed (`4 passed, 386 deselected, 7 subtests passed`).
### src/doctor.rs provider auth API-key env precedence

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` is covered against Rust's auth-mode branch order: `OPENAI_API_KEY` or `CODEX_API_KEY` selects API-key reachability before `CODEX_ACCESS_TOKEN` or stored ChatGPT auth can select ChatGPT reachability.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_mode_api_key_env_precedes_access_token_and_stored_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_api_key_env_precedes_access_token_and_stored_auth or provider_reachability_mode_handles_codex_env_auth or provider_reachability_mode_not_required_ignores_stored_auth or provider_reachability_mode_treats_non_api_stored_auth_as_chatgpt" -q` passed (`4 passed, 387 deselected, 9 subtests passed`).
### src/doctor.rs provider auth access-token precedence

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` is covered against Rust's auth-mode branch order: `CODEX_ACCESS_TOKEN` selects ChatGPT reachability before stored auth is considered, including stored API-key auth.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_mode_access_token_precedes_stored_api_key`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_access_token_precedes_stored_api_key or provider_reachability_mode_api_key_env_precedes_access_token_and_stored_auth or provider_reachability_mode_uses_api_key_auth or provider_reachability_mode_not_required_ignores_stored_auth" -q` passed (`4 passed, 388 deselected, 5 subtests passed`).
### src/doctor.rs provider ChatGPT configured endpoint

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_plan_from_parts`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_reachability_plan_from_parts` is covered against Rust's ChatGPT auth endpoint branch: the configured ChatGPT base URL is used as the required endpoint and no `/models` route probe is attached.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_plan_uses_configured_chatgpt_endpoint_without_route_probe`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_plan_uses_configured_chatgpt_endpoint_without_route_probe or default_reachability_plan_uses_chatgpt_without_env_auth or provider_reachability_plan_uses_default_api_key_endpoint_and_route_probe or provider_reachability_plan_omits_endpoint_when_provider_auth_has_no_base_url" -q` passed (`4 passed, 389 deselected`).
### src/doctor.rs provider API-key configured endpoint

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_plan_from_parts`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_reachability_plan_from_parts` is covered against Rust's API-key configured-endpoint branch: a supplied provider base URL replaces the default OpenAI API endpoint and receives the `/models` route probe with provider query params.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe or provider_reachability_plan_uses_default_api_key_endpoint_and_route_probe or provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls or provider_reachability_plan_uses_configured_chatgpt_endpoint_without_route_probe" -q` passed (`4 passed, 390 deselected`).
### src/doctor.rs stored auth explicit mode precedence

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_mode` and `_stored_auth_issues` are covered against Rust's explicit-mode precedence: `auth_mode` is used before inferring API-key mode from a stored `OPENAI_API_KEY` field.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_stored_auth_mode_prefers_explicit_auth_mode_over_stored_key_field`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_mode_prefers_explicit_auth_mode_over_stored_key_field or stored_auth_mode_infers_api_key_from_empty_stored_key or stored_auth_validation_rejects_missing_api_key or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed (`4 passed, 391 deselected`).
### src/doctor.rs external ChatGPT account_id

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` is covered against Rust's external ChatGPT token validation: `tokens.account_id` is sufficient account metadata even when `id_token.chatgpt_account_id` is absent, while `last_refresh` remains independently required.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_stored_auth_validation_accepts_external_top_level_account_id`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_accepts_external_top_level_account_id or stored_auth_validation_accepts_external_id_token_account_id or stored_auth_validation_rejects_missing_chatgpt_tokens or stored_auth_mode_prefers_explicit_auth_mode_over_stored_key_field" -q` passed (`4 passed, 392 deselected`).
### src/doctor.rs external ChatGPT blank access token

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` is covered against Rust's external ChatGPT access-token validation: whitespace-only `tokens.access_token` is treated as missing even when account metadata and refresh metadata are present.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_stored_auth_validation_rejects_external_blank_access_token`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_rejects_external_blank_access_token or stored_auth_validation_accepts_external_top_level_account_id or stored_auth_validation_accepts_external_id_token_account_id or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed (`4 passed, 393 deselected`).
### src/doctor.rs external ChatGPT missing token data

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` is covered against Rust's external ChatGPT no-token-data branch: missing `tokens` reports external token data and independently reports missing refresh metadata.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_stored_auth_validation_rejects_external_missing_token_data`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_rejects_external_missing_token_data or stored_auth_validation_rejects_external_blank_access_token or stored_auth_validation_accepts_external_top_level_account_id or stored_auth_validation_accepts_external_id_token_account_id" -q` passed (`4 passed, 394 deselected`).
### src/doctor.rs ChatGPT blank refresh token

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` is covered against Rust's ChatGPT refresh-token validation: whitespace-only `tokens.refresh_token` is treated as missing while `last_refresh` remains an independent metadata issue.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_stored_auth_validation_rejects_blank_chatgpt_refresh_token`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_rejects_blank_chatgpt_refresh_token or stored_auth_validation_rejects_missing_chatgpt_tokens or stored_auth_mode_prefers_explicit_auth_mode_over_stored_key_field or doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth" -q` passed (`4 passed, 395 deselected`).
### src/doctor.rs ChatGPT blank access token

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` is covered against Rust's ChatGPT access-token validation: whitespace-only `tokens.access_token` is treated as missing independently from refresh token and refresh metadata.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_stored_auth_validation_rejects_blank_chatgpt_access_token`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_rejects_blank_chatgpt_access_token or stored_auth_validation_rejects_blank_chatgpt_refresh_token or stored_auth_validation_rejects_missing_chatgpt_tokens or doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth" -q` passed (`4 passed, 396 deselected`).
### src/doctor.rs API-key CODEX_API_KEY fallback

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::_stored_auth_issues` is covered against Rust's API-key env fallback: `CODEX_API_KEY` satisfies API-key stored auth when the stored `OPENAI_API_KEY` value is blank.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_stored_auth_validation_accepts_codex_api_key_env`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "stored_auth_validation_accepts_codex_api_key_env or stored_auth_validation_rejects_missing_api_key or stored_auth_mode_infers_api_key_from_empty_stored_key or env_var_present_rejects_empty_values" -q` passed (`4 passed, 397 deselected`).
### src/doctor.rs provider auth default remediation

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_specific_auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_specific_auth_check` is covered against Rust's default missing-env remediation: when a provider env key is required and no instructions are configured, remediation is `Set {ENV} for the active model provider.`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_specific_auth_uses_default_missing_env_remediation`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_specific_auth_uses_default_missing_env_remediation or provider_specific_auth_fails_when_provider_env_key_is_missing or provider_specific_auth_uses_present_provider_env_key_and_skips_openai_required or provider_specific_auth_allows_non_openai_provider_without_env_key" -q` passed (`4 passed, 398 deselected`).
### src/doctor.rs provider auth env detail preservation

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `provider_specific_auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's detail flow: auth env var details collected before provider-specific auth are preserved when provider auth short-circuits the stored-auth path.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_provider_specific_preserves_auth_env_details`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_provider_specific_preserves_auth_env_details or doctor_auth_check_handles_provider_specific_auth or provider_specific_auth_uses_default_missing_env_remediation or provider_specific_auth_uses_present_provider_env_key_and_skips_openai_required" -q` passed (`4 passed, 399 deselected`).
### src/doctor.rs stored API key presence detail

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` now matches Rust `auth.openai_api_key.is_some()` detail semantics: `stored API key` reports `true` when the stored key field exists, even if the value is empty and still incomplete.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_reports_empty_stored_api_key_as_present`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_reports_empty_stored_api_key_as_present or stored_auth_mode_infers_api_key_from_empty_stored_key or stored_auth_validation_accepts_codex_api_key_env or stored_auth_validation_rejects_missing_api_key" -q` passed (`4 passed, 400 deselected`).
### src/doctor.rs stored agent identity presence detail

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` now matches Rust `auth.agent_identity.is_some()` detail semantics: `stored agent identity` reports `true` when the field exists, even if the value is blank and still incomplete.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_reports_blank_agent_identity_as_present`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_reports_blank_agent_identity_as_present or stored_auth_validation_rejects_missing_agent_identity_token or doctor_auth_check_reports_empty_stored_api_key_as_present or stored_auth_mode_prefers_explicit_auth_mode_over_stored_key_field" -q` passed (`4 passed, 401 deselected`).
### src/doctor.rs auth warning summary precedence

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's warning summary precedence: stored-auth issues select `auth is provided by environment, but stored credentials are incomplete` before the multiple auth env vars warning branch.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_prioritizes_incomplete_stored_summary_over_multiple_env_warning`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_prioritizes_incomplete_stored_summary_over_multiple_env_warning or doctor_auth_check_warns_when_env_auth_covers_incomplete_stored_auth or doctor_auth_check_reports_environment_auth_and_multiple_env_warning or doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth" -q` passed (`4 passed, 402 deselected`).
### src/doctor.rs env-only auth success

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's `Ok(None) if !env_auth_vars.is_empty()` branch: a supported auth env var is sufficient when `auth.json` is absent.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_uses_environment_auth_without_stored_credentials`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_uses_environment_auth_without_stored_credentials or doctor_auth_check_fails_when_no_credentials_are_available or doctor_auth_check_provider_specific_preserves_auth_env_details or doctor_auth_check_reports_environment_auth_and_multiple_env_warning" -q` passed (`4 passed, 403 deselected`).
### src/doctor.rs auth read-error detail shape

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` now matches Rust's stored-auth read-error arm: the check detail contains only the auth read error string, not the pre-collected auth storage/auth file details.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_fails_when_stored_auth_cannot_be_read`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_fails_when_stored_auth_cannot_be_read or doctor_auth_check_fails_when_no_credentials_are_available or doctor_auth_check_uses_environment_auth_without_stored_credentials or doctor_auth_check_reports_empty_stored_api_key_as_present" -q` passed (`4 passed, 403 deselected`).

### src/doctor.rs no-credentials auth details

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's no-credentials branch: auth storage mode and auth file details are retained when no auth env vars and no `auth.json` are available.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_no_credentials_reports_storage_mode_and_auth_file`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_no_credentials_reports_storage_mode_and_auth_file or doctor_auth_check_fails_when_no_credentials_are_available or doctor_auth_check_uses_environment_auth_without_stored_credentials or doctor_auth_check_fails_when_stored_auth_cannot_be_read" -q` passed (`4 passed, 404 deselected`).
### src/doctor.rs auth env var order

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's fixed auth env var reporting order: `OPENAI_API_KEY`, `CODEX_API_KEY`, then `CODEX_ACCESS_TOKEN`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_reports_auth_env_vars_in_rust_order`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_reports_auth_env_vars_in_rust_order or doctor_auth_check_reports_environment_auth_and_multiple_env_warning or doctor_auth_check_prioritizes_incomplete_stored_summary_over_multiple_env_warning" -q` passed (`3 passed, 406 deselected`).
### src/doctor.rs non-OpenAI provider no-env auth

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `provider_specific_auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's provider-specific short-circuit when the active provider does not require OpenAI auth and has no provider env key.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_allows_non_openai_provider_without_env_key`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_allows_non_openai_provider_without_env_key or provider_specific_auth_allows_non_openai_provider_without_env_key or doctor_auth_check_handles_provider_specific_auth or doctor_auth_check_provider_specific_preserves_auth_env_details" -q` passed (`4 passed, 406 deselected`).
### src/doctor.rs provider default remediation entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `provider_specific_auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's missing provider env key branch when no provider-specific instructions are configured, including default remediation and detail ordering.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_missing_provider_env_uses_default_remediation`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_missing_provider_env_uses_default_remediation or provider_specific_auth_uses_default_missing_env_remediation or provider_specific_auth_fails_when_provider_env_key_is_missing or doctor_auth_check_handles_provider_specific_auth" -q` passed (`4 passed, 407 deselected`).
### src/doctor.rs provider OpenAI-required entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `provider_specific_auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's branch where provider-specific auth returns `None` because the active provider still requires OpenAI auth, even when the provider env key is present.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_requires_openai_auth_ignores_provider_env_key`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_requires_openai_auth_ignores_provider_env_key or provider_specific_auth_uses_present_provider_env_key_and_skips_openai_required or doctor_auth_check_missing_provider_env_uses_default_remediation" -q` passed (`3 passed, 409 deselected`).
### src/doctor.rs complete external ChatGPT auth entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's complete `chatgptAuthTokens` stored-credential branch, including the `chatgpt_auth_tokens` mode detail, stored ChatGPT token presence detail, and OK summary.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_accepts_complete_external_chatgpt_auth_tokens`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_accepts_complete_external_chatgpt_auth_tokens or stored_auth_validation_accepts_external_top_level_account_id or stored_auth_validation_accepts_external_id_token_account_id or stored_auth_validation_rejects_external_missing_token_data" -q` passed (`4 passed, 409 deselected`).
### src/doctor.rs complete agent identity auth entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's complete `agentIdentity` stored-credential branch, including the `agent_identity` mode detail, stored agent identity presence detail, and OK summary.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_accepts_complete_agent_identity_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_accepts_complete_agent_identity_auth or doctor_auth_check_reports_blank_agent_identity_as_present or stored_auth_validation_rejects_missing_agent_identity_token" -q` passed (`3 passed, 411 deselected`).
### src/doctor.rs complete ChatGPT auth entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's complete default `chatgpt` stored-credential branch, including the `chatgpt` mode detail, stored ChatGPT token presence detail, and OK summary.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_accepts_complete_chatgpt_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_accepts_complete_chatgpt_auth or stored_auth_validation_rejects_blank_chatgpt_access_token or stored_auth_validation_rejects_blank_chatgpt_refresh_token or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed (`4 passed, 411 deselected`).
### src/doctor.rs complete API-key auth entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's complete `apiKey` stored-credential branch, including the `api_key` mode detail, stored API key presence detail, and OK summary.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_accepts_complete_api_key_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_accepts_complete_api_key_auth or doctor_auth_check_reports_empty_stored_api_key_as_present or stored_auth_validation_rejects_missing_api_key or stored_auth_validation_accepts_codex_api_key_env" -q` passed (`4 passed, 412 deselected`).
### src/doctor.rs env-only multiple auth vars

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's no-stored-auth env branch where multiple auth env vars still produce OK; the multiple-env warning remains stored-auth-only.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_allows_multiple_env_auth_without_stored_credentials`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_allows_multiple_env_auth_without_stored_credentials or doctor_auth_check_uses_environment_auth_without_stored_credentials or doctor_auth_check_reports_environment_auth_and_multiple_env_warning or doctor_auth_check_reports_auth_env_vars_in_rust_order" -q` passed (`4 passed, 413 deselected`).
### src/doctor.rs incomplete stored auth remediation

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` now locks Rust's fail-only remediation for incomplete stored credentials when no auth env vars are present.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth or doctor_auth_check_warns_when_env_auth_covers_incomplete_stored_auth or doctor_auth_check_prioritizes_incomplete_stored_summary_over_multiple_env_warning" -q` passed (`3 passed, 414 deselected`).
### src/doctor.rs multiple env warning no remediation

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` now locks that the stored-auth multiple-env warning branch does not attach remediation; Rust only adds the stored-auth remediation when status is fail.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_reports_environment_auth_and_multiple_env_warning`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_reports_environment_auth_and_multiple_env_warning or doctor_auth_check_allows_multiple_env_auth_without_stored_credentials or doctor_auth_check_warns_when_env_auth_covers_incomplete_stored_auth or doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth" -q` passed (`4 passed, 413 deselected`).
### src/doctor.rs CODEX_API_KEY covers blank stored key

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's API-key stored-auth branch where `CODEX_API_KEY` env auth satisfies a blank stored `OPENAI_API_KEY` field.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_accepts_codex_api_key_env_for_blank_stored_api_key`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_accepts_codex_api_key_env_for_blank_stored_api_key or stored_auth_validation_accepts_codex_api_key_env or doctor_auth_check_reports_empty_stored_api_key_as_present or doctor_auth_check_accepts_complete_api_key_auth" -q` passed (`4 passed, 414 deselected`).
### src/doctor.rs OPENAI_API_KEY covers missing stored key

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's API-key stored-auth branch where `OPENAI_API_KEY` env auth satisfies an absent stored `OPENAI_API_KEY` field.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_accepts_openai_api_key_env_for_missing_stored_api_key`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_accepts_openai_api_key_env_for_missing_stored_api_key or stored_auth_validation_rejects_missing_api_key or doctor_auth_check_accepts_codex_api_key_env_for_blank_stored_api_key or doctor_auth_check_reports_empty_stored_api_key_as_present" -q` passed (`4 passed, 415 deselected`).
### src/doctor.rs explicit ChatGPT mode entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's explicit `chatgpt` auth mode precedence over a present stored `OPENAI_API_KEY` field.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_prefers_explicit_chatgpt_mode_over_stored_api_key_field`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_prefers_explicit_chatgpt_mode_over_stored_api_key_field or stored_auth_mode_prefers_explicit_auth_mode_over_stored_key_field or doctor_auth_check_accepts_complete_api_key_auth or stored_auth_validation_rejects_missing_chatgpt_tokens" -q` passed (`4 passed, 416 deselected`).
### src/doctor.rs explicit external ChatGPT mode entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's explicit `chatgptAuthTokens` auth mode precedence over a present stored `OPENAI_API_KEY` field.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_prefers_explicit_external_chatgpt_mode_over_stored_api_key_field`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_prefers_explicit_external_chatgpt_mode_over_stored_api_key_field or doctor_auth_check_accepts_complete_external_chatgpt_auth_tokens or doctor_auth_check_prefers_explicit_chatgpt_mode_over_stored_api_key_field or stored_auth_validation_rejects_external_missing_token_data" -q` passed (`4 passed, 417 deselected`).
### src/doctor.rs explicit agent identity mode entry

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `auth_check` / `stored_auth_mode_value` / `stored_auth_issues`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_auth_check` is covered against Rust's explicit `agentIdentity` auth mode precedence over a present stored `OPENAI_API_KEY` field.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_auth_check_prefers_explicit_agent_identity_mode_over_stored_api_key_field`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_auth_check_prefers_explicit_agent_identity_mode_over_stored_api_key_field or doctor_auth_check_accepts_complete_agent_identity_auth or doctor_auth_check_reports_blank_agent_identity_as_present or doctor_auth_check_prefers_explicit_external_chatgpt_mode_over_stored_api_key_field" -q` passed (`4 passed, 418 deselected`).
### src/doctor.rs provider mode empty API env

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth` / `env_var_present`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` is covered against Rust's empty-env handling: an empty `OPENAI_API_KEY` is absent and does not block `CODEX_ACCESS_TOKEN` from selecting ChatGPT reachability.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_mode_ignores_empty_api_key_env_before_access_token`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_ignores_empty_api_key_env_before_access_token or provider_reachability_mode_api_key_env_precedes_access_token_and_stored_auth or provider_reachability_mode_access_token_precedes_stored_api_key or env_var_present_rejects_empty_values" -q` passed (`4 passed, 419 deselected, 2 subtests passed`).
### src/doctor.rs provider mode empty CODEX_API_KEY env

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth` / `env_var_present`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` now covers both empty `OPENAI_API_KEY` and empty `CODEX_API_KEY` as absent before `CODEX_ACCESS_TOKEN` selects ChatGPT reachability.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_mode_ignores_empty_api_key_env_before_access_token`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_ignores_empty_api_key_env_before_access_token or provider_reachability_mode_api_key_env_precedes_access_token_and_stored_auth or provider_reachability_mode_access_token_precedes_stored_api_key or env_var_present_rejects_empty_values" -q` passed (`4 passed, 419 deselected, 4 subtests passed`).
### src/doctor.rs provider mode inferred API key

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_auth_reachability_mode_from_auth` / `stored_auth_mode_value`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_auth_reachability_mode_from_auth` is covered against Rust's stored-auth inference path where no explicit mode plus a stored `OPENAI_API_KEY` field selects API-key reachability.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_mode_infers_api_key_from_stored_key_without_auth_mode`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_mode_infers_api_key_from_stored_key_without_auth_mode or provider_reachability_mode_uses_api_key_auth or provider_reachability_mode_treats_non_api_stored_auth_as_chatgpt or stored_auth_mode_infers_api_key_from_empty_stored_key" -q` passed (`4 passed, 420 deselected, 4 subtests passed`).
### src/doctor.rs provider URL empty query

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_url_for_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_url_for_path` now covers Rust's empty query-param guard: an empty query map appends no `?` or `&`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_url_for_path_matches_rust_slash_and_query_rules`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_url_for_path_matches_rust_slash_and_query_rules or provider_reachability_plan_adds_models_route_probe or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe" -q` passed (`3 passed, 421 deselected`).
### src/doctor.rs provider URL empty path query

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_url_for_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_url_for_path` now covers Rust's empty-path plus query-params branch: the base URL is trimmed and query params are appended directly.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_url_for_path_matches_rust_slash_and_query_rules`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_url_for_path_matches_rust_slash_and_query_rules or provider_reachability_plan_adds_models_route_probe or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe" -q` passed (`3 passed, 421 deselected`).
### src/doctor.rs provider URL empty path existing query

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_url_for_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_url_for_path` now covers Rust's empty-path plus existing-query branch: query params append with `&` when the assembled URL already contains `?`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_url_for_path_matches_rust_slash_and_query_rules`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_url_for_path_matches_rust_slash_and_query_rules or provider_reachability_plan_adds_models_route_probe or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe" -q` passed (`3 passed, 421 deselected`).

### src/doctor.rs ChatGPT plan ignores provider endpoint

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_plan_from_parts`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_reachability_plan_from_parts` now covers Rust's ChatGPT-auth branch ignoring provider base URL/query params and using only `chatgpt_base_url` with no route probe.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_plan_chatgpt_ignores_provider_endpoint`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_plan_chatgpt_ignores_provider_endpoint or provider_reachability_plan_uses_configured_chatgpt_endpoint_without_route_probe or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe" -q` passed (`3 passed, 422 deselected`).

### src/doctor.rs API-key Azure route-probe skip

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_plan_from_parts` / `should_probe_models_route`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_reachability_plan_from_parts` now covers API-key reachability planning reusing Rust's Azure Responses route-probe filter, leaving Azure provider endpoints without a `/models` probe.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_plan_api_key_skips_azure_route_probe`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_plan_api_key_skips_azure_route_probe or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe or should_probe_models_route_matches_rust_provider_filters" -q` passed (`3 passed, 423 deselected`).

### src/doctor.rs API-key Bedrock route-probe skip

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_plan_from_parts` / `should_probe_models_route`.
- Python parity: `pycodex/cli/doctor_updates.py::provider_reachability_plan_from_parts` now covers API-key reachability planning reusing Rust's Amazon Bedrock route-probe filter, leaving Bedrock provider endpoints without a `/models` probe.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_plan_api_key_skips_bedrock_route_probe`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_plan_api_key_skips_bedrock_route_probe or provider_reachability_plan_api_key_skips_azure_route_probe or provider_reachability_skips_route_probe_for_bedrock or should_probe_models_route_matches_rust_provider_filters" -q` passed (`4 passed, 423 deselected`).

### src/doctor.rs provider URL multiple slashes

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_url_for_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_url_for_path` now covers Rust's repeated boundary-slash trimming from `trim_end_matches('/')` and `trim_start_matches('/')` before appending query params.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_url_for_path_matches_rust_slash_and_query_rules`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_url_for_path_matches_rust_slash_and_query_rules or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe or provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls" -q` passed (`3 passed, 424 deselected`).

### src/doctor.rs provider URL all-slash path

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_url_for_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_url_for_path` now trims the path before the empty-path branch, matching Rust when a path is made only of `/` characters.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_url_for_path_matches_rust_slash_and_query_rules`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_url_for_path_matches_rust_slash_and_query_rules or provider_reachability_plan_api_key_skips_bedrock_route_probe or provider_reachability_plan_api_key_skips_azure_route_probe or provider_reachability_plan_chatgpt_ignores_provider_endpoint or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe" -q` passed (`5 passed, 422 deselected`).

### src/doctor.rs provider URL all-slash path query

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_url_for_path`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_url_for_path` now covers an all-slash path trimming to the empty-path branch before query params are appended with `?`.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_url_for_path_matches_rust_slash_and_query_rules`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_url_for_path_matches_rust_slash_and_query_rules or provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe or provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls" -q` passed (`3 passed, 424 deselected`).

### src/doctor.rs provider required base failure

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now covers required endpoint base-probe failures: fail status, network remediation, no structured issue, and no route probe after the base failure.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_required_base_failure_fails_without_issue`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_required_base_failure_fails_without_issue or provider_reachability_optional_base_failure_warns or provider_reachability_check_ok_when_no_endpoint_to_probe or provider_reachability_outcome_reports_required_failures" -q` passed (`4 passed, 424 deselected`).

### src/doctor.rs provider outcome required precedence

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_outcome`.
- Python parity: `pycodex/cli/doctor_updates.py::_provider_reachability_outcome` now covers required failures taking fail status precedence even when warnings are also present.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_outcome_reports_required_failures`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_outcome_reports_required_failures or provider_reachability_required_base_failure_fails_without_issue or provider_reachability_route_probe_unexpected_status_warns" -q` passed (`3 passed, 425 deselected`).

### src/doctor.rs provider required failure route warning

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check` / `provider_reachability_outcome`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now covers multi-endpoint aggregation where a required base failure determines fail status while a later route warning is still recorded.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_required_failure_precedes_later_route_warning`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_required_failure_precedes_later_route_warning or provider_reachability_required_base_failure_fails_without_issue or provider_reachability_route_probe_unexpected_status_warns or provider_reachability_outcome_reports_required_failures" -q` passed (`4 passed, 425 deselected`).

### src/doctor.rs provider optional failure later success

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check` / `provider_reachability_outcome`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now covers multi-endpoint aggregation where an optional base failure remains a warning while later required endpoints are still probed successfully.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_optional_failure_survives_later_success`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_optional_failure_survives_later_success or provider_reachability_optional_base_failure_warns or provider_reachability_required_failure_precedes_later_route_warning or provider_reachability_route_401_keeps_reachability_ok" -q` passed (`4 passed, 426 deselected`).

### src/doctor.rs provider route failure later success

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now covers multi-endpoint aggregation where a 404 route failure records an issue but does not stop a later endpoint from being probed successfully.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_failure_allows_later_success`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_failure_allows_later_success or provider_reachability_route_404_fails_bad_base_url_path or provider_reachability_route_401_keeps_reachability_ok or provider_reachability_route_probe_transport_error_reports_issue" -q` passed (`4 passed, 427 deselected`).

### src/doctor.rs provider route transport later success

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now covers multi-endpoint aggregation where a route transport error records an issue but does not stop a later endpoint from being probed successfully.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_transport_error_allows_later_success`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_transport_error_allows_later_success or provider_reachability_route_probe_transport_error_reports_issue or provider_reachability_route_failure_allows_later_success or provider_reachability_route_403_keeps_reachability_ok" -q` passed (`4 passed, 428 deselected`).

### src/doctor.rs provider route warning later success

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check` / `provider_reachability_outcome`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now covers multi-endpoint aggregation where a route warning remains warning status while later endpoints are still probed successfully.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_warning_allows_later_success`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_warning_allows_later_success or provider_reachability_route_probe_unexpected_status_warns or provider_reachability_optional_failure_survives_later_success or provider_reachability_route_failure_allows_later_success" -q` passed (`4 passed, 429 deselected`).

### src/doctor.rs provider multiple success endpoints

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check` / `provider_reachability_outcome`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_provider_reachability_check` now covers multiple successful provider endpoints staying ok while all base and route probes are executed.
- Tests: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_multiple_success_endpoints_stays_ok`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_multiple_success_endpoints_stays_ok or doctor_provider_reachability_check_probes_base_and_models_route or provider_reachability_route_204_keeps_reachability_ok or provider_reachability_route_403_keeps_reachability_ok" -q` passed with 4 passed, 430 deselected.
### src/doctor.rs provider route 404 issue fields

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_reachability_check` test `provider_reachability_route_404_fails_bad_base_url_path`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_404_fails_bad_base_url_path` now locks the structured issue metadata emitted for HTTP 404 `/models` route probes: severity, cause, measured URL/status, expected route contract, remedy, and `route probe` field tagging.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_404_fails_bad_base_url_path or provider_reachability_route_failure_allows_later_success or provider_reachability_route_probe_transport_error_reports_issue or provider_reachability_route_401_keeps_reachability_ok" -q` passed with 4 passed, 430 deselected.
### src/doctor.rs provider route 3xx warning classification

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_route_probe_url` / `provider_reachability_check`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_probe_unexpected_status_warns` now covers HTTP 302 route-probe responses as warning outcomes, matching Rust's non-2xx/non-401/non-403/non-404 classification.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_probe_unexpected_status_warns or provider_reachability_route_warning_allows_later_success or provider_reachability_outcome_reports_required_failures or provider_reachability_route_401_keeps_reachability_ok" -q` passed with 4 passed, 430 deselected, 2 subtests passed.
### src/doctor.rs provider route 2xx bounds

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `provider_route_probe_url` / `provider_reachability_check`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_route_204_keeps_reachability_ok` now covers HTTP 200, 204, and 299 route-probe responses as ok outcomes, matching Rust's `(200..300)` route success classification.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_route_204_keeps_reachability_ok or provider_reachability_route_403_keeps_reachability_ok or provider_reachability_route_401_keeps_reachability_ok or provider_reachability_route_404_fails_bad_base_url_path or provider_reachability_route_probe_unexpected_status_warns" -q` passed with 5 passed, 429 deselected, 5 subtests passed.
### src/doctor.rs provider base status reachability

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `http_probe_url` / `provider_reachability_check`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_provider_reachability_base_http_statuses_still_probe_route` covers Rust's base-probe contract where any successful HTTP probe result is treated as reachable, including HTTP 302 and HTTP 500, and route probing still continues.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "provider_reachability_base_http_statuses_still_probe_route or provider_reachability_required_base_failure_fails_without_issue or provider_reachability_route_401_keeps_reachability_ok or provider_reachability_route_probe_unexpected_status_warns" -q` passed with 4 passed, 431 deselected, 4 subtests passed.
### src/doctor.rs HTTP probe error fallback

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `http_probe_url_with_timeout` / `http_get_probe_status_with_timeout` error mapping.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_http_probe_error_text_matches_rust_error_classes` now covers the fallback path where non-timeout, non-connect, and non-builder probe errors preserve their string text.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "http_probe_error_text_matches_rust_error_classes or provider_reachability_required_base_failure_fails_without_issue or mcp_http_probe_reports_head_and_get_failures or mcp_http_probe_falls_back_to_get_when_head_times_out" -q` passed with 4 passed, 431 deselected.
### src/doctor.rs MCP HEAD success probe

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_http_probe_url_with_timeout`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_mcp_http_probe_head_success_skips_get` covers the Rust branch where a successful `HEAD` probe returns immediately without issuing the `GET` fallback.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_http_probe_head_success_skips_get or mcp_http_probe_falls_back_to_get_when_head_times_out or mcp_http_probe_reports_head_and_get_failures or http_probe_error_text_matches_rust_error_classes" -q` passed with 4 passed, 432 deselected.
### src/doctor.rs MCP GET fallback status passthrough

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_http_probe_url_with_timeout`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_mcp_http_probe_falls_back_to_get_when_head_times_out` now covers GET fallback status passthrough for HTTP 200, 405, and 500 after HEAD failure.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_http_probe_falls_back_to_get_when_head_times_out or mcp_http_probe_head_success_skips_get or mcp_http_probe_reports_head_and_get_failures or http_probe_error_text_matches_rust_error_classes" -q` passed with 4 passed, 432 deselected, 3 subtests passed.
### src/doctor.rs MCP combined error mapping

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `mcp_http_probe_url_with_timeout` plus `http_probe_url_with_timeout` / `http_get_probe_status_with_timeout` error mapping.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_mcp_http_probe_reports_head_and_get_failures` now covers combined `HEAD {head_err}; GET {get_err}` failure text for timeout/connect and builder/fallback string error mappings.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "mcp_http_probe_reports_head_and_get_failures or mcp_http_probe_falls_back_to_get_when_head_times_out or mcp_http_probe_head_success_skips_get or http_probe_error_text_matches_rust_error_classes" -q` passed with 4 passed, 432 deselected, 5 subtests passed.
### src/doctor.rs DNS first IPv6 counts

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `dns_address_family_details`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_dns_address_family_details_counts_and_first_ipv6` covers direct IPv4/IPv6 counting and first-family reporting for a lookup result where IPv6 is returned first.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "dns_address_family_details_counts_and_first_ipv6 or dns_address_family_details_matches_rust_empty_and_failure_shapes or doctor_websocket_check_reports_dns_family_details" -q` passed with 3 passed, 434 deselected.
### src/doctor.rs path readiness other path

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `path_readiness`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_path_readiness_reports_dir_file_and_missing` now covers existing non-file/non-directory paths as `(other)`, in addition to directory, file, and missing path details.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "path_readiness_reports_dir_file_and_missing or doctor_state_check_reports_paths_rollouts_and_missing_db_integrity or fallback_state_check_uses_resolver_success_and_error_paths" -q` passed with 3 passed, 434 deselected.
### src/doctor.rs SQLite integrity non-ok rows

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `sqlite_integrity_detail`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_sqlite_integrity_detail_reports_non_ok_rows` covers non-`ok` integrity rows being joined with `; ` and copied into both details and integrity failures.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "sqlite_integrity_detail_reports_non_ok_rows or sqlite_integrity_detail_reports_missing_and_ok or doctor_state_check_fails_for_invalid_sqlite_database or doctor_state_check_reports_paths_rollouts_and_missing_db_integrity" -q` passed with 4 passed, 434 deselected.
### src/doctor.rs SQLite integrity check errors

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `sqlite_integrity_detail`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_sqlite_integrity_detail_reports_check_errors` covers integrity check errors being formatted as `{label} integrity: {err}` and copied into both details and integrity failures.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "sqlite_integrity_detail_reports_check_errors or sqlite_integrity_detail_reports_non_ok_rows or sqlite_integrity_detail_reports_missing_and_ok or doctor_state_check_fails_for_invalid_sqlite_database" -q` passed with 4 passed, 435 deselected.
### src/doctor.rs rollout stats missing root

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `collect_rollout_stats_inner`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_collect_rollout_stats_missing_root_is_empty_success` covers Rust's `NotFound` branch where a missing rollout root is an empty successful scan with no error.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "collect_rollout_stats_missing_root_is_empty_success or collect_rollout_stats_counts_nested_rollout_files or push_rollout_stats_detail_reports_error_and_zero_average or rollout_stats_details_reports_active_and_archived_roots" -q` passed with 4 passed, 436 deselected.
### src/doctor.rs rollout stats scan error partial counts

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `collect_rollout_stats_inner`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_collect_rollout_stats_preserves_partial_counts_on_scan_error` covers scan errors preserving previously accumulated file/byte counts and stopping traversal with the error text.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "collect_rollout_stats_preserves_partial_counts_on_scan_error or collect_rollout_stats_missing_root_is_empty_success or collect_rollout_stats_counts_nested_rollout_files or push_rollout_stats_detail_reports_error_and_zero_average" -q` passed with 4 passed, 437 deselected.
### src/doctor.rs rollout stats saturating bytes

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `collect_rollout_stats_inner`.
- Python parity: `pycodex/cli/doctor_updates.py::_collect_rollout_stats` now clamps total rollout bytes at `u64::MAX`, matching Rust `saturating_add`; `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_collect_rollout_stats_saturates_total_bytes` covers the overflow boundary.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "collect_rollout_stats_saturates_total_bytes or collect_rollout_stats_preserves_partial_counts_on_scan_error or collect_rollout_stats_missing_root_is_empty_success or collect_rollout_stats_counts_nested_rollout_files" -q` passed with 4 passed, 438 deselected.
### src/doctor.rs rollout saturated average

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `RolloutStats::average_bytes` / `push_rollout_stats_detail`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_collect_rollout_stats_saturates_total_bytes` now also asserts the integer average rendered after rollout total bytes saturate at `u64::MAX`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "collect_rollout_stats_saturates_total_bytes or collect_rollout_stats_preserves_partial_counts_on_scan_error or push_rollout_stats_detail_reports_error_and_zero_average" -q` passed with 3 passed, 439 deselected.
### src/doctor.rs standalone cache file entries

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `standalone_release_cache_details`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_standalone_release_cache_details_counts_entries` now covers file entries as well as directory entries in the release cache count, matching Rust `read_dir(...).filter_map(Result::ok).count()`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "standalone_release_cache_details_counts_entries or doctor_state_check_reports_paths_rollouts_and_missing_db_integrity" -q` passed with 2 passed, 440 deselected.
### src/doctor.rs env var whitespace present

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `env_var_present`.
- Python parity: `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_env_var_present_rejects_empty_values` now covers whitespace-only env values as present, matching Rust's non-empty `OsString` check.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "env_var_present_rejects_empty_values or provider_reachability_mode_ignores_empty_api_key_env_before_access_token or provider_reachability_mode_api_key_env_precedes_access_token_and_stored_auth or mcp_check_fails_required_missing_env" -q` passed with 3 passed, 439 deselected, 4 subtests passed.
### src/doctor.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: local `#[cfg(test)]` inventory and module helper surface.
- Python parity: added `pycodex/cli/DOCTOR_RS_STATUS.md` as the focused status ledger for this large module, separate from sibling `src/doctor/*` modules.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.
### src/doctor.rs local Rust test closeout audit

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: local `#[cfg(test)]` test inventory.
- Python parity: `pycodex/cli/DOCTOR_RS_STATUS.md` now records 35 reconciled Rust tests and 4 remaining name-level reconciliation items for the module promotion pass.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.
### src/doctor.rs local Rust test-name reconciliation complete

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: local `#[cfg(test)]` test inventory.
- Python parity: added exact Rust test comments for the final four name-level gaps: `read_probe_file_rejects_unreadable_file`, `executable_path_exists_rejects_non_executable_file`, `terminal_check_warns_for_dumb_terminal`, and `terminal_check_warns_for_narrow_terminal`; `pycodex/cli/DOCTOR_RS_STATUS.md` now records all 39 local Rust tests as reconciled and marks the module `complete_candidate`.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.
### src/doctor.rs non-test helper surface audit

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchor: `run_doctor`, `build_report`, `load_config`, `config_overrides_from_interactive`, report JSON helpers, check runners, and source-local diagnostic helpers.
- Python parity: `pycodex/cli/DOCTOR_RS_STATUS.md` now records the non-test helper mapping: orchestration lives in `pycodex/cli/parser.py::_run_doctor`, report/config/check helpers live in `pycodex/cli/doctor_updates.py`, and async/progress/network internals are documented as intentional Python adaptations while preserving the visible report contract.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/output/detail.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/output/detail.rs`.
- Rust anchor: source-local detail row/value transformation helpers; this module has no local Rust `#[test]` functions.
- Python parity: added `pycodex/cli/DOCTOR_OUTPUT_DETAIL_RS_STATUS.md` as the focused status ledger for this module, recording coverage of detail APIs, parsing helpers, humanization helpers, category renderers, row assembly helpers, issue metadata, and the `detail_lines` pipeline.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/output.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/output.rs`.
- Rust anchor: human doctor report renderer, grouping constants, status/note/summary helpers, redaction helpers, style helpers, sample report fixtures, and 17 local Rust tests.
- Python parity: added `pycodex/cli/DOCTOR_OUTPUT_RS_STATUS.md` as the focused status ledger for this module with status `closeout_in_progress`; existing `_doctor_output_*` helpers and `redact_doctor_detail` carry the mapped behavior.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/output.rs local Rust test-name reconciliation complete

- Rust crate/module: `codex-cli` / `src/doctor/output.rs`.
- Rust anchor: local `#[cfg(test)]` test inventory with 17 named Rust tests.
- Python parity: `pycodex/cli/DOCTOR_OUTPUT_RS_STATUS.md` now records all 17 local Rust tests as reconciled through existing exact Python parity comments, `pycodex/cli/TEST_ALIGNMENT.md` entries, or explicit status-ledger mappings for snapshot/color/feature-flag/detail-style tests.
- Status: module moved from `closeout_in_progress` to `complete_candidate`.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/output.rs summary no-color Unicode snapshot validation

- Rust crate/module: `codex-cli` / `src/doctor/output.rs`.
- Rust anchors: `render_human_report_supports_summary_output_without_color`, `summary_line`, `status_marker_slot`, and `row_description`.
- Python parity: `_doctor_output_sample_report_summary_*` helpers now preserve Rust no-color Unicode markers/separators/remediation text (`✓`, `⚠`, `✗`, `·`, `─`, and `—`) instead of stale replacement-character fixtures.
- Status: module moved from `complete_candidate` to `complete`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q` passed (`442 passed, 32 subtests passed`).

### src/doctor/progress.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/progress.rs`.
- Rust anchor: `should_show_progress` plus the local `DoctorProgress` lifecycle surface.
- Python parity: added `pycodex/cli/DOCTOR_PROGRESS_RS_STATUS.md` with status `complete_candidate`; `_should_show_doctor_progress` and `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_progress_visibility_matches_rust` reconcile all 4 local Rust tests.
- Adaptation: exact stderr carriage-return rendering remains an implementation detail; Python tracks the user-visible progress selection contract.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/system.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/system.rs`.
- Rust anchor: `SystemCheckInputs::detect`, `system_check`, `system_check_from_inputs`, and the 2 local Rust tests.
- Python parity: added `pycodex/cli/DOCTOR_SYSTEM_RS_STATUS.md` with status `complete_candidate`; `doctor_system_check` plus focused Python tests reconcile OS language, missing-language fallback, and Rust `LOCALE_ENV_VARS` detail ordering.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/title.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/title.rs`.
- Rust anchor: terminal-title item parsing, alias normalization, project source/value selection, invalid-item warnings, truncation shape, and 7 local Rust tests.
- Python parity: added `pycodex/cli/DOCTOR_TITLE_RS_STATUS.md` with status `complete_candidate`; `doctor_terminal_title_check` and helper coverage reconcile default, disabled, project fallback/omission, invalid item, all-invalid, alias, and ASCII truncation behavior.
- Adaptation: Rust grapheme-cluster truncation is documented; current Python parity records the ASCII truncation shape present in Rust tests.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/git.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/git.rs`.
- Rust anchor: Git discovery, `git_check_from_inputs`, summary/warning/remediation branches, branch normalization, `.git` entry summaries, command-output normalization, old Windows Git warnings, and 5 local Rust tests.
- Python parity: added `pycodex/cli/DOCTOR_GIT_RS_STATUS.md` with status `complete_candidate`; `doctor_git_check`, `GitCheckInputs`, and helper tests reconcile all local Rust tests plus detached HEAD, empty branch/fsmonitor, command output, gitfile, and no-Git/no-repo behavior.
- Adaptation: Rust Tokio process execution/timeout is represented through Python's injectable command runner and observable result contract.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/updates.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/updates.rs`.
- Rust anchors: `updates_check`, `push_cached_version_details`, `push_latest_version_details`, `push_latest_version_probe_error_details`, `fetch_latest_version`, `fetch_latest_github_release_version`, `fetch_homebrew_cask_version`, `http_get_json`, `is_newer`, `parse_version`, `VersionInfo`, and `update_action_label`.
- Rust tests: `is_newer_compares_plain_semver` and `update_action_labels_install_contexts`.
- Python parity: added `pycodex/cli/DOCTOR_UPDATES_RS_STATUS.md`; current implementation maps the module through `pycodex/cli/doctor_updates.py`, `pycodex/cli/update_action.py`, and `pycodex/cli/update_versions.py`, with existing Rust-derived coverage in `tests/test_cli_doctor_updates.py` for cache details, latest-version details/probe failures, fetch routing, npm update-target branches, semver comparison, and update-action labels.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/runtime.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/runtime.rs`.
- Rust anchors: `runtime_check`, `search_check`, `install_method_name`, `search_provider`, and `build_commit`.
- Rust tests: no local `#[test]` functions in this module; parity is source-contract based.
- Python parity: added `pycodex/cli/DOCTOR_RUNTIME_RS_STATUS.md` with status `complete_candidate`; `doctor_runtime_check`, `doctor_search_check`, `_runtime_install_method_name`, and `_select_rg_command_and_provider` cover runtime provenance, install-method summary, build commit fallback, bundled/system search readiness, empty `rg --version` fallback, and warning remediation.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/background.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/background.rs`.
- Rust anchors: `background_server_check`, `push_file_detail`, `server_mode`, `SocketStatus`, `socket_status`, and `concise_probe_error`.
- Rust tests: `not_running_background_server_stays_ok_without_version`, `running_background_server_reports_app_server_version`, and `failed_version_probe_reports_unavailable`.
- Python parity: added `pycodex/cli/DOCTOR_BACKGROUND_RS_STATUS.md` with status `complete_candidate`; `doctor_background_server_check`, `_push_file_detail`, `_background_server_mode`, `_default_app_server_version_probe`, and `_concise_probe_error` cover passive daemon state details, not-running/running/stale summaries, version details, persistent/ephemeral mode, remediation, and concise probe-error rendering.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor/thread_inventory.rs module status audit

- Rust crate/module: `codex-cli` / `src/doctor/thread_inventory.rs`.
- Rust anchors: `thread_inventory_check`, `thread_inventory_check_for_roots`, `missing_state_db_check`, `parity_check_from_scan_and_rows`, rollout scanning helpers, `source_category`, `count_summary`, and sample helpers.
- Rust tests: `thread_inventory_check_ok_when_rollouts_match_db`, `thread_inventory_check_warns_for_missing_stale_and_mismatched_rows`, `source_category_coarsens_structured_sources`, and `count_summary_caps_distinct_values`.
- Python parity: added `pycodex/cli/DOCTOR_THREAD_INVENTORY_RS_STATUS.md` with status `complete_candidate`; `doctor_thread_inventory_check` and focused helpers cover rollout/state DB parity, session_meta ID preference, malformed/empty rollout scans, structured source summaries, provider summaries, count-summary capping, and warning issue payloads for missing DB/read errors/parity differences/scan issues.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/exit_status.rs module status audit

- Rust crate/module: `codex-cli` / `src/exit_status.rs`.
- Rust anchor: `handle_exit_status`.
- Rust tests: no local `#[test]` functions in this module; parity is source-contract based.
- Python parity: added `pycodex/cli/EXIT_STATUS_RS_STATUS.md` with status `complete_candidate`; `exit_code_from_returncode` preserves normal exit codes, maps negative Python subprocess return codes to Rust Unix `128 + signal` semantics, and falls back to `1` for missing status.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/wsl_paths.rs module status audit

- Rust crate/module: `codex-cli` / `src/wsl_paths.rs`.
- Rust anchors: `win_path_to_wsl`, `normalize_for_wsl`, and the `is_wsl` re-export dependency.
- Rust tests: `win_to_wsl_basic` and `normalize_is_noop_on_unix_paths`.
- Python parity: added `pycodex/cli/WSL_PATHS_RS_STATUS.md` with status `complete_candidate`; `win_path_to_wsl` and `normalize_for_wsl` cover Windows drive path conversion, drive-root conversion, non-drive/UNC rejection, no-op non-WSL behavior, and deterministic WSL branch selection.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/app_cmd.rs module status audit

- Rust crate/module: `codex-cli` / `src/app_cmd.rs`.
- Rust anchors: `AppCommand` and `run_app` workspace canonicalization before desktop-app launch.
- Rust tests: no local `#[test]` functions in this module; parity is source-contract based.
- Python parity: added `pycodex/cli/APP_CMD_RS_STATUS.md` with status `complete_candidate`; `AppCommand`, `workspace_for_app_command`, and parser app-command dispatch cover default path, optional `--download-url`, existing-path canonicalization, missing-path fallback, and platform launcher delegation.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/state_db_recovery.rs module status audit

- Rust crate/module: `codex-cli` / `src/state_db_recovery.rs`.
- Rust anchors: `startup_error`, `is_locked`, `confirm_repair`, `repair_files`, `print_repair_backups`, `print_diagnostic_guidance`, `print_locked_guidance`, `sqlite_paths`, `backup_path`, and `print_technical_details`.
- Rust tests: `repair_backs_up_owned_database_files`, `repair_replaces_blocking_sqlite_home_file`, and `lock_failures_skip_repair`.
- Python parity: added `pycodex/cli/STATE_DB_RECOVERY_RS_STATUS.md` with status `complete_candidate`; `state_db_*` CLI exports and `tests/test_cli_state_db_recovery.py` cover embedded startup-error extraction, lock detection, SQLite sidecar expansion, backup sequencing, blocking-home repair, owned DB backup repair, empty repair guard, and recovery stderr guidance.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs module status audit

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors audited: `run_command_under_seatbelt`, `run_command_under_landlock`, `run_command_under_windows_sandbox`, `run_command_under_sandbox`, `spawn_debug_sandbox_child`, `load_debug_sandbox_config_with_codex_home`, `build_debug_sandbox_config_with_loader_overrides`, `config_uses_permission_profiles`, `cli_overrides_use_legacy_sandbox_mode`, `ManagedRequirementsMode`, and the Windows stdio bridge tests.
- Python parity: added `pycodex/cli/DEBUG_SANDBOX_RS_STATUS.md` with status `partial`; existing helpers and tests cover managed requirements mode, legacy override detection, permission-profile overrides, effective-config probing, read-only default selection, loader override adaptation, platform guard messages, child env markers, Unix `arg0`, and Windows stdio chunk/output behavior.
- Remaining gaps: backend execution entrypoints and Rust config-builder integration paths are not yet complete in Python, so the module was not promoted to `complete_candidate`.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs execution-plan shim

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox`, `spawn_debug_sandbox_child`, and `ManagedRequirementsMode::for_profile_invocation`.
- Python parity: added `DebugSandboxExecutionPlan` and `build_debug_sandbox_execution_plan`, exported them from `pycodex.cli`, and routed `_run_sandbox` through the plan so command, cwd, platform backend choice, permission profile, managed requirements mode, and child env preparation are module-owned before compatibility subprocess execution.
- Remaining gaps: real Seatbelt/Landlock/Windows backend spawning, permission-profile cwd/backend args, network proxy metadata/application, and full config-loader integration remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs permission-profile cwd and network env plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` and `spawn_debug_sandbox_child`.
- Python parity: `DebugSandboxExecutionPlan` now records `permission_profile_cwd` from the resolved cwd, matching Rust's current `let permission_profile_cwd = cwd.clone()` behavior; `build_debug_sandbox_execution_plan` also applies network env values before the disabled-network marker, preserving Rust `apply_env` then `CODEX_SANDBOX_NETWORK_DISABLED=1` ordering.
- Python tests added but not run: `test_execution_plan_uses_cwd_for_permission_profile_cwd` and `test_execution_plan_applies_network_env_before_disabled_marker` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real backend spawning, backend-specific command args, network proxy lifecycle/metadata, and full config-loader integration remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs backend spawn input plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` backend match arms and `spawn_debug_sandbox_child` program/arg0 inputs.
- Python parity: `DebugSandboxExecutionPlan` now records `backend_program`, `backend_args`, and `child_arg0`; Landlock records the configured `codex_linux_sandbox_exe` plus `codex-linux-sandbox` child arg0, Seatbelt records `/usr/bin/sandbox-exec` with no child arg0, and Windows remains a special session path with no subprocess backend program metadata.
- Python tests added but not run: `test_execution_plan_records_backend_program_args_and_arg0` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real backend spawning, network proxy lifecycle/metadata, and full config-loader integration remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs config-load decision plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `load_debug_sandbox_config_with_codex_home` and `build_debug_sandbox_config_with_loader_overrides`.
- Python parity: added `DebugSandboxConfigLoadPlan` and `build_debug_sandbox_config_load_plan`, exported the plan API from `pycodex.cli`, and captured permission-profile override insertion, legacy `sandbox_mode` detection, harness cwd, codex-linux-sandbox exe, codex-home fallback cwd, managed-requirements loader override adjustment, strict-config propagation, and read-only retry selection.
- Python tests added but not run: `test_config_load_plan_matches_rust_loader_decisions` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual ConfigBuilder-backed loading, real backend spawning, and network proxy lifecycle/metadata remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs network proxy decision plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` managed network proxy setup before backend spawn.
- Python parity: added `DebugSandboxNetworkPlan` and `build_debug_sandbox_network_plan`, exported the plan API from `pycodex.cli`, and captured proxy-start selection when a network spec is present, permission-profile forwarding, managed-network-requirements forwarding, default audit metadata, proxy env capture, and child-process lifetime documentation.
- Python tests added but not run: `test_network_plan_matches_rust_proxy_lifetime_decision` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real network proxy startup/application, backend spawning, and actual ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs subprocess argv selection

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `spawn_debug_sandbox_child` program/args selection and `run_command_under_sandbox` backend dispatch inputs.
- Python parity: added `debug_sandbox_subprocess_argv`, exported it from `pycodex.cli`, and routed `_run_sandbox` through it so backend program/args are preferred when present while Windows/direct compatibility execution falls back to the original command tuple.
- Python tests added but not run: `test_subprocess_argv_prefers_backend_program_when_present` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock backend arg generation, Windows session execution, network proxy startup/application, and actual ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs backend args builder input plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `create_seatbelt_command_args` and `create_linux_sandbox_command_args_for_permission_profile` call-site inputs inside `run_command_under_sandbox`.
- Python parity: added `DebugSandboxBackendArgsPlan` and `build_debug_sandbox_backend_args_plan`, exported them from `pycodex.cli`, and captured command, cwd, permission-profile cwd, permission profile, Landlock legacy mode, Landlock managed-network proxy allowance, Seatbelt extra Unix sockets, and Seatbelt `enforce_managed_network=false` semantics at the module boundary.
- Python tests added but not run: `test_backend_args_plan_matches_rust_builder_inputs` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: calling real Seatbelt/Landlock argv builders, Windows session execution, network proxy startup/application, and actual ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs Windows session plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_windows_session` elevated/legacy spawn inputs and output drain timeout.
- Python parity: added `DebugSandboxWindowsSessionPlan` and `build_debug_sandbox_windows_session_plan`, exported from `pycodex.cli`, capturing elevated vs legacy branch, effective permission-profile inputs, command/cwd/env, codex_home, override/deny-list defaults, `tty=false`, `stdin_open=true`, private-desktop flag, and 5 second output drain timeout.
- Python tests added but not run: `test_windows_session_plan_matches_rust_spawn_inputs` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows session spawning, stdio bridge control flow, ctrl-c termination, and process exit wiring remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs public entrypoint plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_seatbelt`, `run_command_under_landlock`, and `run_command_under_windows_sandbox` public entrypoint forwarding into `run_command_under_sandbox`.
- Python parity: added `DebugSandboxEntrypointPlan` and `build_debug_sandbox_entrypoint_plan`, exported from `pycodex.cli`, capturing command/cwd/profile/config override forwarding, managed-requirements mode selection, loader override propagation, optional `codex_linux_sandbox_exe`, and Seatbelt-only `log_denials` plus extra Unix socket forwarding.
- Python tests added but not run: `test_entrypoint_plan_matches_rust_public_entrypoint_forwarding` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: functional entrypoint wiring, actual backend spawning, Windows session execution, network proxy startup/application, and actual ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs child spawn plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `spawn_debug_sandbox_child` child process setup and env ordering.
- Python parity: added `DebugSandboxChildSpawnPlan` and `build_debug_sandbox_child_spawn_plan`, exported from `pycodex.cli`, capturing program/args/cwd, Unix `arg0` handling, `apply_env`-style env updates before the disabled-network marker override, `env_clear`, inherited stdio, and `kill_on_drop=true`.
- Python tests added but not run: `test_child_spawn_plan_matches_rust_spawn_helper_ordering` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: functional child spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, network proxy startup/application, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs network env application plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: managed network proxy `network.apply_to_env` use inside the Seatbelt/Landlock `apply_env` closures and the later disabled-network marker in `spawn_debug_sandbox_child`.
- Python parity: added `DebugSandboxNetworkEnvApplicationPlan` and `build_debug_sandbox_network_env_application_plan`, exported from `pycodex.cli`, capturing Seatbelt sandbox marker insertion, proxy env application only when a proxy exists, and the disabled-network marker override after proxy env mutation.
- Python tests added but not run: `test_network_env_application_plan_matches_rust_apply_env_order` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual managed network proxy startup, functional child spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs Seatbelt denial logger plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: macOS `DenialLogger` lifecycle in `run_command_under_sandbox`.
- Python parity: added `DebugSandboxDenialLoggerPlan` and `build_debug_sandbox_denial_logger_plan`, exported from `pycodex.cli`, capturing creation only when denial logging is requested on macOS, child-spawn attachment, post-wait finish, and the denial summary strings.
- Python tests added but not run: `test_denial_logger_plan_matches_rust_macos_lifecycle` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: functional denial log collection/output, managed network proxy startup, functional child spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs shared run flow plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: shared `run_command_under_sandbox` orchestration order.
- Python parity: added `DebugSandboxRunFlowPlan` and `build_debug_sandbox_run_flow_plan`, exported from `pycodex.cli`, capturing config loading with `strict_config=false`, `config.cwd` reuse for command cwd and permission-profile cwd, env creation before Windows special-case handling, Windows session exit/error before denial logger and network setup, denial logger creation before network proxy startup, child wait before denial logger finish, and final exit-status handling for non-Windows backends.
- Python tests added but not run: `test_run_flow_plan_matches_rust_shared_sandbox_order` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: concrete phase execution, managed network proxy startup, functional child spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs execution-to-child-spawn bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` backend spawn metadata flowing into `spawn_debug_sandbox_child`.
- Python parity: added `debug_sandbox_child_spawn_plan_from_execution_plan`, exported from `pycodex.cli`, converting `DebugSandboxExecutionPlan` into `DebugSandboxChildSpawnPlan` while preserving backend program/args, direct command fallback, cwd, env, Unix `arg0`, and disabled-network marker state.
- Python tests added but not run: `test_execution_plan_converts_to_child_spawn_plan` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real child process spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs exit status plan

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `exit_status.rs::handle_exit_status` as called by `run_command_under_sandbox` after child wait.
- Python parity: added `DebugSandboxExitStatusPlan` and `build_debug_sandbox_exit_status_plan`, exported from `pycodex.cli`, capturing normal exit-code propagation, Unix `128 + signal` handling, and generic fallback exit code 1.
- Python tests added but not run: `test_exit_status_plan_matches_rust_handle_exit_status` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real process termination from the planned status, real child process spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs denial summary formatter

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: Seatbelt denial summary output after `DenialLogger::finish`.
- Python parity: added `format_debug_sandbox_denial_summary`, exported from `pycodex.cli`, matching the leading blank line, `=== Sandbox denials ===` header, `None found.` empty summary, and `({name}) {capability}` denial lines.
- Python tests added but not run: `test_denial_summary_format_matches_rust_output` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: functional denial log collection, real process termination, real child process spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs process termination helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `exit_status.rs::handle_exit_status` process termination as called after sandbox child wait.
- Python parity: added `raise_debug_sandbox_exit_status`, exported from `pycodex.cli`, raising `SystemExit` with the process exit code selected by `DebugSandboxExitStatusPlan`.
- Python tests added but not run: `test_raise_exit_status_matches_rust_process_exit` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: wiring process termination into the real child wait path, real child process spawning, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, functional denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs network proxy error formatter

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: managed network proxy startup error context in `run_command_under_sandbox`.
- Python parity: added `format_debug_sandbox_network_proxy_error`, exported from `pycodex.cli`, matching Rust's `failed to start managed network proxy: {err}` message.
- Python tests added but not run: `test_network_proxy_error_format_matches_rust_context` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual managed network proxy startup, wiring proxy startup errors into concrete phase execution, real child spawning, backend argv builders, Windows session execution, functional denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs child spawn runner helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `spawn_debug_sandbox_child` process launch inputs.
- Python parity: added `DebugSandboxChildRunResult` and `run_debug_sandbox_child_spawn_plan`, exported from `pycodex.cli`, converting a child-spawn plan into argv/executable/cwd/env/inherited-stdio `subprocess.run` inputs while preserving Unix `arg0` behavior and capturing the return code for later exit-status handling.
- Python tests added but not run: `test_child_spawn_runner_uses_plan_launch_inputs` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: wiring this runner into the shared debug sandbox entrypoints, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs child wait exit-status bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `child.wait().await` followed by `handle_exit_status(status)` in `run_command_under_sandbox`.
- Python parity: added `DebugSandboxChildRunExitStatusPlan` and `run_debug_sandbox_child_spawn_plan_with_exit_status`, exported from `pycodex.cli`, pairing the child run result with the Rust-compatible exit-status plan selected from the return code.
- Python tests added but not run: `test_child_spawn_runner_builds_exit_status_plan_after_wait` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: raising process exit from this prepared post-wait plan, wiring the runner into shared debug sandbox entrypoints, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs child run exit-status raise helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `handle_exit_status(status)` after sandbox child wait.
- Python parity: added `raise_debug_sandbox_child_run_exit_status`, exported from `pycodex.cli`, raising `SystemExit` from a prepared `DebugSandboxChildRunExitStatusPlan` through the already-aligned exit-status helper.
- Python tests added but not run: `test_child_run_exit_status_raise_matches_rust_handle_exit_status` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: wiring the runner and raise helper into shared debug sandbox entrypoints, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs execution plan child-run bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` flow from backend spawn metadata into `spawn_debug_sandbox_child`, child wait, and exit-status handling.
- Python parity: added `run_debug_sandbox_execution_plan_with_exit_status`, exported from `pycodex.cli`, wiring `DebugSandboxExecutionPlan` through the child-spawn plan, child runner, and post-wait exit-status bridge.
- Python tests added but not run: `test_execution_plan_runs_through_child_runner_and_exit_status` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: wiring public debug sandbox entrypoint plans into this shared runner, real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs entrypoint plan shared-runner bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: public `run_command_under_seatbelt`, `run_command_under_landlock`, and `run_command_under_windows_sandbox` forwarding into `run_command_under_sandbox`.
- Python parity: added `run_debug_sandbox_entrypoint_plan_with_exit_status`, exported from `pycodex.cli`, converting `DebugSandboxEntrypointPlan` into the shared execution runner while keeping backend args and network env as explicit inputs from separate slices.
- Python tests added but not run: `test_entrypoint_plan_runs_through_shared_runner` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builders, actual Windows session execution, managed network proxy startup, concrete phase execution, denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs managed network proxy startup helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: managed network proxy startup in `run_command_under_sandbox` and its `failed to start managed network proxy: {err}` context.
- Python parity: added `DebugSandboxNetworkProxyStartResult` and `start_debug_sandbox_network_proxy_plan`, exported from `pycodex.cli`, preserving skipped startup when no network spec exists, child-process lifetime, successful proxy env handoff, and Rust-style error wrapping through an injectable starter.
- Python tests added but not run: `test_network_proxy_start_uses_planned_inputs` and `test_network_proxy_start_wraps_errors_like_rust_context` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builders, actual Windows session execution, concrete phase execution, denial log collection, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs denial logger finish helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `DenialLogger::finish` after child wait and the emitted denial summary.
- Python parity: added `DebugSandboxDenialLogResult` and `finish_debug_sandbox_denial_logger_plan`, exported from `pycodex.cli`, collecting denials through an injectable finish boundary only when the macOS logger is enabled and formatting the same output lines.
- Python tests added but not run: `test_denial_logger_finish_collects_and_formats_output` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builders, actual Windows session execution, concrete phase execution, denial logger phase wiring, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs denial logger phase wiring

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `spawn_debug_sandbox_child`, `child.wait().await`, and post-wait `DenialLogger::finish` ordering.
- Python parity: added `DebugSandboxExecutionWithDenialsResult` and `run_debug_sandbox_execution_plan_with_denial_logging`, exported from `pycodex.cli`, running the child first and then finishing denial logging through the injectable collector.
- Python tests added but not run: `test_execution_with_denial_logging_finishes_after_child_wait` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builders, actual Windows session execution, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs backend args builder boundary

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: calls to `create_seatbelt_command_args` and `create_linux_sandbox_command_args_for_permission_profile` before `spawn_debug_sandbox_child`.
- Python parity: added `DebugSandboxBackendArgsBuildResult` and `build_debug_sandbox_backend_args_from_plan`, exported from `pycodex.cli`, passing the full backend args plan into an injectable platform builder and returning the resulting backend args.
- Python tests added but not run: `test_backend_args_build_uses_injected_platform_builder` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builder implementations, actual Windows session execution, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs backend args child-run bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: platform backend args builder output passed into `spawn_debug_sandbox_child`.
- Python parity: added `run_debug_sandbox_backend_args_plan_with_exit_status`, exported from `pycodex.cli`, building backend args from a plan and feeding them through the shared execution/child-run/exit-status bridge.
- Python tests added but not run: `test_backend_args_plan_runs_builder_output_through_child_runner` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builder implementations, actual Windows session execution, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs windows session run boundary

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_windows_session` elevated/legacy spawn result and `windows sandbox failed: {err}` failure branch.
- Python parity: added `DebugSandboxWindowsSessionRunResult` and `run_debug_sandbox_windows_session_plan`, exported from `pycodex.cli`, invoking an injectable Windows session spawner and preserving mode, exit code, output drain timeout, and failure shape.
- Python tests added but not run: `test_windows_session_run_uses_spawner_and_wraps_errors` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builder implementations, Windows stdio bridge control flow, ctrl-c termination, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs windows session control-flow helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_windows_session` wait-vs-Ctrl-C branch, stdin EOF close task, session terminate request, and output drain timeout.
- Python parity: added `DebugSandboxWindowsSessionControlResult` and `run_debug_sandbox_windows_session_control_flow`, exported from `pycodex.cli`, preserving normal exit, Ctrl-C terminate request, fallback exit code `-1`, stdin EOF close, stdin close task abort, and 5 second output drain wait decisions.
- Python tests added but not run: `test_windows_session_control_flow_matches_rust_exit_and_ctrl_c_paths` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builder implementations, real Windows stdio forwarder/session IO, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs windows session IO bridge helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `windows_stdio_bridge::spawn_input_forwarder`, `spawn_output_forwarder`, `session.close_stdin`, and `session.request_terminate` as used by `run_command_under_windows_session`.
- Python parity: added `DebugSandboxWindowsSessionIoBridgeResult` and `run_debug_sandbox_windows_session_io_bridge`, exported from `pycodex.cli`, forwarding finite stdin through the Rust-compatible 8 KiB chunker, closing stdin after EOF, optionally requesting termination, and returning ordered stdout/stderr bytes through the existing output forwarder contract.
- Python tests added but not run: `test_windows_session_io_bridge_forwards_stdio_and_control_hooks` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Seatbelt/Landlock argv builder implementations, actual Windows platform session objects/background forwarder threads, concrete phase execution, and ConfigBuilder-backed loading remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs seatbelt backend argv adapter

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` call to `create_seatbelt_command_args` and the returned argv passed to `/usr/bin/sandbox-exec`.
- Python parity: added `build_debug_sandbox_seatbelt_backend_args_from_plan`, exported from `pycodex.cli`, preserving the Seatbelt `sandbox-exec` argv shape (`-p <policy>`, `-D...` definitions, `--`, then command) while keeping full policy generation delegated to the sandboxing crate boundary.
- Python tests added but not run: `test_seatbelt_backend_args_adapter_matches_rust_sandbox_exec_argv_shape` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: real Landlock argv builder implementation, actual Windows platform session objects/background forwarder threads, concrete phase execution, ConfigBuilder-backed loading, and final decision on where full Seatbelt policy generation lives remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs landlock backend argv adapter

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` call to `create_linux_sandbox_command_args_for_permission_profile` and the returned argv passed to `codex-linux-sandbox`.
- Python parity: added `build_debug_sandbox_landlock_backend_args_from_plan`, exported from `pycodex.cli`, preserving the Landlock helper argv order (`--sandbox-policy-cwd`, `--command-cwd`, `--permission-profile`, optional `--use-legacy-landlock`, optional `--allow-network-for-proxy`, `--`, then command) while keeping full permission-profile model serialization delegated to protocol/sandboxing boundaries.
- Python tests added but not run: `test_landlock_backend_args_adapter_matches_rust_helper_argv_shape` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads, concrete phase execution, ConfigBuilder-backed loading, and final decisions on full Seatbelt policy generation plus Landlock permission-profile serialization ownership remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs run-flow phase execution helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` sequential phase execution after the existing phase-order plan.
- Python parity: added `DebugSandboxRunFlowExecutionResult` and `execute_debug_sandbox_run_flow_plan`, exported from `pycodex.cli`, invoking injected phase handlers in Rust order, recording missing handlers, supporting strict missing-handler errors, and stopping at terminal phases (`handle_exit_status`, `run_windows_session_and_exit`, or `windows_unavailable_error`).
- Python tests added but not run: `test_run_flow_execution_uses_rust_phase_order_and_terminal_phase` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads, real phase handler wiring, ConfigBuilder-backed loading, and final decisions on full Seatbelt policy generation plus Landlock permission-profile serialization ownership remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs run-flow handler wiring helper

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` phase handlers wired to the planned phase sequence before execution.
- Python parity: added `DebugSandboxRunFlowHandlerWiring` and `build_debug_sandbox_run_flow_handler_wiring`, exported from `pycodex.cli`, selecting handlers that exist in the Rust phase plan, omitting handlers for phases that are not in the selected branch, and exposing missing plus terminal phase metadata for the executor.
- Python tests added but not run: `test_run_flow_handler_wiring_selects_planned_phase_handlers` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads, production phase handler hookups, ConfigBuilder-backed loading, and final decisions on full Seatbelt policy generation plus Landlock permission-profile serialization ownership remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs default run-flow handlers

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` phase handlers backed by the existing helper results for config, env, network, backend args, child wait, denial logging, and exit status.
- Python parity: added `build_debug_sandbox_default_run_flow_handlers`, exported from `pycodex.cli`, wiring existing helper result objects into the planned phase names so the run-flow executor can drive a complete non-Windows phase sequence.
- Python tests added but not run: `test_default_run_flow_handlers_wire_existing_helper_results` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads, real ConfigBuilder/platform-backed phase implementations, and final decisions on full Seatbelt policy generation plus Landlock permission-profile serialization ownership remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs config-loader execution bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `load_debug_sandbox_config_with_codex_home` calling `build_debug_sandbox_config_with_loader_overrides`, then retrying with `SandboxMode::ReadOnly` for legacy configs without explicit `sandbox_mode`.
- Python parity: added `DebugSandboxConfigLoadResult` and `run_debug_sandbox_config_load_plan`, exported from `pycodex.cli`, executing the existing config-load plan through an injected ConfigBuilder-shaped loader and preserving the read-only retry boundary.
- Python tests added but not run: `test_config_load_runner_matches_rust_read_only_retry` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads, real ConfigBuilder/platform-backed phase implementations, and final decisions on full Seatbelt policy generation plus Landlock permission-profile serialization ownership remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs config-loader phase wiring

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` `load_debug_sandbox_config` phase consuming the config-loader result before downstream cwd/env/backend phases.
- Python parity: extended `build_debug_sandbox_default_run_flow_handlers` so the `load_debug_sandbox_config` phase can return a `DebugSandboxConfigLoadResult` from `run_debug_sandbox_config_load_plan`, while keeping the previous plan-only fallback.
- Python tests added but not run: extended `test_default_run_flow_handlers_wire_existing_helper_results` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads, real ConfigBuilder/platform-backed phase implementations, and final decisions on full Seatbelt policy generation plus Landlock permission-profile serialization ownership remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs ConfigBuilder call-order adapter

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `build_debug_sandbox_config_with_loader_overrides` and its `ConfigBuilder::default().cli_overrides(...).harness_overrides(...).strict_config(...).loader_overrides(...).codex_home(...).fallback_cwd(...).build()` chain.
- Python parity: added `build_debug_sandbox_config_with_loader_overrides_from_plan`, exported from `pycodex.cli`, applying the same ConfigBuilder-shaped method order and feeding it through `run_debug_sandbox_config_load_plan` for the read-only retry path.
- Python tests added but not run: `test_config_builder_adapter_matches_rust_builder_call_order` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads, a real ConfigBuilder-compatible implementation, and final decisions on full Seatbelt policy generation plus Landlock permission-profile serialization ownership remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs platform implementation ownership decisions

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_sandbox` delegating full Seatbelt policy generation to `codex_sandboxing::seatbelt`, Landlock profile serialization/helper argv to `codex_sandboxing::landlock`, Windows session behavior to platform session helpers, and config building to `ConfigBuilder`.
- Python parity: added `DebugSandboxPlatformImplementationDecision` and `build_debug_sandbox_platform_implementation_decisions`, exported from `pycodex.cli`, documenting which heavy platform/config implementations are delegated and which adapter/phase contracts remain owned by `debug_sandbox.rs`.
- Python tests added but not run: `test_platform_implementation_decisions_document_debug_sandbox_boundaries` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads plus real ConfigBuilder/platform-backed phase implementations behind existing adapters remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs default ConfigBuilder bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `build_debug_sandbox_config_with_loader_overrides` ending in `builder.build().await`, as used by `load_debug_sandbox_config_with_codex_home` and the read-only retry path.
- Python parity: added `DebugSandboxDefaultConfigBuilder`, `DebugSandboxConfigBuilderResult`, and `load_debug_sandbox_config_with_default_builder`, exported from `pycodex.cli`, connecting the existing ConfigBuilder-shaped call-order adapter to `pycodex.config.load_config_layers_state` and returning a config object with `config_layer_stack.effective_config()` compatibility.
- Python tests added but not run: `test_default_config_builder_bridge_loads_python_config_layers` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads plus the full Rust config-builder integration matrix remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs Windows config spawn plan bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_windows_session` deriving `permission_profile`, `WindowsSandboxLevel::from_config(config)`, `config.codex_home`, and `config.permissions.windows_sandbox_private_desktop` before selecting elevated versus legacy spawn inputs.
- Python parity: added `build_debug_sandbox_windows_session_plan_from_config`, exported from `pycodex.cli`, deriving the same Windows session spawn plan fields from a Config-shaped object while reusing the existing elevated/legacy plan representation.
- Python tests added but not run: `test_windows_session_plan_from_config_matches_rust_config_inputs` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs Windows post-spawn stdio bridge

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: `run_command_under_windows_session` after a successful spawn: wrap the session, start stdin/stdout/stderr forwarders, close stdin on EOF, select on session exit versus Ctrl-C, abort the stdin close task, wait for stdout/stderr drain with a 5 second timeout, and exit with the session code; also the spawn error branch that prints `windows sandbox failed: {err}` and exits 1.
- Python parity: added `DebugSandboxWindowsSpawnBridgeResult` and `run_debug_sandbox_windows_session_with_stdio_bridge`, exported from `pycodex.cli`, combining an injectable spawner with the existing finite stdio/control bridge and Rust-style spawn error wrapping.
- Python tests added but not run: `test_windows_session_spawn_stdio_bridge_combines_spawn_and_forwarders` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: actual Windows platform session objects/background forwarder threads remain partial.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs complete-candidate native boundary closeout

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors advanced: the whole module-scoped behavior contract for config loading, backend argv preparation, child execution, entrypoint forwarding, Seatbelt/Landlock ownership, and Windows session spawn/control/stdio boundaries.
- Python parity: added `DebugSandboxDeferredNativeBoundary` and `build_debug_sandbox_deferred_native_boundaries`, exported from `pycodex.cli`, documenting native Windows session objects, long-lived Windows background forwarder threads, and sibling-crate policy generation as explicit adapter/deferred boundaries; `pycodex/cli/DEBUG_SANDBOX_RS_STATUS.md` now marks the module `complete_candidate`.
- Python tests added but not run: `test_deferred_native_boundaries_record_remaining_platform_work` in `tests/test_cli_debug_sandbox.py`.
- Remaining gaps: no unclassified module-local behavior gap remains; promotion to `complete` waits on actual pytest execution after `codex-cli` functional code is complete.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/login.rs complete-candidate status audit

- Rust crate/module: `codex-cli` / `src/login.rs`.
- Rust anchors advanced: `init_login_file_logging`, `print_login_server_start`, `run_login_with_chatgpt`, `run_login_with_api_key`, `run_login_with_access_token`, `read_api_key_from_stdin`, `read_access_token_from_stdin`, `run_login_with_device_code`, `run_login_with_device_code_fallback_to_browser`, `run_login_status`, `run_logout`, `load_config_or_exit`, and `safe_format_key`.
- Python parity: recorded `pycodex/cli/LOGIN_RS_STATUS.md` as `complete_candidate`; existing `pycodex/cli/login.py` helpers and `tests/test_cli_login.py` cover the module-owned user-visible messages, stdin secret handling, config error prefixes, direct-login log setup decisions, API-key masking, status/logout output, and flow result prefixes.
- Python tests added: none in this turn; this is a module status closeout over existing Rust-derived coverage.
- Remaining gaps: no unclassified `codex-cli/src/login.rs` module-local behavior gap remains; OAuth server/device-code/token storage internals are sibling `codex-login` crate ownership and are not claimed by this module.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/lib.rs complete-candidate status audit

- Rust crate/module: `codex-cli` / `src/lib.rs`.
- Rust anchors advanced: child module declarations for `debug_sandbox`, `exit_status`, and `login`; public re-exports for sandbox and login entrypoints; `SeatbeltCommand`, `LandlockCommand`, `WindowsCommand`; and `parse_allow_unix_socket_path`.
- Python parity: added `pycodex/cli/LIB_RS_STATUS.md` with status `complete_candidate`; existing `pycodex.cli` exports, `pycodex/cli/parser.py` sandbox parsing, `pycodex/cli/debug_sandbox.py` planning helpers, `pycodex/cli/login.py`, and `pycodex/cli/exit_status.py` cover the module-owned library-boundary export and command option surface.
- Python tests added: none in this turn; this is a module status closeout over existing parser/debug/login/exit-status coverage.
- Remaining gaps: no unclassified `codex-cli/src/lib.rs` module-local behavior gap remains; `main.rs`, extension command modules, remote-control modules, and desktop-app modules remain separate Rust module boundaries.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/desktop_app/mod.rs complete-candidate status audit

- Rust crate/module: `codex-cli` / `src/desktop_app/mod.rs`.
- Rust anchors advanced: target-gated `run_app_open_or_install` dispatch to `mac::run_mac_app_open_or_install` on macOS and `windows::run_windows_app_open_or_install` on Windows.
- Python parity: added `pycodex/cli/DESKTOP_APP_MOD_RS_STATUS.md` with status `complete_candidate`; existing `pycodex/cli/parser.py::_run_app_command` mirrors the current-OS dispatch by selecting `_run_app_command_macos` on `darwin`, `_run_app_command_windows` on Windows, and returning success on unsupported hosts where Rust does not compile this command module.
- Python tests added: none in this turn; this is a module status closeout over existing parser/app-command coverage.
- Remaining gaps: no unclassified `desktop_app/mod.rs` module-local behavior gap remains; `desktop_app/mac.rs` and `desktop_app/windows.rs` remain separate Rust module boundaries.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/desktop_app/windows.rs Windows workspace display and guidance

- Rust crate/module: `codex-cli` / `src/desktop_app/windows.rs`.
- Rust anchors advanced: `display_workspace_path`, `run_windows_app_open_or_install`, and `open_shell_target`.
- Python parity: added `display_windows_workspace_path`, exported from `pycodex.cli`, and updated `_run_app_command_windows` to print Rust's installed-app and post-install workspace guidance, treat Explorer as a best-effort shell handoff, and use the Microsoft Store fallback only for the default installer path.
- Python tests added but not run: `tests/test_cli_app_cmd.py::CliAppCommandTests::test_display_windows_workspace_path_matches_rust_extended_prefix_handling`.
- Remaining gaps: no unclassified `desktop_app/windows.rs` module-local behavior gap remains.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/desktop_app/mac.rs hdiutil mount parser

- Rust crate/module: `codex-cli` / `src/desktop_app/mac.rs`.
- Rust anchors advanced: `parse_hdiutil_attach_mount_point` and its two local Rust tests.
- Python parity: added `parse_hdiutil_attach_mount_point`, exported from `pycodex.cli`, and recorded `pycodex/cli/DESKTOP_APP_MAC_RS_STATUS.md` with status `partial`.
- Python tests added but not run: `tests/test_cli_app_cmd.py::CliAppCommandTests::test_parse_hdiutil_attach_mount_point_matches_rust`.
- Remaining gaps: Python's macOS app runner still opens the installer URL instead of Rust's native `curl`/`hdiutil`/`ditto` download, mount, install, and detach chain.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/desktop_app/mac.rs app path and installer command planning

- Rust crate/module: `codex-cli` / `src/desktop_app/mac.rs`.
- Rust anchors advanced: `candidate_codex_app_paths`, `candidate_applications_dirs`, `is_apple_silicon_mac` default URL choice, `open_codex_app`, `download_dmg`, `mount_dmg`, `detach_dmg`, `copy_app_bundle`, and temp installer naming.
- Python parity: added pure planning helpers for app paths, install destinations, default DMG URL selection, `open -a`, `curl`, `hdiutil attach`, `hdiutil detach`, `ditto`, and installer temp-root details; updated `pycodex/cli/DESKTOP_APP_MAC_RS_STATUS.md`.
- Python tests added but not run: `tests/test_cli_app_cmd.py::CliAppCommandTests::test_mac_app_command_shapes_match_rust`.
- Remaining gaps: Python still does not execute the planned native macOS DMG download/mount/install/detach chain.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/desktop_app/mac.rs native open/install execution

- Rust crate/module: `codex-cli` / `src/desktop_app/mac.rs`.
- Rust anchors advanced: `run_mac_app_open_or_install`, `download_and_install_codex_to_user_applications`, `find_codex_app_in_mount`, and `install_codex_app_bundle`.
- Python parity: updated `_run_app_command_macos` to execute the Rust-shaped native flow: open an existing app, otherwise select the default DMG with arm64/Rosetta/`hw.optional.arm64` probes, download the DMG, mount it, parse the mount point, locate the mounted `.app`, attempt `ditto` install into Applications directories, detach with a warning on detach failure, and launch from the installed app. Added `find_codex_app_in_mount` for direct `Codex.app` priority before generic `.app` bundles.
- Python tests added but not run: `tests/test_cli_app_cmd.py::CliAppCommandTests::test_find_codex_app_in_mount_matches_rust_priority`.
- Remaining gaps: no known module-owned functional gaps remain; promotion to `complete` waits on actual pytest execution after `codex-cli` functional code is complete.
- Validation: `python -m py_compile pycodex\cli\app_cmd.py pycodex\cli\parser.py pycodex\cli\__init__.py tests\test_cli_app_cmd.py` passed on 2026-06-17. Focused pytest remains deferred by current crate automation rule.

### src/marketplace_cmd.rs compatibility shim status

- Rust crate/module: `codex-cli` / `src/marketplace_cmd.rs`.
- Rust anchors advanced: `MarketplaceCli`, `MarketplaceSubcommand`, `AddMarketplaceArgs`, `UpgradeMarketplaceArgs`, `RemoveMarketplaceArgs`, and local parser tests.
- Python parity: recorded `pycodex/cli/MARKETPLACE_CMD_RS_STATUS.md` as `complete_candidate`; existing `pycodex/cli/parser.py` covers the `plugin marketplace` subcommand parser surface and local config shim behavior, while deep Git marketplace snapshot add/remove/upgrade remains `codex-core-plugins` extension behavior outside the active core priority.
- Python tests added but not run: `tests/test_cli_parser.py::CliParserTests::test_parse_plugin_marketplace_remove_matches_rust`.
- Remaining gaps: no known module-owned parser-surface gap remains; extension side effects remain documented compatibility-shim debt.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/plugin_cmd.rs selector/surface compatibility shim

- Rust crate/module: `codex-cli` / `src/plugin_cmd.rs`.
- Rust anchors advanced: `PluginCli`, `PluginSubcommand`, `AddPluginArgs`, `ListPluginsArgs`, `RemovePluginArgs`, and `parse_plugin_selection`.
- Python parity: updated `_parse_plugin_selector` so bare plugin names now require `--marketplace` unless passed as `<plugin>@<marketplace>`, and conflicting explicit marketplace names are rejected like Rust. Added `pycodex/cli/PLUGIN_CMD_RS_STATUS.md` with status `complete_candidate`; deep plugin install/cache and marketplace snapshot behavior remains `codex-core-plugins` extension debt.
- Python tests added but not run: `tests/test_cli_parser.py::CliParserTests::test_plugin_selector_requires_marketplace_like_rust` and `tests/test_cli_parser.py::CliParserTests::test_plugin_selector_rejects_marketplace_mismatch_like_rust`.
- Remaining gaps: no known module-owned selector/parser gap remains; extension side effects remain documented compatibility-shim debt.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/mcp_cmd.rs env/name helper compatibility shim

- Rust crate/module: `codex-cli` / `src/mcp_cmd.rs`.
- Rust anchors advanced: `McpCli`, `McpSubcommand`, `AddMcpTransportArgs`, `parse_env_pair`, and `validate_server_name`.
- Python parity: added `_parse_mcp_env_pair` and `_validate_mcp_server_name`, then routed `mcp add` and `mcp remove` through those Rust-shaped helper contracts. Added `pycodex/cli/MCP_CMD_RS_STATUS.md` with status `complete_candidate`; MCP OAuth/runtime behavior remains extension/runtime debt outside this CLI module.
- Python tests added but not run: `tests/test_cli_parser.py::CliParserTests::test_mcp_env_pair_matches_rust` and `tests/test_cli_parser.py::CliParserTests::test_mcp_server_name_validation_matches_rust`.
- Remaining gaps: no known module-owned parser/helper gap remains; MCP OAuth/effective-runtime behavior remains documented compatibility-shim debt.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/remote_control_cmd.rs human output compatibility shim

- Rust crate/module: `codex-cli` / `src/remote_control_cmd.rs`.
- Rust anchors advanced: `RemoteControlCommand`, `RemoteControlSubcommand`, `remote_control_start_human_message`, `remote_control_start_human_lines`, and JSON start/stop output shape.
- Python parity: added `_remote_control_start_human_message` and routed `_remote_control_human_lines` through it so connected, connecting, errored, disabled, foreground, and daemon human messages match Rust. Added `pycodex/cli/REMOTE_CONTROL_CMD_RS_STATUS.md` with status `complete_candidate`; foreground app-server task/socket lifecycle remains app-server crate debt outside this CLI module.
- Python tests added but not run: `tests/test_cli_parser.py::CliParserTests::test_remote_control_human_start_messages_match_rust` and `tests/test_cli_parser.py::CliParserTests::test_remote_control_human_lines_match_rust_foreground_hint`.
- Remaining gaps: no known module-owned CLI output/parser gap remains; daemon lifecycle and socket readiness internals remain documented compatibility-shim debt.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/main.rs top-level parser and dispatch shell status

- Rust crate/module: `codex-cli` / `src/main.rs`.
- Rust anchors advanced: `MultitoolCli`, `Subcommand`, `CompletionCommand`, `FeatureToggles`, `FeaturesCli`, `format_exit_messages`, `handle_app_exit`, `reject_root_strict_config_for_subcommand`, `reject_remote_mode_for_subcommand`, and top-level command dispatch guards.
- Python parity: added `pycodex/cli/MAIN_RS_STATUS.md` with status `complete_candidate`; existing `pycodex/cli/spec.py`, `pycodex/cli/parser.py`, `pycodex/cli/features.py`, and `pycodex/cli/app_exit.py` cover the module-owned parser/dispatch/helper shell.
- Python tests added: none in this turn; this is a module status closeout over existing parser, feature, completion, strict-config, remote-mode, app-exit, and command-surface coverage.
- Remaining gaps: no known `src/main.rs` module-owned top-level parser/helper gap remains; deep subcommand runtimes remain separate crate/module boundaries.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox/pid_tracker.rs macOS descendant tracking shim

- Rust crate/module: `codex-cli` / `src/debug_sandbox/pid_tracker.rs`.
- Rust anchors advanced: `PidTracker::new`, `PidTracker::stop`, `pid_is_alive`, `list_child_pids`, and recursive descendant collection in `track_descendants`.
- Python parity: added `DebugSandboxPidTracker`, `debug_sandbox_pid_is_alive`, `debug_sandbox_list_child_pids`, and `collect_debug_sandbox_descendant_pids`; exported them from `pycodex.cli` and recorded `pycodex/cli/PID_TRACKER_RS_STATUS.md` with status `complete_candidate`.
- Python tests added but not run: `tests/test_cli_debug_sandbox.py::CliDebugSandboxTests::test_pid_tracker_new_rejects_non_positive_root_like_rust`, `test_pid_tracker_collects_recursive_descendants_like_rust`, and `test_pid_tracker_child_listing_boundary_is_platform_guarded`.
- Remaining gaps: Python intentionally uses a dependency-free macOS `pgrep -P` snapshot boundary instead of Rust's native long-running kqueue watcher; native cleanup fidelity remains a documented implementation difference.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox/seatbelt.rs denial parsing/filtering shim

- Rust crate/module: `codex-cli` / `src/debug_sandbox/seatbelt.rs`.
- Rust anchors advanced: `SandboxDenial`, `DenialLogger::finish`, `start_log_stream`, and `parse_message`.
- Python parity: added `DebugSandboxSeatbeltDenial`, `parse_debug_sandbox_seatbelt_denial_message`, and `collect_debug_sandbox_seatbelt_denials`; exported them from `pycodex.cli` and recorded `pycodex/cli/SEATBELT_RS_STATUS.md` with status `complete_candidate`.
- Python tests added but not run: `tests/test_cli_debug_sandbox.py::CliDebugSandboxTests::test_seatbelt_parse_message_matches_rust_regex` and `test_seatbelt_collect_denials_filters_pid_and_deduplicates_like_rust`.
- Remaining gaps: Python keeps native `log stream` process management behind the debug-sandbox injectable boundary; long-running PID tracking fidelity is tracked by `PID_TRACKER_RS_STATUS.md`.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/debug_sandbox.rs parent status reconciliation

- Rust crate/module: `codex-cli` / `src/debug_sandbox.rs`.
- Rust anchors reconciled: parent `run_command_under_sandbox` orchestration, public Seatbelt/Landlock/Windows entrypoint forwarding, child spawn/exit-status bridge, network proxy planning, denial logger lifecycle integration, backend argv adapters, Windows session adapters, and config-loader bridge.
- Python parity: refreshed `pycodex/cli/DEBUG_SANDBOX_RS_STATUS.md` and README wording to reflect that the parent module is `complete_candidate`; nested `pid_tracker.rs` and `seatbelt.rs` now have separate status files.
- Python tests added: none in this turn; this is a module status reconciliation over existing helper coverage and the newly separated nested-module ledgers.
- Remaining gaps: no known parent `src/debug_sandbox.rs` module-owned behavior gap remains outside deferred crate-level validation; native kqueue/log-stream fidelity is tracked by nested module status files.
- Validation: not run; current crate automation defers actual pytest execution until `codex-cli` functional code is complete.

### src/doctor.rs Responses WebSocket probe dispatch

- Rust crate/module: `codex-cli` / `src/doctor.rs`.
- Rust anchors advanced: `websocket_reachability_check` constructs a
  `ResponsesWebsocketClient`, inserts
  `OpenAI-Beta: responses_websockets=2026-02-06`, and calls
  `ResponsesWebsocketClient::probe_handshake(...)` from
  `codex-api/src/endpoint/responses_websocket.rs`.
- Python parity: `pycodex/cli/doctor_updates.py::doctor_websocket_check`
  now dispatches real probes through
  `pycodex.codex_api.endpoint.responses_websocket.ResponsesWebsocketClient`
  instead of bypassing the `codex-api` client boundary with the generic
  websocket helper. The existing doctor output shape is preserved.
- Python tests: `tests/test_cli_doctor_updates.py` websocket doctor tests now
  intercept `doctor_updates.responses_connect_websocket` at the codex-api
  connector boundary and verify beta headers, API-key auth, timeout forwarding,
  DNS detail preservation, endpoint query preservation through
  `Provider::websocket_url_for_path("responses")`, `websocket_error_detail`
  `ApiError` formatting, immediate close reporting, and timeout warnings.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_websocket_check or websocket_probe_warning or dns_address_family_details" -q --tb=short`
  passed on 2026-06-21 with `9 passed, 433 deselected`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -k "websocket_error_detail or doctor_websocket_check or websocket_probe_warning or dns_address_family_details" -q --tb=short`
  passed on 2026-06-21 with `12 passed, 433 deselected`.
- Validation: `python -m pytest tests/test_cli_doctor_updates.py -q --tb=short`
  passed on 2026-06-21 with `445 passed, 32 subtests passed`.
- Validation: `python -m py_compile pycodex/cli/doctor_updates.py tests/test_cli_doctor_updates.py`
  passed on 2026-06-21.
