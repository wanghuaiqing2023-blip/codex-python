"""Test-only plugin helpers aligned with ``codex-rs/core/src/plugins/test_support.rs``."""

from __future__ import annotations

__test__ = False

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pycodex.core.config import CONFIG_TOML_FILE
from pycodex.core_plugins import OPENAI_CURATED_MARKETPLACE_NAME


TEST_CURATED_PLUGIN_SHA = "0123456789abcdef0123456789abcdef01234567"


@dataclass(frozen=True)
class PluginsTestConfig:
    codex_home: Path
    fallback_cwd: Path
    plugins_enabled: bool = False
    raw_config: dict[str, object] | None = None


def write_file(path: str | Path, contents: str) -> None:
    target = Path(path)
    parent = target.parent
    if parent == target:
        raise ValueError("file should have a parent")
    parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")


def write_curated_plugin(root: str | Path, plugin_name: str) -> None:
    plugin_root = Path(root) / "plugins" / plugin_name
    write_file(
        plugin_root / ".codex-plugin" / "plugin.json",
        (
            "{\n"
            f'  "name": "{plugin_name}",\n'
            '  "description": "Plugin that includes skills, MCP servers, and app connectors"\n'
            "}"
        ),
    )
    write_file(
        plugin_root / "skills" / "SKILL.md",
        "---\nname: sample\ndescription: sample\n---\n",
    )
    write_file(
        plugin_root / ".mcp.json",
        '{\n'
        '  "mcpServers": {\n'
        '    "sample-docs": {\n'
        '      "type": "http",\n'
        '      "url": "https://sample.example/mcp"\n'
        "    }\n"
        "  }\n"
        "}",
    )
    write_file(
        plugin_root / ".app.json",
        '{\n'
        '  "apps": {\n'
        '    "calendar": {\n'
        '      "id": "connector_calendar"\n'
        "    }\n"
        "  }\n"
        "}",
    )


def write_openai_curated_marketplace(root: str | Path, plugin_names: Iterable[str]) -> None:
    root_path = Path(root)
    names = list(plugin_names)
    plugins = [
        {
            "name": plugin_name,
            "source": {
                "source": "local",
                "path": f"./plugins/{plugin_name}",
            },
        }
        for plugin_name in names
    ]
    marketplace = {
        "name": OPENAI_CURATED_MARKETPLACE_NAME,
        "plugins": plugins,
    }
    write_file(
        root_path / ".agents" / "plugins" / "marketplace.json",
        json.dumps(marketplace, indent=2) + "\n",
    )
    for plugin_name in names:
        write_curated_plugin(root_path, plugin_name)


def write_curated_plugin_sha(codex_home: str | Path) -> None:
    write_curated_plugin_sha_with(codex_home, TEST_CURATED_PLUGIN_SHA)


def write_curated_plugin_sha_with(codex_home: str | Path, sha: str) -> None:
    write_file(Path(codex_home) / ".tmp" / "plugins.sha", f"{sha}\n")


def write_plugins_feature_config(codex_home: str | Path) -> None:
    write_file(
        Path(codex_home) / CONFIG_TOML_FILE,
        "[features]\nplugins = true\n",
    )


async def load_plugins_config(codex_home: str | Path) -> PluginsTestConfig:
    home = Path(codex_home)
    config_path = home / CONFIG_TOML_FILE
    raw_config: dict[str, object] | None = None
    plugins_enabled = False
    if config_path.exists():
        raw_config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        features = raw_config.get("features")
        if isinstance(features, dict):
            plugins_enabled = bool(features.get("plugins", False))
    return PluginsTestConfig(
        codex_home=home,
        fallback_cwd=home,
        plugins_enabled=plugins_enabled,
        raw_config=raw_config,
    )


__all__ = [
    "PluginsTestConfig",
    "TEST_CURATED_PLUGIN_SHA",
    "load_plugins_config",
    "write_curated_plugin",
    "write_curated_plugin_sha",
    "write_curated_plugin_sha_with",
    "write_file",
    "write_openai_curated_marketplace",
    "write_plugins_feature_config",
]
