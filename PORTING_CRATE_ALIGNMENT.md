# PORTING_CRATE_ALIGNMENT.md

Updated: 2026-06-05

This file is the crate-level alignment inventory for the Rust Codex to PyCodex port.

It registers every Rust workspace crate and assigns a Python target location. Registration does not imply full implementation.

## Rule

```text
crate-level alignment = absolute inventory
module-level alignment = prefer natural 1:1, document merge/split exceptions
function-level alignment = selective local anchor
```

Every Rust crate should have a Python target coordinate even when the status is `deferred`, `shim`, `out_of_scope`, or `not_started`.

## Status Values

| Status | Meaning |
|---|---|
| `implemented` | Python has a real implementation package or module for this crate/domain |
| `shim` | Python has a compatibility surface or approximate implementation only |
| `deferred` | Registered but intentionally not active implementation scope |
| `out_of_scope` | Registered and explicitly excluded from current porting goal |
| `not_started` | Registered but not yet organized or implemented |

## Crate Inventory

| Rust crate | Rust path | Python target | Domain | Status | Policy |
|---|---|---|---|---|---|
| `codex-agent-graph-store` | `codex/codex-rs/agent-graph-store` | `pycodex/agent_graph_store` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-agent-identity` | `codex/codex-rs/agent-identity` | `pycodex/agent_identity` | `auth_identity_secrets` | `not_started` | `register_then_decide` |
| `codex-analytics` | `codex/codex-rs/analytics` | `pycodex/analytics` | `cloud_backend_connectors_feedback` | `not_started` | `register_then_decide` |
| `codex-ansi-escape` | `codex/codex-rs/ansi-escape` | `pycodex/ansi_escape` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-api` | `codex/codex-rs/codex-api` | `pycodex/codex_api` | `protocol_and_api_contracts` | `not_started` | `register_then_decide` |
| `codex-app-server` | `codex/codex-rs/app-server` | `pycodex/app_server` | `app_server_transport` | `deferred` | `compatibility_shim_only` |
| `codex-app-server-client` | `codex/codex-rs/app-server-client` | `pycodex/app_server_client` | `app_server_transport` | `shim` | `compatibility_shim_only` |
| `codex-app-server-daemon` | `codex/codex-rs/app-server-daemon` | `pycodex/app_server_daemon` | `app_server_transport` | `deferred` | `compatibility_shim_only` |
| `codex-app-server-protocol` | `codex/codex-rs/app-server-protocol` | `pycodex/app_server_protocol` | `protocol_and_api_contracts` | `partial` | `selected_protocol_types` |
| `codex-app-server-test-client` | `codex/codex-rs/app-server-test-client` | `pycodex/app_server_test_client` | `app_server_transport` | `not_started` | `register_then_decide` |
| `codex-app-server-transport` | `codex/codex-rs/app-server-transport` | `pycodex/app_server_transport` | `app_server_transport` | `deferred` | `compatibility_shim_only` |
| `codex-apply-patch` | `codex/codex-rs/apply-patch` | `pycodex/apply_patch` | `command_file_sandbox_tools` | `implemented` | `canonical_runtime_package` |
| `codex-arg0` | `codex/codex-rs/arg0` | `pycodex/arg0` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-async-utils` | `codex/codex-rs/async-utils` | `pycodex/async_utils` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-aws-auth` | `codex/codex-rs/aws-auth` | `pycodex/aws_auth` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-backend-client` | `codex/codex-rs/backend-client` | `pycodex/backend_client` | `cloud_backend_connectors_feedback` | `not_started` | `register_then_decide` |
| `codex-backend-openapi-models` | `codex/codex-rs/codex-backend-openapi-models` | `pycodex/codex_backend_openapi_models` | `protocol_and_api_contracts` | `not_started` | `register_then_decide` |
| `codex-bwrap` | `codex/codex-rs/bwrap` | `pycodex/bwrap` | `command_file_sandbox_tools` | `not_started` | `register_then_decide` |
| `codex-cli` | `codex/codex-rs/cli` | `pycodex/cli` | `user_entrypoints` | `implemented` | `port_behavior` |
| `codex-client` | `codex/codex-rs/codex-client` | `pycodex/codex_client` | `core_runtime_and_model_io` | `not_started` | `register_then_decide` |
| `codex-cloud-requirements` | `codex/codex-rs/cloud-requirements` | `pycodex/cloud_requirements` | `configuration_policy_features` | `not_started` | `register_then_decide` |
| `codex-cloud-tasks` | `codex/codex-rs/cloud-tasks` | `pycodex/cloud_tasks` | `cloud_backend_connectors_feedback` | `not_started` | `register_then_decide` |
| `codex-cloud-tasks-client` | `codex/codex-rs/cloud-tasks-client` | `pycodex/cloud_tasks_client` | `cloud_backend_connectors_feedback` | `not_started` | `register_then_decide` |
| `codex-cloud-tasks-mock-client` | `codex/codex-rs/cloud-tasks-mock-client` | `pycodex/cloud_tasks_mock_client` | `cloud_backend_connectors_feedback` | `not_started` | `register_then_decide` |
| `codex-code-mode` | `codex/codex-rs/code-mode` | `pycodex/code_mode` | `user_entrypoints` | `not_started` | `register_then_decide` |
| `codex-collaboration-mode-templates` | `codex/codex-rs/collaboration-mode-templates` | `pycodex/collaboration_mode_templates` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-config` | `codex/codex-rs/config` | `pycodex/config` | `configuration_policy_features` | `implemented` | `port_behavior` |
| `codex-connectors` | `codex/codex-rs/connectors` | `pycodex/connectors` | `cloud_backend_connectors_feedback` | `not_started` | `register_then_decide` |
| `codex-core` | `codex/codex-rs/core` | `pycodex/core` | `core_runtime_and_model_io` | `implemented` | `port_behavior` |
| `codex-core-api` | `codex/codex-rs/core-api` | `pycodex/core_api` | `protocol_and_api_contracts` | `not_started` | `register_then_decide` |
| `codex-core-plugins` | `codex/codex-rs/core-plugins` | `pycodex/core_plugins` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-core-skills` | `codex/codex-rs/core-skills` | `pycodex/core_skills` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-debug-client` | `codex/codex-rs/debug-client` | `pycodex/debug_client` | `user_entrypoints` | `not_started` | `register_then_decide` |
| `codex-exec` | `codex/codex-rs/exec` | `pycodex/exec` | `user_entrypoints` | `implemented` | `port_behavior` |
| `codex-exec-server` | `codex/codex-rs/exec-server` | `pycodex/exec_server` | `command_file_sandbox_tools` | `not_started` | `register_then_decide` |
| `codex-execpolicy` | `codex/codex-rs/execpolicy` | `pycodex/execpolicy` | `configuration_policy_features` | `implemented` | `canonical_runtime_package` |
| `codex-execpolicy-legacy` | `codex/codex-rs/execpolicy-legacy` | `pycodex/execpolicy_legacy` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-experimental-api-macros` | `codex/codex-rs/codex-experimental-api-macros` | `pycodex/codex_experimental_api_macros` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-extension-api` | `codex/codex-rs/ext/extension-api` | `pycodex/ext/extension_api` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-external-agent-migration` | `codex/codex-rs/external-agent-migration` | `pycodex/external_agent_migration` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-external-agent-sessions` | `codex/codex-rs/external-agent-sessions` | `pycodex/external_agent_sessions` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-features` | `codex/codex-rs/features` | `pycodex/features` | `configuration_policy_features` | `implemented` | `canonical_runtime_package` |
| `codex-feedback` | `codex/codex-rs/feedback` | `pycodex/feedback` | `cloud_backend_connectors_feedback` | `not_started` | `register_then_decide` |
| `codex-file-search` | `codex/codex-rs/file-search` | `pycodex/file_search` | `state_history_files` | `not_started` | `register_then_decide` |
| `codex-file-system` | `codex/codex-rs/file-system` | `pycodex/file_system` | `state_history_files` | `not_started` | `register_then_decide` |
| `codex-file-watcher` | `codex/codex-rs/file-watcher` | `pycodex/file_watcher` | `state_history_files` | `not_started` | `register_then_decide` |
| `codex-git-utils` | `codex/codex-rs/git-utils` | `pycodex/git_utils` | `platform_utilities` | `implemented` | `canonical_runtime_package` |
| `codex-goal-extension` | `codex/codex-rs/ext/goal` | `pycodex/ext/goal` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-guardian` | `codex/codex-rs/ext/guardian` | `pycodex/ext/guardian` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-hooks` | `codex/codex-rs/hooks` | `pycodex/hooks` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-install-context` | `codex/codex-rs/install-context` | `pycodex/install_context` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-keyring-store` | `codex/codex-rs/keyring-store` | `pycodex/keyring_store` | `auth_identity_secrets` | `not_started` | `register_then_decide` |
| `codex-linux-sandbox` | `codex/codex-rs/linux-sandbox` | `pycodex/linux_sandbox` | `command_file_sandbox_tools` | `shim` | `platform_approximation` |
| `codex-lmstudio` | `codex/codex-rs/lmstudio` | `pycodex/lmstudio` | `provider_and_network_adapters` | `not_started` | `register_then_decide` |
| `codex-login` | `codex/codex-rs/login` | `pycodex/login` | `auth_identity_secrets` | `shim` | `transitional_package` |
| `codex-mcp` | `codex/codex-rs/codex-mcp` | `pycodex/codex_mcp` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-mcp-server` | `codex/codex-rs/mcp-server` | `pycodex/mcp_server` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-memories-extension` | `codex/codex-rs/ext/memories` | `pycodex/ext/memories` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-memories-read` | `codex/codex-rs/memories/read` | `pycodex/memories/read` | `state_history_files` | `not_started` | `register_then_decide` |
| `codex-memories-write` | `codex/codex-rs/memories/write` | `pycodex/memories/write` | `state_history_files` | `not_started` | `register_then_decide` |
| `codex-model-provider` | `codex/codex-rs/model-provider` | `pycodex/model_provider` | `core_runtime_and_model_io` | `not_started` | `register_then_decide` |
| `codex-model-provider-info` | `codex/codex-rs/model-provider-info` | `pycodex/model_provider_info` | `core_runtime_and_model_io` | `not_started` | `register_then_decide` |
| `codex-models-manager` | `codex/codex-rs/models-manager` | `pycodex/models_manager` | `provider_and_network_adapters` | `not_started` | `register_then_decide` |
| `codex-network-proxy` | `codex/codex-rs/network-proxy` | `pycodex/network_proxy` | `provider_and_network_adapters` | `shim` | `partial_runtime_helpers` |
| `codex-ollama` | `codex/codex-rs/ollama` | `pycodex/ollama` | `provider_and_network_adapters` | `not_started` | `register_then_decide` |
| `codex-otel` | `codex/codex-rs/otel` | `pycodex/otel` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-plugin` | `codex/codex-rs/plugin` | `pycodex/plugin` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-process-hardening` | `codex/codex-rs/process-hardening` | `pycodex/process_hardening` | `command_file_sandbox_tools` | `not_started` | `register_then_decide` |
| `codex-protocol` | `codex/codex-rs/protocol` | `pycodex/protocol` | `protocol_and_api_contracts` | `implemented` | `port_behavior` |
| `codex-realtime-webrtc` | `codex/codex-rs/realtime-webrtc` | `pycodex/realtime_webrtc` | `provider_and_network_adapters` | `not_started` | `register_then_decide` |
| `codex-response-debug-context` | `codex/codex-rs/response-debug-context` | `pycodex/response_debug_context` | `core_runtime_and_model_io` | `not_started` | `register_then_decide` |
| `codex-responses-api-proxy` | `codex/codex-rs/responses-api-proxy` | `pycodex/responses_api_proxy` | `core_runtime_and_model_io` | `not_started` | `register_then_decide` |
| `codex-rmcp-client` | `codex/codex-rs/rmcp-client` | `pycodex/rmcp_client` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-rollout` | `codex/codex-rs/rollout` | `pycodex/rollout` | `state_history_files` | `implemented` | `canonical_runtime_package` |
| `codex-rollout-trace` | `codex/codex-rs/rollout-trace` | `pycodex/rollout_trace` | `state_history_files` | `not_started` | `register_then_decide` |
| `codex-sandboxing` | `codex/codex-rs/sandboxing` | `pycodex/sandboxing` | `command_file_sandbox_tools` | `shim` | `transitional_package` |
| `codex-secrets` | `codex/codex-rs/secrets` | `pycodex/secrets` | `auth_identity_secrets` | `not_started` | `register_then_decide` |
| `codex-shell-command` | `codex/codex-rs/shell-command` | `pycodex/shell_command` | `command_file_sandbox_tools` | `implemented` | `port_behavior` |
| `codex-shell-escalation` | `codex/codex-rs/shell-escalation` | `pycodex/shell_escalation` | `command_file_sandbox_tools` | `not_started` | `register_then_decide` |
| `codex-skills` | `codex/codex-rs/skills` | `pycodex/skills` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |
| `codex-state` | `codex/codex-rs/state` | `pycodex/state` | `state_history_files` | `shim` | `partial_runtime_helpers` |
| `codex-stdio-to-uds` | `codex/codex-rs/stdio-to-uds` | `pycodex/stdio_to_uds` | `app_server_transport` | `not_started` | `register_then_decide` |
| `codex-terminal-detection` | `codex/codex-rs/terminal-detection` | `pycodex/terminal_detection` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-test-binary-support` | `codex/codex-rs/test-binary-support` | `pycodex/test_binary_support` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-thread-manager-sample` | `codex/codex-rs/thread-manager-sample` | `pycodex/thread_manager_sample` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-thread-store` | `codex/codex-rs/thread-store` | `pycodex/thread_store` | `state_history_files` | `not_started` | `register_then_decide` |
| `codex-tools` | `codex/codex-rs/tools` | `pycodex/tools` | `user_entrypoints` | `partial` | `selected_helper_port` |
| `codex-tui` | `codex/codex-rs/tui` | `pycodex/tui` | `user_entrypoints` | `shim` | `canonical_compatibility_package` |
| `codex-uds` | `codex/codex-rs/uds` | `pycodex/uds` | `app_server_transport` | `not_started` | `register_then_decide` |
| `codex-utils-absolute-path` | `codex/codex-rs/utils/absolute-path` | `pycodex/utils/absolute_path` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-approval-presets` | `codex/codex-rs/utils/approval-presets` | `pycodex/utils/approval_presets` | `platform_utilities` | `implemented` | `canonical_runtime_package` |
| `codex-utils-cache` | `codex/codex-rs/utils/cache` | `pycodex/utils/cache` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-cargo-bin` | `codex/codex-rs/utils/cargo-bin` | `pycodex/utils/cargo_bin` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-cli` | `codex/codex-rs/utils/cli` | `pycodex/utils/cli` | `platform_utilities` | `implemented` | `port_behavior` |
| `codex-utils-elapsed` | `codex/codex-rs/utils/elapsed` | `pycodex/utils/elapsed` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-fuzzy-match` | `codex/codex-rs/utils/fuzzy-match` | `pycodex/utils/fuzzy_match` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-home-dir` | `codex/codex-rs/utils/home-dir` | `pycodex/utils/home_dir` | `platform_utilities` | `implemented` | `canonical_runtime_package` |
| `codex-utils-image` | `codex/codex-rs/utils/image` | `pycodex/utils/image` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-json-to-toml` | `codex/codex-rs/utils/json-to-toml` | `pycodex/utils/json_to_toml` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-oss` | `codex/codex-rs/utils/oss` | `pycodex/utils/oss` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-output-truncation` | `codex/codex-rs/utils/output-truncation` | `pycodex/utils/output_truncation` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-path` | `codex/codex-rs/utils/path-utils` | `pycodex/utils/path_utils` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-plugins` | `codex/codex-rs/utils/plugins` | `pycodex/utils/plugins` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-pty` | `codex/codex-rs/utils/pty` | `pycodex/utils/pty` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-readiness` | `codex/codex-rs/utils/readiness` | `pycodex/utils/readiness` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-rustls-provider` | `codex/codex-rs/utils/rustls-provider` | `pycodex/utils/rustls_provider` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-sandbox-summary` | `codex/codex-rs/utils/sandbox-summary` | `pycodex/utils/sandbox_summary` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-sleep-inhibitor` | `codex/codex-rs/utils/sleep-inhibitor` | `pycodex/utils/sleep_inhibitor` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-stream-parser` | `codex/codex-rs/utils/stream-parser` | `pycodex/utils/stream_parser` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-utils-string` | `codex/codex-rs/utils/string` | `pycodex/utils/string` | `platform_utilities` | `implemented` | `canonical_runtime_package` |
| `codex-utils-template` | `codex/codex-rs/utils/template` | `pycodex/utils/template` | `platform_utilities` | `not_started` | `register_then_decide` |
| `codex-v8-poc` | `codex/codex-rs/v8-poc` | `pycodex/v8_poc` | `other_or_experimental` | `not_started` | `register_then_decide` |
| `codex-web-search-extension` | `codex/codex-rs/ext/web-search` | `pycodex/ext/web_search` | `extensions_mcp_plugins_skills` | `deferred` | `compatibility_shim_only` |

## Next Use

- Use this file to decide where existing Python code should live.
- Do not use this file as proof that behavior is implemented or verified.
- For each active Python package, keep a local README explaining Rust crate/module coverage.
- For each touched test, add Rust source comments where possible.