# TUI Session Regression Checklist

This checklist connects common `python -m pycodex` product flows to their Rust
owners and executable evidence. It is not a chronological test log.

## Scope Rules

- Rust source and Rust-derived tests are the behavior authority.
- Module tests prove ownership; E2E and native comparisons prove collaboration.
- A row is closed only when its owner, anchor, native/product evidence, Python
  evidence, and remaining debt are explicit.

## P0 Checklist

| ID | Scenario | Rust Owner/Boundary | Rust Anchor | Native Rust/Python Evidence | Python Evidence | Status | Remaining Gap |
|---|---|---|---|---|---|---|---|
| P0-startup | Startup shell and footer | `codex-tui::tui`, `codex-tui::history_cell::session` | `tui.rs::init` and session-header snapshots | `test_windows_conpty_native_and_python_startup_current_screen_when_enabled` | startup and status tests in `tests/e2e/tui/test_startup.py` | closed | Exact Ratatui cell colors remain visual debt. |
| P0-mcp-warning | MCP startup warning projection | `codex-tui::app_server_events`, `codex-tui::app` | MCP startup event and warning routing | `test_windows_conpty_native_and_python_configured_mcp_failure_surface_when_enabled` | MCP warning tests under `pycodex/tui/tests` | closed | Full MCP runtime is outside this TUI projection contract. |
| P0-input-turn | Input submission and turn lifecycle | `codex-tui::bottom_pane::chat_composer`, `codex-tui::chatwidget::protocol` | Enter submission and turn events | `test_windows_conpty_native_and_python_local_sse_multi_turn_clean_shutdown_when_enabled` | session tests in `tests/e2e/tui/test_session.py` | closed | Exact composer chrome remains visual debt. |
| P0-stream-status | Working, reconnect, and interrupt state | `codex-tui::status_indicator_widget`, `codex-tui::chatwidget::streaming` | status tick and interrupt affordance | `test_windows_conpty_native_and_python_active_turn_model_slash_disabled_when_enabled` | reconnect and streaming tests in `tests/e2e/tui/test_reconnect.py` | closed | Spinner cadence remains visual debt. |
| P0-assistant-no-dup | Single assistant finalization | `codex-tui::chatwidget::streaming`, `codex-core::session::turn` | stream-to-history finalization | `test_windows_conpty_native_and_python_local_sse_multi_turn_clean_shutdown_when_enabled` | no-duplicate tests under `pycodex/tui/tests` | closed | Retained-screen placement remains visual debt. |
| P0-tools | Tool progress and output | `codex-core::tools`, `codex-tui::exec_cell` | command lifecycle and exec rendering | `test_windows_conpty_native_and_python_local_sse_exec_command_output_when_enabled` | tool tests in `tests/e2e/tui/test_tools.py` | closed | Exact exec-cell glyphs remain visual debt. |
| P0-reasoning | Summary visible and raw reasoning hidden | `codex-core::session::turn`, `codex-tui::chatwidget::protocol` | summary delta and raw delta routing | `test_windows_conpty_native_and_python_local_sse_reasoning_raw_hidden_by_default_when_enabled` | reasoning tests under `pycodex/tui/tests` | closed | Exact reasoning-cell styling remains visual debt. |
| P0-long-reply | Transcript paging and long replies | `codex-tui::pager_overlay`, `codex-tui::app::input` | `PagerView::handle_key_event` | `test_windows_conpty_native_and_python_long_transcript_overlay_bottom_when_enabled` | pager tests under `pycodex/tui/tests` | closed | Some no-alt-screen projection diagnostics remain opt-in. |
| P0-exit-resume | Exit summary and resume hint | `codex-tui::AppExitInfo`, `codex-cli::format_exit_messages` | exit token and resume formatting | `test_windows_conpty_native_and_python_live_multi_turn_clean_shutdown_when_enabled` | exit tests under `tests/e2e/tui/test_session.py` | closed | Exact final-screen placement remains visual debt. |

## P1 Checklist

| ID | Scenario | Rust Owner/Boundary | Current Evidence | Remaining Gap |
|---|---|---|---|---|
| P1-slash | Slash commands remain local and use Rust-owned views | `codex-tui::chatwidget::slash_dispatch`, `codex-tui::bottom_pane::command_popup` | Slash and status-line tests in `tests/e2e/tui/test_slash_commands.py` and `test_statusline.py` | Less-common nested views still need native visual comparisons. |
| P1-composer | Cursor, history, Unicode, and queued input | `codex-tui::bottom_pane::chat_composer`, `codex-tui::bottom_pane::textarea` | Composer module tests and ConPTY session tests | Seeded persistent Ctrl-R recall remains an opt-in diagnostic. |
| P1-native-harness | Native Rust/Python terminal comparison | `codex-tui::tui::event_stream` | ConPTY support in `tests/e2e/support` | Native executable and terminal readiness vary by environment. |

## Deterministic E2E

```powershell
python -m pytest tests/e2e -q
```

## Live Smoke Gate

Run only with valid OAuth credentials and acceptable network variability:

```powershell
$env:PYCODEX_RUN_LIVE_OAUTH_TUI=1
python -m pytest pycodex/tui/tests/test_live_conversation_integration.py -k live -q --tb=short
```

Native Rust/Python ConPTY comparisons additionally require the native
executable and explicit gates:

```powershell
$env:PYCODEX_RUN_NATIVE_TUI_COMPARISON=1
$env:PYCODEX_RUN_EXPERIMENTAL_CONPTY_TUI=1
$env:PYCODEX_CONPTY_DRIVER_VERIFIED=1
$env:PYCODEX_CONPTY_TUI_INPUT_VERIFIED=1
$env:PYCODEX_NATIVE_CODEX_EXE='C:\Users\27605\AppData\Local\codex-rust-target\codex-rs\debug\codex.exe'
python -m pytest tests/e2e -q --tb=short
```

## Manual Smoke

```powershell
python -m pycodex --no-alt-screen -C C:\Users\27605\codex-python -s read-only -a never
```

Required compatibility inputs retained by the current gate:

- `请分析当前这个项目是做什么的`
- `/status`
- `/model`
- `/quit`
