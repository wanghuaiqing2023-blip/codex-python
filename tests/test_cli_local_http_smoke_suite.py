"""Core local HTTP CLI smoke regression suite.

Run with:
    python -m unittest tests.test_cli_local_http_smoke_suite
"""

from __future__ import annotations

import unittest

from tests.test_cli_parser import TopLevelCliParserTests


CORE_LOCAL_HTTP_CLI_SMOKE_TESTS: tuple[tuple[type[unittest.TestCase], str], ...] = (
    (
        TopLevelCliParserTests,
        "test_main_prompt_without_subcommand_uses_local_http_exec_when_available",
    ),
    (
        TopLevelCliParserTests,
        "test_main_prompt_without_subcommand_forwards_root_image_to_local_http_exec",
    ),
    (
        TopLevelCliParserTests,
        "test_main_prompt_without_subcommand_forwards_root_cd_to_local_http_exec",
    ),
    (
        TopLevelCliParserTests,
        "test_main_prompt_without_subcommand_forwards_root_model_to_local_http_exec",
    ),
    (
        TopLevelCliParserTests,
        "test_main_prompt_without_subcommand_forwards_root_approval_to_local_http_exec",
    ),
    (
        TopLevelCliParserTests,
        "test_main_prompt_without_subcommand_forwards_root_dangerous_bypass_to_local_http_exec",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_sse_smoke_outputs_final_message",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_sse_streamed_exec_command_runs_tool_and_followup",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_sse_streamed_apply_patch_runs_tool_and_followup",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_view_image_smoke_returns_image_content",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_output_schema_smoke_reaches_followup_request",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_exec_command_apply_patch_heredoc_smoke",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_json_local_shell_call_smoke_outputs_command_execution",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_json_orphan_tool_outputs_are_hidden",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_write_stdin_smoke_continues_session_and_followup",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_resume_local_http_smoke_reads_history_and_appends_rollout",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_resume_local_http_output_schema_smoke_reaches_followup_request",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_shell_tool_on_request_requires_approval",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_apply_patch_on_request_requires_approval",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_request_permissions_on_request_returns_cancel_output",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_context_window_error_prints_json_error_event",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_provider_http_error_prints_json_error_event",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_provider_rate_limit_prints_json_error_event",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_retryable_stream_error_retries_and_succeeds",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_provider_usage_limit_prints_json_error_event",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_provider_connection_error_prints_human_error_event",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_provider_timeout_prints_json_error_event",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_interrupted_prints_json_without_partial_and_persists_marker",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_resume_local_http_interrupted_appends_marker_and_suppresses_partial",
    ),
    (
        TopLevelCliParserTests,
        "test_main_exec_local_http_shell_tool_followup_interrupted_persists_tool_and_marker",
    ),
)


def core_local_http_cli_smoke_suite() -> unittest.TestSuite:
    return unittest.TestSuite(
        test_class(test_name)
        for test_class, test_name in CORE_LOCAL_HTTP_CLI_SMOKE_TESTS
    )


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return core_local_http_cli_smoke_suite()


if __name__ == "__main__":
    unittest.main()
