# Exec parser fallback env-isolation

## Context
- Local HTTP and core execution routing in `pycodex.cli.parser._run_noninteractive_exec` depends on runtime-enabled feature probes.
- Tests that disable `local_http_exec_enabled` for fallback coverage can still hit core execution when `OPENAI_API_KEY`/`CODEX_API_KEY` are present in the environment.

## Resolution
- Updated parser fallback tests that expect remote/app-server path to make core routing explicit:
  - `test_main_exec_allows_strict_config`
  - `test_main_exec_reads_stdin_prompt_when_no_prompt_argument`
  - `test_main_exec_dash_reads_forced_stdin_prompt`
  - `test_main_exec_prepares_noninteractive_plan`
- Each now patches `pycodex.cli.parser.core_exec_enabled` to `False` alongside `local_http_exec_enabled=False`.

## Validation
- `python -m pytest -q tests/test_cli_parser.py tests/test_cli_core_smoke_suite.py`
- `python -m pytest -q tests/test_cli_parser.py -k "main_exec_allows_strict_config or main_exec_reads_stdin_prompt_when_no_prompt_argument or main_exec_dash_reads_forced_stdin_prompt or main_exec_prepares_noninteractive_plan"`
