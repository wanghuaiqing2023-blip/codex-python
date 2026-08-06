import json
from pathlib import Path
from uuid import uuid4

import pytest

from pycodex.config import ConfigLayerEntry, ConfigLayerSource, ConfigLayerStack
from pycodex.core.client import ModelClient
from pycodex.core import ToolInfo
from pycodex.core.hook_runtime import run_user_prompt_submit_hooks
from pycodex.core.session.turn.runtime import (
    build_user_turn_responses_request_from_session,
    built_tools,
)
from pycodex.core_plugins import PluginsManager
from pycodex.core_skills import SkillsManager
from pycodex.exec.local_runtime import LocalHttpModelInfo, LocalHttpProvider, create_exec_core_session
from pycodex.exec.session import ExecSessionConfig
from pycodex.codex_mcp import McpConnectionManager
from pycodex.features import Feature, Features
from pycodex.protocol import ResponseItem, SessionSource, Tool, UserInput


def _skill(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {name}\n---\n", encoding="utf-8")


def test_product_session_services_owns_model_client(tmp_path: Path, monkeypatch) -> None:
    # Rust: codex-core::state::service::SessionServices owns the ModelClient
    # used by session::turn to activate the WebSocket-to-HTTP fallback.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    config = ExecSessionConfig(model="gpt-test", model_provider_id="openai", cwd=tmp_path)
    model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
    model_client = ModelClient(
        session_id="session",
        thread_id=str(uuid4()),
        installation_id="install",
    )

    session = create_exec_core_session(config, model_info, model_client=model_client)

    assert session.services.model_client is model_client


@pytest.mark.asyncio
async def test_product_session_services_runs_configured_user_prompt_submit_hook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Rust: codex-core::session::session::build_hooks_for_config installs the
    # registry in SessionServices, and hook_runtime::run_user_prompt_submit_hooks
    # executes it before sampling.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    audit_log = tmp_path / "hook-audit.jsonl"
    hook_script = tmp_path / "audit_hook.py"
    hook_script.write_text(
        "from pathlib import Path\n"
        "import json\n"
        "import sys\n"
        "payload = json.load(sys.stdin)\n"
        f"Path({str(audit_log)!r}).write_text(json.dumps(payload), encoding='utf-8')\n"
        "print(json.dumps({'hookSpecificOutput': {"
        "'hookEventName': 'UserPromptSubmit', "
        "'additionalContext': 'session hook context'}}))\n",
        encoding="utf-8",
    )
    command = f'python -B "{hook_script}"'
    stack = ConfigLayerStack.new(
        (
            ConfigLayerEntry.new(
                ConfigLayerSource.user(codex_home / "config.toml"),
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": command,
                                        "commandWindows": command,
                                    }
                                ]
                            }
                        ]
                    }
                },
            ),
        )
    )
    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=tmp_path,
        bypass_hook_trust=True,
        config_layer_stack=stack,
    )
    session = create_exec_core_session(
        config,
        LocalHttpModelInfo(slug="gpt-test", base_instructions="base"),
        thread_id="thread-hooks",
    )

    turn = await session.new_default_turn()
    outcome = await run_user_prompt_submit_hooks(
        session,
        turn,
        prompt="audit this prompt",
    )

    assert outcome is not None
    assert outcome.should_stop is False
    assert outcome.additional_contexts == ("session hook context",)
    assert json.loads(audit_log.read_text(encoding="utf-8"))["prompt"] == "audit this prompt"
    assert [event.type for event in session.emitted_events[-2:]] == [
        "hook_started",
        "hook_completed",
    ]


@pytest.mark.asyncio
async def test_product_session_turn_context_carries_provider_capabilities_and_auth_manager(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Rust: codex-core::session::turn_context::make_turn_context creates a
    # SharedModelProvider and stores it with auth_manager on every TurnContext.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    config = ExecSessionConfig(model="gpt-test", model_provider_id="openai", cwd=tmp_path)
    model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
    transport_provider = LocalHttpProvider(base_url="https://api.example.test/v1")
    auth_manager = object()
    session = create_exec_core_session(
        config,
        model_info,
        provider=transport_provider,
        auth_manager=auth_manager,
    )

    turn = await session.new_default_turn()
    router = await built_tools(session, turn)

    assert turn.provider is session.provider
    assert turn.provider is not transport_provider
    assert turn.provider.capabilities().web_search is True
    assert turn.auth_manager is auth_manager
    assert {
        "type": "web_search",
        "external_web_access": False,
    } in router.model_visible_specs()


@pytest.mark.asyncio
async def test_product_session_reuses_managers_config_and_router_across_turns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Rust: codex-core/src/session/turn_context.rs::new_default_turn_with_sub_id
    # and codex-core/src/session/turn.rs::built_tools.
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    _skill(codex_home / "skills" / "local" / "SKILL.md", "local-skill")
    stack = ConfigLayerStack.new(
        (
            ConfigLayerEntry.new(ConfigLayerSource.user(codex_home / "config.toml"), {}),
        )
    )
    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=tmp_path,
        config_layer_stack=stack,
        mcp_servers={"docs": {"url": "https://example.test/mcp"}},
    )
    model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base")
    session = create_exec_core_session(config, model_info)

    assert isinstance(session.services.plugins_manager, PluginsManager)
    assert isinstance(session.services.skills_manager, SkillsManager)
    assert isinstance(session.services.mcp_connection_manager, McpConnectionManager)
    manager_ids = (
        id(session.services.plugins_manager),
        id(session.services.skills_manager),
        id(session.services.mcp_connection_manager),
    )

    first = await session.new_default_turn()
    first_router = await built_tools(session, first)
    await session.record_context_updates_and_set_reference_context_item(first)
    second = await session.new_default_turn()
    second_router = await built_tools(session, second)

    assert isinstance(first.config, ExecSessionConfig)
    assert first.config.config_layer_stack is stack
    assert "local-skill" in {skill.name for skill in first.turn_skills.outcome.skills}
    developer_text = "\n".join(
        content.text
        for item in session.history
        if item.type == "message" and item.role == "developer"
        for content in item.content
        if getattr(content, "text", None)
    )
    assert "local-skill" in developer_text
    assert manager_ids == (
        id(session.services.plugins_manager),
        id(session.services.skills_manager),
        id(session.services.mcp_connection_manager),
    )
    first_names = {spec["name"] for spec in first_router.model_visible_specs()}
    second_names = {spec["name"] for spec in second_router.model_visible_specs()}
    assert {
        "list_mcp_resources",
        "list_mcp_resource_templates",
        "read_mcp_resource",
    }.issubset(first_names)
    assert first_names == second_names


@pytest.mark.asyncio
async def test_product_session_exposes_codex_apps_tools_when_exec_config_enables_apps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Rust: codex-core::session::turn::built_tools uses TurnContext::apps_enabled,
    # whose product-session state is backed by Config::features plus ChatGPT auth.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    features = Features.with_defaults().enable(Feature.APPS)
    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=tmp_path,
        features=features,
    )

    class ChatGptAuthManager:
        def current_auth_uses_codex_backend(self):
            return True

    session = create_exec_core_session(
        config,
        LocalHttpModelInfo(slug="gpt-test", base_instructions="base"),
        auth_manager=ChatGptAuthManager(),
    )
    app_tool = ToolInfo(
        server_name="codex_apps",
        callable_namespace="mcp__codex_apps__github",
        callable_name="_get_user_login",
        tool=Tool(
            name="github_get_user_login",
            description="Return the authenticated GitHub login.",
            input_schema={"type": "object", "properties": {}},
        ),
        connector_id="connector_github",
        connector_name="GitHub",
    )

    class AppsMcpManager:
        def __init__(self):
            self.calls = []

        async def list_all_tools(self):
            return (app_tool,)

        async def has_servers(self):
            return True

        async def call_tool(self, server, tool_name, arguments, meta):
            self.calls.append((server, tool_name, arguments, meta))
            return {
                "content": [{"type": "text", "text": "fixture-github-user"}],
                "isError": False,
            }

    mcp_manager = AppsMcpManager()
    session.services.mcp_connection_manager = mcp_manager

    turn = await session.new_default_turn()
    router = await built_tools(session, turn)

    assert turn.config.apps_enabled() is False
    assert turn.apps_enabled() is True
    assert any(
        spec.get("type") == "namespace"
        and spec.get("name") == "mcp__codex_apps__github"
        and any(tool.get("name") == "_get_user_login" for tool in spec.get("tools", ()))
        for spec in router.model_visible_specs()
    )
    call = router.build_tool_call(
        ResponseItem.function_call(
            "_get_user_login",
            "{}",
            "call-github-login",
            namespace="mcp__codex_apps__github",
        )
    )
    assert call is not None
    output = await router.dispatch_tool_call_with_terminal_outcome(call)
    assert output.result.result.content == (
        {"type": "text", "text": "fixture-github-user"},
    )
    assert mcp_manager.calls == [
        ("codex_apps", "github_get_user_login", {}, None)
    ]


@pytest.mark.asyncio
async def test_product_tui_request_plan_uses_cli_session_and_core_tool_router(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Rust crate/module anchors:
    # - codex-tui::app_server_session starts threads with SessionSource::Cli.
    # - codex-core::session::turn::built_tools registers core Goal handlers.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    config = ExecSessionConfig(
        model="gpt-test",
        model_provider_id="openai",
        cwd=tmp_path,
        user_instructions="project instructions",
        developer_instructions="configured developer instructions",
    )
    model_info = LocalHttpModelInfo(slug="gpt-test", base_instructions="base instructions")
    session = create_exec_core_session(
        config,
        model_info,
        thread_id=str(uuid4()),
        state_db=object(),
    )
    client = ModelClient(
        session_id="session",
        thread_id=str(uuid4()),
        installation_id="install",
        session_source=SessionSource.cli(),
    )

    plan = await build_user_turn_responses_request_from_session(
        session,
        (UserInput.text_input("inspect parity"),),
        client,
        {"base_url": "https://example.test/v1"},
        model_info,
    )
    turn = await session.new_default_turn()
    router = await built_tools(session, turn)

    assert session.session_source == SessionSource.cli()
    assert turn.session_source == SessionSource.cli()
    assert plan.prompt.base_instructions.text == "base instructions"
    role_text = [
        (
            item.role,
            "\n".join(
                content.text
                for content in item.content
                if isinstance(getattr(content, "text", None), str)
            ),
        )
        for item in plan.prompt.input
        if item.type == "message"
    ]
    assert any(role == "developer" and "configured developer instructions" in text for role, text in role_text)
    assert any(role == "user" and "<environment_context>" in text for role, text in role_text)
    assert role_text[-1] == ("user", "inspect parity")

    assert session.services.extensions.tool_contributors() == ()
    model_visible_names = {spec["name"] for spec in router.model_visible_specs()}
    request_names = {spec["name"] for spec in plan.prompt.tools}
    assert {"get_goal", "create_goal", "update_goal"}.issubset(model_visible_names)
    assert request_names == {spec["name"] for spec in plan.request["tools"]}
    assert model_visible_names == request_names
