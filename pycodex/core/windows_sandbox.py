"""Windows sandbox configuration helpers.

Ported from the pure configuration/decision helpers in
``codex/codex-rs/core/src/windows_sandbox.rs``. Platform setup, preflight,
metrics, and Windows-only sandbox orchestration remain outside this stdlib-only
slice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Mapping

from pycodex.features import Feature, Features, FeaturesToml
from pycodex.protocol import WindowsSandboxLevel


ELEVATED_SANDBOX_NUX_ENABLED = True
_WINDOWS_SANDBOX_SETUP_VERSION = 5


class WindowsSandboxModeToml(str, Enum):
    ELEVATED = "elevated"
    UNELEVATED = "unelevated"


class WindowsSandboxSetupMode(str, Enum):
    ELEVATED = "elevated"
    UNELEVATED = "unelevated"


@dataclass(frozen=True)
class WindowsToml:
    sandbox: WindowsSandboxModeToml | None = None
    sandbox_private_desktop: bool | None = None

    def __post_init__(self) -> None:
        if self.sandbox is not None and not isinstance(self.sandbox, WindowsSandboxModeToml):
            object.__setattr__(self, "sandbox", WindowsSandboxModeToml(self.sandbox))
        if self.sandbox_private_desktop is not None and not isinstance(self.sandbox_private_desktop, bool):
            raise TypeError("sandbox_private_desktop must be a bool or None")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "WindowsToml | None":
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise TypeError("windows config must be a mapping")
        sandbox = value.get("sandbox")
        private_desktop = value.get("sandbox_private_desktop")
        return cls(
            sandbox=WindowsSandboxModeToml(sandbox) if isinstance(sandbox, str) else None,
            sandbox_private_desktop=private_desktop if isinstance(private_desktop, bool) else None,
        )


@dataclass(frozen=True)
class ConfigToml:
    windows: WindowsToml | None = None
    features: FeaturesToml | None = None

    def __post_init__(self) -> None:
        if self.windows is not None and not isinstance(self.windows, WindowsToml):
            if isinstance(self.windows, Mapping):
                object.__setattr__(self, "windows", WindowsToml.from_mapping(self.windows))
            else:
                raise TypeError("windows must be WindowsToml, mapping, or None")
        if self.features is not None and not isinstance(self.features, FeaturesToml):
            if isinstance(self.features, Mapping):
                object.__setattr__(self, "features", FeaturesToml.from_mapping(self.features))
            else:
                raise TypeError("features must be FeaturesToml, mapping, or None")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConfigToml":
        if not isinstance(value, Mapping):
            raise TypeError("config must be a mapping")
        return cls(
            windows=WindowsToml.from_mapping(value.get("windows")) if value.get("windows") is not None else None,
            features=FeaturesToml.from_mapping(value.get("features")) if isinstance(value.get("features"), Mapping) else None,
        )


@dataclass(frozen=True)
class WindowsSandboxSetupRequest:
    mode: WindowsSandboxSetupMode
    permission_profile: Any
    permission_profile_cwd: str | Path
    command_cwd: str | Path
    env_map: dict[str, str] = field(default_factory=dict)
    codex_home: str | Path = ""

    def __post_init__(self) -> None:
        if not isinstance(self.mode, WindowsSandboxSetupMode):
            object.__setattr__(self, "mode", WindowsSandboxSetupMode(self.mode))
        for field_name in ("permission_profile_cwd", "command_cwd", "codex_home"):
            value = getattr(self, field_name)
            if not isinstance(value, (str, Path)):
                raise TypeError(f"{field_name} must be a string or Path")
            object.__setattr__(self, field_name, Path(value))
        if not isinstance(self.env_map, dict):
            raise TypeError("env_map must be a dict")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in self.env_map.items()):
            raise TypeError("env_map must contain string keys and values")


def windows_sandbox_level_from_config(config: Any) -> WindowsSandboxLevel:
    mode = _config_windows_sandbox_mode(config)
    if mode is WindowsSandboxModeToml.ELEVATED:
        return WindowsSandboxLevel.ELEVATED
    if mode is WindowsSandboxModeToml.UNELEVATED:
        return WindowsSandboxLevel.RESTRICTED_TOKEN
    return windows_sandbox_level_from_features(_config_features(config))


def windows_sandbox_level_from_features(features: Features) -> WindowsSandboxLevel:
    if not isinstance(features, Features):
        raise TypeError("features must be Features")
    if features.enabled(Feature.WINDOWS_SANDBOX_ELEVATED):
        return WindowsSandboxLevel.ELEVATED
    if features.enabled(Feature.WINDOWS_SANDBOX):
        return WindowsSandboxLevel.RESTRICTED_TOKEN
    return WindowsSandboxLevel.DISABLED


def resolve_windows_sandbox_mode(cfg: ConfigToml | Mapping[str, Any]) -> WindowsSandboxModeToml | None:
    config = _config_toml(cfg)
    if config.windows is not None and config.windows.sandbox is not None:
        return config.windows.sandbox
    return legacy_windows_sandbox_mode(config.features)


def resolve_windows_sandbox_private_desktop(cfg: ConfigToml | Mapping[str, Any]) -> bool:
    config = _config_toml(cfg)
    if config.windows is not None and config.windows.sandbox_private_desktop is not None:
        return config.windows.sandbox_private_desktop
    return True


def legacy_windows_sandbox_mode(features: FeaturesToml | Mapping[str, bool] | None) -> WindowsSandboxModeToml | None:
    if features is None:
        return None
    entries = features.entries() if isinstance(features, FeaturesToml) else _bool_entries(features)
    return legacy_windows_sandbox_mode_from_entries(entries)


def legacy_windows_sandbox_mode_from_entries(entries: Mapping[str, bool]) -> WindowsSandboxModeToml | None:
    values = _bool_entries(entries)
    if values.get(Feature.WINDOWS_SANDBOX_ELEVATED.key(), False):
        return WindowsSandboxModeToml.ELEVATED
    if values.get(Feature.WINDOWS_SANDBOX.key(), False) or values.get("enable_experimental_windows_sandbox", False):
        return WindowsSandboxModeToml.UNELEVATED
    return None


def windows_sandbox_setup_mode_tag(mode: WindowsSandboxSetupMode | str) -> str:
    sandbox_mode = mode if isinstance(mode, WindowsSandboxSetupMode) else WindowsSandboxSetupMode(mode)
    if sandbox_mode is WindowsSandboxSetupMode.ELEVATED:
        return "elevated"
    return "unelevated"


def sandbox_setup_is_complete(_codex_home: str) -> bool:
    codex_home = Path(_codex_home)
    marker_version = _read_setup_json_version(codex_home / ".sandbox" / "setup_marker.json")
    if marker_version != _WINDOWS_SANDBOX_SETUP_VERSION:
        return False
    users_version = _read_setup_json_version(codex_home / ".sandbox-secrets" / "sandbox_users.json")
    return users_version == _WINDOWS_SANDBOX_SETUP_VERSION


def elevated_setup_failure_details(_err: BaseException) -> tuple[str, str] | None:
    return None


def elevated_setup_failure_metric_name(_err: BaseException) -> str:
    raise RuntimeError("elevated_setup_failure_metric_name is only supported on Windows")


def run_elevated_setup(
    permission_profile: Any,
    permission_profile_cwd: Path | str,
    command_cwd: Path | str,
    env_map: Mapping[str, str],
    codex_home: Path | str,
) -> object:
    raise NotImplementedError("elevated Windows sandbox setup is only supported on Windows")


def run_legacy_setup_preflight(
    permission_profile: Any,
    permission_profile_cwd: Path | str,
    command_cwd: Path | str,
    env_map: Mapping[str, str],
    codex_home: Path | str,
) -> object:
    raise NotImplementedError("legacy Windows sandbox setup is only supported on Windows")


def run_setup_refresh_with_extra_read_roots(
    permission_profile: Any,
    permission_profile_cwd: Path | str,
    command_cwd: Path | str,
    env_map: Mapping[str, str],
    codex_home: Path | str,
    extra_read_roots: Sequence[Path | str],
) -> object:
    """Rust ``windows_sandbox::run_setup_refresh_with_extra_read_roots`` interface.

    The Rust implementation refreshes Windows sandbox setup with the supplied
    extra read roots. The Python stdlib port does not yet include the native
    Windows setup backend, but callers should still go through this explicit
    interface rather than silently treating refresh as a no-op.
    """

    raise NotImplementedError(
        "Windows sandbox read-root refresh is only supported on Windows"
    )


async def run_windows_sandbox_setup(request: WindowsSandboxSetupRequest) -> None:
    if not isinstance(request, WindowsSandboxSetupRequest):
        raise TypeError("request must be WindowsSandboxSetupRequest")
    if request.mode is WindowsSandboxSetupMode.ELEVATED:
        if not sandbox_setup_is_complete(request.codex_home):
            run_elevated_setup(
                request.permission_profile,
                request.permission_profile_cwd,
                request.command_cwd,
                request.env_map,
                request.codex_home,
            )
    else:
        run_legacy_setup_preflight(
            request.permission_profile,
            request.permission_profile_cwd,
            request.command_cwd,
            request.env_map,
            request.codex_home,
        )
    from pycodex.core.config.edit import ConfigEditsBuilder

    await (
        ConfigEditsBuilder.new(request.codex_home)
        .set_windows_sandbox_mode(windows_sandbox_setup_mode_tag(request.mode))
        .clear_legacy_windows_sandbox_keys()
        .apply()
    )


def _read_setup_json_version(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        return None
    return version


def _config_toml(value: ConfigToml | Mapping[str, Any]) -> ConfigToml:
    if isinstance(value, ConfigToml):
        return value
    if isinstance(value, Mapping):
        return ConfigToml.from_mapping(value)
    raise TypeError("cfg must be ConfigToml or mapping")


def _config_windows_sandbox_mode(config: Any) -> WindowsSandboxModeToml | None:
    permissions = getattr(config, "permissions", None)
    raw = getattr(permissions, "windows_sandbox_mode", None)
    if raw is None and isinstance(config, Mapping):
        permissions = config.get("permissions")
        if isinstance(permissions, Mapping):
            raw = permissions.get("windows_sandbox_mode")
    return WindowsSandboxModeToml(raw) if isinstance(raw, str) else raw


def _config_features(config: Any) -> Features:
    features = getattr(config, "features", None)
    if features is None and isinstance(config, Mapping):
        features = config.get("features")
    if isinstance(features, Features):
        return features
    raise TypeError("config.features must be Features when windows_sandbox_mode is not set")


def _bool_entries(entries: Mapping[str, bool]) -> dict[str, bool]:
    if not isinstance(entries, Mapping):
        raise TypeError("entries must be a mapping")
    result: dict[str, bool] = {}
    for key, value in entries.items():
        if not isinstance(key, str):
            raise TypeError("feature entry keys must be strings")
        if not isinstance(value, bool):
            raise TypeError("feature entry values must be bools")
        result[key] = value
    return result


__all__ = [
    "ELEVATED_SANDBOX_NUX_ENABLED",
    "ConfigToml",
    "WindowsSandboxModeToml",
    "WindowsSandboxSetupMode",
    "WindowsSandboxSetupRequest",
    "WindowsToml",
    "elevated_setup_failure_details",
    "elevated_setup_failure_metric_name",
    "legacy_windows_sandbox_mode",
    "legacy_windows_sandbox_mode_from_entries",
    "resolve_windows_sandbox_mode",
    "resolve_windows_sandbox_private_desktop",
    "run_elevated_setup",
    "run_legacy_setup_preflight",
    "run_setup_refresh_with_extra_read_roots",
    "run_windows_sandbox_setup",
    "sandbox_setup_is_complete",
    "windows_sandbox_level_from_config",
    "windows_sandbox_level_from_features",
    "windows_sandbox_setup_mode_tag",
]
