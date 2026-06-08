"""Config-time OTEL defaults and metadata sanitization.

Ported from ``codex/codex-rs/core/src/config/otel.rs`` with validation helpers
mirroring the stdlib-only portions of ``codex/codex-rs/otel/src``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.core.otel_init import OtelConfig, OtelExporterKind

DEFAULT_OTEL_ENVIRONMENT = "dev"


def resolve_config(config: Mapping[str, Any] | OtelConfig | None, startup_warnings: list[str] | None = None) -> OtelConfig:
    """Apply Rust ``OtelConfigToml`` defaults and drop invalid metadata."""

    warnings = startup_warnings if startup_warnings is not None else []
    if config is None:
        config = {}
    if isinstance(config, OtelConfig):
        raw = {
            "log_user_prompt": config.log_user_prompt,
            "environment": config.environment,
            "exporter": config.exporter,
            "trace_exporter": config.trace_exporter,
            "metrics_exporter": config.metrics_exporter,
            "span_attributes": config.span_attributes,
            "tracestate": config.tracestate,
        }
    elif isinstance(config, Mapping):
        raw = config
    else:
        raise TypeError("otel config must be a mapping, OtelConfig, or None")

    return OtelConfig(
        log_user_prompt=_optional_bool(raw, "log_user_prompt", False),
        environment=_optional_str(raw, "environment", DEFAULT_OTEL_ENVIRONMENT),
        exporter=_exporter_or_default(raw.get("exporter"), OtelExporterKind.none()),
        trace_exporter=_exporter_or_default(raw.get("trace_exporter"), OtelExporterKind.none()),
        metrics_exporter=_exporter_or_default(raw.get("metrics_exporter"), OtelExporterKind.statsig()),
        span_attributes=resolve_span_attributes(raw.get("span_attributes"), warnings),
        tracestate=resolve_tracestate(raw.get("tracestate"), warnings),
    )


def resolve_span_attributes(span_attributes: Any, startup_warnings: list[str]) -> dict[str, str]:
    if span_attributes is None:
        return {}
    attributes = _string_mapping(span_attributes, "otel.span_attributes")
    resolved: dict[str, str] = {}
    for key, value in sorted(attributes.items()):
        try:
            validate_span_attributes({key: value})
        except ValueError as exc:
            push_invalid_config_warning("otel.span_attributes", exc, startup_warnings)
            continue
        resolved[key] = value
    return resolved


def resolve_tracestate(tracestate: Any, startup_warnings: list[str]) -> dict[str, dict[str, str]]:
    if tracestate is None:
        return {}
    entries = _nested_string_mapping(tracestate, "otel.tracestate")
    resolved: dict[str, dict[str, str]] = {}
    for member_key, fields in sorted(entries.items()):
        sanitized = resolve_tracestate_member_fields(member_key, fields, startup_warnings)
        if not sanitized:
            continue
        try:
            validate_tracestate_member(member_key, sanitized)
        except ValueError as exc:
            push_invalid_config_warning("otel.tracestate", exc, startup_warnings)
            continue
        resolved[member_key] = sanitized

    try:
        validate_tracestate_entries(resolved)
    except ValueError as exc:
        push_invalid_config_warning("otel.tracestate", exc, startup_warnings)
        return {}
    return resolved


def resolve_tracestate_member_fields(member_key: str, fields: Mapping[str, str], startup_warnings: list[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for field_key, value in sorted(fields.items()):
        try:
            validate_tracestate_member(member_key, {field_key: value})
        except ValueError as exc:
            push_invalid_config_warning("otel.tracestate", exc, startup_warnings)
            continue
        resolved[field_key] = value
    return resolved


def push_invalid_config_warning(config_key: str, err: Exception, startup_warnings: list[str]) -> None:
    startup_warnings.append(f"Ignoring invalid `{config_key}` config: {err}")


def validate_span_attributes(attributes: Mapping[str, str]) -> None:
    if any(key == "" for key in attributes):
        raise ValueError("configured span attribute key must not be empty")


def validate_tracestate_entries(entries: Mapping[str, Mapping[str, str]]) -> None:
    encoded = [_encode_tracestate_member_fields(key, fields) for key, fields in sorted(entries.items())]
    if len(encoded) > 32:
        raise ValueError("invalid configured tracestate: too many list-members")
    header = ",".join(f"{key}={value}" for key, value in encoded)
    if len(header) > 512:
        raise ValueError("invalid configured tracestate: header is too large")
    seen: set[str] = set()
    for key, _value in encoded:
        if key in seen:
            raise ValueError("invalid configured tracestate: duplicate list-member key")
        seen.add(key)
        if not _is_tracestate_member_key(key):
            raise ValueError("invalid configured tracestate: invalid list-member key")


def validate_tracestate_member(member_key: str, fields: Mapping[str, str]) -> None:
    key, value = _encode_tracestate_member_fields(member_key, fields)
    if not _is_tracestate_member_key(key):
        raise ValueError("invalid configured tracestate: invalid list-member key")
    if len(f"{key}={value}") > 512:
        raise ValueError("invalid configured tracestate: list-member is too large")


def _encode_tracestate_member_fields(member_key: str, fields: Mapping[str, str]) -> tuple[str, str]:
    encoded: list[str] = []
    for field_key, value in sorted(fields.items()):
        if not _is_configured_tracestate_field_key(field_key):
            raise ValueError(f"invalid configured tracestate field key {member_key}.{field_key}")
        if not _is_configured_tracestate_field_value(value):
            raise ValueError(f"invalid configured tracestate value for {member_key}.{field_key}")
        encoded.append(f"{field_key}:{value}")
    value = ";".join(encoded)
    if not _is_header_safe_tracestate_member_value(value):
        raise ValueError(f"invalid configured tracestate value for {member_key}")
    return member_key, value


def _is_configured_tracestate_field_key(field_key: str) -> bool:
    return bool(field_key) and all(33 <= ord(char) <= 126 and char not in ":;,=" for char in field_key)


def _is_configured_tracestate_field_value(value: str) -> bool:
    return all(_is_tracestate_member_value_byte(ord(char)) and char != ";" for char in value)


def _is_header_safe_tracestate_member_value(value: str) -> bool:
    return value == "" or (all(_is_tracestate_member_value_byte(ord(char)) for char in value) and not value.endswith(" "))


def _is_tracestate_member_value_byte(byte: int) -> bool:
    return 32 <= byte <= 126 and byte not in (ord(","), ord("="))


def _is_tracestate_member_key(key: str) -> bool:
    if not key or len(key) > 256:
        return False
    if key.count("@") > 1:
        return False
    if "@" in key:
        tenant, system = key.split("@", 1)
        return bool(tenant) and len(tenant) <= 241 and _is_key_part(tenant) and _is_key_part(system)
    return _is_key_part(key)


def _is_key_part(value: str) -> bool:
    allowed_extra = "_-*/."
    return (
        bool(value)
        and value[0].islower()
        and value[0].isascii()
        and value[0].isalnum()
        and all(char.isascii() and (char.islower() or char.isdigit() or char in allowed_extra) for char in value)
    )


def _exporter_or_default(value: Any, default: OtelExporterKind) -> OtelExporterKind:
    if value is None:
        return default
    if isinstance(value, OtelExporterKind):
        return value
    return OtelExporterKind.from_mapping(value)


def _optional_bool(value: Mapping[str, Any], key: str, default: bool) -> bool:
    item = value.get(key, default)
    if not isinstance(item, bool):
        raise TypeError(f"{key} must be a bool")
    return item


def _optional_str(value: Mapping[str, Any], key: str, default: str) -> str:
    item = value.get(key, default)
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


def _string_mapping(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise TypeError(f"{label} must contain string keys and values")
    return dict(value)


def _nested_string_mapping(value: Any, label: str) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    if not all(isinstance(key, str) and isinstance(item, Mapping) for key, item in value.items()):
        raise TypeError(f"{label} must contain string keys and mapping values")
    return {key: _string_mapping(item, f"{label}.{key}") for key, item in value.items()}


__all__ = [
    "DEFAULT_OTEL_ENVIRONMENT",
    "push_invalid_config_warning",
    "resolve_config",
    "resolve_span_attributes",
    "resolve_tracestate",
    "resolve_tracestate_member_fields",
    "validate_span_attributes",
    "validate_tracestate_entries",
    "validate_tracestate_member",
]
