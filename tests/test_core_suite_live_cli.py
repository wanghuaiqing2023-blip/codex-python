"""Rust integration parity for ``core/tests/suite/live_cli.rs``.

Rust marks these as ignored live OpenAI smoke tests.  Python keeps the same CLI
behavior contract with a deterministic fake Responses backend: the CLI can use
tool calls to create ``hello.txt`` and can surface the current working directory
after a shell-command turn.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from pycodex.cli.parser import main


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


def _run_cli_with_fake_responses(tmpdir: str, prompt: str, responses: list[dict[str, object]]) -> tuple[int, str, str, list[dict[str, object]]]:
    request_bodies: list[dict[str, object]] = []

    def opener(request):
        request_bodies.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse(responses.pop(0))

    with patch.dict(
        os.environ,
        {
            "CODEX_HOME": tmpdir,
            "PYCODEX_EXEC_LOCAL_HTTP": "1",
            "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
            "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
            "OPENAI_API_KEY": "sk-live-cli-parity",
            "PYCODEX_EXEC_MODEL": "",
            "OPENAI_MODEL": "",
        },
    ):
        with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
            with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                stdout = io.StringIO()
                stderr = io.StringIO()
                code = main(
                    [
                        "exec",
                        "--cd",
                        tmpdir,
                        "--dangerously-bypass-approvals-and-sandbox",
                        prompt,
                    ],
                    stdout=stdout,
                    stderr=stderr,
                )
    return code, stdout.getvalue(), stderr.getvalue(), request_bodies


def test_live_create_file_hello_txt() -> None:
    """Rust: ``live_create_file_hello_txt``."""

    patch_text = "*** Begin Patch\n*** Add File: hello.txt\n+hello\n*** End Patch\n"
    responses: list[dict[str, object]] = [
        {
            "output": [
                {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "input": patch_text,
                    "call_id": "patch-hello",
                }
            ]
        },
        {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "created hello.txt"}],
                }
            ]
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        code, stdout, stderr, request_bodies = _run_cli_with_fake_responses(
            tmpdir,
            "Use the shell tool with the apply_patch command to create a file named hello.txt containing the text 'hello'.",
            responses,
        )
        hello_path = Path(tmpdir) / "hello.txt"
        contents = hello_path.read_text(encoding="utf-8")

    assert code == 0, stderr
    assert stdout == "created hello.txt\n"
    assert contents.strip() == "hello"
    assert any(tool.get("name") == "apply_patch" for tool in request_bodies[0].get("tools", ()))
    patch_outputs = [item for item in request_bodies[1]["input"] if item.get("type") == "custom_tool_call_output"]
    assert len(patch_outputs) == 1
    assert patch_outputs[0]["call_id"] == "patch-hello"
    assert patch_outputs[0]["success"] is True


def test_live_print_working_directory() -> None:
    """Rust: ``live_print_working_directory``."""

    with tempfile.TemporaryDirectory() as tmpdir:
        command = subprocess.list2cmdline(
            [sys.executable, "-c", "import os; print(os.getcwd())"]
        )
        responses: list[dict[str, object]] = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "pwd-call",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": tmpdir}],
                    }
                ]
            },
        ]
        code, stdout, stderr, request_bodies = _run_cli_with_fake_responses(
            tmpdir,
            "Print the current working directory using the shell function.",
            responses,
        )

    assert code == 0, stderr
    assert tmpdir in stdout
    assert any(tool.get("name") == "exec_command" for tool in request_bodies[0].get("tools", ()))
    tool_outputs = [item for item in request_bodies[1]["input"] if item.get("type") == "function_call_output"]
    assert len(tool_outputs) == 1
    assert tool_outputs[0]["call_id"] == "pwd-call"
    assert tmpdir in tool_outputs[0]["output"]
