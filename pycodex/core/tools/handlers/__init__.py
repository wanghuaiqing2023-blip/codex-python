"""Core tool handler modules aligned with ``codex-rs/core/src/tools/handlers``.

Concrete handlers still live in their submodules.  The shared pure helper layer
from Rust's ``core/src/tools/handlers/mod.rs`` is re-exported here so all
handlers use one common argument parsing, hook rewrite, and permission boundary.
The exports are intentionally lazy to avoid importing concrete handlers through
``pycodex.core`` during package initialization.
"""

__all__ = [
    "EffectiveAdditionalPermissions",
    "apply_granted_turn_permissions",
    "implicit_granted_permissions",
    "intersect_permission_profiles",
    "merge_permission_profiles",
    "normalize_additional_permissions",
    "normalize_and_validate_additional_permissions",
    "normalize_request_permissions_response",
    "parse_arguments",
    "parse_arguments_with_base_path",
    "permissions_are_preapproved",
    "record_granted_request_permissions",
    "resolve_tool_environment",
    "resolve_workdir_base_path",
    "rewrite_function_arguments",
    "rewrite_function_string_argument",
    "session_strict_auto_review",
    "updated_hook_command",
]


def __getattr__(name: str):
    if name in __all__:
        from . import utils

        return getattr(utils, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
