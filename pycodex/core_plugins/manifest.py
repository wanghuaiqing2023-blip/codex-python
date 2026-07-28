"""Plugin manifest parsing for ``codex-core-plugins``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from pycodex.utils.plugins import find_plugin_manifest_path

MAX_DEFAULT_PROMPT_COUNT = 3
MAX_DEFAULT_PROMPT_LEN = 128


@dataclass(frozen=True)
class PluginManifestHooks:
    paths: tuple[Path, ...] = ()
    inline: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class PluginManifestPaths:
    skills: Path | None = None
    mcp_servers: Path | None = None
    apps: Path | None = None
    hooks: PluginManifestHooks | None = None


@dataclass(frozen=True)
class PluginManifestInterface:
    display_name: str | None = None
    short_description: str | None = None
    long_description: str | None = None
    developer_name: str | None = None
    category: str | None = None
    capabilities: tuple[str, ...] = ()
    website_url: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    default_prompt: tuple[str, ...] | None = None
    brand_color: str | None = None
    composer_icon: Path | None = None
    logo: Path | None = None
    screenshots: tuple[Path, ...] = ()


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str | None
    description: str | None
    keywords: tuple[str, ...]
    paths: PluginManifestPaths
    interface: PluginManifestInterface | None


def load_plugin_manifest(plugin_root: str | Path) -> PluginManifest | None:
    root = Path(plugin_root)
    manifest_path = find_plugin_manifest_path(root)
    if manifest_path is None:
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None

    raw_name = raw.get("name", "")
    name = raw_name if isinstance(raw_name, str) and raw_name.strip() else root.name
    raw_version = raw.get("version")
    version = raw_version.strip() if isinstance(raw_version, str) else None
    if version == "":
        version = None
    description = raw.get("description") if isinstance(raw.get("description"), str) else None
    raw_keywords = raw.get("keywords", [])
    keywords = (
        tuple(item for item in raw_keywords if isinstance(item, str))
        if isinstance(raw_keywords, list)
        else ()
    )

    interface = _resolve_interface(root, raw.get("interface"))
    return PluginManifest(
        name=name,
        version=version,
        description=description,
        keywords=keywords,
        paths=PluginManifestPaths(
            skills=_resolve_manifest_path(root, raw.get("skills")),
            mcp_servers=_resolve_manifest_path(root, raw.get("mcpServers")),
            apps=_resolve_manifest_path(root, raw.get("apps")),
            hooks=_resolve_manifest_hooks(root, raw.get("hooks")),
        ),
        interface=interface,
    )


def _resolve_manifest_hooks(root: Path, value: Any) -> PluginManifestHooks | None:
    if isinstance(value, str):
        path = _resolve_manifest_path(root, value)
        return PluginManifestHooks(paths=(path,)) if path is not None else None
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            paths = tuple(
                path
                for item in value
                if (path := _resolve_manifest_path(root, item)) is not None
            )
            return PluginManifestHooks(paths=paths) if paths else None
        inline = tuple(item for item in value if isinstance(item, dict))
        return PluginManifestHooks(inline=inline) if inline else None
    if isinstance(value, dict):
        return PluginManifestHooks(inline=(value,))
    return None


def _resolve_interface(root: Path, value: Any) -> PluginManifestInterface | None:
    if not isinstance(value, dict):
        return None
    screenshots_value = value.get("screenshots", [])
    screenshots = (
        tuple(
            path
            for item in screenshots_value
            if (path := _resolve_manifest_path(root, item)) is not None
        )
        if isinstance(screenshots_value, list)
        else ()
    )
    capabilities_value = value.get("capabilities", [])
    capabilities = (
        tuple(item for item in capabilities_value if isinstance(item, str))
        if isinstance(capabilities_value, list)
        else ()
    )
    interface = PluginManifestInterface(
        display_name=_string(value.get("displayName")),
        short_description=_string(value.get("shortDescription")),
        long_description=_string(value.get("longDescription")),
        developer_name=_string(value.get("developerName")),
        category=_string(value.get("category")),
        capabilities=capabilities,
        website_url=_string(value.get("websiteUrl", value.get("websiteURL"))),
        privacy_policy_url=_string(
            value.get("privacyPolicyUrl", value.get("privacyPolicyURL"))
        ),
        terms_of_service_url=_string(
            value.get("termsOfServiceUrl", value.get("termsOfServiceURL"))
        ),
        default_prompt=_resolve_default_prompts(value.get("defaultPrompt")),
        brand_color=_string(value.get("brandColor")),
        composer_icon=_resolve_manifest_path(root, value.get("composerIcon")),
        logo=_resolve_manifest_path(root, value.get("logo")),
        screenshots=screenshots,
    )
    return interface if any(
        (
            interface.display_name is not None,
            interface.short_description is not None,
            interface.long_description is not None,
            interface.developer_name is not None,
            interface.category is not None,
            bool(interface.capabilities),
            interface.website_url is not None,
            interface.privacy_policy_url is not None,
            interface.terms_of_service_url is not None,
            interface.default_prompt is not None,
            interface.brand_color is not None,
            interface.composer_icon is not None,
            interface.logo is not None,
            bool(interface.screenshots),
        )
    ) else None


def _resolve_default_prompts(value: Any) -> tuple[str, ...] | None:
    values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    prompts: list[str] = []
    for item in values:
        if len(prompts) >= MAX_DEFAULT_PROMPT_COUNT:
            break
        if not isinstance(item, str):
            continue
        prompt = " ".join(item.split())
        if prompt and len(prompt) <= MAX_DEFAULT_PROMPT_LEN:
            prompts.append(prompt)
    return tuple(prompts) if prompts else None


def _resolve_manifest_path(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.startswith("./") or value == "./":
        return None
    relative = PurePosixPath(value[2:])
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return (root / Path(*relative.parts)).resolve()


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


__all__ = [
    "PluginManifest",
    "PluginManifestHooks",
    "PluginManifestInterface",
    "PluginManifestPaths",
    "load_plugin_manifest",
]
