# codex-config test alignment

This ledger records Rust module-scoped behavior contracts for `codex-config`
that are aligned in Python.

Focused validation: `$files = Get-ChildItem tests -Filter 'test_config_*.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q` passed on 2026-06-17 with `271 passed, 13 subtests passed`.

## complete_candidate

### `src/config_toml.rs` typed config TOML document

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/config_toml.rs`
- Python module: `pycodex/config/config_toml.py`
- Python tests: `tests/test_config_config_toml.py`
- Status: `complete_candidate`
- Evidence: Rust defines the aggregate typed `config.toml` document model,
  default helpers, `ForcedChatgptWorkspaceIds`, local nested TOML shapes,
  project trust lookup, model provider validation, OSS provider validation,
  and legacy sandbox to permission profile derivation. Python mirrors those
  contracts through `ConfigToml`, `ConfigLockfileToml`, `DebugToml`,
  `DebugConfigLockToml`, `ThreadStoreToml`, `AutoReviewToml`,
  `ProjectConfig`, realtime audio config, `ToolsToml`, `AgentsToml`,
  `GhostSnapshotToml`, `validate_model_providers()`,
  `validate_oss_provider()`, `ConfigToml.get_active_project()`, and
  `ConfigToml.derive_permission_profile()`. Sibling config modules stored as
  aggregate fields remain tracked by their own module status files.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/config_requirements.rs` managed requirements TOML and constraints

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/config_requirements.rs`
- Python module: `pycodex/config/config_requirements.py`
- Python tests: `tests/test_config_config_requirements.py`
- Status: `complete_candidate`
- Evidence: Rust defines requirements TOML parsing and normalization for
  approval policies, approval reviewers, sandbox modes, remote sandbox host
  overrides, web search modes, feature/computer-use requirements, managed
  hooks, app/tool requirements, MCP/plugin requirements, network and filesystem
  requirements, guardian policy config, residency, and exec-policy rules.
  Python mirrors the module contract through `ConfigRequirementsToml`,
  `ConfigRequirementsWithSources`, `ConfigRequirements`,
  `ConstrainedWithSource`, `Sourced`, network/filesystem containers, app/MCP
  requirement shapes, and `sandbox_mode_requirement_for_permission_profile()`.
  Tests derive from Rust module tests for source precedence, descending app
  merge semantics, first-match remote sandbox config, legacy-to-canonical
  network normalization, mixed-shape rejection, filesystem glob normalization,
  sourced constraint errors, managed-hooks drift rejection, and exec-policy
  parse errors.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/cloud_requirements.rs` cloud requirements loader

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/cloud_requirements.rs`
- Python module: `pycodex/config/cloud_requirements.py`
- Python tests: `tests/test_config_cloud_requirements.py`
- Status: `complete_candidate`
- Evidence: Rust defines `CloudRequirementsLoadErrorCode`, a display-only
  `CloudRequirementsLoadError` with `code()` and `status_code()` accessors,
  and a `CloudRequirementsLoader` backed by a shared async future. Python
  mirrors the default `Ok(None)` loader, single execution across concurrent
  `get()` calls, cloned resolved mapping results for callers, and shared
  failure surfacing.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/constraint.rs` constrained values and constraint errors

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/constraint.rs`
- Python module: `pycodex/config/constraint.py`
- Python tests: `tests/test_config_constraint.py`
- Status: `complete_candidate`
- Evidence: Rust `Constrained` validates initial values, accepts unrestricted
  values through `allow_any`, builds single-value constraints through
  `allow_only`, applies normalizers on initialization and `set`, probes with
  `can_set` without mutation or normalization, and composes validators with
  `add_validator`. Rust `ConstraintError` display strings and
  `RequirementSource` display labels are mirrored in Python.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/diagnostics.rs` config diagnostic ranges and rendering

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/diagnostics.rs`
- Python module: `pycodex/config/diagnostics.py`
- Python tests: `tests/test_config_diagnostics.py`
- Status: `complete_candidate`
- Evidence: Rust uses 1-based `TextPosition`/`TextRange` coordinates, formats
  load errors as `path:line:column: message`, maps TOML and typed TOML failures
  to `ConfigError`, skips non-concrete or unreadable layers while searching
  for the first layer error, renders source snippets with gutters and caret
  spans, and falls back to header-only formatting when source text is
  unavailable. Python mirrors those contracts with dependency-light TOML
  diagnostics and lightweight key-path span anchoring.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/fingerprint.rs` config origin recording and version hashes

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/fingerprint.rs`
- Python module: `pycodex/config/fingerprint.py`
- Python tests: `tests/test_config_fingerprint.py`
- Status: `complete_candidate`
- Evidence: Rust `record_origins` traverses tables and arrays, records only
  scalar leaves with dot-joined paths, includes array indexes, and ignores a
  scalar root with an empty path. Rust `version_for_toml` converts TOML-like
  data to JSON, recursively sorts object keys, preserves array order, hashes
  the canonical serialized JSON with SHA-256, and returns `sha256:<hex>`.
  Python mirrors these contracts through `record_origins()` and
  `version_for_toml()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/host_name.rs` host-name normalization and FQDN preference

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/host_name.rs`
- Python module: `pycodex/config/host_name.py`
- Python tests: `tests/test_config_host_name.py`
- Status: `complete_candidate`
- Evidence: Rust `normalize_host_name` trims whitespace and trailing dots,
  lowercases, and rejects empty hostnames; `normalize_fqdn_candidate` accepts
  only DNS-qualified normalized names; `compute_host_name` prefers a canonical
  FQDN and falls back to the cleaned kernel hostname. Python mirrors these
  contracts through `_normalize_host_name`, `_normalize_fqdn_candidate`, and
  cached `host_name()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/hook_config.rs` hooks config TOML and JSON shapes

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/hook_config.rs`
- Rust tests: `codex/codex-rs/config/src/hooks_tests.rs`
- Python module: `pycodex/config/hook_config.py`
- Python tests: `tests/test_config_hook_config.py`
- Status: `complete_candidate`
- Evidence: Rust defines `HooksFile`, `HooksToml`, `HookStateToml`,
  `HookEventsToml`, `MatcherGroup`, `HookHandlerConfig`, and
  `ManagedHooksRequirementsToml`. Python mirrors existing JSON hook files,
  TOML arrays of event tables, inline state maps, all ten hook event groups,
  helper empty/count/event-order behavior, command/prompt/agent handlers,
  command `timeout`, `async`, `statusMessage`, `commandWindows` and
  `command_windows`, and managed hooks flattened beside `managed_dir` and
  `windows_managed_dir`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/key_aliases.rs` config key alias normalization

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/key_aliases.rs`
- Python module: `pycodex/config/key_aliases.py`
- Python tests: `tests/test_config_key_aliases.py`
- Status: `complete_candidate`
- Evidence: Rust aliases `memories.no_memories_if_mcp_or_web_search` to
  `memories.disable_on_external_context`, applies aliases only at the matching
  table path, preserves an existing canonical key when both names are present,
  recursively normalizes nested tables, and normalizes array items with the
  same table path. Python mirrors these contracts through
  `normalize_key_aliases()` and `normalized_with_key_aliases()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/loader/layer_io.rs` managed config layer IO

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/loader/layer_io.rs`
- Python module: `pycodex/config/loader.py`
- Python tests: `tests/test_config_loader.py`
- Status: `complete_candidate`
- Evidence: Rust defines `MangedConfigFromFile`,
  `ManagedConfigFromMdm`, `LoadedConfigLayers`,
  `load_config_layers_internal`, `read_config_from_path`, strict config TOML
  validation, and `managed_config_default_path`. Python mirrors those
  contracts with `ManagedConfigFromFile`, `ManagedConfigFromMdm`,
  `LoadedConfigLayers`, `load_config_layers_internal()`,
  `read_config_from_path()`, `read_managed_config_from_path()`,
  `managed_config_default_path()`, and dependency-light raw/base64 managed
  preference adapters. Broader loader orchestration and concrete macOS
  preference extraction remain separate module boundaries.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/loader/macos.rs` managed preferences config and requirements

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/loader/macos.rs`
- Python module: `pycodex/config/loader.py`
- Python tests: `tests/test_config_loader.py`
- Status: `complete_candidate`
- Evidence: Rust defines the managed-preferences application id and config /
  requirements keys, MDM requirement source construction, base64 UTF-8 TOML
  decoding, managed config parsing with optional strict validation, managed
  requirements parsing, and requirements merging with remote sandbox config.
  Python mirrors those contracts through
  `MANAGED_PREFERENCES_APPLICATION_ID`, `MANAGED_PREFERENCES_CONFIG_KEY`,
  `MANAGED_PREFERENCES_REQUIREMENTS_KEY`,
  `managed_preferences_requirements_source()`,
  `managed_config_from_mdm_base64()`,
  `managed_requirements_from_mdm_base64()`, and
  `load_managed_admin_requirements_toml()`. CoreFoundation preference reads
  are intentionally represented by raw/base64 injection helpers.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/loader/mod.rs` root config loader orchestration

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/loader/mod.rs`
- Python module: `pycodex/config/loader.py`
- Python tests: `tests/test_config_loader.py`
- Status: `complete_candidate`
- Evidence: Rust owns the root loader flow that assembles requirements and
  config layers from system, user, project, session/runtime, thread, and
  legacy managed sources. Python mirrors the module contract through system
  path helpers, `insert_layer_by_precedence()`, `load_requirements_toml()`,
  `LegacyManagedConfigToml`, `load_requirements_from_legacy_scheme()`,
  `load_user_config_layer()`, `sanitize_project_config()`,
  `project_trust_context()`, project trust lookup helpers,
  `load_project_layers()`, `merge_root_checkout_project_hooks()`,
  `resolve_relative_paths_in_config_toml()`, and
  `load_config_layers_state()`. The `loader/layer_io.rs` and
  `loader/macos.rs` child modules remain separately tracked status units.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/lib.rs` crate-root export surface

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/lib.rs`
- Python module: `pycodex/config/__init__.py`
- Python tests: package import coverage across `tests/test_config_*.py`
- Status: `complete_candidate`
- Evidence: Rust declares the config crate modules, exposes
  `CONFIG_TOML_FILE`, public child modules, and `pub use` aliases for config
  requirements, constraints, diagnostics, hooks, host name, edit helpers, MCP
  shapes, merge, project root markers, requirements exec policy, schema,
  skills, state, strict config, thread config, and typed config values. Python
  mirrors that crate-root convenience surface through `pycodex.config`
  imports and `__all__`, while each functional contract remains tracked by its
  own module status file.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/marketplace_edit.rs` user marketplace config edits

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/marketplace_edit.rs`
- Python module: `pycodex/config/marketplace_edit.py`
- Python tests: `tests/test_config_marketplace_edit.py`
- Status: `complete_candidate`
- Evidence: Rust defines `MarketplaceConfigUpdate`,
  `RemoveMarketplaceConfigOutcome`, `record_user_marketplace`,
  `remove_user_marketplace`, and `remove_user_marketplace_config` for
  marketplace settings in `$CODEX_HOME/config.toml`. Python mirrors update
  writes with optional revision/ref/sparse paths, missing-config not-found
  behavior, boolean removal results, case-mismatch reporting with the
  configured name, table and inline-table removal, and empty `marketplaces`
  table cleanup. Python intentionally uses a dependency-light TOML
  mapping/serializer rather than `toml_edit::DocumentMut` decoration
  preservation.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/merge.rs` config layer merge semantics

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/merge.rs`
- Rust tests: `codex/codex-rs/config/src/merge_tests.rs`
- Python module: `pycodex/config/merge.py`
- Python tests: `tests/test_config_merge.py`
- Status: `complete_candidate`
- Evidence: Rust recursively merges TOML tables with overlay precedence,
  replaces mixed table/non-table values with normalized overlay values,
  normalizes memory key aliases in both base and overlay layers, preserves the
  canonical memory key when canonical and legacy names appear together, and
  normalizes `permissions.<profile>.network.domains` keys before overlaying.
  Python mirrors those contracts through `merge_toml_values()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/mcp_types.rs` MCP server config shapes

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/mcp_types.rs`
- Rust tests: `codex/codex-rs/config/src/mcp_types_tests.rs`
- Python module: `pycodex/config/mcp_types.py`
- Python tests: `tests/test_config_mcp_types.py`
- Status: `complete_candidate`
- Evidence: Rust defines MCP config data shapes for app tool approval,
  disabled reasons, per-tool approval config, env var source metadata, OAuth
  client config, raw-to-effective server config conversion, stdio and
  streamable-http transports, timeout parsing, enabled/required/parallel
  flags, tool filters, scopes, OAuth resource, and remote stdio cwd validation.
  Python mirrors those contracts with `McpServerConfig`,
  `McpServerTransportConfig`, `McpServerEnvVar`,
  `McpServerOAuthConfig`, `McpServerToolConfig`, `AppToolApproval`, and
  `McpServerDisabledReason`, while keeping MCP runtime startup and transport
  execution outside this module boundary.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/mcp_edit.rs` global MCP config edits

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/mcp_edit.rs`
- Rust tests: `codex/codex-rs/config/src/mcp_edit_tests.rs`
- Python module: `pycodex/config/mcp_edit.py`
- Python tests: `tests/test_config_mcp_edit.py`
- Status: `complete_candidate`
- Evidence: Rust loads `$CODEX_HOME/config.toml` MCP server entries, treats
  missing config or missing `mcp_servers` as empty, rejects inline
  `bearer_token` before type conversion, replaces/removes the complete
  `mcp_servers` table through `ConfigEditsBuilder`, creates `CODEX_HOME` before
  writing, serializes stdio and streamable-http transports, sorted env/header
  tables, env var entries, timeouts, tool filters, OAuth client id/resource,
  per-server approval defaults, and sorted per-tool approval overrides. Python
  mirrors those contracts with dependency-light TOML parsing/serialization and
  Rust-derived snapshot tests.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/overrides.rs` TOML-shaped override layers

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/overrides.rs`
- Python module: `pycodex/config/overrides.py`
- Python tests: `tests/test_config_overrides.py`
- Status: `complete_candidate`
- Evidence: Rust `default_empty_table` creates an empty TOML table and
  `build_cli_overrides_layer` applies parsed `(path, value)` pairs in order.
  Dotted paths create nested tables, leaf assignments overwrite prior values,
  and non-table intermediate values are replaced with tables before applying
  deeper segments. Python mirrors those contracts through
  `default_empty_table()`, `build_cli_overrides_layer()`, and
  `apply_single_override()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/permissions_toml.rs` permission profiles and network TOML

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/permissions_toml.rs`
- Python module: `pycodex/config/permissions_toml.py`
- Python tests: `tests/test_config_permissions_toml.py`
- Status: `complete_candidate`
- Evidence: Rust defines permission profile TOML shapes, workspace-root
  filtering, filesystem/network permission helpers, profile inheritance
  resolution and error variants, network proxy application, domain/Unix socket
  overlays, MITM action/hook validation, and runtime MITM hook conversion.
  Python mirrors those contracts with `PermissionsToml`,
  `PermissionProfileToml`, `NetworkToml`, `NetworkMitmToml`, the domain/socket
  permission containers, `merge_permission_profiles()`, and
  `overlay_network_domain_permissions()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/plugin_edit.rs` user plugin config edits

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/plugin_edit.rs`
- Python module: `pycodex/config/plugin_edit.py`
- Python tests: `tests/test_config_plugin_edit.py`
- Status: `complete_candidate`
- Evidence: Rust defines `PluginConfigEdit`, `set_user_plugin_enabled`,
  `clear_user_plugin`, and `apply_user_plugin_config_edits` for user plugin
  settings in `$CODEX_HOME/config.toml`. Python mirrors set-enabled writes,
  preservation of existing plugin fields, clearing plugin entries, removing an
  empty plugins table, no-op behavior for missing clear targets, no-op behavior
  for empty edit lists, and ordered edit batches. Python intentionally uses a
  dependency-light TOML mapping/serializer instead of `toml_edit::DocumentMut`
  decoration preservation.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/profile_toml.rs` named profile TOML shapes

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/profile_toml.rs`
- Python module: `pycodex/config/profile_toml.py`
- Python tests: `tests/test_config_profile_toml.py`
- Status: `complete_candidate`
- Evidence: Rust `ConfigProfile` defines the profile-scoped optional config
  field set with `deny_unknown_fields`, keeps deprecated JS REPL fields as
  schema-skipped compatibility inputs, and exposes profile-scoped `ProfileTui`
  with `session_picker_view`. Python mirrors those contracts with
  `ConfigProfile.from_mapping()`, `ProfileTui.from_mapping()`, path
  normalization, unknown-field rejection, enum wire-value validation, and
  TOML-like `to_mapping()` output.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/tui_keymap.rs` TUI keymap config schema

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/tui_keymap.rs`
- Python module: `pycodex/config/tui_keymap.py`
- Python tests: `tests/test_config_tui_keymap.py`
- Status: `complete_candidate`
- Evidence: Rust owns the typed `[tui.keymap]` config shape, rejects unknown
  contexts/actions, rejects removed backtrack actions, accepts global action
  bindings including `minus` and `alt-minus`, preserves single binding, list
  binding, and empty-list unbind shapes, and canonicalizes key specs with
  modifier aliases, key aliases, and `ctrl-alt-shift` modifier ordering.
  Python mirrors those contracts through `TuiKeymap`, the context dataclasses,
  `KeybindingsSpec`, and `normalize_keybinding_spec()`, plus `Tui.keymap`
  integration.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/types.rs` loaded and effective config value types

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/types.rs`
- Rust tests: `codex/codex-rs/config/src/types_tests.rs`
- Python module: `pycodex/config/types.py`
- Python tests: `tests/test_config_types.py`
- Status: `complete_candidate`
- Evidence: Rust defines simple config value types, enum wire names, defaults,
  and conversion helpers for session picker view, credential store modes,
  Windows/TUI/history/analytics/feedback/notifications, tool suggestions,
  memories, apps, OTEL, notices, plugin policy, marketplace state, sandbox
  workspace-write settings, and shell environment policy. Python mirrors those
  contracts with source-derived tests for memory clamping and legacy aliases,
  enum wire/display values, TUI aggregate defaults and overrides,
  apps/OTEL/notice/plugin/marketplace/sandbox shapes, shell environment policy
  conversion, and unknown-field or invalid-shape rejection. Re-exported sibling
  behavior remains tracked in each sibling module's own status file.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/project_root_markers.rs` marker config parsing

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/project_root_markers.rs`
- Python module: `pycodex/config/project_root_markers.py`
- Python tests: `tests/test_config_project_root_markers.py`
- Status: `complete_candidate`
- Evidence: Rust returns the default marker list `[".git"]`; missing or
  non-table config returns `None`; a specified string array returns the marker
  list; an empty array is preserved as an explicit empty list; and any
  specified non-array or non-string entry reports
  `project_root_markers must be an array of strings`. Python mirrors these
  contracts through `default_project_root_markers()` and
  `project_root_markers_from_config()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/requirements_exec_policy.rs` requirements exec-policy rules

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/requirements_exec_policy.rs`
- Python module: `pycodex/config/requirements_exec_policy.py`
- Python tests: `tests/test_config_requirements_exec_policy.py`
- Status: `complete_candidate`
- Evidence: Rust defines the `[rules]` TOML shape for requirements, converts
  prefix rules into exec-policy prefix rules, expands first-token alternatives
  into one program rule per head token, rejects empty rule lists, empty
  patterns, empty justifications, missing decisions, `allow` decisions, and
  invalid `token`/`any_of` pattern-token shapes, and compares
  `RequirementsExecPolicy` values through sorted policy fingerprints. Python
  mirrors these contracts through `RequirementsExecPolicyToml`,
  `RequirementsExecPolicyPrefixRuleToml`,
  `RequirementsExecPolicyPatternTokenToml`,
  `RequirementsExecPolicyDecisionToml`,
  `RequirementsExecPolicyParseError`, and `RequirementsExecPolicy`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/schema.rs` config schema helpers

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/schema.rs`
- Python module: `pycodex/config/schema.py`
- Python tests: `tests/test_core_bin_config_schema.py`
- Status: `complete_candidate`
- Evidence: Rust builds the config schema, recursively canonicalizes JSON
  object keys while preserving array order, renders pretty JSON bytes, and
  writes them to disk. Python mirrors the public helper surface with
  `canonicalize()`, `config_schema()`, `config_schema_json()`, and
  `write_config_schema()`, using the checked-in upstream schema fixture rather
  than a Python schemars dependency.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/skills_config.rs` skill config shapes

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/skills_config.rs`
- Rust tests: `codex/codex-rs/config/src/types_tests.rs`
- Python module: `pycodex/config/skills_config.py`
- Python tests: `tests/test_config_skills_config.py`
- Status: `complete_candidate`
- Evidence: Rust defines the skill config data shapes re-exported through
  `codex-config`: `SkillConfig`, `SkillsConfig`, and `BundledSkillsConfig`.
  Python mirrors `BundledSkillsConfig` default `enabled=true`,
  `SkillsConfig` optional/empty defaults, path and name selectors,
  required `SkillConfig.enabled` during deserialization, unknown-field
  rejection, invalid shape rejection, and TOML-like mapping round trips.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/state.rs` config layer state

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/state.rs`
- Rust tests: `codex/codex-rs/config/src/state_tests.rs`
- Python module: `pycodex/config/state.py`
- Python tests: `tests/test_config_state.py`
- Status: `complete_candidate`
- Evidence: Rust defines `ConfigLoadOptions`, `LoaderOverrides`,
  `ConfigLayerEntry`, `ConfigLayerStackOrdering`, `ConfigLayerStack`, and
  layer-order validation. Python mirrors loader override defaults, user config
  path fallback, raw/disabled layer constructors, version metadata, API layer
  projection, config and hook folder lookup, startup warnings, requirements
  accessors, disabled-layer filtering, high-to-low layer ordering, effective
  config and effective user config merges, canonical origin recording, active
  highest-precedence user layer selection, user-layer replacement, user-layer
  copying, precedence validation, and project root-to-cwd validation.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/thread_config.rs` thread config root loader/source behavior

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/thread_config.rs`
- Python module: `pycodex/config/thread_config.py`
- Python tests: `tests/test_config_thread_config.py`
- Status: `complete_candidate`
- Evidence: Rust defines `ThreadConfigContext`, `SessionThreadConfig`,
  `UserThreadConfig`, `ThreadConfigSource`, `ThreadConfigLoadErrorCode`,
  `ThreadConfigLoadError`, `ThreadConfigLoader`, `StaticThreadConfigLoader`,
  `NoopThreadConfigLoader`, root source-to-layer conversion, and session config
  TOML projection. Python mirrors the static and noop loader contracts, error
  accessors/display, `load_config_layers()` conversion flow, user-source
  no-layer behavior, empty-session suppression, session `SessionFlags` layer
  creation, `model_provider` and `model_providers` projection, and sorted
  feature boolean projection. Rust `src/thread_config/remote.rs` remains a
  separate module boundary for concrete remote/proto behavior.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/thread_config/remote.rs` remote thread config compatibility

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/thread_config/remote.rs`
- Python module: `pycodex/config/thread_config.py`
- Python tests: `tests/test_config_thread_config.py`
- Status: `complete_candidate`
- Evidence: Rust defines the gRPC-backed `RemoteThreadConfigLoader`, 5-second
  `load_thread_config_request` timeout, remote status to
  `ThreadConfigLoadErrorCode` mapping, proto source conversion, session config
  conversion, `ModelProviderInfo` conversion, auth command conversion, and
  parse-error paths for omitted source payloads, missing provider ids, omitted
  or unknown wire APIs, zero auth timeouts, and invalid auth cwd values. Python
  mirrors the request and conversion contracts with an injectable client
  boundary instead of a concrete tonic/gRPC dependency.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.

### `src/strict_config.rs` ignored fields and unknown feature diagnostics

- Rust owner: `codex-config`
- Rust module: `codex/codex-rs/config/src/strict_config.rs`
- Rust tests: `codex/codex-rs/config/src/strict_config_tests.rs`
- Python module: `pycodex/config/strict_config.py`
- Python tests: `tests/test_config_strict_config.py`
- Status: `complete_candidate`
- Evidence: Rust strict config validation converts TOML parse failures to
  diagnostics, lets type errors take precedence over ignored fields, reports
  unknown top-level fields with key spans, rejects unknown feature keys under
  `[features]` and `[profiles.<name>.features]`, accepts opaque desktop keys,
  and preserves non-file source names. Python mirrors those contracts with
  `config_error_from_ignored_toml_fields()`,
  `config_error_from_ignored_toml_value_fields()`,
  `ignored_toml_value_field()`, and `unknown_feature_toml_value_field()`.
- Validation: not run in this turn; current automation defers actual pytest
  execution until `codex-config` functional code is complete.
