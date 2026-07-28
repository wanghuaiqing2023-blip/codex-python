"""RFC 9110/6750 ``WWW-Authenticate`` parsing for MCP OAuth."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InsufficientScopeChallenge:
    www_authenticate_header: str
    required_scope: str | None


@dataclass(frozen=True)
class BearerInsufficientScope:
    required_scope: str | None


_MISSING = object()
_INVALID = object()


def _header_field(header: Any, name: str) -> Any:
    if isinstance(header, Mapping):
        return header.get(name)
    return getattr(header, name)


def insufficient_scope_challenge(
    headers: Iterable[Any],
) -> InsufficientScopeChallenge | None:
    for header in headers:
        name = str(_header_field(header, "name"))
        if name.lower() != "www-authenticate":
            continue
        value = str(_header_field(header, "value"))
        parsed = parse_bearer_insufficient_scope(value)
        if parsed is not None:
            return InsufficientScopeChallenge(value, parsed.required_scope)
    return None


def parse_bearer_insufficient_scope(
    header: str,
) -> BearerInsufficientScope | None:
    segments = _split_unquoted_segments(header)
    if segments is None:
        return None
    challenge: dict[str, object] | None = None

    def finish() -> BearerInsufficientScope | None:
        if challenge is None or challenge["error"] != "insufficient_scope":
            return None
        scope = challenge["scope"]
        return BearerInsufficientScope(
            scope if isinstance(scope, str) and _valid_scope(scope) else None
        )

    for segment in segments:
        parameter = _parse_auth_param(segment)
        if parameter is not None:
            if challenge is not None:
                _add_parameter(challenge, *parameter)
            continue

        completed = finish()
        if completed is not None:
            return completed

        start = _parse_challenge_start(segment)
        if start is None:
            return None
        scheme, parameter = start
        challenge = None
        if scheme.lower() == "bearer":
            challenge = {"error": _MISSING, "scope": _MISSING}
            if parameter is not None:
                _add_parameter(challenge, *parameter)

    return finish()


def _add_parameter(
    challenge: dict[str, object],
    name: str,
    value: str | None,
) -> None:
    key = name.lower()
    if key not in {"error", "scope"}:
        return
    current = challenge[key]
    if current is _MISSING and value is not None:
        challenge[key] = value
    else:
        challenge[key] = _INVALID


def _parse_challenge_start(
    segment: str,
) -> tuple[str, tuple[str, str | None] | None] | None:
    segment = segment.strip()
    if not segment:
        return None
    split_at = next(
        (index for index, char in enumerate(segment) if char.isspace()),
        None,
    )
    if split_at is None:
        scheme, parameter = segment, None
    else:
        scheme = segment[:split_at]
        parameter = _parse_auth_param(segment[split_at:])
    if not _is_http_token(scheme):
        return None
    return scheme, parameter


def _parse_auth_param(segment: str) -> tuple[str, str | None] | None:
    if "=" not in segment:
        return None
    name, value = segment.strip().split("=", 1)
    name = name.strip()
    if not _is_http_token(name):
        return None
    return name, _parse_auth_param_value(value.strip())


def _parse_auth_param_value(value: str) -> str | None:
    if value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            return None
        decoded: list[str] = []
        index = 1
        end = len(value) - 1
        while index < end:
            char = value[index]
            if char == "\\":
                index += 1
                if index >= end:
                    return None
                decoded.append(value[index])
            else:
                decoded.append(char)
            index += 1
        return "".join(decoded)
    return value if _is_http_token(value) else None


def _split_unquoted_segments(header: str) -> list[str] | None:
    segments: list[str] = []
    start = 0
    in_quotes = False
    escaped = False
    for index, char in enumerate(header):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_quotes:
            escaped = True
        elif char == '"':
            in_quotes = not in_quotes
        elif char in {",", ";"} and not in_quotes:
            segments.append(header[start:index])
            start = index + 1
    if in_quotes or escaped:
        return None
    segments.append(header[start:])
    return segments


def _valid_scope(scope: str) -> bool:
    return all(
        token
        and all(
            byte == 0x21 or 0x23 <= byte <= 0x5B or 0x5D <= byte <= 0x7E
            for byte in token.encode("utf-8")
        )
        for token in scope.split(" ")
    )


def _is_http_token(value: str) -> bool:
    allowed = "!#$%&'*+-.^_`|~"
    return bool(value) and all(char.isascii() and (char.isalnum() or char in allowed) for char in value)


__all__ = [
    "BearerInsufficientScope",
    "InsufficientScopeChallenge",
    "insufficient_scope_challenge",
    "parse_bearer_insufficient_scope",
]
