"""User marketplace config edits ported from ``codex-config``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from . import toml_compat as _toml
from .plugin_edit import CONFIG_TOML_FILE, _format_toml_value, _quote_key

JsonValue = Any


@dataclass(frozen=True)
class MarketplaceConfigUpdate:
    last_updated: str
    source_type: str
    source: str
    last_revision: str | None = None
    ref_name: str | None = None
    sparse_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sparse_paths", tuple(str(item) for item in self.sparse_paths))


class RemoveMarketplaceConfigOutcome(str, Enum):
    REMOVED = "removed"
    NOT_FOUND = "not_found"
    NAME_CASE_MISMATCH = "name_case_mismatch"


@dataclass(frozen=True)
class RemoveMarketplaceConfigResult:
    outcome: RemoveMarketplaceConfigOutcome
    configured_name: str | None = None

    @classmethod
    def removed(cls) -> "RemoveMarketplaceConfigResult":
        return cls(RemoveMarketplaceConfigOutcome.REMOVED)

    @classmethod
    def not_found(cls) -> "RemoveMarketplaceConfigResult":
        return cls(RemoveMarketplaceConfigOutcome.NOT_FOUND)

    @classmethod
    def name_case_mismatch(cls, configured_name: str) -> "RemoveMarketplaceConfigResult":
        return cls(RemoveMarketplaceConfigOutcome.NAME_CASE_MISMATCH, configured_name)


def record_user_marketplace(
    codex_home: Path | str,
    marketplace_name: str,
    update: MarketplaceConfigUpdate,
) -> None:
    home = Path(codex_home)
    config_path = home / CONFIG_TOML_FILE
    document = _read_config_mapping(config_path) if config_path.exists() else {}
    marketplaces = document.get("marketplaces")
    if not isinstance(marketplaces, dict):
        marketplaces = {}
        document["marketplaces"] = marketplaces
    entry: dict[str, JsonValue] = {
        "last_updated": update.last_updated,
        "source_type": update.source_type,
        "source": update.source,
    }
    if update.last_revision is not None:
        entry["last_revision"] = update.last_revision
    if update.ref_name is not None:
        entry["ref"] = update.ref_name
    if update.sparse_paths:
        entry["sparse_paths"] = list(update.sparse_paths)
    marketplaces[str(marketplace_name)] = entry
    home.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_serialize_config(document), encoding="utf-8", newline="\n")


def remove_user_marketplace(codex_home: Path | str, marketplace_name: str) -> bool:
    return remove_user_marketplace_config(codex_home, marketplace_name).outcome == RemoveMarketplaceConfigOutcome.REMOVED


def remove_user_marketplace_config(codex_home: Path | str, marketplace_name: str) -> RemoveMarketplaceConfigResult:
    home = Path(codex_home)
    config_path = home / CONFIG_TOML_FILE
    if not config_path.exists():
        return RemoveMarketplaceConfigResult.not_found()
    document = _read_config_mapping(config_path)
    outcome = _remove_marketplace(document, marketplace_name)
    if outcome.outcome != RemoveMarketplaceConfigOutcome.REMOVED:
        return outcome
    home.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_serialize_config(document), encoding="utf-8", newline="\n")
    return outcome


def _remove_marketplace(document: dict[str, JsonValue], marketplace_name: str) -> RemoveMarketplaceConfigResult:
    marketplaces = document.get("marketplaces")
    if not isinstance(marketplaces, dict):
        return RemoveMarketplaceConfigResult.not_found()
    if marketplace_name in marketplaces:
        del marketplaces[marketplace_name]
        if not marketplaces:
            document.pop("marketplaces", None)
        return RemoveMarketplaceConfigResult.removed()
    for configured_name in marketplaces:
        if configured_name != marketplace_name and configured_name.lower() == marketplace_name.lower():
            return RemoveMarketplaceConfigResult.name_case_mismatch(configured_name)
    return RemoveMarketplaceConfigResult.not_found()


def _read_config_mapping(path: Path) -> dict[str, JsonValue]:
    raw = path.read_text(encoding="utf-8")
    try:
        return dict(_toml.loads(raw))
    except _toml.TOMLDecodeError:
        return _parse_multiline_marketplaces_inline_table(raw)


def _parse_multiline_marketplaces_inline_table(raw: str) -> dict[str, JsonValue]:
    match = re.search(r"marketplaces\s*=\s*\{\s*(.*)\s*\}\s*$", raw, flags=re.DOTALL)
    if match is None:
        return dict(_toml.loads(raw))
    marketplaces: dict[str, JsonValue] = {}
    for name, body in re.findall(r"([A-Za-z0-9_.-]+)\s*=\s*\{([^{}]*)\}", match.group(1)):
        entry: dict[str, JsonValue] = {}
        for field, raw_value in re.findall(r"([A-Za-z0-9_.-]+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^,]+)", body):
            value_text = raw_value.strip()
            if value_text.startswith(("\"", "'")) and value_text.endswith(("\"", "'")):
                entry[field] = value_text[1:-1]
            elif value_text == "true":
                entry[field] = True
            elif value_text == "false":
                entry[field] = False
            else:
                entry[field] = value_text
        marketplaces[name] = entry
    return {"marketplaces": marketplaces}


def _serialize_config(document: dict[str, JsonValue]) -> str:
    if not document:
        return ""
    lines: list[str] = []
    for key, value in document.items():
        if key == "marketplaces" and isinstance(value, dict):
            _serialize_marketplaces(value, lines)
            continue
        lines.append(f"{_quote_key(key)} = {_format_toml_value(value)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _serialize_marketplaces(marketplaces: dict[str, JsonValue], lines: list[str]) -> None:
    for name, value in marketplaces.items():
        if not isinstance(value, dict):
            continue
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[marketplaces.{_quote_key(name)}]")
        for field_name, field_value in value.items():
            lines.append(f"{_quote_key(field_name)} = {_format_toml_value(field_value)}")


__all__ = [
    "MarketplaceConfigUpdate",
    "RemoveMarketplaceConfigOutcome",
    "RemoveMarketplaceConfigResult",
    "record_user_marketplace",
    "remove_user_marketplace",
    "remove_user_marketplace_config",
]
