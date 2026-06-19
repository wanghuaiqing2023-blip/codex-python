# codex-backend-openapi-models test alignment

Rust crate: `codex-backend-openapi-models`

Python package: `pycodex/codex_backend_openapi_models`

Status: `complete`

Certified modules:

- `codex/codex-rs/codex-backend-openapi-models/src/models/additional_rate_limit_details.rs`
  -> `pycodex/codex_backend_openapi_models/models/additional_rate_limit_details.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_window_snapshot.rs`
  -> `pycodex/codex_backend_openapi_models/models/rate_limit_window_snapshot.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_details.rs`
  -> `pycodex/codex_backend_openapi_models/models/rate_limit_status_details.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_payload.rs`
  -> `pycodex/codex_backend_openapi_models/models/rate_limit_status_payload.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/credit_status_details.rs`
  -> `pycodex/codex_backend_openapi_models/models/credit_status_details.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/config_file_response.rs`
  -> `pycodex/codex_backend_openapi_models/models/config_file_response.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/git_pull_request.rs`
  -> `pycodex/codex_backend_openapi_models/models/git_pull_request.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/external_pull_request_response.rs`
  -> `pycodex/codex_backend_openapi_models/models/external_pull_request_response.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/task_response.rs`
  -> `pycodex/codex_backend_openapi_models/models/task_response.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/code_task_details_response.rs`
  -> `pycodex/codex_backend_openapi_models/models/code_task_details_response.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/task_list_item.rs`
  -> `pycodex/codex_backend_openapi_models/models/task_list_item.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/paginated_list_task_list_item_.rs`
  -> `pycodex/codex_backend_openapi_models/models/paginated_list_task_list_item.py`
- `codex/codex-rs/codex-backend-openapi-models/src/models/mod.rs`
  -> `pycodex/codex_backend_openapi_models/models/__init__.py`
- `codex/codex-rs/codex-backend-openapi-models/src/lib.rs`
  -> `pycodex/codex_backend_openapi_models/__init__.py`

Remaining Rust modules:

None. All known Rust modules in this crate are mapped.

Rust tests and fixtures for certified modules:

- `src/models/additional_rate_limit_details.rs`
  - Source-contract coverage for required string fields, `new(...)` defaults,
    derived default values, and `serde_with::rust::double_option` JSON behavior
    for omitted/null/object `rate_limit`.
- `src/models/rate_limit_window_snapshot.rs`
  - Source-contract coverage for four `i32` fields, derived default zero
    values, `new(...)` constructor assignment, and serde snake_case field names.
- `src/models/rate_limit_status_details.rs`
  - Source-contract coverage for bool fields, derived default false values,
    `new(...)` defaults, and `serde_with::rust::double_option` JSON behavior for
    omitted/null/object primary and secondary windows.
- `src/models/rate_limit_status_payload.rs`
  - Source-contract coverage for `PlanType` and `RateLimitReachedKind` serde
    values plus unknown fallback, `RateLimitReachedType` JSON key `type`,
    payload constructor/default behavior, and double-option JSON behavior for
    rate-limit, credits, additional-rate-limits, and reached-type fields.
- `src/models/credit_status_details.rs`
  - Source-contract coverage for bool fields, derived default false values,
    `new(...)` defaults, balance string double-option behavior, and approximate
    local/cloud message JSON array double-option behavior.
- `src/models/config_file_response.rs`
  - Source-contract coverage for optional string fields, `new(...)`
    constructor assignment, derived default `None` values, serde field names,
    and `skip_serializing_if = Option::is_none` omission behavior.
- `src/models/git_pull_request.rs`
  - Source-contract coverage for required pull request scalar fields, optional
    string/bool/JSON fields, derived defaults, `new(...)` constructor
    assignment, serde field names, and skip-none optional serialization.
- `src/models/external_pull_request_response.rs`
  - Source-contract coverage for required response IDs, nested
    `GitPullRequest`, derived defaults, `new(...)` constructor assignment,
    serde field names, and skip-none optional `codex_updated_sha`
    serialization.
- `src/models/task_response.rs`
  - Source-contract coverage for required task fields, optional turn and
    metadata fields, derived defaults, `new(...)` constructor assignment,
    serde field names, skip-none optional serialization, and nested external
    pull request response list decoding.
- `src/models/code_task_details_response.rs`
  - Source-contract coverage for required task details response nesting,
    optional current turn maps, derived defaults, `new(...)` constructor
    assignment, serde field names, skip-none optional serialization, and
    string-keyed JSON-object map handling.
- `src/models/task_list_item.rs`
  - Source-contract coverage for required list item fields, optional title,
    timestamp, status-display, and pull request fields, derived defaults,
    `new(...)` constructor assignment, serde field names, skip-none optional
    serialization, and nested external pull request response list decoding.
- `src/models/paginated_list_task_list_item_.rs`
  - Source-contract coverage for required task list item vector, optional
    cursor, derived defaults, `new(...)` constructor assignment, serde field
    names, skip-none optional cursor serialization, and nested `TaskListItem`
    list decoding.
- `src/models/mod.rs`
  - Source-contract coverage for the curated generated-model module declarations
    and public re-export surface used by the workspace.
- `src/lib.rs`
  - Source-contract coverage for the crate root `pub mod models` surface and
    absence of hand-written root model types.

Python parity coverage:

- `tests/test_codex_backend_openapi_models_additional_rate_limit_details.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_double_option_rate_limit_serialization_states`
  - `test_from_mapping_rejects_non_string_required_fields`
- `tests/test_codex_backend_openapi_models_rate_limit_window_snapshot.py`
  - `test_new_matches_rust_constructor`
  - `test_default_matches_derived_default`
  - `test_json_mapping_uses_rust_serde_field_names`
  - `test_from_mapping_rejects_non_integer_fields`
- `tests/test_codex_backend_openapi_models_rate_limit_status_details.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_double_option_window_serialization_states`
  - `test_from_mapping_rejects_wrong_field_types`
- `tests/test_codex_backend_openapi_models_rate_limit_status_payload.py`
  - `test_plan_type_and_reached_kind_unknown_fallbacks`
  - `test_reached_type_uses_type_field_name`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_double_option_payload_fields_decode_and_serialize`
  - `test_from_mapping_rejects_wrong_field_types`
- `tests/test_codex_backend_openapi_models_credit_status_details.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_double_option_fields_decode_and_serialize`
  - `test_from_mapping_rejects_wrong_field_types`
- `tests/test_codex_backend_openapi_models_config_file_response.py`
  - `test_new_matches_rust_constructor`
  - `test_default_and_serialization_omit_none_fields`
  - `test_from_mapping_uses_rust_serde_field_names`
  - `test_from_mapping_rejects_non_string_optional_fields`
- `tests/test_codex_backend_openapi_models_git_pull_request.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_from_mapping_uses_rust_serde_field_names_and_json_values`
  - `test_from_mapping_rejects_wrong_required_and_optional_types`
- `tests/test_codex_backend_openapi_models_external_pull_request_response.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_from_mapping_uses_rust_serde_field_names`
  - `test_from_mapping_rejects_wrong_field_types`
- `tests/test_codex_backend_openapi_models_task_response.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_from_mapping_uses_rust_serde_field_names`
  - `test_from_mapping_rejects_wrong_field_types`
- `tests/test_codex_backend_openapi_models_code_task_details_response.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_from_mapping_uses_rust_serde_field_names`
  - `test_from_mapping_rejects_wrong_field_types`
- `tests/test_codex_backend_openapi_models_task_list_item.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_from_mapping_uses_rust_serde_field_names`
  - `test_from_mapping_rejects_wrong_field_types`
  - `test_pull_requests_accepts_model_instances`
- `tests/test_codex_backend_openapi_models_paginated_list_task_list_item.py`
  - `test_new_matches_rust_constructor_defaults`
  - `test_default_matches_derived_default`
  - `test_from_mapping_uses_rust_serde_field_names`
  - `test_from_mapping_rejects_wrong_field_types`
  - `test_items_accepts_model_instances`
- `tests/test_codex_backend_openapi_models_models_mod.py`
  - `test_models_namespace_matches_rust_curated_exports`
  - `test_models_namespace_keeps_python_helpers_private_to_python`
- `tests/test_codex_backend_openapi_models_lib.py`
  - `test_crate_root_reexports_models_namespace_only`

Validation:

- `python -m pytest @files`, where `@files` was the PowerShell-expanded list of
  `tests/test_codex_backend_openapi_models*.py`, passed on 2026-06-18 with
  `55 passed`.
