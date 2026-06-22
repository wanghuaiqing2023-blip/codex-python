# pycodex.network_proxy Test Alignment

Rust crate: `codex-network-proxy`
Rust path: `codex/codex-rs/network-proxy`

## Status

`module_progress`

`src/config.rs`, `src/state.rs`, `src/policy.rs`, `src/network_policy.rs`,
`src/reasons.rs`, `src/responses.rs`, `src/connect_policy.rs`,
`src/upstream.rs`, the `src/runtime.rs` blocked-request buffer,
host policy/local/scoped-IP guard, DNS/private-address guard, dynamic domain mutation, unix-socket/accessor, and reload slices, the `src/http_proxy.rs`
absolute-form/header helper, `json_blocked` response shape helper, CONNECT accept policy, live CONNECT listener/direct-tunnel/upstream-proxy route, plain HTTP unix-socket preflight, plain HTTP host/policy/method preflight, and live plain HTTP direct/upstream-proxy forwarding slices, the `src/proxy.rs` environment override
helper slice, and `src/mitm_hook.rs` are complete under the dependency-light
Python port. The `src/mitm.rs` policy/action slice is also covered, the
`src/socks5.rs` policy/inspection, live TCP no-auth CONNECT relay, and live UDP ASSOCIATE/relay slices are covered, and the `src/certs.rs`
managed CA file-safety slice is covered. The `src/proxy.rs`
builder/runtime-settings/stdlib task startup/handle wait/shutdown/drop slice is also covered. The crate still has open runtime
modules for live proxy operation, MITM TLS termination, native SOCKS
listener/upstream runtime identity, native tokio/Rama task identity, and certificate
generation/rustls acceptor handling.

## Rust-Derived Tests

| Rust module | Rust tests/contracts | Python tests | Status |
|---|---|---|---|
| `src/config.rs` | `network_proxy_settings_default_matches_local_use_baseline` | `tests/test_network_proxy_config_rs.py::test_network_proxy_settings_default_matches_local_use_baseline` | complete |
| `src/config.rs` | `partial_network_config_uses_struct_defaults_for_missing_fields` | `tests/test_network_proxy_config_rs.py::test_partial_network_config_uses_struct_defaults_for_missing_fields` | complete |
| `src/config.rs` | `set_allowed_domains_preserves_existing_deny_for_same_pattern` | `tests/test_network_proxy_config_rs.py::test_set_allowed_domains_preserves_existing_deny_for_same_pattern` | complete |
| `src/config.rs` | `network_domain_permissions_serialize_to_effective_map_shape` | `tests/test_network_proxy_config_rs.py::test_network_domain_permissions_serialize_to_effective_map_shape` | complete |
| `src/config.rs` | `parse_host_port_*`, `host_and_port_from_network_addr_*` | `tests/test_network_proxy_config_rs.py::test_host_and_port_from_network_addr_matches_rust_parse_cases` | complete |
| `src/config.rs` | `resolve_addr_*`, `clamp_bind_addrs_*` | `tests/test_network_proxy_config_rs.py::test_resolve_runtime_clamps_non_loopback_unless_dangerously_allowed`, `tests/test_network_proxy_config_rs.py::test_resolve_runtime_forces_loopback_when_unix_sockets_enabled` | complete |
| `src/config.rs` | `resolve_runtime_rejects_relative_allow_unix_sockets_entries`, `resolve_runtime_accepts_unix_style_absolute_allow_unix_sockets_entries` | `tests/test_network_proxy_config_rs.py::test_resolve_runtime_rejects_relative_allow_unix_sockets_entries`, `tests/test_network_proxy_config_rs.py::test_resolve_runtime_accepts_unix_style_absolute_allow_unix_sockets_entries` | complete |
| `src/config.rs` | `NetworkProxySettings::upsert_domain_permission` source contract | `tests/test_network_proxy_config_rs.py::test_upsert_domain_permission_removes_normalized_opposite_entries` | complete |
| `src/state.rs` | `validate_policy_against_constraints_*` tests called from `src/runtime.rs::tests` | `tests/test_network_proxy_state_rs.py` | complete |
| `src/state.rs` | `build_config_state` source contract | `tests/test_network_proxy_state_rs.py::test_build_config_state_validates_relative_unix_socket_and_denied_global_wildcard` | complete |
| `src/runtime.rs`, `src/state.rs` | `build_config_state_allows_global_wildcard_allowed_domains` | `tests/test_network_proxy_state_rs.py::test_build_config_state_allows_global_wildcard_allowed_domains` | complete |
| `src/runtime.rs`, `src/state.rs` | `build_config_state_allows_bracketed_global_wildcard_allowed_domains` | `tests/test_network_proxy_state_rs.py::test_build_config_state_allows_bracketed_global_wildcard_allowed_domains` | complete |
| `src/runtime.rs`, `src/state.rs` | `build_config_state_rejects_global_wildcard_denied_domains`, `build_config_state_rejects_bracketed_global_wildcard_denied_domains` | `tests/test_network_proxy_state_rs.py::test_build_config_state_rejects_global_wildcard_denied_domains` | complete |
| `src/policy.rs` | `method_allowed_*` | `tests/test_network_proxy_policy_rs.py::test_method_allowed_full_allows_everything`, `tests/test_network_proxy_policy_rs.py::test_method_allowed_limited_allows_only_safe_methods` | complete |
| `src/policy.rs` | `compile_globset_*` | `tests/test_network_proxy_policy_rs.py::test_compile_globset_normalizes_trailing_dots`, `test_compile_globset_normalizes_wildcards`, `test_compile_globset_supports_mid_label_wildcards`, `test_compile_globset_normalizes_apex_and_subdomains`, `test_compile_globset_normalizes_bracketed_ipv6_literals`, `test_compile_globset_preserves_scoped_ipv6_literals` | complete |
| `src/policy.rs` | `is_loopback_host_*`, `is_non_public_ip_rejects_private_and_loopback_ranges` | `tests/test_network_proxy_policy_rs.py::test_is_loopback_host_handles_localhost_variants`, `test_is_loopback_host_handles_ip_literals`, `test_is_non_public_ip_rejects_private_loopback_and_reserved_ranges`, `test_is_non_public_ip_allows_public_ranges` | complete |
| `src/policy.rs` | `normalize_host_*` | `tests/test_network_proxy_policy_rs.py::test_normalize_host_matches_rust_policy_cases` | complete |
| `src/policy.rs` | global wildcard allow/deny compilation source contract | `tests/test_network_proxy_policy_rs.py::test_compile_denylist_rejects_global_wildcard_but_allowlist_accepts_it` | complete |
| `src/runtime.rs`, `src/policy.rs` | `compile_globset_is_case_insensitive` | `tests/test_network_proxy_policy_rs.py::test_runtime_compile_globset_is_case_insensitive` | complete |
| `src/runtime.rs`, `src/policy.rs` | `compile_globset_excludes_apex_for_subdomain_patterns`, `compile_globset_includes_apex_for_double_wildcard_patterns` | `tests/test_network_proxy_policy_rs.py::test_runtime_compile_globset_wildcard_boundaries` | complete |
| `src/runtime.rs`, `src/policy.rs` | `compile_globset_rejects_bracketed_global_wildcard`, `compile_globset_rejects_double_wildcard_bracketed_global_wildcard` | `tests/test_network_proxy_policy_rs.py::test_runtime_compile_globset_rejects_bracketed_global_wildcards` | complete |
| `src/runtime.rs`, `src/policy.rs` | `compile_globset_dedupes_patterns_without_changing_behavior` | `tests/test_network_proxy_policy_rs.py::test_runtime_compile_globset_dedupes_patterns_without_changing_behavior` | complete |
| `src/runtime.rs`, `src/policy.rs` | `compile_globset_rejects_invalid_patterns` | `tests/test_network_proxy_policy_rs.py::test_runtime_compile_globset_rejects_invalid_patterns` | complete |
| `src/network_policy.rs` | `evaluate_host_policy_emits_domain_event_for_decider_allow_override` | `tests/test_network_proxy_network_policy_rs.py::test_evaluate_host_policy_emits_domain_event_for_decider_allow_override` | complete |
| `src/network_policy.rs` | `evaluate_host_policy_emits_domain_event_for_baseline_deny` | `tests/test_network_proxy_network_policy_rs.py::test_evaluate_host_policy_emits_domain_event_for_baseline_deny` | complete |
| `src/network_policy.rs` | `evaluate_host_policy_emits_domain_event_for_decider_ask` | `tests/test_network_proxy_network_policy_rs.py::test_evaluate_host_policy_emits_domain_event_for_decider_ask` | complete |
| `src/network_policy.rs` | `evaluate_host_policy_emits_metadata_fields` | `tests/test_network_proxy_network_policy_rs.py::test_evaluate_host_policy_emits_metadata_fields` | complete |
| `src/network_policy.rs` | `emit_block_decision_audit_event_emits_non_domain_event` | `tests/test_network_proxy_network_policy_rs.py::test_emit_block_decision_audit_event_emits_non_domain_event` | complete |
| `src/network_policy.rs` | `evaluate_host_policy_still_denies_not_allowed_local_without_decider_override` | `tests/test_network_proxy_network_policy_rs.py::test_evaluate_host_policy_still_denies_not_allowed_local_without_decider_override` | complete |
| `src/network_policy.rs` | `ask_uses_decider_source_and_ask_decision` | `tests/test_network_proxy_network_policy_rs.py::test_ask_uses_decider_source_and_ask_decision` | complete |
| `src/reasons.rs` | `REASON_*` source constants | `tests/test_network_proxy_reasons_rs.py::test_reason_constants_match_rust_reasons_rs` | complete |
| `src/runtime.rs`, `src/reasons.rs` | `HostBlockReason::as_str` source contract | `tests/test_network_proxy_reasons_rs.py::test_host_block_reason_as_str_uses_reasons_rs_constants` | complete |
| `src/responses.rs` | `blocked_message_with_policy_returns_human_message` | `tests/test_network_proxy_responses_rs.py::test_blocked_message_with_policy_returns_human_message` | complete |
| `src/responses.rs` | `blocked_header_value` source contract | `tests/test_network_proxy_responses_rs.py::test_blocked_header_value_maps_reason_categories` | complete |
| `src/responses.rs` | `blocked_message` source contract | `tests/test_network_proxy_responses_rs.py::test_blocked_message_maps_reason_text` | complete |
| `src/responses.rs` | `blocked_text_response`, `blocked_text_response_with_policy` source contract | `tests/test_network_proxy_responses_rs.py::test_blocked_text_response_shape_matches_rust` | complete |
| `src/responses.rs` | `text_response`, `json_response` source contract | `tests/test_network_proxy_responses_rs.py::test_text_and_json_response_shape_matches_rust_helpers` | complete |
| `src/connect_policy.rs` | `direct_connector_rejects_non_public_target_when_local_binding_disabled` | `tests/test_network_proxy_connect_policy_rs.py::test_direct_connector_rejects_non_public_target_when_local_binding_disabled` | complete |
| `src/connect_policy.rs` | `direct_connector_allows_non_public_target_when_local_binding_enabled` | `tests/test_network_proxy_connect_policy_rs.py::test_direct_connector_allows_non_public_target_when_local_binding_enabled` | complete |
| `src/connect_policy.rs` | `TargetCheckedTcpConnector::serve` proxy-address bypass source contract | `tests/test_network_proxy_connect_policy_rs.py::test_proxy_address_bypasses_direct_target_policy_projection` | complete |
| `src/upstream.rs` | `read_proxy_env` source contract | `tests/test_network_proxy_upstream_rs.py::test_read_proxy_env_uses_first_non_empty_valid_http_proxy`, `tests/test_network_proxy_upstream_rs.py::test_read_proxy_env_ignores_non_http_and_invalid_proxy_values` | complete |
| `src/upstream.rs` | `ProxyConfig::proxy_for_protocol` source contract | `tests/test_network_proxy_upstream_rs.py::test_proxy_config_protocol_selection_matches_rust_priority` | complete |
| `src/upstream.rs` | `proxy_for_connect` source contract | `tests/test_network_proxy_upstream_rs.py::test_proxy_for_connect_uses_secure_proxy_selection_from_env` | complete |
| `src/upstream.rs` | `UpstreamClient` constructor and route-selection source contracts | `tests/test_network_proxy_upstream_rs.py::test_upstream_client_constructors_capture_proxy_config_and_target_policy`, `tests/test_network_proxy_upstream_rs.py::test_upstream_client_select_route_projects_rust_proxy_insertion_decision`, `tests/test_network_proxy_upstream_rs.py::test_upstream_client_unix_socket_constructor_uses_direct_proxy_config` | complete |
| `src/runtime.rs` | `blocked_snapshot_does_not_consume_entries` | `tests/test_network_proxy_runtime_blocked_rs.py::test_blocked_snapshot_does_not_consume_entries` | complete |
| `src/runtime.rs` | `drain_blocked_returns_buffered_window` | `tests/test_network_proxy_runtime_blocked_rs.py::test_drain_blocked_returns_buffered_window` | complete |
| `src/runtime.rs` | `blocked_request_violation_log_line_serializes_payload` | `tests/test_network_proxy_runtime_blocked_rs.py::test_blocked_request_violation_log_line_serializes_payload` | complete |
| `src/runtime.rs` | `BlockedRequest` serde skip-field source contract | `tests/test_network_proxy_runtime_blocked_rs.py::test_blocked_request_to_mapping_skips_only_rust_skip_serializing_fields` | complete |
| `src/runtime.rs` | `BlockedRequestObserver`, `NetworkProxyState::record_blocked` source contract | `tests/test_network_proxy_runtime_blocked_rs.py::test_record_blocked_notifies_observer_with_original_entry` | complete |
| `src/runtime.rs` | `host_blocked_rejects_allowlisted_hostname_when_dns_lookup_fails` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_rejects_allowlisted_hostname_when_dns_lookup_fails` | complete |
| `src/runtime.rs` | `host_resolves_to_non_public_ip_blocks_on_dns_lookup_timeout` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_resolves_to_non_public_ip_blocks_on_dns_lookup_timeout` | complete |
| `src/runtime.rs` | `host_resolves_to_non_public_ip_blocks_on_dns_lookup_error` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_resolves_to_non_public_ip_blocks_on_dns_lookup_error` | complete |
| `src/runtime.rs` | `host_resolves_to_non_public_ip_blocks_private_resolution` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_resolves_to_non_public_ip_blocks_private_resolution` | complete |
| `src/runtime.rs` | `host_resolves_to_non_public_ip_allows_public_resolution` and final `host_blocked` allow branch source contract | `tests/test_network_proxy_runtime_dns_rs.py::test_host_resolves_to_non_public_ip_allows_public_resolution`, `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_allows_allowlisted_hostname_with_public_dns_resolution` | complete |
| `src/runtime.rs` | `add_allowed_domain_removes_matching_deny_entry` | `tests/test_network_proxy_runtime_domains_rs.py::test_add_allowed_domain_removes_matching_deny_entry` | complete |
| `src/runtime.rs` | `add_denied_domain_removes_matching_allow_entry` | `tests/test_network_proxy_runtime_domains_rs.py::test_add_denied_domain_removes_matching_allow_entry` | complete |
| `src/runtime.rs` | `add_denied_domain_forces_block_with_global_wildcard_allowlist` | `tests/test_network_proxy_runtime_domains_rs.py::test_add_denied_domain_forces_block_with_global_wildcard_allowlist` | complete |
| `src/runtime.rs` | `add_allowed_domain_succeeds_when_managed_baseline_allows_expansion` | `tests/test_network_proxy_runtime_domains_rs.py::test_add_allowed_domain_succeeds_when_managed_baseline_allows_expansion` | complete |
| `src/runtime.rs` | `add_allowed_domain_rejects_expansion_when_managed_baseline_is_fixed` | `tests/test_network_proxy_runtime_domains_rs.py::test_add_allowed_domain_rejects_expansion_when_managed_baseline_is_fixed` | complete |
| `src/runtime.rs` | `add_denied_domain_rejects_expansion_when_managed_baseline_is_fixed` | `tests/test_network_proxy_runtime_domains_rs.py::test_add_denied_domain_rejects_expansion_when_managed_baseline_is_fixed` | complete |
| `src/proxy.rs`, `src/runtime.rs` | `NetworkProxy::add_allowed_domain` facade source contract | `tests/test_network_proxy_runtime_domains_rs.py::test_network_proxy_add_allowed_domain_forwards_to_state` | complete |
| `src/runtime.rs` | `unix_socket_allowlist_is_rejected_on_non_macos` | `tests/test_network_proxy_runtime_accessors_rs.py::test_unix_socket_allowlist_is_rejected_when_platform_not_supported` | complete |
| `src/runtime.rs` | `unix_socket_allowlist_is_respected_on_macos` | `tests/test_network_proxy_runtime_accessors_rs.py::test_unix_socket_allowlist_is_respected_when_supported` | complete |
| `src/runtime.rs` | `unix_socket_allowlist_resolves_symlinks` | `tests/test_network_proxy_runtime_accessors_rs.py::test_unix_socket_allowlist_resolves_symlinks_when_supported` | complete; skipped if symlink creation is unavailable |
| `src/runtime.rs` | `unix_socket_allow_all_flag_bypasses_allowlist` | `tests/test_network_proxy_runtime_accessors_rs.py::test_unix_socket_allow_all_flag_bypasses_allowlist_when_supported` | complete |
| `src/runtime.rs` | `NetworkProxyState::{method_allowed,allow_upstream_proxy,allow_local_binding,network_mode}` source contract | `tests/test_network_proxy_runtime_accessors_rs.py::test_runtime_accessors_read_current_network_config` | complete |
| `src/runtime.rs` | `NetworkProxyState::set_network_mode` source contract | `tests/test_network_proxy_runtime_accessors_rs.py::test_set_network_mode_updates_mode_when_constraints_allow`, `tests/test_network_proxy_runtime_accessors_rs.py::test_set_network_mode_rejects_widening_managed_constraint` | complete |
| `src/runtime.rs` | `ConfigReloader::maybe_reload`, `NetworkProxyState::current_cfg`, private `reload_if_needed` source contract | `tests/test_network_proxy_runtime_reload_rs.py::test_current_cfg_reloads_on_demand_and_preserves_blocked_buffer` | complete |
| `src/runtime.rs` | `NetworkProxyState::enabled` source contract | `tests/test_network_proxy_runtime_reload_rs.py::test_enabled_uses_reloaded_config_state` | complete |
| `src/runtime.rs` | `ConfigReloader::reload_now`, `NetworkProxyState::force_reload` success/error source contracts | `tests/test_network_proxy_runtime_reload_rs.py::test_force_reload_replaces_state_and_preserves_blocked_buffer`, `tests/test_network_proxy_runtime_reload_rs.py::test_force_reload_error_keeps_previous_config_state` | complete |
| `src/runtime.rs` | `host_blocked_denied_wins_over_allowed` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_denied_wins_over_allowed` | complete |
| `src/runtime.rs` | `host_blocked_requires_allowlist_match` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_requires_allowlist_match` | complete |
| `src/runtime.rs` | `host_blocked_subdomain_wildcards_exclude_apex` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_subdomain_wildcards_exclude_apex` | complete |
| `src/runtime.rs` | `host_blocked_global_wildcard_allowlist_allows_public_hosts_except_denylist` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_global_wildcard_allowlist_allows_public_hosts_except_denylist` | complete |
| `src/runtime.rs` | `host_blocked_rejects_loopback_when_local_binding_disabled` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_rejects_loopback_when_local_binding_disabled` | complete |
| `src/runtime.rs` | `host_blocked_allows_loopback_when_explicitly_allowlisted_and_local_binding_disabled` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_allows_loopback_when_explicitly_allowlisted_and_local_binding_disabled` | complete |
| `src/runtime.rs` | `host_blocked_allows_private_ip_literal_when_explicitly_allowlisted` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_allows_private_ip_literal_when_explicitly_allowlisted` | complete |
| `src/runtime.rs` | `host_blocked_requires_exact_scoped_ipv6_allowlist_match`, `host_blocked_requires_exact_scoped_ipv6_denylist_match` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_scoped_ipv6_allowlist_and_denylist_are_exact` | complete |
| `src/runtime.rs` | `host_blocked_denies_scoped_ipv6_literal_before_local_binding` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_denies_unscoped_scoped_ipv6_before_local_binding` | complete |
| `src/runtime.rs` | `host_blocked_rejects_scoped_ipv6_literal_when_not_allowlisted`, `host_blocked_rejects_private_ip_literals_when_local_binding_disabled`, `host_blocked_rejects_loopback_when_allowlist_empty` | `tests/test_network_proxy_runtime_dns_rs.py::test_host_blocked_rejects_private_and_loopback_literals_when_not_allowlisted` | complete |
| `src/http_proxy.rs` | `validate_absolute_form_host_header_allows_matching_default_port` | `tests/test_network_proxy_http_proxy_rs.py::test_validate_absolute_form_host_header_allows_matching_default_port` | complete |
| `src/http_proxy.rs` | `validate_absolute_form_host_header_rejects_mismatched_host` | `tests/test_network_proxy_http_proxy_rs.py::test_validate_absolute_form_host_header_rejects_mismatched_host` | complete |
| `src/http_proxy.rs` | `validate_absolute_form_host_header_rejects_missing_non_default_port` | `tests/test_network_proxy_http_proxy_rs.py::test_validate_absolute_form_host_header_rejects_missing_non_default_port` | complete |
| `src/http_proxy.rs` | `validate_absolute_form_host_header` source contract for origin-form/missing/invalid Host | `tests/test_network_proxy_http_proxy_rs.py::test_validate_absolute_form_host_header_allows_origin_form_or_missing_host`, `tests/test_network_proxy_http_proxy_rs.py::test_validate_absolute_form_host_header_reports_invalid_host_header` | complete |
| `src/http_proxy.rs` | `remove_hop_by_hop_request_headers_keeps_forwarding_headers` | `tests/test_network_proxy_http_proxy_rs.py::test_remove_hop_by_hop_request_headers_keeps_forwarding_headers` | complete |
| `src/http_proxy.rs` | `remove_hop_by_hop_request_headers` source contract for `TE` and Connection tokens | `tests/test_network_proxy_http_proxy_rs.py::test_remove_hop_by_hop_request_headers_removes_te_and_connection_tokens_case_insensitively` | complete |
| `src/http_proxy.rs` | `http_connect_accept_blocks_in_limited_mode` | `tests/test_network_proxy_http_proxy_rs.py::test_http_connect_accept_blocks_in_limited_mode` | complete |
| `src/http_proxy.rs` | `http_connect_accept_allows_allowlisted_host_in_full_mode` | `tests/test_network_proxy_http_proxy_rs.py::test_http_connect_accept_allows_allowlisted_host_in_full_mode` | complete |
| `src/http_proxy.rs` | `http_connect_accept_blocks_hooked_host_in_full_mode_without_mitm_state` | `tests/test_network_proxy_http_proxy_rs.py::test_http_connect_accept_blocks_hooked_host_in_full_mode_without_mitm_state` | complete |
| `src/http_proxy.rs` | `http_connect_accept_denies_denylisted_host` | `tests/test_network_proxy_http_proxy_rs.py::test_http_connect_accept_denies_denylisted_host` | complete |
| `src/http_proxy.rs` | `http_plain_proxy_rejects_absolute_uri_host_header_mismatch` | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_rejects_absolute_uri_host_header_mismatch` | complete |
| `src/http_proxy.rs` | `http_plain_proxy` proxy-disabled branch source contract | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_disabled_records_blocked_request` | complete |
| `src/http_proxy.rs` | `http_plain_proxy` host-policy deny branch source contract | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_denies_denylisted_host_with_json_blocked` | complete |
| `src/http_proxy.rs` | `json_blocked` and `BlockedResponse` optional-field serde source contract | `tests/test_network_proxy_http_proxy_rs.py::test_json_blocked_omits_policy_fields_when_details_absent`, `tests/test_network_proxy_http_proxy_rs.py::test_json_blocked_includes_policy_fields_when_details_present` | complete |
| `src/http_proxy.rs` | `http_plain_proxy` method-policy branch source contract | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_blocks_disallowed_method_after_host_policy_allows` | complete |
| `src/http_proxy.rs` | `http_plain_proxy` upstream-failure branch source contract | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_allowed_request_maps_upstream_failure_to_bad_gateway` | complete |
| `src/http_proxy.rs`, `src/upstream.rs` | `http_plain_proxy`, `UpstreamClient::{direct,from_env_proxy}.serve`, `remove_hop_by_hop_request_headers` source contract | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_forwards_allowed_direct_http_request`, `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_routes_allowed_request_via_upstream_proxy` | complete |
| `src/http_proxy.rs` | `http_plain_proxy_blocks_unix_socket_when_method_not_allowed` | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_blocks_unix_socket_when_method_not_allowed` | complete |
| `src/http_proxy.rs` | `http_plain_proxy_rejects_unix_socket_when_not_allowlisted` | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_rejects_unix_socket_when_not_allowlisted_on_supported_platform`, `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_rejects_unix_socket_when_platform_unsupported` | complete |
| `src/http_proxy.rs` | `http_plain_proxy_attempts_allowed_unix_socket_proxy` | `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_attempts_allowed_unix_socket_proxy` | complete |
| `src/http_proxy.rs`, `src/upstream.rs` | `http_connect_proxy`, `forward_connect_tunnel`, `proxy_for_connect` source contract | `tests/test_network_proxy_http_proxy_rs.py::test_http_proxy_listener_routes_connect_via_upstream_proxy_env` | complete |
| `src/proxy.rs` | `proxy_url_env_value_resolves_lowercase_aliases` | `tests/test_network_proxy_proxy_rs.py::test_proxy_url_env_value_resolves_lowercase_aliases` | complete |
| `src/proxy.rs` | `has_proxy_url_env_vars_detects_lowercase_aliases` | `tests/test_network_proxy_proxy_rs.py::test_has_proxy_url_env_vars_detects_lowercase_aliases` | complete |
| `src/proxy.rs` | `has_proxy_url_env_vars_detects_websocket_proxy_keys` | `tests/test_network_proxy_proxy_rs.py::test_has_proxy_url_env_vars_detects_websocket_proxy_keys` | complete |
| `src/proxy.rs` | `apply_proxy_env_overrides_sets_common_tool_vars` | `tests/test_network_proxy_proxy_rs.py::test_apply_proxy_env_overrides_sets_common_tool_vars` | complete |
| `src/proxy.rs` | `apply_proxy_env_overrides_sets_only_expected_env_keys` | `tests/test_network_proxy_proxy_rs.py::test_apply_proxy_env_overrides_sets_only_expected_env_keys` | complete |
| `src/proxy.rs` | `apply_proxy_env_overrides_uses_http_for_all_proxy_without_socks` | `tests/test_network_proxy_proxy_rs.py::test_apply_proxy_env_overrides_uses_http_for_all_proxy_without_socks` | complete |
| `src/proxy.rs` | `apply_proxy_env_overrides_uses_plain_http_proxy_url` | `tests/test_network_proxy_proxy_rs.py::test_apply_proxy_env_overrides_uses_plain_http_proxy_url` | complete |
| `src/proxy.rs` | `apply_proxy_env_overrides_preserves_existing_git_ssh_command`, `apply_proxy_env_overrides_preserves_unmarked_git_ssh_command_with_proxy_shape`, `apply_proxy_env_overrides_refreshes_previous_codex_proxy_git_ssh_command` | `tests/test_network_proxy_proxy_rs.py::test_apply_proxy_env_overrides_preserves_existing_git_ssh_command`, `tests/test_network_proxy_proxy_rs.py::test_apply_proxy_env_overrides_preserves_unmarked_git_ssh_command_with_proxy_shape`, `tests/test_network_proxy_proxy_rs.py::test_apply_proxy_env_overrides_refreshes_previous_codex_proxy_git_ssh_command` | complete |
| `src/proxy.rs` | `windows_managed_loopback_addr_clamps_non_loopback_inputs` | `tests/test_network_proxy_proxy_rs.py::test_windows_managed_loopback_addr_clamps_non_loopback_inputs` | complete |
| `src/proxy.rs` | `reserve_windows_managed_listeners_falls_back_when_http_port_is_busy` | `tests/test_network_proxy_proxy_rs.py::test_reserve_windows_managed_listeners_falls_back_when_http_port_is_busy` | complete |
| `src/proxy.rs` | `managed_proxy_builder_uses_loopback_ports` | `tests/test_network_proxy_proxy_rs.py::test_managed_proxy_builder_uses_loopback_ports` | complete |
| `src/proxy.rs` | `non_codex_managed_proxy_builder_uses_configured_ports` | `tests/test_network_proxy_proxy_rs.py::test_non_codex_managed_proxy_builder_uses_configured_ports` | complete |
| `src/proxy.rs` | `managed_proxy_builder_does_not_reserve_socks_listener_when_disabled` | `tests/test_network_proxy_proxy_rs.py::test_managed_proxy_builder_does_not_reserve_socks_listener_when_disabled` | complete |
| `src/proxy.rs` | `NetworkProxy::replace_config_state` immutable running endpoint guards and runtime-settings refresh source contracts | `tests/test_network_proxy_proxy_rs.py::test_network_proxy_replace_config_state_rejects_runtime_endpoint_changes`, `tests/test_network_proxy_proxy_rs.py::test_network_proxy_replace_config_state_refreshes_runtime_settings` | complete |
| `src/proxy.rs` | `NetworkProxy::run`, `NetworkProxyHandle::shutdown`, `run_http_proxy_with_std_listener`, `run_socks5_with_std_listener` source contract | `tests/test_network_proxy_proxy_rs.py::test_network_proxy_run_starts_http_and_socks_tasks_and_shutdown_aborts_them` | complete |
| `src/proxy.rs` | `NetworkProxyHandle::wait` source contract joins HTTP and optional SOCKS tasks before propagating task errors. | `tests/test_network_proxy_proxy_rs.py::test_network_proxy_handle_wait_awaits_socks_task_before_http_error` | complete |
| `src/proxy.rs` | `Drop for NetworkProxyHandle`, `abort_tasks` source contract cancels unfinished proxy tasks when a handle is dropped before wait/shutdown. | `tests/test_network_proxy_proxy_rs.py::test_network_proxy_handle_drop_cancels_unfinished_tasks` | complete |
| `src/mitm_hook.rs` | `validate_requires_mitm_for_hooks` | `tests/test_network_proxy_mitm_hook_rs.py::test_validate_requires_mitm_for_hooks` | complete |
| `src/mitm_hook.rs` | `validate_allows_hooks_in_full_mode` | `tests/test_network_proxy_mitm_hook_rs.py::test_validate_allows_hooks_in_full_mode` | complete |
| `src/mitm_hook.rs` | `validate_rejects_body_matchers_for_now` | `tests/test_network_proxy_mitm_hook_rs.py::test_validate_rejects_body_matchers_for_now` | complete |
| `src/mitm_hook.rs` | `validate_rejects_relative_secret_file`, `validate_rejects_dual_secret_sources` | `tests/test_network_proxy_mitm_hook_rs.py::test_validate_rejects_relative_secret_file`, `tests/test_network_proxy_mitm_hook_rs.py::test_validate_rejects_dual_secret_sources` | complete |
| `src/mitm_hook.rs` | `compile_resolves_env_backed_injected_headers`, `compile_resolves_file_backed_injected_headers` | `tests/test_network_proxy_mitm_hook_rs.py::test_compile_resolves_env_backed_injected_headers`, `tests/test_network_proxy_mitm_hook_rs.py::test_compile_resolves_file_backed_injected_headers` | complete |
| `src/mitm_hook.rs` | `evaluate_returns_first_matching_hook` | `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_returns_first_matching_hook` | complete |
| `src/mitm_hook.rs` | `evaluate_matches_query_and_header_constraints`, `evaluate_matches_wildcard_path_query_and_header_constraints` | `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_matches_query_and_header_constraints`, `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_matches_wildcard_path_query_and_header_constraints` | complete |
| `src/mitm_hook.rs` | `validate_rejects_invalid_wildcard_path_pattern`, `evaluate_path_wildcard_does_not_cross_segment_boundaries` | `tests/test_network_proxy_mitm_hook_rs.py::test_validate_rejects_invalid_wildcard_path_pattern`, `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_path_wildcard_does_not_cross_segment_boundaries` | complete |
| `src/mitm_hook.rs` | `evaluate_treats_glob_metacharacters_as_literal_without_glob_prefix`, `evaluate_allows_literal_values_with_reserved_prefixes` | `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_treats_glob_metacharacters_as_literal_without_glob_prefix`, `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_allows_literal_values_with_reserved_prefixes` | complete |
| `src/mitm_hook.rs` | `evaluate_returns_hooked_host_no_match_when_query_constraint_fails`, `evaluate_returns_no_hooks_for_unconfigured_host` | `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_returns_hooked_host_no_match_when_query_constraint_fails`, `tests/test_network_proxy_mitm_hook_rs.py::test_evaluate_returns_no_hooks_for_unconfigured_host` | complete |
| `src/mitm.rs` / `src/mitm_tests.rs` | `mitm_policy_blocks_disallowed_method_and_records_telemetry` | `tests/test_network_proxy_mitm_rs.py::test_mitm_policy_blocks_disallowed_method_and_records_telemetry` | complete |
| `src/mitm.rs` / `src/mitm_tests.rs` | `mitm_policy_rejects_host_mismatch` | `tests/test_network_proxy_mitm_rs.py::test_mitm_policy_rejects_host_mismatch` | complete |
| `src/mitm.rs` / `src/mitm_tests.rs` | `mitm_policy_rechecks_local_private_target_after_connect` | `tests/test_network_proxy_mitm_rs.py::test_mitm_policy_rechecks_local_private_target_after_connect` | complete |
| `src/mitm.rs` / `src/mitm_tests.rs` | `mitm_policy_allows_matching_hooked_write_in_full_mode` | `tests/test_network_proxy_mitm_rs.py::test_mitm_policy_allows_matching_hooked_write_in_full_mode` | complete |
| `src/mitm.rs` / `src/mitm_tests.rs` | `mitm_policy_blocks_matching_hooked_write_in_limited_mode` | `tests/test_network_proxy_mitm_rs.py::test_mitm_policy_blocks_matching_hooked_write_in_limited_mode` | complete |
| `src/mitm.rs` / `src/mitm_tests.rs` | `mitm_policy_blocks_hook_miss_for_hooked_host_and_records_telemetry_in_full_mode` | `tests/test_network_proxy_mitm_rs.py::test_mitm_policy_blocks_hook_miss_for_hooked_host_and_records_telemetry_in_full_mode` | complete |
| `src/mitm.rs` / `src/mitm_tests.rs` | `apply_mitm_hook_actions_replaces_authorization_header` | `tests/test_network_proxy_mitm_rs.py::test_apply_mitm_hook_actions_replaces_authorization_header` | complete |
| `src/mitm.rs` | `extract_request_host`, `authority_header_value`, `build_https_uri`, `path_and_query`, `path_for_log` source contracts | `tests/test_network_proxy_mitm_rs.py::test_mitm_request_host_prefers_host_header_then_uri_authority`, `tests/test_network_proxy_mitm_rs.py::test_mitm_authority_header_value_formats_default_port_and_ipv6`, `tests/test_network_proxy_mitm_rs.py::test_mitm_build_https_uri_and_path_helpers_match_rust_source_contract` | complete |
| `src/socks5.rs` | `handle_socks5_tcp_emits_block_decision_for_proxy_disabled` | `tests/test_network_proxy_socks5_rs.py::test_handle_socks5_tcp_emits_block_decision_for_proxy_disabled` | complete |
| `src/socks5.rs` | `handle_socks5_tcp_blocks_hooked_host_in_full_mode` | `tests/test_network_proxy_socks5_rs.py::test_handle_socks5_tcp_blocks_hooked_host_in_full_mode` | complete |
| `src/socks5.rs` | `inspect_socks5_udp_emits_block_decision_for_mode_guard_deny` | `tests/test_network_proxy_socks5_rs.py::test_inspect_socks5_udp_emits_block_decision_for_mode_guard_deny` | complete |
| `src/socks5.rs` | `run_socks5_with_std_listener`, `handle_socks5_tcp`, `TargetCheckedTcpConnector` source contract | `tests/test_network_proxy_socks5_rs.py::test_run_socks5_with_std_listener_relays_allowed_tcp_connect` | complete |
| `src/socks5.rs` | `run_socks5_with_std_listener`, `DefaultUdpRelay`, `inspect_socks5_udp` source contract | `tests/test_network_proxy_socks5_rs.py::test_run_socks5_with_std_listener_relays_allowed_udp_associate` | complete |
| `src/certs.rs` | `validate_existing_ca_key_file_rejects_group_world_permissions` | `tests/test_network_proxy_certs_rs.py::test_validate_existing_ca_key_file_rejects_group_world_permissions` | complete |
| `src/certs.rs` | `validate_existing_ca_key_file_rejects_symlink` | `tests/test_network_proxy_certs_rs.py::test_validate_existing_ca_key_file_rejects_symlink` | complete on Unix-capable hosts; skipped when symlink creation is unavailable |
| `src/certs.rs` | `validate_existing_ca_key_file_allows_private_permissions` | `tests/test_network_proxy_certs_rs.py::test_validate_existing_ca_key_file_allows_private_permissions` | complete |
| `src/certs.rs` | `managed_ca_paths`, `write_atomic_create_new` source contracts | `tests/test_network_proxy_certs_rs.py::test_managed_ca_paths_uses_codex_home_proxy_file_names`, `tests/test_network_proxy_certs_rs.py::test_write_atomic_create_new_writes_file_and_refuses_overwrite` | complete |

## Validation

2026-06-21:

- `python -m pytest tests\test_network_proxy_config_rs.py -q --tb=short`
  - `16 passed`
- `python -m pytest tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `60 passed, 4 subtests passed`

2026-06-22:

- `python -m pytest tests\test_network_proxy_state_rs.py -q --tb=short`
  - `15 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `91 passed, 4 subtests passed`

2026-06-22 policy follow-up:

- `python -m pytest tests\test_network_proxy_policy_rs.py -q --tb=short`
  - `39 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `130 passed, 4 subtests passed`

2026-06-22 network-policy follow-up:

- `python -m pytest tests\test_network_proxy_network_policy_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `137 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_network_policy_rs.py`
  - passed

2026-06-22 reasons follow-up:

- `python -m pytest tests\test_network_proxy_reasons_rs.py -q --tb=short`
  - `2 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `139 passed, 4 subtests passed`
- `python -m py_compile tests\test_network_proxy_reasons_rs.py pycodex\network_proxy\__init__.py`
  - passed

2026-06-22 responses follow-up:

- `python -m pytest tests\test_network_proxy_responses_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `144 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_responses_rs.py`
  - passed

2026-06-22 connect-policy follow-up:

- `python -m pytest tests\test_network_proxy_connect_policy_rs.py -q --tb=short`
  - `3 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `147 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_connect_policy_rs.py`
  - passed

2026-06-22 upstream follow-up:

- `python -m pytest tests\test_network_proxy_upstream_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `154 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_upstream_rs.py`
  - passed

2026-06-22 runtime blocked-buffer follow-up:

- `python -m pytest tests\test_network_proxy_runtime_blocked_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `159 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_runtime_blocked_rs.py`
  - passed

2026-06-22 HTTP proxy helper follow-up:

- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `166 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 proxy env follow-up:

- `python -m pytest tests\test_network_proxy_proxy_rs.py -q --tb=short`
  - `9 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `175 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_proxy_rs.py`
  - passed

2026-06-22 MITM hook follow-up:

- `python -m pytest tests\test_network_proxy_mitm_hook_rs.py -q --tb=short`
  - `16 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `191 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_mitm_hook_rs.py`
  - passed

2026-06-22 MITM policy/action follow-up:

- `python -m pytest tests\test_network_proxy_mitm_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `198 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_mitm_rs.py`
  - passed

2026-06-22 SOCKS5 policy/inspection follow-up:

- `python -m pytest tests\test_network_proxy_socks5_rs.py -q --tb=short`
  - `3 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `201 passed, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_socks5_rs.py`
  - passed

2026-06-22 certs file-safety follow-up:

- `python -m pytest tests\test_network_proxy_certs_rs.py -q --tb=short`
  - `4 passed, 1 skipped`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `205 passed, 1 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_certs_rs.py`
  - passed

2026-06-22 runtime DNS/private-address guard follow-up:

- `python -m pytest tests\test_network_proxy_runtime_dns_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_runtime_dns_rs.py -q --tb=short`
  - `13 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `211 passed, 1 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_mitm_rs.py`
  - passed

2026-06-22 proxy builder/runtime-settings follow-up:

- `python -m pytest tests\test_network_proxy_proxy_rs.py -q --tb=short`
  - `14 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `216 passed, 1 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_proxy_rs.py`
  - passed

2026-06-22 runtime dynamic domain mutation follow-up:

- `python -m pytest tests\test_network_proxy_runtime_domains_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `223 passed, 1 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_runtime_domains_rs.py`
  - passed

2026-06-22 runtime unix-socket/accessor follow-up:

- `python -m pytest tests\test_network_proxy_runtime_accessors_rs.py -q --tb=short`
  - `6 passed, 1 skipped`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `229 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_runtime_accessors_rs.py`
  - passed

2026-06-22 runtime reload follow-up:

- `python -m pytest tests\test_network_proxy_runtime_reload_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `233 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_runtime_reload_rs.py`
  - passed

2026-06-22 HTTP CONNECT accept follow-up:

- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `11 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `237 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 HTTP plain unix-socket preflight follow-up:

- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `15 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `241 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 HTTP plain host/method preflight follow-up:

- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `20 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `246 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 HTTP blocked JSON response shape follow-up:

- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `22 passed`
- `$files = Get-ChildItem tests -Filter 'test_network_proxy*.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short`
  - `213 passed, 2 skipped`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 runtime host policy/local/scoped-IP follow-up:

- `python -m pytest tests\test_network_proxy_runtime_dns_rs.py -q --tb=short`
  - `14 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `254 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_runtime_dns_rs.py`
  - passed

2026-06-22 runtime host policy base follow-up:

- `python -m pytest tests\test_network_proxy_runtime_dns_rs.py -q --tb=short`
  - `16 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `256 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile tests\test_network_proxy_runtime_dns_rs.py pycodex\network_proxy\__init__.py`
  - passed

2026-06-22 runtime build_config_state global wildcard follow-up:

- `python -m pytest tests\test_network_proxy_state_rs.py -q --tb=short`
  - `19 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `260 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile tests\test_network_proxy_state_rs.py pycodex\network_proxy\__init__.py`
  - passed

2026-06-22 runtime compile_globset follow-up:

- `python -m pytest tests\test_network_proxy_policy_rs.py -q --tb=short`
  - `44 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `265 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_policy_rs.py`
  - passed

2026-06-22 proxy macOS GIT_SSH_COMMAND follow-up:

- `python -m pytest tests\test_network_proxy_proxy_rs.py -q --tb=short`
  - `17 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `268 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_proxy_rs.py`
  - passed

2026-06-22 MITM request helper follow-up:

- `python -m pytest tests\test_network_proxy_mitm_rs.py -q --tb=short`
  - `10 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `271 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_mitm_rs.py`
  - passed

2026-06-22 HTTP live CONNECT listener/direct-tunnel follow-up:

- Rust source: `codex-network-proxy/src/http_proxy.rs`
- Rust test: `http_proxy_listener_accepts_plain_http1_connect_requests`
- Python test: `tests/test_network_proxy_http_proxy_rs.py::test_http_proxy_listener_accepts_plain_http1_connect_requests`
- Contract: `run_http_proxy_with_std_listener` serves a real local stdlib TCP listener, parses a raw HTTP/1 CONNECT request, applies the existing CONNECT accept policy, writes an `HTTP/1.1 200 OK` response for an allowlisted target, and forwards client bytes to the direct target TCP stream like `forward_connect_tunnel`.
- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `23 passed`
- `python -m pytest tests\test_network_proxy_config_rs.py tests\test_network_proxy_state_rs.py tests\test_network_proxy_policy_rs.py tests\test_network_proxy_network_policy_rs.py tests\test_network_proxy_reasons_rs.py tests\test_network_proxy_responses_rs.py tests\test_network_proxy_connect_policy_rs.py tests\test_network_proxy_upstream_rs.py tests\test_network_proxy_runtime_blocked_rs.py tests\test_network_proxy_runtime_dns_rs.py tests\test_network_proxy_runtime_domains_rs.py tests\test_network_proxy_runtime_accessors_rs.py tests\test_network_proxy_runtime_reload_rs.py tests\test_network_proxy_http_proxy_rs.py tests\test_network_proxy_proxy_rs.py tests\test_network_proxy_mitm_hook_rs.py tests\test_network_proxy_mitm_rs.py tests\test_network_proxy_socks5_rs.py tests\test_network_proxy_certs_rs.py tests\test_core_network_proxy_loader.py tests\test_config_permissions_toml.py tests\test_core_config_permissions.py -q --tb=short`
  - `274 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 HTTP CONNECT upstream-proxy route follow-up:

- Rust source: `codex-network-proxy/src/http_proxy.rs`, `codex-network-proxy/src/upstream.rs`
- Rust items: `http_connect_proxy`, `forward_connect_tunnel`, `proxy_for_connect`
- Python test: `tests/test_network_proxy_http_proxy_rs.py::test_http_proxy_listener_routes_connect_via_upstream_proxy_env`
- Contract: when `allow_upstream_proxy` is true and `proxy_for_connect` selects an HTTP env proxy, the live stdlib CONNECT listener routes the tunnel through the upstream proxy, sends a CONNECT request with the original target authority, accepts the upstream 200 response, and forwards client bytes over that upstream stream.
- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `24 passed`
- `$files = @(Get-ChildItem tests -Filter 'test_network_proxy_*.py' | ForEach-Object { $_.FullName }) + @('tests\test_core_network_proxy_loader.py','tests\test_config_permissions_toml.py','tests\test_core_config_permissions.py'); python -m pytest $files -q --tb=short`
  - `275 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 HTTP plain live upstream forwarding follow-up:

- Rust source: `codex-network-proxy/src/http_proxy.rs`, `codex-network-proxy/src/upstream.rs`
- Rust items: `http_plain_proxy`, `remove_hop_by_hop_request_headers`, `UpstreamClient::{direct,from_env_proxy}.serve`
- Python tests: `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_forwards_allowed_direct_http_request`, `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_routes_allowed_request_via_upstream_proxy`, `tests/test_network_proxy_http_proxy_rs.py::test_http_plain_proxy_allowed_request_maps_upstream_failure_to_bad_gateway`
- Contract: after plain HTTP preflight allows a request, hop-by-hop request headers are stripped, direct routing sends origin-form targets to the target server, env-proxy routing sends absolute-form targets to the upstream HTTP proxy when `allow_upstream_proxy` is enabled, upstream responses are projected into `NetworkProxyResponse`, and upstream connection/response failures map to `502 upstream failure`.
- `python -m pytest tests\test_network_proxy_http_proxy_rs.py -q --tb=short`
  - `26 passed`
- `$files = @(Get-ChildItem tests -Filter 'test_network_proxy_*.py' | ForEach-Object { $_.FullName }) + @('tests\test_core_network_proxy_loader.py','tests\test_config_permissions_toml.py','tests\test_core_config_permissions.py'); python -m pytest $files -q --tb=short`
  - `277 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_http_proxy_rs.py`
  - passed

2026-06-22 SOCKS5 live TCP listener/relay follow-up:

- Rust source: `codex-network-proxy/src/socks5.rs`
- Rust items: `run_socks5_with_std_listener`, `run_socks5_with_listener`, `handle_socks5_tcp`, `TargetCheckedTcpConnector`
- Python test: `tests/test_network_proxy_socks5_rs.py::test_run_socks5_with_std_listener_relays_allowed_tcp_connect`
- Contract: the live SOCKS5 listener accepts a no-auth TCP CONNECT request, applies the existing SOCKS5 TCP policy boundary, establishes a target TCP connection for an allowed request, writes a successful SOCKS5 reply, and relays bytes bidirectionally through real local sockets.
- `python -m pytest tests\test_network_proxy_socks5_rs.py -q --tb=short`
  - `4 passed`
- `$files = @(Get-ChildItem tests -Filter 'test_network_proxy_*.py' | ForEach-Object { $_.FullName }) + @('tests\test_core_network_proxy_loader.py','tests\test_config_permissions_toml.py','tests\test_core_config_permissions.py'); python -m pytest $files -q --tb=short`
  - `278 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_socks5_rs.py`
  - passed

2026-06-22 SOCKS5 live UDP ASSOCIATE/relay follow-up:

- Rust source: `codex-network-proxy/src/socks5.rs`
- Rust items: `run_socks5_with_std_listener`, `run_socks5_with_listener`, `DefaultUdpRelay`, `inspect_socks5_udp`
- Python test: `tests/test_network_proxy_socks5_rs.py::test_run_socks5_with_std_listener_relays_allowed_udp_associate`
- Contract: when SOCKS5 UDP support is enabled, UDP ASSOCIATE starts a relay, each datagram is checked through the existing UDP inspection policy, allowed payloads are forwarded to a real UDP target, and target responses are returned in SOCKS5 UDP framing.
- `python -m pytest tests\test_network_proxy_socks5_rs.py -q --tb=short`
  - `5 passed`
- `$files = @(Get-ChildItem tests -Filter 'test_network_proxy_*.py' | ForEach-Object { $_.FullName }) + @('tests\test_core_network_proxy_loader.py','tests\test_config_permissions_toml.py','tests\test_core_config_permissions.py'); python -m pytest $files -q --tb=short`
  - `279 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_socks5_rs.py`
  - passed

2026-06-22 proxy run/shutdown live task follow-up:

- Rust source: `codex-network-proxy/src/proxy.rs`
- Rust items: `NetworkProxy::run`, `NetworkProxyHandle::shutdown`, `run_http_proxy_with_std_listener`, `run_socks5_with_std_listener`
- Python test: `tests/test_network_proxy_proxy_rs.py::test_network_proxy_run_starts_http_and_socks_tasks_and_shutdown_aborts_them`
- Contract: an enabled proxy consumes reserved listeners, starts HTTP and optional SOCKS listener tasks, exposes reachable listener endpoints, and shutdown aborts both listener tasks.
- `python -m pytest tests\test_network_proxy_proxy_rs.py -q --tb=short`
  - `18 passed`
- `$files = @(Get-ChildItem tests -Filter 'test_network_proxy_*.py' | ForEach-Object { $_.FullName }) + @('tests\test_core_network_proxy_loader.py','tests\test_config_permissions_toml.py','tests\test_core_config_permissions.py'); python -m pytest $files -q --tb=short`
  - `280 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_proxy_rs.py`
  - passed

2026-06-22 proxy handle wait/drop follow-up:

- Rust source: `codex-network-proxy/src/proxy.rs`
- Rust items: `NetworkProxyHandle::wait`, `abort_tasks`, `Drop for NetworkProxyHandle`
- Python tests: `tests/test_network_proxy_proxy_rs.py::test_network_proxy_handle_wait_awaits_socks_task_before_http_error`, `tests/test_network_proxy_proxy_rs.py::test_network_proxy_handle_drop_cancels_unfinished_tasks`
- Contract: `wait` joins both HTTP and optional SOCKS tasks before propagating errors, and dropping an incomplete handle cancels unfinished proxy tasks.
- `python -m pytest tests\test_network_proxy_proxy_rs.py -q --tb=short`
  - `20 passed`
- `$files = @(Get-ChildItem tests -Filter 'test_network_proxy_*.py' | ForEach-Object { $_.FullName }) + @('tests\test_core_network_proxy_loader.py','tests\test_config_permissions_toml.py','tests\test_core_config_permissions.py'); python -m pytest $files -q --tb=short`
  - `282 passed, 2 skipped, 4 subtests passed`
- `python -m py_compile pycodex\network_proxy\__init__.py tests\test_network_proxy_proxy_rs.py`
  - passed

## Remaining Crate Gaps

- `src/runtime.rs`: full native reloadable/live async runtime identity. Rust uses on-demand reload through `reload_if_needed`; no separate reload task exists in `src/proxy.rs`.
- `src/http_proxy.rs`, `src/socks5.rs`, `src/proxy.rs`: native SOCKS/Rama upstream runtime identity, native task orchestration details, and Tokio JoinHandle identity. The HTTP/1 CONNECT listener/direct-tunnel/upstream-proxy route, plain HTTP direct/upstream-proxy forwarding, SOCKS5 TCP no-auth CONNECT relay, SOCKS5 UDP ASSOCIATE/relay, stdlib `NetworkProxy.run` startup/shutdown, and handle wait/drop slices are covered by the 2026-06-22 real local socket/source-contract tests.
- `src/mitm.rs`, `src/certs.rs`: MITM TLS termination, CA/host certificate generation, rustls acceptor setup, body inspection stream, and live upstream forwarding.
