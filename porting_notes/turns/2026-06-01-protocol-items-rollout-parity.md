# Protocol Items And Rollout Parity

## Scope

- Continued the graph-guided core runtime slice around session data contracts:
  `exec -> context -> model request -> stream handling -> tool dispatch -> final answer`.
- Focused on protocol item conversion, approval decisions, event payload parsing, and latest-thread rollout append behavior.
- Deferred MCP/plugin/deep app-server implementation beyond compatibility shapes already exercised by core protocol tests.

## Upstream graph/source slice

- Graph nodes used:
  - `file:codex-rs/protocol/src/items.rs`
  - `file:codex-rs/protocol/src/protocol.rs`
  - `file:codex-rs/protocol/src/approvals.rs`
  - `file:codex-rs/rollout/src/list.rs`
- Rust source confirmed:
  - `UserMessageItem` legacy behavior flattens text chunks and preserves image/local-image metadata.
  - `EventMsg` and approval decision types are shared protocol contracts on the core session path.
  - Rollout listing supports created-at and updated-at ordering; Python latest-thread append should use created-at ordering for the current resume helper to avoid old threads jumping ahead solely because a turn was appended.

## Python changes

- Added a local `_camel_to_snake` helper in `pycodex/protocol/approvals.py` so `ReviewDecision.from_mapping` can parse structured response/request approval payloads without importing back through `protocol.py`.
- Stabilized app-server path JSON for user-input local image/skill content and command execution cwd in `pycodex/protocol/items.py` with POSIX-style output where the app-server tests require cross-platform strings.
- Preserved Rust-shaped `ImageView` and `ImageGeneration` path string behavior separately, matching existing protocol item tests on Windows.
- Allowed direct `WebSearchItem(..., action={})` to map to the `other` action while keeping Rust-shaped `TurnItem.from_mapping({"type": "WebSearch", ...})` strict about a missing `action`.
- Kept v2 app-server `webSearch` payloads compatible when `action` is absent by injecting `other` only for the lower-camel app-server type.
- Made app-server `AgentMessageItem` roundtrip equality compare user-visible joined text, phase, and citation so a single v2 `text` field remains equivalent to chunked Python/Rust content for common UI behavior.
- Changed `append_turn_to_latest_thread_rollout` to select latest matching thread by created-at ordering, then append the turn context to that selected rollout.

## Validation

- `python -m unittest tests.test_protocol_protocol tests.test_protocol_models_content tests.test_protocol_items tests.test_protocol_user_input tests.test_core_event_mapping tests.test_core_context_updates tests.test_core_contextual_user_message tests.test_core_rollout tests.test_core_thread_rollout_truncation`
  - 182 tests passed.
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_router tests.test_core_stream_events_utils tests.test_core_unified_exec_handler tests.test_core_shell_handler tests.test_core_apply_patch tests.test_core_view_image_handler tests.test_protocol_protocol tests.test_protocol_items tests.test_core_rollout`
  - 538 tests passed, 1 skipped.

## Follow-up debt

- Full protocol/app-server parity still has peripheral areas that should stay deferred unless the core CLI/runtime path needs them.
- `pytest` is not installed in this workspace, so pytest-only tests remain outside the current validation set unless that dependency is approved.
