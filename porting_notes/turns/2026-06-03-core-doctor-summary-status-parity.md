# 2026-06-03 — Doctor Summary Status Parity

## Goal
Unblock the remaining `doctor` CLI parity edge in the core command path by preserving upstream status semantics in summary aggregation.

## What we changed
- Updated `pycodex/cli/parser.py` ` _doctor_cli_status` normalization to map Rust-style `"warning"` to CLI `"warn"` and keep only canonical statuses during aggregation.
- Kept exit code behavior: failures still produce non-zero code, but warning-only summaries now stay successful (`0`) with warning counts reflected in the summary line.

## Evidence
- `python -m pytest -q tests/test_cli_parser.py::TopLevelCliParserTests::test_main_doctor_summary_counts_warning_status_as_warning`
- `python -m pytest -q tests/test_cli_parser.py::TopLevelCliParserTests::test_main_doctor_all_requests_installation_path_details`
- `python -m pytest -q tests/test_cli_local_http_smoke_suite.py::TopLevelCliParserTests::test_main_doctor_summary_counts_warning_status_as_warning`
