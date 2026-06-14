from pycodex.core.tools.handlers.multi_agents_spec import (
    SpawnAgentToolOptions,
    create_spawn_agent_tool_v1,
)


def _spawn_agent_description(spec):
    assert spec["type"] == "namespace"
    assert spec["name"] == "multi_agent_v1"
    for tool in spec["tools"]:
        if tool.get("name") == "spawn_agent":
            return tool["description"]
    raise AssertionError("spawn_agent description should be present")


def test_spawn_agent_description_lists_visible_models_and_reasoning_efforts():
    # Rust: core/tests/suite/spawn_agent_description.rs
    # test `spawn_agent_description_lists_visible_models_and_reasoning_efforts`.
    spec = create_spawn_agent_tool_v1(
        SpawnAgentToolOptions(
            include_usage_hint=True,
            available_models=(
                {
                    "model": "visible-model",
                    "description": "Fast and capable",
                    "show_in_picker": True,
                    "default_reasoning_effort": "medium",
                    "supported_reasoning_efforts": (
                        {"effort": "low", "description": "Quick scan"},
                        {"effort": "medium", "description": "Balanced"},
                        {"effort": "high", "description": "Deep dive"},
                    ),
                    "service_tiers": ({"id": "priority", "name": "Fast"},),
                },
                {
                    "model": "hidden-model",
                    "description": "Should not be shown",
                    "show_in_picker": False,
                    "default_reasoning_effort": "low",
                    "supported_reasoning_efforts": ({"effort": "low", "description": "Not visible"},),
                    "service_tiers": (),
                },
            ),
        )
    )

    description = _spawn_agent_description(spec)

    assert "- `visible-model`: Fast and capable" in description
    assert "Available model overrides (optional; inherited parent model is preferred):" in description
    assert (
        "Spawned agents inherit your current model by default. Omit `model` to use that preferred default; "
        "set `model` only when an explicit override is needed."
    ) in description
    assert (
        "Do not set the `model` field unless the user explicitly asks for a different model or there is a clear task-specific reason."
    ) in description
    assert "Reasoning efforts: low, medium (default), high." in description
    assert "Service tiers: priority." in description
    assert "hidden-model" not in description
    assert (
        "Only use `spawn_agent` if and only if the user explicitly asks for sub-agents, delegation, or parallel agent work."
    ) in description
    assert (
        "Requests for depth, thoroughness, research, investigation, or detailed codebase analysis do not count as permission to spawn."
    ) in description
    assert (
        "Agent-role guidance below only helps choose which agent to use after spawning is already authorized; it never authorizes spawning by itself."
    ) in description
    assert "A mini model can solve many tasks faster than the main model." not in description
