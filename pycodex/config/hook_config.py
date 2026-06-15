"""Hook config TOML/JSON shapes ported from ``codex-config``."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.protocol import HookEventName

from . import toml_compat as _toml

JsonValue = Any

_EVENT_FIELDS: tuple[tuple[str, str, HookEventName], ...] = (
    ("PreToolUse", "pre_tool_use", HookEventName.PRE_TOOL_USE),
    ("PermissionRequest", "permission_request", HookEventName.PERMISSION_REQUEST),
    ("PostToolUse", "post_tool_use", HookEventName.POST_TOOL_USE),
    ("PreCompact", "pre_compact", HookEventName.PRE_COMPACT),
    ("PostCompact", "post_compact", HookEventName.POST_COMPACT),
    ("SessionStart", "session_start", HookEventName.SESSION_START),
    ("UserPromptSubmit", "user_prompt_submit", HookEventName.USER_PROMPT_SUBMIT),
    ("SubagentStart", "subagent_start", HookEventName.SUBAGENT_START),
    ("SubagentStop", "subagent_stop", HookEventName.SUBAGENT_STOP),
    ("Stop", "stop", HookEventName.STOP),
)


@dataclass(frozen=True)
class HookHandlerConfig:
    type: str
    command: str | None = None
    command_windows: str | None = None
    timeout_sec: int | None = None
    async_: bool = False
    status_message: str | None = None

    @classmethod
    def command_handler(
        cls,
        command: str,
        *,
        command_windows: str | None = None,
        timeout_sec: int | None = None,
        async_: bool = False,
        status_message: str | None = None,
    ) -> "HookHandlerConfig":
        return cls(
            "command",
            command=str(command),
            command_windows=command_windows,
            timeout_sec=timeout_sec,
            async_=async_,
            status_message=status_message,
        )

    @classmethod
    def prompt(cls) -> "HookHandlerConfig":
        return cls("prompt")

    @classmethod
    def agent(cls) -> "HookHandlerConfig":
        return cls("agent")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HookHandlerConfig":
        if not isinstance(value, Mapping):
            raise TypeError("hook handler config must be a mapping")
        handler_type = value.get("type")
        if handler_type == "command":
            command = value.get("command")
            if not isinstance(command, str):
                raise TypeError("command hook requires a string command")
            timeout = value.get("timeout")
            if timeout is not None and not isinstance(timeout, int):
                raise TypeError("command hook timeout must be an integer or None")
            command_windows = value.get("commandWindows", value.get("command_windows"))
            if command_windows is not None and not isinstance(command_windows, str):
                raise TypeError("command_windows must be a string or None")
            status_message = value.get("statusMessage")
            if status_message is not None and not isinstance(status_message, str):
                raise TypeError("statusMessage must be a string or None")
            async_value = value.get("async", False)
            if not isinstance(async_value, bool):
                raise TypeError("async must be a bool")
            return cls.command_handler(
                command,
                command_windows=command_windows,
                timeout_sec=timeout,
                async_=async_value,
                status_message=status_message,
            )
        if handler_type == "prompt":
            return cls.prompt()
        if handler_type == "agent":
            return cls.agent()
        raise ValueError(f"unknown hook handler type: {handler_type!r}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "command":
            data: dict[str, JsonValue] = {"type": "command", "command": self.command}
            if self.command_windows is not None:
                data["commandWindows"] = self.command_windows
            if self.timeout_sec is not None:
                data["timeout"] = self.timeout_sec
            if self.async_:
                data["async"] = self.async_
            if self.status_message is not None:
                data["statusMessage"] = self.status_message
            return data
        return {"type": self.type}


@dataclass(frozen=True)
class MatcherGroup:
    matcher: str | None = None
    hooks: tuple[HookHandlerConfig, ...] = ()

    def __post_init__(self) -> None:
        if self.matcher is not None and not isinstance(self.matcher, str):
            raise TypeError("matcher must be a string or None")
        object.__setattr__(self, "hooks", tuple(self.hooks))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "MatcherGroup":
        if not isinstance(value, Mapping):
            raise TypeError("matcher group must be a mapping")
        hooks = value.get("hooks", [])
        if not _is_sequence(hooks):
            raise TypeError("matcher group hooks must be a sequence")
        matcher = value.get("matcher")
        return cls(
            matcher=matcher if matcher is not None else None,
            hooks=tuple(
                hook if isinstance(hook, HookHandlerConfig) else HookHandlerConfig.from_mapping(hook)
                for hook in hooks
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.matcher is not None:
            data["matcher"] = self.matcher
        if self.hooks:
            data["hooks"] = [hook.to_mapping() for hook in self.hooks]
        return data


@dataclass(frozen=True)
class HookEventsToml:
    pre_tool_use: tuple[MatcherGroup, ...] = ()
    permission_request: tuple[MatcherGroup, ...] = ()
    post_tool_use: tuple[MatcherGroup, ...] = ()
    pre_compact: tuple[MatcherGroup, ...] = ()
    post_compact: tuple[MatcherGroup, ...] = ()
    session_start: tuple[MatcherGroup, ...] = ()
    user_prompt_submit: tuple[MatcherGroup, ...] = ()
    subagent_start: tuple[MatcherGroup, ...] = ()
    subagent_stop: tuple[MatcherGroup, ...] = ()
    stop: tuple[MatcherGroup, ...] = ()

    @classmethod
    def from_toml(cls, contents: str) -> "HookEventsToml":
        return cls.from_mapping(_toml.loads(contents))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "HookEventsToml":
        data = {} if value is None else dict(value)
        kwargs: dict[str, tuple[MatcherGroup, ...]] = {}
        for toml_key, field_name, _event in _EVENT_FIELDS:
            entries = data.get(toml_key, data.get(field_name, ()))
            if entries is None:
                entries = ()
            if not _is_sequence(entries):
                raise TypeError(f"{toml_key} must be a sequence")
            kwargs[field_name] = tuple(
                item if isinstance(item, MatcherGroup) else MatcherGroup.from_mapping(item)
                for item in entries
            )
        return cls(**kwargs)

    def is_empty(self) -> bool:
        return all(not groups for _toml_key, field_name, _event in _EVENT_FIELDS for groups in (getattr(self, field_name),))

    def handler_count(self) -> int:
        return sum(len(group.hooks) for _toml_key, field_name, _event in _EVENT_FIELDS for group in getattr(self, field_name))

    def into_matcher_groups(self) -> tuple[tuple[HookEventName, tuple[MatcherGroup, ...]], ...]:
        return tuple((event, getattr(self, field_name)) for _toml_key, field_name, event in _EVENT_FIELDS)

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        for toml_key, field_name, _event in _EVENT_FIELDS:
            groups = getattr(self, field_name)
            if groups:
                data[toml_key] = [group.to_mapping() for group in groups]
        return data


@dataclass(frozen=True)
class HookStateToml:
    enabled: bool | None = None
    trusted_hash: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HookStateToml":
        if not isinstance(value, Mapping):
            raise TypeError("hook state must be a mapping")
        enabled = value.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise TypeError("hook state enabled must be a bool or None")
        trusted_hash = value.get("trusted_hash")
        if trusted_hash is not None and not isinstance(trusted_hash, str):
            raise TypeError("hook state trusted_hash must be a string or None")
        return cls(enabled=enabled, trusted_hash=trusted_hash)

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.enabled is not None:
            data["enabled"] = self.enabled
        if self.trusted_hash is not None:
            data["trusted_hash"] = self.trusted_hash
        return data


@dataclass(frozen=True)
class HooksFile:
    hooks: HookEventsToml = field(default_factory=HookEventsToml)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HooksFile":
        if not isinstance(value, Mapping):
            raise TypeError("hooks file must be a mapping")
        return cls(hooks=HookEventsToml.from_mapping(value.get("hooks")))


@dataclass(frozen=True)
class HooksToml:
    events: HookEventsToml = field(default_factory=HookEventsToml)
    state: Mapping[str, HookStateToml] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", dict(sorted(self.state.items())))

    @classmethod
    def from_toml(cls, contents: str) -> "HooksToml":
        return cls.from_mapping(_toml.loads(contents))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "HooksToml":
        data = {} if value is None else dict(value)
        events = HookEventsToml.from_mapping(data)
        state_value = data.get("state", {})
        if not isinstance(state_value, Mapping):
            raise TypeError("hooks state must be a mapping")
        return cls(
            events=events,
            state={
                str(key): state if isinstance(state, HookStateToml) else HookStateToml.from_mapping(state)
                for key, state in state_value.items()
            },
        )


@dataclass(frozen=True)
class ManagedHooksRequirementsToml:
    managed_dir: Path | None = None
    windows_managed_dir: Path | None = None
    hooks: HookEventsToml = field(default_factory=HookEventsToml)

    def __post_init__(self) -> None:
        if self.managed_dir is not None:
            object.__setattr__(self, "managed_dir", Path(self.managed_dir))
        if self.windows_managed_dir is not None:
            object.__setattr__(self, "windows_managed_dir", Path(self.windows_managed_dir))

    @classmethod
    def from_toml(cls, contents: str) -> "ManagedHooksRequirementsToml":
        return cls.from_mapping(_toml.loads(contents))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "ManagedHooksRequirementsToml":
        data = {} if value is None else dict(value)
        managed_dir = data.get("managed_dir")
        windows_managed_dir = data.get("windows_managed_dir")
        return cls(
            managed_dir=Path(managed_dir) if managed_dir is not None else None,
            windows_managed_dir=Path(windows_managed_dir) if windows_managed_dir is not None else None,
            hooks=HookEventsToml.from_mapping(data),
        )

    def is_empty(self) -> bool:
        return self.managed_dir is None and self.windows_managed_dir is None and self.hooks.is_empty()

    def handler_count(self) -> int:
        return self.hooks.handler_count()

    def managed_dir_for_current_platform(self) -> Path | None:
        return self.windows_managed_dir if os.name == "nt" else self.managed_dir


def _is_sequence(value: JsonValue) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


__all__ = [
    "HookEventsToml",
    "HookHandlerConfig",
    "HookStateToml",
    "HooksFile",
    "HooksToml",
    "ManagedHooksRequirementsToml",
    "MatcherGroup",
]
