# Unified Exec Sandbox Denial Truncation

## Upstream graph/source slice

- Used `codex/.understand-anything/knowledge-graph.json` to locate:
  - `codex-rs/core/src/exec.rs#is_likely_sandbox_denied`
  - `codex-rs/core/src/unified_exec/errors.rs#UnifiedExecError`
  - `codex-rs/core/src/unified_exec/process.rs`
  - `codex-rs/core/src/exec_tests.rs`
- Confirmed from Rust source that unified exec sandbox-denial startup checks:
  - ignore non-sandbox mode and processes that have not exited;
  - reuse `is_likely_sandbox_denied` with stderr and aggregated output set to the collected text;
  - build an empty-output fallback of `Process exited with code {exit_code}`;
  - otherwise pass the denial text through `formatted_truncate_text(..., Tokens(UNIFIED_EXEC_OUTPUT_MAX_TOKENS))`.

## Python changes

- `pycodex/core/exec.py`
  - Updated `unified_exec_sandbox_denial_message` to format long sandbox-denial output with the same unified-exec token budget used by Rust.
  - Fixed a dataclass/API collision in `ExecExpiration`: the `cancellation` field and `ExecExpiration.cancellation(...)` factory had the same name, causing normal timeout construction to see the classmethod object as a cancellation token. The public API remains:
    - `ExecExpiration.cancellation(token)` as a factory;
    - `expiration.cancellation` as the readable token.
- `tests/test_core_exec.py`
  - Added long-output coverage for sandbox-denial message truncation.
  - Added the missing `EXIT_CODE_SIGNAL_BASE` import used by the existing empty-output fallback test.

## Validation

- `python -m py_compile pycodex\core\exec.py tests\test_core_exec.py`
- Ran all 16 `tests.test_core_exec` test functions with an in-memory pytest `raises` shim because the active Python environment does not have pytest installed.
- `python -m unittest tests.test_core_tool_runtimes.ToolRuntimesTests.test_unified_exec_options_combines_default_timeout_with_network_denial_cancellation`
- `python -m unittest tests.test_core_unified_exec tests.test_core_unified_exec_handler`

## Known gaps

- The local environment lacks pytest, so the pytest-style file could not be run through the normal pytest runner in this turn.
- This slice only covers sandbox-denial message parity and the cancellation-token construction bug; broader terminal-bench/self-repair infrastructure remains deferred while core runtime behavior is still being completed.
