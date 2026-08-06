"""End-to-end coverage for the Rust-owned ``/mcp`` slash command."""

import asyncio
import json
import os
from pathlib import Path
import sys

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    _SseFixtureServer,
    _completed_text_response,
    _isolated_codex_home_env_with_config,
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_repeated_local_slash_candidate,
    slash_candidate_pair,
)
from tests.e2e.support._native_tui import (
    ConptyInputStep,
    TerminalSize,
    TuiComparisonCommand,
    run_windows_conpty_tui_command,
)
from tests.e2e.tui._common import SESSION_CONFIGURED_COMPOSER_PATTERN
from tests.e2e.support.responses_fixture import _responses_sse
from tests.support.app_test_support.auth_fixtures import (
    ChatGptAuthFixture,
    write_chatgpt_auth,
)
from tests.support.core_test_support.apps_test_server import AppsTestServer

pytestmark = pytest.mark.e2e

ROWS = 36
COLS = 140


def _configured_mcp_config(
    base_url: str,
    *,
    tools_list_delay_seconds: float = 0.0,
    tools_list_release_file: Path | None = None,
    tools_list_block_file: Path | None = None,
) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    command = json.dumps(sys.executable)
    cwd = json.dumps(str(repo_root))
    env_items: list[str] = []
    if tools_list_delay_seconds > 0:
        env_items.append(
            f'PYCODEX_TEST_MCP_TOOLS_LIST_DELAY_SECONDS = "{tools_list_delay_seconds}"'
        )
    if tools_list_release_file is not None:
        env_items.append(
            "PYCODEX_TEST_MCP_TOOLS_LIST_RELEASE_FILE = "
            + json.dumps(str(tools_list_release_file))
        )
    if tools_list_block_file is not None:
        env_items.append(
            "PYCODEX_TEST_MCP_TOOLS_LIST_BLOCK_FILE = "
            + json.dumps(str(tools_list_block_file))
        )
    server_env = f"env = {{ {', '.join(env_items)} }}\n" if env_items else ""
    server = (
        f"command = {command}\n"
        'args = ["-B", "-m", "pycodex.rmcp_client.bin.test_stdio_server"]\n'
        f"cwd = {cwd}\n"
        + server_env
        + "startup_timeout_sec = 120\n"
        + "required = true\n\n"
    )
    return (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\napps = false\nplugins = false\n\n'
        '[model_providers.pycodex_mock]\n'
        'name = "Mock provider that /mcp must not call"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        '[mcp_servers.zeta]\n'
        + server
        + '[mcp_servers.alpha]\n'
        + server
        + f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        + 'trust_level = "trusted"\n'
    )


def _bundled_node_repl_exe() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    root = local_app_data / "OpenAI" / "Codex" / "runtimes" / "cua_node"
    candidates = sorted(
        root.glob("*/bin/node_repl.exe"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        pytest.fail(f"bundled node_repl.exe is required for native /mcp parity: {root}")
    return candidates[0]


def _node_repl_mcp_config(base_url: str, node_repl_exe: Path) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\napps = false\nplugins = false\n\n'
        '[model_providers.pycodex_mock]\n'
        'name = "Mock provider that /mcp must not call"\n'
        f'base_url = "{base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        '[mcp_servers.node_repl]\n'
        f'command = {json.dumps(str(node_repl_exe))}\n'
        'args = []\n'
        'startup_timeout_sec = 120\n'
        'required = true\n\n'
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )


def _host_apps_and_node_repl_config(
    model_base_url: str,
    apps_base_url: str,
) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        'model = "gpt-5.5"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n'
        f'chatgpt_base_url = "{apps_base_url}"\n\n'
        '[features]\napps = true\nplugins = false\n\n'
        '[model_providers.pycodex_mock]\n'
        'name = "Mock provider that /mcp must not call"\n'
        f'base_url = "{model_base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        '[mcp_servers.node_repl]\n'
        f'command = {json.dumps(sys.executable)}\n'
        'args = ["-B", "-m", "pycodex.rmcp_client.bin.test_stdio_server"]\n'
        f'cwd = {json.dumps(str(repo_root))}\n'
        'required = true\n\n'
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )


def _failing_mcp_config(model_base_url: str) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        'model = "mock-model"\n'
        'model_provider = "pycodex_mock"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        'suppress_unstable_features_warning = true\n\n'
        '[features]\napps = false\nplugins = false\n\n'
        '[model_providers.pycodex_mock]\n'
        'name = "Mock provider that /mcp must not call"\n'
        f'base_url = "{model_base_url}"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n'
        'request_max_retries = 0\n'
        'stream_max_retries = 0\n'
        'supports_websockets = false\n\n'
        '[mcp_servers.broken]\n'
        'command = "pycodex-e2e-deliberately-missing-mcp-server"\n'
        'startup_timeout_sec = 2\n'
        'required = false\n\n'
        f"[projects.'{str(repo_root.resolve(strict=False)).lower()}']\n"
        'trust_level = "trusted"\n'
    )


def _run_failing_mcp_inventory(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    fixture = _completed_text_response(
        f"resp-{label}-broken-mcp-unused",
        f"msg-{label}-broken-mcp-unused",
        "BROKEN_MCP_MUST_NOT_REACH_MODEL",
    )
    with _SseFixtureServer(fixture) as model_server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _failing_mcp_config(model_server.base_url)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/mcp",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=40.0,
                        ready_quiet_period=0.8,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_screen_text="/mcp", ready_timeout=10.0),
                    ConptyInputStep(
                        "",
                        ready_screen_text="Tools: (none)",
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        capture_name="broken-mcp-complete",
                    ),
                ),
                env=env,
                timeout=2,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = tuple(model_server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-broken-mcp-inventory",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def _screen_server_names(screen: str) -> tuple[str, ...]:
    names: list[str] = []
    lines = screen.splitlines()
    for index, line in enumerate(lines[:-1]):
        stripped = line.strip()
        if not stripped.startswith(("• ", "- ")):
            continue
        following = lines[index + 1].strip()
        if following.startswith(("• Auth:", "- Auth:")):
            names.append(stripped[2:].strip())
    return tuple(names)


def _screen_inventory(screen: str) -> dict[str, dict[str, object]]:
    lines = screen.splitlines()
    server_rows: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(("• ", "- ")):
            continue
        if (
            index + 1 < len(lines)
            and lines[index + 1].strip().lstrip("•- ").startswith("Auth:")
        ):
            server_rows.append((index, stripped[2:].strip()))

    inventory: dict[str, dict[str, object]] = {}
    for server_index, (start, name) in enumerate(server_rows):
        end = (
            server_rows[server_index + 1][0]
            if server_index + 1 < len(server_rows)
            else len(lines)
        )
        auth: str | None = None
        tool_fragments: list[str] = []
        collecting_tools = False
        for line in lines[start + 1 : end]:
            stripped = line.strip()
            value = stripped.lstrip("•- ")
            if value.startswith("Auth:"):
                auth = value.removeprefix("Auth:").strip()
                continue
            if value.startswith("Tools:"):
                collecting_tools = True
                value = value.removeprefix("Tools:").strip()
                if value:
                    tool_fragments.append(value)
                continue
            if collecting_tools:
                if not stripped or stripped.startswith(("• ", "- ")):
                    break
                tool_fragments.append(stripped)
        raw_tools = " ".join(tool_fragments)
        inventory[name] = {
            "auth": auth,
            "tools": (
                []
                if raw_tools == "(none)"
                else [item.strip() for item in raw_tools.split(",") if item.strip()]
            ),
        }
    return inventory


def _run_host_apps_inventory(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
    apps_server: AppsTestServer,
    authenticated: bool = True,
    ready_text: str = "github_fetch_issue",
):
    fixture = _completed_text_response(
        f"resp-{label}-apps-mcp-unused",
        f"msg-{label}-apps-mcp-unused",
        "HOST_APPS_MCP_MUST_NOT_REACH_MODEL",
    )
    with _SseFixtureServer(fixture) as model_server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _host_apps_and_node_repl_config(
                model_server.base_url,
                apps_server.chatgpt_base_url,
            )
        )
        home = Path(env["CODEX_HOME"])
        if authenticated:
            write_chatgpt_auth(
                home,
                ChatGptAuthFixture("apps-access-token").account_id("account-test"),
            )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/mcp",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=40.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_screen_text="/mcp", ready_timeout=10.0),
                    ConptyInputStep(
                        "",
                        ready_screen_text=ready_text,
                        ready_timeout=40.0,
                        ready_quiet_period=0.8,
                        capture_name="host-apps-complete",
                    ),
                ),
                env=env,
                timeout=2,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = tuple(model_server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-host-apps-mcp-inventory",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def _mcp_tool_call_response(
    *,
    response_id: str,
    item_id: str,
    call_id: str,
    namespace: str,
    name: str,
) -> bytes:
    return _responses_sse(
        {"type": "response.created", "response": {"id": response_id}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": item_id,
                "type": "function_call",
                "call_id": call_id,
                "namespace": namespace,
                "name": name,
                "arguments": "{}",
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )


def _tool_search_call_response(
    *,
    response_id: str,
    item_id: str,
    call_id: str,
    query: str,
) -> bytes:
    return _responses_sse(
        {"type": "response.created", "response": {"id": response_id}},
        {
            "type": "response.output_item.done",
            "item": {
                "id": item_id,
                "type": "tool_search_call",
                "call_id": call_id,
                "status": "completed",
                "execution": "client",
                "arguments": {"query": query, "limit": 8},
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": None,
                    "output_tokens": 1,
                    "output_tokens_details": None,
                    "total_tokens": 2,
                },
            },
        },
    )


def _model_request_tool_identities(request: dict[str, object]) -> tuple[str, ...]:
    identities: list[str] = []
    for tool in request.get("tools", []):
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name", ""))
        children = tool.get("tools", [])
        if isinstance(children, list):
            child_names = [
                str(child.get("name", ""))
                for child in children
                if isinstance(child, dict)
            ]
            if child_names:
                identities.extend(f"{name}.{child}" for child in child_names)
                continue
        identities.append(name)
    return tuple(identities)


def _run_host_apps_tool_call(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    connector_id = "connector_github_e2e"
    tool_name = "github_get_user_login"
    call_id = f"call-{label}-github-login"
    final_answer = f"CODEX_APPS_GITHUB_LOGIN_DONE_{label.upper()}"
    search_body = _tool_search_call_response(
        response_id=f"resp-{label}-github-login-search",
        item_id=f"ts-{label}-github-login-search",
        call_id=f"call-{label}-github-login-search",
        query="GitHub authenticated user login",
    )
    tool_body = _mcp_tool_call_response(
        response_id=f"resp-{label}-github-login-call",
        item_id=f"fc-{label}-github-login-call",
        call_id=call_id,
        namespace="mcp__codex_apps__github",
        name="_get_user_login",
    )
    final_body = _completed_text_response(
        f"resp-{label}-github-login-final",
        f"msg-{label}-github-login-final",
        final_answer,
    )
    filler_tools = tuple(
        {
            "name": f"github_fixture_tool_{index:03d}",
            "description": f"Read fixture record number {index}.",
            "annotations": {"readOnlyHint": True},
            "inputSchema": {"type": "object", "properties": {}},
            "_meta": {
                "connector_id": connector_id,
                "connector_name": "GitHub",
                "connector_description": "Read GitHub account metadata.",
            },
        }
        for index in range(100)
    )
    apps_server = asyncio.run(
        AppsTestServer.mount_with_tools(
            (
                {
                    "name": tool_name,
                    "description": "Return the authenticated GitHub login.",
                    "annotations": {"readOnlyHint": True},
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "_meta": {
                        "connector_id": connector_id,
                        "connector_name": "GitHub",
                        "connector_description": "Read GitHub account metadata.",
                    },
                },
                *filler_tools,
            ),
            apps=(
                {
                    "id": connector_id,
                    "name": "GitHub",
                    "description": "Read GitHub account metadata.",
                },
            ),
            tool_call_result={
                "content": [
                    {
                        "type": "text",
                        "text": '{"login":"fixture-github-user","id":277317463}',
                    }
                ],
                "structuredContent": {
                    "login": "fixture-github-user",
                    "id": 277317463,
                },
                "isError": False,
            },
        )
    )
    try:
        with _SseFixtureServer((search_body, tool_body, final_body)) as model_server:
            config = _host_apps_and_node_repl_config(
                model_server.base_url,
                apps_server.chatgpt_base_url,
            )
            config += (
                "\n[apps.connector_github_e2e]\n"
                'default_tools_approval_mode = "auto"\n'
            )
            env, temp_home = _isolated_codex_home_env_with_config(
                config
            )
            write_chatgpt_auth(
                Path(env["CODEX_HOME"]),
                ChatGptAuthFixture("apps-access-token").account_id("account-test"),
            )
            prompt = "Call the codex_apps GitHub login MCP tool and report its result."
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/mcp",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=40.0,
                            ready_quiet_period=0.5,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="/mcp",
                            ready_timeout=10.0,
                        ),
                        ConptyInputStep(
                            prompt,
                            ready_screen_text=tool_name,
                            ready_timeout=40.0,
                            ready_quiet_period=0.5,
                            atomic_write=True,
                            capture_name="github-tool-inventory",
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text=prompt,
                            ready_timeout=10.0,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text=final_answer,
                            ready_timeout=40.0,
                            ready_quiet_period=0.5,
                            capture_name="github-tool-call-complete",
                        ),
                        ConptyInputStep("/quit\r", ready_timeout=0.2),
                    ),
                    env=env,
                    timeout=50,
                    size=TerminalSize(rows=40, cols=150),
                )
            model_requests = tuple(
                json.loads(body) for body in model_server.request_bodies
            )
        apps_calls = tuple(asyncio.run(apps_server.recorded_calls()))
    finally:
        asyncio.run(apps_server.shutdown())

    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-host-apps-github-tool-call",
        rows=40,
        cols=150,
    )
    return transcript, model_requests, apps_calls, final_answer


def _style_signature(style: object) -> tuple[object, ...]:
    def color_signature(color: object | None) -> tuple[object, object] | None:
        if color is None:
            return None
        return (getattr(color, "kind", None), getattr(color, "value", None))

    return (
        color_signature(getattr(style, "fg", None)),
        color_signature(getattr(style, "bg", None)),
        bool(getattr(style, "bold", False)),
        bool(getattr(style, "dim", False)),
        bool(getattr(style, "italic", False)),
        bool(getattr(style, "underline", False)),
        bool(getattr(style, "reverse", False)),
    )


def _row_contract(transcript, checkpoint: str, token: str) -> tuple[str, tuple[tuple[object, ...], ...]]:
    screen = transcript.checkpoint_cells(checkpoint, rows=ROWS, cols=COLS)
    for row in screen.rows:
        text = "".join(cell.char for cell in row).rstrip()
        if token not in text:
            continue
        start = len(text) - len(text.lstrip())
        return (
            text[start:],
            tuple(_style_signature(cell.style) for cell in row[start : len(text)]),
        )
    raise AssertionError(f"{token!r} missing from checkpoint {checkpoint!r}")


def _tools_continuation_indents(
    transcript,
    checkpoint: str,
    *,
    server_name: str,
) -> tuple[int, ...]:
    screen = transcript.checkpoint_cells(checkpoint, rows=ROWS, cols=COLS)
    rows = ["".join(cell.char for cell in row).rstrip() for row in screen.rows]
    server_row = next(
        (
            index
            for index, text in enumerate(rows)
            if text.strip() == f"• {server_name}"
        ),
        None,
    )
    if server_row is None:
        raise AssertionError(
            f"server {server_name!r} missing from checkpoint {checkpoint!r}"
        )
    tools_row = next(
        (
            index
            for index in range(server_row + 1, len(rows))
            if rows[index].lstrip().startswith("• Tools:")
        ),
        None,
    )
    if tools_row is None:
        raise AssertionError(
            f"Tools row for {server_name!r} missing from checkpoint {checkpoint!r}"
        )

    indents: list[int] = []
    for text in rows[tools_row + 1 :]:
        stripped = text.lstrip()
        if not stripped or stripped.startswith("• "):
            break
        indents.append(len(text) - len(stripped))
    if not indents:
        raise AssertionError(
            f"Tools row for {server_name!r} did not wrap in checkpoint {checkpoint!r}"
        )
    return tuple(indents)


def _run_configured_mcp_inventory(
    command: TuiComparisonCommand,
    *,
    label: str,
    artifact_dir: Path,
):
    fixture = _completed_text_response(
        f"resp-{label}-mcp-unused",
        f"msg-{label}-mcp-unused",
        "MCP_INVENTORY_MUST_NOT_REACH_MODEL",
    )
    with _SseFixtureServer(fixture) as server:
        env, temp_home = _isolated_codex_home_env_with_config(
            _configured_mcp_config(server.base_url)
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                command,
                input_steps=(
                    ConptyInputStep(
                        "/mcp",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=30.0,
                        ready_quiet_period=0.8,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_screen_text="/mcp", ready_timeout=10.0),
                    ConptyInputStep(
                        "",
                        ready_screen_text="sandbox_meta",
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        capture_name="mcp-basic",
                    ),
                    ConptyInputStep(
                        "/mcp verbose",
                        ready_screen_text="sandbox_meta",
                        ready_timeout=10.0,
                        ready_quiet_period=0.3,
                        atomic_write=True,
                    ),
                    ConptyInputStep("\r", ready_screen_text="/mcp verbose", ready_timeout=10.0),
                    ConptyInputStep(
                        "",
                        ready_screen_text="memo://codex/{slug}",
                        ready_timeout=30.0,
                        ready_quiet_period=0.5,
                        capture_name="mcp-verbose",
                    ),
                ),
                env=env,
                timeout=2,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = tuple(server.request_bodies)
    transcript.write_artifacts(
        artifact_dir,
        prefix=f"{label}-configured-mcp-inventory",
        rows=ROWS,
        cols=COLS,
    )
    return transcript, requests


def test_mcp_slash_command_uses_extension_inventory_effect_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.MCP]

    assert SlashCommand.MCP.supports_inline_args() is True
    assert SlashCommand.MCP.available_during_task() is True
    assert SlashCommand.MCP.available_in_side_conversation() is False
    assert route.category == "extension"
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"


def test_windows_conpty_native_and_python_mcp_forms_are_local(
    tmp_path: Path,
) -> None:
    # Rust source/test contract:
    # - bare `/mcp` emits FetchMcpInventory(ToolsAndAuthOnly);
    # - `/mcp verbose` emits FetchMcpInventory(Full);
    # - any other inline argument renders the usage line;
    # - none of these paths submits a model turn.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    commands = (
        ("/mcp", "No MCP servers configured"),
        ("/mcp verbose", "No MCP servers configured"),
        ("/mcp full", r"Usage: /mcp \[verbose\]"),
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_repeated_local_slash_candidate(
            command,
            label=label,
            commands_and_effects=commands,
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert "No MCP servers configured" in output
        assert "Usage: /mcp [verbose]" in output
        assert "Traceback" not in output


def test_windows_conpty_configured_mcp_inventory_text_styles_and_verbose_detail_match_rust(
    tmp_path: Path,
) -> None:
    """Compare the real configured inventory, not only the empty-state text.

    Rust owners:
    - ``app::background_requests::fetch_all_mcp_server_statuses`` fetches the
      live server inventory without creating a model turn;
    - ``history_cell::mcp::new_mcp_tools_output_from_statuses`` owns ordering,
      glyphs, styles, and the basic-vs-verbose resource detail contract.
    """

    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)
    rust, rust_requests = _run_configured_mcp_inventory(
        rust_command,
        label="rust",
        artifact_dir=tmp_path,
    )
    python, python_requests = _run_configured_mcp_inventory(
        python_command,
        label="python",
        artifact_dir=tmp_path,
    )

    assert rust_requests == ()
    assert python_requests == ()
    for checkpoint in ("mcp-basic", "mcp-verbose"):
        for token in (
            "/mcp",
            "MCP Tools",
            "alpha",
            "Auth:",
            "Tools:",
            "zeta",
        ):
            assert _row_contract(python, checkpoint, token) == _row_contract(
                rust, checkpoint, token
            ), f"checkpoint={checkpoint!r}, token={token!r}"

    basic_screen = python.checkpoint_screen("mcp-basic", rows=ROWS, cols=COLS)
    rust_basic_screen = rust.checkpoint_screen("mcp-basic", rows=ROWS, cols=COLS)
    assert "Loading MCP inventory" not in rust_basic_screen
    assert "Loading MCP inventory" not in basic_screen
    assert "Resources:" not in basic_screen
    assert "Resource templates:" not in basic_screen

    for transcript in (rust, python):
        assert "Loading MCP inventory" not in transcript.checkpoint_screen(
            "mcp-verbose", rows=ROWS, cols=COLS
        )

    for token in (
        "Resources:",
        "Example Note",
        "memo://codex/example-note",
        "Resource templates:",
        "Codex Memo",
        "memo://codex/{slug}",
    ):
        assert _row_contract(python, "mcp-verbose", token) == _row_contract(
            rust, "mcp-verbose", token
        ), f"checkpoint='mcp-verbose', token={token!r}"


def test_windows_conpty_delayed_mcp_loading_is_visible_only_while_request_is_pending(
    tmp_path: Path,
) -> None:
    """Reproduce the manual long-running MCP inventory lifecycle.

    The real stdio server deliberately delays ``tools/list`` so ConPTY captures
    both the transient loading frame and the completed frame.  A text-only
    final checkpoint cannot prove that the loading cell was ever active, while
    a fast server can complete before the terminal paints that frame.
    """

    native_exe = require_native_slash_comparison()
    _, python_command = slash_candidate_pair(native_exe)
    fixture = _completed_text_response(
        "resp-python-mcp-delay-unused",
        "msg-python-mcp-delay-unused",
        "MCP_DELAY_MUST_NOT_REACH_MODEL",
    )
    with _SseFixtureServer(fixture) as server:
        tools_release_file = tmp_path / "release-tools-list"
        tools_block_file = tmp_path / "block-tools-list"
        env, temp_home = _isolated_codex_home_env_with_config(
            _configured_mcp_config(
                server.base_url,
                tools_list_release_file=tools_release_file,
                tools_list_block_file=tools_block_file,
            )
        )
        with temp_home:
            transcript = run_windows_conpty_tui_command(
                python_command,
                input_steps=(
                    ConptyInputStep(
                        "/mcp",
                        ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                        ready_timeout=40.0,
                        ready_quiet_period=0.5,
                        atomic_write=True,
                        after_ready=lambda: tools_block_file.touch(),
                    ),
                    ConptyInputStep(
                        "\r",
                        ready_screen_text="/mcp",
                        ready_timeout=10.0,
                        ready_quiet_period=0.5,
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text="Loading MCP inventory",
                        # Full-suite Windows startup can spend tens of seconds
                        # loading the configured MCP process before the local
                        # command paints its pending state.  The release-file
                        # handshake still makes completion deterministic once
                        # that real pending frame has been observed.
                        ready_timeout=45.0,
                        after_ready=lambda: tools_release_file.touch(),
                    ),
                    ConptyInputStep(
                        "",
                        ready_screen_text="sandbox_meta",
                        ready_timeout=45.0,
                        ready_quiet_period=0.5,
                        capture_name="mcp-complete",
                    ),
                ),
                env=env,
                timeout=2,
                size=TerminalSize(rows=ROWS, cols=COLS),
            )
        requests = tuple(server.request_bodies)

    transcript.write_artifacts(
        tmp_path,
        prefix="python-delayed-mcp-inventory",
        rows=ROWS,
        cols=COLS,
    )
    complete = transcript.checkpoint_screen("mcp-complete", rows=ROWS, cols=COLS)
    assert "Loading MCP inventory" in transcript.normalized_stdout()
    assert ("Loading MCP inventory",) in transcript.observed_ready_sequences
    assert "Loading MCP inventory" not in complete
    assert "sandbox_meta" in complete
    assert requests == ()


def test_windows_conpty_bundled_node_repl_completion_removes_loading_in_rust_and_python(
    tmp_path: Path,
) -> None:
    """Exercise the same bundled ``node_repl`` server used in manual testing."""

    native_exe = require_native_slash_comparison()
    node_repl_exe = _bundled_node_repl_exe()
    rust_command, python_command = slash_candidate_pair(native_exe)
    transcripts = {}

    for label, command in (("rust", rust_command), ("python", python_command)):
        fixture = _completed_text_response(
            f"resp-{label}-node-repl-unused",
            f"msg-{label}-node-repl-unused",
            "NODE_REPL_MCP_MUST_NOT_REACH_MODEL",
        )
        with _SseFixtureServer(fixture) as server:
            env, temp_home = _isolated_codex_home_env_with_config(
                _node_repl_mcp_config(server.base_url, node_repl_exe)
            )
            with temp_home:
                transcript = run_windows_conpty_tui_command(
                    command,
                    input_steps=(
                        ConptyInputStep(
                            "/mcp",
                            ready_pattern=SESSION_CONFIGURED_COMPOSER_PATTERN,
                            ready_timeout=40.0,
                            ready_quiet_period=0.5,
                            atomic_write=True,
                        ),
                        ConptyInputStep(
                            "\r",
                            ready_screen_text="/mcp",
                            ready_timeout=10.0,
                        ),
                        ConptyInputStep(
                            "",
                            ready_screen_text="js_reset",
                            ready_timeout=40.0,
                            ready_quiet_period=0.5,
                            capture_name="node-repl-complete",
                        ),
                    ),
                    env=env,
                    timeout=2,
                    size=TerminalSize(rows=ROWS, cols=COLS),
                )
            requests = tuple(server.request_bodies)
        transcript.write_artifacts(
            tmp_path,
            prefix=f"{label}-node-repl-mcp-inventory",
            rows=ROWS,
            cols=COLS,
        )
        assert requests == ()
        transcripts[label] = transcript

    for label, transcript in transcripts.items():
        complete = transcript.checkpoint_screen(
            "node-repl-complete", rows=ROWS, cols=COLS
        )
        assert "Loading MCP inventory" not in complete, label
        assert "node_repl" in complete, label
        assert "js_add_node_module_dir" in complete, label
        assert "js_reset" in complete, label

    for token in ("/mcp", "MCP Tools", "node_repl", "Auth:", "Tools:"):
        assert _row_contract(
            transcripts["python"], "node-repl-complete", token
        ) == _row_contract(
            transcripts["rust"], "node-repl-complete", token
        ), token


def test_windows_conpty_effective_mcp_inventory_includes_host_apps_and_configured_server(
    tmp_path: Path,
) -> None:
    """Compare the complete effective inventory, including host-owned Apps.

    Rust owners:
    - ``codex-mcp::mcp::effective_mcp_servers`` merges configured servers with
      the authenticated host-owned ``codex_apps`` server;
    - app-server ``mcpServerStatus/list`` returns that effective set to TUI.

    This deliberately keeps Apps enabled.  The older fixtures disable Apps and
    therefore cannot prove the real authenticated inventory contract.
    """

    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(
        native_exe,
        disable_apps=False,
    )
    bulk_tools = tuple(
        {
            "name": f"bulk_tool_{index:02d}",
            "description": f"Bulk inventory tool {index}",
            "inputSchema": {"type": "object"},
        }
        for index in range(16)
    )
    tools = bulk_tools + (
        {
            "name": "codex_document_control_execute_document_command",
            "description": "Execute a document command",
            "inputSchema": {"type": "object"},
        },
        {
            "name": "github_fetch_issue",
            "description": "Fetch an issue",
            "inputSchema": {"type": "object"},
        },
    )
    apps_server = asyncio.run(AppsTestServer.mount_with_tools(tools))
    try:
        rust, rust_requests = _run_host_apps_inventory(
            rust_command,
            label="rust",
            artifact_dir=tmp_path,
            apps_server=apps_server,
        )
        python, python_requests = _run_host_apps_inventory(
            python_command,
            label="python",
            artifact_dir=tmp_path,
            apps_server=apps_server,
        )
    finally:
        asyncio.run(apps_server.shutdown())

    assert rust_requests == ()
    assert python_requests == ()
    rust_screen = rust.checkpoint_screen("host-apps-complete", rows=ROWS, cols=COLS)
    python_screen = python.checkpoint_screen("host-apps-complete", rows=ROWS, cols=COLS)
    expected_servers = ("codex_apps", "node_repl")
    assert _screen_server_names(rust_screen) == expected_servers
    assert _screen_server_names(python_screen) == expected_servers
    expected_inventory = {
        "codex_apps": {
            "auth": "Bearer token",
            "tools": [
                *(f"bulk_tool_{index:02d}" for index in range(16)),
                "codex_document_control_execute_document_command",
                "github_fetch_issue",
            ],
        },
        "node_repl": {
            "auth": "Unsupported",
            "tools": [
                "cwd",
                "echo",
                "echo-tool",
                "image",
                "image_scenario",
                "sandbox_meta",
                "sync",
                "sync_readonly",
            ],
        },
    }
    rust_inventory = _screen_inventory(rust_screen)
    python_inventory = _screen_inventory(python_screen)
    (tmp_path / "mcp-effective-inventory-diff.json").write_text(
        json.dumps(
            {
                "expected": expected_inventory,
                "rust": rust_inventory,
                "python": python_inventory,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    assert rust_inventory == expected_inventory
    assert python_inventory == expected_inventory
    assert python_inventory == rust_inventory
    for token in (
        "codex_apps",
        "Auth: Bearer token",
        "codex_document_control_execute_document_command",
        "github_fetch_issue",
        "bulk_tool_15",
        "node_repl",
        "sandbox_meta",
    ):
        assert _row_contract(
            python, "host-apps-complete", token
        ) == _row_contract(rust, "host-apps-complete", token), token
    rust_continuation_indents = _tools_continuation_indents(
        rust,
        "host-apps-complete",
        server_name="codex_apps",
    )
    python_continuation_indents = _tools_continuation_indents(
        python,
        "host-apps-complete",
        server_name="codex_apps",
    )
    assert set(rust_continuation_indents) == {4}
    assert python_continuation_indents == rust_continuation_indents, (
        "wrapped /mcp Tools rows must preserve the Rust continuation indentation: "
        f"rust={rust_continuation_indents}, python={python_continuation_indents}"
    )
    for screen in (rust_screen, python_screen):
        assert "Loading MCP inventory" not in screen


def test_windows_conpty_host_apps_tool_is_exposed_called_and_returned_to_model(
    tmp_path: Path,
) -> None:
    """Prove deferred authenticated Codex Apps execution beyond `/mcp` inventory.

    Rust owners:
    - ``core::mcp_tool_exposure`` filters authenticated Codex Apps tools by the
      accessible connector directory and defers inventories of 100+ tools
      behind ``tool_search``;
    - ``core::mcp_tool_call`` routes the namespaced model call back to the raw
      ``codex_apps/github_get_user_login`` MCP tool and returns its result to
      the next model request.
    """

    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(
        native_exe,
        disable_apps=False,
    )
    results = {}
    for label, command in (("rust", rust_command), ("python", python_command)):
        results[label] = _run_host_apps_tool_call(
            command,
            label=label,
            artifact_dir=tmp_path,
        )

    for label in ("rust", "python"):
        transcript, model_requests, apps_calls, final_answer = results[label]
        assert len(model_requests) == 3, (
            f"{label} should make one request for tool_search, one for the MCP "
            f"call, and one for the final answer: {model_requests!r}"
        )
        assert any(
            isinstance(tool, dict) and tool.get("type") == "tool_search"
            for tool in model_requests[0].get("tools", [])
        ), (
            f"{label} should defer the large MCP inventory behind tool_search; "
            "exposed tools: "
            f"{_model_request_tool_identities(model_requests[0])!r}"
        )
        searched_request = json.dumps(model_requests[1])
        assert "tool_search_output" in searched_request
        assert "get_user_login" in searched_request, (
            f"{label} tool_search did not expose github_get_user_login"
        )
        assert "fixture-github-user" in json.dumps(model_requests[2]), (
            f"{label} did not return the successful MCP result to the model"
        )
        tool_calls = [
            call for call in apps_calls if call.get("method") == "tools/call"
        ]
        assert len(tool_calls) == 1, (
            f"{label} should issue exactly one Codex Apps tools/call: {apps_calls!r}"
        )
        assert tool_calls[0].get("params", {}).get("name") == "github_get_user_login"
        screen = transcript.checkpoint_screen(
            "github-tool-call-complete",
            rows=40,
            cols=150,
        )
        assert "Called codex_apps.github_get_user_login" in screen
        assert "fixture-github-user" in screen
        assert final_answer in screen


def test_windows_conpty_apps_enabled_without_chatgpt_auth_does_not_inject_host_server(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(
        native_exe,
        disable_apps=False,
    )
    apps_server = asyncio.run(AppsTestServer.mount())
    try:
        transcripts = {}
        for label, command in (("rust", rust_command), ("python", python_command)):
            transcript, requests = _run_host_apps_inventory(
                command,
                label=f"{label}-unauthenticated",
                artifact_dir=tmp_path,
                apps_server=apps_server,
                authenticated=False,
                ready_text="sandbox_meta",
            )
            assert requests == ()
            transcripts[label] = transcript
    finally:
        calls = asyncio.run(apps_server.recorded_calls())
        asyncio.run(apps_server.shutdown())

    expected = {
        "node_repl": {
            "auth": "Unsupported",
            "tools": [
                "cwd",
                "echo",
                "echo-tool",
                "image",
                "image_scenario",
                "sandbox_meta",
                "sync",
                "sync_readonly",
            ],
        }
    }
    assert calls == []
    for label, transcript in transcripts.items():
        screen = transcript.checkpoint_screen(
            "host-apps-complete", rows=ROWS, cols=COLS
        )
        assert _screen_inventory(screen) == expected, label
        assert "codex_apps" not in screen, label


def test_windows_conpty_failed_mcp_server_remains_in_complete_inventory(
    tmp_path: Path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust_command, python_command = slash_candidate_pair(native_exe)
    transcripts = {}
    for label, command in (("rust", rust_command), ("python", python_command)):
        transcript, requests = _run_failing_mcp_inventory(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        assert requests == ()
        transcripts[label] = transcript

    expected = {"broken": {"auth": "Unsupported", "tools": []}}
    for label, transcript in transcripts.items():
        screen = transcript.checkpoint_screen(
            "broken-mcp-complete", rows=ROWS, cols=COLS
        )
        assert _screen_inventory(screen) == expected, label
        assert "Loading MCP inventory" not in screen, label
    for token in ("• broken", "Auth: Unsupported", "Tools: (none)"):
        assert _row_contract(
            transcripts["python"], "broken-mcp-complete", token
        ) == _row_contract(
            transcripts["rust"], "broken-mcp-complete", token
        ), token
