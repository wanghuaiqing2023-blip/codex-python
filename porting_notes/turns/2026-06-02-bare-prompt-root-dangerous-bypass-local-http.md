# 2026-06-02 bare prompt root dangerous bypass local HTTP

## Scope

- Extended the bare top-level prompt local HTTP exec coverage to include the root
  `--dangerously-bypass-approvals-and-sandbox` option.
- Verified that `codex --dangerously-bypass-approvals-and-sandbox --cd <dir> <prompt>`
  is routed through the local HTTP `exec` path, preserves the selected working
  directory, and permits shell execution without the approval gate.

## Behavior covered

- The mocked model requests a shell command that writes `created-bare.txt` in the
  configured `--cd` directory.
- The CLI completes successfully, emits the final model answer, and sends the
  shell tool output back to the model with `success: true`.
- The tool output includes the process exit summary, matching the local runtime's
  user-facing command result shape.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_dangerous_bypass_to_local_http_exec`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`
