# Unified Exec Snapshot Timing

- Updated `pycodex/core/unified_exec.py` session snapshot behavior to avoid over-draining output on interactive (`tty=True`) commands.
- Added output-close tracking (`_output_closed`) and deadline/post-exit wait logic in `_ManagedUnifiedExecSession.snapshot()`.
- Kept non-interactive (`tty=False`) behavior of waiting through completion so completed commands still return terminal output and are cleaned up.
- Verified with `tests/test_core_unified_exec.py::CoreUnifiedExecHeadTailBufferTests`, `tests/test_core_unified_exec.py`, `tests/test_core_unified_exec_handler.py`, and `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_default_session_exec_command_then_write_stdin`.
