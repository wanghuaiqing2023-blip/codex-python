"""Python interface for Rust ``codex-core-plugins``."""

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

from pycodex.plugin import LoadedPlugin, PluginLoadOutcome
from pycodex.utils.plugins import PluginSkillRoot

from .manager import (
    ConfiguredMarketplace,
    ConfiguredMarketplaceListOutcome,
    ConfiguredMarketplacePlugin,
    PluginDetail,
    PluginDetailsUnavailableReason,
    PluginInstallError,
    PluginInstallOutcome,
    PluginInstallRequest,
    PluginReadOutcome,
    PluginReadRequest,
    PluginRemoteSyncError,
    PluginUninstallError,
    PluginsConfigInput,
    PluginsManager,
    RemotePluginSyncResult,
)
from .marketplace_upgrade import (
    ConfiguredMarketplaceUpgradeError as PluginMarketplaceUpgradeError,
)
from .marketplace_upgrade import (
    ConfiguredMarketplaceUpgradeOutcome as PluginMarketplaceUpgradeOutcome,
)

__all__ = [
    "ConfiguredMarketplace",
    "ConfiguredMarketplaceListOutcome",
    "ConfiguredMarketplacePlugin",
    "LoadedPlugin",
    "OPENAI_BUNDLED_MARKETPLACE_NAME",
    "OPENAI_CURATED_MARKETPLACE_NAME",
    "PluginDetail",
    "PluginDetailsUnavailableReason",
    "PluginInstallError",
    "PluginInstallOutcome",
    "PluginInstallRequest",
    "PluginLoadOutcome",
    "PluginMarketplaceUpgradeError",
    "PluginMarketplaceUpgradeOutcome",
    "PluginReadOutcome",
    "PluginReadRequest",
    "PluginRemoteSyncError",
    "PluginSkillRoot",
    "PluginUninstallError",
    "PluginsConfigInput",
    "PluginsManager",
    "RemotePluginSyncResult",
    "TOOL_SUGGEST_DISCOVERABLE_PLUGIN_ALLOWLIST",
]
