# codex-config src/config_requirements.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/config/src/config_requirements.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/config_requirements.rs` |
| Python module | `pycodex/config/config_requirements.py` |
| Python tests | `tests/test_config_config_requirements.py` |
| Status | `complete_candidate` |

`src/config_requirements.rs` owns managed requirements TOML shapes and their normalized constraint projection. Loader source discovery, filesystem reads, legacy config loading, and runtime application in core remain outside this module boundary.

## Covered Behavior Areas

- Default requirements allow unrestricted approval policy and reviewer values, read-only permission profile defaults, cached web search defaults, and optional residency constraints.
- `ConfigRequirementsWithSources.merge_unset_fields` fills only unset fields, preserves earlier source precedence, ignores blank guardian policy strings, and merges app requirements with Rust's descending-precedence semantics.
- Approval policy, approvals reviewer, sandbox mode, web search mode, residency, managed hooks, and exec-policy requirements build sourced constraints and include requirement sources in errors.
- Remote sandbox config normalizes hostnames, applies the first matching host pattern, and does not override higher-precedence requirements after source merging.
- Network requirements preserve canonical domain and Unix-socket permission tables, normalize legacy allowed/denied domain lists and allowed Unix socket lists, reject mixed legacy/canonical shapes, and expose allowed/denied projections.
- Filesystem requirements reserve `permissions.filesystem` for requirements-level deny-read constraints and normalize glob-containing patterns.
- Managed permission profiles, app/tool requirements, MCP server identities, plugin MCP requirements, feature requirements, computer-use requirements, appshots, managed-hooks-only, and guardian policy TOML shapes are parsed.
- Exec policy requirements convert TOML rules to a requirements policy and surface parse failures with the requirement source.

## Rust Test Inventory

Representative Rust tests covered in Python include:

- `deserialize_allow_managed_hooks_only`
- `allow_managed_hooks_only_false_is_still_configured`
- `deserialize_managed_permission_profiles`
- `deserialize_allow_appshots`
- `filesystem_requirements_table_cannot_define_a_permission_profile`
- `allow_appshots_false_is_still_configured`
- `deserialize_computer_use_requirements`
- `merge_unset_fields_copies_every_field_and_sets_sources`
- `merge_unset_fields_fills_missing_values`
- `merge_unset_fields_does_not_overwrite_existing_values`
- `merge_unset_fields_ignores_blank_guardian_override`
- `deserialize_guardian_policy_config`
- `blank_guardian_policy_config_is_empty`
- `deserialize_filesystem_deny_read_requirements`
- `deserialize_filesystem_deny_read_glob_requirements`
- `deserialize_apps_requirements`
- `deserialize_apps_tool_requirements`
- `merge_app_requirements_descending_*`
- `merge_unset_fields_merges_apps_across_sources_with_enabled_evaluation`
- `merge_unset_fields_apps_empty_higher_source_does_not_block_lower_disables`
- `constraint_error_includes_requirement_source`
- `deserialize_allowed_approval_policies`
- `deserialize_allowed_approvals_reviewers`
- `deserialize_legacy_allowed_approvals_reviewer`
- `empty_allowed_approvals_reviewers_is_rejected`
- `deserialize_allowed_sandbox_modes`
- `remote_sandbox_config_first_match_overrides_top_level`
- `remote_sandbox_config_non_match_preserves_top_level`
- `remote_sandbox_config_does_not_override_higher_precedence_sandbox_modes`
- `deserialize_allowed_web_search_modes`
- `allowed_web_search_modes_allows_disabled`
- `allowed_web_search_modes_empty_restricts_to_disabled`
- `deserialize_feature_requirements`
- `deserialize_managed_hooks_requirements`
- `merge_unset_fields_does_not_overwrite_existing_hooks`
- `managed_hooks_constraint_rejects_drift`
- `network_requirements_are_preserved_as_constraints_with_source`
- `legacy_network_requirements_are_preserved_as_constraints_with_source`
- `mixed_legacy_and_canonical_network_requirements_are_rejected`
- `network_permission_containers_project_allowed_and_denied_entries`
- `deserialize_mcp_server_requirements`
- `deserialize_plugin_mcp_server_requirements`
- `deserialize_exec_policy_requirements`
- `exec_policy_error_includes_requirement_source`

## Remaining Closeout

- Defer pytest until `codex-config` functional code is complete.
