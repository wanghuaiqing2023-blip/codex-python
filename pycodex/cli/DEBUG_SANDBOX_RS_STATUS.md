# codex-cli src/debug_sandbox.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/debug_sandbox.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/debug_sandbox.rs` |
| Python module | `pycodex/cli/debug_sandbox.py` |
| Python parser integration | `pycodex/cli/parser.py::_run_sandbox` |
| Python exports | `pycodex/cli/__init__.py` debug-sandbox helpers |
| Python tests | `tests/test_cli_debug_sandbox.py` |
| Status | `complete` |

`src/debug_sandbox.rs` owns the debug sandbox command execution path and its
supporting configuration/environment behavior for Seatbelt, Landlock, and
Windows sandbox backends.

The module is now `complete`: Rust-owned behavior contracts are mirrored through
Python helpers or explicit injectable/native boundaries, and the focused Python
parity test module passes after crate functional code reached complete-candidate
coverage.

The two nested Rust modules are tracked separately:

- `codex/codex-rs/cli/src/debug_sandbox/pid_tracker.rs`:
  `pycodex/cli/PID_TRACKER_RS_STATUS.md`
- `codex/codex-rs/cli/src/debug_sandbox/seatbelt.rs`:
  `pycodex/cli/SEATBELT_RS_STATUS.md`

## Completed Behavior Areas

- `ManagedRequirementsMode::for_profile_invocation` is mirrored by
  `ManagedRequirementsMode.for_profile_invocation`.
- Legacy `sandbox_mode` override detection is mirrored by
  `cli_overrides_use_legacy_sandbox_mode`.
- Permission-profile override appending is mirrored by
  `with_permissions_profile_override`.
- Effective-config permission profile probing is mirrored by
  `config_uses_permission_profiles`.
- Legacy config read-only default selection is mirrored by
  `should_default_legacy_config_to_read_only`.
- Loader override adjustment for managed requirements is mirrored by
  `loader_overrides_with_managed_requirements_mode`.
- Config-loader decision planning is mirrored by
  `DebugSandboxConfigLoadPlan` and `build_debug_sandbox_config_load_plan`,
  including permission-profile override insertion, legacy `sandbox_mode`
  detection, codex-home fallback cwd, strict-config propagation, managed
  requirements override adjustment, and read-only retry selection.
- Config-loader execution is mirrored at the injectable boundary by
  `DebugSandboxConfigLoadResult` and `run_debug_sandbox_config_load_plan`,
  calling a supplied ConfigBuilder-shaped loader and applying the Rust
  read-only retry when the plan identifies a legacy config without an explicit
  `sandbox_mode` override.
- ConfigBuilder call ordering is mirrored by
  `build_debug_sandbox_config_with_loader_overrides_from_plan`, applying
  `cli_overrides`, `harness_overrides`, `strict_config`, `loader_overrides`,
  optional `codex_home`/`fallback_cwd`, and `build` in the Rust order.
- The default Python ConfigBuilder-compatible bridge is connected by
  `DebugSandboxDefaultConfigBuilder`,
  `DebugSandboxConfigBuilderResult`, and
  `load_debug_sandbox_config_with_default_builder`, feeding the planned
  overrides into `pycodex.config.load_config_layers_state` and exposing the
  resulting layer stack/effective config through the same config-loader result
  boundary.
- Platform implementation ownership is recorded by
  `DebugSandboxPlatformImplementationDecision` and
  `build_debug_sandbox_platform_implementation_decisions`, keeping full
  Seatbelt policy generation and Landlock permission-profile serialization
  delegated while `debug_sandbox.rs` owns adapter wiring and phase contracts.
- Shared `run_command_under_sandbox` phase ordering is mirrored by
  `DebugSandboxRunFlowPlan` and `build_debug_sandbox_run_flow_plan`, including
  config loading with `strict_config=false`, `config.cwd` reuse for both cwd
  and permission-profile cwd, env creation before the Windows special case,
  Windows session exit/error before denial logger and network setup, denial
  logger creation before network proxy startup, child wait before denial
  logger finish, and final exit-status handling for non-Windows backends.
- Shared run-flow phase execution is mirrored by
  `DebugSandboxRunFlowExecutionResult` and
  `execute_debug_sandbox_run_flow_plan`, invoking injected phase handlers in
  Rust order, recording missing handlers, and stopping at terminal phases such
  as `handle_exit_status`, `run_windows_session_and_exit`, or
  `windows_unavailable_error`.
- Shared run-flow handler wiring is mirrored by
  `DebugSandboxRunFlowHandlerWiring` and
  `build_debug_sandbox_run_flow_handler_wiring`, selecting concrete handlers
  that match the planned Rust phase sequence and exposing missing/terminal
  phase metadata before execution.
- Default run-flow handlers are mirrored by
  `build_debug_sandbox_default_run_flow_handlers`, wiring existing config,
  execution, network, backend-args, child, denial, exit-status, and Windows
  session helper results into the planned Rust phase names, including the
  injectable config-loader execution result for `load_debug_sandbox_config`.
- Child exit-status handling is mirrored by `DebugSandboxExitStatusPlan` and
  `build_debug_sandbox_exit_status_plan`, including normal exit-code
  propagation, Unix `128 + signal` handling, and the generic fallback code 1.
- Process termination from the planned child exit status is mirrored by
  `raise_debug_sandbox_exit_status`, which raises `SystemExit` with the same
  code Rust passes to `std::process::exit`.
- Public entrypoint forwarding for `run_command_under_seatbelt`,
  `run_command_under_landlock`, and `run_command_under_windows_sandbox` is
  mirrored by `DebugSandboxEntrypointPlan` and
  `build_debug_sandbox_entrypoint_plan`, including command/cwd/profile/config
  override forwarding, managed-requirements mode selection, loader override and
  `codex-linux-sandbox` propagation, and Seatbelt-only `log_denials` plus
  extra Unix socket forwarding.
- Platform availability guard messages for Seatbelt and Windows sandbox are
  mirrored by `sandbox_unavailable_error`.
- Child process environment changes for disabled network sandboxing and
  Seatbelt are mirrored by `debug_sandbox_child_env` and
  `debug_sandbox_seatbelt_env`.
- Unix child `arg0` selection is mirrored by `debug_sandbox_child_arg0`.
- Debug sandbox launch path string rendering now preserves Rust/Unix argv shape
  through `_debug_sandbox_path_arg`, avoiding host Windows separator rewriting
  for backend programs, Seatbelt `-D...` definitions, Landlock cwd arguments,
  subprocess argv, child `arg0`, executable, and current-directory launch
  strings.
- Child spawn setup is mirrored by `DebugSandboxChildSpawnPlan` and
  `build_debug_sandbox_child_spawn_plan`, including program/args/cwd, Unix
  `arg0` handling, `apply_env`-style env updates before the disabled-network
  marker override, `env_clear`, inherited stdio, and `kill_on_drop=true`.
- Windows sandbox session spawn input derivation from `Config` is mirrored by
  `build_debug_sandbox_windows_session_plan_from_config`, including effective
  permission profile lookup, `WindowsSandboxLevel::Elevated` selection,
  `codex_home`, command/cwd/profile cwd/env forwarding, `tty=false`,
  `stdin_open=true`, and `windows_sandbox_private_desktop`.
- Windows post-spawn stdio/control bridging is mirrored by
  `DebugSandboxWindowsSpawnBridgeResult` and
  `run_debug_sandbox_windows_session_with_stdio_bridge`, combining an
  injectable session spawner with stdin forwarding, stdout/stderr chunk
  collection, Ctrl-C termination hooks, stdin close, output drain timeout, and
  Rust-style `windows sandbox failed: {err}` error wrapping.
- Native/platform-heavy implementation gaps are explicitly recorded by
  `DebugSandboxDeferredNativeBoundary` and
  `build_debug_sandbox_deferred_native_boundaries`, keeping Windows session
  objects, long-lived Windows forwarder threads, and sibling-crate policy
  generation behind injectable/debug-sandbox adapter boundaries.
- Functional child spawn invocation from the child-spawn plan is mirrored by
  `run_debug_sandbox_child_spawn_plan`, including argv construction, current
  directory, explicit env, Unix `arg0` via `executable`, inherited stdio,
  non-checking wait semantics, and return-code capture for later exit-status
  handling.
- The Rust post-wait bridge from `child.wait().await` into
  `handle_exit_status(status)` is mirrored by
  `run_debug_sandbox_child_spawn_plan_with_exit_status`, pairing the child run
  result with the `DebugSandboxExitStatusPlan` selected from its return code.
- Raising process exit from that prepared post-wait child run plan is mirrored
  by `raise_debug_sandbox_child_run_exit_status`, which delegates to the same
  Rust-compatible `SystemExit` code selection as `raise_debug_sandbox_exit_status`.
- Python sandbox command execution now uses `DebugSandboxExecutionPlan` and
  `build_debug_sandbox_execution_plan` to centralize command, cwd, platform
  guard, managed-requirements mode, permission-profile, and child environment
  preparation before the compatibility subprocess launch.
- The execution plan records `permission_profile_cwd` as the same path as
  `cwd`, matching Rust's current `run_command_under_sandbox` behavior, and
  applies network-proxy environment values before the disabled-network marker
  override in the same order as `spawn_debug_sandbox_child`.
- Managed network proxy decision planning is mirrored by
  `DebugSandboxNetworkPlan` and `build_debug_sandbox_network_plan`, including
  "start proxy only when a network spec is present", permission-profile
  forwarding, managed-network-requirements forwarding, default audit metadata,
  proxy environment capture, and child-process lifetime documentation.
- Managed network proxy startup error context is mirrored by
  `format_debug_sandbox_network_proxy_error`, matching Rust's
  `failed to start managed network proxy: {err}` message.
- Managed network proxy startup is mirrored at the injectable boundary by
  `DebugSandboxNetworkProxyStartResult` and
  `start_debug_sandbox_network_proxy_plan`, preserving the child-process
  lifetime, successful proxy env handoff, skipped startup when no network spec
  exists, and Rust-style startup error wrapping.
- Managed network proxy environment application is mirrored by
  `DebugSandboxNetworkEnvApplicationPlan` and
  `build_debug_sandbox_network_env_application_plan`, including Seatbelt's
  sandbox marker insertion, applying proxy env only when a proxy exists, and
  applying the disabled-network marker after proxy env mutation.
- macOS Seatbelt denial logger lifecycle is mirrored by
  `DebugSandboxDenialLoggerPlan` and
  `build_debug_sandbox_denial_logger_plan`, including creation only when
  denial logging is requested on macOS, child-spawn attachment, post-wait
  finish, and the Rust user-facing denial summary strings.
- Nested `pid_tracker.rs` child-process descendant tracking is covered by
  `pycodex/cli/PID_TRACKER_RS_STATUS.md`; this parent module owns only the
  integration point that attaches the tracker after child spawn.
- Nested `seatbelt.rs` denial parsing/filtering is covered by
  `pycodex/cli/SEATBELT_RS_STATUS.md`; this parent module owns only the
  lifecycle ordering around denial logger creation/attachment/finish.
- Seatbelt denial summary formatting is mirrored by
  `format_debug_sandbox_denial_summary`, including the leading blank line,
  `=== Sandbox denials ===` header, `None found.` empty output, and
  `({name}) {capability}` denial lines.
- Functional Seatbelt denial log collection/output is mirrored at the
  injectable finish boundary by `DebugSandboxDenialLogResult` and
  `finish_debug_sandbox_denial_logger_plan`, collecting denials only when the
  macOS logger is enabled and formatting the same post-wait output lines.
- Denial logger phase wiring is mirrored by
  `DebugSandboxExecutionWithDenialsResult` and
  `run_debug_sandbox_execution_plan_with_denial_logging`, which runs the child
  first and finishes the denial logger after the child wait, matching Rust's
  post-wait order.
- The execution plan records backend spawn inputs: Seatbelt uses
  `/usr/bin/sandbox-exec` with no child `arg0`, Landlock uses the configured
  `codex-linux-sandbox` path with child `arg0` set to `codex-linux-sandbox`,
  and Windows remains a special session path without subprocess backend
  program metadata.
- Backend argument-builder inputs are mirrored by
  `DebugSandboxBackendArgsPlan` and `build_debug_sandbox_backend_args_plan`,
  including command, cwd, permission-profile cwd, permission profile,
  Landlock legacy mode, Landlock managed-network proxy allowance, Seatbelt
  extra Unix sockets, and Seatbelt's non-enforced managed-network flag.
- Backend argument-builder invocation is mirrored at the injectable boundary by
  `DebugSandboxBackendArgsBuildResult` and
  `build_debug_sandbox_backend_args_from_plan`, passing the complete plan into
  a platform builder and returning actual backend args while preserving a
  compatibility fallback when no builder is supplied.
- Seatbelt backend argv shape is mirrored by
  `build_debug_sandbox_seatbelt_backend_args_from_plan`, preserving the
  `sandbox-exec` argument structure returned to `debug_sandbox.rs`
  (`-p <policy>`, `-D...` definitions, `--`, then command). Full Seatbelt
  policy generation remains owned by the sandboxing crate boundary.
- Landlock backend argv shape is mirrored by
  `build_debug_sandbox_landlock_backend_args_from_plan`, preserving the
  `codex-linux-sandbox` helper argument order returned to `debug_sandbox.rs`
  (`--sandbox-policy-cwd`, `--command-cwd`, `--permission-profile`, optional
  legacy/proxy flags, `--`, then command). Full permission-profile model
  serialization remains delegated to the protocol/sandboxing boundary.
- Backend args builder output is wired into the child-runner path by
  `run_debug_sandbox_backend_args_plan_with_exit_status`, which builds backend
  args from the plan and feeds them through the shared execution/child
  wait/exit-status bridge.
- Windows session spawn inputs are mirrored by
  `DebugSandboxWindowsSessionPlan` and
  `build_debug_sandbox_windows_session_plan`, including elevated vs legacy
  branch selection, effective permission-profile inputs, codex home,
  command/cwd/env, read/write override defaults, empty deny-list defaults,
  `tty=false`, `stdin_open=true`, private-desktop forwarding, and the 5 second
  output drain timeout.
- Windows session spawning is mirrored at the injectable boundary by
  `DebugSandboxWindowsSessionRunResult` and
  `run_debug_sandbox_windows_session_plan`, preserving elevated/legacy mode,
  exit-code handoff, output drain timeout, and Rust-style
  `windows sandbox failed: {err}` failure shape.
- `debug_sandbox_subprocess_argv` now turns the execution plan into the launch
  argv used by the Python compatibility runner, preferring backend
  program/args when present and falling back to the original command for
  Windows or direct compatibility execution.
- `debug_sandbox_child_spawn_plan_from_execution_plan` bridges
  `DebugSandboxExecutionPlan` into the Rust-style child spawn plan, preserving
  backend program/args, direct command fallback, cwd, env, Unix `arg0`, and
  disabled-network marker state.
- `run_debug_sandbox_execution_plan_with_exit_status` wires that execution
  plan through the Rust-style child spawn runner and post-wait exit-status
  bridge, preserving backend spawn metadata while keeping backend argv builder
  construction as a separate remaining concern.
- `run_debug_sandbox_entrypoint_plan_with_exit_status` wires the public
  entrypoint forwarding plan into the shared execution runner while accepting
  explicit backend args/network inputs from the still-separate backend-builder
  and proxy setup slices.
- Windows session post-spawn control flow is mirrored by
  `DebugSandboxWindowsSessionControlResult` and
  `run_debug_sandbox_windows_session_control_flow`, preserving normal exit vs
  Ctrl-C termination, fallback exit code `-1`, stdin EOF close, stdin-close
  task abort, and 5 second stdout/stderr drain wait decisions.
- Windows session finite stdio bridge behavior is mirrored by
  `DebugSandboxWindowsSessionIoBridgeResult` and
  `run_debug_sandbox_windows_session_io_bridge`, forwarding stdin through the
  Rust-compatible 8 KiB chunker, closing stdin after EOF, optionally requesting
  termination, and returning ordered stdout/stderr bytes through the existing
  output forwarder contract.
- Windows stdin/output forwarding contracts are mirrored by
  `windows_stdin_forward_chunks` and `windows_output_forward_bytes`.

## Rust Test Inventory

The Rust module currently contains 7 named module integration tests plus 2
Windows-only stdio bridge tests:

- `debug_sandbox_honors_active_permission_profiles`
- `debug_sandbox_honors_config_profile_loader_overrides`
- `debug_sandbox_honors_explicit_legacy_sandbox_mode`
- `debug_sandbox_defaults_legacy_configs_to_read_only`
- `debug_sandbox_honors_explicit_builtin_permission_profile`
- `debug_sandbox_honors_explicit_named_permission_profile`
- `debug_sandbox_uses_explicit_profile_cwd`
- `input_forwarder_sends_chunks_and_reports_eof`
- `output_forwarder_writes_all_chunks`

Current Python parity tests cover the helper-level contracts for config
selection, loader override adaptation, ConfigBuilder-shaped call ordering, the
default Python config-loader bridge, environment preparation, platform guard
messages, child `arg0`, backend argv adapters, shared run-flow planning,
entrypoint/child-run bridges, and Windows stdio/session hook behavior.

## Deferred Native Boundaries

- Actual Windows platform session objects remain owned by
  `codex-windows-sandbox`; Python receives an injectable spawner and mirrors the
  post-spawn control/stdio behavior.
- Long-lived Windows background forwarder threads remain a Rust/native runtime
  concern; Python mirrors finite chunking, hook calls, close/terminate
  decisions, and output-drain semantics.
- Full Seatbelt policy generation and Landlock permission-profile
  serialization remain owned by sibling sandboxing/protocol crates; this module
  mirrors the argv shapes consumed by `debug_sandbox.rs`.
- Native macOS `log stream` and kqueue PID tracking fidelity are tracked in the
  nested `seatbelt.rs` and `pid_tracker.rs` status files; this parent module
  now has no known module-owned behavior gap outside validation.
- The Rust config-builder integration matrix is represented by the default
  Python config-loader bridge and focused parity entries; broader validation is
  deferred until crate-level test execution is allowed.

## Completion Criteria

Completed on 2026-06-17:

1. Functional code coverage for this module reached `complete_candidate`.
2. Focused validation passed: `python -m pytest tests/test_cli_debug_sandbox.py -q`
   reported `61 passed`.
3. A broader CLI test run still has failures in sibling
   `codex-cli/src/doctor/output.rs`; those are outside this module boundary.
