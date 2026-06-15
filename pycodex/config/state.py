"""Config layer state helpers ported from ``codex-config``."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.network_proxy import ConfigLayerSource

from .fingerprint import record_origins, version_for_toml
from .key_aliases import normalized_with_key_aliases
from .merge import merge_toml_values

JsonValue = Any


@dataclass(frozen=True)
class LoaderOverrides:
    user_config_path: Path | None = None
    user_config_profile: str | None = None
    managed_config_path: Path | None = None
    system_config_path: Path | None = None
    system_requirements_path: Path | None = None
    ignore_managed_requirements: bool = False
    ignore_user_config: bool = False
    ignore_user_and_project_exec_policy_rules: bool = False
    macos_managed_config_requirements_base64: str | None = None

    @classmethod
    def without_managed_config_for_tests(cls) -> "LoaderOverrides":
        base = Path(tempfile.gettempdir()) / "codex-config-tests"
        return cls(
            managed_config_path=base / "managed_config.toml",
            system_config_path=base / "config.toml",
            system_requirements_path=base / "requirements.toml",
            macos_managed_config_requirements_base64="",
        )

    @classmethod
    def with_managed_config_path_for_tests(cls, managed_config_path: Path | str) -> "LoaderOverrides":
        base = cls.without_managed_config_for_tests()
        return cls(
            user_config_path=base.user_config_path,
            user_config_profile=base.user_config_profile,
            managed_config_path=Path(managed_config_path),
            system_config_path=base.system_config_path,
            system_requirements_path=base.system_requirements_path,
            ignore_managed_requirements=base.ignore_managed_requirements,
            ignore_user_config=base.ignore_user_config,
            ignore_user_and_project_exec_policy_rules=base.ignore_user_and_project_exec_policy_rules,
            macos_managed_config_requirements_base64=base.macos_managed_config_requirements_base64,
        )

    def user_config_file(self, codex_home: Path | str) -> Path:
        if self.user_config_path is not None:
            return self.user_config_path
        return Path(codex_home) / "config.toml"


@dataclass(frozen=True)
class ConfigLoadOptions:
    loader_overrides: LoaderOverrides = field(default_factory=LoaderOverrides)
    strict_config: bool = False

    @classmethod
    def from_loader_overrides(cls, loader_overrides: LoaderOverrides) -> "ConfigLoadOptions":
        return cls(loader_overrides=loader_overrides, strict_config=False)


@dataclass(frozen=True)
class ConfigLayerMetadata:
    name: ConfigLayerSource
    version: str


@dataclass(frozen=True)
class ConfigLayer:
    name: ConfigLayerSource
    version: str
    config: JsonValue
    disabled_reason: str | None = None


@dataclass(frozen=True)
class ConfigLayerEntry:
    name: ConfigLayerSource
    config: Mapping[str, JsonValue] = field(default_factory=dict)
    raw_toml: str | None = None
    version: str | None = None
    disabled_reason: str | None = None
    hooks_config_folder_override: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, ConfigLayerSource):
            raise TypeError("name must be ConfigLayerSource")
        if not isinstance(self.config, Mapping):
            raise TypeError("config must be a mapping")
        object.__setattr__(self, "config", dict(self.config))
        if self.version is None:
            object.__setattr__(self, "version", version_for_toml(self.config))
        if self.hooks_config_folder_override is not None:
            object.__setattr__(self, "hooks_config_folder_override", Path(self.hooks_config_folder_override))

    @classmethod
    def new(cls, name: ConfigLayerSource, config: Mapping[str, JsonValue]) -> "ConfigLayerEntry":
        return cls(name=name, config=config)

    @classmethod
    def new_with_raw_toml(
        cls,
        name: ConfigLayerSource,
        config: Mapping[str, JsonValue],
        raw_toml: str,
    ) -> "ConfigLayerEntry":
        return cls(name=name, config=config, raw_toml=raw_toml)

    @classmethod
    def new_disabled(
        cls,
        name: ConfigLayerSource,
        config: Mapping[str, JsonValue],
        disabled_reason: str,
    ) -> "ConfigLayerEntry":
        return cls(name=name, config=config, disabled_reason=str(disabled_reason))

    def is_disabled(self) -> bool:
        return self.disabled_reason is not None

    def raw_toml_text(self) -> str | None:
        return self.raw_toml

    def with_hooks_config_folder_override(self, folder: Path | str | None) -> "ConfigLayerEntry":
        return ConfigLayerEntry(
            name=self.name,
            config=self.config,
            raw_toml=self.raw_toml,
            version=self.version,
            disabled_reason=self.disabled_reason,
            hooks_config_folder_override=Path(folder) if folder is not None else None,
        )

    def metadata(self) -> ConfigLayerMetadata:
        assert self.version is not None
        return ConfigLayerMetadata(name=self.name, version=self.version)

    def as_layer(self) -> ConfigLayer:
        assert self.version is not None
        return ConfigLayer(
            name=self.name,
            version=self.version,
            config=dict(self.config),
            disabled_reason=self.disabled_reason,
        )

    def config_folder(self) -> Path | None:
        if self.name.type == "system" and self.name.file is not None:
            return self.name.file.parent
        if self.name.type == "user" and self.name.file is not None:
            return self.name.file.parent
        if self.name.type == "project":
            return self.name.dot_codex_folder
        return None

    def hooks_config_folder(self) -> Path | None:
        return self.hooks_config_folder_override or self.config_folder()


class ConfigLayerStackOrdering(str, Enum):
    LOWEST_PRECEDENCE_FIRST = "lowest_precedence_first"
    HIGHEST_PRECEDENCE_FIRST = "highest_precedence_first"


@dataclass(frozen=True)
class ConfigLayerStack:
    layers: tuple[ConfigLayerEntry, ...] = ()
    requirements: Any = None
    requirements_toml: Any = None
    ignore_user_and_project_exec_policy_rules_value: bool = False
    startup_warnings_value: tuple[str, ...] | None = None
    user_layer_index: int | None = None

    @classmethod
    def new(
        cls,
        layers: Sequence[ConfigLayerEntry],
        requirements: Any = None,
        requirements_toml: Any = None,
    ) -> "ConfigLayerStack":
        layer_tuple = tuple(layers)
        user_layer_index = verify_layer_ordering(layer_tuple)
        return cls(
            layers=layer_tuple,
            requirements=requirements,
            requirements_toml=requirements_toml,
            user_layer_index=user_layer_index,
        )

    def with_user_and_project_exec_policy_rules_ignored(self, ignored: bool) -> "ConfigLayerStack":
        return self._replace(ignore_user_and_project_exec_policy_rules_value=bool(ignored))

    def ignore_user_and_project_exec_policy_rules(self) -> bool:
        return self.ignore_user_and_project_exec_policy_rules_value

    def with_startup_warnings(self, startup_warnings: Sequence[str]) -> "ConfigLayerStack":
        return self._replace(startup_warnings_value=tuple(str(item) for item in startup_warnings))

    def startup_warnings(self) -> tuple[str, ...] | None:
        return self.startup_warnings_value

    def get_active_user_layer(self) -> ConfigLayerEntry | None:
        if self.user_layer_index is None:
            return None
        return self.layers[self.user_layer_index]

    def get_user_config_file(self) -> Path | None:
        layer = self.get_active_user_layer()
        if layer is None or layer.name.type != "user":
            return None
        return layer.name.file

    def get_user_layers(
        self,
        ordering: ConfigLayerStackOrdering,
        include_disabled: bool,
    ) -> list[ConfigLayerEntry]:
        return [layer for layer in self.get_layers(ordering, include_disabled) if layer.name.type == "user"]

    def effective_user_config(self) -> dict[str, JsonValue] | None:
        user_layers = self.get_user_layers(ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST, False)
        if not user_layers:
            return None
        merged: dict[str, JsonValue] = {}
        for layer in user_layers:
            merge_toml_values(merged, layer.config)
        return merged

    def with_user_config(self, config_toml: Path | str, user_config: Mapping[str, JsonValue]) -> "ConfigLayerStack":
        config_path = Path(config_toml)
        profile = next(
            (
                layer.name.profile
                for layer in self.layers
                if layer.name.type == "user" and layer.name.file == config_path
            ),
            None,
        )
        return self.with_user_config_profile(config_path, profile, user_config)

    def with_user_config_profile(
        self,
        config_toml: Path | str,
        profile: str | None,
        user_config: Mapping[str, JsonValue],
    ) -> "ConfigLayerStack":
        config_path = Path(config_toml)
        user_layer = ConfigLayerEntry.new(ConfigLayerSource.user(config_path, profile), user_config)
        removed_index: int | None = None
        layers: list[ConfigLayerEntry] = []
        for layer in self.layers:
            if layer.name.type == "user" and layer.name.file == config_path:
                removed_index = len(layers)
                continue
            layers.append(layer)
        if removed_index is not None:
            layers.insert(removed_index, user_layer)
        else:
            _insert_layer_by_precedence(layers, user_layer)
        return self._replace_layers(layers)

    def with_user_layer_from(self, other: "ConfigLayerStack") -> "ConfigLayerStack":
        layers = [layer for layer in self.layers if layer.name.type != "user"]
        for user_layer in (layer for layer in other.layers if layer.name.type == "user"):
            _insert_layer_by_precedence(layers, user_layer)
        return self._replace_layers(layers)

    def effective_config(self) -> dict[str, JsonValue]:
        merged: dict[str, JsonValue] = {}
        for layer in self.get_layers(ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST, False):
            merge_toml_values(merged, layer.config)
        return merged

    def origins(self) -> dict[str, ConfigLayerMetadata]:
        origins: dict[str, ConfigLayerMetadata] = {}
        for layer in self.get_layers(ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST, False):
            config = normalized_with_key_aliases(layer.config, ())
            record_origins(config, layer.metadata(), [], origins)
        return origins

    def layers_high_to_low(self) -> list[ConfigLayerEntry]:
        return self.get_layers(ConfigLayerStackOrdering.HIGHEST_PRECEDENCE_FIRST, False)

    def get_layers(
        self,
        ordering: ConfigLayerStackOrdering,
        include_disabled: bool,
    ) -> list[ConfigLayerEntry]:
        layers = [layer for layer in self.layers if include_disabled or not layer.is_disabled()]
        if ordering == ConfigLayerStackOrdering.HIGHEST_PRECEDENCE_FIRST:
            layers.reverse()
        return layers

    def _replace(self, **changes: Any) -> "ConfigLayerStack":
        values = {
            "layers": self.layers,
            "requirements": self.requirements,
            "requirements_toml": self.requirements_toml,
            "ignore_user_and_project_exec_policy_rules_value": self.ignore_user_and_project_exec_policy_rules_value,
            "startup_warnings_value": self.startup_warnings_value,
            "user_layer_index": self.user_layer_index,
        }
        values.update(changes)
        return ConfigLayerStack(**values)

    def _replace_layers(self, layers: Sequence[ConfigLayerEntry]) -> "ConfigLayerStack":
        layer_tuple = tuple(layers)
        return self._replace(layers=layer_tuple, user_layer_index=verify_layer_ordering(layer_tuple))


def verify_layer_ordering(layers: Sequence[ConfigLayerEntry]) -> int | None:
    precedences = [_source_precedence(layer.name) for layer in layers]
    if precedences != sorted(precedences):
        raise ValueError("config layers are not in correct precedence order")

    user_layer_index: int | None = None
    previous_project: Path | None = None
    for index, layer in enumerate(layers):
        if layer.name.type == "user":
            user_layer_index = index
        if layer.name.type == "project":
            current = layer.name.dot_codex_folder
            if current is None:
                raise ValueError("project layer has no .codex folder")
            if previous_project is not None:
                parent = previous_project.parent
                if previous_project == current or parent not in current.parents:
                    raise ValueError("project layers are not ordered from root to cwd")
            previous_project = current
    return user_layer_index


def _insert_layer_by_precedence(layers: list[ConfigLayerEntry], layer: ConfigLayerEntry) -> None:
    precedence = _source_precedence(layer.name)
    for index, current in enumerate(layers):
        if _source_precedence(current.name) > precedence:
            layers.insert(index, layer)
            return
    layers.append(layer)


def _source_precedence(source: ConfigLayerSource) -> int:
    return {
        "mdm": 0,
        "legacy_managed_config_toml_from_file": 5,
        "legacy_managed_config_toml_from_mdm": 5,
        "system": 1,
        "user": 2,
        "project": 3,
        "session_flags": 4,
    }.get(source.type, 5)


__all__ = [
    "ConfigLayer",
    "ConfigLayerEntry",
    "ConfigLayerMetadata",
    "ConfigLayerSource",
    "ConfigLayerStack",
    "ConfigLayerStackOrdering",
    "ConfigLoadOptions",
    "LoaderOverrides",
    "verify_layer_ordering",
]
