# Exec Approval Event Round Trip

## Upstream graph slice

- Knowledge graph node:
  - `class:codex-rs/protocol/src/approvals.rs#ExecApprovalRequestEvent:218`
- Rust source read:
  - `codex/codex-rs/protocol/src/approvals.rs`

## Rust behavior confirmed

- `ExecApprovalRequestEvent` is the structured event payload for command approvals.
- It serializes command, cwd, optional `approval_id`, `turn_id`, `reason`, network approval context, proposed exec/network policy amendments, additional permissions, available decisions, and parsed command actions.
- If explicit `available_decisions` are absent, Rust derives defaults from the same context fields.

## Python changes

- `pycodex/protocol/approvals.py`
  - Added `NetworkApprovalContext.from_mapping` and `to_mapping`.
  - Added `ExecApprovalRequestEvent.from_mapping` and `to_mapping`.
  - Added small local helpers for string lists, generic sequences, and parsed command mapping.

- `tests/test_protocol_approvals.py`
  - Added full Rust-shape JSON round-trip coverage for `ExecApprovalRequestEvent`, including:
    - `approval_id`
    - `turn_id`
    - `reason`
    - `network_approval_context`
    - `proposed_execpolicy_amendment`
    - `proposed_network_policy_amendments`
    - `additional_permissions`
    - `available_decisions`
    - `parsed_cmd`

## Validation

- `python -m py_compile pycodex\protocol\approvals.py tests\test_protocol_approvals.py`
- `python -m unittest tests.test_protocol_approvals.ProtocolApprovalsTests.test_exec_approval_request_event_round_trips_rust_json_shape`
- `python -m unittest tests.test_protocol_approvals`
- `python -m unittest tests.test_protocol_protocol.ProtocolProtocolTests.test_request_event_payloads_parse_structured_payloads`
- `python -m unittest tests.test_protocol_protocol`

## Known gaps

- App-server camelCase aliases continue to be parsed through `pycodex/protocol/protocol.py`; the new event-local `from_mapping` is intentionally focused on the Rust protocol snake_case event shape.
