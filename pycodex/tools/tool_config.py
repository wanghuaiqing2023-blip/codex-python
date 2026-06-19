"""Tool configuration helpers ported from ``codex-rs/tools/src/tool_config.rs``."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core.tools import ToolUserShellType
from pycodex.core.tools.handlers.request_user_input import (
    request_user_input_available_modes as _request_user_input_available_modes,
)
from pycodex.core.tools.handlers.shell import ShellCommandBackendConfig
from pycodex.core.tools.handlers.unified_exec import UnifiedExecShellMode, ZshForkConfig
from pycodex.features import Feature, Features
from pycodex.protocol.config_types import ModeKind
from pycodex.protocol.openai_models import ConfigShellToolType, ModelInfo
from pycodex.utils.pty import conpty_supported as _conpty_supported


class ToolEnvironmentMode(str, Enum):
    NONE = "none"
    SINGLE = "single"
    MULTIPLE = "multiple"

    @classmethod
    def from_count(cls, count: int) -> "ToolEnvironmentMode":
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("count must be an integer")
        if count < 0:
            raise ValueError("count must be non-negative")
        if count == 0:
            return cls.NONE
        if count == 1:
            return cls.SINGLE
        return cls.MULTIPLE

    def has_environment(self) -> bool:
        return self is not ToolEnvironmentMode.NONE


def request_user_input_available_modes(features: Any) -> tuple[ModeKind, ...]:
    return _request_user_input_available_modes(
        default_mode_enabled=_feature_enabled(features, Feature.DEFAULT_MODE_REQUEST_USER_INPUT),
    )


def shell_command_backend_for_features(features: Any) -> ShellCommandBackendConfig:
    if _feature_enabled(features, Feature.SHELL_TOOL) and _feature_enabled(features, Feature.SHELL_ZSH_FORK):
        return ShellCommandBackendConfig.ZSH_FORK
    return ShellCommandBackendConfig.CLASSIC


def shell_type_for_model_and_features(
    model_info: ModelInfo | Mapping[str, Any] | Any,
    features: Any,
    *,
    conpty_supported: bool | None = None,
) -> ConfigShellToolType:
    model_shell_type = _model_shell_type(model_info)
    unified_exec_enabled = _feature_enabled(features, Feature.UNIFIED_EXEC)

    if model_shell_type is ConfigShellToolType.UNIFIED_EXEC and not unified_exec_enabled:
        model_shell_type = ConfigShellToolType.SHELL_COMMAND
    elif model_shell_type in {ConfigShellToolType.DEFAULT, ConfigShellToolType.LOCAL}:
        model_shell_type = ConfigShellToolType.SHELL_COMMAND

    if not _feature_enabled(features, Feature.SHELL_TOOL):
        return ConfigShellToolType.DISABLED
    if _feature_enabled(features, Feature.SHELL_ZSH_FORK):
        return ConfigShellToolType.SHELL_COMMAND
    if unified_exec_enabled:
        if conpty_supported is None:
            conpty_supported = _conpty_supported()
        return ConfigShellToolType.UNIFIED_EXEC if conpty_supported else ConfigShellToolType.SHELL_COMMAND
    return model_shell_type


def unified_exec_shell_mode_for_session(
    shell_command_backend: ShellCommandBackendConfig | str,
    user_shell_type: ToolUserShellType | str,
    shell_zsh_path: str | os.PathLike[str] | None,
    main_execve_wrapper_exe: str | os.PathLike[str] | None,
) -> UnifiedExecShellMode:
    backend = ShellCommandBackendConfig(shell_command_backend)
    shell_type = ToolUserShellType(user_shell_type)
    if (
        os.name == "posix"
        and backend is ShellCommandBackendConfig.ZSH_FORK
        and shell_type is ToolUserShellType.ZSH
        and shell_zsh_path is not None
        and main_execve_wrapper_exe is not None
    ):
        zsh_path = Path(shell_zsh_path)
        wrapper_path = Path(main_execve_wrapper_exe)
        if zsh_path.is_absolute() and wrapper_path.is_absolute():
            return UnifiedExecShellMode.zsh_fork(
                ZshForkConfig(
                    shell_zsh_path=zsh_path,
                    main_execve_wrapper_exe=wrapper_path,
                ),
            )
    return UnifiedExecShellMode.direct()


def _model_shell_type(model_info: ModelInfo | Mapping[str, Any] | Any) -> ConfigShellToolType:
    if isinstance(model_info, ModelInfo):
        return model_info.shell_type
    if isinstance(model_info, Mapping):
        try:
            return ConfigShellToolType(str(model_info["shell_type"]))
        except KeyError as exc:
            raise KeyError("model_info mapping must include shell_type") from exc
    shell_type = getattr(model_info, "shell_type", None)
    if shell_type is None:
        raise TypeError("model_info must provide shell_type")
    return ConfigShellToolType(str(shell_type))


def _feature_enabled(features: Any, feature: Feature) -> bool:
    if isinstance(features, Features):
        return features.enabled(feature)

    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        try:
            return bool(enabled(feature))
        except Exception:
            pass
        try:
            return bool(enabled(feature.value))
        except Exception:
            pass
        try:
            return bool(enabled(feature.name))
        except Exception:
            pass

    if isinstance(features, Mapping):
        for key in _feature_keys(feature):
            if key in features:
                return bool(features[key])
        return False

    if isinstance(features, Iterable) and not isinstance(features, (str, bytes)):
        values = set(features)
        return any(key in values for key in (feature, *_feature_keys(feature)))

    for key in _feature_keys(feature):
        attr_name = key if isinstance(key, str) else str(key)
        if hasattr(features, attr_name):
            return bool(getattr(features, attr_name))

    return False


def _feature_keys(feature: Feature) -> tuple[str, ...]:
    snake = []
    for char in feature.value:
        if char.isupper() and snake:
            snake.append("_")
        snake.append(char.lower())
    return (feature.value, feature.name, "".join(snake), feature.key())


__all__ = [
    "ShellCommandBackendConfig",
    "ToolEnvironmentMode",
    "ToolUserShellType",
    "UnifiedExecShellMode",
    "ZshForkConfig",
    "request_user_input_available_modes",
    "shell_command_backend_for_features",
    "shell_type_for_model_and_features",
    "unified_exec_shell_mode_for_session",
]
