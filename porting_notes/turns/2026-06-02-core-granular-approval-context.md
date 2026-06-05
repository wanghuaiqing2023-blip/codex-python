# Core granular approval context support

## Upstream slice

- Used the upstream graph around `TurnContext`, `PermissionsInstructions`, and `AskForApproval::Granular`.
- Confirmed behavior in:
  - `codex-rs/protocol/src/protocol.rs#AskForApproval`
  - `codex-rs/protocol/src/protocol.rs#GranularApprovalConfig`
  - `codex-rs/core/src/session/turn_context.rs#to_turn_context_item`
  - `codex-rs/core/src/context/permissions_instructions.rs`

## Rust behavior matched

- Rust `AskForApproval` includes a `Granular(GranularApprovalConfig)` variant.
- Permission instructions render granular policy details directly.
- `request_permissions` prompt instructions appear only when the feature is enabled and the granular category allows it.
- Turn context persistence can carry the granular approval value.

## Python changes

- `TurnContextItem` now accepts and serializes `GranularApprovalConfig` as `{"granular": {...}}` while preserving existing string policies.
- `InMemoryCodexSession` now carries granular approval through its internal approval wrapper instead of coercing it to a plain `AskForApproval`.
- Initial context generation now passes granular policy values directly to `PermissionsInstructions`.
- `writable_roots_text` now validates item types before sorting, preserving the intended TypeError boundary for invalid inputs.

## Validation

- `python -m unittest tests.test_protocol_protocol.ProtocolProtocolTests.test_turn_context_item_round_trips_granular_approval_policy tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_initial_context_supports_granular_approval_policy tests.test_core_permissions_instructions`
- `python -m unittest tests.test_protocol_protocol tests.test_core_permissions_instructions tests.test_core_session_runtime tests.test_core_turn_prompt tests.test_core_turn_request tests.test_core_turn_runtime`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite tests.test_exec_local_http_runtime_smoke_suite`
- `python -m py_compile pycodex\protocol\protocol.py pycodex\core\session_runtime.py pycodex\core\permissions_instructions.py tests\test_protocol_protocol.py tests\test_core_session_runtime.py tests\test_core_permissions_instructions.py`

## Known gaps

- Other protocol event types that still type `approval_policy` as plain `AskForApproval` may need the same granular JSON support in later slices if they become active on the core runtime path.
- This does not implement additional granular guardian/app-server flows; it preserves the core prompt/context and rollout carrier behavior.
