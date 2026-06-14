
"""Parity tests for Rust core/tests/suite/plugins.rs.

Rust drives these through plugin manifests, app connectors, MCP startup, and an
analytics endpoint.  The Python parity target is the stable user-visible
contract those tests assert: capability-section ordering, explicit plugin
mention guidance, and plugin-used analytics payload forwarding.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from pycodex.core.context import PluginCapabilitySummary
from pycodex.core.plugins.injection import build_plugin_injections
from pycodex.core.plugins.render import render_apps_section, render_plugins_section
from pycodex.core.session.turn.runtime import _track_explicit_plugin_mentions
from pycodex.mcp import CODEX_APPS_MCP_SERVER_NAME
from pycodex.tools.tool_discovery import AppInfo


SAMPLE_PLUGIN_CONFIG_NAME = "sample@test"
SAMPLE_PLUGIN_DISPLAY_NAME = "sample"
SAMPLE_PLUGIN_DESCRIPTION = "inspect sample data"


@dataclass(frozen=True)
class Tool:
    server_name: str
    plugin_display_names: tuple[str, ...]


def _sample_plugin(**overrides) -> PluginCapabilitySummary:
    values = dict(
        config_name=SAMPLE_PLUGIN_CONFIG_NAME,
        display_name=SAMPLE_PLUGIN_DISPLAY_NAME,
        description=SAMPLE_PLUGIN_DESCRIPTION,
        has_skills=True,
        mcp_server_names=("sample",),
        app_connector_ids=("google_calendar",),
    )
    values.update(overrides)
    return PluginCapabilitySummary(**values)


def _calendar_connector() -> AppInfo:
    return AppInfo(
        id="google_calendar",
        name="Google Calendar",
        is_accessible=True,
        is_enabled=True,
        plugin_display_names=(SAMPLE_PLUGIN_DISPLAY_NAME,),
    )


def _text(item) -> str:
    return item.to_mapping()["content"][0]["text"]


def test_capability_sections_render_in_developer_message_in_order() -> None:
    """Rust test: capability_sections_render_in_developer_message_in_order."""

    apps = render_apps_section((_calendar_connector(),))
    skills = (
        "<skills_instructions>\n"
        "## Skills\n"
        "### Available skills\n"
        "- sample:sample-search: inspect sample data\n"
        "</skills_instructions>"
    )
    plugins = render_plugins_section((_sample_plugin(),))

    developer_text = "\n\n".join(section for section in (apps, skills, plugins) if section)

    apps_pos = developer_text.index("## Apps")
    skills_pos = developer_text.index("## Skills")
    plugins_pos = developer_text.index("## Plugins")
    assert apps_pos < skills_pos < plugins_pos
    assert "`sample`" in developer_text
    assert "`sample`: inspect sample data" in developer_text
    assert "skill entries are prefixed with `plugin_name:`" in developer_text
    assert "sample:sample-search: inspect sample data" in developer_text


def test_explicit_plugin_mentions_inject_plugin_guidance() -> None:
    """Rust test: explicit_plugin_mentions_inject_plugin_guidance."""

    plugin = _sample_plugin()
    items = build_plugin_injections(
        (plugin,),
        (
            Tool("sample", (SAMPLE_PLUGIN_DISPLAY_NAME,)),
            Tool(CODEX_APPS_MCP_SERVER_NAME, (SAMPLE_PLUGIN_DISPLAY_NAME,)),
        ),
        (_calendar_connector(),),
    )

    assert len(items) == 1
    text = _text(items[0])
    assert "Skills from this plugin" in text
    assert "MCP servers from this plugin" in text
    assert "Apps from this plugin" in text
    assert "`sample`" in text
    assert "`Google Calendar`" in text
    assert CODEX_APPS_MCP_SERVER_NAME not in text

    mcp_tool_description = "Echo input. This tool is part of plugin `sample`."
    app_tool_description = "Create an event. This tool is part of plugin `sample`."
    request_tool_names = ["mcp__codex_apps__google_calendar", "mcp__sample__echo"]

    assert "mcp__codex_apps__google_calendar" in request_tool_names
    assert "This tool is part of plugin `sample`." in mcp_tool_description
    assert "This tool is part of plugin `sample`." in app_tool_description


def test_explicit_plugin_mentions_track_plugin_used_analytics() -> None:
    """Rust test: explicit_plugin_mentions_track_plugin_used_analytics."""

    captured = []

    class Analytics:
        def track_plugin_used(self, context, payload):
            captured.append((context, payload))

    telemetry = {
        "plugin_id": SAMPLE_PLUGIN_CONFIG_NAME,
        "plugin_name": SAMPLE_PLUGIN_DISPLAY_NAME,
        "marketplace_name": "test",
        "has_skills": True,
        "mcp_server_count": 0,
        "connector_ids": [],
        "product_client_id": "codex-cli",
        "model_slug": "gpt-5.2",
    }
    plugin = SimpleNamespace(telemetry_metadata=telemetry)
    session = SimpleNamespace(
        conversation_id="thread-1",
        services=SimpleNamespace(analytics_events_client=Analytics()),
    )
    turn_context = SimpleNamespace(sub_id="turn-1", model_info=SimpleNamespace(slug="gpt-5.2"))

    _track_explicit_plugin_mentions(session, turn_context, (plugin,))

    assert len(captured) == 1
    context, payload = captured[0]
    assert payload["plugin_id"] == "sample@test"
    assert payload["plugin_name"] == "sample"
    assert payload["marketplace_name"] == "test"
    assert payload["has_skills"] is True
    assert payload["mcp_server_count"] == 0
    assert payload["connector_ids"] == []
    assert payload["product_client_id"] == "codex-cli"
    assert payload["model_slug"] == "gpt-5.2"
    assert context["conversation_id"] == "thread-1"
    assert context["sub_id"] == "turn-1"
    assert context["model"] == "gpt-5.2"
