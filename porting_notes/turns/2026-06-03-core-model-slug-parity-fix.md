## Core Model Slug Parity Fix

Date: 2026-06-03

- Identified a Python-side drift where runtime defaults and warning strings used `gpt-5.3-Codex-Spark` while upstream Rust paths consistently use `gpt-5.3-codex` in core/session/runtime behavior.
- Updated:
  - `pycodex/exec/local_runtime.py`
  - `pycodex/cli/parser.py`
  - `pycodex/core/session_runtime.py`
  - `tests/test_cli_parser.py`
  - `tests/test_exec_local_runtime.py`
  - `tests/test_core_compact.py`
- Validation run:
  - `python -m pytest -q tests/test_cli_parser.py::TopLevelCliParserTests::test_main_debug_models_returns_supported_default_models tests/test_cli_parser.py::TopLevelCliParserTests::test_main_prompt_without_subcommand_uses_local_http_exec_when_available tests/test_core_compact.py::CompactTests::test_collect_user_messages_filters_context_and_legacy_warnings tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_default_local_http_model_precedence`
  - `python -m pytest -q tests/test_exec_core_runtime_smoke_suite.py tests/test_core_smoke_suite.py`

Result: all selected tests passed.
