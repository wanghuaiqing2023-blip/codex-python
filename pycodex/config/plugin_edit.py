"""User plugin config edits ported from ``codex-config``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from . import toml_compat as _toml

CONFIG_TOML_FILE = "config.toml"
JsonValue = Any


@dataclass(frozen=True)
class PluginConfigEdit:
    kind: Literal["set_enabled", "clear"]
    plugin_key: str
    enabled: bool | None = None

    @classmethod
    def set_enabled(cls, plugin_key: str, enabled: bool) -> "PluginConfigEdit":
        return cls("set_enabled", str(plugin_key), bool(enabled))

    @classmethod
    def clear(cls, plugin_key: str) -> "PluginConfigEdit":
        return cls("clear", str(plugin_key))


async def set_user_plugin_enabled(codex_home: Path | str, plugin_key: str, enabled: bool) -> None:
    await apply_user_plugin_config_edits(codex_home, [PluginConfigEdit.set_enabled(plugin_key, enabled)])


async def clear_user_plugin(codex_home: Path | str, plugin_key: str) -> None:
    await apply_user_plugin_config_edits(codex_home, [PluginConfigEdit.clear(plugin_key)])


async def apply_user_plugin_config_edits(codex_home: Path | str, edits: list[PluginConfigEdit]) -> None:
    apply_user_plugin_config_edits_blocking(codex_home, edits)


def apply_user_plugin_config_edits_blocking(codex_home: Path | str, edits: list[PluginConfigEdit]) -> None:
    if not edits:
        return
    home = Path(codex_home)
    config_path = home / CONFIG_TOML_FILE
    exists = config_path.exists()
    document = _read_config_mapping(config_path) if exists else {}
    mutated = False
    for edit in edits:
        if edit.kind == "set_enabled":
            assert edit.enabled is not None
            mutated = _set_plugin_enabled(document, edit.plugin_key, edit.enabled) or mutated
        elif edit.kind == "clear":
            mutated = _clear_plugin(document, edit.plugin_key) or mutated
        else:
            raise ValueError(f"unknown plugin config edit kind: {edit.kind}")
    if not mutated:
        return
    home.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_serialize_config(document), encoding="utf-8", newline="\n")


def _read_config_mapping(path: Path) -> dict[str, JsonValue]:
    raw = path.read_text(encoding="utf-8")
    return dict(_toml.loads(raw))


def _set_plugin_enabled(document: dict[str, JsonValue], plugin_key: str, enabled: bool) -> bool:
    plugins = document.get("plugins")
    if not isinstance(plugins, dict):
        plugins = {}
        document["plugins"] = plugins
    plugin = plugins.get(plugin_key)
    if not isinstance(plugin, dict):
        plugin = {}
        plugins[plugin_key] = plugin
    if plugin.get("enabled") == enabled:
        return False
    plugin["enabled"] = enabled
    return True


def _clear_plugin(document: dict[str, JsonValue], plugin_key: str) -> bool:
    plugins = document.get("plugins")
    if not isinstance(plugins, dict):
        return False
    if plugin_key not in plugins:
        return False
    del plugins[plugin_key]
    if not plugins:
        document.pop("plugins", None)
    return True


def _serialize_config(document: dict[str, JsonValue]) -> str:
    if not document:
        return ""
    lines: list[str] = []
    for key, value in document.items():
        if key == "plugins" and isinstance(value, dict):
            _serialize_plugins(value, lines)
            continue
        lines.append(f"{_quote_key(key)} = {_format_toml_value(value)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _serialize_plugins(plugins: dict[str, JsonValue], lines: list[str]) -> None:
    for plugin_key, value in plugins.items():
        if not isinstance(value, dict):
            continue
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[plugins.{_quote_key(plugin_key)}]")
        for field_name, field_value in value.items():
            lines.append(f"{_quote_key(field_name)} = {_format_toml_value(field_value)}")


def _quote_key(key: str) -> str:
    if key.replace("_", "").replace("-", "").isalnum() and "@" not in key and "." not in key:
        return key
    return '"' + key.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _format_toml_value(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


__all__ = [
    "PluginConfigEdit",
    "apply_user_plugin_config_edits",
    "apply_user_plugin_config_edits_blocking",
    "clear_user_plugin",
    "set_user_plugin_enabled",
]
