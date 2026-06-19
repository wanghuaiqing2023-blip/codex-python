# codex-config src/types.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/config/src/types.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/types.rs` |
| Python module | `pycodex/config/types.py` |
| Python tests | `tests/test_config_types.py` |
| Status | `complete_candidate` |

`src/types.rs` owns simple loaded/effective Codex config value types, enum wire names, defaults, and narrow conversion helpers. Behavior owned by re-exported sibling modules such as `mcp_types`, `skills_config`, and `tui_keymap` is tracked in those modules' own status files.

## Covered Behavior Areas

- Session picker, auth credential store, OAuth credential store, Windows sandbox, URI file opener, history, notification, pet-anchor, and marketplace source enums keep Rust wire values.
- `UriBasedFileOpener.get_scheme`, notification display values, and session picker display values mirror Rust.
- `History`, analytics, feedback, tool-suggest, apps, plugin, marketplace, sandbox workspace-write, OTEL, notice, TUI, and shell environment policy TOML shapes reject unknown fields where Rust uses `deny_unknown_fields`.
- `ToolSuggestDisabledTool.normalized` trims ids and drops empty ids.
- `MemoriesConfig` applies Rust defaults and clamps raw-memory, rollout, unused-days, rollout-age, idle-hour, and rate-limit thresholds.
- `MemoriesToml` accepts the legacy `no_memories_if_mcp_or_web_search` alias.
- `AppsConfigToml`, `AppConfig`, app tool config, plugin MCP server config, and marketplace config preserve Rust field names and defaults.
- `OtelConfig` applies Rust defaults, including `dev` environment and Statsig metrics exporter.
- `Tui` aggregate defaults and overrides match Rust fields, including notifications, alternate screen, status line, terminal title, pet settings, keymap, model availability NUX, and resize-reflow row cap.
- `Notice` and external config migration prompt shapes preserve renamed GPT-5.1 Codex Max field and default maps.
- `SandboxWorkspaceWrite` converts to the app-server sandbox settings shape.
- `ShellEnvironmentPolicyToml` converts to shell environment policy defaults and overrides.

## Rust Test Inventory

- `memories_config_clamps_count_limits_to_nonzero_values`
- `memories_config_clamps_rate_limit_remaining_threshold`
- `deserialize_skill_config_with_name_selector` (via `types.rs` re-export)
- `deserialize_skill_config_with_path_selector` (via `types.rs` re-export)

Additional Python coverage records source-derived contracts for enum wire values, TUI aggregate defaults, apps/OTEL/notice/plugin/marketplace/sandbox shapes, shell environment policy conversion, unknown-field rejection, and memory alias/default behavior.

## Remaining Closeout

- Defer pytest until `codex-config` functional code is complete.
