import json
import tempfile
import io
import os
import re
import shlex
import subprocess
import sys
import asyncio
import unittest
from collections.abc import Mapping
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from pathlib import Path

from pycodex.execpolicy import (
    ExecPolicyPrefixRule,
)
from pycodex.core import (
    ExecApprovalRequirement,
    SessionMeta,
    append_thread_name,
    count_session_rollout_files,
    find_session_rollout_containing_response_marker,
    last_user_image_count_in_rollout,
    materialize_session_rollout,
    read_event_msgs_from_rollout,
    read_response_items_from_rollout,
    read_thread_item_from_rollout,
)
from pycodex.core.client import ModelClient
from pycodex.core.client_common import REVIEW_PROMPT
from pycodex.core.shell import Shell, ShellType
from pycodex.core.session.turn.runtime import UserTurnSamplingResult
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
    final_text_from_local_http_exec_result,
    final_text_from_response_items,
    LocalHttpHeadTailBuffer,
    LocalHttpExecSessionManager,
    LocalHttpModelInfo,
    LocalHttpProvider,
    LocalHttpReviewModelInfo,
    LocalHttpShellInvocation,
    LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES,
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
    core_exec_config_summary,
    core_exec_enabled,
    core_exec_initial_messages_from_rollout,
    core_review_rollout_input_items,
    persist_core_exec_resume_rollout,
    persist_core_exec_rollout,
    local_core_exec_enabled,
    local_http_exec_enabled,
    local_http_exec_shell_tools_enabled,
    local_http_generate_chunk_id,
    local_http_retain_head_tail_output,
    local_http_exec_schema_output_payload,
    local_http_exec_output_text,
    local_http_apply_patch_approval_required_output,
    local_http_apply_patch_tool_spec,
    local_http_exec_config_summary,
    local_http_exec_max_tool_rounds,
    local_http_review_rollout_input_items,
    local_http_request_permissions_tool_spec,
    local_http_write_stdin_tool_spec,
    local_http_write_stdin_approval_required_output,
    local_http_write_stdin_unknown_session_output,
    local_http_model_allows_apply_patch_tool,
    local_http_model_allows_view_image_tool,
    local_http_model_can_request_original_image_detail,
    local_http_model_disabled_tool_names,
    local_http_model_supports_image_inputs,
    local_http_view_image_tool_spec,
    local_http_exec_initial_messages_from_rollout,
    local_http_shell_tool_auto_execute_allowed,
    local_http_shell_tool_approval_required_output,
    local_http_shell_tool_forbidden_output,
    local_http_shell_tool_spec,
    local_http_shell_tools_built_tools,
    local_http_exec_tool_output_max_chars,
    reasoning_texts_from_local_http_exec_result,
    persist_local_http_exec_rollout,
    persist_local_http_exec_resume_rollout,
    response_items_from_local_http_tool_outputs,
    resolve_local_http_exec_resume_rollout_path,
    run_exec_tool_output_http_sampling,
    run_exec_review_core_http_sampling,
    run_exec_resume_user_turn_core_http_sampling,
    run_exec_resume_user_turn_http_sampling,
    run_exec_review_http_sampling,
    run_exec_user_turn_core_sampling,
    run_exec_user_turn_default_local_http_sampling,
    run_exec_user_turn_http_sampling,
    run_exec_user_turn_with_shell_tools_http_sampling,
    shell_tool_outputs_from_local_http_exec_result,
    tool_call_items_from_local_http_exec_result,
    tool_output_items_from_local_http_exec_result,
    tool_timeline_items_from_local_http_exec_result,
    usage_from_local_http_exec_result,
    _merge_local_http_sampling_result,
    _local_http_prompt_visible_rollout_items,
    _local_http_response_rollout_payloads,
    _approx_bytes_for_tokens,
    _approx_token_count,
    _local_http_shell_tool_exec_policy_command,
    _shell_command_execution_argv,
    _truncate_shell_tool_output,
)
from pycodex.exec.run import ExecRunPlan, InitialOperation
from pycodex.exec.session import ExecSessionConfig
from pycodex.protocol import (
    AdditionalPermissionProfile,
    CodexErrorInfo,
    ContentItem,
    ErrorEvent,
    EventMsg,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemPath,
    FileSystemSandboxEntry,
    ModelRerouteEvent,
    ModelRerouteReason,
    ModelVerification,
    ModelVerificationEvent,
    NetworkPermissions,
    PermissionProfile,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsResponse,
    ResponseItem,
    StreamErrorEvent,
    TokenCountEvent,
    TokenUsage,
    TokenUsageInfo,
    WarningEvent,
)
from pycodex.protocol import AskForApproval, CodexErr, GranularApprovalConfig, ReviewRequest, ReviewTarget, UserInput


def shell_join_for_test(argv: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return " ".join(shlex.quote(part) for part in argv)


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


class FakePayloadResponse:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return []


def _message_texts(message_items: list[dict]) -> list[str]:
    return [item["content"][0]["text"] for item in message_items if item.get("content")]


def _assert_message_texts_in_order(testcase: unittest.TestCase, message_items: list[dict], expected: list[str]) -> None:
    texts = _message_texts(message_items)
    cursor = 0
    for text in expected:
        try:
            cursor = texts.index(text, cursor) + 1
        except ValueError:
            testcase.fail(f"missing message text sequence {expected!r} in {texts!r}")


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


class ExistingViewImageToolRouter:
    def model_visible_specs(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "name": "view_image",
                "description": "Existing image tool",
                "parameters": {"type": "object", "properties": {}},
            }
        ]


class ExistingReviewDisabledToolRouter:
    def model_visible_specs(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "name": "view_image",
                "description": "Existing image tool",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "get_goal",
                "description": "Existing goal tool",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "create_goal",
                "description": "Existing goal tool",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "update_goal",
                "description": "Existing goal tool",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "web_search",
                "description": "Existing web search tool",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "existing",
                "description": "Existing allowed tool",
                "parameters": {"type": "object", "properties": {}},
            },
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


class FakeRawExecCommandToolCallResponse:
    def __init__(self, arguments: object, call_id: str = "call-1") -> None:
        self.arguments = arguments
        self.call_id = call_id

    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": json.dumps(self.arguments),
                        "call_id": self.call_id,
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


class FakeRawWriteStdinToolCallResponse:
    def __init__(self, arguments: object, call_id: str = "stdin-1") -> None:
        self.arguments = arguments
        self.call_id = call_id

    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "write_stdin",
                        "arguments": json.dumps(self.arguments),
                        "call_id": self.call_id,
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeRequestPermissionsToolCallResponse:
    def __init__(self, arguments: str | Mapping[str, object] | None = None) -> None:
        self.arguments = (
            "{\"permissions\":{\"network\":{\"enabled\":true}}}"
            if arguments is None
            else json.dumps(arguments)
            if isinstance(arguments, Mapping)
            else arguments
        )

    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "request_permissions",
                        "arguments": self.arguments,
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


class FakeDangerousToolCallResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"rm -rf /important/data\",\"shell\":\"/bin/bash\"}",
                        "call_id": "call-1",
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


class FakeToolCallWithRelativeAdditionalPermissionsWorkdirResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": json.dumps(
                            {
                                "command": "pwd",
                                "workdir": "nested",
                                "sandbox_permissions": "with_additional_permissions",
                                "additional_permissions": {"file_system": {"write": ["."]}},
                            }
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


class FakeToolCallWithEmptyObjectAdditionalPermissionsResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\",\"sandbox_permissions\":\"with_additional_permissions\",\"additional_permissions\":{}}",
                        "call_id": "call-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeToolCallWithNullAdditionalPermissionsResponse:
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
                            "\"additional_permissions\":null}"
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


class FakeToolCallWithInvalidAdditionalPermissionsResponse:
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
                            "\"additional_permissions\":[]}"
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


class FakeToolCallWithHeredocPrefixRuleResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": json.dumps(
                            {
                                "command": "python3 <<'PY'\nprint('hello')\nPY",
                                "prefix_rule": ["python3", "script.py"],
                            },
                            separators=(",", ":"),
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
        self.assertNotIn("cwd", spec["parameters"]["properties"])
        self.assertIn("yield_time_ms", spec["parameters"]["properties"])
        self.assertIn("max_output_tokens", spec["parameters"]["properties"])
        self.assertNotIn("timeout", spec["parameters"]["properties"])
        self.assertNotIn("timeout_ms", spec["parameters"]["properties"])
        login = spec["parameters"]["properties"]["login"]
        self.assertIn("-l/-i semantics", login["description"])
        self.assertIn("Defaults to true", login["description"])
        sandbox_permissions = spec["parameters"]["properties"]["sandbox_permissions"]
        self.assertNotIn("additional_permissions", spec["parameters"]["properties"])
        self.assertNotIn("with_additional_permissions", sandbox_permissions["description"])
        self.assertIn("require_escalated", sandbox_permissions["description"])
        justification = spec["parameters"]["properties"]["justification"]
        self.assertIn("Only set if sandbox_permissions", justification["description"])
        self.assertIn("Do you want to", justification["description"])
        prefix_rule = spec["parameters"]["properties"]["prefix_rule"]
        self.assertIn("Only specify when sandbox_permissions", prefix_rule["description"])
        self.assertIn("git", prefix_rule["description"])
        self.assertIn("pull", prefix_rule["description"])
        self.assertEqual(spec["output_schema"]["required"], ["wall_time_seconds", "output"])
        output_schema = spec["output_schema"]
        self.assertFalse(output_schema["additionalProperties"])
        self.assertIn("chunk_id", output_schema["properties"])
        self.assertIn("exit_code", output_schema["properties"])
        self.assertIn("session_id", output_schema["properties"])
        self.assertIn("original_token_count", output_schema["properties"])
        self.assertIn("possibly truncated", output_schema["properties"]["output"]["description"])
        self.assertFalse(spec["parameters"]["additionalProperties"])

    def test_local_http_shell_tool_spec_includes_additional_permissions_when_enabled(self) -> None:
        spec = local_http_shell_tool_spec(exec_permission_approvals_enabled=True)

        sandbox_permissions = spec["parameters"]["properties"]["sandbox_permissions"]
        self.assertIn("with_additional_permissions", sandbox_permissions["description"])
        additional_permissions = spec["parameters"]["properties"]["additional_permissions"]
        self.assertFalse(additional_permissions["additionalProperties"])
        self.assertIn("network", additional_permissions["properties"])
        self.assertIn("file_system", additional_permissions["properties"])
        self.assertIn("enabled", additional_permissions["properties"]["network"]["properties"])
        file_system = additional_permissions["properties"]["file_system"]
        self.assertFalse(file_system["additionalProperties"])
        self.assertIn("read", file_system["properties"])
        self.assertIn("write", file_system["properties"])

    def test_local_http_shell_tool_spec_hides_login_and_additional_permissions_when_disabled(self) -> None:
        spec = local_http_shell_tool_spec(
            allow_login_shell=False,
            exec_permission_approvals_enabled=False,
        )

        properties = spec["parameters"]["properties"]
        self.assertNotIn("login", properties)
        self.assertNotIn("additional_permissions", properties)
        self.assertIn("sandbox_permissions", properties)
        self.assertNotIn("with_additional_permissions", properties["sandbox_permissions"]["description"])

    def test_local_http_shell_command_execution_argv_uses_default_user_shell(self) -> None:
        invocation = LocalHttpShellInvocation("Get-Content README.md")

        with patch(
            "pycodex.exec.local_runtime.default_user_shell",
            return_value=Shell(ShellType.POWERSHELL, "pwsh.exe"),
        ):
            self.assertEqual(
                _shell_command_execution_argv(invocation),
                ("pwsh.exe", "-Command", "Get-Content README.md"),
            )

        with patch(
            "pycodex.exec.local_runtime.default_user_shell",
            return_value=Shell(ShellType.SH, "/bin/sh"),
        ):
            self.assertEqual(
                _shell_command_execution_argv(LocalHttpShellInvocation("cat README.md", login=False)),
                ("/bin/sh", "-c", "cat README.md"),
            )

    def test_local_http_shell_command_execution_argv_preserves_explicit_shell(self) -> None:
        self.assertEqual(
            _shell_command_execution_argv(LocalHttpShellInvocation("Get-ChildItem", shell="powershell.exe")),
            ("powershell.exe", "-Command", "Get-ChildItem"),
        )
        self.assertEqual(
            _shell_command_execution_argv(LocalHttpShellInvocation("dir", shell="cmd.exe")),
            ("cmd.exe", "/C", "dir"),
        )
        self.assertEqual(
            _shell_command_execution_argv(LocalHttpShellInvocation("cat README.md", shell="/bin/bash", login=False)),
            ("/bin/bash", "-c", "cat README.md"),
        )

    def test_local_http_shell_tool_exec_policy_command_uses_same_shell_argv(self) -> None:
        invocation = LocalHttpShellInvocation("pwd")

        with patch(
            "pycodex.exec.local_runtime.default_user_shell",
            return_value=Shell(ShellType.POWERSHELL, "pwsh.exe"),
        ):
            self.assertEqual(
                _local_http_shell_tool_exec_policy_command(invocation),
                _shell_command_execution_argv(invocation),
            )
            self.assertEqual(
                _local_http_shell_tool_exec_policy_command(invocation),
                ("pwsh.exe", "-Command", "pwd"),
            )

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

    def test_local_http_view_image_tool_spec_shape(self) -> None:
        spec = local_http_view_image_tool_spec(can_request_original_image_detail=True)

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], "view_image")
        self.assertIs(spec["strict"], False)
        self.assertEqual(spec["parameters"]["required"], ["path"])
        self.assertIn("path", spec["parameters"]["properties"])
        self.assertEqual(spec["parameters"]["properties"]["detail"]["enum"], ["high", "original"])
        self.assertEqual(spec["output_schema"]["required"], ["image_url", "detail"])

    def test_local_http_shell_tools_built_tools_preserves_existing_specs(self) -> None:
        router = local_http_shell_tools_built_tools(lambda _session, _turn: ExistingToolRouter())(None, None)
        specs = router.model_visible_specs()

        self.assertEqual(
            [spec["name"] for spec in specs],
            ["existing", "exec_command", "write_stdin", "apply_patch", "view_image"],
        )

    def test_local_http_shell_tools_built_tools_uses_configured_shell_spec_flags(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            allow_login_shell=False,
            exec_permission_approvals_enabled=False,
            request_permissions_tool_enabled=False,
        )

        router = local_http_shell_tools_built_tools(config=config)(None, None)
        specs = router.model_visible_specs()
        self.assertEqual([spec["name"] for spec in specs], ["exec_command", "write_stdin", "apply_patch", "view_image"])
        exec_command = next(spec for spec in specs if spec["name"] == "exec_command")
        properties = exec_command["parameters"]["properties"]

        self.assertNotIn("login", properties)
        self.assertNotIn("additional_permissions", properties)
        self.assertIn("sandbox_permissions", properties)
        self.assertNotIn("with_additional_permissions", properties["sandbox_permissions"]["description"])

    def test_local_http_shell_tools_built_tools_hides_apply_patch_when_model_lacks_support(self) -> None:
        router = local_http_shell_tools_built_tools(
            model_info=SimpleNamespace(apply_patch_tool_type=None)
        )(None, None)
        specs = router.model_visible_specs()

        self.assertEqual([spec["name"] for spec in specs], ["exec_command", "write_stdin", "view_image"])

    def test_local_http_model_allows_apply_patch_tool_matches_rust_model_gate(self) -> None:
        self.assertTrue(local_http_model_allows_apply_patch_tool(None))
        self.assertTrue(local_http_model_allows_apply_patch_tool(SimpleNamespace()))
        self.assertTrue(local_http_model_allows_apply_patch_tool(LocalHttpModelInfo(slug="gpt-5")))
        self.assertFalse(
            local_http_model_allows_apply_patch_tool(SimpleNamespace(apply_patch_tool_type=None))
        )

    def test_local_http_model_image_helpers_match_rust_defaults(self) -> None:
        self.assertTrue(local_http_model_supports_image_inputs(None))
        self.assertTrue(local_http_model_supports_image_inputs(LocalHttpModelInfo(slug="gpt-5")))
        self.assertFalse(local_http_model_supports_image_inputs(SimpleNamespace(input_modalities=("text",))))
        self.assertTrue(local_http_model_supports_image_inputs(SimpleNamespace(input_modalities=("text", "image"))))
        self.assertTrue(local_http_model_allows_view_image_tool(None))
        self.assertTrue(local_http_model_allows_view_image_tool(LocalHttpModelInfo(slug="gpt-5")))
        self.assertFalse(local_http_model_allows_view_image_tool(SimpleNamespace(view_image_tool_disabled=True)))
        self.assertFalse(
            local_http_model_allows_view_image_tool(SimpleNamespace(disabled_tool_names=("view_image",)))
        )
        self.assertEqual(local_http_model_disabled_tool_names(None), frozenset())
        self.assertEqual(
            local_http_model_disabled_tool_names(SimpleNamespace(disabled_tool_names=("view_image", "get_goal"))),
            frozenset({"view_image", "get_goal"}),
        )
        self.assertFalse(local_http_model_can_request_original_image_detail(None))
        self.assertFalse(local_http_model_can_request_original_image_detail(LocalHttpModelInfo(slug="gpt-5")))
        self.assertTrue(
            local_http_model_can_request_original_image_detail(
                SimpleNamespace(supports_image_detail_original=True)
            )
        )

    def test_local_http_shell_tools_built_tools_hides_view_image_for_review_model(self) -> None:
        model_info = LocalHttpReviewModelInfo(LocalHttpModelInfo(slug="gpt-5"))

        router = local_http_shell_tools_built_tools(model_info=model_info)(None, None)
        specs = router.model_visible_specs()

        self.assertEqual(local_http_model_disabled_tool_names(model_info), LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES)
        self.assertEqual([spec["name"] for spec in specs], ["exec_command", "write_stdin", "apply_patch"])

    def test_local_http_shell_tools_built_tools_filters_existing_view_image_for_review_model(self) -> None:
        model_info = LocalHttpReviewModelInfo(LocalHttpModelInfo(slug="gpt-5"))

        router = local_http_shell_tools_built_tools(
            lambda _session, _turn: ExistingViewImageToolRouter(),
            model_info=model_info,
        )(None, None)
        specs = router.model_visible_specs()

        self.assertEqual([spec["name"] for spec in specs], ["exec_command", "write_stdin", "apply_patch"])

    def test_local_http_shell_tools_built_tools_filters_review_disabled_base_tools(self) -> None:
        model_info = LocalHttpReviewModelInfo(LocalHttpModelInfo(slug="gpt-5"))

        router = local_http_shell_tools_built_tools(
            lambda _session, _turn: ExistingReviewDisabledToolRouter(),
            model_info=model_info,
        )(None, None)
        specs = router.model_visible_specs()

        self.assertEqual([spec["name"] for spec in specs], ["existing", "exec_command", "write_stdin", "apply_patch"])

    def test_local_http_shell_tools_built_tools_exposes_permission_tools_when_configured(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            exec_permission_approvals_enabled=True,
            request_permissions_tool_enabled=True,
        )

        router = local_http_shell_tools_built_tools(config=config)(None, None)
        specs = router.model_visible_specs()
        self.assertEqual([spec["name"] for spec in specs], ["exec_command", "write_stdin", "request_permissions", "apply_patch", "view_image"])
        exec_command = next(spec for spec in specs if spec["name"] == "exec_command")
        properties = exec_command["parameters"]["properties"]

        self.assertIn("additional_permissions", properties)
        self.assertIn("with_additional_permissions", properties["sandbox_permissions"]["description"])

    def test_local_http_shell_tools_built_tools_accepts_async_base_builder(self) -> None:
        async def build_base(_session, _turn):
            return ExistingToolRouter()

        router = asyncio.run(local_http_shell_tools_built_tools(build_base)(None, None))
        specs = router.model_visible_specs()

        self.assertEqual(
            [spec["name"] for spec in specs],
            ["existing", "exec_command", "write_stdin", "apply_patch", "view_image"],
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
        self.assertIn(chr(0x2026), output)
        self.assertNotEqual(output, "甲乙丙丁")

    def test_local_http_shell_tool_truncation_marker_matches_rust_shape(self) -> None:
        output = _truncate_shell_tool_output("abcdefghijklmnopqrstuvwxyz", 12)

        self.assertRegex(output, rf"{chr(0x2026)}\d+ chars truncated{chr(0x2026)}")
        self.assertIn(f"abcdef{chr(0x2026)}14 chars truncated{chr(0x2026)}uvwxyz", output)
        self.assertNotIn("... ", output)

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
    async def test_run_exec_user_turn_core_sampling_runs_default_exec_tool_loop(self) -> None:
        cwd = Path.cwd()
        config = ExecSessionConfig(
            model="gpt-test",
            model_provider_id="openai",
            cwd=cwd,
            user_instructions="project instructions",
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("run the command"),)),
            "run the command",
        )
        provider = LocalHttpProvider()
        model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        command = shell_join_for_test(
            [
                sys.executable,
                "-c",
                "print('exec bridge output')",
            ]
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [
                    ResponseItem.function_call(
                        "exec_command",
                        json.dumps({"cmd": command, "yield_time_ms": 1_000}),
                        "call-exec",
                    )
                ]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done after exec"),))]

        result = await run_exec_user_turn_core_sampling(
            config,
            plan,
            client,
            provider,
            model_info,
            sampler,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertEqual(result.last_agent_message, "done after exec")
        self.assertEqual(len(result.request_plans), 2)
        self.assertIn("base", seen_requests[0].request_plan.request["instructions"])
        input_items = seen_requests[1].request_plan.request["input"]
        output_items = [item for item in input_items if getattr(item, "type", None) == "function_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0].call_id, "call-exec")
        output_text = output_items[0].output.body.text
        self.assertIn("exec bridge output", output_text)
        self.assertIn("Process exited with code 0", output_text)
        self.assertEqual(result.tool_response_items[0].call_id, "call-exec")

    async def test_run_exec_user_turn_core_sampling_uses_config_allow_login_shell_for_tools(self) -> None:
        cwd = Path.cwd()
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("inspect tools"),)),
            "inspect tools",
        )
        provider = LocalHttpProvider()
        model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        seen_tools_by_setting = {}

        async def run_with_setting(allow_login_shell: bool) -> None:
            config = ExecSessionConfig(
                model="gpt-test",
                model_provider_id="openai",
                cwd=cwd,
                allow_login_shell=allow_login_shell,
            )

            async def sampler(request):
                seen_tools_by_setting[allow_login_shell] = request.request_plan.request["tools"]
                return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

            await run_exec_user_turn_core_sampling(
                config,
                plan,
                client,
                provider,
                model_info,
                sampler,
            )

        await run_with_setting(True)
        await run_with_setting(False)

        tools_when_allowed = {tool["name"]: tool for tool in seen_tools_by_setting[True]}
        tools_when_blocked = {tool["name"]: tool for tool in seen_tools_by_setting[False]}
        self.assertIn("login", tools_when_allowed["exec_command"]["parameters"]["properties"])
        self.assertNotIn("login", tools_when_blocked["exec_command"]["parameters"]["properties"])

    async def test_run_exec_user_turn_core_sampling_uses_model_parallel_tool_calls(self) -> None:
        cwd = Path.cwd()
        config = ExecSessionConfig(
            model="gpt-test",
            model_provider_id="openai",
            cwd=cwd,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("inspect request"),)),
            "inspect request",
        )
        provider = LocalHttpProvider()
        model_info = LocalHttpModelInfo(
            slug="gpt-test",
            base_instructions="base",
            supports_parallel_tool_calls=True,
        )
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        await run_exec_user_turn_core_sampling(
            config,
            plan,
            client,
            provider,
            model_info,
            sampler,
        )

        self.assertTrue(seen_requests[0].request_plan.request["parallel_tool_calls"])

    async def test_run_exec_user_turn_http_sampling_uses_core_exec_tool_loop_by_default(self) -> None:
        cwd = Path.cwd()
        config = ExecSessionConfig(
            model="gpt-test",
            model_provider_id="openai",
            cwd=cwd,
            user_instructions="project instructions",
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("run the command"),)),
            "run the command",
        )
        provider = LocalHttpProvider(base_url="https://api.example.test/v1")
        model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        command = shell_join_for_test(
            [
                sys.executable,
                "-c",
                "print('http core exec output')",
            ]
        )
        request_bodies = []
        responses = [
            FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "exec_command",
                            "arguments": json.dumps({"cmd": command, "yield_time_ms": 1_000}),
                            "call_id": "call-exec",
                        }
                    ]
                }
            ),
            FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done after core exec"}],
                        }
                    ]
                }
            ),
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        result = await run_exec_user_turn_http_sampling(
            config,
            plan,
            client,
            provider,
            model_info,
            auth="sk-test",
            opener=opener,
        )

        self.assertEqual(len(request_bodies), 2)
        self.assertTrue(any(tool["name"] == "exec_command" for tool in request_bodies[0]["tools"]))
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "call-exec")
        self.assertIn("http core exec output", output_items[0]["output"])
        self.assertEqual(result.last_agent_message, "done after core exec")

        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor(), config=config)
        self.assertEqual(
            [(item.id, item.type, item.payload["status"]) for item in timeline_items],
            [
                ("call-exec", "command_execution", "in_progress"),
                ("call-exec", "command_execution", "completed"),
            ],
        )
        self.assertEqual(timeline_items[0].payload["command"], command)
        self.assertEqual(timeline_items[0].payload["source"], "agent")
        self.assertIn("http core exec output", timeline_items[1].payload["aggregated_output"])
        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, config=config, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        command_events = [
            line["item"]
            for line in json_lines
            if line["type"] == "item.completed" and line["item"]["type"] == "command_execution"
        ]
        self.assertEqual(
            [(item["id"], item["command"], item["status"]) for item in command_events],
            [
                ("call-exec", command, "in_progress"),
                ("call-exec", command, "completed"),
            ],
        )
        self.assertIn("http core exec output", command_events[1]["aggregated_output"])
        human_stdout = io.StringIO()
        human_stderr = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            config=config,
            stdout=human_stdout,
            stderr=human_stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        human_error = human_stderr.getvalue()
        self.assertIn("exec", human_error)
        self.assertIn(command, human_error)
        self.assertIn("succeeded", human_error)
        self.assertIn("http core exec output", human_error)
        self.assertEqual(human_stdout.getvalue(), "done after core exec\n")

    async def test_run_exec_user_turn_http_sampling_uses_core_apply_patch_tool_loop_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = ExecSessionConfig(
                model="gpt-test",
                model_provider_id="openai",
                cwd=root,
                approval_policy=AskForApproval.NEVER,
                permission_profile=PermissionProfile.workspace_write(),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("create file"),)),
                "create file",
            )
            provider = LocalHttpProvider(base_url="https://api.example.test/v1")
            model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
            client = ModelClient(
                session_id="session",
                thread_id="thread",
                installation_id="install",
                provider=provider,
            )
            patch_text = "*** Begin Patch\n*** Add File: created.txt\n+core patch\n*** End Patch\n"
            request_bodies = []
            responses = [
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "custom_tool_call",
                                "name": "apply_patch",
                                "input": patch_text,
                                "call_id": "patch-1",
                            }
                        ]
                    }
                ),
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done after patch"}],
                            }
                        ]
                    }
                ),
            ]

            def opener(request):
                request_bodies.append(json.loads(request.data.decode("utf-8")))
                return responses.pop(0)

            result = await run_exec_user_turn_http_sampling(
                config,
                plan,
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
            )

            self.assertEqual((root / "created.txt").read_text(encoding="utf-8"), "core patch\n")

        self.assertEqual(len(request_bodies), 2)
        self.assertTrue(any(tool["name"] == "apply_patch" for tool in request_bodies[0]["tools"]))
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "custom_tool_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "patch-1")
        self.assertNotIn("name", output_items[0])
        self.assertIs(output_items[0]["success"], True)
        self.assertIn("Success. Updated the following files:", output_items[0]["output"])
        self.assertEqual(result.last_agent_message, "done after patch")

    async def test_run_exec_user_turn_http_sampling_core_apply_patch_respects_read_only_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = ExecSessionConfig(
                model="gpt-test",
                model_provider_id="openai",
                cwd=root,
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.read_only(),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("create file"),)),
                "create file",
            )
            provider = LocalHttpProvider(base_url="https://api.example.test/v1")
            model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
            client = ModelClient(
                session_id="session",
                thread_id="thread",
                installation_id="install",
                provider=provider,
            )
            patch_text = "*** Begin Patch\n*** Add File: created.txt\n+blocked patch\n*** End Patch\n"
            request_bodies = []
            responses = [
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "custom_tool_call",
                                "name": "apply_patch",
                                "input": patch_text,
                                "call_id": "patch-1",
                            }
                        ]
                    }
                ),
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "blocked"}],
                            }
                        ]
                    }
                ),
            ]

            def opener(request):
                request_bodies.append(json.loads(request.data.decode("utf-8")))
                return responses.pop(0)

            result = await run_exec_user_turn_http_sampling(
                config,
                plan,
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
            )

            self.assertFalse((root / "created.txt").exists())

        self.assertEqual(result.last_agent_message, "blocked")
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "custom_tool_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "patch-1")
        self.assertIs(output_items[0]["success"], False)
        self.assertIn("approval_required", output_items[0]["output"])

    async def test_run_exec_user_turn_http_sampling_core_request_permissions_unblocks_apply_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            def request_permissions_callback(_parent_ctx, call_id, args, cwd, _cancel_token):
                self.assertEqual(call_id, "perm-1")
                self.assertEqual(cwd, root)
                self.assertEqual(args.reason, "Need to create the requested file")
                return RequestPermissionsResponse(
                    permissions=RequestPermissionProfile(
                        file_system=FileSystemPermissions(
                            (
                                FileSystemSandboxEntry(
                                    FileSystemPath.explicit_path(root),
                                    FileSystemAccessMode.WRITE,
                                ),
                            )
                        )
                    ),
                    scope=PermissionGrantScope.TURN,
                )

            config = ExecSessionConfig(
                model="gpt-test",
                model_provider_id="openai",
                cwd=root,
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.read_only(),
                request_permissions_callback=request_permissions_callback,
                request_permissions_tool_enabled=True,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("create file"),)),
                "create file",
            )
            provider = LocalHttpProvider(base_url="https://api.example.test/v1")
            model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
            client = ModelClient(
                session_id="session",
                thread_id="thread",
                installation_id="install",
                provider=provider,
            )
            request_permissions_arguments = {
                "reason": "Need to create the requested file",
                "permissions": {
                    "file_system": {
                        "entries": [
                            {
                                "path": {"type": "path", "path": "."},
                                "access": "write",
                            }
                        ]
                    }
                },
            }
            patch_text = "*** Begin Patch\n*** Add File: created.txt\n+granted patch\n*** End Patch\n"
            request_bodies = []
            responses = [
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "request_permissions",
                                "arguments": json.dumps(request_permissions_arguments),
                                "call_id": "perm-1",
                            }
                        ]
                    }
                ),
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "custom_tool_call",
                                "name": "apply_patch",
                                "input": patch_text,
                                "call_id": "patch-1",
                            }
                        ]
                    }
                ),
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done after grant"}],
                            }
                        ]
                    }
                ),
            ]

            def opener(request):
                request_bodies.append(json.loads(request.data.decode("utf-8")))
                return responses.pop(0)

            result = await run_exec_user_turn_http_sampling(
                config,
                plan,
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
            )

            self.assertEqual((root / "created.txt").read_text(encoding="utf-8"), "granted patch\n")

        self.assertEqual(result.last_agent_message, "done after grant")
        self.assertEqual(len(request_bodies), 3)
        self.assertTrue(any(tool["name"] == "request_permissions" for tool in request_bodies[0]["tools"]))
        request_permission_outputs = [
            item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"
        ]
        self.assertEqual(len(request_permission_outputs), 1)
        self.assertEqual(request_permission_outputs[0]["call_id"], "perm-1")
        self.assertIs(request_permission_outputs[0]["success"], True)
        patch_outputs = [item for item in request_bodies[2]["input"] if item["type"] == "custom_tool_call_output"]
        self.assertEqual(len(patch_outputs), 1)
        self.assertEqual(patch_outputs[0]["call_id"], "patch-1")
        self.assertIs(patch_outputs[0]["success"], True)
        self.assertIn("Success. Updated the following files:", patch_outputs[0]["output"])

    async def test_run_exec_user_turn_http_sampling_core_request_permissions_auto_denies_when_approval_never(self) -> None:
        def request_permissions_callback(_parent_ctx, _call_id, _args, _cwd, _cancel_token):
            raise AssertionError("approval never should not ask the client for permissions")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = ExecSessionConfig(
                model="gpt-test",
                model_provider_id="openai",
                cwd=root,
                approval_policy=AskForApproval.NEVER,
                permission_profile=PermissionProfile.read_only(),
                request_permissions_callback=request_permissions_callback,
                request_permissions_tool_enabled=True,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("request permissions"),)),
                "request permissions",
            )
            provider = LocalHttpProvider(base_url="https://api.example.test/v1")
            model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
            client = ModelClient(
                session_id="session",
                thread_id="thread",
                installation_id="install",
                provider=provider,
            )
            request_permissions_arguments = {
                "reason": "Need network",
                "permissions": {"network": {"enabled": True}},
            }
            request_bodies = []
            responses = [
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "request_permissions",
                                "arguments": json.dumps(request_permissions_arguments),
                                "call_id": "perm-1",
                            }
                        ]
                    }
                ),
                FakePayloadResponse(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "denied"}],
                            }
                        ]
                    }
                ),
            ]

            def opener(request):
                request_bodies.append(json.loads(request.data.decode("utf-8")))
                return responses.pop(0)

            result = await run_exec_user_turn_http_sampling(
                config,
                plan,
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
            )

        self.assertEqual(result.last_agent_message, "denied")
        self.assertEqual(len(request_bodies), 2)
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "perm-1")
        self.assertIs(output_items[0]["success"], True)
        output = json.loads(output_items[0]["output"])
        self.assertEqual(output["permissions"], {})
        self.assertEqual(output["scope"], "turn")
        self.assertFalse(output.get("strict_auto_review", False))

    async def test_run_exec_user_turn_http_sampling_passes_exec_approval_policy_to_core_tools(self) -> None:
        cwd = Path.cwd()
        config = ExecSessionConfig(
            model="gpt-test",
            model_provider_id="openai",
            cwd=cwd,
            approval_policy=AskForApproval.NEVER,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("run escalated"),)),
            "run escalated",
        )
        provider = LocalHttpProvider(base_url="https://api.example.test/v1")
        model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            provider=provider,
        )
        request_bodies = []
        responses = [
            FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "exec_command",
                            "arguments": json.dumps(
                                {
                                    "cmd": "echo should-not-run",
                                    "sandbox_permissions": "require_escalated",
                                }
                            ),
                            "call_id": "call-escalated",
                        }
                    ]
                }
            ),
            FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "blocked"}],
                        }
                    ]
                }
            ),
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        result = await run_exec_user_turn_http_sampling(
            config,
            plan,
            client,
            provider,
            model_info,
            auth="sk-test",
            opener=opener,
        )

        self.assertEqual(result.last_agent_message, "blocked")
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "call-escalated")
        self.assertIn("cannot ask for escalated permissions", output_items[0]["output"])
        self.assertNotIn("should-not-run", output_items[0]["output"])

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
        _assert_message_texts_in_order(self, message_items, ["previous user", "previous assistant", "current prompt"])
        self.assertEqual(message_items[-1]["content"][0]["text"], "current prompt")

    async def test_run_exec_review_http_sampling_uses_review_prompt_and_renders_output(self) -> None:
        seen = {}

        class ReviewResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": json.dumps(
                                            {
                                                "findings": [],
                                                "overall_correctness": "patch is correct",
                                                "overall_explanation": "No findings.",
                                                "overall_confidence_score": 0.91,
                                            }
                                        ),
                                    }
                                ],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return ReviewResponse()

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
            user_instructions="project instructions must not enter review",
            approval_policy=AskForApproval.ON_REQUEST,
        )
        plan = ExecRunPlan(
            InitialOperation.review(ReviewRequest(ReviewTarget.uncommitted_changes())),
            "current changes",
        )

        result = await run_exec_review_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["instructions"], REVIEW_PROMPT)
        input_texts = [item["content"][0]["text"] for item in seen["body"]["input"] if item.get("content")]
        self.assertIn(
            "Review the current code changes (staged, unstaged, and untracked files) and provide prioritized findings.",
            input_texts,
        )
        self.assertFalse(any("project instructions must not enter review" in text for text in input_texts))
        self.assertEqual(final_text_from_local_http_exec_result(result), "No findings.")
        session_events = tuple(result.session_events)
        self.assertEqual(session_events[0].type, "entered_review_mode")
        self.assertEqual(session_events[0].payload.user_facing_hint, "current changes")
        exit_event = next(event for event in reversed(session_events) if event.type == "exited_review_mode")
        self.assertEqual(exit_event.payload.review_output.overall_explanation, "No findings.")
        self.assertEqual(exit_event.payload.review_output.overall_confidence_score, 0.91)
        rollout_input = local_http_review_rollout_input_items(result)
        self.assertEqual(len(rollout_input), 1)
        self.assertIn("full review output from reviewer model", rollout_input[0].text)
        self.assertIn("<action>review</action>", rollout_input[0].text)
        self.assertIn("No findings.", rollout_input[0].text)

    async def test_run_exec_review_core_http_sampling_uses_review_prompt_and_renders_output(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "findings": [],
                                            "overall_correctness": "patch is correct",
                                            "overall_explanation": "Core review ok.",
                                            "overall_confidence_score": 0.87,
                                        }
                                    ),
                                }
                            ],
                        }
                    ]
                }
            )

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
            user_instructions="project instructions must not enter review",
            approval_policy=AskForApproval.ON_REQUEST,
        )
        plan = ExecRunPlan(
            InitialOperation.review(ReviewRequest(ReviewTarget.uncommitted_changes())),
            "current changes",
        )

        result = await run_exec_review_core_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["instructions"], REVIEW_PROMPT)
        input_texts = [item["content"][0]["text"] for item in seen["body"]["input"] if item.get("content")]
        self.assertIn(
            "Review the current code changes (staged, unstaged, and untracked files) and provide prioritized findings.",
            input_texts,
        )
        self.assertFalse(any("project instructions must not enter review" in text for text in input_texts))
        self.assertEqual(final_text_from_local_http_exec_result(result), "Core review ok.")
        session_events = tuple(result.session_events)
        self.assertEqual(session_events[0].type, "entered_review_mode")
        exit_event = next(event for event in reversed(session_events) if event.type == "exited_review_mode")
        self.assertEqual(exit_event.payload.review_output.overall_confidence_score, 0.87)

    async def test_run_exec_review_http_sampling_plain_text_output_emits_review_lifecycle(self) -> None:
        class PlainReviewResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "Looks good from here."}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

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
        config = ExecSessionConfig(model="gpt-test", model_provider_id="openai", cwd=Path("C:/work/project"))
        plan = ExecRunPlan(
            InitialOperation.review(ReviewRequest(ReviewTarget.uncommitted_changes())),
            "current changes",
        )

        result = await run_exec_review_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=lambda _request: PlainReviewResponse(),
            built_tools=lambda _sess, _turn: Router(),
        )

        session_events = tuple(result.session_events)
        self.assertEqual(session_events[0].type, "entered_review_mode")
        exit_event = next(event for event in reversed(session_events) if event.type == "exited_review_mode")
        self.assertEqual(exit_event.payload.review_output.overall_explanation, "Looks good from here.")
        self.assertEqual(final_text_from_local_http_exec_result(result), "Looks good from here.")

    async def test_run_exec_review_http_sampling_shell_tools_hide_view_image(self) -> None:
        seen = {}

        class ReviewResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "Looks good from here."}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return ReviewResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "base_instructions": "base",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "supports_image_detail_original": True,
                "input_modalities": ("text", "image"),
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        config = ExecSessionConfig(model="gpt-test", model_provider_id="openai", cwd=Path("C:/work/project"))
        plan = ExecRunPlan(
            InitialOperation.review(ReviewRequest(ReviewTarget.uncommitted_changes())),
            "current changes",
        )

        await run_exec_review_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
            use_shell_tools=True,
        )

        tool_names = [tool["name"] for tool in seen["body"]["tools"]]
        self.assertIn("exec_command", tool_names)
        self.assertIn("apply_patch", tool_names)
        self.assertNotIn("view_image", tool_names)

    async def test_run_exec_review_http_sampling_interrupted_output_uses_review_interrupted_lifecycle(self) -> None:
        async def fake_run(*_args, **_kwargs):
            return UserTurnSamplingResult(
                request_plan=None,
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("partial review"),)),),
                turn_status="interrupted",
            )

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
        config = ExecSessionConfig(model="gpt-test", model_provider_id="openai", cwd=Path("C:/work/project"))
        plan = ExecRunPlan(
            InitialOperation.review(ReviewRequest(ReviewTarget.uncommitted_changes())),
            "current changes",
        )

        with patch("pycodex.exec.local_runtime.run_exec_user_turn_http_sampling", fake_run):
            result = await run_exec_review_http_sampling(
                config,
                plan,
                ModelClient(session_id="session", thread_id="thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                auth="sk-test",
                built_tools=lambda _sess, _turn: Router(),
            )

        session_events = tuple(result.session_events)
        self.assertEqual([session_events[0].type, session_events[-1].type], ["entered_review_mode", "exited_review_mode"])
        self.assertIsNone(session_events[-1].payload.review_output)
        self.assertEqual(final_text_from_local_http_exec_result(result), "")
        self.assertIn("Review was interrupted", final_text_from_response_items(result.response_items))
        rollout_input = local_http_review_rollout_input_items(result)
        self.assertIn("User initiated a review task, but was interrupted.", rollout_input[0].text)
        self.assertIn("<action>review</action>", rollout_input[0].text)
        self.assertIn("None.", rollout_input[0].text)

        with tempfile.TemporaryDirectory() as tmpdir:
            rollout_path = persist_local_http_exec_rollout(
                Path(tmpdir),
                config,
                result,
                ModelClient(session_id="session", thread_id="review-interrupted", installation_id="install"),
                input_items=rollout_input,
            )
            self.assertIsNotNone(rollout_path)
            persisted_items = read_response_items_from_rollout(rollout_path)
        persisted_texts = [
            content.text
            for item in persisted_items
            for content in item.content
            if isinstance(getattr(content, "text", None), str)
        ]
        self.assertTrue(any("User initiated a review task, but was interrupted." in text for text in persisted_texts))
        self.assertTrue(any("Review was interrupted. Please re-run /review" in text for text in persisted_texts))
        self.assertFalse(any("<turn_aborted>" in text for text in persisted_texts))

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
        self.assertEqual(headers["x-codex-installation-id"], "pycodex-local-exec")
        self.assertIn("x-codex-window-id", headers)
        self.assertTrue(headers["X-codex-window-id".lower()].endswith(":0"))
        self.assertEqual(seen["body"]["client_metadata"]["x-codex-installation-id"], "pycodex-local-exec")
        self.assertEqual(seen["body"]["model"], "gpt-env")
        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertTrue(local_http_exec_enabled({"OPENAI_API_KEY": "sk-env"}))
        self.assertTrue(local_http_exec_enabled({"CODEX_API_KEY": "sk-codex"}))
        self.assertFalse(local_http_exec_enabled({"PYCODEX_EXEC_LOCAL_HTTP": "0", "OPENAI_API_KEY": "sk-env"}))
        self.assertTrue(local_core_exec_enabled({"PYCODEX_EXEC_CORE": "1"}))
        self.assertTrue(local_core_exec_enabled({"PYCODEX_EXEC_CORE": "enabled"}))
        self.assertFalse(local_core_exec_enabled({"PYCODEX_EXEC_CORE": "0", "OPENAI_API_KEY": "sk-env"}))
        self.assertFalse(local_core_exec_enabled({"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"}))
        self.assertTrue(local_core_exec_enabled({"OPENAI_API_KEY": "sk-env"}))
        self.assertTrue(local_core_exec_enabled({"CODEX_API_KEY": "sk-codex"}))
        self.assertTrue(core_exec_enabled({"PYCODEX_EXEC_CORE": "1"}))
        self.assertTrue(core_exec_enabled({"OPENAI_API_KEY": "sk-env"}))

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

    def test_local_http_exec_result_uses_streamed_last_agent_message_without_response_items(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            last_agent_message="streamed answer",
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "")
        self.assertEqual(final_text_from_local_http_exec_result(result), "streamed answer")

        stdout = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=stdout,
            stderr=io.StringIO(),
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertEqual(stdout.getvalue(), "streamed answer\n")

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual([line["type"] for line in json_lines], ["turn.started", "item.completed", "turn.completed"])
        self.assertEqual(json_lines[1]["item"]["type"], "agent_message")
        self.assertEqual(json_lines[1]["item"]["text"], "streamed answer")

    def test_local_http_exec_result_prefers_response_items_over_streamed_last_agent_message(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("item answer"),)),),
            last_agent_message="streamed answer",
        )

        self.assertEqual(final_text_from_local_http_exec_result(result), "item answer")

    def test_local_http_exec_merge_preserves_followup_streamed_last_agent_message(self) -> None:
        previous = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            last_agent_message="partial answer",
        )
        followup = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            last_agent_message="streamed followup answer",
        )

        merged = _merge_local_http_sampling_result(
            previous,
            (
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "ok",
                    "success": True,
                },
            ),
            followup,
        )

        self.assertEqual(merged.last_agent_message, "streamed followup answer")
        self.assertEqual(final_text_from_local_http_exec_result(merged), "streamed followup answer")

    def test_local_http_exec_merge_preserves_followup_interrupted_status(self) -> None:
        previous = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            last_agent_message="partial answer",
            turn_status="completed",
        )
        followup = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            last_agent_message="interrupted partial",
            turn_status="interrupted",
        )

        merged = _merge_local_http_sampling_result(previous, (), followup)

        self.assertEqual(merged.turn_status, "interrupted")
        self.assertEqual(merged.last_agent_message, "interrupted partial")
        self.assertEqual(final_text_from_local_http_exec_result(merged), "")

    def test_local_http_exec_merge_accumulates_stream_runtime_artifacts(self) -> None:
        previous = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            stream_events=({"type": "output_item.added", "item_id": "msg-1"},),
            stream_event_dispatch_plans=("dispatch-1",),
            stream_event_apply_plans=("apply-1",),
            stream_runtime_state_summary={"last_agent_message": "partial"},
        )
        followup = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            stream_events=({"type": "completed", "response_id": "resp-2"},),
            stream_event_dispatch_plans=("dispatch-2",),
            stream_event_apply_plans=("apply-2",),
            stream_runtime_state_summary={"last_agent_message": "final"},
        )

        merged = _merge_local_http_sampling_result(previous, (), followup)

        self.assertEqual(
            merged.stream_events,
            (
                {"type": "output_item.added", "item_id": "msg-1"},
                {"type": "completed", "response_id": "resp-2"},
            ),
        )
        self.assertEqual(merged.stream_event_dispatch_plans, ("dispatch-1", "dispatch-2"))
        self.assertEqual(merged.stream_event_apply_plans, ("apply-1", "apply-2"))
        self.assertEqual(merged.stream_runtime_state_summary, {"last_agent_message": "final"})

    def test_local_http_exec_merge_keeps_previous_stream_state_summary_when_followup_has_none(self) -> None:
        previous = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            stream_runtime_state_summary={"last_agent_message": "partial"},
        )
        followup = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            stream_runtime_state_summary=None,
        )

        merged = _merge_local_http_sampling_result(previous, (), followup)

        self.assertEqual(merged.stream_runtime_state_summary, {"last_agent_message": "partial"})

    def test_local_http_exec_json_output_does_not_replay_stream_deltas(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            session_events=(
                EventMsg.from_mapping(
                    {
                        "type": "agent_message_content_delta",
                        "thread_id": "thread-1",
                        "turn_id": "turn-1",
                        "item_id": "msg-1",
                        "delta": "partial",
                    }
                ),
                EventMsg.from_mapping(
                    {
                        "type": "reasoning_content_delta",
                        "thread_id": "thread-1",
                        "turn_id": "turn-1",
                        "item_id": "reason-1",
                        "delta": "think",
                        "summary_index": 0,
                    }
                ),
                EventMsg.from_mapping(
                    {
                        "type": "agent_reasoning_section_break",
                        "item_id": "reason-1",
                        "summary_index": 1,
                    }
                ),
            ),
            stream_events=(
                {"type": "output_item_added", "item": ResponseItem.reasoning(id="reason-1")},
                {"type": "reasoning_summary_delta", "item_id": "reason-1", "delta": "think", "summary_index": 0},
                {"type": "reasoning_summary_part_added", "item_id": "reason-1", "summary_index": 0},
                {"type": "completed", "response_id": "resp-1", "end_turn": True},
            ),
        )

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

    def test_local_http_exec_error_replays_attached_session_events(self) -> None:
        error = CodexErr.simple("context_window_exceeded")
        object.__setattr__(error, "session_events", (
            EventMsg.with_payload(
                "token_count",
                TokenCountEvent(
                    info=TokenUsageInfo(
                        total_token_usage=TokenUsage(
                            input_tokens=5,
                            cached_input_tokens=1,
                            output_tokens=3,
                            reasoning_output_tokens=2,
                            total_tokens=8,
                        ),
                        last_token_usage=TokenUsage(
                            input_tokens=5,
                            cached_input_tokens=1,
                            output_tokens=3,
                            reasoning_output_tokens=2,
                            total_tokens=8,
                        ),
                        model_context_window=128000,
                    ),
                ),
            ),
        ))
        processor = JsonEventProcessor()
        stdout = io.StringIO()

        emit_local_http_exec_error(processor, error, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([line["type"] for line in lines], ["turn.started", "turn.failed"])
        self.assertEqual(lines[1]["error"]["message"], str(error))
        self.assertEqual(processor.last_usage.input_tokens, 5)
        self.assertEqual(processor.last_usage.cached_input_tokens, 1)

    def test_local_http_exec_error_replays_metadata_session_events_inside_turn(self) -> None:
        error = CodexErr.simple("context_window_exceeded")
        object.__setattr__(error, "session_events", (
            EventMsg.with_payload(
                "model_reroute",
                ModelRerouteEvent("gpt-5.3-codex", "gpt-5.2", ModelRerouteReason.HIGH_RISK_CYBER_ACTIVITY),
            ),
            EventMsg.with_payload("warning", WarningEvent("reroute warning")),
            EventMsg.with_payload(
                "model_verification",
                ModelVerificationEvent((ModelVerification.TRUSTED_ACCESS_FOR_CYBER,)),
            ),
        ))
        processor = JsonEventProcessor()
        stdout = io.StringIO()

        emit_local_http_exec_error(processor, error, stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(
            [line["type"] for line in lines],
            ["turn.started", "item.completed", "item.completed", "turn.failed"],
        )
        self.assertEqual(lines[1]["item"]["message"], "model rerouted: gpt-5.3-codex -> gpt-5.2 (HighRiskCyberActivity)")
        self.assertEqual(lines[2]["item"]["message"], "reroute warning")
        self.assertEqual(lines[3]["error"]["message"], str(error))

    def test_local_http_exec_result_replays_metadata_session_events(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            session_events=(
                EventMsg.with_payload(
                    "model_reroute",
                    ModelRerouteEvent("gpt-5.3-codex", "gpt-5.2", ModelRerouteReason.HIGH_RISK_CYBER_ACTIVITY),
                ),
                EventMsg.with_payload("warning", WarningEvent("reroute warning")),
                EventMsg.with_payload(
                    "model_verification",
                    ModelVerificationEvent((ModelVerification.TRUSTED_ACCESS_FOR_CYBER,)),
                ),
            ),
        )

        json_stdout = io.StringIO()
        json_processor = JsonEventProcessor()
        emit_local_http_exec_result(json_processor, result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(json_lines[0]["type"], "turn.started")
        self.assertEqual(json_lines[1]["item"]["message"], "model rerouted: gpt-5.3-codex -> gpt-5.2 (HighRiskCyberActivity)")
        self.assertEqual(json_lines[2]["item"]["message"], "reroute warning")
        self.assertEqual(json_lines[-1]["type"], "turn.completed")

        stderr = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=io.StringIO(),
            stderr=stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        output = stderr.getvalue()
        self.assertIn("model rerouted: gpt-5.3-codex -> gpt-5.2", output)
        self.assertIn("warning: reroute warning", output)
        self.assertNotIn("model/verification", output)

    def test_local_http_exec_result_replays_stream_error_session_event(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            session_events=(
                EventMsg.with_payload(
                    "stream_error",
                    StreamErrorEvent(
                        "Reconnecting... 1/5",
                        CodexErrorInfo.response_stream_disconnected(502),
                        "temporary disconnect",
                    ),
                ),
            ),
        )

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(json_lines[0]["type"], "turn.started")
        self.assertEqual(json_lines[1]["type"], "error")
        self.assertEqual(json_lines[1]["message"], "Reconnecting... 1/5 (temporary disconnect)")
        self.assertEqual(json_lines[-1]["type"], "turn.completed")

        stderr = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=io.StringIO(),
            stderr=stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertIn("ERROR: Reconnecting... 1/5 (temporary disconnect)", stderr.getvalue())

    def test_local_http_exec_result_renders_interrupted_turn_without_final_answer(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("partial"),)),),
            turn_status="interrupted",
        )

        json_stdout = io.StringIO()
        final_text = emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(final_text, "")
        self.assertEqual([line["type"] for line in json_lines], ["turn.started"])

        stderr = io.StringIO()
        final_text = emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=io.StringIO(),
            stderr=stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertEqual(final_text, "")
        self.assertIn("turn interrupted", stderr.getvalue())
        self.assertNotIn("partial", stderr.getvalue())

    def test_local_http_exec_rollout_persists_interrupted_turn_marker(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("partial"),)),),
            turn_status="interrupted",
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        client = ModelClient(session_id="session", thread_id="thread-interrupted", installation_id="install")

        with tempfile.TemporaryDirectory() as tmp:
            rollout_path = persist_local_http_exec_rollout(Path(tmp), config, result, client)
            self.assertIsNotNone(rollout_path)
            items = read_response_items_from_rollout(rollout_path)
            events = read_event_msgs_from_rollout(rollout_path)

        self.assertEqual(items[-1].role, "user")
        self.assertIn("<turn_aborted>", items[-1].content[0].text)
        self.assertIn("interrupted the previous turn", items[-1].content[0].text)
        self.assertEqual(events[-1].type, "turn_aborted")
        self.assertEqual(events[-1].payload.reason, "interrupted")

    def test_local_http_exec_error_replays_attached_terminal_error_event(self) -> None:
        error = CodexErr.simple("context_window_exceeded")
        object.__setattr__(error, "session_events", (
            EventMsg.with_payload(
                "error",
                ErrorEvent("too much context", CodexErrorInfo.context_window_exceeded()),
            ),
        ))

        json_stdout = io.StringIO()
        emit_local_http_exec_error(JsonEventProcessor(), error, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual([line["type"] for line in json_lines], ["turn.started", "error", "turn.failed"])
        self.assertEqual(json_lines[1]["message"], "too much context")
        self.assertEqual(json_lines[2]["error"]["message"], str(error))

        stderr = io.StringIO()
        emit_local_http_exec_error(HumanEventProcessor(), error, stderr=stderr)
        self.assertEqual(stderr.getvalue().count("ERROR:"), 1)
        self.assertIn("ERROR: too much context", stderr.getvalue())

    async def test_local_http_context_window_error_attaches_session_events(self) -> None:
        class ContextWindowResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "status": "failed",
                        "error": {
                            "code": "context_length_exceeded",
                            "message": "too much context",
                        },
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(_request):
            return ContextWindowResponse()

        model_info = SimpleNamespace(
            slug="gpt-test",
            context_window=2000,
            max_context_window=None,
            effective_context_window_percent=80,
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        result = await run_exec_user_turn_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        events = tuple(getattr(result, "session_events", ()))
        self.assertEqual([event.type for event in events[-3:]], ["token_count", "error", "task_complete"])
        self.assertEqual(events[-3].payload.info.total_token_usage.total_tokens, 1600)
        self.assertEqual(events[-2].payload.codex_error_info.type, "context_window_exceeded")
        self.assertIsNone(events[-1].payload.last_agent_message)

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
            _assert_message_texts_in_order(self, message_items, ["previous user", "previous assistant", "current prompt"])
            self.assertEqual(message_items[-1]["content"][0]["text"], "current prompt")
            self.assertEqual(request_headers[0]["session-id"], thread_id)
            self.assertEqual(request_headers[0]["thread-id"], thread_id)
            self.assertEqual(count_session_rollout_files(codex_home), 1)
            self.assertEqual(find_session_rollout_containing_response_marker(codex_home, "done"), rollout_path)
            self.assertEqual(read_response_items_from_rollout(rollout_path)[-1].content[0].text, "done")

    async def test_local_http_resume_runner_uses_core_exec_tool_loop_and_persists_outputs(self) -> None:
        request_bodies = []
        command = shell_join_for_test(
            [
                sys.executable,
                "-c",
                "print('resume core exec output')",
            ]
        )
        responses = [
            FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "exec_command",
                            "arguments": json.dumps({"cmd": command, "yield_time_ms": 1_000}),
                            "call_id": "resume-core-exec",
                        }
                    ]
                }
            ),
            FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "resume done"}],
                        }
                    ]
                }
            ),
        ]

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
            thread_id = "77777777-7777-7777-7777-777777777777"
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

            plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("run resumed command"),)), "run resumed command")

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
            )

            rollout_items = read_response_items_from_rollout(rollout_path)

        self.assertEqual(result.last_agent_message, "resume done")
        self.assertEqual(len(request_bodies), 2)
        first_messages = [item for item in request_bodies[0]["input"] if item.get("type") == "message"]
        _assert_message_texts_in_order(
            self,
            first_messages,
            ["previous user", "previous assistant", "run resumed command"],
        )
        followup_outputs = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(len(followup_outputs), 1)
        self.assertEqual(followup_outputs[0]["call_id"], "resume-core-exec")
        self.assertIn("resume core exec output", followup_outputs[0]["output"])
        self.assertEqual(
            [(item.type, item.call_id) for item in rollout_items[-3:]],
            [
                ("function_call", "resume-core-exec"),
                ("function_call_output", "resume-core-exec"),
                ("message", None),
            ],
        )
        self.assertIn("resume core exec output", rollout_items[-2].output.body.text)
        self.assertEqual(rollout_items[-1].content[0].text, "resume done")

    async def test_core_http_resume_runner_uses_reconstructed_history_and_persists_output(self) -> None:
        request_bodies = []

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakePayloadResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "core resumed"}],
                        }
                    ]
                }
            )

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
            thread_id = "88888888-8888-8888-8888-888888888888"
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

            plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("continue core"),)), "continue core")

            result = await run_exec_resume_user_turn_core_http_sampling(
                codex_home,
                config,
                plan,
                ModelClient(session_id="session", thread_id="new-thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                thread_id=thread_id,
                auth="sk-test",
                opener=opener,
            )
            rollout_items = read_response_items_from_rollout(rollout_path)

        self.assertEqual(final_text_from_response_items(result.response_items), "core resumed")
        message_items = [item for item in request_bodies[0]["input"] if item.get("type") == "message"]
        _assert_message_texts_in_order(
            self,
            message_items,
            ["previous user", "previous assistant", "continue core"],
        )
        self.assertEqual(rollout_items[-1].content[0].text, "core resumed")

    async def test_core_http_resume_runner_passes_output_schema_to_request(self) -> None:
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
        output_schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "99999999-9999-9999-9999-999999999999"
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
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("continue with schema"),), output_schema=output_schema),
                "continue with schema",
            )

            await run_exec_resume_user_turn_core_http_sampling(
                codex_home,
                config,
                plan,
                ModelClient(session_id="session", thread_id="new-thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                thread_id=thread_id,
                auth="sk-test",
                opener=opener,
            )

        self.assertEqual(request_bodies[0]["text"]["format"]["schema"], output_schema)

    async def test_local_http_resume_runner_uses_reconstructed_model_history(self) -> None:
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
                        "content": [{"type": "input_text", "text": "pre compact"}],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "drop user"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "drop assistant"}],
                    },
                ):
                    file.write(json.dumps({"timestamp": "2025-01-02T03:04:05Z", "type": "response_item", "payload": payload}) + "\n")
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:06Z",
                            "type": "compacted",
                            "payload": {
                                "message": "summary",
                                "replacement_history": [
                                    {
                                        "type": "message",
                                        "role": "user",
                                        "content": [{"type": "input_text", "text": "summary user"}],
                                    },
                                    {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [{"type": "output_text", "text": "summary assistant"}],
                                    },
                                    {
                                        "type": "message",
                                        "role": "user",
                                        "content": [{"type": "input_text", "text": "rolled back user"}],
                                    },
                                    {
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [{"type": "output_text", "text": "rolled back assistant"}],
                                    },
                                ],
                            },
                        }
                    )
                    + "\n"
                )
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:07Z",
                            "type": "event_msg",
                            "payload": {"type": "thread_rolled_back", "num_turns": 1},
                        }
                    )
                    + "\n"
                )

            await run_exec_resume_user_turn_http_sampling(
                codex_home,
                config,
                ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("current prompt"),)), "current prompt"),
                ModelClient(session_id="session", thread_id="new-thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                thread_id=thread_id,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

        message_items = [item for item in request_bodies[0]["input"] if item.get("type") == "message"]
        message_texts = _message_texts(message_items)
        _assert_message_texts_in_order(self, message_items, ["summary user", "summary assistant", "current prompt"])
        self.assertNotIn("pre compact", message_texts)
        self.assertNotIn("rolled back user", message_texts)

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

    async def test_local_http_resume_runner_persists_interrupted_turn_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "77777777-7777-7777-7777-777777777777"
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
            interrupted = UserTurnSamplingResult(
                request_plan=None,
                response_items=(),
                turn_status="interrupted",
            )

            with patch("pycodex.exec.local_runtime.run_exec_user_turn_http_sampling", return_value=interrupted):
                result = await run_exec_resume_user_turn_http_sampling(
                    codex_home,
                    ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/resume")),
                    ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("current"),)), "current"),
                    ModelClient(session_id="session", thread_id="fresh-thread", installation_id="install"),
                    {"base_url": "https://api.example.test/v1"},
                    SimpleNamespace(slug="gpt-test"),
                    thread_id=thread_id,
                    auth="sk-test",
                )

            self.assertIs(result, interrupted)
            items = read_response_items_from_rollout(rollout_path)
            self.assertIn("<turn_aborted>", items[-1].content[0].text)
            events = read_event_msgs_from_rollout(rollout_path)
            self.assertEqual(events[-1].type, "turn_aborted")
            self.assertEqual(events[-1].payload.reason, "interrupted")

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
            _assert_message_texts_in_order(self, message_items, ["previous named", "current named"])
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
            _assert_message_texts_in_order(self, first_messages, ["previous shell", "current shell"])
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
                persisted_types[current_index + 1 : current_index + 5],
                ["function_call", "message", "function_call_output", "message"],
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
        token_count = next(event for event in reversed(result.session_events) if event.type == "token_count")
        self.assertEqual(token_count.payload.info.total_token_usage.input_tokens, 10)

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

    def test_local_http_exec_result_uses_session_token_count_event_when_raw_usage_missing(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            session_events=(
                EventMsg.with_payload(
                    "token_count",
                    TokenCountEvent(
                        info=TokenUsageInfo(
                            total_token_usage=TokenUsage(
                                input_tokens=12,
                                cached_input_tokens=2,
                                output_tokens=8,
                                reasoning_output_tokens=3,
                                total_tokens=20,
                            ),
                            last_token_usage=TokenUsage(
                                input_tokens=12,
                                cached_input_tokens=2,
                                output_tokens=8,
                                reasoning_output_tokens=3,
                                total_tokens=20,
                            ),
                            model_context_window=128000,
                        ),
                    ),
                ),
            ),
        )

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(json_lines[-1]["type"], "turn.completed")
        self.assertEqual(json_lines[-1]["usage"]["input_tokens"], 12)
        self.assertEqual(json_lines[-1]["usage"]["cached_input_tokens"], 2)
        self.assertEqual(json_lines[-1]["usage"]["output_tokens"], 8)
        self.assertEqual(json_lines[-1]["usage"]["reasoning_output_tokens"], 3)

        stderr = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=io.StringIO(),
            stderr=stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertIn("18", stderr.getvalue())
        self.assertIn("tokens used", stderr.getvalue())

    def test_local_http_rollout_interleaves_multiple_client_tool_search_outputs(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            tool_response_items=(
                ResponseItem(type="tool_search_output", call_id="search-1", status="completed", execution="client"),
                ResponseItem(type="tool_search_output", call_id="search-2", status="completed", execution="client"),
            ),
            raw_results=(
                {
                    "output": [
                        {
                            "type": "tool_search_call",
                            "call_id": "search-1",
                            "status": "completed",
                            "execution": "client",
                            "arguments": {"query": "alpha"},
                        },
                        {
                            "type": "tool_search_call",
                            "call_id": "search-2",
                            "status": "completed",
                            "execution": "client",
                            "arguments": {"query": "beta"},
                        },
                    ]
                },
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                },
            ),
        )

        prompt_visible_items = _local_http_prompt_visible_rollout_items(result)

        self.assertEqual(
            [(item.type, item.call_id) for item in prompt_visible_items],
            [
                ("tool_search_call", "search-1"),
                ("tool_search_call", "search-2"),
                ("tool_search_output", "search-1"),
                ("tool_search_output", "search-2"),
                ("message", None),
            ],
        )

    def test_local_http_rollout_removes_orphan_tool_outputs_from_raw_payload(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "function_call_output",
                        "call_id": "orphan-function",
                        "output": "drop",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "orphan-custom",
                        "output": "drop",
                    },
                    {
                        "type": "tool_search_output",
                        "call_id": "orphan-search",
                        "status": "completed",
                        "execution": "client",
                        "tools": [],
                    },
                    {
                        "type": "tool_search_output",
                        "call_id": "server-search",
                        "status": "completed",
                        "execution": "server",
                        "tools": [],
                    },
                    {
                        "type": "tool_search_output",
                        "status": "completed",
                        "execution": "client",
                        "tools": [],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    },
                ]
            },
        )

        prompt_visible_items = _local_http_prompt_visible_rollout_items(result)

        self.assertEqual(
            [(item.type, item.call_id) for item in prompt_visible_items],
            [
                ("tool_search_output", "server-search"),
                ("tool_search_output", None),
                ("message", None),
            ],
        )

    def test_local_http_rollout_inserts_missing_output_for_local_shell_call(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "local_shell_call",
                        "call_id": "shell-1",
                        "status": "completed",
                        "action": {
                            "type": "exec",
                            "command": ["pwd"],
                        },
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    },
                ]
            },
        )

        prompt_visible_items = _local_http_prompt_visible_rollout_items(result)

        self.assertEqual(
            [(item.type, item.call_id) for item in prompt_visible_items],
            [
                ("local_shell_call", "shell-1"),
                ("function_call_output", "shell-1"),
                ("message", None),
            ],
        )
        self.assertEqual(prompt_visible_items[1].output.to_json(), "aborted")

        timeline_items = tool_timeline_items_from_local_http_exec_result(
            result,
            JsonEventProcessor(),
            config=ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project")),
        )
        self.assertEqual(
            [(item.id, item.type, item.payload["command"], item.payload["status"]) for item in timeline_items],
            [
                ("shell-1", "command_execution", "pwd", "in_progress"),
                ("shell-1", "command_execution", "pwd", "completed"),
            ],
        )
        self.assertEqual(timeline_items[-1].payload["aggregated_output"], "aborted")

    def test_local_http_rollout_prefers_raw_response_items_for_persistence(self) -> None:
        display_item = SimpleNamespace(content=[SimpleNamespace(text="display only")])
        result = SimpleNamespace(
            response_items=(display_item,),
            tool_response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "persisted"}],
                    }
                ]
            },
        )

        payloads = _local_http_response_rollout_payloads(result)

        self.assertEqual(payloads[0]["type"], "message")
        self.assertEqual(payloads[0]["role"], "assistant")
        self.assertEqual(payloads[0]["content"][0]["text"], "persisted")

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
        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor(), config=config)
        self.assertEqual(
            [(item.id, item.type, item.payload["command"], item.payload["cwd"], item.payload["status"]) for item in timeline_items],
            [
                ("call-1", "command_execution", "pwd", "C:/work/project", "in_progress"),
                ("call-1", "command_execution", "pwd", "C:/work/project", "completed"),
                ("call-2", "command_execution", "pwd", "C:/work/project", "in_progress"),
                ("call-2", "command_execution", "pwd", "C:/work/project", "completed"),
            ],
        )
        self.assertEqual([item.payload["aggregated_output"] for item in timeline_items], ["", "C:/work/project", "", "C:/work/project"])
        self.assertEqual(
            [item.payload["command_actions"] for item in timeline_items],
            [
                [{"type": "unknown", "command": "pwd"}],
                [{"type": "unknown", "command": "pwd"}],
                [{"type": "unknown", "command": "pwd"}],
                [{"type": "unknown", "command": "pwd"}],
            ],
        )
        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, config=config, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        tool_events = [
            line["item"]
            for line in json_lines
            if line["type"] == "item.completed" and line["item"]["type"] == "command_execution"
        ]
        self.assertEqual(
            [(item["id"], item["command"], item["cwd"], item["source"], item["status"]) for item in tool_events],
            [
                ("call-1", "pwd", "C:/work/project", "agent", "in_progress"),
                ("call-1", "pwd", "C:/work/project", "agent", "completed"),
                ("call-2", "pwd", "C:/work/project", "agent", "in_progress"),
                ("call-2", "pwd", "C:/work/project", "agent", "completed"),
            ],
        )
        self.assertEqual([item["aggregated_output"] for item in tool_events], ["", "C:/work/project", "", "C:/work/project"])
        self.assertEqual(tool_events[0]["command_actions"], [{"type": "unknown", "command": "pwd"}])

    def test_local_http_tool_timeline_uses_response_item_calls_when_raw_payload_is_absent(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(
                ResponseItem.function_call(
                    "exec_command",
                    json.dumps({"cmd": "pwd"}),
                    "call-history",
                ),
            ),
            raw_tool_output_items=(
                {
                    "type": "function_call_output",
                    "call_id": "call-history",
                    "name": "exec_command",
                    "output": "C:/work/project\n",
                    "success": True,
                },
            ),
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))

        tool_call_items = tool_call_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual(len(tool_call_items), 1)
        self.assertEqual(tool_call_items[0].payload["tool"], "exec_command")

        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor(), config=config)
        self.assertEqual(
            [(item.id, item.type, item.payload["command"], item.payload["status"]) for item in timeline_items],
            [
                ("call-history", "command_execution", "pwd", "in_progress"),
                ("call-history", "command_execution", "pwd", "completed"),
            ],
        )
        self.assertEqual(timeline_items[-1].payload["aggregated_output"], "C:/work/project")

    def test_local_http_tool_timeline_uses_response_item_outputs_when_raw_payload_is_absent(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(
                ResponseItem.function_call(
                    "exec_command",
                    json.dumps({"cmd": "pwd"}),
                    "call-history",
                ),
                ResponseItem(type="function_call_output", call_id="call-history", output="C:/work/project\n"),
            ),
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))

        tool_output_items = tool_output_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual(len(tool_output_items), 1)
        self.assertEqual(tool_output_items[0].payload["result"], "C:/work/project\n")
        self.assertEqual(tool_output_items[0].payload["status"], "completed")

        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor(), config=config)
        self.assertEqual(
            [(item.id, item.type, item.payload["command"], item.payload["status"]) for item in timeline_items],
            [
                ("call-history", "command_execution", "pwd", "in_progress"),
                ("call-history", "command_execution", "pwd", "completed"),
            ],
        )
        self.assertEqual(timeline_items[-1].payload["aggregated_output"], "C:/work/project")

    def test_local_http_tool_timeline_drops_orphan_function_and_custom_outputs(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "function_call_output",
                        "call_id": "orphan-function",
                        "output": "drop",
                    },
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "orphan-custom",
                        "output": "drop",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "",
                        "output": "failed to parse tool arguments",
                    },
                ]
            },
        )

        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor())

        self.assertEqual(len(timeline_items), 1)
        self.assertEqual(timeline_items[0].type, "mcp_tool_call")
        self.assertEqual(timeline_items[0].payload["call_id"], "")
        self.assertEqual(timeline_items[0].payload["result"], "failed to parse tool arguments")

    def test_local_http_tool_timeline_maps_local_shell_call_to_command_execution(self) -> None:
        local_shell_call = ResponseItem.from_mapping(
            {
                "type": "local_shell_call",
                "call_id": "shell-history",
                "status": "completed",
                "action": {
                    "type": "exec",
                    "command": ["pwd"],
                    "working_directory": "C:/work/project",
                },
            }
        )
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(
                local_shell_call,
                ResponseItem(type="function_call_output", call_id="shell-history", output="C:/work/project\n"),
            ),
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/fallback"))

        tool_call_items = tool_call_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual(tool_call_items, ())

        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor(), config=config)
        self.assertEqual(
            [(item.id, item.type, item.payload["command"], item.payload["cwd"], item.payload["status"]) for item in timeline_items],
            [
                ("shell-history", "command_execution", "pwd", "C:/work/project", "in_progress"),
                ("shell-history", "command_execution", "pwd", "C:/work/project", "completed"),
            ],
        )
        self.assertEqual(timeline_items[-1].payload["aggregated_output"], "C:/work/project")
        self.assertEqual(timeline_items[0].payload["command_actions"], [{"type": "unknown", "command": "pwd"}])

    async def test_local_http_exec_shell_tool_loop_continues_by_default_until_no_tool_calls(self) -> None:
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
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 3)
        self.assertEqual(len(result.raw_tool_output_items), 2)

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

    def test_local_http_reasoning_texts_skip_raw_reasoning_content_by_default(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "public summary"}],
                        "content": [
                            {"type": "reasoning_text", "text": "hidden raw chain"},
                            {"type": "text", "text": "visible note"},
                        ],
                    }
                ]
            },
        )

        self.assertEqual(
            reasoning_texts_from_local_http_exec_result(result),
            ("public summary",),
        )

    def test_local_http_reasoning_texts_accept_app_server_style_fields(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "reasoning",
                        "summary_text": ["public summary"],
                        "raw_content": [
                            {"type": "reasoning_text", "text": "hidden raw chain"},
                            "visible raw note",
                        ],
                    }
                ]
            },
        )

        self.assertEqual(
            reasoning_texts_from_local_http_exec_result(result),
            ("public summary",),
        )

    def test_local_http_human_reasoning_uses_raw_content_when_enabled(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "public summary"}],
                        "content": [
                            {"type": "reasoning_text", "text": "hidden raw chain"},
                            {"type": "text", "text": "visible raw note"},
                        ],
                    }
                ]
            },
        )

        default_stderr = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            stdout=io.StringIO(),
            stderr=default_stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertIn("public summary", default_stderr.getvalue())
        self.assertNotIn("hidden raw chain", default_stderr.getvalue())
        self.assertNotIn("visible raw note", default_stderr.getvalue())

        raw_processor = HumanEventProcessor()
        raw_processor.show_raw_agent_reasoning = True
        raw_stderr = io.StringIO()
        emit_local_http_exec_result(
            raw_processor,
            result,
            stdout=io.StringIO(),
            stderr=raw_stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertIn("hidden raw chain", raw_stderr.getvalue())
        self.assertIn("visible raw note", raw_stderr.getvalue())
        self.assertNotIn("public summary", raw_stderr.getvalue())

        config_stderr = io.StringIO()
        emit_local_http_exec_result(
            HumanEventProcessor(),
            result,
            config=ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path("C:/work/project"),
                show_raw_agent_reasoning=True,
            ),
            stdout=io.StringIO(),
            stderr=config_stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=False,
        )
        self.assertIn("hidden raw chain", config_stderr.getvalue())
        self.assertIn("visible raw note", config_stderr.getvalue())

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
        emit_local_http_exec_result(JsonEventProcessor(), result, config=config, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        self.assertEqual(
            [line["type"] for line in json_lines],
            ["turn.started", "item.completed", "item.completed", "turn.completed"],
        )
        self.assertEqual(json_lines[1]["item"]["type"], "command_execution")
        self.assertEqual(json_lines[1]["item"]["id"], "call-1")
        self.assertEqual(json_lines[1]["item"]["command"], "pwd")
        self.assertEqual(json_lines[1]["item"]["cwd"], "C:/work/project")
        self.assertEqual(json_lines[1]["item"]["source"], "agent")
        self.assertEqual(json_lines[1]["item"]["status"], "in_progress")
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
        self.assertIn("Wall time:", outputs[0]["output"])
        self.assertIn("Process exited with code 0", outputs[0]["output"])
        self.assertIn("Original token count:", outputs[0]["output"])
        self.assertIn("Output:", outputs[0]["output"])
        self.assertIn("C:/work/project", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_nonzero_exit_remains_successful_tool_result(self) -> None:
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

        self.assertIs(outputs[0]["success"], True)
        self.assertIn("Process exited with code 7", outputs[0]["output"])
        self.assertIn("nope", outputs[0]["output"])

    def test_local_http_exec_unknown_function_tool_returns_model_visible_error(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "function_call",
                        "name": "existing",
                        "arguments": "{}",
                        "call_id": "unknown-1",
                    }
                ]
            },
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertEqual(
            outputs,
            (
                {
                    "type": "function_call_output",
                    "call_id": "unknown-1",
                    "name": "existing",
                    "output": "unsupported call: existing",
                    "success": False,
                },
            ),
        )

    def test_local_http_exec_unknown_custom_tool_returns_model_visible_error(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "custom_tool_call",
                        "name": "custom_existing",
                        "input": "raw input",
                        "call_id": "custom-unknown-1",
                    }
                ]
            },
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertEqual(outputs[0]["type"], "custom_tool_call_output")
        self.assertEqual(outputs[0]["call_id"], "custom-unknown-1")
        self.assertNotIn("name", outputs[0])
        self.assertEqual(outputs[0]["output"], "unsupported custom tool call: custom_existing")
        self.assertIs(outputs[0]["success"], False)
        tool_response_items = response_items_from_local_http_tool_outputs(outputs)
        self.assertEqual(tool_response_items[0].type, "custom_tool_call_output")
        self.assertIsNone(tool_response_items[0].name)
        self.assertIs(tool_response_items[0].output.success, False)

    def test_local_http_exec_custom_exec_command_payload_is_not_executed(self) -> None:
        result = UserTurnSamplingResult(
            request_plan=None,
            response_items=(),
            raw_result={
                "output": [
                    {
                        "type": "custom_tool_call",
                        "name": "exec_command",
                        "input": "pwd",
                        "call_id": "custom-exec-1",
                    }
                ]
            },
        )
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))

        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("custom exec_command payload must not be executed")

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertEqual(outputs[0]["type"], "custom_tool_call_output")
        self.assertEqual(outputs[0]["call_id"], "custom-exec-1")
        self.assertNotIn("name", outputs[0])
        self.assertEqual(outputs[0]["output"], "tool exec_command invoked with incompatible payload")
        self.assertIs(outputs[0]["success"], False)
        result_with_outputs = replace(
            result,
            tool_response_items=response_items_from_local_http_tool_outputs(outputs),
            raw_tool_output_items=outputs,
        )
        timeline_items = tool_timeline_items_from_local_http_exec_result(result_with_outputs, JsonEventProcessor())
        self.assertEqual([item.type for item in timeline_items], ["mcp_tool_call", "mcp_tool_call"])

    async def test_local_http_exec_shell_tool_nonzero_exit_marks_timeline_failed(self) -> None:
        class Completed:
            returncode = 7
            stdout = ""
            stderr = "nope"

        def fake_runner(_command, **_kwargs):
            return Completed()

        responses = [FakeToolCallResponse(), FakeResponse()]

        def opener(_request):
            return responses.pop(0)

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
        result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            SimpleNamespace(
                slug="gpt-test",
                base_instructions="base",
                supports_reasoning_summaries=False,
                support_verbosity=False,
                service_tier_for_request=lambda tier: tier,
            ),
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
            runner=fake_runner,
        )

        tool_outputs = tool_output_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual(tool_outputs[0].payload["status"], "failed")
        self.assertIn("Process exited with code 7", tool_outputs[0].payload["result"])

        json_stdout = io.StringIO()
        emit_local_http_exec_result(JsonEventProcessor(), result, stdout=json_stdout)
        json_lines = [json.loads(line) for line in json_stdout.getvalue().splitlines()]
        completed_tools = [
            line["item"]
            for line in json_lines
            if line["type"] == "item.completed" and line["item"]["type"] == "command_execution"
        ]
        self.assertEqual(completed_tools[-1]["status"], "failed")

    async def test_local_http_exec_shell_tool_combines_stdout_and_stderr_with_separator(self) -> None:
        class Completed:
            returncode = 1
            stdout = "stdout text"
            stderr = "stderr text"

        def fake_runner(_command, **_kwargs):
            return Completed()

        def opener(_request):
            return FakeToolCallResponse()

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

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner)

        self.assertIn("stdout text\nstderr text", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_timeout_uses_unified_exec_shape(self) -> None:
        def fake_runner(_command, **_kwargs):
            raise subprocess.TimeoutExpired(
                cmd="pwd",
                timeout=2.5,
                output=b"partial stdout",
                stderr=b"partial stderr",
            )

        def opener(_request):
            return FakeToolCallResponse()

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

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner, timeout=2.5)

        self.assertIs(outputs[0]["success"], False)
        self.assertIn("Process exited with code 124", outputs[0]["output"])
        self.assertIn("command timed out after 2500 milliseconds", outputs[0]["output"])
        self.assertIn("partial stdout\npartial stderr", outputs[0]["output"])

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

        self.assertIn("Original token count:", outputs[0]["output"])
        self.assertIn("Output:", outputs[0]["output"])
        self.assertIn("chars truncated", outputs[0]["output"])
        self.assertTrue(outputs[0]["output"].startswith("Wall time: "))

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

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=fake_runner,
        )

        self.assertIn("Total output lines:", outputs[0]["output"])
        self.assertIn("tokens truncated", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_max_output_tokens_uses_token_marker(self) -> None:
        class Completed:
            returncode = 0
            stdout = "alpha beta gamma delta epsilon zeta eta theta"
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

        def opener(_request):
            return FakeExecCommandToolCallResponse()

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

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=fake_runner,
        )

        self.assertIn("tokens truncated", outputs[0]["output"])
        self.assertNotIn("chars truncated", outputs[0]["output"])

    async def test_local_http_exec_command_max_output_tokens_zero_truncates_all_output(self) -> None:
        class Completed:
            returncode = 0
            stdout = "alpha beta gamma"
            stderr = ""

        def fake_runner(_command, **_kwargs):
            return Completed()

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
            opener=lambda _request: FakeRawExecCommandToolCallResponse({"cmd": "pwd", "max_output_tokens": 0}),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=fake_runner,
        )

        self.assertIn("tokens truncated", outputs[0]["output"])
        self.assertNotIn("alpha beta gamma", outputs[0]["output"])

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

    async def test_local_http_exec_shell_tool_rejects_login_when_disabled_by_config(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not execute disallowed login shell")

        def opener(_request):
            return FakeToolCallWithLoginResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            allow_login_shell=False,
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
        self.assertIn("login shell is disabled by config", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_resolves_omitted_login_from_config(self) -> None:
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
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            allow_login_shell=False,
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
        self.assertFalse(seen["login"])
        self.assertIn("ok", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_output_requires_approval_before_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when approval is required")

        def opener(_request):
            return FakeDangerousToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
            exec_permission_approvals_enabled=True,
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
        self.assertIn("rm -rf /important/data", outputs[0]["output"])
        timeline_items = tool_timeline_items_from_local_http_exec_result(
            replace(result, raw_tool_output_items=outputs),
            JsonEventProcessor(),
        )
        self.assertEqual([(item.type, item.payload["status"]) for item in timeline_items], [
            ("command_execution", "in_progress"),
            ("command_execution", "declined"),
        ])
        self.assertEqual(timeline_items[1].payload["command"], "rm -rf /important/data")

    def test_local_http_approval_outputs_render_granular_label_like_rust_display(self) -> None:
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=False,
            request_permissions=True,
            mcp_elicitations=False,
        )
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=granular,
        )
        invocation = LocalHttpShellInvocation(command="echo hi")

        outputs = [
            local_http_shell_tool_approval_required_output(invocation, config),
            local_http_shell_tool_forbidden_output(invocation, config, "blocked"),
            local_http_apply_patch_approval_required_output(config),
            local_http_write_stdin_approval_required_output(config),
        ]

        for output in outputs:
            self.assertIn("approval_policy: granular", output)
            self.assertNotIn("GranularApprovalConfig", output)

    async def test_local_http_exec_shell_tool_rejects_forbidden_exec_policy_before_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when exec policy forbids the command")

        def opener(_request):
            return FakeDangerousToolCallResponse()

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
        self.assertIn("exit_code: forbidden", outputs[0]["output"])
        self.assertIn("approval_policy: never", outputs[0]["output"])
        self.assertIn("rejected: blocked by policy", outputs[0]["output"])
        self.assertIn("command:\nrm -rf /important/data", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_on_failure_executes_skip_requirement(self) -> None:
        class Completed:
            returncode = 0
            stdout = "ok\n"
            stderr = ""

        def fake_runner(command, **_kwargs):
            self.assertEqual(command, "pwd")
            return Completed()

        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_FAILURE,
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

        self.assertTrue(outputs[0]["success"])
        self.assertIn("ok", outputs[0]["output"])
        self.assertNotIn("approval_required", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_applies_configured_exec_policy_prefix_rules(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when configured policy prompts")

        def opener(_request):
            return FakeToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
            exec_policy_rules=(ExecPolicyPrefixRule.new(["pwd"], "prompt", "inspect cwd first"),),
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

        with patch(
            "pycodex.exec.local_runtime.default_user_shell",
            return_value=Shell(ShellType.POWERSHELL, "pwsh.exe"),
        ):
            outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertFalse(outputs[0]["success"])
        self.assertIn("exit_code: approval_required", outputs[0]["output"])
        self.assertIn("reason: `pwsh.exe -Command pwd` requires approval: inspect cwd first", outputs[0]["output"])
        self.assertNotIn("proposed_execpolicy_amendment", outputs[0]["output"])

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
            exec_permission_approvals_enabled=True,
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

    def test_local_http_shell_tool_approval_output_includes_requirement_reason(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
            exec_permission_approvals_enabled=True,
        )

        output = local_http_shell_tool_approval_required_output(
            LocalHttpShellInvocation("cargo install ripgrep"),
            config,
            exec_approval_requirement=ExecApprovalRequirement.needs_approval(
                reason="`cargo install ripgrep` requires approval by policy",
            ),
        )

        self.assertIn("exit_code: approval_required", output)
        self.assertIn("reason: `cargo install ripgrep` requires approval by policy", output)
        self.assertIn("command:\ncargo install ripgrep", output)

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

    async def test_local_http_exec_shell_tool_resolves_relative_additional_permissions_against_workdir(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when approval is required")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "nested"
            nested.mkdir()

            def opener(_request):
                return FakeToolCallWithRelativeAdditionalPermissionsWorkdirResponse()

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
                approval_policy=AskForApproval.ON_REQUEST,
                exec_permission_approvals_enabled=True,
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

        match = re.search(r"additional_permissions: (.+)\n", outputs[0]["output"])
        self.assertIsNotNone(match)
        additional_permissions = json.loads(match.group(1))
        self.assertEqual(additional_permissions["file_system"]["write"], [str(nested)])

    async def test_local_http_exec_shell_tool_approval_merges_partial_grant_with_new_permissions(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called before approval")

        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_root = Path(first_dir)
            second_root = Path(second_dir)

            class PartialGrantResponse:
                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "output": [
                                {
                                    "type": "function_call",
                                    "name": "shell",
                                    "arguments": json.dumps(
                                        {
                                            "command": "pwd",
                                            "sandbox_permissions": "with_additional_permissions",
                                            "additional_permissions": {
                                                "file_system": {"write": [str(second_root)]}
                                            },
                                        }
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

            def opener(_request):
                return PartialGrantResponse()

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path("C:/work/project"),
                approval_policy=AskForApproval.ON_REQUEST,
                exec_permission_approvals_enabled=True,
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
            granted_permissions = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    (
                        FileSystemSandboxEntry(
                            FileSystemPath.explicit_path(first_root),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )
            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                runner=rejecting_runner,
                granted_permissions=granted_permissions,
            )

        self.assertFalse(outputs[0]["success"])
        self.assertIn("approval_required", outputs[0]["output"])
        match = re.search(r"additional_permissions: (.+)\n", outputs[0]["output"])
        self.assertIsNotNone(match)
        additional_permissions = json.loads(match.group(1))
        self.assertEqual(
            sorted(additional_permissions["file_system"]["write"]),
            sorted([str(first_root), str(second_root)]),
        )

    async def test_local_http_exec_shell_tool_runs_with_granted_additional_permissions(self) -> None:
        runner_calls = []

        def runner(command, **kwargs):
            runner_calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="allowed\n", stderr="")

        def opener(_request):
            return FakeToolCallWithApprovalMetadataResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            exec_permission_approvals_enabled=True,
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
            runner=runner,
            granted_permissions=AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

        self.assertEqual([call[0] for call in runner_calls], ["pwd"])
        self.assertTrue(outputs[0]["success"])
        self.assertIn("allowed", outputs[0]["output"])
        self.assertNotIn("permission_request_unsupported", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_runs_with_request_permissions_preapproved_grant(self) -> None:
        runner_calls = []

        def runner(command, **kwargs):
            runner_calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="preapproved\n", stderr="")

        def opener(_request):
            return FakeToolCallWithApprovalMetadataResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            exec_permission_approvals_enabled=False,
            request_permissions_tool_enabled=True,
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
            runner=runner,
            granted_permissions=AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

        self.assertEqual([call[0] for call in runner_calls], ["pwd"])
        self.assertTrue(outputs[0]["success"])
        self.assertIn("preapproved", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_rejects_granted_permissions_when_feature_disabled(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not execute when additional permissions feature is disabled")

        def opener(_request):
            return FakeToolCallWithApprovalMetadataResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            exec_permission_approvals_enabled=False,
            request_permissions_tool_enabled=False,
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
            runner=rejecting_runner,
            granted_permissions=AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

        self.assertFalse(outputs[0]["success"])
        self.assertIn("permission_request_unsupported", outputs[0]["output"])
        self.assertIn("additional permissions are disabled", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_runs_with_granted_relative_workdir_permissions(self) -> None:
        runner_calls = []

        def runner(command, **kwargs):
            runner_calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="allowed\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "nested"
            nested.mkdir()

            def opener(_request):
                return FakeToolCallWithRelativeAdditionalPermissionsWorkdirResponse()

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
                approval_policy=AskForApproval.ON_REQUEST,
                exec_permission_approvals_enabled=True,
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

            granted_permissions = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    (
                        FileSystemSandboxEntry(
                            FileSystemPath.explicit_path(nested),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )
            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                runner=runner,
                granted_permissions=granted_permissions,
            )

        self.assertEqual([call[0] for call in runner_calls], ["pwd"])
        self.assertEqual(runner_calls[0][1]["cwd"], str(nested))
        self.assertTrue(outputs[0]["success"])
        self.assertIn("allowed", outputs[0]["output"])
        self.assertNotIn("approval_required", outputs[0]["output"])

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

        empty_profile_object = await run_with(lambda _request: FakeToolCallWithEmptyObjectAdditionalPermissionsResponse())
        self.assertFalse(empty_profile_object[0]["success"])
        self.assertIn("permission_request_invalid", empty_profile_object[0]["output"])
        self.assertIn("must include at least one requested permission", empty_profile_object[0]["output"])

        null_profile = await run_with(lambda _request: FakeToolCallWithNullAdditionalPermissionsResponse())
        self.assertFalse(null_profile[0]["success"])
        self.assertIn("permission_request_invalid", null_profile[0]["output"])
        self.assertIn("missing `additional_permissions`", null_profile[0]["output"])

        invalid_profile_type = await run_with(
            lambda _request: FakeToolCallWithInvalidAdditionalPermissionsResponse()
        )
        self.assertFalse(invalid_profile_type[0]["success"])
        self.assertIn("permission_request_invalid", invalid_profile_type[0]["output"])
        self.assertIn("additional_permissions` must be an object mapping permissions", invalid_profile_type[0]["output"])

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
        self.assertIn('proposed_execpolicy_amendment: {"command":["python","-m"]}', outputs[0]["output"])
        self.assertIn("command:\npython -m pytest", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_approval_output_skips_heredoc_prefix_rule_amendment(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not be called when approval is required")

        def opener(_request):
            return FakeToolCallWithHeredocPrefixRuleResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
            exec_permission_approvals_enabled=True,
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

        self.assertIn('prefix_rule: ["python3","script.py"]', outputs[0]["output"])
        self.assertNotIn("proposed_execpolicy_amendment:", outputs[0]["output"])
        self.assertIn("command:\npython3 <<'PY'\nprint('hello')\nPY", outputs[0]["output"])

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
            self.assertNotIn("name", outputs[0])
            self.assertIs(outputs[0]["success"], True)
            self.assertIn("Success. Updated the following files:", outputs[0]["output"])
            self.assertIn("A ", outputs[0]["output"])
            self.assertIn("created.txt", outputs[0]["output"])
            self.assertEqual((Path(tmpdir) / "created.txt").read_text(encoding="utf-8"), "hello\n")
            tool_response_items = response_items_from_local_http_tool_outputs(outputs)
            self.assertEqual(tool_response_items[0].type, "custom_tool_call_output")
            self.assertIsNone(tool_response_items[0].name)
            self.assertIn(Path("created.txt"), outputs[0]["internal_output"]["changes"])
            result_with_outputs = replace(
                result,
                tool_response_items=tool_response_items,
                raw_tool_output_items=outputs,
            )
            timeline_items = tool_timeline_items_from_local_http_exec_result(
                result_with_outputs,
                JsonEventProcessor(),
            )
            self.assertEqual([item.type for item in timeline_items], ["file_change", "file_change"])
            self.assertEqual(
                [item.payload["status"] for item in timeline_items],
                ["in_progress", "completed"],
            )
            self.assertEqual(
                timeline_items[0].payload["changes"],
                [{"path": "created.txt", "kind": "add"}],
            )
            self.assertIs(timeline_items[0].payload["auto_approved"], True)
            self.assertIn("created.txt", timeline_items[1].payload["stdout"])
            self.assertEqual(timeline_items[1].payload["stderr"], "")
            json_stdout = io.StringIO()
            emit_local_http_exec_result(JsonEventProcessor(), result_with_outputs, stdout=json_stdout)
            patch_events = [
                line["item"]
                for line in (json.loads(raw) for raw in json_stdout.getvalue().splitlines())
                if line["type"] == "item.completed"
                and line["item"]["type"] == "file_change"
            ]
            self.assertEqual([event["status"] for event in patch_events], ["in_progress", "completed"])

    async def test_local_http_exec_apply_patch_tool_missing_patch_returns_model_visible_error(self) -> None:
        class EmptyApplyPatchResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "custom_tool_call",
                                "name": "apply_patch",
                                "input": "",
                                "call_id": "patch-empty",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("patch"),)),
            "patch",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=lambda _request: EmptyApplyPatchResponse(),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertEqual(outputs[0]["type"], "custom_tool_call_output")
        self.assertEqual(outputs[0]["call_id"], "patch-empty")
        self.assertEqual(outputs[0]["output"], "apply_patch handler received non-apply_patch input")
        self.assertIs(outputs[0]["success"], False)
        result_with_outputs = replace(
            result,
            tool_response_items=response_items_from_local_http_tool_outputs(outputs),
            raw_tool_output_items=outputs,
        )
        timeline_items = tool_timeline_items_from_local_http_exec_result(result_with_outputs, JsonEventProcessor())
        self.assertEqual([item.type for item in timeline_items], ["mcp_tool_call", "mcp_tool_call"])

    async def test_local_http_exec_apply_patch_tool_invalid_patch_returns_verification_error(self) -> None:
        def opener(_request):
            return FakeApplyPatchToolCallResponse("*** Begin Patch\n*** Not A Real Hunk\n*** End Patch\n")

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("patch"),)),
            "patch",
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
        self.assertIn("apply_patch verification failed:", outputs[0]["output"])
        self.assertIs(outputs[0]["success"], False)
        result_with_outputs = replace(
            result,
            tool_response_items=response_items_from_local_http_tool_outputs(outputs),
            raw_tool_output_items=outputs,
        )
        timeline_items = tool_timeline_items_from_local_http_exec_result(result_with_outputs, JsonEventProcessor())
        self.assertEqual([item.type for item in timeline_items], ["mcp_tool_call", "mcp_tool_call"])

    def test_local_http_exec_function_apply_patch_payload_is_not_executed(self) -> None:
        patch = "*** Begin Patch\n*** Add File: created.txt\n+hello\n*** End Patch\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = UserTurnSamplingResult(
                request_plan=None,
                response_items=(),
                raw_result={
                    "output": [
                        {
                            "type": "function_call",
                            "name": "apply_patch",
                            "arguments": json.dumps({"patch": patch}),
                            "call_id": "function-patch-1",
                        }
                    ]
                },
            )
            config = ExecSessionConfig(model=None, model_provider_id=None, cwd=root)

            outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

            self.assertFalse((root / "created.txt").exists())
            self.assertEqual(outputs[0]["type"], "function_call_output")
            self.assertEqual(outputs[0]["call_id"], "function-patch-1")
            self.assertEqual(outputs[0]["name"], "apply_patch")
            self.assertEqual(outputs[0]["output"], "tool apply_patch invoked with incompatible payload")
            self.assertIs(outputs[0]["success"], False)
            result_with_outputs = replace(
                result,
                tool_response_items=response_items_from_local_http_tool_outputs(outputs),
                raw_tool_output_items=outputs,
            )
            timeline_items = tool_timeline_items_from_local_http_exec_result(result_with_outputs, JsonEventProcessor())
            self.assertEqual([item.type for item in timeline_items], ["mcp_tool_call", "mcp_tool_call"])

    async def test_local_http_exec_command_intercepts_apply_patch_heredoc_before_runner(self) -> None:
        patch_command = (
            "apply_patch <<'PATCH'\n"
            "*** Begin Patch\n"
            "*** Add File: shell-created.txt\n"
            "+from shell wrapper\n"
            "*** End Patch\n"
            "PATCH"
        )

        class ShellApplyPatchResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "exec_command",
                                "arguments": json.dumps({"cmd": patch_command}),
                                "call_id": "call-patch",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("apply_patch shell wrappers must be intercepted before shell execution")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("patch through shell"),)),
                "patch through shell",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=lambda _request: ShellApplyPatchResponse(),
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

            self.assertEqual(outputs[0]["type"], "function_call_output")
            self.assertEqual(outputs[0]["call_id"], "call-patch")
            self.assertIs(outputs[0]["success"], True)
            self.assertIn("Success. Updated the following files:", outputs[0]["output"])
            self.assertEqual((root / "shell-created.txt").read_text(encoding="utf-8"), "from shell wrapper\n")
            self.assertIn(Path("shell-created.txt"), outputs[0]["internal_output"]["changes"])
            result_with_outputs = replace(
                result,
                tool_response_items=response_items_from_local_http_tool_outputs(outputs),
                raw_tool_output_items=outputs,
            )
            timeline_items = tool_timeline_items_from_local_http_exec_result(
                result_with_outputs,
                JsonEventProcessor(),
            )
            self.assertEqual([item.type for item in timeline_items], ["file_change", "file_change"])
            self.assertEqual([item.payload["status"] for item in timeline_items], ["in_progress", "completed"])
            self.assertEqual(timeline_items[0].payload["changes"], [{"path": "shell-created.txt", "kind": "add"}])
            self.assertIs(timeline_items[0].payload["auto_approved"], True)
            self.assertIn("shell-created.txt", timeline_items[1].payload["stdout"])
            self.assertEqual(timeline_items[1].payload["stderr"], "")

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
            changes = outputs[0]["internal_output"]["changes"]
            self.assertIn("-old\n+new\n", changes[Path("old.txt")].unified_diff)
            self.assertEqual(changes[Path("move.txt")].move_path, Path("moved.txt"))
            self.assertEqual((root / "old.txt").read_text(encoding="utf-8"), "new\n")
            self.assertFalse((root / "delete.txt").exists())
            self.assertFalse((root / "move.txt").exists())
            self.assertEqual((root / "moved.txt").read_text(encoding="utf-8"), "moved\n")
            result_with_outputs = replace(
                result,
                tool_response_items=response_items_from_local_http_tool_outputs(outputs),
                raw_tool_output_items=outputs,
            )
            timeline_items = tool_timeline_items_from_local_http_exec_result(
                result_with_outputs,
                JsonEventProcessor(),
            )
            self.assertEqual([item.type for item in timeline_items], ["file_change", "file_change"])
            self.assertEqual(
                timeline_items[0].payload["changes"],
                [
                    {"path": "old.txt", "kind": "update"},
                    {"path": "delete.txt", "kind": "delete"},
                    {"path": "move.txt", "kind": "update"},
                ],
            )
            self.assertEqual([item.payload["status"] for item in timeline_items], ["in_progress", "completed"])

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

            self.assertNotIn("name", outputs[0])
            self.assertIs(outputs[0]["success"], False)
            self.assertIn("approval_required", outputs[0]["output"])
            self.assertFalse((Path(tmpdir) / "created.txt").exists())
            result_with_outputs = replace(
                result,
                tool_response_items=response_items_from_local_http_tool_outputs(outputs),
                raw_tool_output_items=outputs,
            )
            timeline_items = tool_timeline_items_from_local_http_exec_result(
                result_with_outputs,
                JsonEventProcessor(),
            )
            self.assertEqual([item.type for item in timeline_items], ["file_change", "file_change"])
            self.assertEqual(
                [item.payload["status"] for item in timeline_items],
                ["in_progress", "declined"],
            )
            self.assertEqual(
                timeline_items[0].payload["changes"],
                [{"path": "created.txt", "kind": "add"}],
            )
            self.assertIs(timeline_items[0].payload["auto_approved"], False)
            self.assertEqual(timeline_items[1].payload["stdout"], "")
            self.assertIn("approval_required", timeline_items[1].payload["stderr"])
            json_stdout = io.StringIO()
            emit_local_http_exec_result(JsonEventProcessor(), result_with_outputs, stdout=json_stdout)
            patch_events = [
                line["item"]
                for line in (json.loads(raw) for raw in json_stdout.getvalue().splitlines())
                if line["type"] == "item.completed"
                and line["item"]["type"] == "file_change"
            ]
            self.assertEqual([event["status"] for event in patch_events], ["in_progress", "declined"])

    async def test_local_http_exec_request_permissions_tool_output_helper_uses_rust_cancel_error(self) -> None:
        def opener(_request):
            return FakeRequestPermissionsToolCallResponse()

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
            exec_permission_approvals_enabled=True,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request network"),)),
            "request network",
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
        self.assertEqual(outputs[0]["call_id"], "permissions-1")
        self.assertEqual(outputs[0]["name"], "request_permissions")
        self.assertIs(outputs[0]["success"], False)
        self.assertEqual(
            outputs[0]["output"],
            "request_permissions was cancelled before receiving a response",
        )

    async def test_local_http_exec_request_permissions_tool_output_helper_auto_denies_when_approval_never(self) -> None:
        def opener(_request):
            return FakeRequestPermissionsToolCallResponse()

        def request_permissions_callback(_parent_ctx, _call_id, _args, _cwd, _cancel_token):
            raise AssertionError("approval never should not invoke request_permissions callback")

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            request_permissions_callback=request_permissions_callback,
            request_permissions_tool_enabled=True,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request network"),)),
            "request network",
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
        self.assertEqual(
            json.loads(outputs[0]["output"]),
            {
                "permissions": {},
                "scope": "turn",
            },
        )

    async def test_local_http_exec_request_permissions_tool_output_helper_serializes_grant_response(self) -> None:
        seen = {}

        def opener(_request):
            return FakeRequestPermissionsToolCallResponse()

        def request_permissions_callback(parent_ctx, call_id, args, cwd, cancel_token):
            seen["parent_ctx"] = parent_ctx
            seen["call_id"] = call_id
            seen["args"] = args
            seen["cwd"] = cwd
            seen["cancel_token"] = cancel_token
            return RequestPermissionsResponse(
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                scope=PermissionGrantScope.TURN,
            )

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
            request_permissions_callback=request_permissions_callback,
            request_permissions_tool_enabled=True,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request network"),)),
            "request network",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertIsNone(seen["parent_ctx"])
        self.assertEqual(seen["call_id"], "permissions-1")
        self.assertEqual(seen["cwd"], Path("C:/work/project"))
        self.assertIsNone(seen["cancel_token"])
        self.assertEqual(seen["args"].permissions.network, NetworkPermissions(enabled=True))
        self.assertIs(outputs[0]["success"], True)
        self.assertEqual(
            json.loads(outputs[0]["output"]),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
            },
        )

    async def test_local_http_exec_request_permissions_tool_output_helper_rejects_empty_permissions(self) -> None:
        def opener(_request):
            return FakeRequestPermissionsToolCallResponse({"permissions": {}})

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request nothing"),)),
            "request nothing",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertIs(outputs[0]["success"], False)
        self.assertEqual(outputs[0]["output"], "request_permissions requires at least one permission")

    async def test_local_http_exec_request_permissions_tool_output_helper_rejects_bad_arguments(self) -> None:
        def opener(_request):
            return FakeRequestPermissionsToolCallResponse("{")

        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request bad args"),)),
            "request bad args",
        )
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertIs(outputs[0]["success"], False)
        self.assertIn("failed to parse function arguments:", outputs[0]["output"])

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
        self.assertIn("Process exited with code 0", output_items[0]["output"])

    async def test_local_http_exec_apply_patch_followup_request_omits_custom_output_name(self) -> None:
        request_bodies = []

        def first_opener(_request):
            return FakeApplyPatchToolCallResponse()

        def followup_opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
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
            tool_outputs = shell_tool_outputs_from_local_http_exec_result(previous, config)

            tool_response_items = response_items_from_local_http_tool_outputs(tool_outputs)
            self.assertEqual(tool_response_items[0].type, "custom_tool_call_output")
            self.assertIsNone(tool_response_items[0].name)
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
            output_items = [item for item in input_items if item["type"] == "custom_tool_call_output"]
            self.assertEqual(len(output_items), 1)
            self.assertEqual(output_items[0]["call_id"], "patch-1")
            self.assertNotIn("name", output_items[0])
            self.assertIs(output_items[0]["success"], True)
            self.assertIn("Success. Updated the following files:", output_items[0]["output"])
            self.assertIn("created.txt", output_items[0]["output"])

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
        output_schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),), output_schema=output_schema),
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
        self.assertEqual(
            request_bodies[0]["text"]["format"]["schema"]["properties"]["summary"]["type"],
            "string",
        )
        self.assertEqual(
            request_bodies[1]["text"]["format"]["schema"]["properties"]["summary"]["type"],
            "string",
        )
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

    async def test_local_http_exec_shell_tool_loop_groups_same_turn_tool_outputs(self) -> None:
        request_bodies = []

        class Completed:
            returncode = 0
            stdout = "shell output\n"
            stderr = ""

        class ThreeToolCallResponse:
            def read(self) -> bytes:
                output = []
                for call_id in ("call-1", "call-2", "call-3"):
                    output.append(
                        {
                            "type": "function_call",
                            "name": "shell",
                            "arguments": "{\"command\":\"echo shell output\"}",
                            "call_id": call_id,
                        }
                    )
                return json.dumps({"output": output}).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def fake_runner(command, **_kwargs):
            self.assertEqual(command, "echo shell output")
            return Completed()

        responses = [ThreeToolCallResponse(), FakeResponse()]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("run three"),)), "run three")

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
        followup_input = request_bodies[1]["input"]
        function_calls = [
            (index, item)
            for index, item in enumerate(followup_input)
            if item["type"] == "function_call"
        ]
        function_call_outputs = [
            (index, item)
            for index, item in enumerate(followup_input)
            if item["type"] == "function_call_output"
        ]

        self.assertEqual(len(function_calls), 3)
        self.assertEqual(len(function_call_outputs), 3)
        for call_index, _call in function_calls:
            for output_index, _output in function_call_outputs:
                self.assertLess(call_index, output_index)
        self.assertEqual(
            [call["call_id"] for _index, call in function_calls],
            [output["call_id"] for _index, output in function_call_outputs],
        )
        self.assertEqual([output["success"] for _index, output in function_call_outputs], [True, True, True])
        self.assertTrue(all("shell output" in output["output"] for _index, output in function_call_outputs))

    async def test_local_http_exec_shell_tool_loop_follows_up_after_unknown_tool_error(self) -> None:
        request_bodies = []

        class UnknownToolResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "existing",
                                "arguments": "{}",
                                "call_id": "unknown-1",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [UnknownToolResponse(), FakeResponse()]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
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
            built_tools=lambda _sess, _turn: ExistingToolRouter(),
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 2)
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(output_items[0]["call_id"], "unknown-1")
        self.assertEqual(output_items[0]["output"], "unsupported call: existing")
        self.assertIs(output_items[0]["success"], False)

    async def test_local_http_exec_shell_tool_loop_omits_custom_output_name_after_unknown_tool_error(self) -> None:
        request_bodies = []

        class UnknownCustomToolResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "custom_tool_call",
                                "name": "custom_existing",
                                "input": "raw input",
                                "call_id": "custom-unknown-1",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [UnknownCustomToolResponse(), FakeResponse()]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
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
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 2)
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "custom_tool_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "custom-unknown-1")
        self.assertNotIn("name", output_items[0])
        self.assertEqual(output_items[0]["output"], "unsupported custom tool call: custom_existing")
        self.assertIs(output_items[0]["success"], False)

    async def test_local_http_exec_view_image_tool_loop_returns_image_output(self) -> None:
        request_bodies = []

        class ViewImageResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "view_image",
                                "arguments": json.dumps({"path": "image.png", "detail": "original"}),
                                "call_id": "image-1",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [ViewImageResponse(), FakeResponse()]

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
                "supports_image_detail_original": True,
                "input_modalities": ("text", "image"),
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "image.png").write_bytes(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            config = ExecSessionConfig(model=None, model_provider_id=None, cwd=root)
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("inspect image"),)),
                "inspect image",
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
            )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 2)
        view_image_tool = next(tool for tool in request_bodies[0]["tools"] if tool["name"] == "view_image")
        self.assertEqual(view_image_tool["parameters"]["properties"]["detail"]["enum"], ["high", "original"])
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(output_items[0]["call_id"], "image-1")
        self.assertIs(output_items[0]["success"], True)
        self.assertEqual(output_items[0]["output"][0]["type"], "input_image")
        self.assertTrue(output_items[0]["output"][0]["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(output_items[0]["output"][0]["detail"], "original")

    async def test_local_http_exec_shell_tool_loop_returns_apply_patch_followup_answer(self) -> None:
        request_bodies = []
        patch = (
            "*** Begin Patch\n"
            "*** Update File: edit.txt\n"
            "@@\n"
            "-before\n"
            "+after\n"
            "*** End Patch\n"
        )

        responses = [FakeApplyPatchToolCallResponse(patch), FakeResponse()]

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
            root = Path(tmpdir)
            (root / "edit.txt").write_text("before\n", encoding="utf-8")
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("edit file"),)),
                "edit file",
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
            )

            self.assertEqual((root / "edit.txt").read_text(encoding="utf-8"), "after\n")

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 2)
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "custom_tool_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "patch-1")
        self.assertNotIn("name", output_items[0])
        self.assertIs(output_items[0]["success"], True)
        self.assertIn("Success. Updated the following files:", output_items[0]["output"])

        self.assertEqual(len(result.raw_tool_output_items), 1)
        changes = result.raw_tool_output_items[0]["internal_output"]["changes"]
        self.assertIn("-before\n+after\n", changes[Path("edit.txt")].unified_diff)
        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual([item.type for item in timeline_items], ["file_change", "file_change"])
        self.assertEqual(
            [item.payload["status"] for item in timeline_items],
            ["in_progress", "completed"],
        )
        self.assertEqual(timeline_items[0].payload["changes"], [{"path": "edit.txt", "kind": "update"}])

    async def test_local_http_exec_shell_tool_loop_returns_apply_patch_approval_failure(self) -> None:
        request_bodies = []

        responses = [FakeApplyPatchToolCallResponse(), FakeResponse()]

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
            root = Path(tmpdir)
            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
                approval_policy=AskForApproval.ON_REQUEST,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("create file"),)),
                "create file",
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
            )

            self.assertFalse((root / "created.txt").exists())

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "custom_tool_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "patch-1")
        self.assertIs(output_items[0]["success"], False)
        self.assertIn("approval_required", output_items[0]["output"])

        self.assertEqual(len(result.raw_tool_output_items), 1)
        changes = result.raw_tool_output_items[0]["internal_output"]["changes"]
        self.assertIn(Path("created.txt"), changes)
        timeline_items = tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor())
        self.assertEqual([item.type for item in timeline_items], ["file_change", "file_change"])
        self.assertEqual(
            [item.payload["status"] for item in timeline_items],
            ["in_progress", "declined"],
        )
        self.assertEqual(timeline_items[0].payload["changes"], [{"path": "created.txt", "kind": "add"}])
        self.assertIs(timeline_items[0].payload["auto_approved"], False)
        self.assertEqual(timeline_items[1].payload["stdout"], "")
        self.assertIn("approval_required", timeline_items[1].payload["stderr"])

    async def test_local_http_exec_shell_tool_loop_applies_granted_permissions_to_apply_patch(self) -> None:
        request_bodies = []
        patch = "*** Begin Patch\n*** Add File: created.txt\n+granted patch\n*** End Patch\n"

        def request_permissions_arguments(root: Path) -> dict[str, object]:
            permissions = RequestPermissionProfile(
                file_system=FileSystemPermissions(
                    (
                        FileSystemSandboxEntry(
                            FileSystemPath.explicit_path(root),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )
            return {
                "reason": "Allow patching the temp workspace",
                "permissions": permissions.to_mapping(),
            }

        def request_permissions_callback(_parent_ctx, _call_id, args, _cwd, _cancel_token):
            return RequestPermissionsResponse(args.permissions, scope=PermissionGrantScope.TURN)

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
            root = Path(tmpdir)
            responses = [
                FakeRequestPermissionsToolCallResponse(request_permissions_arguments(root)),
                FakeApplyPatchToolCallResponse(patch),
                FakeResponse(),
            ]

            def opener(request):
                request_bodies.append(json.loads(request.data.decode("utf-8")))
                return responses.pop(0)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
                approval_policy=AskForApproval.ON_REQUEST,
                request_permissions_callback=request_permissions_callback,
                request_permissions_tool_enabled=True,
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("request then patch"),)),
                "request then patch",
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
                max_tool_rounds=2,
            )

            self.assertEqual((root / "created.txt").read_text(encoding="utf-8"), "granted patch\n")

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        patch_outputs = [
            item for item in request_bodies[2]["input"]
            if item["type"] == "custom_tool_call_output" and item["call_id"] == "patch-1"
        ]
        self.assertEqual(len(patch_outputs), 1)
        self.assertTrue(patch_outputs[0]["success"])
        self.assertIn("Success. Updated the following files:", patch_outputs[0]["output"])
        self.assertNotIn("approval_required", patch_outputs[0]["output"])

    async def test_local_http_exec_shell_tool_loop_returns_request_permissions_failure(self) -> None:
        request_bodies = []
        responses = [FakeRequestPermissionsToolCallResponse(), FakeResponse()]

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
            approval_policy=AskForApproval.ON_REQUEST,
            exec_permission_approvals_enabled=True,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request network"),)),
            "request network",
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
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual(len(request_bodies), 2)
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "permissions-1")
        self.assertNotIn("name", output_items[0])
        self.assertIs(output_items[0]["success"], False)
        self.assertEqual(
            output_items[0]["output"],
            "request_permissions was cancelled before receiving a response",
        )

    async def test_local_http_exec_shell_tool_loop_returns_request_permissions_success(self) -> None:
        request_bodies = []
        responses = [FakeRequestPermissionsToolCallResponse(), FakeResponse()]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        def request_permissions_callback(_parent_ctx, _call_id, args, _cwd, _cancel_token):
            return RequestPermissionsResponse(args.permissions, scope=PermissionGrantScope.TURN)

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
            approval_policy=AskForApproval.ON_REQUEST,
            request_permissions_callback=request_permissions_callback,
            request_permissions_tool_enabled=True,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request network"),)),
            "request network",
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
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        output_items = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(len(output_items), 1)
        self.assertEqual(output_items[0]["call_id"], "permissions-1")
        self.assertNotIn("name", output_items[0])
        self.assertIs(output_items[0]["success"], True)
        self.assertEqual(
            json.loads(output_items[0]["output"]),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
            },
        )

    async def test_local_http_exec_shell_tool_loop_applies_granted_request_permissions(self) -> None:
        request_bodies = []
        responses = [
            FakeRequestPermissionsToolCallResponse(),
            FakeToolCallWithApprovalMetadataResponse(),
            FakeResponse(),
        ]
        runner_calls = []

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        def runner(command, **kwargs):
            runner_calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="network ok\n", stderr="")

        def request_permissions_callback(_parent_ctx, _call_id, args, _cwd, _cancel_token):
            return RequestPermissionsResponse(args.permissions, scope=PermissionGrantScope.TURN)

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
            approval_policy=AskForApproval.ON_REQUEST,
            request_permissions_callback=request_permissions_callback,
            request_permissions_tool_enabled=True,
        )
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request and run"),)),
            "request and run",
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
            runner=runner,
            max_tool_rounds=2,
        )

        self.assertEqual(final_text_from_response_items(result.response_items), "done")
        self.assertEqual([call[0] for call in runner_calls], ["pwd"])
        self.assertEqual(len(request_bodies), 3)
        permission_outputs = [
            item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"
        ]
        self.assertEqual(permission_outputs[0]["call_id"], "permissions-1")
        self.assertTrue(permission_outputs[0]["success"])
        shell_outputs = [
            item for item in request_bodies[2]["input"] if item["type"] == "function_call_output"
        ]
        shell_output = next(item for item in shell_outputs if item["call_id"] == "call-1")
        self.assertTrue(shell_output["success"])
        self.assertIn("network ok", shell_output["output"])
        self.assertNotIn("permission_request_unsupported", shell_output["output"])

    async def test_local_http_exec_shell_tool_loop_session_grant_carries_across_user_turns(self) -> None:
        request_bodies = []
        first_responses = [FakeRequestPermissionsToolCallResponse(), FakeResponse()]
        second_responses = [FakeToolCallWithApprovalMetadataResponse(), FakeResponse()]
        runner_calls = []

        def first_opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return first_responses.pop(0)

        def second_opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return second_responses.pop(0)

        def runner(command, **kwargs):
            runner_calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="session grant ok\n", stderr="")

        def request_permissions_callback(_parent_ctx, _call_id, args, _cwd, _cancel_token):
            return RequestPermissionsResponse(args.permissions, scope=PermissionGrantScope.SESSION)

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
            approval_policy=AskForApproval.ON_REQUEST,
            request_permissions_callback=request_permissions_callback,
            request_permissions_tool_enabled=True,
        )
        first_plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("request session network"),)),
            "request session network",
        )
        second_plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("reuse session network"),)),
            "reuse session network",
        )

        first_result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            first_plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=first_opener,
            built_tools=lambda _sess, _turn: Router(),
        )
        second_result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            second_plan,
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=second_opener,
            built_tools=lambda _sess, _turn: Router(),
            runner=runner,
        )

        self.assertEqual(final_text_from_response_items(first_result.response_items), "done")
        self.assertEqual(final_text_from_response_items(second_result.response_items), "done")
        self.assertEqual([call[0] for call in runner_calls], ["pwd"])
        self.assertEqual(config.granted_session_permissions.network, NetworkPermissions(enabled=True))
        shell_outputs = [
            item for item in request_bodies[-1]["input"] if item["type"] == "function_call_output"
        ]
        shell_output = next(item for item in shell_outputs if item["call_id"] == "call-1")
        self.assertTrue(shell_output["success"])
        self.assertIn("session grant ok", shell_output["output"])

    async def test_local_http_exec_shell_tool_loop_session_grant_applies_to_later_apply_patch(self) -> None:
        request_bodies = []
        patch = "*** Begin Patch\n*** Add File: session-created.txt\n+session patch\n*** End Patch\n"

        def request_permissions_arguments(root: Path) -> dict[str, object]:
            permissions = RequestPermissionProfile(
                file_system=FileSystemPermissions(
                    (
                        FileSystemSandboxEntry(
                            FileSystemPath.explicit_path(root),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )
            return {
                "reason": "Allow session patching the temp workspace",
                "permissions": permissions.to_mapping(),
            }

        def request_permissions_callback(_parent_ctx, _call_id, args, _cwd, _cancel_token):
            return RequestPermissionsResponse(args.permissions, scope=PermissionGrantScope.SESSION)

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
            root = Path(tmpdir)
            first_responses = [
                FakeRequestPermissionsToolCallResponse(request_permissions_arguments(root)),
                FakeResponse(),
            ]
            second_responses = [FakeApplyPatchToolCallResponse(patch), FakeResponse()]

            def first_opener(request):
                request_bodies.append(json.loads(request.data.decode("utf-8")))
                return first_responses.pop(0)

            def second_opener(request):
                request_bodies.append(json.loads(request.data.decode("utf-8")))
                return second_responses.pop(0)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=root,
                approval_policy=AskForApproval.ON_REQUEST,
                request_permissions_callback=request_permissions_callback,
                request_permissions_tool_enabled=True,
            )

            first_result = await run_exec_user_turn_with_shell_tools_http_sampling(
                config,
                ExecRunPlan(
                    InitialOperation.user_turn((UserInput.text_input("request session patch grant"),)),
                    "request session patch grant",
                ),
                ModelClient(session_id="session", thread_id="thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                auth="sk-test",
                opener=first_opener,
                built_tools=lambda _sess, _turn: Router(),
            )
            second_result = await run_exec_user_turn_with_shell_tools_http_sampling(
                config,
                ExecRunPlan(
                    InitialOperation.user_turn((UserInput.text_input("reuse session patch grant"),)),
                    "reuse session patch grant",
                ),
                ModelClient(session_id="session", thread_id="thread", installation_id="install"),
                {"base_url": "https://api.example.test/v1"},
                model_info,
                auth="sk-test",
                opener=second_opener,
                built_tools=lambda _sess, _turn: Router(),
            )

            self.assertEqual((root / "session-created.txt").read_text(encoding="utf-8"), "session patch\n")

        self.assertEqual(final_text_from_response_items(first_result.response_items), "done")
        self.assertEqual(final_text_from_response_items(second_result.response_items), "done")
        self.assertIsNotNone(config.granted_session_permissions)
        self.assertIsNotNone(config.granted_session_permissions.file_system)
        patch_outputs = [
            item for item in request_bodies[-1]["input"]
            if item["type"] == "custom_tool_call_output" and item["call_id"] == "patch-1"
        ]
        self.assertEqual(len(patch_outputs), 1)
        self.assertTrue(patch_outputs[0]["success"])
        self.assertIn("Success. Updated the following files:", patch_outputs[0]["output"])
        self.assertNotIn("approval_required", patch_outputs[0]["output"])

    async def test_local_http_exec_shell_tool_loop_turn_grant_does_not_carry_across_user_turns(self) -> None:
        first_responses = [FakeRequestPermissionsToolCallResponse(), FakeResponse()]
        second_responses = [FakeToolCallWithApprovalMetadataResponse(), FakeResponse()]
        second_request_bodies = []

        def first_opener(_request):
            return first_responses.pop(0)

        def second_opener(request):
            second_request_bodies.append(json.loads(request.data.decode("utf-8")))
            return second_responses.pop(0)

        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("turn grants must not carry into a later user turn")

        def request_permissions_callback(_parent_ctx, _call_id, args, _cwd, _cancel_token):
            return RequestPermissionsResponse(args.permissions, scope=PermissionGrantScope.TURN)

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
            approval_policy=AskForApproval.ON_REQUEST,
            request_permissions_callback=request_permissions_callback,
            request_permissions_tool_enabled=True,
        )

        await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("request turn network"),)),
                "request turn network",
            ),
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=first_opener,
            built_tools=lambda _sess, _turn: Router(),
        )
        second_result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("reuse turn network"),)),
                "reuse turn network",
            ),
            ModelClient(session_id="session", thread_id="thread", installation_id="install"),
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=second_opener,
            built_tools=lambda _sess, _turn: Router(),
            runner=rejecting_runner,
        )

        self.assertEqual(final_text_from_response_items(second_result.response_items), "done")
        self.assertIsNone(config.granted_session_permissions)
        shell_outputs = [
            item for item in second_request_bodies[-1]["input"] if item["type"] == "function_call_output"
        ]
        shell_output = next(item for item in shell_outputs if item["call_id"] == "call-1")
        self.assertFalse(shell_output["success"])
        self.assertIn("permission_request_unsupported", shell_output["output"])
        self.assertIn("additional permissions are disabled", shell_output["output"])

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
            InitialOperation.user_turn(
                (UserInput.text_input("hello"),),
                output_schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                    "additionalProperties": False,
                },
            ),
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

    async def test_local_http_exec_command_rejects_command_alias_before_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("exec_command should require cmd before execution")

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("pwd"),)), "pwd")
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=lambda _request: FakeRawExecCommandToolCallResponse({"command": "pwd"}),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertEqual(outputs[0]["call_id"], "call-1")
        self.assertIs(outputs[0]["success"], False)
        self.assertIn("failed to parse function arguments:", outputs[0]["output"])
        self.assertIn("cmd", outputs[0]["output"])

    async def test_local_http_exec_command_rejects_invalid_yield_time_before_execution(self) -> None:
        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("exec_command should reject invalid typed arguments before execution")

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("pwd"),)), "pwd")
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=lambda _request: FakeRawExecCommandToolCallResponse({"cmd": "pwd", "yield_time_ms": True}),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertEqual(outputs[0]["call_id"], "call-1")
        self.assertIs(outputs[0]["success"], False)
        self.assertIn("failed to parse function arguments:", outputs[0]["output"])
        self.assertIn("yield_time_ms", outputs[0]["output"])

    async def test_local_http_exec_command_ignores_legacy_cwd_and_timeout_aliases(self) -> None:
        class Completed:
            returncode = 0
            stdout = "ok\n"
            stderr = ""

        seen = {}

        def fake_runner(command, **kwargs):
            seen["command"] = command
            seen["cwd"] = kwargs["cwd"]
            seen["timeout"] = kwargs["timeout"]
            return Completed()

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("pwd"),)), "pwd")
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=lambda _request: FakeRawExecCommandToolCallResponse(
                {"cmd": "pwd", "cwd": "subdir", "timeout_ms": 1}
            ),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner, timeout=5.0)

        self.assertEqual(seen["command"], "pwd")
        self.assertEqual(seen["cwd"], "C:\\work\\project")
        self.assertEqual(seen["timeout"], 5.0)
        self.assertIs(outputs[0]["success"], True)

    async def test_local_http_exec_command_honors_workdir_argument(self) -> None:
        class Completed:
            returncode = 0
            stdout = "ok\n"
            stderr = ""

        seen = {}

        def fake_runner(_command, **kwargs):
            seen["cwd"] = kwargs["cwd"]
            return Completed()

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("pwd"),)), "pwd")
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=lambda _request: FakeRawExecCommandToolCallResponse({"cmd": "pwd", "workdir": "subdir"}),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=fake_runner, timeout=5.0)

        self.assertEqual(seen["cwd"], "C:\\work\\project\\subdir")
        self.assertIs(outputs[0]["success"], True)

    async def test_local_http_exec_shell_tool_rejects_invalid_json_arguments_before_execution(self) -> None:
        class InvalidArgumentsResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "shell",
                                "arguments": "{",
                                "call_id": "call-1",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def rejecting_runner(_command, **_kwargs):
            raise AssertionError("runner must not execute invalid JSON tool arguments")

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("pwd"),)), "pwd")
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=lambda _request: InvalidArgumentsResponse(),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config, runner=rejecting_runner)

        self.assertEqual(outputs[0]["call_id"], "call-1")
        self.assertIs(outputs[0]["success"], False)
        self.assertIn("failed to parse function arguments:", outputs[0]["output"])

    async def test_local_http_exec_shell_tool_reports_missing_command_argument(self) -> None:
        class MissingCommandResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "shell",
                                "arguments": "{}",
                                "call_id": "call-1",
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        config = ExecSessionConfig(model=None, model_provider_id=None, cwd=Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("pwd"),)), "pwd")
        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
            opener=lambda _request: MissingCommandResponse(),
            built_tools=lambda _sess, _turn: Router(),
        )

        outputs = shell_tool_outputs_from_local_http_exec_result(result, config)

        self.assertEqual(outputs[0]["call_id"], "call-1")
        self.assertIs(outputs[0]["success"], False)
        self.assertIn("missing required command", outputs[0]["output"])

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
            InitialOperation.user_turn(
                (UserInput.text_input("hello"),),
                output_schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                    "additionalProperties": False,
                },
            ),
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

    async def test_local_http_write_stdin_missing_session_id_returns_parse_error(self) -> None:
        class FakeSessionManager:
            def __init__(self) -> None:
                self.write_called = False

            def write(self, session_id, chars, *, yield_time=None, output_max_chars=None):
                self.write_called = True
                raise AssertionError("write_stdin should not run with invalid arguments")

        manager = FakeSessionManager()

        def opener(_request):
            return FakeRawWriteStdinToolCallResponse({"chars": "hello\n"})

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
        self.assertIs(outputs[0]["success"], False)
        self.assertIn("failed to parse function arguments:", outputs[0]["output"])
        self.assertIn("session_id", outputs[0]["output"])
        self.assertFalse(manager.write_called)

    async def test_local_http_write_stdin_rejects_non_string_chars(self) -> None:
        class FakeSessionManager:
            def write(self, session_id, chars, *, yield_time=None, output_max_chars=None):
                raise AssertionError("write_stdin should not run with invalid arguments")

        def opener(_request):
            return FakeRawWriteStdinToolCallResponse({"session_id": 7, "chars": ["hello"]})

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
            session_manager=FakeSessionManager(),
        )

        self.assertEqual(outputs[0]["name"], "write_stdin")
        self.assertIs(outputs[0]["success"], False)
        self.assertIn("failed to parse function arguments:", outputs[0]["output"])
        self.assertIn("chars", outputs[0]["output"])

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

    async def test_local_http_write_stdin_preserves_zero_max_output_tokens(self) -> None:
        class FakeSessionManager:
            def __init__(self) -> None:
                self.output_max_chars = None

            def write(self, session_id, chars, *, yield_time=None, output_max_chars=None):
                self.output_max_chars = output_max_chars
                return {
                    "wall_time_seconds": 0.0,
                    "exit_code": 0,
                    "original_token_count": 3,
                    "output": "... tokens truncated...",
                }, True

        manager = FakeSessionManager()

        def opener(_request):
            return FakeWriteStdinToolCallResponse(max_output_tokens=0)

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
        self.assertEqual(manager.output_max_chars, 0)

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

    async def test_local_http_write_stdin_exit_clears_session(self) -> None:
        manager = LocalHttpExecSessionManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "stdin_exit_child.py"
            script.write_text(
                "import sys\n"
                "print('ready')\n"
                "line = sys.stdin.readline()\n"
                "print('got:' + line.strip())\n",
                encoding="utf-8",
            )
            command = f"\"{sys.executable}\" -u \"{script}\""

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
                opener=lambda _request: FakeSessionExecCommandToolCallResponse(command),
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                session_manager=manager,
            )
            session_id = outputs[0]["structured_output"]["session_id"]

            stdin_result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=lambda _request: FakeWriteStdinToolCallResponse(
                    session_id=session_id,
                    chars="hello\n",
                    yield_time_ms=500,
                ),
                built_tools=lambda _sess, _turn: Router(),
            )
            stdin_outputs = shell_tool_outputs_from_local_http_exec_result(
                stdin_result,
                config,
                session_manager=manager,
            )

            self.assertIs(stdin_outputs[0]["success"], True)
            self.assertEqual(stdin_outputs[0]["structured_output"]["exit_code"], 0)
            self.assertNotIn("session_id", stdin_outputs[0]["structured_output"])
            self.assertIn("got:hello", stdin_outputs[0]["output"])

            stale_result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=lambda _request: FakeWriteStdinToolCallResponse(
                    session_id=session_id,
                    chars="again\n",
                    yield_time_ms=100,
                ),
                built_tools=lambda _sess, _turn: Router(),
            )
            stale_outputs = shell_tool_outputs_from_local_http_exec_result(
                stale_result,
                config,
                session_manager=manager,
            )

            self.assertIs(stale_outputs[0]["success"], False)
            self.assertEqual(
                stale_outputs[0]["output"],
                local_http_write_stdin_unknown_session_output(session_id),
            )

    async def test_local_http_write_stdin_eot_closes_process_stdin(self) -> None:
        manager = LocalHttpExecSessionManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "stdin_eof_child.py"
            script.write_text(
                "import sys\n"
                "print('ready', flush=True)\n"
                "for line in sys.stdin:\n"
                "    print('got:' + line.strip(), flush=True)\n"
                "print('closed', flush=True)\n",
                encoding="utf-8",
            )
            command = f"\"{sys.executable}\" -u \"{script}\""

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("start eof session"),)),
                "start eof session",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=lambda _request: FakeSessionExecCommandToolCallResponse(command, tty=True),
                built_tools=lambda _sess, _turn: Router(),
            )

            outputs = shell_tool_outputs_from_local_http_exec_result(
                result,
                config,
                session_manager=manager,
            )
            session_id = outputs[0]["structured_output"]["session_id"]

            write_result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=lambda _request: FakeWriteStdinToolCallResponse(
                    session_id=session_id,
                    chars="hello\n",
                    yield_time_ms=200,
                ),
                built_tools=lambda _sess, _turn: Router(),
            )
            write_outputs = shell_tool_outputs_from_local_http_exec_result(
                write_result,
                config,
                session_manager=manager,
            )

            self.assertIs(write_outputs[0]["success"], True)
            self.assertEqual(write_outputs[0]["structured_output"]["session_id"], session_id)
            self.assertNotIn("exit_code", write_outputs[0]["structured_output"])
            self.assertIn("got:hello", write_outputs[0]["output"])

            eof_result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=lambda _request: FakeWriteStdinToolCallResponse(
                    session_id=session_id,
                    chars="\x04",
                    yield_time_ms=500,
                ),
                built_tools=lambda _sess, _turn: Router(),
            )
            eof_outputs = shell_tool_outputs_from_local_http_exec_result(
                eof_result,
                config,
                session_manager=manager,
            )

            self.assertIs(eof_outputs[0]["success"], True)
            self.assertEqual(eof_outputs[0]["structured_output"]["exit_code"], 0)
            self.assertNotIn("session_id", eof_outputs[0]["structured_output"])
            self.assertIn("closed", eof_outputs[0]["output"])

    async def test_local_http_exec_command_session_nonzero_exit_remains_successful_tool_result(self) -> None:
        manager = LocalHttpExecSessionManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "nonzero_child.py"
            script.write_text(
                "import sys\n"
                "print('about to fail')\n"
                "sys.exit(7)\n",
                encoding="utf-8",
            )
            command = f"\"{sys.executable}\" -u \"{script}\""

            def exec_opener(_request):
                return FakeSessionExecCommandToolCallResponse(command, yield_time_ms=1000)

            config = ExecSessionConfig(
                model=None,
                model_provider_id=None,
                cwd=Path(tmpdir),
            )
            plan = ExecRunPlan(
                InitialOperation.user_turn((UserInput.text_input("start nonzero session"),)),
                "start nonzero session",
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

            self.assertIs(outputs[0]["success"], True)
            self.assertEqual(outputs[0]["structured_output"]["exit_code"], 7)
            self.assertIn("Process exited with code 7", outputs[0]["output"])
            self.assertIn("about to fail", outputs[0]["output"])

    async def test_local_http_write_stdin_nonzero_exit_remains_successful_tool_result(self) -> None:
        manager = LocalHttpExecSessionManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "stdin_nonzero_child.py"
            script.write_text(
                "import sys\n"
                "print('ready')\n"
                "sys.stdin.readline()\n"
                "print('done then fail')\n"
                "sys.exit(9)\n",
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
                InitialOperation.user_turn((UserInput.text_input("start stdin nonzero"),)),
                "start stdin nonzero",
            )
            result = await run_exec_user_turn_default_local_http_sampling(
                config,
                plan,
                env={"PYCODEX_EXEC_LOCAL_HTTP": "1", "OPENAI_API_KEY": "sk-env"},
                opener=exec_opener,
                built_tools=lambda _sess, _turn: Router(),
            )
            outputs = shell_tool_outputs_from_local_http_exec_result(result, config, session_manager=manager)
            session_match = re.search(r"Process running with session ID (\d+)", outputs[0]["output"])
            self.assertIsNotNone(session_match)

            def stdin_opener(_request):
                return FakeWriteStdinToolCallResponse(session_id=int(session_match.group(1)), chars="go\n")

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
            self.assertEqual(stdin_outputs[0]["structured_output"]["exit_code"], 9)
            self.assertIn("Process exited with code 9", stdin_outputs[0]["output"])
            self.assertIn("done then fail", stdin_outputs[0]["output"])

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
                return FakeSessionExecCommandToolCallResponse(command, yield_time_ms=250)

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
                timeout=0.1,
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

        result = await run_exec_user_turn_default_local_http_sampling(
            config,
            plan,
            env=env,
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(result.turn_status, "completed")
        self.assertIsNone(result.last_agent_message)
        events = tuple(getattr(result, "session_events", ()))
        self.assertEqual([event.type for event in events[-2:]], ["error", "task_complete"])
        self.assertEqual(events[-2].payload.codex_error_info.type, "other")
        self.assertIn("bad schema", events[-2].payload.message)
        self.assertIsNone(events[-1].payload.last_agent_message)

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

    def test_default_local_http_auth_uses_auth_openai_api_key_value(self) -> None:
        auth = type("Auth", (), {"openai_api_key": "sk-auth-json"})()

        resolved = default_local_http_exec_auth(auth=auth, env={})

        self.assertIs(resolved, auth)

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
        self.assertEqual(default_local_http_exec_model(config_default, env={}), "gpt-5.3-codex")

    def test_local_http_exec_max_tool_rounds_env(self) -> None:
        self.assertIsNone(local_http_exec_max_tool_rounds(env={}))
        self.assertEqual(local_http_exec_max_tool_rounds(env={}, default=1), 1)
        self.assertEqual(local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "3"}), 3)
        self.assertEqual(local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "0"}), 0)
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "-1"})
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            local_http_exec_max_tool_rounds(env={"PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "many"})

    def test_local_http_exec_shell_tools_default_disabled_with_explicit_enable(self) -> None:
        self.assertFalse(local_http_exec_shell_tools_enabled(env={}))
        self.assertTrue(local_http_exec_shell_tools_enabled(env={"PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1"}))
        self.assertFalse(local_http_exec_shell_tools_enabled(env={"PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0"}))

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

    def test_default_local_http_runtime_uses_config_provider_parallel_tool_calls(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id="local-openai",
            cwd=Path("C:/work/project"),
        )

        _client, _provider, model_info, _auth = build_default_local_http_exec_runtime(
            config,
            env={"LOCAL_OPENAI_KEY": "sk-local"},
            config_toml={
                "model_providers": {
                    "local-openai": {
                        "env_key": "LOCAL_OPENAI_KEY",
                        "supports_parallel_tool_calls": True,
                    }
                }
            },
        )

        self.assertTrue(model_info.supports_parallel_tool_calls)

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

    def test_local_http_exec_config_summary_renders_granular_approval_label(self) -> None:
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=False,
            request_permissions=True,
            mcp_elicitations=False,
        )
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
            approval_policy=granular,
        )

        summary_config, summary_session = local_http_exec_config_summary(
            config,
            session_id="session-1",
            thread_id="thread-1",
        )

        self.assertEqual(summary_config["approval_policy"], "granular")
        self.assertEqual(summary_session["approval_policy"], "granular")

    def test_local_http_exec_config_summary_includes_resume_initial_messages(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            rollout_path = Path(tmpdir) / "rollout.jsonl"
            with rollout_path.open("w", encoding="utf-8", newline="\n") as file:
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T00:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "resume prompt", "kind": "plain"},
                        }
                    )
                    + "\n"
                )
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T00:00:01Z",
                            "type": "event_msg",
                            "payload": {"type": "agent_message", "message": "resume answer"},
                        }
                    )
                    + "\n"
                )

            initial_messages = local_http_exec_initial_messages_from_rollout(rollout_path)
            _summary_config, summary_session = local_http_exec_config_summary(
                config,
                session_id="session-1",
                thread_id="thread-1",
                initial_messages=initial_messages,
                rollout_path=rollout_path,
            )

        self.assertEqual(
            summary_session["initial_messages"],
            [
                {"type": "user_message", "message": "resume prompt", "local_images": [], "text_elements": []},
                {"type": "agent_message", "message": "resume answer"},
            ],
        )
        self.assertEqual(summary_session["rollout_path"], str(rollout_path))

    def test_core_runtime_aliases_preserve_local_runtime_helpers(self) -> None:
        config = ExecSessionConfig(
            model=None,
            model_provider_id=None,
            cwd=Path("C:/work/project"),
        )

        summary_config, summary_session = core_exec_config_summary(
            config,
            model="gpt-core",
            session_id="session-core",
            thread_id="thread-core",
        )

        self.assertEqual(summary_config["model"], "gpt-core")
        self.assertEqual(summary_session["session_id"], "session-core")
        self.assertEqual(summary_session["thread_id"], "thread-core")
        self.assertIs(persist_core_exec_rollout, persist_local_http_exec_rollout)
        self.assertIs(persist_core_exec_resume_rollout, persist_local_http_exec_resume_rollout)
        self.assertIs(core_review_rollout_input_items, local_http_review_rollout_input_items)
        self.assertIs(core_exec_initial_messages_from_rollout, local_http_exec_initial_messages_from_rollout)

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


