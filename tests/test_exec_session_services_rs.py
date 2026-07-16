from pathlib import Path
from uuid import uuid4

import pytest

from pycodex.config import ConfigLayerEntry, ConfigLayerSource, ConfigLayerStack
from pycodex.core.client import ModelClient
from pycodex.core.session.turn.runtime import (
    build_user_turn_responses_request_from_session,
    built_tools,
)
from pycodex.core_plugins import PluginsManager
from pycodex.core_skills import SkillsManager
from pycodex.exec.local_runtime import LocalHttpModelInfo, LocalHttpProvider, create_exec_core_session
from pycodex.exec.session import ExecSessionConfig
from pycodex.mcp import McpConnectionManager
from pycodex.protocol import SessionSource, UserInput


def _skill(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {name}\n---\n", encoding="utf-8")


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
