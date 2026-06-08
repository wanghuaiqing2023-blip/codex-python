"""Python interface for Rust ``codex-core-plugins``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


OPENAI_CURATED_MARKETPLACE_NAME = "openai-curated"
OPENAI_BUNDLED_MARKETPLACE_NAME = "openai-bundled"
TOOL_SUGGEST_DISCOVERABLE_PLUGIN_ALLOWLIST = (
    "github@openai-curated",
    "notion@openai-curated",
    "slack@openai-curated",
    "gmail@openai-curated",
    "google-calendar@openai-curated",
    "google-drive@openai-curated",
    "openai-developers@openai-curated",
    "canva@openai-curated",
    "teams@openai-curated",
    "sharepoint@openai-curated",
    "outlook-email@openai-curated",
    "outlook-calendar@openai-curated",
    "linear@openai-curated",
    "figma@openai-curated",
    "chrome@openai-bundled",
    "computer-use@openai-bundled",
)


@dataclass(frozen=True)
class PluginsConfigInput:
    config_layer_stack: Any
    plugins_enabled: bool
    remote_plugin_enabled: bool
    chatgpt_base_url: str

    @classmethod
    def new(
        cls,
        config_layer_stack: Any,
        plugins_enabled: bool,
        remote_plugin_enabled: bool,
        chatgpt_base_url: str,
    ) -> "PluginsConfigInput":
        return cls(config_layer_stack, plugins_enabled, remote_plugin_enabled, chatgpt_base_url)


@dataclass(frozen=True)
class PluginInstallRequest:
    plugin_name: str
    marketplace_path: Any


@dataclass(frozen=True)
class PluginReadRequest:
    plugin_name: str
    marketplace_path: Any


@dataclass(frozen=True)
class PluginInstallOutcome:
    plugin_id: Any
    plugin_version: str
    installed_path: Any
    auth_policy: Any


@dataclass(frozen=True)
class PluginReadOutcome:
    marketplace_name: str
    marketplace_path: Any | None
    plugin: "PluginDetail"


@dataclass(frozen=True)
class PluginHookSummary:
    key: str
    event_name: Any


class PluginDetailsUnavailableReason(str, Enum):
    INSTALL_REQUIRED_FOR_REMOTE_SOURCE = "install_required_for_remote_source"


@dataclass(frozen=True)
class PluginDetail:
    id: str
    name: str
    local_version: str | None = None
    description: str | None = None
    source: Any | None = None
    policy: Any | None = None
    interface: Any | None = None
    keywords: list[str] = field(default_factory=list)
    installed: bool = False
    enabled: bool = False
    skills: list[Any] = field(default_factory=list)
    disabled_skill_paths: set[Any] = field(default_factory=set)
    hooks: list[PluginHookSummary] = field(default_factory=list)
    apps: list[Any] = field(default_factory=list)
    mcp_server_names: list[str] = field(default_factory=list)
    details_unavailable_reason: PluginDetailsUnavailableReason | None = None


@dataclass(frozen=True)
class ConfiguredMarketplacePlugin:
    id: str
    name: str
    local_version: str | None = None
    installed_version: str | None = None
    source: Any | None = None
    policy: Any | None = None
    interface: Any | None = None
    keywords: list[str] = field(default_factory=list)
    installed: bool = False
    enabled: bool = False


@dataclass(frozen=True)
class ConfiguredMarketplace:
    name: str
    path: Any
    interface: Any | None = None
    plugins: list[ConfiguredMarketplacePlugin] = field(default_factory=list)


@dataclass(frozen=True)
class ConfiguredMarketplaceListOutcome:
    marketplaces: list[ConfiguredMarketplace] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class RemotePluginSyncResult:
    installed_plugin_ids: list[str] = field(default_factory=list)
    enabled_plugin_ids: list[str] = field(default_factory=list)
    disabled_plugin_ids: list[str] = field(default_factory=list)
    uninstalled_plugin_ids: list[str] = field(default_factory=list)


class PluginRemoteSyncError(Exception):
    pass


class PluginInstallError(Exception):
    def is_invalid_request(self) -> bool:
        return False


class PluginUninstallError(Exception):
    def is_invalid_request(self) -> bool:
        return False


class PluginMarketplaceUpgradeError(Exception):
    pass


@dataclass(frozen=True)
class PluginMarketplaceUpgradeOutcome:
    upgraded: bool = False


class PluginsManager:
    def __init__(self, codex_home: Any, restriction_product: Any | None = None) -> None:
        self.codex_home = codex_home
        self.restriction_product = restriction_product

    @classmethod
    def new(cls, codex_home: Any) -> "PluginsManager":
        return cls(codex_home)

    @classmethod
    def new_with_restriction_product(cls, codex_home: Any, restriction_product: Any) -> "PluginsManager":
        return cls(codex_home, restriction_product)

    def clear_cache(self) -> None:
        return None

    def clear_remote_installed_plugins_cache(self) -> bool:
        return False

    def list_marketplaces_for_config(
        self,
        _plugins_config_input: PluginsConfigInput | None,
        _extra_marketplaces: list[Any] | tuple[Any, ...],
    ) -> ConfiguredMarketplaceListOutcome:
        return ConfiguredMarketplaceListOutcome()

    async def read_plugin_detail_for_marketplace_plugin(
        self,
        _plugins_config_input: PluginsConfigInput | None,
        _marketplace_name: str,
        plugin: ConfiguredMarketplacePlugin,
    ) -> PluginDetail:
        raise FileNotFoundError(f"plugin detail not available: {plugin.id}")


LoadedPlugin = Any
PluginLoadOutcome = Any
