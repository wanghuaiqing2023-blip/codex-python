import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("bin.write_hooks_schema_fixtures", "main"),
        ("config_rules", "hook_states_from_stack"),
        ("declarations", "PluginHookDeclaration"),
        ("engine", "CommandShell"),
        ("engine.command_runner", "run_command"),
        ("engine.discovery", "discover_handlers"),
        ("engine.dispatcher", "execute_handlers"),
        ("engine.output_parser", "parse_pre_tool_use"),
        ("engine.schema_loader", "GeneratedHookSchemas"),
        ("events.common", "SubagentHookContext"),
        ("events.compact", "PreCompactRequest"),
        ("events.permission_request", "PermissionRequestRequest"),
        ("events.post_tool_use", "PostToolUseRequest"),
        ("events.pre_tool_use", "PreToolUseRequest"),
        ("events.session_start", "SessionStartRequest"),
        ("events.stop", "StopRequest"),
        ("events.user_prompt_submit", "UserPromptSubmitRequest"),
        ("legacy_notify", "legacy_notify_json"),
        ("output_spill", "HookOutputSpiller"),
        ("registry", "Hooks"),
        ("schema", "write_schema_fixtures"),
        ("types", "Hook"),
    ],
)
def test_hooks_item_has_rust_aligned_owner(
    module_name: str, symbol: str
) -> None:
    """Rust source: codex-hooks module graph rooted at src/lib.rs."""
    module = importlib.import_module(f"pycodex.hooks.{module_name}")
    item = getattr(module, symbol)
    if callable(item):
        assert item.__module__ == module.__name__


@pytest.mark.parametrize("module_name", ["events"])
def test_hooks_marker_module_exists(module_name: str) -> None:
    """Rust source: codex-hooks/src/events/mod.rs."""
    importlib.import_module(f"pycodex.hooks.{module_name}")


def test_crate_root_reexports_rust_public_surface() -> None:
    root = importlib.import_module("pycodex.hooks")
    registry = importlib.import_module("pycodex.hooks.registry")
    types = importlib.import_module("pycodex.hooks.types")

    assert root.Hooks is registry.Hooks
    assert root.Hook is types.Hook
