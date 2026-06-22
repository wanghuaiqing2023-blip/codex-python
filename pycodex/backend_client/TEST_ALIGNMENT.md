# pycodex.backend_client Test Alignment

Rust crate: `codex-backend-client`

| Rust source/test | Behavior contract | Python test | Status |
|---|---|---|---|
| `src/types.rs::CodeTaskDetailsResponseExt`, `tests::unified_diff_prefers_current_diff_task_turn`, fixture `task_details_with_diff.json` | Diff extraction prefers `current_diff_task_turn` output-diff content. | `tests/test_backend_client_types_rs.py::test_unified_diff_prefers_current_diff_task_turn` | complete_slice |
| `src/types.rs::CodeTaskDetailsResponseExt`, `tests::unified_diff_falls_back_to_pr_output_diff`, fixture `task_details_with_error.json` | Diff extraction falls back to assistant `pr.output_diff.diff`. | `tests/test_backend_client_types_rs.py::test_unified_diff_falls_back_to_pr_output_diff` | complete_slice |
| `src/types.rs::Turn::message_texts`, `tests::assistant_text_messages_extracts_text_content` | Assistant messages include structured text content and ignore non-text fragments. | `tests/test_backend_client_types_rs.py::test_assistant_text_messages_extracts_text_content` | complete_slice |
| `src/types.rs::Turn::user_prompt`, `tests::user_text_prompt_joins_parts_with_spacing` | User text fragments are joined by blank lines. | `tests/test_backend_client_types_rs.py::test_user_text_prompt_joins_parts_with_spacing` | complete_slice |
| `src/types.rs::TurnError::summary`, `tests::assistant_error_message_combines_code_and_message` | Assistant error summary combines code and message with `": "`. | `tests/test_backend_client_types_rs.py::test_assistant_error_message_combines_code_and_message` | complete_slice |
| `src/client.rs::Client::map_plan_type`, `tests::map_plan_type_supports_usage_based_business_variants` | Backend plan variants map to protocol account plan variants, with unknown-like variants collapsed. | `tests/test_backend_client_client_rs.py::test_map_plan_type_supports_usage_based_business_variants_and_unknowns` | complete_slice |
| `src/client.rs::rate_limit_snapshots_from_payload`, `tests::usage_payload_maps_primary_and_additional_rate_limits` | Primary, secondary, credit, plan, reached-type, and additional-rate-limit fields map into protocol snapshots. | `tests/test_backend_client_client_rs.py::test_usage_payload_maps_primary_and_additional_rate_limits` | complete_slice |
| `src/client.rs::rate_limit_snapshots_from_payload`, `tests::usage_payload_maps_zero_rate_limit_when_primary_absent` | Missing primary rate limit still produces the codex snapshot and additional empty snapshot. | `tests/test_backend_client_client_rs.py::test_usage_payload_maps_zero_rate_limit_when_primary_absent` | complete_slice |
| `src/client.rs::get_rate_limits`, `tests::preferred_snapshot_selection_matches_get_rate_limits_behavior` | Preferred snapshot selection chooses `limit_id == "codex"` or falls back to first. | `tests/test_backend_client_client_rs.py::test_preferred_snapshot_selection_matches_get_rate_limits_behavior` | complete_slice |
| `src/client.rs::map_rate_limit_reached_type`, `tests::usage_payload_maps_every_rate_limit_reached_type` | Backend reached-kind values map to protocol reached-type values; unknown maps to `None`. | `tests/test_backend_client_client_rs.py::test_usage_payload_maps_every_rate_limit_reached_type` | complete_slice |
| `src/client.rs::send_add_credits_nudge_email_url`, `tests::add_credits_nudge_email_uses_expected_paths_and_bodies` | Codex/ChatGPT path styles and add-credits request bodies match Rust serde shape. | `tests/test_backend_client_client_rs.py::test_add_credits_nudge_email_uses_expected_paths_and_bodies` | complete_slice |
| `src/client.rs::{get_rate_limits_many,list_tasks,get_task_details_with_body,list_sibling_turns,get_config_requirements_file,create_task}` | Codex/ChatGPT endpoint path styles and list-task query insertion order match Rust request construction. | `tests/test_backend_client_client_rs.py::test_endpoint_url_helpers_match_client_path_style_contract` | complete_slice |
| `src/client.rs::create_task` | Successful create-task response extracts nested `task.id` before falling back to top-level `id`, and reports decode/no-id errors with URL/content-type/body context. | `tests/test_backend_client_client_rs.py::test_create_task_id_from_response_prefers_task_id_then_top_level_id` | complete_slice |
| `src/client.rs::{exec_request,exec_request_detailed,decode_json}` | Endpoint methods execute through a transport boundary, attach JSON content type/body for POSTs, decode typed JSON, and preserve detailed non-2xx errors. | `tests/test_backend_client_client_rs.py::test_client_endpoint_methods_execute_through_injected_transport`, `tests/test_backend_client_client_rs.py::test_exec_request_error_and_decode_error_context_match_rust` | complete_slice |
| `src/client.rs::{exec_request_detailed,get_rate_limits_many,create_task}` | Default transport performs real local HTTP, preserves non-2xx status/content-type/body, and sends compact JSON request bodies. | `tests/test_backend_client_client_rs.py::test_default_stdlib_transport_uses_real_local_http_and_preserves_error_body` | complete_slice |
| `src/client.rs::headers`, `codex-api::AuthProvider::add_auth_headers` | Auth provider headers are added after user-agent and before explicit account/FedRAMP overrides, preserving HeaderMap-style case-insensitive replacement. | `tests/test_backend_client_client_rs.py::test_auth_provider_headers_are_applied_before_explicit_account_overrides` | complete_slice |
| `src/client.rs` endpoint methods and `headers` | Endpoint requests pass auth-provider headers through to the transport. | `tests/test_backend_client_client_rs.py::test_auth_provider_headers_are_visible_to_transport` | complete_slice |
| `src/client.rs::Client::new`, `codex-client::with_chatgpt_cloudflare_cookie_store` | ChatGPT Cloudflare cookies are stored and replayed through the backend-client transport hook. | `tests/test_backend_client_client_rs.py::test_chatgpt_cloudflare_cookie_store_is_applied_to_transport_requests` | complete_slice |
| `src/client.rs::Client::new`, `codex-client::build_reqwest_client_with_custom_ca` | HTTPS standard-library transport selects the configured Codex custom CA bundle for SSL context creation. | `tests/test_backend_client_client_rs.py::test_stdlib_transport_uses_custom_ca_bundle_for_https_ssl_context` | complete_slice |
| `src/client.rs::Client::new`, `PathStyle::from_base_url`, `headers` | ChatGPT hosts normalize to `/backend-api`, path style derives from base URL, and default headers include `codex-cli`. | `tests/test_backend_client_client_rs.py::test_client_new_normalizes_chatgpt_urls_and_headers` | complete_slice |
| `src/client.rs::RequestError` | Unexpected status display includes method, URL, status, content type, and body; unauthorized recognizes 401. | `tests/test_backend_client_client_rs.py::test_request_error_display_and_unauthorized_match_rust` | complete_slice |

## Validation

2026-06-22:

- `python -m pytest tests\test_backend_client_types_rs.py tests\test_backend_client_client_rs.py -q --tb=short`
  - `24 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_backend_client_types_rs.py tests\test_backend_client_client_rs.py -q --tb=short`
  - `25 passed`
- `python -m unittest tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs -v`
  - `24 tests`
- `python -m py_compile pycodex\backend_client\__init__.py tests\test_backend_client_types_rs.py tests\test_backend_client_client_rs.py`
  - passed

## Implementation Notes

- Python uses dependency-light standard-library/injected HTTP transport rather than native async `reqwest`.
- Custom CA and ChatGPT Cloudflare cookie behavior are delegated to completed `pycodex.codex_client` contracts.
