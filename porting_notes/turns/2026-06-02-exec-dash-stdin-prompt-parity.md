# Exec dash stdin prompt parity

## Upstream graph and source slice

- Graph node: `function:codex-rs/exec/src/lib.rs#run_exec_session`
- Graph node: `function:codex-rs/exec/src/lib.rs#resolve_root_prompt`
- Graph node: `function:codex-rs/exec/src/lib.rs#resolve_prompt`
- Graph node: `function:codex-rs/exec/src/lib.rs#decode_prompt_bytes`
- Source: `codex/codex-rs/exec/src/lib.rs`

Rust treats a positional `-` as a prompt sentinel for `codex exec`, forcing the
prompt to be read from stdin. Prompt bytes accept a UTF-8 BOM, decode UTF-16LE
and UTF-16BE BOM input, reject UTF-32 BOM input with an actionable message, and
report invalid UTF-8 with the invalid byte offset. When a normal prompt argument
is present and stdin is piped, Rust appends the piped text inside a `<stdin>`
block.

## Python changes

- Updated `pycodex.exec.cli.parse_exec_args` to accept a bare `-` as the
  normal exec prompt instead of treating it as an unknown option.
- Updated resume parsing to accept bare `-` as the resume prompt positional as
  well.
- Added exec-run preparation tests proving both normal exec and resume accept
  bare `-` and force stdin prompt input.
- Added a CLI entrypoint smoke test proving `codex exec -` reaches the
  non-interactive exec plan path with stdin input.

## Validation

- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_dash_reads_forced_stdin_prompt tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_reads_stdin_prompt_when_no_prompt_argument`
