# protocol/v2/turn.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/turn.rs`

Python module: `pycodex/app_server_protocol/turn.py`

Status: complete for the module-scoped app-server protocol data contract.

## Covered

- `TurnStatus`, `AdditionalContextKind`, and `TurnPlanStepStatus` wire values.
- `TurnEnvironmentParams`, `AdditionalContextEntry`, `TurnStartParams`,
  `TurnStartResponse`, `TurnSteerParams`, `TurnSteerResponse`,
  `TurnInterruptParams`, and `TurnInterruptResponse`.
- `ByteRange`, `TextElement`, and `UserInput` tagged variants for text, image,
  local image, skill, and mention input.
- `UserInput.text_char_count()` behavior.
- Turn started/completed, diff updated, and plan updated notifications.
- `Usage`, `TurnPlanStep`, and plan step status payloads.

## Intentional Adaptations

- Runtime config/model values such as approval policy, approvals reviewer,
  sandbox policy, reasoning effort/summary, personality, output schema, and
  collaboration mode remain JSON-compatible protocol payloads.
- `service_tier` uses an `UNSET` sentinel to preserve Rust's omitted-vs-null
  double-option semantics.
- `Turn` is imported from the already-ported `thread_data.py` module.

## Validation

- `python -m py_compile pycodex/app_server_protocol/turn.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered byte ranges, text elements, user input variants,
  start/steer/interrupt params, service tier null/omitted behavior, turn
  response/notifications, usage, plan notifications, and package exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
