# codex-login test alignment

Rust crate: `codex-login`

Python package: `pycodex/login`

Status: `complete_candidate`

Certified modules:

- `codex/codex-rs/login/src/lib.rs` -> `pycodex/login/__init__.py`
- `codex/codex-rs/login/src/auth/mod.rs` -> `pycodex/login/auth/__init__.py`
- `codex/codex-rs/login/src/auth/manager.rs` -> `pycodex/login/auth/manager.py`
- `codex/codex-rs/login/src/auth_env_telemetry.rs` -> `pycodex/login/auth_env_telemetry.py`
- `codex/codex-rs/login/src/auth/agent_identity.rs` -> `pycodex/login/auth/agent_identity.py`
- `codex/codex-rs/login/src/auth/default_client.rs` -> `pycodex/login/auth/default_client.py`
- `codex/codex-rs/login/src/auth/error.rs` -> `pycodex/login/auth/error.py`
- `codex/codex-rs/login/src/auth/external_bearer.rs` -> `pycodex/login/auth/external_bearer.py`
- `codex/codex-rs/login/src/auth/revoke.rs` -> `pycodex/login/auth/revoke.py`
- `codex/codex-rs/login/src/auth/storage.rs` -> `pycodex/login/auth/storage.py`
- `codex/codex-rs/login/src/auth/util.rs` -> `pycodex/login/auth/util.py`
- `codex/codex-rs/login/src/device_code_auth.rs` -> `pycodex/login/device_code_auth.py`
- `codex/codex-rs/login/src/pkce.rs` -> `pycodex/login/pkce.py`
- `codex/codex-rs/login/src/server.rs` -> `pycodex/login/server.py`
- `codex/codex-rs/login/src/token_data.rs` -> `pycodex/login/token_data.py`

Remaining Rust modules:

- None.

Rust tests and fixtures for certified modules:

- `codex/codex-rs/login/src/lib.rs`
  - Source-contract coverage for crate-root module declarations and public
    re-exports of completed child modules; `src/server.rs` and
    `src/auth/manager.rs` remain separate pending modules.
- `codex/codex-rs/login/src/auth/mod.rs`
  - Source-contract coverage for auth subtree declarations and package-level
    re-exports of completed child modules, including the manager module.
- `codex/codex-rs/login/src/auth/manager.rs`
  - Source-contract coverage for auth mode constants, `CodexAuth` variants and
    account/token accessors, trim-and-ignore-empty environment credential
    lookup, login/logout/save/load helpers, `AuthConfig` restrictions,
    refresh-token failure classification, endpoint override selection,
    external ChatGPT token conversion, `AuthManager` cached reload behavior,
    external API-key resolution compatibility, and unauthorized recovery step
    routing.
- `codex/codex-rs/login/src/auth_env_telemetry.rs`
  - `collect_auth_env_telemetry_buckets_provider_env_key_name`
- `codex/codex-rs/login/src/token_data_tests.rs`
  - `id_token_info_parses_email_and_plan`
  - `id_token_info_parses_go_plan`
  - `id_token_info_parses_hc_plan_as_enterprise`
  - `id_token_info_parses_usage_based_business_plans`
  - `id_token_info_handles_missing_fields`
  - `id_token_info_parses_fedramp_account_claim`
  - `jwt_expiration_parses_exp_claim`
  - `jwt_expiration_handles_missing_exp`
  - `jwt_expiration_rejects_malformed_jwt`
  - `workspace_account_detection_matches_workspace_plans`
- `codex/codex-rs/login/src/auth/util.rs`
  - `try_parse_error_message_extracts_openai_error_message`
  - `try_parse_error_message_falls_back_to_raw_text`
- `codex/codex-rs/login/src/auth/error.rs`
  - Pure re-export of `RefreshTokenFailedError` and `RefreshTokenFailedReason`
- `codex/codex-rs/login/src/auth/agent_identity.rs`
  - `agent_identity_authapi_base_url_prefers_env_value`
  - `agent_identity_authapi_base_url_uses_prod_authapi_by_default`
- `codex/codex-rs/login/src/auth/default_client_tests.rs`
  - `test_get_codex_user_agent`
  - `is_first_party_originator_matches_known_values`
  - `is_first_party_chat_originator_matches_known_values`
  - `test_create_client_sets_default_headers`
  - `test_invalid_suffix_is_sanitized`
  - `test_invalid_suffix_is_sanitized2`
  - `test_macos`
- `codex/codex-rs/login/src/auth/external_bearer.rs`
  - Source-contract coverage for provider command execution, token caching,
    forced refresh, timeout/error reporting, and command path resolution.
- `codex/codex-rs/login/src/auth/storage_tests.rs`
  - `file_storage_load_returns_auth_dot_json`
  - `file_storage_save_persists_auth_dot_json`
  - `file_storage_round_trips_agent_identity_auth`
  - `file_storage_loads_agent_identity_as_jwt`
  - `file_storage_delete_removes_auth_file`
  - `ephemeral_storage_save_load_delete_is_in_memory_only`
  - `keyring_auth_storage_load_returns_deserialized_auth`
  - `keyring_auth_storage_compute_store_key_for_home_directory`
  - `keyring_auth_storage_save_persists_and_removes_fallback_file`
  - `keyring_auth_storage_delete_removes_keyring_and_file`
  - `auto_auth_storage_load_prefers_keyring_value`
  - `auto_auth_storage_load_uses_file_when_keyring_empty`
  - `auto_auth_storage_load_falls_back_when_keyring_errors`
  - `auto_auth_storage_save_prefers_keyring`
  - `auto_auth_storage_save_falls_back_when_keyring_errors`
  - `auto_auth_storage_delete_removes_keyring_and_file`
- `codex/codex-rs/login/src/auth/revoke.rs`
  - `derives_revoke_url_from_refresh_token_override`
  - `revoke_request_times_out`
  - Source-contract coverage for token selection, managed ChatGPT filtering,
    replacement revoke decisions, endpoint override precedence, request payload
    shape, and failed response formatting.
- `codex/codex-rs/login/src/pkce.rs`
  - Source-contract coverage for 64-byte verifier randomness, URL-safe no-pad
    base64 encoding, S256 challenge derivation, and CLI compatibility reuse.
- `codex/codex-rs/login/src/device_code_auth.rs`
  - Source-contract coverage for user-code request payloads, response aliases,
    interval parsing, 404 not-enabled errors, token polling success/retry/timeout
    behavior, prompt text, verification URL derivation, and CLI compatibility
    reuse.
- `codex/codex-rs/login/src/server.rs`
  - `persist_tokens_async_revokes_previous_auth_without_failing_login`
  - `persist_tokens_async_does_not_revoke_reused_refresh_token`
  - `parse_token_endpoint_error_prefers_error_description`
  - `parse_token_endpoint_error_reads_nested_error_message_and_code`
  - `parse_token_endpoint_error_falls_back_to_error_code`
  - `parse_token_endpoint_error_preserves_plain_text_for_display`
  - `redact_sensitive_query_value_only_scrubs_known_keys`
  - `redact_sensitive_url_parts_preserves_safe_url_shape`
  - `sanitize_url_for_logging_redacts_sensitive_issuer_parts`
  - `compose_success_url_omits_streamlined_success_by_default`
  - `compose_success_url_includes_streamlined_success_when_requested`
  - `render_login_error_page_escapes_dynamic_fields`
  - `render_login_error_page_uses_entitlement_copy`
  - Source-contract coverage for server options, login server handles,
    authorization URL construction, callback handling, token exchange,
    workspace restriction checks, and device-code callback reuse.

Python parity coverage:

- `tests/test_login_lib_rs.py`
  - `test_login_root_reexports_completed_child_modules`
  - `test_login_root_all_contains_completed_crate_root_exports`
- `tests/test_login_auth_mod.py`
  - `test_auth_package_reexports_completed_child_module_contracts`
  - `test_auth_package_all_matches_completed_public_surface`
- `tests/test_login_auth_manager.py`
  - `test_env_key_readers_trim_and_ignore_blank_values`
  - `test_resolved_and_storage_mode_match_auth_dot_json_rules`
  - `test_login_with_api_key_overwrites_file_auth`
  - `test_refresh_token_error_classification_matches_rust_codes`
  - `test_refresh_token_endpoint_prefers_override`
  - `test_external_chatgpt_tokens_require_metadata_and_build_auth_json`
  - `test_load_auth_prefers_codex_api_key_env_over_storage`
  - `test_auth_manager_reload_tracks_changed_auth`
  - `test_enforce_login_restrictions_logs_out_wrong_mode`
  - `test_codex_auth_chatgpt_accessors`
- `tests/test_login_auth_env_telemetry.py`
  - `test_env_var_present_matches_rust_presence_rules`
  - `test_env_var_present_treats_non_unicode_lookup_as_present`
  - `test_collect_auth_env_telemetry_buckets_provider_env_key_name`
  - `test_collect_auth_env_telemetry_without_provider_key`
  - `test_auth_env_telemetry_to_otel_metadata_preserves_fields`
- `tests/test_login_token_data.py`
  - `test_id_token_info_parses_email_and_plan`
  - `test_id_token_info_parses_alias_and_usage_based_workspace_plans`
  - `test_id_token_info_handles_missing_fields_and_profile_email`
  - `test_id_token_info_parses_user_account_and_fedramp_claims`
  - `test_jwt_expiration_parses_exp_and_missing_exp`
  - `test_jwt_expiration_rejects_malformed_jwt`
  - `test_workspace_account_detection_matches_workspace_plans`
  - `test_token_data_mapping_serializes_id_token_as_raw_jwt`
- `tests/test_login_auth_util.py`
  - `test_try_parse_error_message_extracts_openai_error_message`
  - `test_try_parse_error_message_falls_back_to_raw_text`
  - `test_try_parse_error_message_falls_back_for_invalid_json`
  - `test_try_parse_error_message_empty_text_is_unknown_error`
  - `test_try_parse_error_message_requires_nested_string_message`
- `tests/test_login_auth_error.py`
  - `test_login_auth_error_reexports_protocol_refresh_failure_types`
  - `test_login_auth_error_preserves_protocol_error_behavior`
- `tests/test_login_agent_identity.py`
  - `test_agent_identity_authapi_base_url_prefers_trimmed_env_value`
  - `test_agent_identity_authapi_base_url_uses_prod_by_default`
  - `test_key_maps_record_runtime_id_and_private_key`
  - `test_agent_identity_auth_load_uses_callable_registrar_and_exposes_record_fields`
  - `test_agent_identity_auth_load_accepts_method_registrar_and_awaitable_result`
  - `test_agent_identity_auth_load_requires_registration_backend`
  - `test_agent_identity_auth_load_rejects_invalid_registrar`
- `tests/test_login_default_client.py`
  - `test_get_codex_user_agent_starts_with_originator_prefix`
  - `test_default_client_module_is_reexported_from_login_surfaces`
  - `test_is_first_party_originator_matches_known_values`
  - `test_is_first_party_chat_originator_matches_known_values`
  - `test_invalid_suffix_is_sanitized`
  - `test_originator_prefers_env_override_and_caches_it`
  - `test_set_default_originator_uses_provided_value_and_rejects_second_init`
  - `test_set_default_originator_rejects_invalid_header_value`
  - `test_env_originator_override_wins_over_provided_originator`
  - `test_default_headers_include_originator_user_agent_and_residency`
  - `test_create_client_sets_default_headers_and_sandbox_policy`
- `tests/test_login_external_bearer.py`
  - `test_resolve_provider_auth_program_matches_rust_path_rules`
  - `test_run_provider_auth_command_trims_stdout`
  - `test_run_provider_auth_command_rejects_empty_token`
  - `test_run_provider_auth_command_reports_stderr_for_nonzero_exit`
  - `test_run_provider_auth_command_reports_non_utf8_stdout`
  - `test_run_provider_auth_command_times_out`
  - `test_bearer_token_refresher_caches_and_refresh_forces_command`
  - `test_bearer_token_refresher_zero_refresh_interval_never_expires_cache`
  - `test_bearer_token_refresher_expired_cache_refetches`
- `tests/test_login_auth_storage.py`
  - `test_get_auth_file_and_delete_file_if_exists`
  - `test_file_storage_save_load_and_json_shape`
  - `test_file_storage_load_missing_returns_none`
  - `test_file_storage_loads_agent_identity_jwt_as_record`
  - `test_ephemeral_storage_save_load_delete_is_in_memory_only`
  - `test_keyring_auth_storage_compute_store_key_for_home_directory`
  - `test_keyring_auth_storage_load_returns_deserialized_auth`
  - `test_keyring_auth_storage_save_persists_and_removes_fallback_file`
  - `test_keyring_auth_storage_delete_removes_keyring_and_file`
  - `test_auto_auth_storage_load_prefers_keyring_value`
  - `test_auto_auth_storage_load_uses_file_when_keyring_empty`
  - `test_auto_auth_storage_load_falls_back_when_keyring_errors`
  - `test_auto_auth_storage_save_prefers_keyring`
  - `test_auto_auth_storage_save_falls_back_when_keyring_errors`
  - `test_create_auth_storage_selects_backends`
  - `test_keyring_auth_storage_load_wraps_keyring_errors`
  - `test_keyring_auth_storage_load_wraps_deserialize_errors`
  - `test_keyring_auth_storage_save_wraps_keyring_errors`
- `tests/test_login_auth_revoke.py`
  - `test_resolved_auth_mode_matches_rust_defaulting_rules`
  - `test_managed_chatgpt_tokens_filters_non_chatgpt_auth`
  - `test_revocable_token_prefers_refresh_then_access`
  - `test_should_revoke_auth_tokens_matches_replacement_rules`
  - `test_derive_revoke_url_from_refresh_token_override`
  - `test_revoke_token_endpoint_override_precedence`
  - `test_revoke_oauth_token_sends_refresh_payload_with_client_id`
  - `test_revoke_oauth_token_sends_access_payload_without_client_id`
  - `test_revoke_oauth_token_wraps_error_message`
  - `test_revoke_auth_tokens_is_noop_without_revocable_token`
  - `test_revoke_auth_tokens_uses_selected_refresh_token`
- `tests/test_login_pkce.py`
  - `test_code_challenge_for_verifier_matches_rust_s256_contract`
  - `test_generate_pkce_uses_64_random_bytes_and_no_padding`
  - `test_cli_build_pkce_reuses_login_pkce_module`
- `tests/test_login_device_code_auth.py`
  - `test_deserialize_interval_matches_rust_string_parser`
  - `test_request_user_code_posts_client_id_and_accepts_usercode_alias`
  - `test_request_user_code_404_is_not_enabled`
  - `test_request_user_code_rejects_missing_user_code`
  - `test_poll_for_token_returns_authorization_code_and_pkce`
  - `test_poll_for_token_retries_on_forbidden_then_succeeds`
  - `test_poll_for_token_times_out_after_max_wait`
  - `test_print_device_code_prompt_contains_url_code_and_warning`
  - `test_request_device_code_derives_api_base_and_verification_url`
- `tests/test_login_server.py`
  - `test_server_options_new_matches_rust_defaults`
  - `test_build_authorize_url_includes_pkce_state_scope_and_workspace`
  - `test_parse_token_endpoint_error_matches_rust_precedence`
  - `test_sensitive_url_redaction_preserves_safe_shape`
  - `test_compose_success_url_and_workspace_restriction`
  - `test_login_error_page_escapes_dynamic_fields_and_entitlement_copy`

Validation:

- `python -m pytest @files -q` over PowerShell-expanded
  `tests/test_login_*.py` passed with `108 passed`.
- `python -m py_compile pycodex/login/auth/manager.py
  pycodex/login/auth/__init__.py pycodex/login/__init__.py
  tests/test_login_auth_manager.py` passed.
