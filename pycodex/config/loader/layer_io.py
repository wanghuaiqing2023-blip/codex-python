"""Port of ``codex-config/src/loader/layer_io.rs``."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from .. import toml_compat as _toml
from ..config_toml import ConfigToml
from ..state import LoaderOverrides


JsonValue = Any
CODEX_MANAGED_CONFIG_SYSTEM_PATH = PurePosixPath("/etc/codex/managed_config.toml")


@dataclass(frozen=True)
class ManagedConfigFromFile:
    managed_config: Mapping[str, JsonValue]
    file: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "managed_config", dict(self.managed_config))
        object.__setattr__(self, "file", Path(self.file))


@dataclass(frozen=True)
class ManagedConfigFromMdm:
    managed_config: Mapping[str, JsonValue]
    raw_toml: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "managed_config", dict(self.managed_config))


@dataclass(frozen=True)
class LoadedConfigLayers:
    managed_config: ManagedConfigFromFile | None = None
    managed_config_from_mdm: ManagedConfigFromMdm | None = None


def managed_config_default_path(
    codex_home: Path | str,
    platform: str | None = None,
) -> PurePath:
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        return CODEX_MANAGED_CONFIG_SYSTEM_PATH
    return Path(codex_home) / "managed_config.toml"


def read_config_from_path(
    path: Path | str,
    *,
    strict_config: bool = False,
) -> dict[str, JsonValue] | None:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    parsed = _toml.loads(raw)
    if not isinstance(parsed, Mapping):
        raise TypeError(f"{path} must contain a TOML table")
    if strict_config:
        ConfigToml.from_mapping(parsed)
    return dict(parsed)


def read_managed_config_from_path(
    path: Path | str,
    *,
    strict_config: bool = False,
) -> dict[str, JsonValue] | None:
    return read_config_from_path(path, strict_config=strict_config)


def load_config_layers_internal(
    codex_home: Path | str,
    *,
    overrides: LoaderOverrides | None = None,
    strict_config: bool = False,
    managed_config_mdm_raw_toml: str | None = None,
    managed_config_mdm_base64: str | None = None,
) -> LoadedConfigLayers:
    from .macos import managed_config_from_mdm_base64
    from .macos import managed_config_from_mdm_raw_toml

    codex_home = Path(codex_home)
    overrides = overrides or LoaderOverrides()
    managed_path = overrides.managed_config_path or managed_config_default_path(codex_home)
    managed_config = read_managed_config_from_path(
        managed_path,
        strict_config=strict_config,
    )
    if (
        managed_config_mdm_raw_toml is not None
        and managed_config_mdm_base64 is not None
    ):
        raise ValueError(
            "managed config MDM raw TOML and base64 inputs are mutually exclusive"
        )
    mdm = (
        managed_config_from_mdm_raw_toml(
            managed_config_mdm_raw_toml,
            strict_config=strict_config,
        )
        if managed_config_mdm_raw_toml is not None
        else managed_config_from_mdm_base64(
            managed_config_mdm_base64,
            strict_config=strict_config,
        )
    )
    return LoadedConfigLayers(
        managed_config=(
            ManagedConfigFromFile(managed_config, Path(managed_path))
            if managed_config is not None
            else None
        ),
        managed_config_from_mdm=mdm,
    )


__all__ = [
    "CODEX_MANAGED_CONFIG_SYSTEM_PATH",
    "LoadedConfigLayers",
    "ManagedConfigFromFile",
    "ManagedConfigFromMdm",
    "load_config_layers_internal",
    "managed_config_default_path",
    "read_config_from_path",
    "read_managed_config_from_path",
]
