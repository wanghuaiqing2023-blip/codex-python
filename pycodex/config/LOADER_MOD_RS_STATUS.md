# codex-config `src/loader/mod.rs` alignment

Status: `complete_candidate`

## Scope

- Rust crate: `codex-config`
- Rust module: `codex/codex-rs/config/src/loader/mod.rs`
- Python module: `pycodex/config/loader.py`
- Python tests: `tests/test_config_loader.py`

This status covers the root loader orchestration module: system/user/project
config layer assembly, requirements loading and legacy backfill, session/thread
layer precedence, project-local sanitization, project trust lookup, relative
path resolution, and startup warning behavior.

Sibling modules `loader/layer_io.rs` and `loader/macos.rs` are tracked in
their own status files. This root module status references their loaded-layer
interfaces without re-owning their file IO or managed-preferences parsing
contracts.

## Evidence

- System and requirements path helpers mirror Unix and Windows path contracts,
  including loader override support.
- `insert_layer_by_precedence()` and `source_precedence()` preserve Rust layer
  ordering for system, user, project, session/thread, and legacy managed
  layers.
- `load_requirements_toml()` fills only unset sourced fields, ignores missing
  requirements files, and applies remote sandbox config before source merging.
- `LegacyManagedConfigToml`, `legacy_managed_config_to_requirements()`, and
  `load_requirements_from_legacy_scheme()` mirror legacy managed config
  backfill, including read-only sandbox inclusion and auto-reviewer/user
  reviewer expansion.
- `load_user_config_layer()` returns empty user layers for missing or ignored
  user config.
- `resolve_relative_paths_in_config_toml()` preserves unknown fields while
  resolving known path fields against the layer base directory.
- `sanitize_project_config()` removes the project-local denylist in Rust order
  and `project_ignored_config_keys_warning()` mirrors the warning text shape.
- `project_trust_context()`, project trust lookup helpers, `find_project_root()`,
  `find_git_checkout_root()`, and `load_project_layers()` mirror project-root
  discovery, trust gating, root-to-cwd project layer ordering, disabled
  untrusted bad TOML layers, missing config layer recording, and project
  startup warnings.
- `merge_root_checkout_project_hooks()` mirrors linked-worktree hook override
  behavior by replacing only hook declarations from the root checkout layer.
- `load_config_layers_state()` composes system, user, project, session override,
  injected thread layers, requirements, startup warnings, and legacy managed
  config layers into `ConfigLayerStack`.

## Validation

Not run in this turn. The current automation instruction defers actual pytest
execution until `codex-config` functional code is complete.

