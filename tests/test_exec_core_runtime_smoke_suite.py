"""Core runtime smoke regression suite.

Run with:
    python -m unittest tests.test_exec_core_runtime_smoke_suite
"""

from __future__ import annotations

import unittest

from tests.test_exec_core_runtime import ExecCoreRuntimeTests


CORE_RUNTIME_SMOKE_TESTS: tuple[tuple[type[unittest.TestCase], str], ...] = (
    (
        ExecCoreRuntimeTests,
        "test_build_default_core_exec_runtime_rewrites_auth_error",
    ),
    (
        ExecCoreRuntimeTests,
        "test_resolve_core_exec_resume_target_aligns_named_session",
    ),
    (
        ExecCoreRuntimeTests,
        "test_run_core_exec_command_runs_fresh_exec_and_persists",
    ),
    (
        ExecCoreRuntimeTests,
        "test_run_core_exec_command_runs_review_and_persists",
    ),
    (
        ExecCoreRuntimeTests,
        "test_run_core_exec_command_runs_resume_without_persisting",
    ),
    (
        ExecCoreRuntimeTests,
        "test_run_core_exec_command_resume_without_target_starts_new_turn_and_persists",
    ),
    (
        ExecCoreRuntimeTests,
        "test_run_core_exec_command_resume_pre_resolved_miss_does_not_lookup_again",
    ),
)


def core_exec_runtime_smoke_suite() -> unittest.TestSuite:
    return unittest.TestSuite(
        test_class(test_name)
        for test_class, test_name in CORE_RUNTIME_SMOKE_TESTS
    )


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return core_exec_runtime_smoke_suite()


if __name__ == "__main__":
    unittest.main()
