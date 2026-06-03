"""Core-focused smoke suite for CLI + runtime behavior."""

from __future__ import annotations

import unittest

from tests.test_cli_core_smoke_suite import core_cli_smoke_suite
from tests.test_exec_core_runtime_smoke_suite import core_exec_runtime_smoke_suite


def core_smoke_suite() -> unittest.TestSuite:
    return unittest.TestSuite(
        (
            core_cli_smoke_suite(),
            core_exec_runtime_smoke_suite(),
        )
    )


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return core_smoke_suite()


if __name__ == "__main__":
    unittest.main()
