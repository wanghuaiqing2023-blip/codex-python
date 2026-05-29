import json
import tempfile
import io
import re
import sys
import unittest
from urllib.error import HTTPError
from pathlib import Path

from pycodex.core.client import ModelClient
from pycodex.exec.event_processor import HumanEventProcessor, JsonEventProcessor
from pycodex.exec.local_runtime import (
    build_default_local_http_exec_runtime,
    default_local_http_exec_auth,
    default_local_http_exec_base_url,
    default_local_http_exec_model,
    emit_local_http_exec_error,
    emit_local_http_exec_result,
    final_text_from_response_items,
    LocalHttpExecSessionManager,
    local_http_exec_enabled,
    local_http_apply_patch_tool_spec,
    local_http_exec_config_summary,
    local_http_exec_max_tool_rounds,
    local_http_write_stdin_tool_spec,
    local_http_shell_tool_auto_execute_allowed,
    local_http_shell_tool_spec,
    local_http_shell_tools_built_tools,
    local_http_exec_tool_output_max_chars,
    reasoning_texts_from_local_http_exec_result,
    response_items_from_local_http_tool_outputs,
    run_exec_tool_output_http_sampling,
    run_exec_user_turn_default_local_http_sampling,
    run_exec_user_turn_http_sampling,
    run_exec_user_turn_with_shell_tools_http_sampling,
    shell_tool_outputs_from_local_http_exec_result,
    tool_call_items_from_local_http_exec_result,
    tool_output_items_from_local_http_exec_result,
    usage_from_local_http_exec_result,
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
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{\"command\":\"pwd\"}",
                        "call_id": "call-1",
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "I need to run a command."}],
                    },
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeExecCommandToolCallResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": "{\"cmd\":\"pwd\",\"max_output_tokens\":4}",
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
    def __init__(self, session_id: int = 7, chars: str = "hello\n") -> None:
        self.session_id = session_id
        self.chars = chars

    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "write_stdin",
                        "arguments": json.dumps({"session_id": self.session_id, "chars": self.chars, "yield_time_ms": 100}),
                        "call_id": "stdin-1",
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class FakeSessionExecCommandToolCallResponse:
    def __init__(self, command: str) -> None:
        self.command = command

    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": json.dumps({"cmd": self.command, "yield_time_ms": 500}),
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
                            "\"sandbox_permissions\":\"require_escalated\","
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
        self.assertEqual(spec["parameters"]["required"], ["cmd"])
        self.assertIn("workdir", spec["parameters"]["properties"])
        self.assertIn("yield_time_ms", spec["parameters"]["properties"])
        self.assertIn("max_output_tokens", spec["parameters"]["properties"])
        self.assertEqual(spec["output_schema"]["required"], ["wall_time_seconds", "output"])
        self.assertIn("session_id", spec["output_schema"]["properties"])
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
        self.assertEqual(spec["parameters"]["required"], ["session_id"])
        self.assertIn("chars", spec["parameters"]["properties"])
        self.assertEqual(spec["output_schema"]["required"], ["wall_time_seconds", "output"])

    def test_local_http_shell_tools_built_tools_preserves_existing_specs(self) -> None:
        router = local_http_shell_tools_built_tools(lambda _session, _turn: ExistingToolRouter())(None, None)
        specs = router.model_visible_specs()

        self.assertEqual([spec["name"] for spec in specs], ["existing", "exec_command", "write_stdin", "apply_patch"])


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
        self.assertIn("project instructions", seen["body"]["input"][0]["content"][0]["text"])
        self.assertEqual(seen["body"]["input"][1]["content"][0]["text"], "hello")
        self.assertEqual(seen["body"]["text"]["format"]["schema"]["properties"]["ok"]["type"], "boolean")

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

        self.assertIn("[truncated", outputs[0]["output"])
        self.assertLessEqual(outputs[0]["output"].index("[truncated"), 21)

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

        self.assertIn("sandbox_permissions: require_escalated", outputs[0]["output"])
        self.assertIn("justification: Need to inspect the workspace", outputs[0]["output"])
        self.assertIn("command:\npwd", outputs[0]["output"])

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
        self.assertIn("[truncated", outputs[0]["output"])

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
        self.assertIs(outputs[0]["success"], False)
        self.assertIn("session_id: 7", outputs[0]["output"])
        self.assertIn("No active local exec session exists", outputs[0]["output"])

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
            session_match = re.search(r"session_id: (\d+)", outputs[0]["output"])
            self.assertIsNotNone(session_match)
            self.assertIn("ready", outputs[0]["output"])

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

        with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY is required"):
            build_default_local_http_exec_runtime(config, env={"PYCODEX_EXEC_LOCAL_HTTP": "1"})

    def test_default_local_http_auth_prefers_env_key(self) -> None:
        auth = type("Auth", (), {"openai_api_key": "sk-auth-json"})()

        resolved = default_local_http_exec_auth(auth=auth, env={"OPENAI_API_KEY": "sk-env"})

        self.assertEqual(resolved, "sk-env")

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
