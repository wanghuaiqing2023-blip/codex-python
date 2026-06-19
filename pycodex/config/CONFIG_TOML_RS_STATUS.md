# codex-config `src/config_toml.rs` alignment

Status: `complete_candidate`

## Scope

- Rust crate: `codex-config`
- Rust module: `codex/codex-rs/config/src/config_toml.rs`
- Python module: `pycodex/config/config_toml.py`
- Python tests: `tests/test_config_config_toml.py`

This status covers the module-scoped behavior contract for the typed
`config.toml` document model: top-level config fields, default helpers,
workspace ID parsing, project trust lookup, legacy sandbox to permission
profile derivation, model provider validation, OSS provider validation, and
the local nested TOML data shapes owned by `config_toml.rs`.

Sibling module contracts such as MCP server types, permission profiles,
profiles, hooks, skills, thread config, strict config, and requirements are
tracked in their own module status files even when `ConfigToml` stores those
values as aggregate fields.

## Evidence

- `DEFAULT_PROJECT_DOC_MAX_BYTES`, project-doc defaults, and login-shell
  defaults are mirrored by Python defaults.
- `ForcedChatgptWorkspaceIds` accepts a single string or a list of strings,
  exposes `into_vec()`, and rejects comma-separated single-string values with
  the Rust user-facing guidance.
- `ConfigToml.from_toml()` and `from_mapping()` parse the supported top-level
  TOML surface into typed Python dataclasses while rejecting unknown top-level
  fields.
- `ConfigLockfileToml`, `DebugToml`, `DebugConfigLockToml`,
  `ThreadStoreToml`, `AutoReviewToml`, `ProjectConfig`, realtime audio config,
  `ToolsToml`, `AgentsToml`, and `GhostSnapshotToml` mirror the Rust local
  shapes and wire values needed by core configuration loading.
- `ProjectConfig.is_trusted()` and `is_untrusted()` match Rust trust-level
  semantics.
- `ConfigToml.get_active_project()` mirrors Rust project lookup precedence:
  resolved cwd first, then repo root, with path normalization for lookup keys.
- `ConfigToml.derive_permission_profile()` mirrors the Rust legacy sandbox
  precedence for explicit sandbox overrides, configured sandbox modes, trusted
  project defaults, and the feature-gated implicit default fallback.
- `validate_model_providers()` rejects reserved model provider ids and provider
  entries that try to shadow built-in provider ids, matching Rust validation.
- `validate_oss_provider()` accepts `lmstudio` and `ollama` and rejects the
  legacy Ollama chat provider id and unknown providers, matching Rust.

## Validation

Not run in this turn. The current automation instruction defers actual pytest
execution until `codex-config` functional code is complete.

