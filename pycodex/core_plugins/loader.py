"""Plugin loading owned by ``codex-core-plugins::loader``."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pycodex.plugin import LoadedPlugin, PluginLoadOutcome, prompt_safe_plugin_description


def curated_plugin_cache_version(plugin_version: str) -> str:
    value = str(plugin_version)
    if len(value) == 40 and all(character in "0123456789abcdefABCDEF" for character in value):
        return value[:8]
    return value


async def load_plugins_from_layer_stack(
    config_layer_stack: Any,
    codex_home: str | Path,
) -> PluginLoadOutcome:
    config = _effective_config(config_layer_stack)
    plugins = config.get("plugins", {})
    if not isinstance(plugins, Mapping):
        return PluginLoadOutcome()

    loaded: list[LoadedPlugin] = []
    for config_name, settings in sorted(plugins.items(), key=lambda item: str(item[0])):
        if not isinstance(config_name, str):
            continue
        plugin = _load_configured_plugin(
            Path(codex_home),
            config_name,
            enabled=_plugin_enabled(settings),
        )
        if plugin is not None:
            loaded.append(plugin)
    return PluginLoadOutcome.from_plugins(loaded)


def configured_curated_plugin_ids_from_codex_home(codex_home: str | Path) -> list[str]:
    config_path = Path(codex_home) / "config.toml"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    plugins = config.get("plugins")
    if not isinstance(plugins, Mapping):
        return []
    return sorted(
        key
        for key in plugins
        if isinstance(key, str) and key.endswith("@openai-curated")
    )


def _plugin_enabled(settings: Any) -> bool:
    if isinstance(settings, bool):
        return settings
    if isinstance(settings, Mapping):
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
    versions = sorted(
        (path for path in plugin_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )
    if not versions:
        return None
    root = versions[-1]
    manifest_path = root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return LoadedPlugin(config_name, root, enabled=enabled, error=str(exc))
    if not isinstance(manifest, Mapping):
        return LoadedPlugin(
            config_name,
            root,
            enabled=enabled,
            error="plugin manifest must be an object",
        )

    interface = manifest.get("interface", {})
    display_name = interface.get("displayName") if isinstance(interface, Mapping) else None
    description = manifest.get("description")
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
    return {
        str(name): config
        for name, config in raw.items()
        if isinstance(config, Mapping)
    }


def _load_apps(path: Path | None) -> tuple[str, ...]:
    value = _read_json_mapping(path)
    raw = value.get("apps", {})
    if not isinstance(raw, Mapping):
        return ()
    return tuple(
        sorted(
            {
                str(config.get("id")).strip()
                for config in raw.values()
                if isinstance(config, Mapping) and str(config.get("id", "")).strip()
            }
        )
    )


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


__all__ = [
    "configured_curated_plugin_ids_from_codex_home",
    "curated_plugin_cache_version",
    "load_plugins_from_layer_stack",
    "prompt_safe_plugin_description",
]
