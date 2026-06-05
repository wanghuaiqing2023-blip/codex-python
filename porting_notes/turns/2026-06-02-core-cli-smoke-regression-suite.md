# Core CLI smoke regression suite

## Scope

- Added a standard-library `unittest` suite for the Python core local HTTP CLI smoke path.
- The suite groups the currently working end-to-end CLI coverage for:
  - SSE final answers.
  - Streamed `exec_command` and `apply_patch` tool calls.
  - Shell-tool and apply-patch follow-up turns.
  - `write_stdin` continuation.
  - `exec resume` history loading and tool follow-up.
  - Approval/request-permissions cancellation behavior.
  - Context-window and provider error rendering.
  - Interrupted turn rollout persistence.

## Upstream navigation

- Used the upstream knowledge graph as a navigation check for the active dependency slice.
- Relevant graph tour: CLI and execution path.
- Relevant upstream test areas surfaced by the graph include:
  - `codex-rs/core/tests/suite/cli_stream.rs`
  - `codex-rs/core/tests/suite/exec.rs`
  - `codex-rs/core/tests/suite/apply_patch_cli.rs`

## Python changes

- Added `tests/test_cli_local_http_smoke_suite.py`.
- The suite imports existing `TopLevelCliParserTests` cases and exposes `load_tests`, so it can be run with:

```powershell
python -m unittest tests.test_cli_local_http_smoke_suite
```

## Validation

```powershell
python -m py_compile tests\test_cli_local_http_smoke_suite.py
python -m unittest tests.test_cli_local_http_smoke_suite
```

Result:

- 21 tests ran.
- All passed.
- Runtime was about 1.3 seconds.

## Follow-up

- This suite is now the first practical regression entrypoint for continuing core CLI port work.
- Broader full-suite issues remain outside this slice, including the existing doctor/update-resource warning failure observed earlier.
