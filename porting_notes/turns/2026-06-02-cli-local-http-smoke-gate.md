# 2026-06-02 CLI local HTTP smoke gate

## Upstream slice

- Continued the graph-guided `codex exec` path from the Rust entrypoint toward the common runtime loop:
  - `codex-rs/exec/src/lib.rs`
  - `codex-rs/core/src/tools/router.rs`
  - `codex-rs/core/src/tools/parallel.rs`
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
  - `codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs`

## Python evidence

- The existing CLI smoke suite already covers the real top-level `main(["exec", ...])` local HTTP path.
- It exercises:
  - final assistant output
  - streamed `exec_command` tool calls
  - streamed `apply_patch`
  - shell command tool execution and follow-up requests
  - `view_image`
  - output schema follow-up handling
  - `write_stdin` continuing a live local process session
  - resume flows, approvals, JSON events, interruption, retry, and provider errors

## Validation

- `python -m unittest tests.test_cli_local_http_smoke_suite`
  - 33 tests passed.
- `python -m unittest tests.test_local_http_core_smoke_suite`
  - 47 tests passed.

## Follow-up

- Keep this smoke gate as the recurring check for common `pycodex exec` regressions.
- Next implementation slice should move beyond local-http compatibility toward direct CLI/core session smoke coverage where `pycodex exec` can use the in-memory core tool loop without a mocked HTTP local runtime.
