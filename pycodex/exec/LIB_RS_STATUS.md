# codex-exec src/lib.rs status

Status: complete_candidate

Rust crate: `codex-exec`
Rust module: `codex/codex-rs/exec/src/lib.rs`
Rust tests: `codex/codex-rs/exec/src/lib_tests.rs`
Python modules:

- `pycodex/exec/__init__.py`
- `pycodex/exec/run.py`
- `pycodex/exec/session.py`
- `pycodex/exec/config_plan.py`

Python tests:

- `tests/test_exec_run.py`
- `tests/test_exec_session.py`
- `tests/test_exec_config_plan.py`

## Behavior contract

Rust `src/lib.rs` is the main `codex-exec` orchestration module. It owns:

- the public export surface for CLI args, status, JSONL event types, and event
  processors;
- constants and tracing/logging defaults used by `codex exec`;
- prompt decoding, stdin prompt resolution, output-schema loading, review
  request construction, and initial operation selection;
- thread start/resume request construction and session-configured event
  mapping;
- resume lookup helpers, cwd matching, rollout context parsing, and thread
  item backfill helpers;
- exec-mode server request rejection/cancellation behavior;
- the async `run_main` and session loop wiring to the in-process app server.

## Python alignment

The testable helper/export surface is largely represented:

- `pycodex.exec.__init__` re-exports the Python exec CLI, run preparation,
  session, websocket, event processor, and event schema surfaces.
- `pycodex.exec.run` mirrors Rust prompt decoding, stdin wrapping, output
  schema loading, review request construction, and initial operation planning.
- `pycodex.exec.session` mirrors request id sequencing, thread start/resume
  params, turn/review requests, resume lookup helpers, backfill helpers,
  session-configured mapping, server request decisions, and exec-loop step
  helpers.
- `pycodex.exec.config_plan` carries Rust constants such as
  `DEFAULT_ANALYTICS_ENABLED` and `EXEC_DEFAULT_LOG_FILTER`, plus bootstrap
  planning equivalents for the pre-client part of `run_main`.
- `pycodex.exec.config_plan.ExecRunMainPlan` and
  `build_exec_run_main_plan(...)` mirror the remaining `run_main` startup
  choices: JSON versus human processor selection, telemetry/logging defaults,
  runtime path projection, environment-manager source selection, config
  warnings, and in-process app-server start argument shape.

The Rust `lib_tests.rs` helper contracts are represented by Python coverage for
prompt decoding, review request targets, stdin context wrapping, output schema
loading, lagged event warnings, resume model-provider filtering, thread item
backfill, MCP elicitation cancel responses, thread start/session-configured
mapping, active permission profile selection, and related request/loop helpers.

## Adaptations

Python keeps Rust `run_main` as a deterministic startup/request plan rather
than starting the full in-process app-server inside this module. Transport
startup remains owned by the app-server client boundary, but the exec-owned
decisions and request/session contracts are mirrored and tested here.

## Evidence

- Rust source inspected: `codex/codex-rs/exec/src/lib.rs`.
- Rust tests inspected: `codex/codex-rs/exec/src/lib_tests.rs`.
- Python implementation inspected:
  `pycodex/exec/__init__.py`, `pycodex/exec/run.py`,
  `pycodex/exec/session.py`, `pycodex/exec/config_plan.py`.
- Python tests inspected:
  `tests/test_exec_run.py`, `tests/test_exec_session.py`,
  `tests/test_exec_config_plan.py`.
- Focused validation passed on 2026-06-17:
  `python -m pytest tests/test_exec_cli.py tests/test_exec_run.py
  tests/test_exec_session.py tests/test_exec_config_plan.py
  tests/test_exec_event_processor.py -q` -> `320 passed, 12 subtests passed`.
