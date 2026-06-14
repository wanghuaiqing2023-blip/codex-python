# Core Test Status

Last updated: 2026-06-10

Purpose: track unit/integration test coverage for the Python `pycodex.core` port without bloating `PORTING_STATUS.md`.

Use this file for:

- Core module test coverage matrix.
- Newly added test files.
- Known missing tests.
- Deferred test execution notes.
- Slow or flaky test notes.

Do not use this file for implementation progress. Keep implementation status in `PORTING_STATUS.md` or per-turn notes.

## Current policy

- Prefer existing Rust tests first when upstream Rust tests exist.
- Prefer focused module tests over broad smoke tests.
- Broad guard tests are allowed only when they enforce coverage discipline or import/public-surface contracts.
- Do not add empty placeholder tests just to satisfy coverage names.
- If a module has broad integration coverage instead of a direct file, document the alias here or in the coverage guard.

Primary parity index:

- `CORE_RUST_TEST_PARITY.md`

## 2026-06-09 - Rust core test parity inventory

Created `CORE_RUST_TEST_PARITY.md` as the source-of-truth worklist for test parity from existing Rust tests.

Inventory result:

```text
core/src unit/module test files: 97
core/src Rust test functions found: 1717
core/src files with Python mapping: 97
core/src files missing Python mapping: 0

core/tests integration test files: 88
core/tests Rust test functions found: 762
core/tests files with Python mapping: 83
core/tests files missing Python mapping: 5

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/safety_check_downgrade.rs`
with `tests/test_core_suite_safety_check_downgrade.py`; focused run:
`python -m pytest tests/test_core_suite_safety_check_downgrade.py -q` -> 7 passed.

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/search_tool.rs`
with `tests/test_core_suite_search_tool.py`; focused run:
`python -m pytest tests/test_core_suite_search_tool.py -q` -> 14 passed.

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/shell_command.rs`
with `tests/test_core_suite_shell_command.py`; focused run:
`python -m pytest tests/test_core_suite_shell_command.py -q` -> 9 passed.

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/shell_serialization.rs`
with `tests/test_core_suite_shell_serialization.py`; focused run:
`python -m pytest tests/test_core_suite_shell_serialization.py -q` -> 9 passed.

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/skill_approval.rs`
with `tests/test_core_suite_skill_approval.py`; focused run:
`python -m pytest tests/test_core_suite_skill_approval.py -q` -> 2 passed.

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/spawn_agent_description.rs`
with `tests/test_core_suite_spawn_agent_description.py`; focused run:
`python -m pytest tests/test_core_suite_spawn_agent_description.py -q` -> 1 passed.

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/sqlite_state.rs`
with `tests/test_core_suite_sqlite_state.py`; focused run: `python -m pytest tests/test_core_suite_sqlite_state.py -q` -> 7 passed.
```

Policy update:

- Future deep tests should start from `CORE_RUST_TEST_PARITY.md`.
- Broad Python module coverage guards remain useful, but they are not proof of Rust test parity.
- Prefer filling missing Rust unit/module mappings before tackling full runtime harness integration tests.







## 2026-06-11 - hooks_mcp Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/hooks_mcp.rs` -> `tests/test_core_suite_hooks_mcp.py`.

Added suite-level parity coverage for MCP hook payload behavior: prefixed and non-prefixed MCP tool namespaces both surface the canonical `mcp__rmcp__echo` hook tool name, PreToolUse block/rewrite outcomes preserve the original MCP input, and PostToolUse receives structured MCP tool responses plus additional-context propagation.

Validation:
`python -m pytest tests/test_core_suite_hooks_mcp.py tests/test_core_hook_runtime.py tests/test_core_tool_registry.py tests/test_protocol_mcp_dynamic_tools.py -q`

Result:
`65 passed in 0.75s`

## 2026-06-11 - image_rollout Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/image_rollout.rs` -> `tests/test_core_suite_image_rollout.py`.

Added suite-level parity coverage for rollout persistence of image user input:
copy/paste local images persist as local image open tag, `input_image`,
image close tag, and trailing text; drag/drop data URL images persist directly
as `input_image` plus trailing text. The test writes and reads a rollout JSONL
so the persisted `ResponseItem` shape is covered without recreating the Rust
mock SSE fixture.

Validation:
`python -m pytest tests/test_core_suite_image_rollout.py -q`

Result:
`2 passed in 0.66s`

## 2026-06-11 - items Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/items.rs` -> `tests/test_core_suite_items.py`.

Added suite-level parity coverage for the Rust item integration behaviors:
user/assistant/reasoning/web-search/image-generation turn item shapes, legacy
begin/end events, plan-mode proposed-plan extraction and stripping, citation
stripping across chunk boundaries, and agent/reasoning delta metadata.

Validation:
`python -m pytest tests/test_core_suite_items.py -q`

Result:
`14 passed in 0.54s`

## 2026-06-11 - json_result Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/json_result.rs` -> `tests/test_core_suite_json_result.py`.

Added suite-level parity coverage for final output JSON schema request shaping:
`text.format` uses `codex_output_schema`, `json_schema`, strict mode, and the
provided schema; the assistant message body remains parseable JSON with the
expected `explanation` and `final_answer` fields.

Validation:
`python -m pytest tests/test_core_suite_json_result.py -q`

Result:
`2 passed in 0.52s`

## 2026-06-11 - model_overrides Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/model_overrides.rs` -> `tests/test_core_suite_model_overrides.py`.

Added suite-level parity coverage for runtime thread settings overrides:
updating model and reasoning effort applies to the in-memory session and emits
`thread_settings_applied`, but does not modify an existing `config.toml` and
does not create one when absent.

Validation:
`python -m pytest tests/test_core_suite_model_overrides.py -q`

Result:
`2 passed in 0.53s`

## 2026-06-11 - live_cli Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/live_cli.rs` -> `tests/test_core_suite_live_cli.py`.

The Rust file contains ignored live OpenAI smoke tests. Python mirrors the CLI
behavior contract with deterministic fake Responses output: one test drives an
`apply_patch` custom tool call that creates `hello.txt`; the other drives an
`exec_command` function call and confirms the current working directory is
surfaced in both tool output and final stdout.

Validation:
`python -m pytest tests/test_core_suite_live_cli.py -q`

Result:
`2 passed in 0.98s`

## 2026-06-11 - mcp_turn_metadata Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/mcp_turn_metadata.rs` -> `tests/test_core_suite_mcp_turn_metadata.py`.

Added suite-level parity coverage for Apps MCP request metadata after same-turn
user input requests. Both the approval-elicitation path and the
`request_user_input` tool path are represented by marking the turn metadata
state and asserting the resulting Apps MCP request `_meta` includes
`x-codex-turn-metadata.user_input_requested_during_turn == true`.

Validation:
`python -m pytest tests/test_core_suite_mcp_turn_metadata.py -q`

Result:
`2 passed in 0.52s`
## 2026-06-10 - hooks Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/hooks.rs` -> `tests/test_core_suite_hooks.py`.

Added a suite-level parity anchor for the 40 Rust hook integration cases. The new tests cover the stable Python boundary for Stop hook continuation prompts, SessionStart/UserPromptSubmit ordering payloads, PermissionRequest payload aliases, PreToolUse block/rewrite outcomes, PostToolUse replacement feedback, additional context messages, and apply_patch/Edit alias post-tool payloads. This complements the existing lower-level hook runtime, tool parallel, tool router, and orchestrator tests rather than recreating Rust's remote SSE fixture harness.

Validation:
`python -m pytest tests/test_core_suite_hooks.py tests/test_core_hook_runtime.py tests/test_core_context_hook_additional_context.py tests/test_protocol_items.py -q`

Result:
`67 passed in 0.99s`
## 2026-06-10 - hierarchical_agents Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/hierarchical_agents.rs` -> `tests/test_core_suite_hierarchical_agents.py`.

Added focused parity coverage for `Feature::ChildAgentsMd` user-instruction composition: the hierarchical AGENTS.md guidance is appended after project `AGENTS.md` text and is emitted even when no project doc exists, preserving the final `# AGENTS.md instructions for ...` contextual wrapper shape.

Validation:
`python -m pytest tests/test_core_suite_hierarchical_agents.py tests/test_core_agents_md.py tests/test_core_context_user_instructions.py -q`

Result:
`23 passed, 1 skipped in 1.06s`
## 2026-06-10 - fork_thread Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/fork_thread.rs` -> `tests/test_core_suite_fork_thread.py`.

Added focused parity coverage for repeated `ForkSnapshot::TruncateBeforeNthUserMessage` truncation and `fork_thread_from_history` accepting `InitialHistory::Resumed` with no source rollout path. Also aligned `ThreadManager.remove_thread` with the existing bool removal contract.

Validation:
`python -m pytest tests/test_core_suite_fork_thread.py tests/test_core_thread_manager.py tests/test_core_thread_rollout_truncation.py -q`

Result:
`30 passed in 0.90s`
## 2026-06-10 - deprecation_notice Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/deprecation_notice.rs` -> `tests/test_core_suite_deprecation_notice.py`.

Added focused parity coverage for startup deprecation notices produced by legacy unified-exec feature usage, both boolean values of the deprecated `web_search_request` feature flag, and `use_legacy_landlock`, including exact Rust summary/details text and protocol `DeprecationNoticeEvent` round-trip shape.

Validation:
python -m pytest tests/test_core_suite_deprecation_notice.py tests/test_core_features.py tests/test_protocol_protocol.py::ProtocolProtocolTests::test_deprecation_notice_event_matches_upstream_protocol_contract -q

Result:
18 passed, 2 subtests passed in 0.69s
## 2026-06-10 - compact_resume_fork Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/compact_resume_fork.rs` -> `tests/test_core_suite_compact_resume_fork.py`.

Added focused parity coverage for compacted replacement-history prefixes across resume/fork continuations, second-compaction resume bases, rollback behind compaction preserving compacted summary history while dropping the edited turn, and rollback trimming pre-turn context updates before a follow-up turn. Also aligned rollout reconstruction rollback trimming so adjacent pre-turn developer/context update items are removed with the rolled-back user turn, matching the Rust integration behavior.

Validation:
python -m pytest tests/test_core_suite_compact_resume_fork.py tests/test_core_rollout.py tests/test_core_thread_rollout_truncation.py -q

Result:
71 passed in 1.01s
## 2026-06-10 - compact_remote_parity Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/compact_remote_parity.rs` -> `tests/test_core_suite_compact_remote_parity.py`.

Added focused parity coverage for legacy remote compact versus Responses compaction v2 request-shape equivalence, API-key service-tier upgrade behavior, manual compact hook payload view parity, pre-turn and mid-turn auto compaction replacement-history parity, and the Rust integration test's normalization helper cases for temporary skill paths and shell wall times.

Validation:
python -m pytest tests/test_core_suite_compact_remote_parity.py tests/test_core_compact_remote.py tests/test_core_compact_remote_v2.py -q

Result:
57 passed, 4 subtests passed in 0.92s
## 2026-06-10 - collaboration_instructions Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/collaboration_instructions.rs` -> `tests/test_core_suite_collaboration_instructions.py`.

Added focused parity coverage for collaboration-mode developer instruction XML rendering, default omission, session and turn overrides, include flag suppression, update/no-op behavior, mode-change behavior, resume replay semantics, and empty instruction omission.

Validation:
python -m pytest tests/test_core_suite_collaboration_instructions.py tests/test_core_context_collaboration_mode_instructions.py tests/test_core_context_updates.py -q

Result:
29 passed in 0.69s
## 2026-06-10 - client_websockets Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/client_websockets.rs` -> `tests/test_core_suite_client_websockets.py`.

Added focused parity coverage for Responses websocket request shape, OpenAI beta/header metadata, provider websocket enablement, response.processed gating, preconnect/prewarm connection reuse, cached session reuse, trace and turn metadata forwarding, v2 incremental `previous_response_id` behavior, full-create fallback on non-prefix or changed request fields, timing-metrics headers, websocket stream attempt metadata, rate-limit/reasoning metadata state, and fallback/error-path boundaries.

Validation:
python -m pytest tests/test_core_suite_client_websockets.py tests/test_core_client.py -q

Result:
171 passed in 0.73s
## 2026-06-10 - apply_patch_cli Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/apply_patch_cli.rs` -> `tests/test_core_suite_apply_patch_cli.py`.

Added focused parity coverage for direct apply_patch add/update/delete/move behavior, multiple hunks, trailing newlines, insert-only hunks, overwrite moves/adds, verification errors, path traversal and symlink escape rejection, heredoc interception, streamed patch progress, EOF anchors, change-context disambiguation, and apply-patch diff/action metadata. Also tightened Python apply_patch verification so patch paths resolve inside the detected workspace root instead of escaping through `..` or symlinks.

Validation:
python -m pytest tests/test_core_suite_apply_patch_cli.py tests/test_core_unified_exec_handler.py::CoreUnifiedExecHandlerTests::test_intercept_exec_apply_patch_applies_direct_patch_without_spawning_shell tests/test_core_unified_exec_handler.py::CoreUnifiedExecHandlerTests::test_exec_command_handler_intercepts_apply_patch_shell_command -q

Result:
35 passed, 2 skipped in 0.73s
## 2026-06-10 - all.rs Rust integration aggregator accounted

Mapped one `core/tests` Rust integration file with no standalone behavior tests:

- `codex/codex-rs/core/tests/all.rs` -> not applicable; it only aggregates the `suite` integration modules with `mod suite`.

No Python test file was added because the Rust file contains no test functions or behavior contract beyond test-binary aggregation.

Validation:
No focused pytest run required for this no-op aggregator mapping.

Result:
Accounted as mapped; next actionable missing Rust integration file is `codex/codex-rs/core/tests/suite/apply_patch_cli.rs`.
## 2026-06-10 - approvals Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/approvals.rs` -> `tests/test_core_suite_approvals.py`.

Added focused parity coverage for approval decision sets, apply-patch/session approval decisions, execpolicy amendment decisions, prefix-rule propagation/matching, fallback amendment behavior for compound commands, network policy amendment decisions, and network approval available decisions.

Validation:
python -m pytest tests/test_core_suite_approvals.py tests/test_core_exec_policy.py tests/test_protocol_permission_models.py -q

Result:
91 passed, 31 subtests passed in 0.82s
## 2026-06-10 - CLI stream Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/cli_stream.rs` -> `tests/test_core_suite_cli_stream.py`.

Added focused parity coverage for streamed Responses SSE output, OpenAI base URL endpoint routing, model instructions/profile instruction propagation, session rollout file creation and response item persistence, and git metadata round-trip serialization.

Validation:

```text
python -m pytest tests/test_core_suite_cli_stream.py tests/test_core_http_transport.py tests/test_protocol_models_content.py -q
```

Result:

```text
88 passed, 33 subtests passed in 0.99s
```
## 2026-06-10 - agent websocket Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/agent_websocket.rs` -> `tests/test_core_suite_agent_websocket.py`.

Added focused parity coverage for websocket shell-chain request deltas, startup prewarm request metadata, delayed preconnect tolerance, Responses WebSocket V2 beta headers, previous response chaining, and per-turn service tier updates/drops.

Validation:

```text
python -m pytest tests/test_core_suite_agent_websocket.py tests/test_core_client_websocket_request.py tests/test_core_client_metadata.py -q
```

Result:

```text
17 passed in 0.76s
```
## 2026-06-10 - additional context Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/additional_context.rs` -> `tests/test_core_suite_additional_context.py`.

Added focused parity coverage for model-visible additional context, user-text preservation, trusted/application role routing, cross-turn deduplication, changed-value re-emission, and truncation before model input.

Validation:

```text
python -m pytest tests/test_core_suite_additional_context.py tests/test_core_context_fragments.py tests/test_core_context_hook_additional_context.py -q
```

Result:

```text
13 passed in 0.74s
```
## 2026-06-10 - abort tasks Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/abort_tasks.rs` -> `tests/test_core_suite_abort_tasks.py`.

Added focused parity coverage for interrupt-visible `<turn_aborted>` markers, synthesized aborted function-call outputs, and follow-up history containing the abort marker. This keeps the Python test fast while preserving the Rust integration contract without spawning a long-running shell process.

Validation:

```text
python -m pytest tests/test_core_suite_abort_tasks.py tests/test_core_contextual_user_message.py tests/test_core_compact_remote.py -q
```

Result:

```text
40 passed in 0.91s
```
## 2026-06-10 - responses headers Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/responses_headers.rs` -> `tests/test_core_responses_headers.py`.

Added focused parity coverage for review/other subagent identity headers, Responses API installation metadata, reasoning summary override serialization, and turn metadata header propagation.

Validation:

```text
python -m pytest tests/test_core_responses_headers.py tests/test_core_client_metadata.py tests/test_core_client_reasoning.py -q
```

Result:

```text
15 passed in 0.73s
```
## 2026-06-10 - session root Rust test parity

Mapped the final missing `core/src` Rust unit/module test file:

- `codex/codex-rs/core/src/session/tests.rs` -> `tests/test_core_session_tests.py` plus existing session/runtime/goal/network parity suites.

Added focused parity coverage for assistant message stream parser seeding/finish boundaries, network policy saved fragments, mailbox delivery deferral/reopen behavior, and goal accounting helpers.

Validation:

```text
python -m pytest tests/test_core_session_tests.py tests/test_core_session_handlers.py tests/test_core_session_input_queue.py tests/test_core_session_request_permissions.py tests/test_core_session_guardian.py tests/test_core_session_review.py tests/test_core_session_rollout_reconstruction.py tests/test_core_session_multi_agents.py tests/test_core_goals.py tests/test_core_client.py tests/test_core_network_proxy_loader.py tests/test_core_context_network_rule_saved.py -q
```

Result:

```text
277 passed, 15 subtests passed in 1.45s
```

Note: the broader `tests/test_core_session_runtime.py` file currently has two pre-existing focused-suite failures unrelated to the new session root parity file; they should be handled as a separate bug-fix slice.
## 2026-06-09 - mapped existing Rust unit tests

Updated `CORE_RUST_TEST_PARITY.md` to mark existing Python coverage for:

- `codex/codex-rs/core/src/agent/role_tests.rs` -> `tests/test_core_agent_role_coordinate.py`, `tests/test_core_agent_roles.py`
- `codex/codex-rs/core/src/plugins/render_tests.rs` -> `tests/test_core_app_plugin_rendering.py`
- `codex/codex-rs/core/src/tools/handlers/dynamic_tests.rs` -> `tests/test_core_dynamic_tool_handler.py`
- `codex/codex-rs/core/src/tools/handlers/request_user_input_tests.rs` -> `tests/test_core_request_user_input_handler.py`
- `codex/codex-rs/core/src/tools/registry_tests.rs` -> `tests/test_core_tool_registry.py`
- `codex/codex-rs/core/src/tools/router_tests.rs` -> `tests/test_core_tool_router.py`
- `codex/codex-rs/core/src/tools/handlers/mcp_resource_spec_tests.rs` -> `tests/test_core_mcp_resource_handler.py`
- `codex/codex-rs/core/src/tools/handlers/mcp_resource_tests.rs` -> `tests/test_core_mcp_resource_handler.py`
- `codex/codex-rs/core/src/tools/handlers/mcp_search_tests.rs` -> `tests/test_core_mcp_tool_handler.py`
- `codex/codex-rs/core/src/tools/handlers/request_user_input_spec_tests.rs` -> `tests/test_core_request_user_input_handler.py`
- `codex/codex-rs/core/src/tools/handlers/test_sync_spec_tests.rs` -> `tests/test_core_test_sync_handler.py`
- `codex/codex-rs/core/src/unified_exec/head_tail_buffer_tests.rs` -> `tests/test_core_unified_exec.py`
- `codex/codex-rs/core/src/unified_exec/mod_tests.rs` -> `tests/test_core_unified_exec.py`, `tests/test_core_unified_exec_module_contract.py`
- `codex/codex-rs/core/src/unified_exec/process_manager_tests.rs` -> `tests/test_core_unified_exec.py`
- `codex/codex-rs/core/src/unified_exec/process_tests.rs` -> `tests/test_core_unified_exec.py`
- `codex/codex-rs/core/src/tools/handlers/agent_jobs_spec_tests.rs` -> `tests/test_core_agent_jobs.py`
- `codex/codex-rs/core/src/tools/handlers/apply_patch_spec_tests.rs` -> `tests/test_core_apply_patch.py`
- `codex/codex-rs/core/src/tasks/mod_tests.rs` -> `tests/test_core_tasks_root.py`
- `codex/codex-rs/core/src/config/network_proxy_spec_tests.rs` -> `tests/test_core_network_proxy_loader.py`
- `codex/codex-rs/core/src/exec_policy_windows_tests.rs` -> `tests/test_core_exec_policy.py`
- `codex/codex-rs/core/src/tools/runtimes/shell/unix_escalation_tests.rs` -> `tests/test_core_tool_runtimes.py`
- `codex/codex-rs/core/src/tools/runtimes/mod_tests.rs` -> `tests/test_core_tool_runtimes.py`

These were false negatives from the automatic candidate-name matcher, not missing behavior tests.

Validation:

```text
python -m pytest tests/test_core_agent_role_coordinate.py tests/test_core_agent_roles.py tests/test_core_app_plugin_rendering.py -q
```

Result:

```text
42 passed in 0.91s
```

Validation:

```text
python -m pytest tests/test_core_dynamic_tool_handler.py tests/test_core_request_user_input_handler.py tests/test_core_tool_registry.py tests/test_core_tool_router.py -q
```

Result:

```text
106 passed in 1.35s
```

Fix while validating:

- Restored `ToolPlanOptions` default namespace-tool behavior when a lightweight turn context has no explicit provider capabilities, so extension namespace tools remain model-visible and dispatchable like Rust `router_tests.rs::extension_tool_executors_are_model_visible_and_dispatchable`.

Validation:

```text
python -m pytest tests/test_core_mcp_resource_handler.py tests/test_core_mcp_tool_handler.py tests/test_core_request_user_input_handler.py tests/test_core_test_sync_handler.py -q
```

Result:

```text
45 passed in 1.08s
```

Validation:

```text
python -m pytest tests/test_core_unified_exec.py tests/test_core_unified_exec_module_contract.py -q
```

Result:

```text
64 passed in 2.40s
```

Validation:

```text
python -m pytest tests/test_core_agent_jobs.py tests/test_core_apply_patch.py -q
```

Result:

```text
77 passed, 3 subtests passed in 1.40s
```

Test fix while validating:

- Updated `tests/test_core_agent_jobs.py` spawn tests to provide explicit `state_db` and `agent_control` doubles, matching the Rust-aligned runtime dependency boundary instead of relying on placeholder execution without those interfaces.

Validation:

```text
python -m pytest tests/test_core_tasks_root.py -q
```

Result:

```text
8 passed in 1.16s
```

Tests added while validating:

- Added the remaining Rust `tasks/mod_tests.rs` metric cases for inactive network proxy turns, memory reads allowed with citations, and automatic local compact metrics.

Validation:

```text
python -m pytest tests/test_core_network_proxy_loader.py -q
```

Result:

```text
31 passed in 0.43s
```

Fixes while validating:

- Aligned `NetworkProxySpec.build_state_with_audit_metadata` with Rust by returning a `NetworkProxyState` that carries `NetworkProxyAuditMetadata`.

Tests added while validating:

- Added the remaining Rust `network_proxy_spec_tests.rs` cases for audit metadata threading, mutable user allowlist entries under managed baselines, and `managed_allowed_domains_only` disabling default allowlist expansion.

Validation:

```text
python -m pytest tests/test_core_exec_policy.py -q
```

Result:

```text
33 passed, 24 subtests passed in 1.28s
```

Tests added while validating:

- Added the remaining Rust `exec_policy_windows_tests.rs` cases for PowerShell inner-command prompt rules, allow rules, known-safe unmatched PowerShell words, and dangerous inner commands proposing the inner-command amendment.

Validation:

```text
python -m pytest tests/test_core_tool_runtimes.py -q
```

Result:

```text
130 passed in 0.67s
```

Fixes while validating:

- Aligned `CoreShellActionProvider.process_decision` with Python `Decision.FORBIDDEN` and made `Decision` visible in the runtime module.
- Aligned permission hook decisions with the Python `ReviewDecision` dataclass API while preserving Rust hook behavior (`allow` short-circuits prompt).

Tests added while validating:

- Added the Rust `unix_escalation_tests.rs::execve_permission_request_hook_short_circuits_prompt` parity case using an in-memory permission hook and fake guardian fallback.

Validation:

```text
python -m pytest tests/test_core_tool_runtimes.py -q
```

Result:

```text
136 passed in 0.65s
```

Tests added while validating:

- Added direct Rust `tools/runtimes/mod_tests.rs` snapshot parity anchors for single-quote escaping, bash/sh bootstrap shells, dot-alias cwd matching, path/secret/unset override handling, and live proxy env restoration.

## 2026-06-09 - core module test coverage guards

Added two broad guard tests for the `pycodex.core` module set:

- `tests/test_core_module_import_contracts.py`
- `tests/test_core_module_test_coverage.py`

Coverage intent:

- Unit-level guard: import every module discovered under `pycodex.core`, check that `__all__` exports are string names, and verify root `pycodex.core.__all__` entries resolve to objects.
- Integration-level guard: scan `pycodex/core/**/*.py` and require each module to have a direct `test_core_*` file or an explicit alias to a broader focused test file.

Notes:

- These tests are the first layer for adding unit and integration coverage across every core module.
- They do not replace deeper Rust-derived behavior tests.
- They are intended to produce a concrete missing-coverage list for follow-up work.
- Tests were not run when added.

## 2026-06-09 - core module coverage guard validation

Ran:

```text
python -m pytest tests/test_core_module_import_contracts.py tests/test_core_module_test_coverage.py -q
```

Result:

```text
4 passed in 1.95s
```

Fixes made while validating:

- Repaired literal `` `r`n `` text pollution in `pycodex/core/__init__.py`.
- Removed stray orphaned `__all__` string entries at the end of `pycodex/core/__init__.py`.
- Added missing root exports for `apply_git_patch` and `diff_since_latest_init`.
- Fixed `pycodex.network_proxy.ConfigLayersLoader` import-time forward reference to `ConfigLayerEntry`.
- Added v1 multi-agent compatibility aliases in `pycodex/core/tools/handlers/multi_agents.py` for `CloseAgentHandler`, `SpawnAgentHandler`, and `WaitAgentHandler`.
- Added explicit module-to-test aliases in `tests/test_core_module_test_coverage.py` for modules covered by broader coordinate or focused handler tests.

Next testing work:

- Add deeper Rust-derived behavior tests for modules that currently only have import/coverage guard coverage.
- Keep slow or broad test runs separate from this guard layer.

## 2026-06-09 - first direct behavior tests for shallow-covered modules

Added direct Rust-derived behavior tests for three modules that previously relied on broader coverage aliases:

- `tests/test_core_state_service.py`
- `tests/test_core_tools_lifecycle_direct.py`
- `tests/test_core_tools_parallel_direct.py`

Coverage intent:

- `codex-core::state::service`: service handle container field preservation, path normalization, and boolean flag validation.
- `codex-core::tools::lifecycle`: direct/code-mode source conversion, start/finish input construction, context store propagation, and contributor notification.
- `codex-core::tools::parallel`: abort message formatting, aborted result shaping, terminal-outcome cancellation decision, and failure response shaping.

Tests were not run when added.

Validation:

```text
python -m pytest tests/test_core_state_service.py tests/test_core_tools_lifecycle_direct.py tests/test_core_tools_parallel_direct.py -q
```

Result:

```text
9 passed in 2.09s
```

## 2026-06-09 - session turn and rollout reconstruction tests

Added direct coordinate tests for:

- `tests/test_core_session_rollout_reconstruction.py`

Coverage intent:

- `codex-core::session::rollout_reconstruction`: Rust `turn_ids_are_compatible` predicate and Python sync/async facade equivalence for empty replay.

Also selected existing Rust-aligned tests for the same session/turn cluster:

- `tests/test_core_turn_prompt.py`
- `tests/test_core_turn_request.py`

Tests not yet recorded as run in this section.

Validation:

```text
python -m pytest tests/test_core_session_rollout_reconstruction.py tests/test_core_turn_prompt.py tests/test_core_turn_request.py -q
```

Result:

```text
14 passed in 1.79s
```

## 2026-06-09 - core session turn Rust test parity

Rust source:

```text
codex/codex-rs/core/src/session/turn_tests.rs
```

Python parity:

```text
tests/test_core_client.py::test_plan_mode_uses_contributed_turn_item_for_last_agent_message
```

Covered Rust behavior:

- `plan_mode_uses_contributed_turn_item_for_last_agent_message`: plan-mode assistant item completion applies turn item contributors before deriving `last_agent_message`.

Validation:

```text
python -m pytest tests/test_core_client.py -q -k plan_mode_uses_contributed_turn_item_for_last_agent_message
1 passed, 132 deselected in 0.72s

python -m pytest tests/test_core_client.py -q
133 passed in 0.57s
```

## 2026-06-09 - core test_sync handler Rust module parity

Rust source:

```text
codex/codex-rs/core/src/tools/handlers/test_sync.rs
```

Python parity:

```text
pycodex/core/tools/handlers/test_sync.py
tests/test_core_test_sync_handler.py
```

Covered Rust behavior:

- `TestSyncHandler` exposes `test_sync_tool`, supports parallel tool calls, accepts function payloads only, parses sleep/barrier arguments, validates barrier participant/timeout errors, releases concurrent waiters, and returns successful `ok` output.

Validation:

```text
python -m pytest tests/test_core_test_sync_handler.py -q
7 passed in 0.69s
```

## 2026-06-09 - core test_sync spec Rust module parity

Rust source:

```text
codex/codex-rs/core/src/tools/handlers/test_sync_spec.rs
```

Python parity:

```text
pycodex/core/tools/handlers/test_sync.py
tests/test_core_test_sync_handler.py::TestSyncHandlerTests::test_test_sync_tool_matches_expected_spec
```

Covered Rust behavior:

- `create_test_sync_tool` exposes the `test_sync_tool` function spec with non-strict schema, sleep fields, barrier object fields, required `id`/`participants`, and no additional properties.

Validation:

```text
python -m pytest tests/test_core_test_sync_handler.py -q
7 passed in 0.69s
```

## 2026-06-09 - core session guardian Rust test parity

Rust source:

```text
codex/codex-rs/core/src/session/tests/guardian_tests.rs
```

Python parity:

```text
tests/test_core_session_guardian.py
```

Covered Rust tests:

- `request_permissions_routes_to_guardian_when_reviewer_is_enabled`
- `request_permissions_guardian_review_stops_when_cancelled`
- `guardian_allows_shell_command_additional_permissions_requests_past_policy_validation`
- `strict_auto_review_turn_grant_forces_guardian_for_shell_command_policy_skip`
- `guardian_allows_unified_exec_additional_permissions_requests_past_policy_validation`
- `process_compacted_history_preserves_separate_guardian_developer_message`
- `shell_command_allows_sticky_turn_permissions_without_inline_request_permissions_feature`
- `guardian_subagent_does_not_inherit_parent_exec_policy_rules`

Validation:

```text
python -m pytest tests/test_core_session_guardian.py -q
8 passed in 0.61s
```
## 2026-06-10 - guardian root Rust test parity

Updated `CORE_RUST_TEST_PARITY.md` to map `codex/codex-rs/core/src/guardian/tests.rs` to existing guardian coverage plus `tests/test_core_guardian_tests.py`.

Added focused parity coverage for guardian transcript rendering, transcript collection, prompt full/delta/stale cursor behavior, network access prompt layout, parent session id inclusion, guardian approval routing, and guardian review session config semantics.

Implementation fix while testing:

- Filled missing `pycodex.core.guardian.prompt` helper functions used by the public prompt builders and transcript collectors.

Validation:

```text
python -m pytest tests/test_core_guardian_root.py tests/test_core_guardian_prompt.py tests/test_core_guardian_approval_request.py tests/test_core_guardian_review.py tests/test_core_guardian_tests.py -q
```

Result:

```text
33 passed in 0.84s
```
## 2026-06-10 - multi-agents handler Rust test parity

Updated `CORE_RUST_TEST_PARITY.md` to map `codex/codex-rs/core/src/tools/handlers/multi_agents_tests.rs` to existing V1/V2/common/session multi-agent Python coverage.

Coverage files:

- `tests/test_core_multi_agents_common.py`
- `tests/test_core_multi_agents_spec.py`
- `tests/test_core_multi_agents_v1_handler.py`
- `tests/test_core_multi_agents_v2_handler.py`
- `tests/test_core_session_multi_agents.py`

Validation:

```text
python -m pytest tests/test_core_multi_agents_common.py tests/test_core_multi_agents_spec.py tests/test_core_multi_agents_v1_handler.py tests/test_core_multi_agents_v2_handler.py tests/test_core_session_multi_agents.py -q
```

Result:

```text
78 passed, 6 subtests passed in 0.90s
```
## 2026-06-10 - config loader Rust test parity

Added `tests/test_core_config_loader.py` and updated `CORE_RUST_TEST_PARITY.md` to map `codex/codex-rs/core/src/config/config_loader_tests.rs` to config loader/root/permissions/network/schema/exec-policy coverage.

The new tests cover loader behavior clusters for relative path resolution, requirements-managed permission profiles, allowed-permission fallback validation, guardian policy config normalization, and managed network proxy requirement errors.

Validation:

```text
python -m pytest tests/test_core_config_loader.py tests/test_core_config_root.py tests/test_core_config_permissions.py tests/test_core_network_proxy_loader.py -q
```

Result:

```text
64 passed, 4 subtests passed in 0.81s
```
## 2026-06-10 - config root Rust test parity

Added `tests/test_core_config.py` and updated `CORE_RUST_TEST_PARITY.md` to map `codex/codex-rs/core/src/config/config_tests.rs` to top-level config parity plus existing config/root/loader/permissions/network/protocol/exec/multi-agent coverage.

The new tests cover top-level config defaults, auth credential store resolution, web-search protocol config, default permission profile selection, requirements fallback, approval reviewer protocol values, shell environment policy defaults, and TUI-adjacent config defaults.

Validation:

```text
python -m pytest tests/test_core_config.py tests/test_core_config_root.py tests/test_core_config_loader.py tests/test_core_config_permissions.py tests/test_core_config_otel.py tests/test_protocol_config_types.py tests/test_core_skill_config_rules.py tests/test_config_overrides.py tests/test_exec_config_plan.py tests/test_core_network_proxy_loader.py -q
```

Result:

```text
188 passed, 12 subtests passed in 1.44s
```









## 2026-06-11 - model_switching.rs Rust suite parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/model_switching.rs` -> `tests/test_core_suite_model_switching.py`.

Added suite-level parity coverage for model switching behavior: model-instruction developer updates, avoiding duplicate personality updates during model changes, service-tier request omission/application rules, image-history normalization when switching between image-capable and text-only models, rollback after generated-image turns, and context-window selection after model downshift.

Focused validation:

`python -m pytest tests/test_core_suite_model_switching.py -q`

Result: 12 passed in 0.54s.


## 2026-06-11 - model_visible_layout.rs Rust suite parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/model_visible_layout.rs` -> `tests/test_core_suite_model_visible_layout.py`.

Added suite-level parity coverage for model-visible request layout behavior: turn override context update ordering, cwd-only AGENTS.md refresh omission, resume prompt ordering with model/personality changes, model override matching rollout model suppressing model-switch instructions, and environment context subagent rendering.

Focused validation:

`python -m pytest tests/test_core_suite_model_visible_layout.py -q`

Result: 6 passed in 0.57s.


## 2026-06-11 - models_cache_ttl.rs Rust suite parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/models_cache_ttl.rs` -> `tests/test_core_suite_models_cache_ttl.py`.

Added a real Python models-manager cache slice and suite-level parity coverage for Rust cache TTL/version behavior: matching response ETag renews cache freshness without another remote models fetch, matching client version uses the cache, and missing or different client versions refresh from the remote catalog.

Focused validation:

`python -m pytest tests/test_core_suite_models_cache_ttl.py -q`

Result: 4 passed in 0.19s.


## 2026-06-11 - models_etag_responses.rs Rust suite parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/models_etag_responses.rs` -> `tests/test_core_suite_models_etag_responses.py`.

Added suite-level parity coverage for response-side models ETag refresh behavior: a mismatched ETag refreshes the persisted models cache once, and a duplicate matching ETag in the same logical flow does not trigger another models fetch.

Focused validation:

`python -m pytest tests/test_core_suite_models_etag_responses.py -q`

Result: 1 passed in 0.18s.


## 2026-06-11 - openai_file_mcp.rs Rust suite parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/openai_file_mcp.rs` -> `tests/test_core_suite_openai_file_mcp.py`.

Added suite-level parity coverage for Codex Apps OpenAI file params: model-visible tool schema marks file params as absolute local path inputs, local file path arguments are uploaded before MCP tool dispatch, and the PostToolUse-style hook input receives the uploaded OpenAI file payload rather than the original path.

Focused validation:

`python -m pytest tests/test_core_suite_openai_file_mcp.py -q`

Result: 1 passed in 0.53s.


## 2026-06-11 - otel.rs Rust suite parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/otel.rs` -> `tests/test_core_suite_otel.py`.

Added a lightweight `pycodex.core.otel_events` telemetry payload boundary and suite-level parity coverage for Rust otel behavior: log field extraction, API/conversation/SSE events, failed/completed response telemetry, response span fields, tool result telemetry, and shell tool decision telemetry.

Focused validation:

`python -m pytest tests/test_core_suite_otel.py -q`

Result: 24 passed in 0.54s.


## 2026-06-11 - override_updates.rs Rust suite parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/override_updates.rs` -> `tests/test_core_suite_override_updates.py`.

Added suite-level parity coverage for thread settings overrides submitted without a user turn: permissions, environment/cwd, and collaboration-mode overrides update session state and emit the settings-applied event without recording model-visible context updates, history batches, or rollout flushes.

Focused validation:

`python -m pytest tests/test_core_suite_override_updates.py -q`

Result: 3 passed in 0.54s.



## 2026-06-11 - pending_input.rs parity

- Rust source: `codex/codex-rs/core/tests/suite/pending_input.rs`
- Python parity: `tests/test_core_suite_pending_input.py`
- Covered Rust tests: 7/7
- Focused pytest: `python -m pytest tests/test_core_suite_pending_input.py -q` -> 7 passed in 0.56s


## 2026-06-11 - permissions_messages.rs parity

- Rust source: `codex/codex-rs/core/tests/suite/permissions_messages.rs`
- Python parity: `tests/test_core_suite_permissions_messages.py`
- Covered Rust tests: 7/7
- Focused pytest: `python -m pytest tests/test_core_suite_permissions_messages.py -q` -> 7 passed in 0.53s


## 2026-06-11 - personality.rs parity

- Rust source: `codex/codex-rs/core/tests/suite/personality.rs`
- Python parity: `tests/test_core_suite_personality.py`
- Covered Rust tests: 12/12
- Focused pytest: `python -m pytest tests/test_core_suite_personality.py -q` -> 12 passed in 0.55s


## 2026-06-11 - personality_migration.rs exact suite parity

- Rust source: `codex/codex-rs/core/tests/suite/personality_migration.rs`
- Python parity: `tests/test_core_suite_personality_migration.py`
- Covered Rust tests: 11/11
- Focused pytest: `python -m pytest tests/test_core_suite_personality_migration.py -q` -> 11 passed in 0.59s


## 2026-06-11 - plugins.rs parity

- Rust source: `codex/codex-rs/core/tests/suite/plugins.rs`
- Python parity: `tests/test_core_suite_plugins.py`
- Covered Rust tests: 3/3
- Focused pytest: `python -m pytest tests/test_core_suite_plugins.py -q` -> 3 passed in 0.53s


## 2026-06-11 - prompt_caching.rs parity

- Rust source: `codex/codex-rs/core/tests/suite/prompt_caching.rs`
- Python parity: `tests/test_core_suite_prompt_caching.py`
- Covered Rust tests: 8/8
- Focused pytest: `python -m pytest tests/test_core_suite_prompt_caching.py -q` -> 8 passed in 0.52s


## 2026-06-11 - prompt_debug_tests.rs parity

- Rust source: `codex/codex-rs/core/tests/suite/prompt_debug_tests.rs`
- Python parity: `tests/test_core_suite_prompt_debug_tests.py`
- Covered Rust tests: 1/1
- Focused pytest: `python -m pytest tests/test_core_suite_prompt_debug_tests.py -q` -> 1 passed in 0.55s


## 2026-06-11 - quota_exceeded.rs parity

- Rust source: `codex/codex-rs/core/tests/suite/quota_exceeded.rs`
- Python parity: `tests/test_core_suite_quota_exceeded.py`
- Covered Rust tests: 1/1
- Focused pytest: `python -m pytest tests/test_core_suite_quota_exceeded.py -q` -> 1 passed in 0.55s

## 2026-06-11 - realtime_conversation Rust integration parity detail completion

Completed the detailed Rust suite parity checklist for an already mapped `core/tests` file:

- `codex/codex-rs/core/tests/suite/realtime_conversation.rs` -> `tests/test_core_realtime_conversation.py`.

Added suite-level coverage for realtime conversation lifecycle, WebRTC start/close edges, request headers, prompt/startup-context overrides, voice selection contracts, user-text mirroring, handoff output/finalization, inbound delegation transcript handling, and non-blocking audio/event forwarding.

Mapping count unchanged because this Rust test file was already counted as mapped in the inventory; this turn completed its per-test todo details.

Validation:
`python -m pytest tests/test_core_realtime_conversation.py -q`

Result:
`50 passed in 0.59s`


## 2026-06-11 - remote_env Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/remote_env.rs` -> `tests/test_core_suite_remote_env.py`.

Added suite-level parity coverage for remote/local environment routing and filesystem safety contracts: remote environment shape and file read/write/remove, selected environment routing for `exec_command`, freeform `apply_patch`, intercepted `apply_patch` through `exec_command`, approval cache scoping by environment id, readable-root checks, symlink parent-dotdot escape rejection, symlink removal preserving target, and symlink copy preserving the link source.

Validation:
`python -m pytest tests/test_core_suite_remote_env.py -q`

Result:
`6 passed, 4 skipped in 0.61s`


## 2026-06-11 - remote_models Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/remote_models.rs` -> `tests/test_core_suite_remote_models.py`.

Added suite-level parity coverage for remote model metadata behavior: longest-prefix and namespaced slug lookup, configured context-window clamping, default context-window preservation, high reasoning metadata propagation, unified-exec shell type selection, truncation policy preservation and tool-output override, remote base instructions, merged remote/bundled model preset ordering and replacement, empty remote response fallback, timeout fallback to bundled default, and hidden picker model visibility.

Validation:
`python -m pytest tests/test_core_suite_remote_models.py -q`

Result:
`17 passed in 0.21s`


## 2026-06-11 - request_compression Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/request_compression.rs` -> `tests/test_core_suite_request_compression.py`.

Added a small HTTP transport request-body preparation boundary and suite-level parity coverage for request compression: enabled compression plus Codex backend auth marks the body with `Content-Encoding: zstd` and passes JSON through a zstd compressor boundary, while API-key auth leaves the plain JSON body uncompressed even when the feature flag is enabled.

Validation:
`python -m pytest tests/test_core_suite_request_compression.py -q`

Result:
`2 passed in 0.54s`

## 2026-06-11 - request_permissions Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/request_permissions.rs` -> `tests/test_core_suite_request_permissions.py`.

Added suite-level parity coverage for inline `with_additional_permissions`, `request_permissions` auto-denial under granular policy, relative filesystem permission materialization, non-widening read-only requests, outside-CWD write grants, denied approval blocking, turn/session grant lifetime, and preapproved shell/exec follow-up calls.

Validation:
`python -m pytest tests/test_core_suite_request_permissions.py -q`

Result:
`14 passed in 0.72s`
## 2026-06-11 - request_permissions_tool Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/request_permissions_tool.rs` -> `tests/test_core_suite_request_permissions_tool.py`.

Added focused parity coverage for request-permissions folder-write grants unblocking later default exec calls and apply_patch writes, without depending on the macOS-only Rust sandbox harness.

Validation:
`python -m pytest tests/test_core_suite_request_permissions_tool.py -q`

Result:
`2 passed in 0.62s`
## 2026-06-11 - request_user_input Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/request_user_input.rs` -> `tests/test_core_suite_request_user_input.py`.

Added focused parity coverage for request_user_input Plan/default-with-feature round trips, Execute/Default/Pair Programming mode rejection messages, and cancellation resolving pending user input with an empty response notification.

Validation:
`python -m pytest tests/test_core_suite_request_user_input.py -q`

Result:
`6 passed in 0.55s`
## 2026-06-11 - responses_api_proxy_headers Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/responses_api_proxy_headers.rs` -> `tests/test_core_suite_responses_api_proxy_headers.py`.

Added focused parity coverage for parent/subagent Responses API identity headers: parent requests omit `x-openai-subagent`, spawned child requests include `x-openai-subagent: collab_spawn`, carry `x-codex-parent-thread-id`, have distinct zero-generation window ids, and preserve fork lineage in `x-codex-turn-metadata`.

Validation:
`python -m pytest tests/test_core_suite_responses_api_proxy_headers.py -q`

Result:
`1 passed in 0.54s`
## 2026-06-11 - resume Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/resume.rs` -> `tests/test_core_suite_resume.py`.

Added focused parity coverage for restored initial messages from rollout event rows, including text elements, reasoning summaries/raw reasoning, token count, and turn completion linkage. Also covered resume model-switch developer instruction emission and non-duplication after the resumed turn settings already reflect the new model.

Validation:
`python -m pytest tests/test_core_suite_resume.py -q`

Result:
`4 passed in 0.60s`
## 2026-06-11 - resume_warning Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/resume_warning.rs` -> `tests/test_core_suite_resume_warning.py`.

Added a focused resume model-mismatch warning boundary that emits a warning event when the previous rollout model differs from the current model and includes both model names in the user-visible warning message.

Validation:
`python -m pytest tests/test_core_suite_resume_warning.py -q`

Result:
`1 passed in 0.58s`
## 2026-06-11 - review Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/review.rs` -> `tests/test_core_suite_review.py`.

Added suite-level parity coverage for review task lifecycle/output behavior: structured review rollout rendering, plain-text fallback, review event filtering, single final assistant output for structured review, review model request selection, isolated review input, parent-session review history materialization, base-branch merge-base cwd resolution, review prompt/tool suppression, and embedded JSON parsing.

Implementation fix while testing:

- Aligned local HTTP review lifecycle ordering so terminal complete events are emitted after `exited_review_mode`, matching the Rust suite's visible review sequence.

Validation:
`python -m pytest tests/test_core_suite_review.py -q`

Result:
`11 passed in 0.64s`

## 2026-06-11 - rmcp_client Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/rmcp_client.rs` -> `tests/test_core_suite_rmcp_client.py`.

Added a lightweight `pycodex.rmcp_client` contract layer and suite-level parity coverage for the 15 Rust RMCP client integration tests: stdio namespace/tool round trip, configured/fallback cwd precedence, sandbox-state metadata, serial versus concurrent MCP scheduling policy, image output conversion and text-only sanitization, whitelisted/local/remote env-var source behavior, streamable HTTP metadata URL behavior, and OAuth token/fallback credential handling.

Validation:
`python -m pytest tests/test_core_suite_rmcp_client.py -q`

Result:
`15 passed in 0.18s`

## 2026-06-11 - rollout_list_find Rust integration parity

Mapped one `core/tests` Rust integration test file:

- `codex/codex-rs/core/tests/suite/rollout_list_find.rs` -> `tests/test_core_suite_rollout_list_find.py`.

Added suite-level parity coverage for rollout lookup behavior: locating active rollout JSONL by thread id, ignoring `.gitignore` coverage around Codex home and granular `sessions/.gitignore` rules, preferring a state-DB-provided rollout path when present, falling back to filesystem scan when state DB has no match, finding named threads through `session_index.jsonl`, and locating archived rollout files by id.

Implementation fix while testing:

- Added optional duck-typed `state_db_ctx` lookup support to rollout find helpers so Python mirrors Rust's SQLite-first lookup contract without requiring a full SQLite runtime in this focused test.

Validation:
`python -m pytest tests/test_core_suite_rollout_list_find.py -q`

Result:
`7 passed in 0.55s`

2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/stream_error_allows_next_turn.rs` with `tests/test_core_suite_stream_error_allows_next_turn.py`; focused run: `python -m pytest tests/test_core_suite_stream_error_allows_next_turn.py -q` -> 1 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/stream_no_completed.rs` with `tests/test_core_suite_stream_no_completed.py`; focused run: `python -m pytest tests/test_core_suite_stream_no_completed.py -q` -> 1 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/subagent_notifications.rs` with `tests/test_core_suite_subagent_notifications.py`; focused run: `python -m pytest tests/test_core_suite_subagent_notifications.py -q` -> 9 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/tool_harness.rs` with `tests/test_core_suite_tool_harness.py`; focused run: `python -m pytest tests/test_core_suite_tool_harness.py -q` -> 5 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/tool_parallelism.rs` with `tests/test_core_suite_tool_parallelism.py`; focused run: `python -m pytest tests/test_core_suite_tool_parallelism.py -q` -> 5 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/tools.rs` with `tests/test_core_suite_tools.py`; focused run: `python -m pytest tests/test_core_suite_tools.py -q` -> 9 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/truncation.rs` with `tests/test_core_suite_truncation.py`; focused run: `python -m pytest tests/test_core_suite_truncation.py -q` -> 10 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/turn_state.rs` with `tests/test_core_suite_turn_state.py`; focused run: `python -m pytest tests/test_core_suite_turn_state.py -q` -> 2 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/unstable_features_warning.rs` with `tests/test_core_suite_unstable_features_warning.py`; focused run: `python -m pytest tests/test_core_suite_unstable_features_warning.py -q` -> 2 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/user_notification.rs` with `tests/test_core_suite_user_notification.py`; focused run: `python -m pytest tests/test_core_suite_user_notification.py -q` -> 1 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/window_headers.rs` with `tests/test_core_suite_window_headers.py`; focused run: `python -m pytest tests/test_core_suite_window_headers.py -q` -> 1 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/websocket_fallback.rs` with `tests/test_core_suite_websocket_fallback.py`; focused run: `python -m pytest tests/test_core_suite_websocket_fallback.py -q` -> 4 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/user_shell_cmd.rs` with `tests/test_core_suite_user_shell_cmd.py`; focused run: `python -m pytest tests/test_core_suite_user_shell_cmd.py -q` -> 7 passed.
2026-06-11: Added Rust parity coverage for `codex/codex-rs/core/tests/suite/view_image.rs` with `tests/test_core_suite_view_image.py`; focused run: `python -m pytest tests/test_core_suite_view_image.py -q` -> 16 passed.
