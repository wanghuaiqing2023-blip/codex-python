# Local HTTP Review Runtime

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/exec/src/lib.rs#run_exec_session:564`
  - `function:codex-rs/exec/src/lib.rs#build_review_request:1846`
  - `file:codex-rs/core/src/session/review.rs`
- Rust source read:
  - `codex/codex-rs/exec/src/lib.rs`
  - `codex/codex-rs/core/src/session/handlers.rs`
  - `codex/codex-rs/core/src/session/review.rs`
  - `codex/codex-rs/core/src/tasks/review.rs`

## Rust behavior confirmed

- `codex review` and `codex exec review` build an `InitialOperation::Review` from `--uncommitted`, `--base`, `--commit`, or a custom review prompt.
- The app-server path starts review execution through `review/start`.
- Core review handling resolves the review request into a synthesized user prompt, runs it under Rust's dedicated `REVIEW_PROMPT` instructions, suppresses ordinary assistant streaming, parses the reviewer model's JSON output, and renders a human-readable final review message.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Added `LocalHttpReviewModelInfo` to apply Rust's review-task base instructions to local HTTP sampling.
  - Added `local_http_review_user_turn_plan` to convert review initial operations into the synthesized user turn used by the review task.
  - Added `run_exec_review_http_sampling` for local HTTP review execution.
  - Added `parse_local_http_review_output` and final review rendering through `render_review_output_text`.
  - Added Rust-shaped parent-thread review rollout rendering via `render_local_http_review_rollout_user_message` and `local_http_review_rollout_input_items`.
  - Added local review lifecycle events around the inner review turn: `entered_review_mode` with the resolved review request, and `exited_review_mode` with the parsed `ReviewOutputEvent`.
  - Added the Rust interrupted-review path: interrupted review turns now emit `exited_review_mode` with no review output, render the interrupted assistant message, and persist the dedicated review interrupted template instead of the generic turn-aborted marker.

- `pycodex/cli/parser.py`
  - Allowed local HTTP `review` execution instead of rejecting it as unsupported.
  - Persisted local HTTP review turns after execution, using the review output user-action message as rollout-visible input.
  - Kept legacy non-local review tests on the preparation-only path unless local HTTP is explicitly enabled.

- `tests/test_exec_local_runtime.py`
  - Added coverage that local HTTP review uses `REVIEW_PROMPT`, sends the synthesized uncommitted-changes prompt, drops normal project instructions for the review turn, and renders structured review output.
  - Covered `EnteredReviewMode` / `ExitedReviewMode` parity for structured JSON output and plain-text fallback review output.
  - Covered interrupted review lifecycle and rollout persistence, including the absence of the generic `<turn_aborted>` prompt marker on the review interrupted path.
  - Covered Rust-shaped parent rollout input for review output: user-action context, `review` action, and rendered reviewer results.

- `tests/test_cli_parser.py`
  - Added CLI coverage for top-level `codex review --uncommitted` through the local HTTP runtime.
  - Covered that local HTTP review execution calls rollout persistence with the review output user-action input.
  - Stabilized existing review preparation tests against API-key environment leakage.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py pycodex\cli\parser.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`
- `python -m unittest tests.test_exec_run tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_uses_review_prompt_and_renders_output tests.test_cli_parser.TopLevelCliParserTests.test_main_review_local_http_runtime_prints_summary_and_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_review_alias_runs_exec_plan_preparation tests.test_cli_parser.TopLevelCliParserTests.test_main_review_inherits_root_exec_shared_options`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_runtime_prints_summary_and_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_review_local_http_runtime_prints_summary_and_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_review_alias_runs_exec_plan_preparation tests.test_cli_parser.TopLevelCliParserTests.test_main_review_inherits_root_exec_shared_options tests.test_cli_parser.TopLevelCliParserTests.test_main_review_requires_review_target`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_uses_review_prompt_and_renders_output tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_runtime_materializes_rollout_unless_ephemeral`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_uses_review_prompt_and_renders_output tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_plain_text_output_emits_review_lifecycle`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_uses_review_prompt_and_renders_output tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_plain_text_output_emits_review_lifecycle tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_interrupted_output_uses_review_interrupted_lifecycle`

## Known gaps

- This is a local HTTP compatibility path, not a full app-server `review/start` implementation.
- The Python path now emits local review lifecycle events and persists Rust-shaped review output/interrupted inputs, but it still does not implement the full app-server `review/start` transport.
