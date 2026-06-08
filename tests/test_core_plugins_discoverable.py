from dataclasses import dataclass, field

import pytest

from pycodex.core.config.edit import ToolSuggestDiscoverableType, ToolSuggestDisabledTool
from pycodex.core.plugins.discoverable import (
    TOOL_SUGGEST_DISCOVERABLE_MARKETPLACE_ALLOWLIST,
    list_tool_suggest_discoverable_plugins,
)
from pycodex.core_plugins import (
    OPENAI_BUNDLED_MARKETPLACE_NAME,
    OPENAI_CURATED_MARKETPLACE_NAME,
    ConfiguredMarketplace,
    ConfiguredMarketplaceListOutcome,
    ConfiguredMarketplacePlugin,
    PluginDetail,
)
from pycodex.features import Feature
from pycodex.tools import DiscoverablePluginInfo


@dataclass
class Features:
    plugins_enabled: bool = True

    def enabled(self, feature):
        return feature is Feature.PLUGINS and self.plugins_enabled


@dataclass
class ToolSuggest:
    discoverables: list[object] = field(default_factory=list)
    disabled_tools: list[object] = field(default_factory=list)


@dataclass
class Config:
    features: Features = field(default_factory=Features)
    tool_suggest: ToolSuggest = field(default_factory=ToolSuggest)
    codex_home: str = "/codex-home"

    def plugins_config_input(self):
        return {"source": "config"}


class FakePluginsManager:
    def __init__(self, marketplaces, details=None, failures=None):
        self.marketplaces = marketplaces
        self.details = details or {}
        self.failures = set(failures or ())
        self.list_calls = 0
        self.read_calls = []

    def list_marketplaces_for_config(self, plugins_input, extra):
        self.list_calls += 1
        assert plugins_input == {"source": "config"}
        assert extra == []
        return ConfiguredMarketplaceListOutcome(list(self.marketplaces))

    async def read_plugin_detail_for_marketplace_plugin(self, plugins_input, marketplace_name, plugin):
        plugin_id = plugin.id if "@" in plugin.id else f"{plugin.id}@{marketplace_name}"
        self.read_calls.append(plugin_id)
        if plugin_id in self.failures:
            raise OSError("broken plugin")
        return self.details.get(
            plugin_id,
            PluginDetail(
                id=plugin_id,
                name=plugin.name,
                description="Plugin that includes skills, MCP servers, and app connectors",
                skills=["skill"],
                mcp_server_names=["sample-docs"],
                apps=[{"connector_id": "connector_calendar"}],
            ),
        )


def marketplace(name, plugin_names):
    return ConfiguredMarketplace(
        name=name,
        path=f"/marketplaces/{name}/marketplace.json",
        plugins=[
            ConfiguredMarketplacePlugin(
                id=f"{plugin_name}@{name}",
                name=plugin_name,
            )
            for plugin_name in plugin_names
        ],
    )


@pytest.mark.asyncio
async def test_returns_uninstalled_curated_allowlisted_plugins_sorted_by_name():
    # Rust test: list_tool_suggest_discoverable_plugins_returns_uninstalled_curated_plugins.
    manager = FakePluginsManager(
        [
            marketplace(
                OPENAI_CURATED_MARKETPLACE_NAME,
                ["sample", "slack", "openai-developers"],
            )
        ]
    )

    result = await list_tool_suggest_discoverable_plugins(Config(), manager)

    assert result == [
        DiscoverablePluginInfo(
            id="openai-developers@openai-curated",
            name="openai-developers",
            description="Plugin that includes skills, MCP servers, and app connectors",
            has_skills=True,
            mcp_server_names=("sample-docs",),
            app_connector_ids=("connector_calendar",),
        ),
        DiscoverablePluginInfo(
            id="slack@openai-curated",
            name="slack",
            description="Plugin that includes skills, MCP servers, and app connectors",
            has_skills=True,
            mcp_server_names=("sample-docs",),
            app_connector_ids=("connector_calendar",),
        ),
    ]
    assert manager.read_calls == [
        "slack@openai-curated",
        "openai-developers@openai-curated",
    ]


@pytest.mark.asyncio
async def test_microsoft_curated_plugins_are_allowlisted_and_sorted():
    # Rust test: list_tool_suggest_discoverable_plugins_returns_microsoft_curated_plugins.
    manager = FakePluginsManager(
        [
            marketplace(
                OPENAI_CURATED_MARKETPLACE_NAME,
                ["teams", "sharepoint", "outlook-email", "outlook-calendar"],
            )
        ]
    )

    result = await list_tool_suggest_discoverable_plugins(Config(), manager)

    assert [plugin.id for plugin in result] == [
        "outlook-calendar@openai-curated",
        "outlook-email@openai-curated",
        "sharepoint@openai-curated",
        "teams@openai-curated",
    ]


@pytest.mark.asyncio
async def test_configured_plugin_id_is_included_and_deduplicated():
    # Rust tests: configured plugin ids are included and allowlisted duplicates do not duplicate.
    config = Config(
        tool_suggest=ToolSuggest(
            discoverables=[
                {"type": "plugin", "id": "sample@openai-curated"},
                {"type": "connector", "id": "connector_calendar"},
            ]
        )
    )
    manager = FakePluginsManager([marketplace(OPENAI_CURATED_MARKETPLACE_NAME, ["sample", "slack"])])

    result = await list_tool_suggest_discoverable_plugins(config, manager)

    assert [plugin.id for plugin in result] == [
        "sample@openai-curated",
        "slack@openai-curated",
    ]
    assert manager.read_calls.count("sample@openai-curated") == 1


@pytest.mark.asyncio
async def test_filters_feature_disabled_installed_disabled_and_non_allowlisted_marketplaces():
    # Rust tests: feature disabled, installed curated plugins, disabled suggestions, and marketplace allowlist.
    disabled = await list_tool_suggest_discoverable_plugins(
        Config(features=Features(plugins_enabled=False)),
        FakePluginsManager([marketplace(OPENAI_CURATED_MARKETPLACE_NAME, ["slack"])]),
    )
    assert disabled == []

    installed_marketplace = ConfiguredMarketplace(
        name=OPENAI_CURATED_MARKETPLACE_NAME,
        path="/marketplaces/openai-curated/marketplace.json",
        plugins=[ConfiguredMarketplacePlugin(id="slack@openai-curated", name="slack", installed=True)],
    )
    hidden_marketplace = marketplace("community", ["slack"])
    disabled_config = Config(
        tool_suggest=ToolSuggest(
            disabled_tools=[ToolSuggestDisabledTool(ToolSuggestDiscoverableType.PLUGIN, "github@openai-curated")]
        )
    )
    manager = FakePluginsManager(
        [
            installed_marketplace,
            hidden_marketplace,
            marketplace(OPENAI_CURATED_MARKETPLACE_NAME, ["github"]),
        ]
    )

    result = await list_tool_suggest_discoverable_plugins(disabled_config, manager)

    assert result == []
    assert manager.read_calls == []


@pytest.mark.asyncio
async def test_bundled_allowlist_missing_plugin_is_ignored_and_description_is_normalized():
    # Rust tests: missing allowlisted plugins are ignored; descriptions are normalized.
    details = {
        "chrome@openai-bundled": PluginDetail(
            id="chrome@openai-bundled",
            name="chrome",
            description="  Plugin\n   with   extra   spacing  ",
            skills=["skill"],
        )
    }
    manager = FakePluginsManager(
        [marketplace(OPENAI_BUNDLED_MARKETPLACE_NAME, ["chrome"])],
        details=details,
    )

    result = await list_tool_suggest_discoverable_plugins(Config(), manager)

    assert TOOL_SUGGEST_DISCOVERABLE_MARKETPLACE_ALLOWLIST == (
        OPENAI_BUNDLED_MARKETPLACE_NAME,
        OPENAI_CURATED_MARKETPLACE_NAME,
    )
    assert result == [
        DiscoverablePluginInfo(
            id="chrome@openai-bundled",
            name="chrome",
            description="Plugin with extra spacing",
            has_skills=True,
        )
    ]


@pytest.mark.asyncio
async def test_detail_load_failures_are_skipped_and_marketplace_list_is_loaded_once(caplog):
    # Rust test: read failures warn and do not reload marketplace per plugin.
    manager = FakePluginsManager(
        [
            marketplace(
                OPENAI_CURATED_MARKETPLACE_NAME,
                ["slack", "openai-developers"],
            )
        ],
        failures={"openai-developers@openai-curated"},
    )

    result = await list_tool_suggest_discoverable_plugins(Config(), manager)

    assert [plugin.id for plugin in result] == ["slack@openai-curated"]
    assert manager.list_calls == 1
    assert "failed to load discoverable plugin suggestion openai-developers@openai-curated" in caplog.text
