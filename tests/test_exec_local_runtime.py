import json
import tempfile
import io
import os
import re
import sys
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from pathlib import Path

from pycodex.core import (
    SessionMeta,
    append_thread_name,
    count_session_rollout_files,
    find_session_rollout_containing_response_marker,
    last_user_image_count_in_rollout,
    materialize_session_rollout,
    read_response_items_from_rollout,
    read_thread_item_from_rollout,
)
from pycodex.core.client import ModelClient
from pycodex.exec.event_processor import HumanEventProcessor, JsonEventProcessor
from pycodex.exec.local_runtime import (
    build_default_local_http_exec_runtime,
    default_local_http_exec_auth,
    default_local_http_exec_base_url,
    default_local_http_exec_model,
    DEFAULT_LOCAL_HTTP_MAX_OUTPUT_TOKENS,
    LOCAL_HTTP_APPROX_BYTES_PER_TOKEN,
    emit_local_http_exec_error,
    emit_local_http_exec_result,
    final_text_from_response_items,
    LocalHttpHeadTailBuffer,
    LocalHttpExecSessionManager,
    LOCAL_HTTP_EXEC_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
    LOCAL_HTTP_EXEC_EARLY_EXIT_GRACE_PERIOD_MS,
    LOCAL_HTTP_EXEC_MAX_YIELD_TIME_MS,
    LOCAL_HTTP_EXEC_MIN_EMPTY_STDIN_YIELD_TIME_MS,
    LOCAL_HTTP_EXEC_MIN_YIELD_TIME_MS,
    LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES,
    LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS,
    LOCAL_HTTP_EXEC_TRAILING_OUTPUT_GRACE_MS,
    LOCAL_HTTP_EXEC_TIMEOUT_EXIT_CODE,
    LOCAL_HTTP_MAX_UNIFIED_EXEC_PROCESSES,
    align_local_http_exec_resume_model_client,
    local_http_exec_enabled,
    local_http_generate_chunk_id,
    local_http_retain_head_tail_output,
    local_http_exec_schema_output_payload,
    local_http_exec_output_text,
    local_http_apply_patch_tool_spec,
    local_http_exec_config_summary,
    local_http_exec_max_tool_rounds,
    local_http_request_permissions_tool_spec,
    local_http_write_stdin_tool_spec,
    local_http_shell_tool_auto_execute_allowed,
    local_http_shell_tool_spec,
    local_http_shell_tools_built_tools,
    local_http_exec_tool_output_max_chars,
    reasoning_texts_from_local_http_exec_result,
    persist_local_http_exec_resume_rollout,
    response_items_from_local_http_tool_outputs,
    resolve_local_http_exec_resume_rollout_path,
    run_exec_tool_output_http_sampling,
    run_exec_resume_user_turn_http_sampling,
    run_exec_user_turn_default_local_http_sampling,
    run_exec_user_turn_http_sampling,
    run_exec_user_turn_with_shell_tools_http_sampling,
    shell_tool_outputs_from_local_http_exec_result,
    tool_call_items_from_local_http_exec_result,
    tool_output_items_from_local_http_exec_result,
    tool_timeline_items_from_local_http_exec_result,
    usage_from_local_http_exec_result,
    _approx_bytes_for_tokens,
    _approx_token_count,
    _truncate_shell_tool_output,
)
from pycodex.exec.run import ExecRunPlan, InitialOperation
from pycodex.exec.session import ExecSessionConfig
from pycodex.protocol import AskForApproval, UserInput


class FakeResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return []


class ExistingToolRouter:
    def model_visible_specs(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "name": "existing",
                "description": "Existing test tool",
                "parameters": {"type": "object", "properties": {}},
            }
        ]


class FakeUsageResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ],
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 3},
                    "output_tokens": 7,
                    "output_tokens_details": {"reasoning_tokens": 2},
                },
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeReasoningResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "thinking summary"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    },
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallResponse:
    def __init__(self, usage: dict | None = None, call_id: str = "call-1") -> None:
        self.usage = usage
        self.call_id = call_id

    def read(self) -> bytes:
        payload = {
            "output": [
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"command\":\"pwd\"}",
                    "call_id": self.call_id,
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "I need to run a command."}],
                },
            ]
        }
        if self.usage is not None:
            payload["usage"] = self.usage
        return json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeExecCommandToolCallResponse:
    def __init__(self, shell: str | None = None) -> None:
        self.shell = shell

    def read(self) -> bytes:
        arguments = {"cmd": "pwd", "max_output_tokens": 4}
        if self.shell is not None:
            arguments["shell"] = self.shell
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": json.dumps(arguments),
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeWriteStdinToolCallResponse:
    def __init__(
        self,
        session_id: int = 7,
        chars: str = "hello\n",
        yield_time_ms: int | None = 100,
        max_output_tokens: int | None = None,
    ) -> None:
        self.session_id = session_id
        self.chars = chars
        self.yield_time_ms = yield_time_ms
        self.max_output_tokens = max_output_tokens

    def read(self) -> bytes:
        arguments = {
            "session_id": self.session_id,
            "chars": self.chars,
        }
        if self.yield_time_ms is not None:
            arguments["yield_time_ms"] = self.yield_time_ms
        if self.max_output_tokens is not None:
            arguments["max_output_tokens"] = self.max_output_tokens
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "write_stdin",
                        "arguments": json.dumps(arguments),
                        "call_id": "stdin-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeRequestPermissionsToolCallResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "request_permissions",
                        "arguments": "{\"permissions\":{\"network\":{\"enabled\":true}}}",
                        "call_id": "permissions-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeSessionExecCommandToolCallResponse:
    def __init__(
        self,
        command: str,
        *,
        yield_time_ms: int | None = 500,
        timeout_ms: int | None = None,
        shell: str | None = None,
        tty: bool | None = None,
    ) -> None:
        self.command = command
        self.yield_time_ms = yield_time_ms
        self.timeout_ms = timeout_ms
        self.shell = shell
        self.tty = tty

    def read(self) -> bytes:
        arguments = {"cmd": self.command}
        if self.yield_time_ms is not None:
            arguments["yield_time_ms"] = self.yield_time_ms
        if self.timeout_ms is not None:
            arguments["timeout_ms"] = self.timeout_ms
        if self.shell is not None:
            arguments["shell"] = self.shell
        if self.tty is not None:
            arguments["tty"] = self.tty
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": json.dumps(arguments),
                        "call_id": "call-session",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithWorkdirTimeoutResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\",\"workdir\":\"subdir\",\"timeout_ms\":2500}",
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithLoginResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\",\"login\":true}",
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithApprovalMetadataResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": (
                            "{\"command\":\"pwd\","
                            "\"sandbox_permissions\":\"with_additional_permissions\","
                            "\"additional_permissions\":{\"network\":{\"enabled\":true},\"file_system\":{\"read\":[],\"write\":[]}},"
                            "\"justification\":\"Need to inspect the workspace\"}"
                        ),
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithMissingAdditionalPermissionsResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\",\"sandbox_permissions\":\"with_additional_permissions\"}",
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithBareAdditionalPermissionsResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\",\"additional_permissions\":{\"network\":{\"enabled\":true}}}",
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithEmptyAdditionalPermissionsResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": (
                            "{\"command\":\"pwd\","
                            "\"sandbox_permissions\":\"with_additional_permissions\","
                            "\"additional_permissions\":{\"network\":{},\"file_system\":{\"read\":[],\"write\":[]}}}"
                        ),
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithRequireEscalatedResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\",\"sandbox_permissions\":\"require_escalated\"}",
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithInvalidSandboxPermissionsResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\",\"sandbox_permissions\":\"full-power\"}",
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithPrefixRuleResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": (
                            "{\"command\":\"python -m pytest\","
                            "\"prefix_rule\":[\"python\",\"-m\"]}"
                        ),
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeApplyPatchToolCallResponse:
    def __init__(self, patch: str | None = None) -> None:
        self.patch = patch or "*** Begin Patch\n*** Add File: created.txt\n+hello\n*** End Patch\n"

    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "custom_tool_call",
                        "name": "apply_patch",
                        "input": self.patch,
                        "call_id": "patch-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolOutputResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call_output",
                        "name": "shell",
                        "call_id": "call-1",
                        "output": "C:/work/project",
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "The command returned the workdir."}],
                    },
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class LocalHttpShellToolSpecTests(unittest.TestCase):
    def test_local_http_shell_tool_spec_shape(self) -> None:
        spec = local_http_shell_tool_spec()

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], "exec_command")
        self.assertIn("Runs a command in a PTY", spec["description"])
        if os.name == "nt":
            self.assertIn("Windows safety rules:", spec["description"])
            self.assertIn("Start-Process", spec["description"])
        self.assertIs(spec["strict"], False)
        self.assertIsNone(spec["defer_loading"])
        self.assertEqual(spec["parameters"]["required"], ["cmd"])
        self.assertIn("workdir", spec["parameters"]["properties"])
        self.assertIn("cwd", spec["parameters"]["properties"])
        self.assertIn("yield_time_ms", spec["parameters"]["properties"])
        self.assertIn("max_output_tokens", spec["parameters"]["properties"])
        self.assertIn("timeout", spec["parameters"]["properties"])
        login = spec["parameters"]["properties"]["login"]
        self.assertIn("-l/-i semantics", login["description"])
        self.assertIn("Defaults to true", login["description"])
        self.assertIn("additional_permissions", spec["parameters"]["properties"])
        sandbox_permissions = spec["parameters"]["properties"]["sandbox_permissions"]
        self.assertIn("with_additional_permissions", sandbox_permissions["description"])
        self.assertIn("require_escalated", sandbox_permissions["description"])
        justification = spec["parameters"]["properties"]["justification"]
        self.assertIn("Only set if sandbox_permissions", justification["description"])
        self.assertIn("Do you want to", justification["description"])
        prefix_rule = spec["parameters"]["properties"]["prefix_rule"]
        self.assertIn("Only specify when sandbox_permissions", prefix_rule["description"])
        self.assertIn('["git", "pull"]', prefix_rule["description"])
        additional_permissions = spec["parameters"]["properties"]["additional_permissions"]
        self.assertFalse(additional_permissions["additionalProperties"])
        self.assertIn("network", additional_permissions["properties"])
        self.assertIn("file_system", additional_permissions["properties"])
        self.assertIn("enabled", additional_permissions["properties"]["network"]["properties"])
        file_system = additional_permissions["properties"]["file_system"]
        self.assertFalse(file_system["additionalProperties"])
        self.assertIn("read", file_system["properties"])
        self.assertIn("write", file_system["properties"])
        self.assertEqual(spec["output_schema"]["required"], ["wall_time_seconds", "output"])
        output_schema = spec["output_schema"]
        self.assertFalse(output_schema["additionalProperties"])
        self.assertIn("chunk_id", output_schema["properties"])
        self.assertIn("exit_code", output_schema["properties"])
        self.assertIn("session_id", output_schema["properties"])
        self.assertIn("original_token_count", output_schema["properties"])
        self.assertIn("possibly truncated", output_schema["properties"]["output"]["description"])
        self.assertFalse(spec["parameters"]["additionalProperties"])

    def test_local_http_apply_patch_tool_spec_shape(self) -> None:
        spec = local_http_apply_patch_tool_spec()

        self.assertEqual(spec["type"], "custom")
        self.assertEqual(spec["name"], "apply_patch")
        self.assertEqual(spec["format"]["type"], "grammar")

    def test_local_http_write_stdin_tool_spec_shape(self) -> None:
        spec = local_http_write_stdin_tool_spec()

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], "write_stdin")
        self.assertIs(spec["strict"], False)
        self.assertIsNone(spec["defer_loading"])
        self.assertEqual(spec["parameters"]["required"], ["session_id"])
        self.assertIn("chars", spec["parameters"]["properties"])
        self.assertIn("yield_time_ms", spec["parameters"]["properties"])
        self.assertIn("max_output_tokens", spec["parameters"]["properties"])
        self.assertEqual(spec["output_schema"]["required"], ["wall_time_seconds", "output"])
        self.assertFalse(spec["output_schema"]["additionalProperties"])

    def test_local_http_request_permissions_tool_spec_shape(self) -> None:
        spec = local_http_request_permissions_tool_spec()

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], "request_permissions")
        self.assertIs(spec["strict"], False)
        self.assertIsNone(spec["defer_loading"])
        self.assertIsNone(spec["output_schema"])
        self.assertEqual(spec["parameters"]["required"], ["permissions"])
        self.assertFalse(spec["parameters"]["additionalProperties"])
        properties = spec["parameters"]["properties"]
        self.assertIn("reason", properties)
        permissions = properties["permissions"]
        self.assertFalse(permissions["additionalProperties"])
        self.assertIn("network", permissions["properties"])
        self.assertIn("file_system", permissions["properties"])
        self.assertIn("enabled", permissions["properties"]["network"]["properties"])
        file_system = permissions["properties"]["file_system"]
        self.assertIn("read", file_system["properties"])
        self.assertIn("write", file_system["properties"])

    def test_local_http_shell_tools_built_tools_preserves_existing_specs(self) -> None:
        router = local_http_shell_tools_built_tools(lambda _session, _turn: ExistingToolRouter())(None, None)
        specs = router.model_visible_specs()

        self.assertEqual(
            [spec["name"] for spec in specs],
            ["existing", "exec_command", "write_stdin", "request_permissions", "apply_patch"],
        )

    def test_local_http_shell_tools_built_tools_accepts_async_base_builder(self) -> None:
        async def build_base(_session, _turn):
            return ExistingToolRouter()

        router = asyncio.run(local_http_shell_tools_built_tools(build_base)(None, None))
        specs = router.model_visible_specs()

        self.assertEqual(
            [spec["name"] for spec in specs],
            ["existing", "exec_command", "write_stdin", "request_permissions", "apply_patch"],
        )

    def test_local_http_generate_chunk_id_shape(self) -> None:
        self.assertRegex(local_http_generate_chunk_id(), r"^[0-9a-f]{6}$")

    def test_local_http_retain_head_tail_output_caps_large_output(self) -> None:
        retained = local_http_retain_head_tail_output("0123456789abcdefghijklmnopqrstuvwxyz", 10)

        self.assertEqual(retained, "01234vwxyz")
        self.assertLessEqual(len(retained.encode("utf-8")), 10)

    def test_local_http_retain_head_tail_output_caps_multibyte_output_by_utf8_bytes(self) -> None:
        retained = local_http_retain_head_tail_output("甲乙丙丁abcd戊己庚辛", 12)

        self.assertEqual(retained, "甲乙庚辛")
        self.assertLessEqual(len(retained.encode("utf-8")), 12)

    def test_local_http_exec_output_hard_cap_constant_matches_rust(self) -> None:
        self.assertEqual(LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES, 1024 * 1024)
        self.assertEqual(LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS, LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES // 4)
        self.assertEqual(LOCAL_HTTP_EXEC_EARLY_EXIT_GRACE_PERIOD_MS, 150)
        self.assertEqual(LOCAL_HTTP_EXEC_TRAILING_OUTPUT_GRACE_MS, 100)

    def test_local_http_head_tail_buffer_fills_head_then_tail_across_chunks(self) -> None:
        buffer = LocalHttpHeadTailBuffer(10)
        buffer.push_text("01")
        buffer.push_text("234")
        self.assertEqual(buffer.to_bytes(), b"01234")

        buffer.push_text("567")
        buffer.push_text("89")
        self.assertEqual(buffer.retained_bytes(), 10)
        self.assertEqual(buffer.omitted_bytes(), 0)
        buffer.push_text("a")

        self.assertEqual(buffer.to_bytes(), b"012346789a")
        self.assertEqual(buffer.omitted_bytes(), 1)
        self.assertEqual(buffer.drain_text(), "012346789a")
        self.assertEqual(buffer.retained_bytes(), 0)
        self.assertEqual(buffer.omitted_bytes(), 0)
        self.assertEqual(buffer.to_bytes(), b"")

    def test_local_http_head_tail_buffer_zero_budget_drops_everything(self) -> None:
        buffer = LocalHttpHeadTailBuffer(0)

        buffer.push_chunk(b"abc")

        self.assertEqual(buffer.retained_bytes(), 0)
        self.assertEqual(buffer.omitted_bytes(), 3)
        self.assertEqual(buffer.to_bytes(), b"")
        self.assertEqual(buffer.snapshot_chunks(), [])

    def test_local_http_head_tail_buffer_drain_text_replaces_invalid_utf8(self) -> None:
        buffer = LocalHttpHeadTailBuffer(10)
        buffer.push_chunk(b"ok\xffdone")

        self.assertEqual(buffer.drain_text(), "ok\ufffddone")

    def test_local_http_head_tail_buffer_large_chunk_replaces_tail_end(self) -> None:
        buffer = LocalHttpHeadTailBuffer(10)

        buffer.push_chunk(b"0123456789")
        buffer.push_chunk(b"ABCDEFGHIJK")

        out = buffer.to_bytes()
        self.assertTrue(out.startswith(b"01234"))
        self.assertTrue(out.endswith(b"GHIJK"))
        self.assertGreater(buffer.omitted_bytes(), 0)

    def test_local_http_shell_tool_truncation_uses_utf8_byte_budget(self) -> None:
        output = _truncate_shell_tool_output("甲乙丙丁", 8)

        self.assertIn("Total output lines: 1", output)
        self.assertIn("chars truncated", output)
        self.assertNotEqual(output, "甲乙丙丁")

    def test_local_http_approx_token_count_uses_utf8_bytes(self) -> None:
        self.assertEqual(_approx_token_count("abcd"), 1)
        self.assertEqual(_approx_token_count("甲乙"), 2)

    def test_local_http_approx_bytes_for_tokens_matches_rust_ratio(self) -> None:
        self.assertEqual(LOCAL_HTTP_APPROX_BYTES_PER_TOKEN, 4)
        self.assertEqual(_approx_bytes_for_tokens(0), 0)
        self.assertEqual(_approx_bytes_for_tokens(3), 12)

    def test_local_http_exec_output_max_tokens_matches_rust_ratio(self) -> None:
        self.assertEqual(LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS, LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES // 4)
        self.assertEqual(_approx_bytes_for_tokens(LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS), LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES)


class ExecLocalRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_exec_user_turn_http_sampling_uses_exec_config_and_plan(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        config = ExecSessionConfig(
            model="gpt-test",
            model_provider_id="openai",
            cwd=Path("C:/work/project"),
            user_instructions="project instructions",
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn(
                (UserInput.text_input("hello"),),
                output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            ),
            "hello",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = {"base_url": "https://api.example.test/v1"}

        result = await run_exec_user_turn_http_sampling(
            config,
            plan,
            client,
            provider,
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(seen["body"]["instructions"], "base")
        input_texts = [item["content"][0]["text"] for item in seen["body"]["input"] if item.get("content")]
        self.assertTrue(any("project instructions" in text for text in input_texts))
        self.assertIn("hello", input_texts)
        self.assertEqual(seen["body"]["text"]["format"]["schema"]["properties"]["ok"]["type"], "boolean")

    async def test_run_exec_user_turn_http_sampling_can_preload_resume_history(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("current prompt"),)), "current prompt")
        with tempfile.TemporaryDirectory() as tmpdir:
            rollout_path = Path(tmpdir) / "rollout.jsonl"
            rollout_path.write_text(
                "\n".join(
                    [
                        json.dumps({"timestamp": "0", "type": "session_meta", "payload": {}}),
                        json.dumps(
                            {
                                "timestamp": "1",
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": "previous user"}],
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2",
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [{"type": "output_text", "text": "previous assistant"}],
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            history_items = read_response_items_from_rollout(rollout_path)

            await run_exec_user_turn_http_sampling(
                config,
                plan,
                ModelClient(session_id="session", thread_id="thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
                history_items=history_items,
            )

        message_items = [item for item in seen["body"]["input"] if item.get("type") == "message"]
        self.assertEqual([item["role"] for item in message_items[-3:]], ["user", "assistant", "user"])
        self.assertEqual(message_items[-3]["content"][0]["text"], "previous user")
        self.assertEqual(message_items[-2]["content"][0]["text"], "previous assistant")
        self.assertEqual(message_items[-1]["content"][0]["text"], "current prompt")

    async def test_default_local_http_runtime_uses_env_provider_and_model(self) -> None:
        seen = {}

        def opener(request):
            seen["url"] = request.full_url
            seen["headers"] = dict(request.header_items())
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            user_instructions=None,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        env = {
            "PYCODEX_EXEC_LOCAL_HTTP": "1",
            "OPENAI_API_KEY": "sk-env",
            "OPENAI_MODEL": "gpt-env",
            "OPENAI_BASE_URL": "https://api.example.test/v1",
        }

        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env=env,
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertTrue(local_http_exec_enabled(env))
        self.assertEqual(seen["url"], "https://api.example.test/v1/responses")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer sk-env")
        headers = {key.lower(): value for key, value in seen["headers"].items()}
        self.assertTrue(headers["X-codex-window-id".lower()].endswith(":0"))
        self.assertEqual(seen["body"]["client_metadata"]["x-codex-installation-id"], "pycodex-local-exec")
        self.assertEqual(seen["body"]["model"], "gpt-env")
        self.assertEqual(final_text_from_response_items(result.response_items), "done")

        stdout = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=stdout,
            stderr=io.StringIO(),
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertEqual(stdout.getvalue(), "done\n")

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual([line["type"] for line in json_lines], ["turn.started", "item.completed", "turn.completed"])
        self.assertEqual(json_lines[1]["item"]["type"], "agent_message")
        self.assertEqual(json_lines[1]["item"]["text"], "done")

        error_stderr = io.StringIO()
        emit_local_http_exec_error(
            HumanEventProcessor(),
            "boom",
            stderr=error_stderr,
        )
        self.assertIn("ERROR: boom", error_stderr.getvalue())

        error_stdout = io.StringIO()
        emit_local_http_exec_error(JsonEventProcessor(), "boom", stdout=error_stdout)
        error_lines = [json.loads(line) for line in error_stdout.getvalue().splitlines()]
        self.assertEqual([line["type"] for line in error_lines], ["turn.started", "turn.failed"])
        self.assertEqual(error_lines[1]["error"]["message"], "boom")

    async def test_default_local_http_runtime_materializes_rollout_unless_ephemeral(self) -> None:
        def opener(_request):
            return FakeResponse()

        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.image("data:image/png;base64,AAAA"), UserInput.text_input("hello"))),
            "hello",
        )
        env = {"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"}
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            persistent_config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path("C:/work/project"),
                ephemeral=False,
            )
            ephemeral_config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path("C:/work/project"),
                ephemeral=True,
            )

            await run_exec_user_turn_default_local_http_sampling(
                persistent_config,
                plan,
                env=env,
                codex_home=codex_home,
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )
            await run_exec_user_turn_default_local_http_sampling(
                ephemeral_config,
                plan,
                env=env,
                codex_home=codex_home,
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            self.assertEqual(count_session_rollout_files(codex_home), 1)
            rollout_path = find_session_rollout_containing_response_marker(codex_home, "done")
            self.assertIsNotNone(rollout_path)
            assert rollout_path is not None
            self.assertEqual(read_thread_item_from_rollout(rollout_path).cwd, Path("C:/work/project"))
            self.assertEqual(last_user_image_count_in_rollout(rollout_path), 1)

    async def test_local_http_resume_rollout_appends_to_existing_thread_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "11111111-1111-1111-1111-111111111111"
            config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/resume"))
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/resume",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:05Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "initial", "kind": "plain"},
                        }
                    )
                    + "\n"
                )
            result = SimpleNamespace(
                response_items=(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "resumed marker"}],
                    },
                )
            )

            appended = persist_local_http_exec_resume_rollout(
                codex_home,
                config,
                result,
                input_items=(UserInput.image("data:image/png;base64,AAAA"), UserInput.text_input("resume")),
                thread_id=thread_id,
            )

            self.assertEqual(appended, rollout_path)
            self.assertEqual(count_session_rollout_files(codex_home), 1)
            self.assertEqual(find_session_rollout_containing_response_marker(codex_home, "resumed marker"), rollout_path)
            self.assertEqual(read_thread_item_from_rollout(rollout_path).cwd, Path("C:/work/resume"))
            self.assertEqual(last_user_image_count_in_rollout(rollout_path), 1)

    async def test_local_http_resume_runner_reads_history_and_appends_result_to_same_rollout(self) -> None:
        request_bodies = []
        request_headers = []

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            request_headers.append({key.lower(): value for key, value in request.header_items()})
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "22222222-2222-2222-2222-222222222222"
            config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/resume"))
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/resume",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                for payload in (
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "previous user"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "previous assistant"}],
                    },
                ):
                    file.write(json.dumps({"timestamp": "2025-01-02T03:04:05Z", "type": "response_item", "payload": payload}) + "\n")

            plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("current prompt"),)), "current prompt")

            result = await run_exec_resume_user_turn_http_sampling(
                codex_home,
                config,
                plan,
                ModelClient(session_id="session", thread_id="new-thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                thread_id=thread_id,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            self.assertEqual(final_text_from_response_items(result.response_items), "done")
            message_items = [item for item in request_bodies[0]["input"] if item.get("type") == "message"]
            self.assertEqual([item["role"] for item in message_items[-3:]], ["user", "assistant", "user"])
            self.assertEqual(message_items[-3]["content"][0]["text"], "previous user")
            self.assertEqual(message_items[-2]["content"][0]["text"], "previous assistant")
            self.assertEqual(message_items[-1]["content"][0]["text"], "current prompt")
            self.assertEqual(request_headers[0]["session-id"], thread_id)
            self.assertEqual(request_headers[0]["thread-id"], thread_id)
            self.assertEqual(request_headers[0]["x-client-request-id"], thread_id)
            self.assertEqual(count_session_rollout_files(codex_home), 1)
            self.assertEqual(find_session_rollout_containing_response_marker(codex_home, "done"), rollout_path)
            self.assertEqual(read_response_items_from_rollout(rollout_path)[-1].content[0].text, "done")

    async def test_local_http_resume_identity_alignment_updates_model_client_before_sampling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "55555555-5555-5555-5555-555555555555"
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/resume",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            assert rollout_path is not None
            client = ModelClient(session_id="session", thread_id="fresh-thread", installation_id="install")

            aligned = align_local_http_exec_resume_model_client(
                codex_home,
                ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/resume")),
                client,
                thread_id=thread_id,
            )

            self.assertEqual(aligned, rollout_path)
            self.assertEqual(client.state.thread_id, thread_id)

    async def test_local_http_resume_runner_uses_pre_resolved_rollout_path(self) -> None:
        request_headers = []

        def opener(request):
            request_headers.append({key.lower(): value for key, value in request.header_items()})
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "66666666-6666-6666-6666-666666666666"
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/resume",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            assert rollout_path is not None
            client = ModelClient(session_id="session", thread_id="fresh-thread", installation_id="install")

            await run_exec_resume_user_turn_http_sampling(
                codex_home,
                ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/resume")),
                ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("current"),)), "current"),
                client,
                {"base_url": "https://api.example.test/v1"},
                model_info,
                thread_id="not-a-real-thread",
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
                resolved_rollout_path=rollout_path,
            )

            self.assertEqual(client.state.thread_id, thread_id)
            self.assertEqual(request_headers[0]["session-id"], thread_id)
            self.assertEqual(request_headers[0]["thread-id"], thread_id)

    async def test_local_http_resume_runner_resolves_named_session_through_index(self) -> None:
        request_bodies = []

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "33333333-3333-3333-3333-333333333333"
            config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/named"))
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/named",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            assert rollout_path is not None
            append_thread_name(codex_home, thread_id, "daily-work")
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:05Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "previous", "kind": "plain"},
                        }
                    )
                    + "\n"
                )
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:06Z",
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "previous named"}],
                            },
                        }
                    )
                    + "\n"
                )

            self.assertEqual(
                resolve_local_http_exec_resume_rollout_path(codex_home, config, session_name="daily-work"),
                rollout_path,
            )

            result = await run_exec_resume_user_turn_http_sampling(
                codex_home,
                config,
                ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("current named"),)), "current named"),
                ModelClient(session_id="session", thread_id=thread_id, installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                session_name="daily-work",
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            self.assertEqual(final_text_from_response_items(result.response_items), "done")
            message_items = [item for item in request_bodies[0]["input"] if item.get("type") == "message"]
            self.assertEqual(message_items[-2]["content"][0]["text"], "previous named")
            self.assertEqual(message_items[-1]["content"][0]["text"], "current named")
            self.assertEqual(find_session_rollout_containing_response_marker(codex_home, "done"), rollout_path)

    async def test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup(self) -> None:
        request_bodies = []

        class Completed:
            returncode = 0
            stdout = "C:/work/resume\n"
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

        responses = [FakeToolCallResponse(), FakeResponse()]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "44444444-4444-4444-4444-444444444444"
            config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/resume"))
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/resume",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:05Z",
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "previous shell"}],
                            },
                        }
                    )
                    + "\n"
                )

            result = await run_exec_resume_user_turn_http_sampling(
                codex_home,
                config,
                ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("current shell"),)), "current shell"),
                ModelClient(session_id="session", thread_id=thread_id, installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                thread_id=thread_id,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
                use_shell_tools=True,
                max_tool_rounds=1,
                runner=fake_runner,
            )

            self.assertEqual(final_text_from_response_items(result.response_items), "done")
            first_messages = [item for item in request_bodies[0]["input"] if item.get("type") == "message"]
            self.assertEqual(first_messages[-2]["content"][0]["text"], "previous shell")
            self.assertEqual(first_messages[-1]["content"][0]["text"], "current shell")
            self.assertEqual(len(request_bodies), 2)
            self.assertEqual(find_session_rollout_containing_response_marker(codex_home, "done"), rollout_path)
            persisted = read_response_items_from_rollout(rollout_path)
            persisted_types = [item.type for item in persisted]
            current_index = next(
                index
                for index, item in enumerate(persisted)
                if item.type == "message"
                and item.role == "user"
                and item.content
                and getattr(item.content[0], "text", None) == "current shell"
            )
            self.assertEqual(
                persisted_types[current_index + 1 : current_index + 4],
                ["function_call", "function_call_output", "message"],
            )

    async def test_local_http_exec_result_maps_usage(self) -> None:
        def opener(_request):
            return FakeUsageResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        env = {
            "PYCODEX_EXEC_LOCAL_HTTP": "1",
            "OPENAI_API_KEY": "sk-env",
            "OPENAI_BASE_URL": "https://api.example.test/v1",
        }

        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env=env,
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        usage = usage_from_local_http_exec_result(result)
        self.assertEqual(usage.input_tokens, 10)
        self.assertEqual(usage.cached_input_tokens, 3)
        self.assertEqual(usage.output_tokens, 7)
        self.assertEqual(usage.reasoning_output_tokens, 2)

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(json_lines[-1]["usage"]["input_tokens"], 10)
        self.assertEqual(json_lines[-1]["usage"]["cached_input_tokens"], 3)

        stderr = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=io.StringIO(),
            stderr=stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertIn("tokens used", stderr.getvalue())
        self.assertIn("14", stderr.getvalue())

    async def test_local_http_exec_shell_tool_loop_accumulates_usage(self) -> None:
        class Completed:
            returncode = 0
            stdout = "C:/work/project\n"
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

        first_usage = {
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 3},
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 2},
        }
        second_usage = {
            "input_tokens": 4,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens": 5,
            "output_tokens_details": {"reasoning_tokens": 1},
        }

        class UsageFinalResponse(FakeResponse):
            def read(self) -> bytes:
                payload = json.loads(super().read().decode("utf-8"))
                payload["usage"] = second_usage
                return json.dumps(payload).encode("utf-8")

        responses = [FakeToolCallResponse(first_usage), UsageFinalResponse()]

        def opener(_request):
            return responses.pop(0)

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
            runner=fake_runner,
            tool_timeout=5.0,
        )

        usage = usage_from_local_http_exec_result(result)
        self.assertEqual(usage.input_tokens, 14)
        self.assertEqual(usage.cached_input_tokens, 4)
        self.assertEqual(usage.output_tokens, 12)
        self.assertEqual(usage.reasoning_output_tokens, 3)

    async def test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds(self) -> None:
        request_bodies = []

        class Completed:
            returncode = 0
            stdout = "C:/work/project\n"
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

        responses = [FakeToolCallResponse(call_id="call-1"), FakeToolCallResponse(call_id="call-2"), FakeResponse()]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
            runner=fake_runner,
            tool_timeout=5.0,
            max_tool_rounds=2,
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 3)
        third_input = request_bodies[2]["input"]
        output_call_ids = [item["call_id"] for item in third_input if item["type"] == "function_call_output"]
        self.assertIn("call-1", output_call_ids)
        self.assertIn("call-2", output_call_ids)
        tool_call_items = tool_call_items_from_local_http_exec_result(result, JsonEventProcessor())
        tool_output_items = tool_output_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual(len(tool_call_items), 2)
        self.assertEqual(len(tool_output_items), 2)
        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual(
            [(item.payload["call_id"], item.payload["status"]) for item in timeline_items],
            [
                ("call-1", "in_progress"),
                ("call-1", "completed"),
                ("call-2", "in_progress"),
                ("call-2", "completed"),
            ],
        )
        self.assertEqual([item.id for item in timeline_items], ["item_0", "item_1", "item_2", "item_3"])
        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        tool_events = [line["item"] for line in json_lines if line["type"] == "item.completed" and line["item"]["type"] == "mcp_tool_call"]
        self.assertEqual(
            [(item["call_id"], item["status"]) for item in tool_events],
            [
                ("call-1", "in_progress"),
                ("call-1", "completed"),
                ("call-2", "in_progress"),
                ("call-2", "completed"),
            ],
        )
        self.assertEqual([item["id"] for item in tool_events], ["item_0", "item_1", "item_2", "item_3"])

    async def test_local_http_exec_result_maps_reasoning_json_event(self) -> None:
        def opener(_request):
            return FakeReasoningResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        env = {
            "PYCODEX_EXEC_LOCAL_HTTP": "1",
            "OPENAI_API_KEY": "sk-env",
            "OPENAI_BASE_URL": "https://api.example.test/v1",
        }

        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env=env,
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(reasoning_texts_from_local_http_exec_result(result), ("thinking summary",))

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(
            [line["type"] for line in json_lines],
            ["turn.started", "item.completed", "item.completed", "turn.completed"],
        )
        self.assertEqual(json_lines[1]["item"]["type"], "reasoning")
        self.assertEqual(json_lines[1]["item"]["text"], "thinking summary")
        self.assertEqual(json_lines[2]["item"]["type"], "agent_message")

    async def test_local_http_exec_result_maps_function_call_json_event_without_execution(self) -> None:
        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        env = {
            "PYCODEX_EXEC_LOCAL_HTTP": "1",
            "OPENAI_API_KEY": "sk-env",
            "OPENAI_BASE_URL": "https://api.example.test/v1",
        }

        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env=env,
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        processor = JsonEventProcessor()
        tool_items = tool_call_items_from_local_http_exec_result(result, processor)
        self.assertEqual(len(tool_items), 1)
        self.assertEqual(tool_items[0].type, "mcp_tool_call")
        self.assertEqual(tool_items[0].payload["server"], "responses")
        self.assertEqual(tool_items[0].payload["tool"], "shell")
        self.assertEqual(tool_items[0].payload["arguments"], {"command": "pwd"})
        self.assertEqual(tool_items[0].payload["status"], "in_progress")

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(
            [line["type"] for line in json_lines],
            ["turn.started", "item.completed", "item.completed", "turn.completed"],
        )
        self.assertEqual(json_lines[1]["item"]["type"], "mcp_tool_call")
        self.assertEqual(json_lines[1]["item"]["tool"], "shell")
        self.assertEqual(json_lines[1]["item"]["arguments"], {"command": "pwd"})
        self.assertEqual(json_lines[2]["item"]["type"], "agent_message")

    async def test_local_http_exec_shell_tool_output_execution_helper(self) -> None:
        seen = {}

        class Completed:
            returncode = 0
            stdout = "C:/work/project\n"
            stderr = ""

        def fake_runner(command, **kwargs):
            seen["command"] = command
            seen["cwd"] = kwargs["cwd"]
            seen["shell"] = kwargs["shell"]
            seen["timeout"] = kwargs["timeout"]
            return Completed()

        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner, timeout=5.0)

        self.assertEqual(seen["command"], "pwd")
        self.assertEqual(seen["cwd"], "C:\\work\\project")
        self.assertTrue(seen["shell"])
        self.assertEqual(seen["timeout"], 5.0)
        self.assertEqual(outputs[0]["type"], "function_call_output")
        self.assertEqual(outputs[0]["call_id"], "call-1")
        self.assertIs(outputs[0]["success"], True)
        self.assertIn("exit_code: 0", outputs[0]["output"])
        self.assertIn("C:/work/project", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_execution_failure_marks_unsuccessful(self) -> None:
        class Completed:
            returncode = 7
            stdout = ""
            stderr = "nope"

        def fake_runner(_command, **_kwargs):
            return Completed()

        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner)

        self.assertIs(outputs[0]["success"], False)
        self.assertIn("exit_code: 7", outputs[0]["output"])
        self.assertIn("nope", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_uses_workdir_and_timeout_arguments(self) -> None:
        seen = {}

        class Completed:
            returncode = 0
            stdout = "ok\n"
            stderr = ""

        def fake_runner(command, **kwargs):
            seen["command"] = command
            seen["cwd"] = kwargs["cwd"]
            seen["timeout"] = kwargs["timeout"]
            return Completed()

        def opener(_request):
            return FakeToolCallWithWorkdirTimeoutResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner, timeout=30.0)

        self.assertEqual(seen["command"], "pwd")
        self.assertEqual(seen["cwd"], "C:\\work\\project\\subdir")
        self.assertEqual(seen["timeout"], 2.5)
        self.assertIn("ok", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_truncates_output(self) -> None:
        class Completed:
            returncode = 0
            stdout = "abcdefghijklmnopqrstuvwxyz"
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=fake_runner,
            output_max_chars=20,
        )

        self.assertIn("Total output lines: 4", outputs[0]["output"])
        self.assertIn("chars truncated", outputs[0]["output"])
        self.assertTrue(outputs[0]["output"].startswith("Total output lines: 4\n\n"))

    async def test_local_http_exec_shell_tool_uses_default_output_token_limit(self) -> None:
        class Completed:
            returncode = 0
            stdout = "x" * (_approx_bytes_for_tokens(DEFAULT_LOCAL_HTTP_MAX_OUTPUT_TOKENS) + 200)
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=fake_runner,
        )

        self.assertIn("Total output lines:", outputs[0]["output"])
        self.assertIn("chars truncated", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_passes_login_argument_to_runner(self) -> None:
        seen = {}

        class Completed:
            returncode = 0
            stdout = "ok\n"
            stderr = ""

        def fake_runner(command, **kwargs):
            seen["command"] = command
            seen["login"] = kwargs["login"]
            return Completed()

        def opener(_request):
            return FakeToolCallWithLoginResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner)

        self.assertEqual(seen["command"], "pwd")
        self.assertTrue(seen["login"])
        self.assertIn("ok", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_output_requires_approval_before_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when approval is required")

        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertFalse(local_http_shell_tool_auto_execute_allowed(config))
        self.assertIs(outputs[0]["success"], False)
        self.assertEqual(outputs[0]["type"], "function_call_output")
        self.assertEqual(outputs[0]["call_id"], "call-1")
        self.assertIn("exit_code: approval_required", outputs[0]["output"])
        self.assertIn("approval_policy: on-request", outputs[0]["output"])
        self.assertIn("pwd", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_approval_output_preserves_metadata(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when approval is required")

        def opener(_request):
            return FakeToolCallWithApprovalMetadataResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertIn("sandbox_permissions: with_additional_permissions", outputs[0]["output"])
        self.assertIn('additional_permissions: {"network":{"enabled":true}}', outputs[0]["output"])
        self.assertNotIn('"file_system"', outputs[0]["output"])
        self.assertIn("justification: Need to inspect the workspace", outputs[0]["output"])
        self.assertIn("command:\npwd", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_rejects_additional_permissions_before_auto_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called for local additional permission requests")

        def opener(_request):
            return FakeToolCallWithApprovalMetadataResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertFalse(outputs[0]["success"])
        self.assertIn("permission_request_unsupported", outputs[0]["output"])
        self.assertIn("additional permissions are disabled", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_rejects_require_escalated_before_auto_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called for require_escalated requests")

        def opener(_request):
            return FakeToolCallWithRequireEscalatedResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertFalse(outputs[0]["success"])
        self.assertIn("permission_request_rejected", outputs[0]["output"])
        self.assertIn("you cannot ask for escalated permissions", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_rejects_unknown_sandbox_permissions_before_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called for unknown sandbox permissions")

        def opener(_request):
            return FakeToolCallWithInvalidSandboxPermissionsResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertFalse(outputs[0]["success"])
        self.assertIn("permission_request_invalid", outputs[0]["output"])
        self.assertIn("invalid sandbox_permissions `full-power`", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_rejects_invalid_additional_permission_shapes_before_auto_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called for invalid additional permission requests")

        async def run_with(opener):
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path("C:/work/project"),
                approval_policy=AskForApproval.NEVER,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("hello"),)),
                "hello",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )
            return shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        missing_profile = await run_with(lambda _request: FakeToolCallWithMissingAdditionalPermissionsResponse())
        self.assertFalse(missing_profile[0]["success"])
        self.assertIn("permission_request_invalid", missing_profile[0]["output"])
        self.assertIn("missing `additional_permissions`", missing_profile[0]["output"])

        bare_profile = await run_with(lambda _request: FakeToolCallWithBareAdditionalPermissionsResponse())
        self.assertFalse(bare_profile[0]["success"])
        self.assertIn("permission_request_invalid", bare_profile[0]["output"])
        self.assertIn("requires `sandbox_permissions` set to `with_additional_permissions`", bare_profile[0]["output"])

        empty_profile = await run_with(lambda _request: FakeToolCallWithEmptyAdditionalPermissionsResponse())
        self.assertFalse(empty_profile[0]["success"])
        self.assertIn("permission_request_invalid", empty_profile[0]["output"])
        self.assertIn("must include at least one requested permission", empty_profile[0]["output"])

    async def test_local_http_exec_shell_tool_approval_output_preserves_prefix_rule(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when approval is required")

        def opener(_request):
            return FakeToolCallWithPrefixRuleResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertIn('prefix_rule: ["python","-m"]', outputs[0]["output"])
        self.assertIn("command:\npython -m pytest", outputs[0]["output"])

    async def test_local_http_exec_apply_patch_tool_output_helper_applies_patch(self) -> None:
        def opener(_request):
            return FakeApplyPatchToolCallResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("create file"),)),
                "create file",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

            self.assertEqual(outputs[0]["type"], "custom_tool_call_output")
            self.assertEqual(outputs[0]["call_id"], "patch-1")
            self.assertEqual(outputs[0]["name"], "apply_patch")
            self.assertIs(outputs[0]["success"], True)
            self.assertIn("apply_patch succeeded", outputs[0]["output"])
            self.assertEqual((Path(tmpdir) / "created.txt").read_text(encoding="utf-8"), "hello\n")
            tool_response_items = response_items_from_local_http_tool_outputs(outputs)
            self.assertEqual(tool_response_items[0].type, "custom_tool_call_output")
            self.assertEqual(tool_response_items[0].name, "apply_patch")

    async def test_local_http_exec_apply_patch_updates_deletes_and_moves_files(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: old.txt\n"
            "@@\n"
            "-old\n"
            "+new\n"
            "*** Delete File: delete.txt\n"
            "*** Update File: move.txt\n"
            "*** Move to: moved.txt\n"
            "@@\n"
            "-move\n"
            "+moved\n"
            "*** End Patch\n"
        )

        def opener(_request):
            return FakeApplyPatchToolCallResponse(patch)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "old.txt").write_text("old\n", encoding="utf-8")
            (root / "delete.txt").write_text("delete me\n", encoding="utf-8")
            (root / "move.txt").write_text("move\n", encoding="utf-8")
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("patch files"),)),
                "patch files",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

            self.assertIs(outputs[0]["success"], True)
            self.assertEqual((root / "old.txt").read_text(encoding="utf-8"), "new\n")
            self.assertFalse((root / "delete.txt").exists())
            self.assertFalse((root / "move.txt").exists())
            self.assertEqual((root / "moved.txt").read_text(encoding="utf-8"), "moved\n")

    async def test_local_http_exec_apply_patch_requires_approval_before_write(self) -> None:
        def opener(_request):
            return FakeApplyPatchToolCallResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
                approval_policy=AskForApproval.ON_REQUEST,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("create file"),)),
                "create file",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

            self.assertEqual(outputs[0]["name"], "apply_patch")
            self.assertIs(outputs[0]["success"], False)
            self.assertIn("approval_required", outputs[0]["output"])
            self.assertFalse((Path(tmpdir) / "created.txt").exists())

    async def test_local_http_exec_tool_output_followup_request(self) -> None:
        request_bodies = []

        class Completed:
            returncode = 0
            stdout = "C:/work/project\n"
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

        def first_opener(_request):
            return FakeToolCallResponse()

        def followup_opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        previous = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=first_opener,
            built_tools=lambda _sess, _turn: Router(),
        )
        tool_outputs = shell_tool_outputs_from_local_http_exec_result(
            previous,
            config,
            runner=fake_runner,
            timeout=5.0,
        )

        tool_response_items = response_items_from_local_http_tool_outputs(tool_outputs)
        self.assertEqual(tool_response_items[0].type, "function_call_output")
        self.assertIs(tool_response_items[0].output.success, True)

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        followup = await run_exec_tool_output_http_sampling(
            config,
            previous,
            tool_outputs,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=followup_opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(final_text_from_response_items(followup.response_items), "done")
        input_items = request_bodies[0]["input"]
        self.assertTrue(any(item["type"] == "function_call" for item in input_items))
        output_items = [item for item in input_items if item["type"] == "function_call_output"]
        self.assertEqual(output_items[0]["call_id"], "call-1")
        self.assertIs(output_items[0]["success"], True)
        self.assertIn("exit_code: 0", output_items[0]["output"])

    async def test_local_http_exec_shell_tool_loop_returns_followup_answer(self) -> None:
        request_bodies = []

        class Completed:
            returncode = 0
            stdout = "C:/work/project\n"
            stderr = ""

        def fake_runner(command, **kwargs):
            self.assertEqual(command, "pwd")
            self.assertEqual(kwargs["cwd"], "C:\\work\\project")
            return Completed()

        responses = [FakeToolCallResponse(), FakeResponse()]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )

        result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
            runner=fake_runner,
            tool_timeout=5.0,
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 2)
        self.assertTrue(any(tool["name"] == "exec_command" for tool in request_bodies[0]["tools"]))
        self.assertTrue(any(tool["name"] == "apply_patch" for tool in request_bodies[0]["tools"]))
        self.assertTrue(any(tool["name"] == "exec_command" for tool in request_bodies[1]["tools"]))
        self.assertTrue(any(tool["name"] == "apply_patch" for tool in request_bodies[1]["tools"]))
        self.assertTrue(any(item["type"] == "function_call" for item in request_bodies[1]["input"]))
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(output_items[0]["call_id"], "call-1")
        self.assertIs(output_items[0]["success"], True)
        self.assertIn("C:/work/project", output_items[0]["output"])
        processor = JsonEventProcessor()
        emitted_tool_calls = tool_call_items_from_local_http_exec_result(result, processor)
        emitted_tool_outputs = tool_output_items_from_local_http_exec_result(result, processor)
        self.assertIn(emitted_tool_calls[0].payload["tool"], {"exec_command", "shell"})
        self.assertEqual(emitted_tool_outputs[0].payload["status"], "completed")
        self.assertIn("C:/work/project", emitted_tool_outputs[0].payload["result"])

    async def test_local_http_exec_command_tool_call_uses_cmd_argument(self) -> None:
        class Completed:
            returncode = 0
            stdout = "C:/work/project with a deliberately long suffix\n"
            stderr = ""

        seen = {}

        def fake_runner(command, **kwargs):
            seen["command"] = command
            seen["cwd"] = kwargs["cwd"]
            return Completed()

        def opener(_request):
            return FakeExecCommandToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=fake_runner,
            timeout=5.0,
        )

        self.assertEqual(seen["command"], "pwd")
        self.assertEqual(seen["cwd"], "C:\\work\\project")
        self.assertEqual(outputs[0]["call_id"], "call-1")
        self.assertIs(outputs[0]["success"], True)

    async def test_local_http_exec_shell_tool_accepts_cwd_alias(self) -> None:
        seen = {}

        class CwdAliasResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "shell",
                                "arguments": "{\"command\":\"pwd\",\"cwd\":\"subdir\"}",
                                "call_id": "call-1",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        class Completed:
            returncode = 0
            stdout = "C:/work/project/subdir\n"
            stderr = ""

        def fake_runner(_command, **kwargs):
            seen["cwd"] = kwargs["cwd"]
            return Completed()

        def opener(_request):
            return CwdAliasResponse()

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("pwd"),)), "pwd")
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner)

        self.assertEqual(seen["cwd"], "C:\\work\\project\\subdir")
        self.assertIs(outputs[0]["success"], True)

    async def test_local_http_exec_command_tool_call_passes_shell_argument(self) -> None:
        class Completed:
            returncode = 0
            stdout = "ok\n"
            stderr = ""

        seen = {}

        def fake_runner(_command, **kwargs):
            seen["executable"] = kwargs.get("executable")
            return Completed()

        def opener(_request):
            return FakeExecCommandToolCallResponse(shell="custom-shell")

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=fake_runner,
            timeout=5.0,
        )

        self.assertEqual(seen["executable"], "custom-shell")
        self.assertIs(outputs[0]["success"], True)

    async def test_local_http_write_stdin_tool_call_reports_unavailable_session_runtime(self) -> None:
        def opener(_request):
            return FakeWriteStdinToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("continue process"),)),
            "continue process",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertEqual(outputs[0]["type"], "function_call_output")
        self.assertEqual(outputs[0]["call_id"], "stdin-1")
        self.assertEqual(outputs[0]["name"], "write_stdin")
        self.assertIs(outputs[0]["success"], False)
        self.assertEqual(outputs[0]["output"], "write_stdin failed: Unknown process id 7")
        self.assertNotIn("structured_output", outputs[0])

    async def test_local_http_write_stdin_uses_default_yield_time(self) -> None:
        class FakeSessionManager:
            def __init__(self) -> None:
                self.yield_time = None

            def write(self, session_id, chars, *, yield_time=None, output_max_chars=None):
                self.yield_time = yield_time
                return {
                    "wall_time_seconds": 0.0,
                    "exit_code": 0,
                    "original_token_count": 0,
                    "output": "",
                }, True

        manager = FakeSessionManager()

        def opener(_request):
            return FakeWriteStdinToolCallResponse(yield_time_ms=None)

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("continue process"),)),
            "continue process",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, session_manager=manager)

        self.assertEqual(outputs[0]["name"], "write_stdin")
        self.assertIs(outputs[0]["success"], True)
        self.assertEqual(manager.yield_time, 0.25)

    async def test_local_http_write_stdin_clamps_yield_time(self) -> None:
        class FakeSessionManager:
            def __init__(self) -> None:
                self.yield_time = None

            def write(self, session_id, chars, *, yield_time=None, output_max_chars=None):
                self.yield_time = yield_time
                return {
                    "wall_time_seconds": 0.0,
                    "exit_code": 0,
                    "original_token_count": 0,
                    "output": "",
                }, True

        async def run_with(chars: str, yield_time_ms: int) -> float:
            manager = FakeSessionManager()

            def opener(_request):
                return FakeWriteStdinToolCallResponse(chars=chars, yield_time_ms=yield_time_ms)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path("C:/work/project"),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("continue process"),)),
                "continue process",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )
            outputs = shell_tool_outputs_from_local_http_exec_result(result, config, session_manager=manager)
            self.assertIs(outputs[0]["success"], True)
            return manager.yield_time

        self.assertEqual(await run_with("hello\n", 0), LOCAL_HTTP_EXEC_MIN_YIELD_TIME_MS / 1000.0)
        self.assertEqual(await run_with("hello\n", 120_000), LOCAL_HTTP_EXEC_MAX_YIELD_TIME_MS / 1000.0)
        self.assertEqual(await run_with("", 1_200), LOCAL_HTTP_EXEC_MIN_EMPTY_STDIN_YIELD_TIME_MS / 1000.0)
        self.assertEqual(
            await run_with("", 600_000),
            LOCAL_HTTP_EXEC_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS / 1000.0,
        )

    async def test_local_http_write_stdin_passes_max_output_tokens(self) -> None:
        class FakeSessionManager:
            def __init__(self) -> None:
                self.output_max_chars = None

            def write(self, session_id, chars, *, yield_time=None, output_max_chars=None):
                self.output_max_chars = output_max_chars
                return {
                    "wall_time_seconds": 0.0,
                    "exit_code": 0,
                    "original_token_count": 0,
                    "output": "",
                }, True

        manager = FakeSessionManager()

        def opener(_request):
            return FakeWriteStdinToolCallResponse(max_output_tokens=4)

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("continue process"),)),
            "continue process",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            session_manager=manager,
            output_max_chars=1000,
        )

        self.assertIs(outputs[0]["success"], True)
        self.assertEqual(manager.output_max_chars, 16)

    async def test_local_http_exec_command_session_accepts_write_stdin(self) -> None:
        manager = LocalHttpExecSessionManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "session_child.py"
            script.write_text(
                "import sys\n"
                "print('ready')\n"
                "line = sys.stdin.readline()\n"
                "print('got:' + line.strip())\n",
                encoding="utf-8",
            )
            command = f"\"{sys.executable}\" -u \"{script}\""

            def exec_opener(_request):
                return FakeSessionExecCommandToolCallResponse(command)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("start session"),)),
                "start session",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=exec_opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                session_manager=manager,
            )
            session_match = re.search(r"Process running with session ID (\d+)", outputs[0]["output"])
            self.assertIsNotNone(session_match)
            self.assertIn("ready", outputs[0]["output"])
            self.assertEqual(outputs[0]["structured_output"]["session_id"], int(session_match.group(1)))
            self.assertIn("ready", outputs[0]["structured_output"]["output"])
            self.assertRegex(outputs[0]["structured_output"]["chunk_id"], r"^[0-9a-f]{6}$")
            self.assertNotIn("timed_out", outputs[0]["structured_output"])
            self.assertNotIn("tty_requested", outputs[0]["structured_output"])

            session_id = int(session_match.group(1))

            def stdin_opener(_request):
                return FakeWriteStdinToolCallResponse(session_id=session_id, chars="hello\n")

            stdin_result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=stdin_opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            stdin_outputs = shell_tool_outputs_from_local_http_exec_result(
                stdin_result,
                config,
                session_manager=manager,
            )

            self.assertIs(stdin_outputs[0]["success"], True)
            self.assertIn("got:hello", stdin_outputs[0]["output"])
            self.assertEqual(stdin_outputs[0]["structured_output"]["exit_code"], 0)
            self.assertIn("got:hello", stdin_outputs[0]["structured_output"]["output"])
            self.assertRegex(stdin_outputs[0]["structured_output"]["chunk_id"], r"^[0-9a-f]{6}$")
            self.assertNotEqual(
                stdin_outputs[0]["structured_output"]["chunk_id"],
                outputs[0]["structured_output"]["chunk_id"],
            )

    async def test_local_http_write_stdin_empty_chars_polls_session_output(self) -> None:
        manager = LocalHttpExecSessionManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "poll_child.py"
            script.write_text(
                "import time\n"
                "print('first', flush=True)\n"
                "time.sleep(1.0)\n"
                "print('second', flush=True)\n",
                encoding="utf-8",
            )
            command = f"\"{sys.executable}\" -u \"{script}\""

            def exec_opener(_request):
                return FakeSessionExecCommandToolCallResponse(command, yield_time_ms=500)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("start poll session"),)),
                "start poll session",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=exec_opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                session_manager=manager,
            )
            session_id = outputs[0]["structured_output"]["session_id"]
            self.assertRegex(outputs[0]["structured_output"]["chunk_id"], r"^[0-9a-f]{6}$")
            first_chunk_id = outputs[0]["structured_output"]["chunk_id"]

            def poll_opener(_request):
                return FakeWriteStdinToolCallResponse(session_id=session_id, chars="", yield_time_ms=1200)

            poll_result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=poll_opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            poll_outputs = shell_tool_outputs_from_local_http_exec_result(
                poll_result,
                config,
                session_manager=manager,
            )

            self.assertIs(poll_outputs[0]["success"], True)
            self.assertIn("second", poll_outputs[0]["structured_output"]["output"])
            self.assertRegex(poll_outputs[0]["structured_output"]["chunk_id"], r"^[0-9a-f]{6}$")
            self.assertNotEqual(poll_outputs[0]["structured_output"]["chunk_id"], first_chunk_id)
            self.assertNotIn("session_id", poll_outputs[0]["structured_output"])

    async def test_local_http_exec_command_session_uses_shell_argument(self) -> None:
        class FakeStdout:
            def readline(self):
                return ""

            def close(self):
                return None

        class FakeStdin:
            def close(self):
                return None

        class FakeProcess:
            pid = 12345
            stdin = FakeStdin()
            stdout = FakeStdout()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        seen = {}
        manager = LocalHttpExecSessionManager()

        def exec_opener(_request):
            return FakeSessionExecCommandToolCallResponse("echo hi", yield_time_ms=0, shell="custom-shell")

        def fake_popen(*_args, **kwargs):
            seen["executable"] = kwargs.get("executable")
            seen["text"] = kwargs.get("text")
            seen["bufsize"] = kwargs.get("bufsize")
            return FakeProcess()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path.cwd(),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("start custom shell session"),)),
            "start custom shell session",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=exec_opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        with patch("pycodex.exec.local_runtime.subprocess.Popen", fake_popen):
            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                session_manager=manager,
            )

        self.assertEqual(seen["executable"], "custom-shell")
        self.assertIs(seen["text"], False)
        self.assertEqual(seen["bufsize"], 0)
        self.assertIs(outputs[0]["success"], True)

    async def test_local_http_exec_session_manager_prunes_oldest_session_at_limit(self) -> None:
        class FakeStdout:
            def readline(self):
                return ""

            def close(self):
                return None

        class FakeStdin:
            def close(self):
                return None

        class FakeProcess:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self.stdin = FakeStdin()
                self.stdout = FakeStdout()
                self.terminated = False

            def poll(self):
                return None

            def wait(self, timeout=None):
                return None

        processes = []
        manager = LocalHttpExecSessionManager(max_sessions=2)

        def fake_popen(*_args, **_kwargs):
            process = FakeProcess(10_000 + len(processes))
            processes.append(process)
            return process

        with patch("pycodex.exec.local_runtime.subprocess.Popen", fake_popen), patch(
            "pycodex.exec.local_runtime._terminate_process_tree",
            lambda process: setattr(process, "terminated", True),
        ):
            manager.start("first", cwd=Path.cwd(), yield_time=0)
            manager.start("second", cwd=Path.cwd(), yield_time=0)
            manager.start("third", cwd=Path.cwd(), yield_time=0)

        self.assertEqual(LOCAL_HTTP_MAX_UNIFIED_EXEC_PROCESSES, 64)
        self.assertEqual(len(manager._sessions), 2)
        self.assertTrue(processes[0].terminated)
        self.assertFalse(processes[1].terminated)
        self.assertFalse(processes[2].terminated)

    def test_local_http_exec_session_manager_prunes_exited_session_before_running_oldest(self) -> None:
        class FakeProcess:
            def __init__(self, *, exited: bool) -> None:
                self.exited = exited
                self.terminated = False

            def poll(self):
                return 0 if self.exited else None

        class FakeSession:
            def __init__(self, *, exited: bool) -> None:
                self.process = FakeProcess(exited=exited)
                self.closed = False

            def close(self) -> None:
                self.closed = True

        manager = LocalHttpExecSessionManager(max_sessions=10)
        sessions = {
            session_id: FakeSession(exited=(session_id == 2))
            for session_id in range(1, 11)
        }
        running_oldest = sessions[1]
        exited_newer = sessions[2]
        running_newest = sessions[10]
        manager._sessions = dict(sessions)
        manager._session_last_used = {
            session_id: float(session_id)
            for session_id in sessions
        }

        with patch(
            "pycodex.exec.local_runtime._terminate_process_tree",
            lambda process: setattr(process, "terminated", True),
        ):
            manager._prune_sessions_if_needed()

        self.assertIn(1, manager._sessions)
        self.assertNotIn(2, manager._sessions)
        self.assertIn(10, manager._sessions)
        self.assertFalse(running_oldest.process.terminated)
        self.assertFalse(running_newest.process.terminated)
        self.assertTrue(exited_newer.closed)

    async def test_local_http_exec_command_session_preserves_tty_request(self) -> None:
        class FakeStdout:
            def readline(self):
                return ""

            def close(self):
                return None

        class FakeStdin:
            def close(self):
                return None

        class FakeProcess:
            pid = 12345
            stdin = FakeStdin()
            stdout = FakeStdout()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        manager = LocalHttpExecSessionManager()

        def exec_opener(_request):
            return FakeSessionExecCommandToolCallResponse("echo hi", yield_time_ms=None, tty=True)

        def fake_popen(*_args, **_kwargs):
            return FakeProcess()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path.cwd(),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("start tty session"),)),
            "start tty session",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=exec_opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        with patch("pycodex.exec.local_runtime.subprocess.Popen", fake_popen):
            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                session_manager=manager,
            )

        self.assertIs(outputs[0]["success"], True)
        self.assertNotIn("tty_requested", outputs[0]["structured_output"])
        self.assertIs(outputs[0]["internal_output"]["tty_requested"], True)
        self.assertNotIn("tty_requested: true", outputs[0]["output"])

    async def test_local_http_exec_command_uses_default_yield_time(self) -> None:
        class FakeSessionManager:
            def __init__(self) -> None:
                self.yield_time = None

            def start(
                self,
                command,
                *,
                cwd,
                shell=None,
                tty_requested=False,
                yield_time=None,
                timeout=None,
                output_max_chars=None,
            ):
                self.yield_time = yield_time
                return {
                    "wall_time_seconds": 0.0,
                    "exit_code": 0,
                    "original_token_count": 0,
                    "output": "",
                }, True

        manager = FakeSessionManager()

        def exec_opener(_request):
            return FakeSessionExecCommandToolCallResponse("echo hi", yield_time_ms=None)

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path.cwd(),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("start default yield session"),)),
            "start default yield session",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=exec_opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, session_manager=manager)

        self.assertIs(outputs[0]["success"], True)
        self.assertEqual(manager.yield_time, 10.0)

    async def test_local_http_exec_command_clamps_yield_time(self) -> None:
        class FakeSessionManager:
            def __init__(self) -> None:
                self.yield_time = None

            def start(
                self,
                command,
                *,
                cwd,
                shell=None,
                tty_requested=False,
                yield_time=None,
                timeout=None,
                output_max_chars=None,
            ):
                self.yield_time = yield_time
                return {
                    "wall_time_seconds": 0.0,
                    "exit_code": 0,
                    "original_token_count": 0,
                    "output": "",
                }, True

        async def run_with(yield_time_ms: int) -> float:
            manager = FakeSessionManager()

            def exec_opener(_request):
                return FakeSessionExecCommandToolCallResponse("echo hi", yield_time_ms=yield_time_ms)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path.cwd(),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("start clamped yield session"),)),
                "start clamped yield session",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=exec_opener,
                built_tools=lambda _sess, _turn: Router(),
            )
            outputs = shell_tool_outputs_from_local_http_exec_result(result, config, session_manager=manager)
            self.assertIs(outputs[0]["success"], True)
            return manager.yield_time

        self.assertEqual(await run_with(0), LOCAL_HTTP_EXEC_MIN_YIELD_TIME_MS / 1000.0)
        self.assertEqual(await run_with(120_000), LOCAL_HTTP_EXEC_MAX_YIELD_TIME_MS / 1000.0)

    def test_local_http_exec_output_text_renders_structured_payload(self) -> None:
        text = local_http_exec_output_text(
            {
                "wall_time_seconds": 0.25,
                "chunk_id": "12:3",
                "exit_code": 0,
                "tty_requested": True,
                "session_id": 12,
                "original_token_count": 3,
                "output": "done",
            }
        )

        self.assertIn("Wall time: 0.2500 seconds", text)
        self.assertIn("Chunk ID: 12:3", text)
        self.assertIn("Process exited with code 0", text)
        self.assertNotIn("tty_requested: true", text)
        self.assertIn("Process running with session ID 12", text)
        self.assertIn("Original token count: 3", text)
        self.assertIn("Output:", text)
        self.assertTrue(text.endswith("done"))

    async def test_local_http_exec_command_session_timeout_cleans_up_session(self) -> None:
        manager = LocalHttpExecSessionManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "sleep_child.py"
            script.write_text(
                "import time\n"
                "print('started', flush=True)\n"
                "time.sleep(5)\n",
                encoding="utf-8",
            )
            command = f"\"{sys.executable}\" -u \"{script}\""

            def exec_opener(_request):
                return FakeSessionExecCommandToolCallResponse(command, yield_time_ms=250, timeout_ms=100)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("start timeout session"),)),
                "start timeout session",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=exec_opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                session_manager=manager,
            )

            self.assertIs(outputs[0]["success"], False)
            self.assertEqual(outputs[0]["structured_output"]["exit_code"], LOCAL_HTTP_EXEC_TIMEOUT_EXIT_CODE)
            self.assertNotIn("timed_out", outputs[0]["structured_output"])
            self.assertIs(outputs[0]["internal_output"]["timed_out"], True)
            self.assertRegex(outputs[0]["structured_output"]["chunk_id"], r"^[0-9a-f]{6}$")
            self.assertNotIn("session_id", outputs[0]["structured_output"])
            self.assertIn(f"Process exited with code {LOCAL_HTTP_EXEC_TIMEOUT_EXIT_CODE}", outputs[0]["output"])
            self.assertNotIn("timed_out: true", outputs[0]["output"])

    def test_local_http_exec_schema_output_payload_removes_internal_fields(self) -> None:
        payload = local_http_exec_schema_output_payload(
            {
                "chunk_id": "abc123",
                "wall_time_seconds": 0.1,
                "exit_code": 124,
                "original_token_count": 4,
                "output": "done",
                "timed_out": True,
                "tty_requested": True,
            }
        )

        self.assertEqual(
            payload,
            {
                "chunk_id": "abc123",
                "wall_time_seconds": 0.1,
                "exit_code": 124,
                "original_token_count": 4,
                "output": "done",
            },
        )

    async def test_local_http_exec_result_maps_function_call_output_json_event_without_execution(self) -> None:
        def opener(_request):
            return FakeToolOutputResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        env = {
            "PYCODEX_EXEC_LOCAL_HTTP": "1",
            "OPENAI_API_KEY": "sk-env",
            "OPENAI_BASE_URL": "https://api.example.test/v1",
        }

        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env=env,
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        processor = JsonEventProcessor()
        output_items = tool_output_items_from_local_http_exec_result(result, processor)
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0].type, "mcp_tool_call")
        self.assertEqual(output_items[0].payload["server"], "responses")
        self.assertEqual(output_items[0].payload["tool"], "shell")
        self.assertEqual(output_items[0].payload["result"], "C:/work/project")
        self.assertEqual(output_items[0].payload["status"], "completed")

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(
            [line["type"] for line in json_lines],
            ["turn.started", "item.completed", "item.completed", "turn.completed"],
        )
        self.assertEqual(json_lines[1]["item"]["type"], "mcp_tool_call")
        self.assertEqual(json_lines[1]["item"]["result"], "C:/work/project")
        self.assertEqual(json_lines[1]["item"]["status"], "completed")
        self.assertEqual(json_lines[2]["item"]["type"], "agent_message")

    async def test_default_local_http_runtime_reports_http_error_body(self) -> None:
        def opener(_request):
            raise HTTPError(
                "https://api.example.test/v1/responses",
                400,
                "Bad Request",
                {},
                io.BytesIO(b'{"error":{"message":"bad schema"}}'),
            )

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),)),
            "hello",
        )
        env = {
            "PYCODEX_EXEC_LOCAL_HTTP": "1",
            "OPENAI_API_KEY": "sk-env",
            "OPENAI_BASE_URL": "https://api.example.test/v1",
        }

        with self.assertRaisesRegex(RuntimeError, "HTTP 400: bad schema"):
            await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env=env,
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

    def test_default_local_http_runtime_requires_api_key(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )

        with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY or CODEX_API_KEY is required"):
            build_default_local_http_exec_runtime(config, env={"PYCODEX_EXEC_LOCAL_HTTP": "1"})

    def test_default_local_http_auth_prefers_env_key(self) -> None:
        auth = type("Auth", (), {"openai_api_key": "sk-auth-json"})()

        resolved = default_local_http_exec_auth(auth=auth, env={"OPENAI_API_KEY": "sk-env"})

        self.assertEqual(resolved, "sk-env")

    def test_default_local_http_auth_uses_codex_api_key_env_var(self) -> None:
        resolved = default_local_http_exec_auth(env={"CODEX_API_KEY": "sk-codex"})

        self.assertEqual(resolved, "sk-codex")

    def test_default_local_http_auth_prefers_openai_env_over_codex_env_key(self) -> None:
        resolved = default_local_http_exec_auth(env={"OPENAI_API_KEY": "sk-openai", "CODEX_API_KEY": "sk-codex"})

        self.assertEqual(resolved, "sk-openai")

    def test_default_local_http_auth_uses_config_provider_env_key(self) -> None:
        resolved = default_local_http_exec_auth(
            env={"LOCAL_OPENAI_KEY": "sk-local"},
            config_toml={"model_providers": {"local-openai": {"env_key": "LOCAL_OPENAI_KEY"}}},
            provider_id="local-openai",
        )

        self.assertEqual(resolved, "sk-local")

    def test_default_local_http_auth_prefers_openai_env_over_provider_env_key(self) -> None:
        resolved = default_local_http_exec_auth(
            env={"OPENAI_API_KEY": "sk-openai", "LOCAL_OPENAI_KEY": "sk-local"},
            config_toml={"model_providers": {"local-openai": {"env_key": "LOCAL_OPENAI_KEY"}}},
            provider_id="local-openai",
        )

        self.assertEqual(resolved, "sk-openai")

    def test_default_local_http_model_precedence(self) -> None:
        config_model = ExecSessionConfig(
            model="gpt-config",
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        config_default = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )

        self.assertEqual(
            default_local_http_exec_model(
                config_model,
                env={"PYCODEX_EXEC_MODEL": "gpt-pycodex", "OPENAI_MODEL": "gpt-openai"},
            ),
            "gpt-config",
        )
        self.assertEqual(
            default_local_http_exec_model(
                config_default,
                env={"PYCODEX_EXEC_MODEL": "gpt-pycodex", "OPENAI_MODEL": "gpt-openai"},
            ),
            "gpt-pycodex",
        )
        self.assertEqual(
            default_local_http_exec_model(config_default, env={"OPENAI_MODEL": "gpt-openai"}),
            "gpt-openai",
        )
        self.assertEqual(
            default_local_http_exec_model(config_default, env={}, config_toml={"model": "gpt-config"}),
            "gpt-config",
        )
        self.assertEqual(default_local_http_exec_model(config_default, env={}), "gpt-5")

    def test_local_http_exec_max_tool_rounds_env(self) -> None:
        self.assertEqual(local_http_exec_max_tool_rounds(env={}), 1)
        self.assertEqual(local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "3"}), 3)
        self.assertEqual(local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "0"}), 0)
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "-1"})
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "many"})

    def test_local_http_exec_tool_output_max_chars_env(self) -> None:
        self.assertIsNone(local_http_exec_tool_output_max_chars(env={}))
        self.assertEqual(local_http_exec_tool_output_max_chars(env={"PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS": "12"}), 12)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            local_http_exec_tool_output_max_chars(env={"PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS": "0"})
        with self.assertRaisesRegex(ValueError, "positive integer"):
            local_http_exec_tool_output_max_chars(env={"PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS": "many"})

    def test_default_local_http_base_url_precedence(self) -> None:
        self.assertEqual(
            default_local_http_exec_base_url(env={"OPENAI_BASE_URL": "https://api.example.test/v1"}),
            "https://api.example.test/v1",
        )
        self.assertEqual(
            default_local_http_exec_base_url(
                env={},
                config_toml={"model_providers": {"local-openai": {"base_url": "https://local.example.test/v1"}}},
                provider_id="local-openai",
            ),
            "https://local.example.test/v1",
        )
        self.assertEqual(default_local_http_exec_base_url(env={}), "https://api.openai.com/v1")

    def test_default_local_http_runtime_uses_config_provider_env_key(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id="local-openai",
            cwd=Path("C:/work/project"),
        )

        _client, provider, _model_info, resolved_auth = build_default_local_http_exec_runtime(
            config,
            env={"LOCAL_OPENAI_KEY": "sk-local"},
            config_toml={
                "model_providers": {
                    "local-openai": {
                        "base_url": "https://local.example.test/v1",
                        "env_key": "LOCAL_OPENAI_KEY",
                    }
                }
            },
        )

        self.assertEqual(resolved_auth, "sk-local")
        self.assertEqual(provider.auth, "sk-local")
        self.assertEqual(provider.base_url, "https://local.example.test/v1")

    def test_local_http_exec_config_summary_uses_model_provider_and_cwd(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        env = {"OPENAI_MODEL": "gpt-env"}

        model = default_local_http_exec_model(config, env=env)
        summary_config, summary_session = local_http_exec_config_summary(
            config,
            model=model,
            session_id="session-1",
            thread_id="thread-1",
        )

        self.assertEqual(summary_config["cwd"], "C:\\work\\project")
        self.assertEqual(summary_session["session_id"], "session-1")
        self.assertEqual(summary_session["thread_id"], "thread-1")
        self.assertEqual(summary_session["model"], "gpt-env")
        self.assertEqual(summary_session["model_provider_id"], "openai")

        stderr = io.StringIO()
        HumanEventProcessor().print_config_summary(
            summary_config,
            "hello",
            summary_session,
            stderr=stderr,
            version="test-version",
        )
        summary_text = stderr.getvalue()
        self.assertIn("OpenAI Codex vtest-version", summary_text)
        self.assertIn("workdir: C:\\work\\project", summary_text)
        self.assertIn("model: gpt-env", summary_text)
        self.assertIn("provider: openai", summary_text)

    def test_default_local_http_runtime_ids_can_feed_config_summary(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        env = {
            "OPENAI_API_KEY": "sk-env",
            "CODEX_INSTALLATION_ID": "install-1",
        }

        client, _provider, model_info, _auth = build_default_local_http_exec_runtime(config, env=env)
        summary_config, summary_session = local_http_exec_config_summary(
            config,
            model=model_info.slug,
            session_id=str(client.state.session_id),
            thread_id=str(client.state.thread_id),
        )

        self.assertEqual(summary_session["session_id"], str(client.state.session_id))
        self.assertEqual(summary_session["thread_id"], str(client.state.thread_id))
        self.assertEqual(summary_config["model"], model_info.slug)
        self.assertEqual(client.state.installation_id, "install-1")


if __name__ == "__main__":
    unittest.main()
