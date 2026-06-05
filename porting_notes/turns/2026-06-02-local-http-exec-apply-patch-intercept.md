# Local HTTP Exec Apply Patch Intercept

## Scope

- Closed a core command/editing path gap in local HTTP `exec`.
- Python now intercepts `apply_patch` heredocs embedded in `exec_command` shell scripts before falling back to normal shell execution.

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request`
  - `function:codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#handle`
  - `function:codex-rs/core/src/tools/handlers/apply_patch.rs#intercept_apply_patch`
  - `function:codex-rs/apply-patch/src/invocation.rs#maybe_parse_apply_patch_verified`
- Rust source read:
  - `codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
  - `codex/codex-rs/core/src/tools/handlers/apply_patch.rs`
  - `pycodex/core/apply_patch.py` for the existing Python parser/verification port.

## Rust behavior confirmed

- `exec_command` parses the command and resolves the working directory.
- Before launching the command, Rust calls `intercept_apply_patch`.
- If the command is an `apply_patch` wrapper such as a heredoc, Rust verifies and applies the patch through the apply-patch runtime rather than requiring an external shell command named `apply_patch`.
- Non-apply-patch commands continue to normal shell execution.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Added `LocalHttpApplyPatchCommand` and helpers that run the existing Python `maybe_parse_apply_patch_verified()` over likely shell argv forms.
  - The local HTTP shell tool path now intercepts verified `apply_patch` shell wrappers after command approval checks and before invoking the shell runner/session manager.
  - Intercepted patches reuse the existing Python apply-patch disk application, protocol change conversion, and approval/preapproval checks.
  - Shell-intercepted apply_patch outputs now emit the same local file-change timeline items as direct `apply_patch` calls when protocol changes are available.
  - File-change timeline metadata now carries local apply-patch `auto_approved`, `stdout`, and `stderr` fields, matching Rust's begin/end event shape more closely.
  - Approval-required apply_patch outputs now carry `auto_approved=false`, empty stdout, and the approval message in stderr so failed file-change events preserve Rust-like metadata.
- `pycodex/exec/events.py`
  - `file_change` JSON payloads now preserve `auto_approved`, `stdout`, and `stderr` when present on the protocol item.
- `tests/test_exec_local_runtime.py`
  - Added coverage proving `exec_command` with an `apply_patch <<'PATCH'` heredoc edits the file directly and never invokes the shell runner.
  - Extended coverage to assert direct and shell-intercepted edits appear as `file_change` in-progress/completed timeline events with the expected metadata.
  - Added assertions for direct and tool-loop approval-required apply_patch metadata.

## Validation

- `python -m py_compile pycodex\exec\events.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_intercepts_apply_patch_heredoc_before_runner tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_updates_deletes_and_moves_files`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_requires_approval_before_write tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_apply_patch_approval_failure tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch`
- `python -m unittest tests.test_exec_local_runtime`

## Known gaps

- The intercepted `exec_command` still returns a `function_call_output` to the model, as Rust does for the `exec_command` call. Local CLI file-change events now preserve the main begin/end metadata; deeper turn-diff tracking parity remains follow-up work.
