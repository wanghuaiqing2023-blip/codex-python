from __future__ import annotations

from dataclasses import dataclass

from pycodex.core.context import PluginCapabilitySummary
from pycodex.core.plugins.injection import build_plugin_injections
from pycodex.mcp import CODEX_APPS_MCP_SERVER_NAME
from pycodex.tools.tool_discovery import AppInfo


@dataclass(frozen=True)
class Tool:
    server_name: str
    plugin_display_names: tuple[str, ...]


def _text(item) -> str:
    mapping = item.to_mapping()
    return mapping["content"][0]["text"]


def test_build_plugin_injections_lists_matching_servers_apps_and_skills() -> None:
    # Rust source: codex/codex-rs/core/src/plugins/injection.rs::build_plugin_injections
    # Rust crate/module: codex-core::plugins::injection
    plugin = PluginCapabilitySummary("github@test", "GitHub", has_skills=True)
    items = build_plugin_injections(
        (plugin,),
        (
            Tool("issues", ("GitHub",)),
            Tool("repos", ("Other", "GitHub")),
            Tool(CODEX_APPS_MCP_SERVER_NAME, ("GitHub",)),
        ),
        (
            AppInfo(
                id="pulls",
                name="Pull Requests",
                is_accessible=True,
                is_enabled=True,
                plugin_display_names=("GitHub",),
            ),
            AppInfo(
                id="disabled",
                name="Disabled",
                is_accessible=True,
                is_enabled=False,
                plugin_display_names=("GitHub",),
            ),
        ),
    )

    assert len(items) == 1
    text = _text(items[0])
    assert "Capabilities from the `GitHub` plugin:" in text
    assert "- Skills from this plugin are prefixed with `GitHub:`." in text
    assert "MCP servers from this plugin available in this session: `issues`, `repos`." in text
    assert "Apps from this plugin available in this session: `Pull Requests`." in text
    assert CODEX_APPS_MCP_SERVER_NAME not in text
    assert "Disabled" not in text


def test_build_plugin_injections_uses_plugin_display_names_not_declared_ids() -> None:
    # Rust contract: injection availability is driven by ToolInfo/AppInfo plugin_display_names.
    plugin = PluginCapabilitySummary(
        "sample@test",
        "Sample",
        has_skills=False,
        mcp_server_names=("declared-server",),
        app_connector_ids=("declared-app",),
    )
    items = build_plugin_injections(
        (plugin,),
        (Tool("declared-server", ()),),
        (
            AppInfo(
                id="declared-app",
                name="Declared App",
                is_accessible=True,
                is_enabled=True,
                plugin_display_names=(),
            ),
        ),
    )

    assert items == ()


def test_build_plugin_injections_omits_empty_capability_hints() -> None:
    plugin = PluginCapabilitySummary("sample@test", "Sample")

    assert build_plugin_injections((plugin,), (), ()) == ()
    assert build_plugin_injections((), (), ()) == ()
