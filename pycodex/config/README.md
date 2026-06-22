# pycodex.config

This package contains Python counterparts for Rust configuration behavior.

## Rust Counterparts

```text
Primary Rust crate: codex-config
Primary Rust path: codex/codex-rs/config

Related Rust crates:
- codex-execpolicy
- codex-features
- codex-model-provider-info
```

## Alignment Role

`pycodex.config` should own configuration parsing, overrides, config data
contracts, and policy-facing config decisions that are not specific to one
runtime entrypoint.

Typical Rust module counterparts include:

```text
codex/codex-rs/config/src/overrides.rs
codex/codex-rs/config/src/config_toml.rs
codex/codex-rs/config/src/types.rs
codex/codex-rs/config/src/profile_toml.rs
codex/codex-rs/config/src/permissions_toml.rs
codex/codex-rs/config/src/merge.rs
codex/codex-rs/config/src/strict_config.rs
```

## Python Modules

Current Python implementation files:

| Python module/file | Role |
|---|---|
| `pycodex/config/cloud_requirements.py` | cloud requirements loader abstraction and load errors |
| `pycodex/config/config_requirements.py` | managed requirements TOML shapes, source precedence, constraints, network/filesystem requirements, apps, MCP, hooks, and exec-policy requirements |
| `pycodex/config/config_toml.py` | typed `config.toml` document model, defaults, project lookup, model provider validation, and legacy sandbox permission-profile derivation |
| `pycodex/config/constraint.py` | constrained-value helpers, requirement source labels, and constraint error formatting |
| `pycodex/config/diagnostics.py` | config parse/validation diagnostic locations and rendering |
| `pycodex/config/merge.py` | TOML-like config layer merge semantics and key normalization |
| `pycodex/config/mcp_edit.py` | global MCP server config loading and persistence edits |
| `pycodex/config/overrides.py` | config override parsing and CLI override representation |
| `pycodex/config/permissions_toml.py` | permission profile TOML shapes, inheritance, network, and MITM helpers |
| `pycodex/config/plugin_edit.py` | user plugin enablement config edits |
| `pycodex/config/profile_toml.py` | named profile TOML shapes and profile-scoped TUI settings |
| `pycodex/config/schema.py` | config schema fixture canonicalization and write helper |
| `pycodex/config/skills_config.py` | skill-related config data shapes and selector entries |
| `pycodex/config/state.py` | config layer entries, layer stack ordering, merged views, and origins |
| `pycodex/config/thread_config.py` | thread-scoped config source loaders, remote compatibility helpers, and session layer conversion |
| `pycodex/config/strict_config.py` | strict config ignored-field and unknown feature diagnostics |
| `pycodex/config/toml_compat.py` | dependency-light TOML compatibility parser used by config-facing code |
| `pycodex/config/tui_keymap.py` | TUI keymap config schema and keybinding normalization |
| `pycodex/config/fingerprint.py` | config origin path recording and deterministic config version hashes |
| `pycodex/config/hook_config.py` | hooks TOML/JSON shapes, hook event groups, handler config, and managed hook requirements |
| `pycodex/config/host_name.py` | best-effort local host name normalization and FQDN preference |
| `pycodex/config/key_aliases.py` | config key alias normalization before typed loading |
| `pycodex/config/loader.py` | config loader helpers, managed layer IO, project layers, precedence, and layer stack construction |
| `pycodex/config/__init__.py` | crate-root style package export surface for config modules |
| `pycodex/config/marketplace_edit.py` | user marketplace config edits |
| `pycodex/config/mcp_types.py` | MCP server config shapes, transport validation, env var source handling, and tool approval config |
| `pycodex/config/project_root_markers.py` | project root marker config parsing and defaults |
| `pycodex/config/requirements_exec_policy.py` | requirements.toml exec-policy rule shape and conversion helpers |
| `pycodex/config/types.py` | loaded/effective config value types, defaults, and simple conversions |

`pycodex/_toml.py` has been deleted; use `pycodex.config.toml_compat` directly.

## Module Status Files

| Status file | Scope |
|---|---|
| `pycodex/config/CLOUD_REQUIREMENTS_RS_STATUS.md` | Tracks only Rust `codex-config/src/cloud_requirements.rs`; cloud requirements loader helpers are complete-candidate. |
| `pycodex/config/CONFIG_REQUIREMENTS_RS_STATUS.md` | Tracks only Rust `codex-config/src/config_requirements.rs`; managed requirements TOML behavior is complete-candidate. |
| `pycodex/config/CONFIG_TOML_RS_STATUS.md` | Tracks only Rust `codex-config/src/config_toml.rs`; typed config TOML behavior is complete-candidate. |
| `pycodex/config/CONSTRAINT_RS_STATUS.md` | Tracks only Rust `codex-config/src/constraint.rs`; constrained-value helpers are complete-candidate. |
| `pycodex/config/DIAGNOSTICS_RS_STATUS.md` | Tracks only Rust `codex-config/src/diagnostics.rs`; config diagnostic rendering is complete-candidate. |
| `pycodex/config/FINGERPRINT_RS_STATUS.md` | Tracks only Rust `codex-config/src/fingerprint.rs`; config fingerprints/origins are complete-candidate. |
| `pycodex/config/HOOK_CONFIG_RS_STATUS.md` | Tracks only Rust `codex-config/src/hook_config.rs`; hook config TOML/JSON shapes are complete-candidate. |
| `pycodex/config/HOST_NAME_RS_STATUS.md` | Tracks only Rust `codex-config/src/host_name.rs`; host-name normalization is complete-candidate. |
| `pycodex/config/KEY_ALIASES_RS_STATUS.md` | Tracks only Rust `codex-config/src/key_aliases.rs`; config key alias normalization is complete-candidate. |
| `pycodex/config/LIB_RS_STATUS.md` | Tracks only Rust `codex-config/src/lib.rs`; crate-root export surface is complete-candidate. |
| `pycodex/config/LOADER_LAYER_IO_RS_STATUS.md` | Tracks only Rust `codex-config/src/loader/layer_io.rs`; managed layer IO behavior is complete-candidate. |
| `pycodex/config/LOADER_MACOS_RS_STATUS.md` | Tracks only Rust `codex-config/src/loader/macos.rs`; managed preferences parsing/requirements behavior is complete-candidate. |
| `pycodex/config/LOADER_MOD_RS_STATUS.md` | Tracks only Rust `codex-config/src/loader/mod.rs`; root loader orchestration behavior is complete-candidate. |
| `pycodex/config/MARKETPLACE_EDIT_RS_STATUS.md` | Tracks only Rust `codex-config/src/marketplace_edit.rs`; user marketplace config edits are complete-candidate. |
| `pycodex/config/MERGE_RS_STATUS.md` | Tracks only Rust `codex-config/src/merge.rs`; config layer merge behavior is complete-candidate. |
| `pycodex/config/MCP_EDIT_RS_STATUS.md` | Tracks only Rust `codex-config/src/mcp_edit.rs`; global MCP config edit behavior is complete-candidate. |
| `pycodex/config/MCP_TYPES_RS_STATUS.md` | Tracks only Rust `codex-config/src/mcp_types.rs`; MCP config shape behavior is complete-candidate. |
| `pycodex/config/OVERRIDES_RS_STATUS.md` | Tracks only Rust `codex-config/src/overrides.rs`; TOML-shaped override layers are complete-candidate. |
| `pycodex/config/PERMISSIONS_TOML_RS_STATUS.md` | Tracks only Rust `codex-config/src/permissions_toml.rs`; permission profile TOML behavior is complete-candidate. |
| `pycodex/config/PLUGIN_EDIT_RS_STATUS.md` | Tracks only Rust `codex-config/src/plugin_edit.rs`; user plugin config edits are complete-candidate. |
| `pycodex/config/PROFILE_TOML_RS_STATUS.md` | Tracks only Rust `codex-config/src/profile_toml.rs`; named profile TOML shapes are complete-candidate. |
| `pycodex/config/PROJECT_ROOT_MARKERS_RS_STATUS.md` | Tracks only Rust `codex-config/src/project_root_markers.rs`; marker parsing/defaults are complete-candidate. |
| `pycodex/config/REQUIREMENTS_EXEC_POLICY_RS_STATUS.md` | Tracks only Rust `codex-config/src/requirements_exec_policy.rs`; requirements exec-policy helpers are complete-candidate. |
| `pycodex/config/SCHEMA_RS_STATUS.md` | Tracks only Rust `codex-config/src/schema.rs`; config schema helpers are complete-candidate. |
| `pycodex/config/SKILLS_CONFIG_RS_STATUS.md` | Tracks only Rust `codex-config/src/skills_config.rs`; skill config shapes are complete-candidate. |
| `pycodex/config/STATE_RS_STATUS.md` | Tracks only Rust `codex-config/src/state.rs`; config layer state helpers are complete-candidate. |
| `pycodex/config/THREAD_CONFIG_REMOTE_RS_STATUS.md` | Tracks only Rust `codex-config/src/thread_config/remote.rs`; remote thread config compatibility behavior is complete-candidate. |
| `pycodex/config/THREAD_CONFIG_RS_STATUS.md` | Tracks only Rust `codex-config/src/thread_config.rs`; thread config root loader/source behavior is complete-candidate. |
| `pycodex/config/STRICT_CONFIG_RS_STATUS.md` | Tracks only Rust `codex-config/src/strict_config.rs`; strict config diagnostics are complete-candidate. |
| `pycodex/config/TUI_KEYMAP_RS_STATUS.md` | Tracks only Rust `codex-config/src/tui_keymap.rs`; TUI keymap config behavior is complete-candidate. |
| `pycodex/config/TYPES_RS_STATUS.md` | Tracks only Rust `codex-config/src/types.rs`; config value types are complete-candidate. |

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
config.overrides
config.toml_loading
config.merge
config.profile
config.permissions
config.strict_config
```

## Test Source Policy

Prefer Rust config tests and fixtures before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-config
# Rust module: src/overrides.rs
# Rust test: tests::example_test_name
# Contract: config.overrides
```

## Current Movement Status

`codex-config` is complete as of 2026-06-17. Module-level parity is recorded in
`pycodex/config/TEST_ALIGNMENT.md`, and focused config validation passed with
`271 passed, 13 subtests passed`.
