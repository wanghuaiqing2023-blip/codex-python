"""Behavior port for Rust ``codex-tui::config_update``.

Upstream source: ``codex/codex-rs/tui/src/config_update.rs``.

This module mirrors the Rust helper layer that builds config edit objects and
app-server request payloads.  Real app-server transport is intentionally
injected through a request handle, matching Rust's ``RequestHandler`` boundary
without fabricating a server.
"""

from __future__ import annotations

import inspect
import json
import sys
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="config_update",
    source="codex/codex-rs/tui/src/config_update.rs",
    status="complete",
)

SERVICE_TIER_DEFAULT_REQUEST_VALUE = "default"

FEATURE_DEFAULTS = {
    "undo": False,
    "shell_tool": True,
    "unified_exec": sys.platform != "win32",
    "shell_zsh_fork": False,
    "shell_snapshot": True,
    "js_repl": False,
    "code_mode": False,
    "code_mode_only": False,
    "js_repl_tools_only": False,
    "terminal_resize_reflow": True,
    "web_search_request": False,
    "web_search_cached": False,
    "standalone_web_search": False,
    "search_tool": False,
    "codex_git_commit": False,
    "runtime_metrics": False,
    "sqlite": True,
    "memories": False,
    "chronicle": False,
    "child_agents_md": False,
    "apply_patch_freeform": False,
    "apply_patch_streaming_events": False,
    "exec_permission_approvals": False,
    "hooks": True,
    "request_permissions_tool": False,
    "use_linux_sandbox_bwrap": False,
    "use_legacy_landlock": False,
    "request_rule": False,
    "experimental_windows_sandbox": False,
    "elevated_windows_sandbox": False,
    "remote_models": False,
    "enable_request_compression": True,
    "network_proxy": False,
    "multi_agent": True,
    "multi_agent_v2": False,
    "enable_fanout": False,
    "apps": True,
    "enable_mcp_apps": False,
    "apps_mcp_path_override": False,
    "tool_search": False,
    "tool_search_always_defer_mcp_tools": False,
    "non_prefixed_mcp_tool_names": False,
    "unavailable_dummy_tools": False,
    "tool_suggest": True,
    "plugins": True,
    "plugin_hooks": False,
    "in_app_browser": True,
    "browser_use": True,
    "browser_use_external": True,
    "computer_use": True,
    "remote_plugin": False,
    "plugin_sharing": True,
    "external_migration": False,
    "image_generation": True,
    "skill_mcp_dependency_install": True,
    "skill_env_var_dependency_prompt": False,
    "mentions_v2": False,
    "steer": True,
    "default_mode_request_user_input": False,
    "guardian_approval": True,
    "goals": True,
    "collaboration_modes": True,
    "tool_call_mcp_elicitation": True,
    "auth_elicitation": False,
    "personality": True,
    "artifact": False,
    "fast_mode": True,
    "realtime_conversation": False,
    "remote_control": False,
    "image_detail_original": False,
    "tui_app_server": True,
    "prevent_idle_sleep": False,
    "workspace_owner_usage_nudge": False,
    "responses_websockets": False,
    "responses_websockets_v2": False,
    "responses_websocket_response_processed": False,
    "remote_compaction_v2": False,
    "workspace_dependencies": True,
}


class MergeStrategy(str, Enum):
    """Semantic mirror of Rust ``ConfigEdit.merge_strategy`` values."""

    REPLACE = "replace"


@dataclass(frozen=True)
class ConfigEdit:
    key_path: str
    value: Any
    merge_strategy: MergeStrategy = MergeStrategy.REPLACE


@dataclass(frozen=True)
class ConfigBatchWriteParams:
    edits: List[ConfigEdit]
    file_path: Optional[str] = None
    expected_version: Optional[int] = None
    reload_user_config: bool = True


@dataclass(frozen=True)
class ConfigReadParams:
    include_layers: bool = False
    cwd: Optional[str] = None


@dataclass(frozen=True)
class SkillsConfigWriteParams:
    path: Optional[str]
    name: Optional[str]
    enabled: bool


@dataclass(frozen=True)
class ClientRequest:
    id: str
    kind: str
    params: Any


class RequestHandle(Protocol):
    def request_typed(self, request: ClientRequest) -> Any:
        ...


def replace_config_value(key_path: str, value: Any) -> ConfigEdit:
    """Build a replacing config edit, matching Rust ``replace_config_value``."""

    return ConfigEdit(key_path=str(key_path), value=value, merge_strategy=MergeStrategy.REPLACE)


def clear_config_value(key_path: str) -> ConfigEdit:
    """Build a config edit that clears a key by writing JSON null."""

    return replace_config_value(key_path, None)


def app_scoped_key_path(app_id: str, key_path: str) -> str:
    """Scope a config key under ``apps.<json quoted app id>``."""

    return f"apps.{json.dumps(str(app_id))}.{key_path}"


def _project_trust_key(project_path: Union[str, Path]) -> str:
    return str(project_path)


def trusted_project_edit(project_path: Union[str, Path]) -> ConfigEdit:
    """Build the project trust-level edit used by onboarding/trust flows."""

    project_key = _project_trust_key(project_path).replace("\\", "\\\\").replace('"', '\\"')
    return replace_config_value(f'projects."{project_key}".trust_level', "trusted")


def build_model_selection_edits(model: str, effort: Optional[Any]) -> List[ConfigEdit]:
    """Build the config edits emitted when a model/effort selection changes."""

    edits = [replace_config_value("model", str(model))]
    if effort is None:
        edits.append(clear_config_value("model_reasoning_effort"))
    else:
        edits.append(replace_config_value("model_reasoning_effort", str(effort)))
    return edits


def _service_tier_config_value(service_tier: str) -> str:
    if service_tier == SERVICE_TIER_DEFAULT_REQUEST_VALUE:
        return SERVICE_TIER_DEFAULT_REQUEST_VALUE
    if service_tier in {"fast", "priority"}:
        return "fast"
    if service_tier == "flex":
        return "flex"
    return service_tier


def build_service_tier_selection_edits(service_tier: Optional[str]) -> List[ConfigEdit]:
    """Build the config edit emitted when service tier selection changes."""

    if service_tier is None:
        return [clear_config_value("service_tier")]
    return [replace_config_value("service_tier", _service_tier_config_value(str(service_tier)))]


def build_windows_sandbox_mode_edits(elevated_enabled: bool) -> List[ConfigEdit]:
    """Build the Windows sandbox migration edits from the Rust helper."""

    sandbox_value = "elevated" if elevated_enabled else "unelevated"
    return [
        replace_config_value("windows.sandbox", sandbox_value),
        clear_config_value("features.experimental_windows_sandbox"),
        clear_config_value("features.elevated_windows_sandbox"),
        clear_config_value("features.enable_experimental_windows_sandbox"),
    ]


def _is_default_false_feature(feature_key: str, feature_defaults: Union[Mapping[str, bool], Sequence[Any], None]) -> bool:
    if feature_defaults is None:
        return False
    if isinstance(feature_defaults, Mapping):
        return feature_defaults.get(feature_key) is False
    for spec in feature_defaults:
        key = getattr(spec, "key", None)
        if key is None and isinstance(spec, Mapping):
            key = spec.get("key")
        if key != feature_key:
            continue
        default = getattr(spec, "default_enabled", None)
        if default is None:
            default = getattr(spec, "default", None)
        if default is None and isinstance(spec, Mapping):
            default = spec.get("default_enabled")
        if default is None and isinstance(spec, Mapping):
            default = spec.get("default")
        return default is False
    return False


def build_feature_enabled_edit(
    feature_key: str,
    enabled: bool,
    *,
    feature_defaults: Union[Mapping[str, bool], Sequence[Any], None] = None,
) -> ConfigEdit:
    """Build the feature toggle config edit.

    Rust consults ``codex_features::FEATURES`` and clears keys for default-false
    features when disabling them.  Python carries the same key/default table for
    the TUI helper while still accepting an injected catalog for focused tests.
    """

    key_path = f"features.{feature_key}"
    if feature_defaults is None:
        feature_defaults = FEATURE_DEFAULTS
    if enabled or not _is_default_false_feature(str(feature_key), feature_defaults):
        return replace_config_value(key_path, bool(enabled))
    return clear_config_value(key_path)


def build_memory_settings_edits(use_memories: bool, generate_memories: bool) -> List[ConfigEdit]:
    return [
        replace_config_value("memories.use_memories", bool(use_memories)),
        replace_config_value("memories.generate_memories", bool(generate_memories)),
    ]


def build_oss_provider_edit(provider: str) -> ConfigEdit:
    return replace_config_value("oss_provider", str(provider))


def _request_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


async def _send_request(request_handle: RequestHandle, request: ClientRequest) -> Any:
    result = request_handle.request_typed(request)
    if inspect.isawaitable(result):
        return await result
    return result


async def write_config_batch(request_handle: RequestHandle, edits: Sequence[ConfigEdit]) -> Any:
    params = ConfigBatchWriteParams(edits=list(edits))
    request = ClientRequest(id=_request_id("tui-config-write"), kind="ConfigBatchWrite", params=params)
    return await _send_request(request_handle, request)


async def write_trusted_project(request_handle: RequestHandle, project_path: Union[str, Path]) -> Any:
    return await write_config_batch(request_handle, [trusted_project_edit(project_path)])


async def read_effective_config(request_handle: RequestHandle, cwd: Union[str, Path]) -> Any:
    params = ConfigReadParams(include_layers=False, cwd=str(cwd))
    request = ClientRequest(id=_request_id("tui-config-read"), kind="ConfigRead", params=params)
    return await _send_request(request_handle, request)


async def write_skill_enabled(request_handle: RequestHandle, path: Union[str, Path], enabled: bool) -> Any:
    params = SkillsConfigWriteParams(path=str(path), name=None, enabled=bool(enabled))
    request = ClientRequest(id=_request_id("tui-skill-config-write"), kind="SkillsConfigWrite", params=params)
    return await _send_request(request_handle, request)


def app_scoped_key_path_quotes_dotted_app_ids() -> None:
    """Executable parity assertion for the Rust unit test of the same name."""

    assert app_scoped_key_path("plugin.linear", "enabled") == 'apps."plugin.linear".enabled'


def trusted_project_edit_targets_project_trust_level() -> None:
    """Executable parity assertion for the Rust unit test of the same name."""

    assert trusted_project_edit("/workspace/team.project") == ConfigEdit(
        key_path='projects."/workspace/team.project".trust_level',
        value="trusted",
        merge_strategy=MergeStrategy.REPLACE,
    )


__all__ = [
    "ClientRequest",
    "ConfigBatchWriteParams",
    "ConfigEdit",
    "FEATURE_DEFAULTS",
    "ConfigReadParams",
    "MergeStrategy",
    "RUST_MODULE",
    "RequestHandle",
    "SERVICE_TIER_DEFAULT_REQUEST_VALUE",
    "SkillsConfigWriteParams",
    "app_scoped_key_path",
    "app_scoped_key_path_quotes_dotted_app_ids",
    "build_feature_enabled_edit",
    "build_memory_settings_edits",
    "build_model_selection_edits",
    "build_oss_provider_edit",
    "build_service_tier_selection_edits",
    "build_windows_sandbox_mode_edits",
    "clear_config_value",
    "read_effective_config",
    "replace_config_value",
    "trusted_project_edit",
    "trusted_project_edit_targets_project_trust_level",
    "write_config_batch",
    "write_skill_enabled",
    "write_trusted_project",
]
