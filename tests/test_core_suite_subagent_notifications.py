from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pycodex.core.agent.role import (
    AgentRoleConfig,
    apply_role_to_config,
    build_spawn_agent_role_description,
)
from pycodex.core.hook_runtime import (
    SessionStartTarget,
    StopRequest,
    StopTarget,
    UserPromptSubmitRequest,
)
from pycodex.core.session_prefix import format_subagent_notification_message
from pycodex.core.tools.handlers.multi_agents import V1SpawnAgentArgs
from pycodex.core.tools.handlers.multi_agents_common import (
    apply_requested_spawn_agent_model_overrides,
    build_agent_shared_config,
)
from pycodex.core.tools.handlers.multi_agents_spec import (
    SpawnAgentToolOptions,
    create_spawn_agent_tool_v1,
)
from pycodex.protocol import AgentStatus, ReasoningEffort


class _ModelsManager:
    def list_models(self, _mode):
        return (
            SimpleNamespace(
                model="gpt-5.4",
                supported_reasoning_levels=(SimpleNamespace(effort=ReasoningEffort.LOW),),
                default_reasoning_level=ReasoningEffort.HIGH,
            ),
        )

    def get_model_info(self, model, _config=None):
        assert model == "gpt-5.4"
        return SimpleNamespace(
            supported_reasoning_levels=(SimpleNamespace(effort=ReasoningEffort.LOW),),
            default_reasoning_level=ReasoningEffort.HIGH,
        )


def _tool_parameter_description(tool, parameter_name):
    return tool["parameters"]["properties"][parameter_name]["description"]


def _role_block(description: str, role_name: str) -> str:
    header = f"{role_name}: {{"
    lines = description.splitlines()
    start = lines.index(header)
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.endswith(": {"):
            break
        block.append(line)
        if line == "}":
            break
    return "\n".join(block)


def test_subagent_start_replaces_session_start_and_injects_context():
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `subagent_start_replaces_session_start_and_injects_context`.
    target = SessionStartTarget.subagent_start(
        turn_id="turn-1",
        agent_id="agent-1",
        agent_type="worker",
    )
    submit = UserPromptSubmitRequest(
        session_id="session",
        turn_id="turn-1",
        subagent={"agent_id": "agent-1", "agent_type": "worker"},
        cwd="C:/work",
        transcript_path="parent.jsonl",
        model="gpt-test",
        permission_mode="never",
        prompt="child: do work",
    )

    assert target.type == "subagent_start"
    assert target.source is None
    assert target.agent_id == "agent-1"
    assert submit.subagent == {"agent_id": "agent-1", "agent_type": "worker"}


def test_subagent_stop_replaces_stop_and_skips_internal_subagents():
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `subagent_stop_replaces_stop_and_skips_internal_subagents`.
    target = StopTarget.subagent_stop(
        agent_id="agent-1",
        agent_type="worker",
        agent_transcript_path="agent.jsonl",
    )
    request = StopRequest(
        session_id="session",
        turn_id="turn-1",
        cwd="C:/work",
        transcript_path="parent.jsonl",
        model="gpt-test",
        permission_mode="never",
        stop_hook_active=True,
        last_assistant_message="child done first",
        target=target,
    )
    internal_stop = StopTarget.stop()

    assert request.target.type == "subagent_stop"
    assert request.target.agent_transcript_path == "agent.jsonl"
    assert request.transcript_path != request.target.agent_transcript_path
    assert request.last_assistant_message == "child done first"
    assert internal_stop.type == "stop"


def test_subagent_notification_is_included_without_wait():
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `subagent_notification_is_included_without_wait`.
    rendered = format_subagent_notification_message(
        "agent-a",
        AgentStatus.completed("child done"),
    )

    assert "<subagent_notification>" in rendered
    assert '"agent_path":"agent-a"' in rendered
    assert '"status":{"completed":"child done"}' in rendered


def test_spawned_child_receives_forked_parent_context():
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `spawned_child_receives_forked_parent_context`.
    args = V1SpawnAgentArgs.from_json(
        '{"message":"child: do work","fork_context":true}'
    )

    assert args.fork_context is True
    assert args.input_items()[0].to_mapping() == {
        "type": "text",
        "text": "child: do work",
    }


def test_spawn_agent_requested_model_and_reasoning_override_inherited_settings_without_role():
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `spawn_agent_requested_model_and_reasoning_override_inherited_settings_without_role`.
    session = SimpleNamespace(models_manager=_ModelsManager())
    turn = SimpleNamespace(model_info=SimpleNamespace(slug="gpt-5.3-codex"))
    config = {"model": "gpt-5.3-codex", "model_reasoning_effort": ReasoningEffort.XHIGH}

    apply_requested_spawn_agent_model_overrides(
        session,
        turn,
        config,
        requested_model="gpt-5.4",
        requested_reasoning_effort=ReasoningEffort.LOW,
    )

    assert config["model"] == "gpt-5.4"
    assert config["model_reasoning_effort"] is ReasoningEffort.LOW


def test_spawned_multi_agent_v2_child_inherits_parent_developer_context():
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `spawned_multi_agent_v2_child_inherits_parent_developer_context`.
    turn = SimpleNamespace(
        config={"model": "gpt-parent"},
        model_info=SimpleNamespace(slug="gpt-parent"),
        provider=None,
        reasoning_effort=None,
        developer_instructions="Parent developer instructions.",
    )

    config = build_agent_shared_config(turn)

    assert config["developer_instructions"] == "Parent developer instructions."


def test_skills_toggle_skips_instructions_for_parent_and_spawned_child():
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `skills_toggle_skips_instructions_for_parent_and_spawned_child`.
    turn = SimpleNamespace(
        config={"include_skill_instructions": False, "model": "gpt-parent"},
        model_info=SimpleNamespace(slug="gpt-parent"),
        provider=None,
        reasoning_effort=None,
    )

    config = build_agent_shared_config(turn)

    assert config["include_skill_instructions"] is False


def test_spawn_agent_role_overrides_requested_model_and_reasoning_settings(tmp_path):
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `spawn_agent_role_overrides_requested_model_and_reasoning_settings`.
    role_path = tmp_path / "custom-role.toml"
    role_path.write_text(
        'developer_instructions = "Stay focused"\n'
        'model = "gpt-5.4"\n'
        'model_reasoning_effort = "high"\n',
        encoding="utf-8",
    )
    config = SimpleNamespace(
        codex_home=tmp_path,
        model="gpt-5.3-codex",
        model_reasoning_effort=ReasoningEffort.XHIGH,
        agent_roles={"custom": AgentRoleConfig(description="Custom role", config_file=role_path)},
        config_layer_stack=[],
    )

    apply_role_to_config(config, "custom")

    assert config.model == "gpt-5.4"
    assert config.model_reasoning_effort == "high"


def test_spawn_agent_tool_description_mentions_role_locked_settings(tmp_path):
    # Rust: core/tests/suite/subagent_notifications.rs
    # test `spawn_agent_tool_description_mentions_role_locked_settings`.
    role_path = tmp_path / "custom-role.toml"
    role_path.write_text(
        'developer_instructions = "Stay focused"\n'
        'model = "gpt-5.4"\n'
        'model_reasoning_effort = "high"\n',
        encoding="utf-8",
    )
    description = build_spawn_agent_role_description(
        {"custom": AgentRoleConfig(description="Custom role", config_file=role_path)}
    )
    spec = create_spawn_agent_tool_v1(
        SpawnAgentToolOptions(agent_type_description=description)
    )
    spawn_agent = spec["tools"][0]
    agent_type_description = _tool_parameter_description(spawn_agent, "agent_type")

    assert _role_block(agent_type_description, "custom") == (
        "custom: {\n"
        "Custom role\n"
        "- This role's model is set to `gpt-5.4` and its reasoning effort is set to `high`. "
        "These settings cannot be changed.\n"
        "}"
    )

