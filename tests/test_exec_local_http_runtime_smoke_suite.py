"""Core local HTTP exec runtime smoke regression suite.

Run with:
    python -m unittest tests.test_exec_local_http_runtime_smoke_suite
"""

from __future__ import annotations

import unittest

from tests.test_exec_local_runtime import ExecLocalRuntimeTests, LocalHttpShellToolSpecTests


CORE_LOCAL_HTTP_RUNTIME_SMOKE_TESTS: tuple[tuple[type[unittest.TestCase], str], ...] = (
    (
        LocalHttpShellToolSpecTests,
        "test_local_http_shell_command_execution_argv_uses_default_user_shell",
    ),
    (
        LocalHttpShellToolSpecTests,
        "test_local_http_shell_tool_exec_policy_command_uses_same_shell_argv",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_resume_runner_uses_reconstructed_model_history",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_rollout_removes_orphan_tool_outputs_from_raw_payload",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_rollout_inserts_missing_output_for_local_shell_call",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_tool_timeline_uses_response_item_calls_when_raw_payload_is_absent",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_tool_timeline_uses_response_item_outputs_when_raw_payload_is_absent",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_tool_timeline_drops_orphan_function_and_custom_outputs",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_tool_timeline_maps_local_shell_call_to_command_execution",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_exec_shell_tool_loop_returns_followup_answer",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_exec_shell_tool_loop_returns_apply_patch_followup_answer",
    ),
    (
        ExecLocalRuntimeTests,
        "test_local_http_exec_shell_tool_loop_returns_request_permissions_success",
    ),
)


def core_local_http_runtime_smoke_suite() -> unittest.TestSuite:
    return unittest.TestSuite(
        test_class(test_name)
        for test_class, test_name in CORE_LOCAL_HTTP_RUNTIME_SMOKE_TESTS
    )


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return core_local_http_runtime_smoke_suite()


if __name__ == "__main__":
    unittest.main()
