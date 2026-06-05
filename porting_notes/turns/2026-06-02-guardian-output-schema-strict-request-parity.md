# Guardian output schema strict request parity

## Upstream graph and source slice

- Graph node: `function:codex-rs/core/src/session/turn.rs#build_prompt`
- Graph node: `function:codex-rs/core/src/guardian/review.rs#is_guardian_reviewer_source`
- Source: `codex/codex-rs/core/src/session/turn.rs`
- Source: `codex/codex-rs/core/src/guardian/review.rs`
- Source: `codex/codex-rs/core/src/guardian/mod.rs`

Rust builds every sampling prompt with `output_schema_strict` enabled except
for the guardian reviewer subagent source. The guardian reviewer is encoded as
`SessionSource::SubAgent(SubAgentSource::Other("guardian"))`; in that case
`build_prompt` sets the prompt's schema strictness to false.

## Python changes

- Added `is_guardian_reviewer_source` and Rust-compatible guardian reviewer
  detection to `pycodex.core.turn_prompt`.
- Changed prompt/request construction to infer output-schema strictness from
  `turn_context.session_source` unless the caller explicitly overrides it.
- Added `session_source` to the in-memory turn/session runtime so core request
  construction can preserve this Rust prompt property.
- Added coverage for prompt-level inference, explicit override behavior,
  request JSON `text.format.strict`, and session-to-turn source propagation.

## Validation

- `python -m unittest tests.test_core_turn_prompt tests.test_core_turn_request tests.test_core_session_runtime`
- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_turn_prompt tests.test_core_turn_request tests.test_core_session_runtime tests.test_core_turn_runtime`

Attempted:

- `python -m unittest tests.test_core_client tests.test_core_turn_prompt tests.test_core_turn_request tests.test_core_session_runtime tests.test_core_turn_runtime`

The combined command could not import `tests.test_core_client` because this
environment does not have `pytest` installed. The other modules in that command
ran successfully before the import error was reported.
