"""Feature-related CLI helpers ported from Codex CLI."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, TextIO

from pycodex.config import CliConfigOverrides
from pycodex.core.config_edit import CONFIG_TOML_FILE, ConfigEditsBuilder, read_toml_mapping
from pycodex.core.features import (
    FEATURES,
    Feature,
    FeatureConfigSource,
    FeatureOverrides,
    Features,
    FeaturesToml,
    Stage,
    StageKind,
    is_known_feature_key,
)
from pycodex.core.paths import find_codex_home


UPSTREAM_CLI_MAIN = "codex/codex-rs/cli/src/main.rs"


class FeatureCliError(ValueError):
    """Raised when feature CLI arguments do not match upstream's shape."""


@dataclass(frozen=True)
class FeatureToggles:
    """Root ``--enable``/``--disable`` options.

    Upstream folds these into config overrides before command dispatch.
    """

    enable: tuple[str, ...] = ()
    disable: tuple[str, ...] = ()

    def to_overrides(self) -> list[str]:
        overrides: list[str] = []
        for feature in self.enable:
            validate_feature(feature)
            overrides.append(f"features.{feature}=true")
        for feature in self.disable:
            validate_feature(feature)
            overrides.append(f"features.{feature}=false")
        return overrides


class FeaturesSubcommand(str, Enum):
    LIST = "list"
    ENABLE = "enable"
    DISABLE = "disable"


@dataclass(frozen=True)
class FeatureSetArgs:
    feature: str


@dataclass(frozen=True)
class FeaturesCli:
    subcommand: FeaturesSubcommand
    args: FeatureSetArgs | None = None


def validate_feature(feature: str) -> None:
    if not is_known_feature_key(feature):
        raise FeatureCliError(f"Unknown feature flag: {feature}")


def parse_features_args(args: Iterable[str]) -> FeaturesCli:
    tokens = tuple(args)
    if not tokens:
        raise FeatureCliError("features requires a subcommand: list, enable, or disable")

    subcommand = tokens[0]
    if subcommand == "list":
        if len(tokens) != 1:
            raise FeatureCliError("features list does not accept extra arguments")
        return FeaturesCli(FeaturesSubcommand.LIST)

    if subcommand in ("enable", "disable"):
        if len(tokens) != 2:
            raise FeatureCliError(f"features {subcommand} requires exactly one feature")
        feature = tokens[1]
        validate_feature(feature)
        parsed_subcommand = FeaturesSubcommand.ENABLE if subcommand == "enable" else FeaturesSubcommand.DISABLE
        return FeaturesCli(parsed_subcommand, FeatureSetArgs(feature))

    raise FeatureCliError(f"unknown features subcommand: {subcommand}")


def stage_str(stage: Stage) -> str:
    if stage.kind is StageKind.UNDER_DEVELOPMENT:
        return "under development"
    if stage.kind is StageKind.EXPERIMENTAL:
        return "experimental"
    if stage.kind is StageKind.STABLE:
        return "stable"
    if stage.kind is StageKind.DEPRECATED:
        return "deprecated"
    if stage.kind is StageKind.REMOVED:
        return "removed"
    raise FeatureCliError(f"unknown feature stage: {stage.kind}")


def format_features_list(features: Features) -> str:
    rows: list[tuple[str, str, bool]] = []
    name_width = 0
    stage_width = 0
    for spec in FEATURES:
        name = spec.key
        stage = stage_str(spec.stage)
        enabled = features.enabled(spec.id)
        name_width = max(name_width, len(name))
        stage_width = max(stage_width, len(stage))
        rows.append((name, stage, enabled))
    rows.sort(key=lambda row: row[0])

    lines = [
        f"{name:<{name_width}}  {stage:<{stage_width}}  {str(enabled).lower()}"
        for name, stage, enabled in rows
    ]
    return "\n".join(lines)


def features_from_config_mapping(config: dict[str, Any]) -> Features:
    features_value = config.get("features")
    features_toml = FeaturesToml.from_mapping(features_value) if isinstance(features_value, dict) else None
    legacy_unified_exec = config.get("experimental_use_unified_exec_tool")
    return Features.from_sources(
        FeatureConfigSource(
            features=features_toml,
            experimental_use_unified_exec_tool=legacy_unified_exec
            if isinstance(legacy_unified_exec, bool)
            else None,
        ),
        FeatureConfigSource(),
        FeatureOverrides(),
    )


def load_features_for_cli(
    codex_home: str | Path,
    raw_config_overrides: Iterable[str] = (),
) -> Features:
    home = Path(codex_home)
    config = read_toml_mapping(home / CONFIG_TOML_FILE)
    CliConfigOverrides(list(raw_config_overrides)).apply_on_mapping(config)
    return features_from_config_mapping(config)


def run_features_command(
    features_cli: FeaturesCli,
    *,
    raw_config_overrides: Iterable[str] = (),
    codex_home: str | Path | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    home = Path(codex_home) if codex_home is not None else find_codex_home()

    if features_cli.subcommand is FeaturesSubcommand.LIST:
        print(format_features_list(load_features_for_cli(home, raw_config_overrides)), file=out)
        return 0

    if features_cli.args is None:
        raise FeatureCliError("features enable/disable requires a feature")

    feature = features_cli.args.feature
    if features_cli.subcommand is FeaturesSubcommand.ENABLE:
        ConfigEditsBuilder.new(home).set_feature_enabled(feature, True).apply_blocking()
        print(f"Enabled feature `{feature}` in config.toml.", file=out)
        warning = under_development_feature_warning(home, feature)
        if warning is not None:
            print(warning, file=err)
        return 0

    if features_cli.subcommand is FeaturesSubcommand.DISABLE:
        ConfigEditsBuilder.new(home).set_feature_enabled(feature, False).apply_blocking()
        print(f"Disabled feature `{feature}` in config.toml.", file=out)
        return 0

    raise FeatureCliError(f"unknown features subcommand: {features_cli.subcommand}")


def under_development_feature_warning(codex_home: str | Path, feature: str) -> str | None:
    spec = next((spec for spec in FEATURES if spec.key == feature), None)
    if spec is None or spec.stage.kind is not StageKind.UNDER_DEVELOPMENT:
        return None
    config_path = Path(codex_home) / "config.toml"
    return (
        f"Under-development features enabled: {feature}. Under-development features are incomplete "
        "and may behave unpredictably. To suppress this warning, set "
        f"`suppress_unstable_features_warning = true` in {config_path}."
    )


__all__ = [
    "FeatureCliError",
    "FeatureSetArgs",
    "FeatureToggles",
    "FeaturesCli",
    "FeaturesSubcommand",
    "features_from_config_mapping",
    "format_features_list",
    "load_features_for_cli",
    "parse_features_args",
    "run_features_command",
    "stage_str",
    "under_development_feature_warning",
    "validate_feature",
]
