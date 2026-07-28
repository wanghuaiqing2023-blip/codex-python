"""Module loading policy ported from ``runtime/module_loader.rs``."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from . import CompletionState
from .value import value_to_error_text
JsonValue = Any

EXIT_SENTINEL = "__codex_code_mode_exit__"


UNSUPPORTED_DYNAMIC_IMPORT_ERROR = "unsupported import in exec"


def is_exit_sentinel(value: JsonValue) -> bool:
    return isinstance(value, str) and value == EXIT_SENTINEL


def is_exit_exception(exit_requested: bool, exception: JsonValue) -> bool:
    return bool(exit_requested) and is_exit_sentinel(exception)


def completion_state_from_rejection(
    exception: JsonValue,
    *,
    exit_requested: bool,
    stored_value_writes: Mapping[str, JsonValue] | None = None,
) -> CompletionState:
    return CompletionState.completed(
        stored_value_writes=stored_value_writes,
        error_text=(
            None
            if is_exit_exception(exit_requested, exception)
            else value_to_error_text(exception)
        ),
    )


def unsupported_static_import_error(specifier: str) -> str:
    return f"Unsupported import in exec: {specifier}"


def unsupported_dynamic_import_error() -> str:
    return UNSUPPORTED_DYNAMIC_IMPORT_ERROR
