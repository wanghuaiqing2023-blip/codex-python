# codex-cli src/doctor.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/cli/src/doctor.rs`.
It intentionally excludes sibling modules under `src/doctor/`, such as
`output.rs`, `git.rs`, `title.rs`, `runtime.rs`, and `thread_inventory.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor.rs` now has all local Rust test names reconciled to Python parity
entries or Rust-derived comments. It remains a `complete_candidate` until the
crate-level functional-code sweep is done and actual pytest validation is run
per the current automation rule.

## Covered Behavior Areas

The existing alignment ledger in `pycodex/cli/TEST_ALIGNMENT.md` records
covered slices for these `src/doctor.rs` anchors:

- report primitives: `CheckStatus`, `DoctorCheck`, `DoctorIssue`, JSON
  redaction, `overall_status`, `generated_at`, and progress wrappers.
- install/update context: npm root comparison, install context description,
  standalone release cache details, package path display, and config override
  bridging.
- config/auth/network: startup warning counts, config details, provider-specific
  auth checks, stored auth validation, proxy environment details, CA file probes,
  and provider reachability planning/outcome.
- MCP diagnostics: disabled server filtering, required env/stdio errors, HTTP
  probe fallback, HEAD/GET status handling, and combined error text.
- terminal diagnostics: color enablement, narrow/dumb terminal warnings,
  locale/terminfo details, remote indicators, Windows console details, and tmux
  nonfatal probe handling.
- state diagnostics: runtime DB path readiness, SQLite integrity details,
  rollout stats traversal, rollout byte saturation, and fallback state check.
- WebSocket/provider reachability helpers: DNS family details, websocket probe
  warning formatting, provider URL path/query construction, route probe filters,
  and route status classification.
- filesystem helpers: `read_probe_file`, `executable_path_exists`,
  `path_readiness`, `push_path_detail`, `push_env_path_detail`, and
  `env_var_present`.

## Rust Test Inventory

The Rust module currently contains 39 named test functions in its local
`#[cfg(test)]` block.

### Reconciled Rust Tests

This audit pass confirmed explicit Python parity entries or Rust-derived test
comments for all 39 local Rust tests:

- `overall_status_prefers_fail`
- `run_sync_check_notifies_progress`
- `run_async_check_notifies_progress`
- `compare_npm_package_roots_detects_match`
- `compare_npm_package_roots_detects_mismatch`
- `startup_warning_counts_group_known_sources`
- `config_overrides_from_interactive_preserves_global_options`
- `redacted_json_report_structures_and_sanitizes_details`
- `mcp_check_ignores_disabled_servers`
- `mcp_check_warns_for_optional_http_reachability`
- `mcp_check_fails_required_remote_stdio_env_var`
- `provider_specific_auth_allows_non_openai_provider_without_env_key`
- `provider_specific_auth_fails_when_provider_env_key_is_missing`
- `stored_auth_validation_rejects_missing_api_key`
- `stored_auth_validation_rejects_missing_chatgpt_tokens`
- `provider_reachability_mode_uses_api_key_auth`
- `provider_reachability_uses_active_provider_endpoint`
- `provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls`
- `provider_reachability_skips_route_probe_for_bedrock`
- `provider_reachability_api_key_does_not_require_chatgpt`
- `provider_reachability_outcome_reports_required_failures`
- `provider_reachability_route_404_fails_bad_base_url_path`
- `provider_reachability_route_401_keeps_reachability_ok`
- `collect_rollout_stats_counts_nested_rollout_files`
- `http_probe_treats_http_status_as_reachable`
- `mcp_http_probe_falls_back_to_get_when_head_times_out`
- `mcp_check_fails_required_missing_stdio_command`
- `read_probe_file_rejects_unreadable_file`
- `executable_path_exists_rejects_non_executable_file`
- `should_enable_color_respects_terminal_inputs`
- `terminal_check_warns_for_dumb_terminal`
- `terminal_check_warns_for_narrow_terminal`
- `terminal_check_warns_for_declared_narrow_terminal`
- `terminal_check_warns_for_non_utf8_locale`
- `terminal_check_warns_for_unreadable_terminfo_path`
- `terminal_check_reports_remote_indicators_as_present_only`
- `terminal_check_includes_windows_console_details`
- `terminal_check_keeps_tmux_probe_failures_non_fatal`
- `color_output_summary_reports_disabled_reasons`

### Remaining Name-Level Reconciliation

None. All 39 local Rust test names are now represented in Python parity comments
or ledger entries. Remaining work is broader crate-level functional completion
and deferred validation, not local Rust test-name reconciliation for this module.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.

## Non-Test Helper Surface Audit

This pass confirms the important non-test helper surface in
`codex-cli/src/doctor.rs` is either mapped into Python or intentionally adapted:

- Rust `run_doctor` is represented by `pycodex/cli/parser.py::_run_doctor`,
  including JSON vs human output selection and failing exit status when the
  aggregate status is `fail`.
- Rust `build_report` is represented by `_run_doctor` plus the module-local
  `doctor_*_check` helpers in `pycodex/cli/doctor_updates.py`. Python keeps the
  report/check contract and timing fields while adapting Rust's async progress
  scheduling into synchronous CLI assembly.
- Rust `load_config` and `config_overrides_from_interactive` are represented by
  parser-side config loading plus `doctor_cli_overrides_for_load_config` and
  `doctor_config_overrides_from_interactive`.
- Rust `run_sync_check` and `run_async_check` are represented by
  `_doctor_run_sync_check`, `_doctor_run_async_check`, and parser-side
  `_timed_doctor_mapping` for the CLI report path.
- Rust JSON helpers (`redacted_json_report`, `redacted_json_check`,
  `redacted_json_issue`, `structured_json_details`, `overall_status`, and
  `generated_at`) are represented by `redacted_doctor_report_mapping` and its
  local helpers.
- The remaining source-local helper clusters are covered by the behavior areas
  above: installation/runtime/search, config/auth/network, MCP, sandbox,
  terminal, state, WebSocket/provider reachability, and filesystem helpers.

Intentional adaptations and non-scope notes:

- Exact Tokio scheduling/progress rendering is not mirrored; Python preserves
  the externally visible check/report contract instead.
- Human report rendering owned by Rust sibling `src/doctor/output.rs` remains
  outside this `src/doctor.rs` module status file.
- Network transport internals use Python stdlib/injectable probes while keeping
  the Rust status/error classification contracts tracked here.
