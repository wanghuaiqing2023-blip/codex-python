# User Prompt Lifecycle Ordering Fix

Date: 2026-06-03

Target slice:
- `pycodex/core/turn_runtime.py`
- `run_user_turn_sampling_from_session`

Issue:
- Terminal sampling errors were surfacing user prompt turn item lifecycle events even when the sample failed, and in some paths prompt message history was duplicated due to a delayed/duplicate emission strategy.

Findings:
- The Rust-like flow records user input before sampling to ensure the prompt is part of the request context, but turn-item lifecycle events should be tied to a successful sample.
- Emitting the full `record_user_prompt_and_emit_turn_item` after preparation added prompt history twice in sessions that do not route turn-item events through callbacks.

Implementation:
- Kept user prompt recording in preparation with no lifecycle emission.
- Added the user input tuple to `_PreparedUserTurnRequest` and deferred prompt turn-item emission until after the first successful `_sample_with_retry`.
- Added `emit_turn_item` control to user prompt recording helpers so prep can suppress item emission.
- Added `_emit_user_prompt_turn_item` helper to emit lifecycle events only when lifecycle methods are available, avoiding duplicate history writes.

Validation:
- Ran `python -m pytest tests/test_core_session_runtime.py tests/test_core_turn_runtime.py` and confirmed all cases pass (167 tests).
