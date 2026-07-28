"""Python port of ``codex-hooks::engine.discovery``."""


from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import replace
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    HookCompletedEvent,
    HookEventName,
    HookExecutionMode,
    HookHandlerType,
    HookOutputEntry,
    HookOutputEntryKind,
    HookPromptFragment,
    HookRunStatus,
    HookRunSummary,
    HookScope,
    HookSource,
    HookTrustStatus,
    ThreadId,
    TruncationPolicyConfig,
)
from pycodex.config.hook_config import HookStateToml
from pycodex.config.hook_config import HookEventsToml
from pycodex.config.hook_config import HookHandlerConfig
from pycodex.config.hook_config import HooksFile
from pycodex.config.hook_config import MatcherGroup
from pycodex.config.fingerprint import version_for_toml
from pycodex.config.state import ConfigLayerStackOrdering
from pycodex.utils.output_truncation import approx_token_count
from pycodex.utils.output_truncation import formatted_truncate_text

from .. import hook_event_key_label, hook_key
from ..config_rules import hook_states_from_stack
from ..declarations import _field, _plugin_key
from ..events.common import matcher_pattern_for_event, validate_matcher_pattern
from . import ConfiguredHandler, HookListEntry

@dataclass
class DiscoveryResult:
    handlers: list[ConfiguredHandler] = field(default_factory=list)
    hook_entries: list[HookListEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _HookHandlerSource:
    path: Path
    key_source: str
    source: HookSource
    is_managed: bool
    bypass_hook_trust: bool
    hook_states: Mapping[str, HookStateToml]
    env: Mapping[str, str] = field(default_factory=dict)
    plugin_id: str | None = None


@dataclass(frozen=True)
class _HookDiscoveryPolicy:
    allow_managed_hooks_only: bool
    bypass_hook_trust: bool

    def allows(self, source: _HookHandlerSource) -> bool:
        return (not self.allow_managed_hooks_only) or source.is_managed


def _source_type(source: Any) -> str:
    return str(_field(source, "type", source))


def _synthetic_layer_path(path: str) -> Path:
    if os.name == "nt":
        return Path("C:/") / path.replace("\\", "/")
    return Path("/") / path


def _config_toml_source_path(layer: Any) -> Path:
    name = _field(layer, "name")
    name_type = _source_type(name)
    file = _field(name, "file")
    if name_type in {"system", "user", "legacy_managed_config_toml_from_file"} and file is not None:
        return Path(file)
    if name_type == "project":
        folder = _call_or_field(layer, "hooks_config_folder")
        if folder is None:
            folder = _field(name, "dot_codex_folder", ".")
        return Path(folder) / "config.toml"
    if name_type == "session_flags":
        return _synthetic_layer_path("<session-flags>/config.toml")
    if name_type == "mdm":
        return _synthetic_layer_path(
            f"<mdm:{_field(name, 'domain', '')}:{_field(name, 'key', '')}>/config.toml"
        )
    if name_type == "legacy_managed_config_toml_from_mdm":
        return _synthetic_layer_path("<legacy-managed-config.toml-mdm>/managed_config.toml")
    return _synthetic_layer_path(f"<{name_type}>/config.toml")


def _call_or_field(source: Any, name: str, default: Any = None) -> Any:
    value = _field(source, name, default)
    if callable(value):
        return value()
    return value


def _hook_metadata_for_config_layer_source(source: Any) -> tuple[HookSource, bool]:
    source_type = _source_type(source)
    if source_type == "system":
        return HookSource.SYSTEM, True
    if source_type == "user":
        return HookSource.USER, False
    if source_type == "project":
        return HookSource.PROJECT, False
    if source_type == "mdm":
        return HookSource.MDM, True
    if source_type == "session_flags":
        return HookSource.SESSION_FLAGS, False
    if source_type == "legacy_managed_config_toml_from_file":
        return HookSource.LEGACY_MANAGED_CONFIG_FILE, True
    if source_type == "legacy_managed_config_toml_from_mdm":
        return HookSource.LEGACY_MANAGED_CONFIG_MDM, True
    return HookSource.UNKNOWN, False


def _hook_source_for_requirement_source(source: Any | None) -> HookSource:
    source_type = _source_type(source) if source is not None else "unknown"
    if source_type == "mdm_managed_preferences":
        return HookSource.MDM
    if source_type == "system_requirements_toml":
        return HookSource.SYSTEM
    if source_type == "legacy_managed_config_toml_from_file":
        return HookSource.LEGACY_MANAGED_CONFIG_FILE
    if source_type == "legacy_managed_config_toml_from_mdm":
        return HookSource.LEGACY_MANAGED_CONFIG_MDM
    if source_type == "cloud_requirements":
        return HookSource.CLOUD_REQUIREMENTS
    return HookSource.UNKNOWN


def _load_hooks_json(
    config_folder: Path | str | None,
    warnings: list[str],
) -> tuple[Path, HookEventsToml] | None:
    if config_folder is None:
        return None
    source_path = Path(config_folder) / "hooks.json"
    if not source_path.is_file():
        return None
    try:
        contents = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"failed to read hooks config {source_path}: {exc}")
        return None
    try:
        parsed_json = json.loads(contents)
        parsed = HooksFile.from_mapping(parsed_json)
    except Exception as exc:
        warnings.append(f"failed to parse hooks config {source_path}: {exc}")
        return None
    if parsed.hooks.is_empty():
        return None
    return source_path, parsed.hooks


def _load_toml_hooks_from_layer(
    layer: Any,
    warnings: list[str],
) -> tuple[Path, HookEventsToml] | None:
    source_path = _config_toml_source_path(layer)
    config = _field(layer, "config", {})
    hook_value = config.get("hooks") if isinstance(config, Mapping) else _field(config, "hooks")
    if hook_value is None:
        return None
    try:
        parsed = HookEventsToml.from_mapping(hook_value)
    except Exception as exc:
        warnings.append(f"failed to parse TOML hooks in {source_path}: {exc}")
        return None
    if parsed.is_empty():
        return None
    return source_path, parsed


def _normalized_hook_identity_mapping(
    event_name: HookEventName,
    matcher: str | None,
    group: MatcherGroup,
    normalized_handler: HookHandlerConfig,
) -> dict[str, Any]:
    group_mapping = group.to_mapping()
    if matcher is None:
        group_mapping.pop("matcher", None)
    else:
        group_mapping["matcher"] = matcher
    group_mapping["hooks"] = [normalized_handler.to_mapping()]
    return {
        "event_name": hook_event_key_label(event_name),
        **group_mapping,
    }


def _command_hook_hash(
    event_name: HookEventName,
    matcher: str | None,
    group: MatcherGroup,
    normalized_handler: HookHandlerConfig,
) -> str:
    return version_for_toml(
        _normalized_hook_identity_mapping(
            event_name,
            matcher,
            group,
            normalized_handler,
        )
    )


def _hook_trust_status(
    is_managed: bool,
    current_hash: str,
    trusted_hash: str | None,
) -> HookTrustStatus:
    if is_managed:
        return HookTrustStatus.MANAGED
    if trusted_hash == current_hash:
        return HookTrustStatus.TRUSTED
    if trusted_hash is not None:
        return HookTrustStatus.MODIFIED
    return HookTrustStatus.UNTRUSTED


def _hook_enabled(is_managed: bool, state: HookStateToml | None) -> bool:
    return is_managed or (None if state is None else state.enabled) is not False


def _hook_trusted_hash(is_managed: bool, state: HookStateToml | None) -> str | None:
    if is_managed or state is None:
        return None
    return state.trusted_hash


def _append_matcher_groups(
    handlers: list[ConfiguredHandler],
    hook_entries: list[HookListEntry],
    warnings: list[str],
    display_order: list[int],
    source: _HookHandlerSource,
    event_name: HookEventName | str,
    groups: Sequence[MatcherGroup],
) -> None:
    event = HookEventName(event_name)
    for group_index, group in enumerate(groups):
        matcher = matcher_pattern_for_event(event, group.matcher)
        if matcher is not None:
            try:
                validate_matcher_pattern(matcher)
            except re.error as exc:
                warnings.append(f"invalid matcher {matcher!r} in {source.path}: {exc}")
                continue
        for handler_index, handler in enumerate(group.hooks):
            if handler.type == "command":
                command = handler.command or ""
                if os.name == "nt" and handler.command_windows is not None:
                    command = handler.command_windows
                if handler.async_:
                    warnings.append(
                        f"skipping async hook in {source.path}: async hooks are not supported yet"
                    )
                    continue
                if command.strip() == "":
                    warnings.append(f"skipping empty hook command in {source.path}")
                    continue
                timeout_sec = max(handler.timeout_sec or 600, 1)
                normalized_handler = HookHandlerConfig.command_handler(
                    command,
                    timeout_sec=timeout_sec,
                    async_=handler.async_,
                    status_message=handler.status_message,
                )
                current_hash = _command_hook_hash(
                    event,
                    matcher,
                    group,
                    normalized_handler,
                )
                for key, value in source.env.items():
                    command = command.replace(f"${{{key}}}", value)
                key = hook_key(source.key_source, event, group_index, handler_index)
                state = source.hook_states.get(key)
                enabled = _hook_enabled(source.is_managed, state)
                trust_status = _hook_trust_status(
                    source.is_managed,
                    current_hash,
                    _hook_trusted_hash(source.is_managed, state),
                )
                entry = HookListEntry(
                    key=key,
                    event_name=event,
                    handler_type=HookHandlerType.COMMAND,
                    matcher=matcher,
                    command=command,
                    timeout_sec=timeout_sec,
                    status_message=handler.status_message,
                    source_path=source.path,
                    source=source.source,
                    plugin_id=source.plugin_id,
                    display_order=display_order[0],
                    enabled=enabled,
                    is_managed=source.is_managed,
                    current_hash=current_hash,
                    trust_status=trust_status,
                )
                hook_entries.append(entry)
                if enabled and (
                    source.bypass_hook_trust
                    or trust_status in {HookTrustStatus.MANAGED, HookTrustStatus.TRUSTED}
                ):
                    handlers.append(
                        ConfiguredHandler(
                            event_name=event,
                            matcher=matcher,
                            command=command,
                            timeout_sec=timeout_sec,
                            status_message=handler.status_message,
                            source_path=source.path,
                            source=source.source,
                            display_order=display_order[0],
                            env=dict(source.env),
                        )
                    )
                display_order[0] += 1
            elif handler.type == "prompt":
                warnings.append(
                    f"skipping prompt hook in {source.path}: prompt hooks are not supported yet"
                )
            elif handler.type == "agent":
                warnings.append(
                    f"skipping agent hook in {source.path}: agent hooks are not supported yet"
                )


def _append_hook_events(
    handlers: list[ConfiguredHandler],
    hook_entries: list[HookListEntry],
    warnings: list[str],
    display_order: list[int],
    source: _HookHandlerSource,
    hook_events: HookEventsToml,
    policy: _HookDiscoveryPolicy,
) -> None:
    if not policy.allows(source):
        return
    for event_name, groups in hook_events.into_matcher_groups():
        _append_matcher_groups(
            handlers,
            hook_entries,
            warnings,
            display_order,
            source,
            event_name,
            groups,
        )


def _append_plugin_hook_sources(
    handlers: list[ConfiguredHandler],
    hook_entries: list[HookListEntry],
    warnings: list[str],
    display_order: list[int],
    plugin_hook_sources: Sequence[Any],
    hook_states: Mapping[str, HookStateToml],
    policy: _HookDiscoveryPolicy,
) -> None:
    for plugin_source in plugin_hook_sources:
        plugin_root = Path(_field(plugin_source, "plugin_root", ""))
        plugin_data_root = Path(_field(plugin_source, "plugin_data_root", ""))
        plugin_id = _plugin_key(_field(plugin_source, "plugin_id", ""))
        source_relative_path = str(_field(plugin_source, "source_relative_path", ""))
        hooks = _field(plugin_source, "hooks", HookEventsToml())
        if isinstance(hooks, Mapping):
            hooks = HookEventsToml.from_mapping(hooks)
        env = {
            "PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "PLUGIN_DATA": str(plugin_data_root),
            "CLAUDE_PLUGIN_DATA": str(plugin_data_root),
        }
        _append_hook_events(
            handlers,
            hook_entries,
            warnings,
            display_order,
            _HookHandlerSource(
                path=Path(_field(plugin_source, "source_path", plugin_root / source_relative_path)),
                key_source=f"{plugin_id}:{source_relative_path}",
                source=HookSource.PLUGIN,
                is_managed=False,
                bypass_hook_trust=policy.bypass_hook_trust,
                hook_states=hook_states,
                env=env,
                plugin_id=plugin_id,
            ),
            hooks,
            policy,
        )


def _requirements_value(config_layer_stack: Any | None) -> Any | None:
    if config_layer_stack is None:
        return None
    requirements = _field(config_layer_stack, "requirements", None)
    if callable(requirements):
        return requirements()
    return requirements


def _allow_managed_hooks_only(config_layer_stack: Any | None) -> bool:
    requirements = _requirements_value(config_layer_stack)
    managed_only = _field(requirements, "allow_managed_hooks_only", None)
    value = _field(managed_only, "value", managed_only)
    return bool(value) if value is not None else False


def discover_handlers(
    config_layer_stack: Any | None,
    plugin_hook_sources: Sequence[Any],
    plugin_hook_load_warnings: Sequence[str],
    bypass_hook_trust: bool,
) -> DiscoveryResult:
    handlers: list[ConfiguredHandler] = []
    hook_entries: list[HookListEntry] = []
    warnings = list(plugin_hook_load_warnings)
    display_order = [0]
    hook_states = hook_states_from_stack(config_layer_stack)
    policy = _HookDiscoveryPolicy(
        allow_managed_hooks_only=_allow_managed_hooks_only(config_layer_stack),
        bypass_hook_trust=bypass_hook_trust,
    )

    if config_layer_stack is not None:
        if hasattr(config_layer_stack, "get_layers"):
            layers = config_layer_stack.get_layers(
                ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST,
                False,
            )
        elif isinstance(config_layer_stack, Sequence):
            layers = config_layer_stack
        else:
            layers = []
        for layer in layers:
            hook_source, is_managed = _hook_metadata_for_config_layer_source(_field(layer, "name"))
            source_path = _config_toml_source_path(layer)
            if not policy.allows(
                _HookHandlerSource(
                    path=source_path,
                    key_source=str(source_path),
                    source=hook_source,
                    is_managed=is_managed,
                    bypass_hook_trust=False,
                    hook_states=hook_states,
                )
            ):
                continue
            json_hooks = _load_hooks_json(_call_or_field(layer, "hooks_config_folder"), warnings)
            toml_hooks = _load_toml_hooks_from_layer(layer, warnings)
            if (
                json_hooks is not None
                and toml_hooks is not None
                and not json_hooks[1].is_empty()
                and not toml_hooks[1].is_empty()
            ):
                warnings.append(
                    "loading hooks from both "
                    f"{json_hooks[0]} and {toml_hooks[0]}; "
                    "prefer a single representation for this layer"
                )
            for source_path, hook_events in (item for item in (json_hooks, toml_hooks) if item is not None):
                _append_hook_events(
                    handlers,
                    hook_entries,
                    warnings,
                    display_order,
                    _HookHandlerSource(
                        path=source_path,
                        key_source=str(source_path),
                        source=hook_source,
                        is_managed=is_managed,
                        bypass_hook_trust=policy.bypass_hook_trust,
                        hook_states=hook_states,
                    ),
                    hook_events,
                    policy,
                )

    _append_plugin_hook_sources(
        handlers,
        hook_entries,
        warnings,
        display_order,
        plugin_hook_sources,
        hook_states,
        policy,
    )
    return DiscoveryResult(handlers, hook_entries, warnings)
