"""Rust-aligned projection of ``codex-network-proxy::mitm_hook``."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import fnmatch
import json
import os
import re
import socket
import stat
import sys
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Mapping, Sequence

JsonValue = Any

@dataclass(frozen=True)
class InjectedHeaderConfig:
    name: str
    secret_env_var: str | None = None
    secret_file: str | None = None
    prefix: str | None = None


@dataclass(frozen=True)
class MitmHookActionsConfig:
    strip_request_headers: list[str] = field(default_factory=list)
    inject_request_headers: list[InjectedHeaderConfig] = field(default_factory=list)


@dataclass(frozen=True)
class MitmHookMatchConfig:
    methods: list[str] = field(default_factory=list)
    path_prefixes: list[str] = field(default_factory=list)
    query: Mapping[str, list[str]] = field(default_factory=dict)
    headers: Mapping[str, list[str]] = field(default_factory=dict)
    body: JsonValue | None = None


@dataclass(frozen=True)
class MitmHookConfig:
    host: str
    matcher: MitmHookMatchConfig = field(default_factory=MitmHookMatchConfig)
    actions: MitmHookActionsConfig = field(default_factory=MitmHookActionsConfig)


@dataclass(frozen=True)
class CompiledGlobMatcher:
    pattern: str
    literal_separator: bool = False

    def __post_init__(self) -> None:
        _validate_glob_pattern(self.pattern)

    def is_match(self, candidate: str) -> bool:
        if self.literal_separator:
            return re.fullmatch(_glob_to_regex(self.pattern, literal_separator=True), candidate) is not None
        return fnmatch.fnmatchcase(candidate, self.pattern)


@dataclass(frozen=True)
class PathMatcher:
    kind: str
    value: str
    glob: CompiledGlobMatcher | None = None

    @classmethod
    def prefix(cls, value: str) -> "PathMatcher":
        return cls("prefix", value)

    @classmethod
    def glob_matcher(cls, pattern: str) -> "PathMatcher":
        return cls("glob", pattern, CompiledGlobMatcher(pattern, literal_separator=True))

    def matches(self, candidate: str) -> bool:
        if self.kind == "prefix":
            return candidate.startswith(self.value)
        assert self.glob is not None
        return self.glob.is_match(candidate)


@dataclass(frozen=True)
class ValueMatcher:
    kind: str
    value: str
    glob: CompiledGlobMatcher | None = None

    @classmethod
    def exact(cls, value: str) -> "ValueMatcher":
        return cls("exact", value)

    @classmethod
    def glob_matcher(cls, pattern: str) -> "ValueMatcher":
        return cls("glob", pattern, CompiledGlobMatcher(pattern, literal_separator=False))

    def matches(self, candidate: str) -> bool:
        if self.kind == "exact":
            return candidate == self.value
        assert self.glob is not None
        return self.glob.is_match(candidate)


@dataclass(frozen=True)
class QueryConstraint:
    name: str
    allowed_values: tuple[ValueMatcher, ...]


@dataclass(frozen=True)
class HeaderConstraint:
    name: str
    allowed_values: tuple[ValueMatcher, ...]


@dataclass(frozen=True)
class SecretSource:
    kind: str
    value: str

    @classmethod
    def env_var(cls, name: str) -> "SecretSource":
        return cls("env_var", name)

    @classmethod
    def file(cls, path: str) -> "SecretSource":
        return cls("file", str(Path(path)))


@dataclass(frozen=True)
class ResolvedInjectedHeader:
    name: str
    value: str
    source: SecretSource


@dataclass(frozen=True)
class MitmHookActions:
    strip_request_headers: tuple[str, ...] = ()
    inject_request_headers: tuple[ResolvedInjectedHeader, ...] = ()


@dataclass(frozen=True)
class MitmHookMatcher:
    methods: tuple[str, ...] = ()
    path_prefixes: tuple[PathMatcher, ...] = ()
    query: tuple[QueryConstraint, ...] = ()
    headers: tuple[HeaderConstraint, ...] = ()
    body: JsonValue | None = None


@dataclass(frozen=True)
class MitmHook:
    host: str
    matcher: MitmHookMatcher
    actions: MitmHookActions


class HookEvaluation(Enum):
    NO_HOOKS_FOR_HOST = "NoHooksForHost"
    HOOKED_HOST_NO_MATCH = "HookedHostNoMatch"
    MATCHED = "Matched"


@dataclass(frozen=True)
class MitmHookEvaluation:
    kind: HookEvaluation
    actions: MitmHookActions | None = None

    @classmethod
    def no_hooks_for_host(cls) -> "MitmHookEvaluation":
        return cls(HookEvaluation.NO_HOOKS_FOR_HOST)

    @classmethod
    def hooked_host_no_match(cls) -> "MitmHookEvaluation":
        return cls(HookEvaluation.HOOKED_HOST_NO_MATCH)

    @classmethod
    def matched(cls, actions: MitmHookActions) -> "MitmHookEvaluation":
        return cls(HookEvaluation.MATCHED, actions)

    def is_matched(self) -> bool:
        return self.kind is HookEvaluation.MATCHED


def _validate_mitm_hook_config(config: NetworkProxyConfig) -> None:
    try:
        validate_mitm_hook_config(config)
    except (TypeError, ValueError) as exc:
        raise NetworkProxyConstraintError(
            "network.mitm_hooks",
            str(exc),
            "valid MITM hook configuration",
        ) from exc


def validate_mitm_hook_config(config: NetworkProxyConfig) -> None:
    hooks = [_coerce_mitm_hook_config(hook) for hook in config.network.mitm_hooks]
    if not hooks:
        return
    if not config.network.mitm:
        raise ValueError("network.mitm_hooks requires network.mitm = true")
    for hook_index, hook in enumerate(hooks):
        try:
            host = _normalize_hook_host(hook.host)
            methods = _normalize_methods(hook.matcher.methods)
            if not methods:
                raise ValueError(f"network.mitm_hooks[{hook_index}].match.methods must not be empty")
            path_prefixes = _compile_path_matchers(hook.matcher.path_prefixes)
            if not path_prefixes:
                raise ValueError(f"network.mitm_hooks[{hook_index}].match.path_prefixes must not be empty")
            if hook.matcher.body is not None:
                raise ValueError(
                    f"network.mitm_hooks[{hook_index}].match.body is reserved for a future release and is not yet supported"
                )
            _validate_query_constraints(hook.matcher.query)
            _validate_header_constraints(hook.matcher.headers)
            _validate_strip_request_headers(hook.actions.strip_request_headers)
            _validate_injected_headers(hook.actions.inject_request_headers)
            if not host:
                raise ValueError(f"network.mitm_hooks[{hook_index}].host must not be empty")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid network.mitm_hooks[{hook_index}]: {exc}") from exc


def compile_mitm_hooks(config: NetworkProxyConfig) -> dict[str, list[MitmHook]]:
    return compile_mitm_hooks_with_resolvers(
        config,
        resolve_env_var=lambda name: os.environ.get(name),
        read_secret_file=lambda path: Path(path).read_text(encoding="utf-8").strip(),
    )


def compile_mitm_hooks_with_resolvers(
    config: NetworkProxyConfig,
    resolve_env_var: Callable[[str], str | None],
    read_secret_file: Callable[[str], str],
) -> dict[str, list[MitmHook]]:
    validate_mitm_hook_config(config)
    hooks_by_host: dict[str, list[MitmHook]] = {}
    for raw_hook in config.network.mitm_hooks:
        hook = _coerce_mitm_hook_config(raw_hook)
        host = _normalize_hook_host(hook.host)
        query = tuple(
            QueryConstraint(_normalize_query_name(name), tuple(_compile_value_matchers(values)))
            for name, values in hook.matcher.query.items()
        )
        headers = tuple(
            HeaderConstraint(_parse_header_name(name), tuple(_compile_value_matchers(values)))
            for name, values in hook.matcher.headers.items()
        )
        actions = MitmHookActions(
            strip_request_headers=tuple(_parse_header_name(name) for name in hook.actions.strip_request_headers),
            inject_request_headers=tuple(
                _compile_injected_header(header, resolve_env_var, read_secret_file)
                for header in hook.actions.inject_request_headers
            ),
        )
        compiled = MitmHook(
            host=host,
            matcher=MitmHookMatcher(
                methods=tuple(_normalize_methods(hook.matcher.methods)),
                path_prefixes=tuple(_compile_path_matchers(hook.matcher.path_prefixes)),
                query=query,
                headers=headers,
                body=None,
            ),
            actions=actions,
        )
        hooks_by_host.setdefault(host, []).append(compiled)
    return hooks_by_host


def evaluate_mitm_hooks(
    hooks_by_host: Mapping[str, Sequence[MitmHook]],
    host: str,
    request: Any,
) -> MitmHookEvaluation:
    hooks = hooks_by_host.get(normalize_host(host))
    if hooks is None:
        return MitmHookEvaluation.no_hooks_for_host()
    for hook in hooks:
        if _mitm_hook_matches(hook, request):
            return MitmHookEvaluation.matched(hook.actions)
    return MitmHookEvaluation.hooked_host_no_match()


def _compile_injected_header(
    header: InjectedHeaderConfig,
    resolve_env_var: Callable[[str], str | None],
    read_secret_file: Callable[[str], str],
) -> ResolvedInjectedHeader:
    name = _parse_header_name(header.name)
    if header.secret_env_var is not None and header.secret_file is None:
        secret = resolve_env_var(header.secret_env_var)
        if secret is None:
            raise ValueError(f"missing required environment variable {header.secret_env_var}")
        source = SecretSource.env_var(header.secret_env_var)
    elif header.secret_env_var is None and header.secret_file is not None:
        path = _parse_secret_file(header.secret_file)
        secret = read_secret_file(path)
        source = SecretSource.file(path)
    else:
        raise ValueError("expected exactly one of secret_env_var or secret_file")
    prefix = header.prefix or ""
    value = f"{prefix}{secret}"
    _validate_header_value(value, f"invalid value for injected header {header.name}")
    return ResolvedInjectedHeader(name=name, value=value, source=source)


def _mitm_hook_matches(hook: MitmHook, request: Any) -> bool:
    method = _request_method(request).upper()
    if method not in hook.matcher.methods:
        return False
    uri = _request_uri(request)
    parsed = urlparse(uri)
    path = parsed.path or uri.split("?", 1)[0] or "/"
    if not any(matcher.matches(path) for matcher in hook.matcher.path_prefixes):
        return False
    if not _mitm_query_matches(hook.matcher.query, parsed.query):
        return False
    return _mitm_headers_match(hook.matcher.headers, _request_headers(request))


def _mitm_query_matches(query_constraints: Sequence[QueryConstraint], raw_query: str) -> bool:
    if not query_constraints:
        return True
    actual_values: dict[str, list[str]] = {}
    for name, value in parse_qsl(raw_query, keep_blank_values=True):
        actual_values.setdefault(name, []).append(value)
    for constraint in query_constraints:
        actual = actual_values.get(constraint.name)
        if not actual:
            return False
        if not any(allowed.matches(candidate) for candidate in actual for allowed in constraint.allowed_values):
            return False
    return True


def _mitm_headers_match(header_constraints: Sequence[HeaderConstraint], headers: Mapping[str, Any]) -> bool:
    normalized: dict[str, list[str]] = {}
    for name, raw_value in headers.items():
        values = raw_value if isinstance(raw_value, list | tuple) else [raw_value]
        normalized.setdefault(name.lower(), []).extend(str(value) for value in values)
    for constraint in header_constraints:
        actual = normalized.get(constraint.name.lower())
        if not actual:
            return False
        if not constraint.allowed_values:
            continue
        if not any(allowed.matches(candidate) for candidate in actual for allowed in constraint.allowed_values):
            return False
    return True


def _coerce_mitm_hook_config(value: Any) -> MitmHookConfig:
    if isinstance(value, MitmHookConfig):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("MITM hook entries must be objects")
    matcher_value = value.get("match", value.get("matcher", {})) or {}
    actions_value = value.get("actions", {}) or {}
    if not isinstance(matcher_value, Mapping):
        raise TypeError("MITM hook match must be an object")
    if not isinstance(actions_value, Mapping):
        raise TypeError("MITM hook actions must be an object")
    injected = actions_value.get("inject_request_headers", []) or []
    if isinstance(injected, str) or not isinstance(injected, Sequence):
        raise TypeError("inject_request_headers must be a sequence")
    return MitmHookConfig(
        host=str(value.get("host", "")),
        matcher=MitmHookMatchConfig(
            methods=list(_string_tuple(matcher_value.get("methods", []), "methods")),
            path_prefixes=list(_string_tuple(matcher_value.get("path_prefixes", []), "path_prefixes")),
            query=_coerce_string_list_mapping(matcher_value.get("query", {}), "query"),
            headers=_coerce_string_list_mapping(matcher_value.get("headers", {}), "headers"),
            body=matcher_value.get("body"),
        ),
        actions=MitmHookActionsConfig(
            strip_request_headers=list(
                _string_tuple(actions_value.get("strip_request_headers", []), "strip_request_headers")
            ),
            inject_request_headers=_coerce_injected_headers(injected),
        ),
    )


def _coerce_injected_headers(values: Sequence[Any]) -> list[InjectedHeaderConfig]:
    result: list[InjectedHeaderConfig] = []
    for item in values:
        if isinstance(item, InjectedHeaderConfig):
            result.append(item)
            continue
        if not isinstance(item, Mapping):
            raise TypeError("inject_request_headers entries must be objects")
        result.append(
            InjectedHeaderConfig(
                name=str(item.get("name", "")),
                secret_env_var=item.get("secret_env_var"),
                secret_file=item.get("secret_file"),
                prefix=item.get("prefix"),
            )
        )
    return result


def _coerce_string_list_mapping(value: Any, field_name: str) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    return {str(key): list(_string_tuple(values, field_name)) for key, values in value.items()}


def _normalize_hook_host(host: str) -> str:
    normalized = normalize_host(host)
    if not normalized:
        raise ValueError("host must not be empty")
    if "*" in normalized:
        raise ValueError("MITM hook hosts must be exact hosts and cannot contain wildcards")
    return normalized


def _normalize_methods(methods: Sequence[str]) -> list[str]:
    result: list[str] = []
    for method in methods:
        normalized = method.strip().upper()
        if not normalized:
            raise ValueError("methods must not contain empty entries")
        result.append(normalized)
    return result


def _compile_path_matchers(path_prefixes: Sequence[str]) -> list[PathMatcher]:
    result: list[PathMatcher] = []
    for prefix in path_prefixes:
        kind, pattern = _parse_matcher_pattern(prefix)
        if kind == "literal":
            if pattern == "":
                raise ValueError("path_prefixes must not contain empty entries")
            result.append(PathMatcher.prefix(pattern))
        else:
            result.append(PathMatcher.glob_matcher(pattern))
    return result


def _compile_value_matchers(values: Sequence[str]) -> list[ValueMatcher]:
    result: list[ValueMatcher] = []
    for value in values:
        kind, pattern = _parse_matcher_pattern(value)
        result.append(ValueMatcher.exact(pattern) if kind == "literal" else ValueMatcher.glob_matcher(pattern))
    return result


def _parse_matcher_pattern(pattern: str) -> tuple[str, str]:
    if pattern.startswith("literal:"):
        return ("literal", pattern[len("literal:") :])
    if pattern.startswith("pattern:"):
        glob_pattern = pattern[len("pattern:") :]
        if not glob_pattern:
            raise ValueError("glob pattern must not be empty")
        _validate_glob_pattern(glob_pattern)
        return ("glob", glob_pattern)
    return ("literal", pattern)


def _validate_query_constraints(query: Mapping[str, Sequence[str]]) -> None:
    for name, values in query.items():
        normalized = _normalize_query_name(name)
        if not normalized:
            raise ValueError("query keys must not be empty")
        if not values:
            raise ValueError(f"query key {name!r} must list at least one allowed value")
        _compile_value_matchers(values)


def _normalize_query_name(name: str) -> str:
    if name == "":
        raise ValueError("query keys must not be empty")
    return name


def _validate_header_constraints(headers: Mapping[str, Sequence[str]]) -> None:
    for name, values in headers.items():
        _parse_header_name(name)
        _compile_value_matchers(values)


def _validate_strip_request_headers(header_names: Sequence[str]) -> None:
    for name in header_names:
        _parse_header_name(name)


def _validate_injected_headers(headers: Sequence[InjectedHeaderConfig]) -> None:
    for header in headers:
        _parse_header_name(header.name)
        if header.secret_env_var is not None and header.secret_file is None:
            if not header.secret_env_var.strip():
                raise ValueError("secret_env_var must not be empty")
        elif header.secret_env_var is None and header.secret_file is not None:
            _parse_secret_file(header.secret_file)
        else:
            raise ValueError("expected exactly one of secret_env_var or secret_file")


_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _parse_header_name(name: str) -> str:
    if not isinstance(name, str) or _HEADER_NAME_RE.fullmatch(name) is None:
        raise ValueError(f"invalid header name {name!r}")
    return name.lower()


def _parse_secret_file(path: str) -> str:
    if not path.strip():
        raise ValueError("secret_file must not be empty")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError(f"secret_file must be an absolute path: {path!r}")
    return str(candidate)


def _validate_header_value(value: str, message: str) -> None:
    if "\r" in value or "\n" in value:
        raise ValueError(message)


def _validate_glob_pattern(pattern: str) -> None:
    in_class = False
    escaped = False
    for ch in pattern:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "[":
            if in_class:
                raise ValueError(f"invalid glob pattern {pattern!r}")
            in_class = True
        elif ch == "]":
            if not in_class:
                raise ValueError(f"invalid glob pattern {pattern!r}")
            in_class = False
    if in_class:
        raise ValueError(f"invalid glob pattern {pattern!r}")


def _glob_to_regex(pattern: str, *, literal_separator: bool) -> str:
    pieces = ["^"]
    index = 0
    while index < len(pattern):
        ch = pattern[index]
        if ch == "*":
            pieces.append("[^/]*" if literal_separator else ".*")
        elif ch == "?":
            pieces.append("[^/]" if literal_separator else ".")
        elif ch == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                raise ValueError(f"invalid glob pattern {pattern!r}")
            cls = pattern[index : end + 1]
            pieces.append(cls)
            index = end
        elif ch == "\\" and index + 1 < len(pattern):
            index += 1
            pieces.append(re.escape(pattern[index]))
        else:
            pieces.append(re.escape(ch))
        index += 1
    pieces.append("$")
    return "".join(pieces)

from .config import (
    NetworkProxyConfig,
    _string_tuple,
)
from .mitm import (
    _request_headers,
    _request_method,
    _request_uri,
)
from .policy import normalize_host
from .state import NetworkProxyConstraintError

__all__ = [
    "CompiledGlobMatcher",
    "HeaderConstraint",
    "HookEvaluation",
    "InjectedHeaderConfig",
    "MitmHook",
    "MitmHookActions",
    "MitmHookActionsConfig",
    "MitmHookConfig",
    "MitmHookEvaluation",
    "MitmHookMatchConfig",
    "MitmHookMatcher",
    "PathMatcher",
    "QueryConstraint",
    "ResolvedInjectedHeader",
    "SecretSource",
    "ValueMatcher",
    "compile_mitm_hooks",
    "compile_mitm_hooks_with_resolvers",
    "evaluate_mitm_hooks",
    "validate_mitm_hook_config",
]
