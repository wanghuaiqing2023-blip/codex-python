"""Core CLI smoke regression suite.

Run with:
    python -m unittest tests.test_cli_core_smoke_suite
"""

from __future__ import annotations

import unittest

from tests.test_cli_parser import TopLevelCliParserTests


CORE_CLI_SMOKE_TESTS: tuple[tuple[type[unittest.TestCase], str], ...] = (
    (
        TopLevelCliParserTests,
        "test_main_exec_core_env_uses_in_memory_core_http_sampling",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_api_key_defaults_to_core_runtime",
    ),
    (
        TopLevelCliParserTests,
        "test_main_review_core_env_uses_core_review_runner",
    ),
    (
        TopLevelCliParserTests,
        "test_main_review_api_key_defaults_to_core_review_runner",
    ),
    (
        TopLevelCliParserTests,
        "test_main_prompt_without_subcommand_uses_core_exec_when_core_only",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_resume_core_env_uses_core_resume_runner",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_resume_core_env_without_target_starts_new_core_turn",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_core_missing_api_key_prints_core_error",
    ),
)


def core_cli_smoke_suite() -> unittest.TestSuite:
    return unittest.TestSuite(
        test_class(test_name)
        for test_class, test_name in CORE_CLI_SMOKE_TESTS
    )


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return core_cli_smoke_suite()


if __name__ == "__main__":
    unittest.main()
