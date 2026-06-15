"""Strict config validation helpers ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pycodex.features import is_known_feature_key

from .diagnostics import (
    ConfigError,
    config_error_from_toml,
    default_range,
    span_for_toml_key_path,
    text_range_from_span,
)
from .toml_compat import TOMLDecodeError, loads

DEFAULT_CONFIG_TOML_FIELDS = frozenset(
    {
        "approval_policy",
        "child_agents_md",
        "desktop",
        "features",
        "model",
        "model_context_window",
        "permissions",
        "profiles",
        "project_doc_max_bytes",
        "project_root_markers",
        "user_instructions",
    }
)


def config_error_from_ignored_toml_fields(
    path: str | Path,
    contents: str,
    allowed_fields: Iterable[str] | None = None,
    validator: Callable[[Mapping[str, Any]], ConfigError | None] | None = None,
) -> ConfigError | None:
    try:
        value = loads(contents)
    except TOMLDecodeError as err:
        return config_error_from_toml(path, contents, err)
    return config_error_from_ignored_toml_value_fields(path, contents, value, allowed_fields, validator)


def config_error_from_ignored_toml_value_fields(
    path: str | Path,
    contents: str,
    value: Mapping[str, Any],
    allowed_fields: Iterable[str] | None = None,
    validator: Callable[[Mapping[str, Any]], ConfigError | None] | None = None,
) -> ConfigError | None:
    return _config_error_from_ignored_toml_value_fields_for_source(
        Path(path),
        contents,
        value,
        allowed_fields,
        validator,
    )


def config_error_from_ignored_toml_value_fields_for_source_name(
    source_name: str,
    contents: str,
    value: Mapping[str, Any],
    allowed_fields: Iterable[str] | None = None,
    validator: Callable[[Mapping[str, Any]], ConfigError | None] | None = None,
) -> ConfigError | None:
    return _config_error_from_ignored_toml_value_fields_for_source(
        Path(source_name),
        contents,
        value,
        allowed_fields,
        validator,
    )


def ignored_toml_value_field(
    value: Mapping[str, Any],
    allowed_fields: Iterable[str] | None = None,
) -> str | None:
    paths = _ignored_toml_value_paths(value, allowed_fields)
    return ".".join(paths[0]) if paths else None


def unknown_feature_toml_value_field(value: Mapping[str, Any]) -> str | None:
    paths = _unknown_feature_toml_value_paths(value)
    return ".".join(paths[0]) if paths else None


def _config_error_from_ignored_toml_value_fields_for_source(
    source: Path,
    contents: str,
    value: Mapping[str, Any],
    allowed_fields: Iterable[str] | None,
    validator: Callable[[Mapping[str, Any]], ConfigError | None] | None,
) -> ConfigError | None:
    if validator is not None:
        error = validator(value)
        if error is not None:
            return error

    ignored_paths = _ignored_toml_value_paths(value, allowed_fields)
    unknown_feature_paths = _unknown_feature_toml_value_paths(value)
    return _unknown_field_error_from_paths(source, contents, ignored_paths) or _unknown_field_error_from_paths(
        source, contents, unknown_feature_paths
    )


def _ignored_toml_value_paths(
    value: Mapping[str, Any],
    allowed_fields: Iterable[str] | None,
) -> list[list[str]]:
    allowed = set(DEFAULT_CONFIG_TOML_FIELDS if allowed_fields is None else allowed_fields)
    paths: list[list[str]] = []
    for key in value:
        if key not in allowed:
            paths.append([str(key)])
    return paths


def _unknown_feature_toml_value_paths(value: Mapping[str, Any]) -> list[list[str]]:
    paths: list[list[str]] = []
    _push_unknown_feature_paths(paths, ("features",), value.get("features"))
    profiles = value.get("profiles")
    if isinstance(profiles, Mapping):
        for profile_name, profile in profiles.items():
            if isinstance(profile, Mapping):
                _push_unknown_feature_paths(paths, ("profiles", str(profile_name), "features"), profile.get("features"))
    return paths


def _push_unknown_feature_paths(
    paths: list[list[str]],
    prefix: Sequence[str],
    features: Any,
) -> None:
    if not isinstance(features, Mapping):
        return
    for feature_key in features:
        key = str(feature_key)
        if not is_known_feature_key(key):
            paths.append([*prefix, key])


def _unknown_field_error_from_paths(
    source: Path,
    contents: str,
    ignored_paths: list[list[str]],
) -> ConfigError | None:
    if not ignored_paths:
        return None
    path_segments = ignored_paths[0]
    ignored_path = ".".join(path_segments)
    span = span_for_toml_key_path(contents, path_segments)
    range_ = text_range_from_span(contents, span) if span is not None else default_range()
    return ConfigError(source, range_, f"unknown configuration field `{ignored_path}`")


__all__ = [
    "DEFAULT_CONFIG_TOML_FIELDS",
    "config_error_from_ignored_toml_fields",
    "config_error_from_ignored_toml_value_fields",
    "config_error_from_ignored_toml_value_fields_for_source_name",
    "ignored_toml_value_field",
    "unknown_feature_toml_value_field",
]
