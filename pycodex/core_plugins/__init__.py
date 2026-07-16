"""Python interface for Rust ``codex-core-plugins``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pycodex.core.context import PluginCapabilitySummary


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

    async def plugins_for_config(self, plugins_config_input: PluginsConfigInput | Any) -> "PluginLoadOutcome":
        if plugins_config_input is not None and not bool(
            getattr(plugins_config_input, "plugins_enabled", True)
        ):
            return PluginLoadOutcome()
        stack = getattr(plugins_config_input, "config_layer_stack", plugins_config_input)
        config = _effective_config(stack)
        plugins = config.get("plugins", {})
        if not isinstance(plugins, dict):
            return PluginLoadOutcome()
        loaded: list[LoadedPlugin] = []
        for config_name, settings in sorted(plugins.items(), key=lambda item: str(item[0])):
            if not isinstance(config_name, str):
                continue
            plugin = _load_configured_plugin(
                Path(self.codex_home),
                config_name,
                enabled=_plugin_enabled(settings),
            )
            if plugin is not None:
                loaded.append(plugin)
        return PluginLoadOutcome(tuple(loaded))

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


@dataclass(frozen=True)
class PluginSkillRoot:
    path: Path
    plugin_id: str | None = None
    plugin_root: Path | None = None


@dataclass(frozen=True)
class LoadedPlugin:
    config_name: str
    root: Path
    manifest_name: str | None = None
    manifest_description: str | None = None
    enabled: bool = True
    skill_roots: tuple[Path, ...] = ()
    disabled_skill_paths: frozenset[Path] = frozenset()
    has_enabled_skills: bool = False
    mcp_servers: Mapping[str, Any] = field(default_factory=dict)
    apps: tuple[str, ...] = ()
    error: str | None = None

    def is_active(self) -> bool:
        return self.enabled and self.error is None

    def capability_summary(self) -> "PluginCapabilitySummary | None":
        if not self.is_active():
            return None
        from pycodex.core.context import PluginCapabilitySummary
        description = _prompt_safe_description(self.manifest_description)
        mcp_names = tuple(sorted(str(name) for name in self.mcp_servers))
        if not self.has_enabled_skills and not mcp_names and not self.apps:
            return None
        return PluginCapabilitySummary(
            config_name=self.config_name,
            display_name=self.manifest_name or self.config_name,
            description=description,
            has_skills=self.has_enabled_skills,
            mcp_server_names=mcp_names,
            app_connector_ids=self.apps,
        )


@dataclass(frozen=True)
class PluginLoadOutcome:
    loaded_plugins: tuple[LoadedPlugin, ...] = ()

    def capability_summaries(self) -> tuple["PluginCapabilitySummary", ...]:
        return tuple(
            summary
            for plugin in self.loaded_plugins
            if (summary := plugin.capability_summary()) is not None
        )

    def plugins(self) -> tuple[LoadedPlugin, ...]:
        return self.loaded_plugins

    def effective_skill_roots(self) -> tuple[Path, ...]:
        return tuple(
            sorted(
                {
                    path
                    for plugin in self.loaded_plugins
                    if plugin.is_active()
                    for path in plugin.skill_roots
                },
                key=str,
            )
        )

    def effective_plugin_skill_roots(self) -> tuple[PluginSkillRoot, ...]:
        roots: list[PluginSkillRoot] = []
        seen: set[Path] = set()
        for plugin in self.loaded_plugins:
            if not plugin.is_active():
                continue
            for path in plugin.skill_roots:
                if path in seen:
                    continue
                seen.add(path)
                roots.append(PluginSkillRoot(path, plugin.config_name, plugin.root))
        roots.sort(key=lambda root: str(root.path))
        return tuple(roots)

    def effective_mcp_servers(self) -> dict[str, Any]:
        servers: dict[str, Any] = {}
        for plugin in self.loaded_plugins:
            if not plugin.is_active():
                continue
            for name, config in plugin.mcp_servers.items():
                servers.setdefault(str(name), config)
        return servers

    def effective_apps(self) -> tuple[str, ...]:
        apps: list[str] = []
        seen: set[str] = set()
        for plugin in self.loaded_plugins:
            if not plugin.is_active():
                continue
            for connector_id in plugin.apps:
                if connector_id not in seen:
                    seen.add(connector_id)
                    apps.append(connector_id)
        return tuple(apps)


def _plugin_enabled(settings: Any) -> bool:
    if isinstance(settings, bool):
        return settings
    if isinstance(settings, dict):
        return bool(settings.get("enabled", True))
    return True


def _load_configured_plugin(
    codex_home: Path,
    config_name: str,
    *,
    enabled: bool,
) -> LoadedPlugin | None:
    name, separator, marketplace = config_name.partition("@")
    if not separator:
        return None
    plugin_dir = codex_home / "plugins" / "cache" / marketplace / name
    if not plugin_dir.is_dir():
        return None
    versions = sorted((path for path in plugin_dir.iterdir() if path.is_dir()), key=lambda path: path.name)
    if not versions:
        return None
    root = versions[-1]
    manifest_path = root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return LoadedPlugin(config_name, root, enabled=enabled, error=str(exc))
    if not isinstance(manifest, dict):
        return LoadedPlugin(config_name, root, enabled=enabled, error="plugin manifest must be an object")
    interface = manifest.get("interface", {}) if isinstance(manifest, dict) else {}
    display_name = interface.get("displayName") if isinstance(interface, dict) else None
    description = manifest.get("description") if isinstance(manifest, dict) else None
    manifest_name = manifest.get("name")
    if not isinstance(manifest_name, str) or not manifest_name.strip():
        manifest_name = name

    skill_roots: list[Path] = []
    default_skills = root / "skills"
    if default_skills.is_dir():
        skill_roots.append(default_skills.resolve())
    custom_skills = _manifest_relative_path(root, manifest.get("skills"), require_file=False)
    if custom_skills is not None and custom_skills not in skill_roots:
        skill_roots.append(custom_skills)

    mcp_path = _manifest_relative_path(root, manifest.get("mcpServers"), require_file=True)
    if mcp_path is None:
        default_mcp = root / ".mcp.json"
        mcp_path = default_mcp if default_mcp.is_file() else None
    apps_path = _manifest_relative_path(root, manifest.get("apps"), require_file=True)
    if apps_path is None:
        default_apps = root / ".app.json"
        apps_path = default_apps if default_apps.is_file() else None
    return LoadedPlugin(
        config_name=config_name,
        root=root,
        manifest_name=str(display_name or manifest_name),
        manifest_description=(
            str(description).strip()
            if isinstance(description, str) and description.strip()
            else None
        ),
        enabled=enabled,
        skill_roots=tuple(sorted(skill_roots, key=str)),
        has_enabled_skills=any(_contains_skill_file(path) for path in skill_roots),
        mcp_servers=_load_mcp_servers(mcp_path),
        apps=_load_apps(apps_path),
    )


def _manifest_relative_path(root: Path, value: Any, *, require_file: bool) -> Path | None:
    if not isinstance(value, str) or not value.startswith("./"):
        return None
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    if require_file:
        return path if path.is_file() else None
    return path if path.is_dir() else None


def _load_mcp_servers(path: Path | None) -> dict[str, Any]:
    value = _read_json_mapping(path)
    raw = value.get("mcpServers", value)
    if not isinstance(raw, Mapping):
        return {}
    return {str(name): config for name, config in raw.items() if isinstance(config, Mapping)}


def _load_apps(path: Path | None) -> tuple[str, ...]:
    value = _read_json_mapping(path)
    raw = value.get("apps", {})
    if not isinstance(raw, Mapping):
        return ()
    connector_ids = sorted(
        {
            str(config.get("id")).strip()
            for config in raw.values()
            if isinstance(config, Mapping) and str(config.get("id", "")).strip()
        }
    )
    return tuple(connector_ids)


def _read_json_mapping(path: Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _contains_skill_file(root: Path) -> bool:
    try:
        return any(path.is_file() for path in root.rglob("SKILL.md"))
    except OSError:
        return False


def _effective_config(stack: Any) -> dict[str, Any]:
    reader = getattr(stack, "effective_config", None)
    if callable(reader):
        value = reader()
        return dict(value) if isinstance(value, Mapping) else {}
    return dict(stack) if isinstance(stack, Mapping) else {}


def _prompt_safe_description(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized[:1024] or None
