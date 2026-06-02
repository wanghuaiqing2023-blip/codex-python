"""Core local HTTP smoke regression suite for CLI and runtime paths.

Run with:
    python -m unittest tests.test_local_http_core_smoke_suite
"""

from __future__ import annotations

import unittest

from tests.test_cli_local_http_smoke_suite import core_local_http_cli_smoke_suite
from tests.test_exec_local_http_runtime_smoke_suite import core_local_http_runtime_smoke_suite


def core_local_http_smoke_suite() -> unittest.TestSuite:
    return unittest.TestSuite(
        (
            core_local_http_cli_smoke_suite(),
            core_local_http_runtime_smoke_suite(),
        )
    )


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return core_local_http_smoke_suite()


if __name__ == "__main__":
    unittest.main()
