"""Profile TOML data shapes ported from ``codex-config::profile_toml``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_CONFIG_PROFILE_FIELDS = (
    "model",
    "service_tier",
    "model_provider",
    "approval_policy",
    "approvals_reviewer",
    "sandbox_mode",
    "model_reasoning_effort",
    "plan_mode_reasoning_effort",
    "model_reasoning_summary",
    "model_verbosity",
    "model_catalog_json",
    "personality",
    "chatgpt_base_url",
    "model_instructions_file",
    "js_repl_node_path",
    "js_repl_node_module_dirs",
    "experimental_compact_prompt_file",
    "include_permissions_instructions",
    "include_apps_instructions",
    "include_collaboration_mode_instructions",
    "include_environment_context",
    "experimental_use_unified_exec_tool",
    "tools",
    "web_search",
    "analytics",
    "tui",
    "windows",
    "features",
    "oss_provider",
)

_CONFIG_PROFILE_FIELD_SET = set(_CONFIG_PROFILE_FIELDS)
_PROFILE_TUI_FIELDS = ("session_picker_view",)
_PROFILE_TUI_FIELD_SET = set(_PROFILE_TUI_FIELDS)


@dataclass(frozen=True)
class ProfileTui:
    """TUI settings supported inside a named profile."""

    session_picker_view: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ProfileTui | None":
        if value is None:
            return None
        data = _mapping(value, "profile tui")
        _deny_unknown(data, _PROFILE_TUI_FIELD_SET, "profile tui")
        session_picker_view = data.get("session_picker_view")
        if session_picker_view is not None and session_picker_view not in {
            "comfortable",
            "dense",
        }:
            raise ValueError("session_picker_view must be 'comfortable' or 'dense'")
        return cls(session_picker_view=session_picker_view)

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.session_picker_view is not None:
            data["session_picker_view"] = self.session_picker_view
        return data


@dataclass(frozen=True)
class ConfigProfile:
    """Common configuration options a user can define as a profile."""

    model: str | None = None
    service_tier: str | None = None
    model_provider: str | None = None
    approval_policy: str | None = None
    approvals_reviewer: str | None = None
    sandbox_mode: str | None = None
    model_reasoning_effort: str | None = None
    plan_mode_reasoning_effort: str | None = None
    model_reasoning_summary: str | None = None
    model_verbosity: str | None = None
    model_catalog_json: Path | None = None
    personality: str | None = None
    chatgpt_base_url: str | None = None
    model_instructions_file: Path | None = None
    js_repl_node_path: Path | None = None
    js_repl_node_module_dirs: tuple[Path, ...] | None = None
    experimental_compact_prompt_file: Path | None = None
    include_permissions_instructions: bool | None = None
    include_apps_instructions: bool | None = None
    include_collaboration_mode_instructions: bool | None = None
    include_environment_context: bool | None = None
    experimental_use_unified_exec_tool: bool | None = None
    tools: Mapping[str, Any] | None = None
    web_search: str | None = None
    analytics: Mapping[str, Any] | None = None
    tui: ProfileTui | None = None
    windows: Mapping[str, Any] | None = None
    features: Mapping[str, Any] | None = None
    oss_provider: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ConfigProfile":
        if value is None:
            return cls()
        data = _mapping(value, "config profile")
        _deny_unknown(data, _CONFIG_PROFILE_FIELD_SET, "config profile")
        return cls(
            model=_optional_str(data, "model"),
            service_tier=_optional_str(data, "service_tier"),
            model_provider=_optional_str(data, "model_provider"),
            approval_policy=_optional_str(data, "approval_policy"),
            approvals_reviewer=_optional_str(data, "approvals_reviewer"),
            sandbox_mode=_optional_str(data, "sandbox_mode"),
            model_reasoning_effort=_optional_str(data, "model_reasoning_effort"),
            plan_mode_reasoning_effort=_optional_str(data, "plan_mode_reasoning_effort"),
            model_reasoning_summary=_optional_str(data, "model_reasoning_summary"),
            model_verbosity=_optional_str(data, "model_verbosity"),
            model_catalog_json=_optional_path(data, "model_catalog_json"),
            personality=_optional_str(data, "personality"),
            chatgpt_base_url=_optional_str(data, "chatgpt_base_url"),
            model_instructions_file=_optional_path(data, "model_instructions_file"),
            js_repl_node_path=_optional_path(data, "js_repl_node_path"),
            js_repl_node_module_dirs=_optional_path_tuple(
                data, "js_repl_node_module_dirs"
            ),
            experimental_compact_prompt_file=_optional_path(
                data, "experimental_compact_prompt_file"
            ),
            include_permissions_instructions=_optional_bool(
                data, "include_permissions_instructions"
            ),
            include_apps_instructions=_optional_bool(data, "include_apps_instructions"),
            include_collaboration_mode_instructions=_optional_bool(
                data, "include_collaboration_mode_instructions"
            ),
            include_environment_context=_optional_bool(
                data, "include_environment_context"
            ),
            experimental_use_unified_exec_tool=_optional_bool(
                data, "experimental_use_unified_exec_tool"
            ),
            tools=_optional_mapping(data, "tools"),
            web_search=_optional_str(data, "web_search"),
            analytics=_optional_mapping(data, "analytics"),
            tui=ProfileTui.from_mapping(data.get("tui")),
            windows=_optional_mapping(data, "windows"),
            features=_optional_mapping(data, "features"),
            oss_provider=_optional_str(data, "oss_provider"),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in _CONFIG_PROFILE_FIELDS:
            value = getattr(self, field)
            if value is None:
                continue
            if isinstance(value, ProfileTui):
                data[field] = value.to_mapping()
            elif isinstance(value, Path):
                data[field] = str(value)
            elif isinstance(value, tuple) and all(isinstance(item, Path) for item in value):
                data[field] = [str(item) for item in value]
            else:
                data[field] = value
        return data


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _deny_unknown(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise KeyError(f"{label} has unknown fields: {', '.join(unknown)}")


def _optional_str(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string or None")
    return item


def _optional_bool(value: Mapping[str, Any], key: str) -> bool | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise TypeError(f"{key} must be a bool or None")
    return item


def _optional_path(value: Mapping[str, Any], key: str) -> Path | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, (str, Path)):
        raise TypeError(f"{key} must be a path string or None")
    return Path(item)


def _optional_path_tuple(value: Mapping[str, Any], key: str) -> tuple[Path, ...] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, list):
        raise TypeError(f"{key} must be a list of path strings or None")
    if not all(isinstance(path, (str, Path)) for path in item):
        raise TypeError(f"{key} must contain path strings")
    return tuple(Path(path) for path in item)


def _optional_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise TypeError(f"{key} must be a mapping or None")
    return item


__all__ = ["ConfigProfile", "ProfileTui"]
