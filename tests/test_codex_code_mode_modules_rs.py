"""Module contracts derived from ``codex-rs/code-mode/src``."""

from __future__ import annotations

import importlib
import threading

import pytest

from pycodex.protocol import ToolName


@pytest.mark.parametrize(
    "module_name",
    (
        "pycodex.code_mode.description",
        "pycodex.code_mode.response",
        "pycodex.code_mode.runtime",
        "pycodex.code_mode.runtime.callbacks",
        "pycodex.code_mode.runtime.globals",
        "pycodex.code_mode.runtime.module_loader",
        "pycodex.code_mode.runtime.timers",
        "pycodex.code_mode.runtime.value",
        "pycodex.code_mode.service",
    ),
)
def test_rust_code_mode_module_has_python_owner(module_name: str) -> None:
    importlib.import_module(module_name)


def test_description_parses_pragma_and_renders_nested_tool() -> None:
    # Rust: code-mode/src/description.rs
    from pycodex.code_mode.description import (
        CodeModeToolDefinition,
        CodeModeToolKind,
        build_exec_tool_description,
        parse_exec_source,
    )

    parsed = parse_exec_source(
        '// @exec: {"yield_time_ms": 17, "max_output_tokens": 19}\ntext("ok")'
    )
    assert parsed.code == 'text("ok")'
    assert parsed.yield_time_ms == 17
    assert parsed.max_output_tokens == 19

    definition = CodeModeToolDefinition(
        name="lookup",
        tool_name=ToolName.plain("lookup"),
        description="Look up a record.",
        kind=CodeModeToolKind.FUNCTION,
        input_schema={"type": "object"},
    )
    rendered = build_exec_tool_description(
        (definition,),
        code_mode_only=True,
        deferred_tools_available=False,
    )
    assert "lookup" in rendered
    assert "Look up a record." in rendered


def test_response_defaults_image_detail() -> None:
    # Rust: code-mode/src/response.rs
    from pycodex.code_mode.response import (
        DEFAULT_IMAGE_DETAIL,
        FunctionCallOutputContentItem,
    )

    item = FunctionCallOutputContentItem.input_image(
        "data:image/png;base64,AAA",
        DEFAULT_IMAGE_DETAIL,
    )
    assert item.detail is DEFAULT_IMAGE_DETAIL


def test_runtime_models_and_command_selection() -> None:
    # Rust: code-mode/src/runtime/mod.rs
    from pycodex.code_mode.runtime import (
        PendingRuntimeMode,
        RuntimeCommand,
        RuntimeControlCommand,
        next_runtime_command,
    )

    result = next_runtime_command((RuntimeCommand.terminate(),))
    assert result.command is not None
    assert result.command.type == "terminate"
    assert PendingRuntimeMode.PAUSE_UNTIL_RESUMED.value == "pause_until_resumed"
    assert RuntimeControlCommand.RESUME.value == "resume"


def test_runtime_callback_and_globals_projection() -> None:
    # Rust: runtime/callbacks.rs and runtime/globals.rs
    from pycodex.code_mode.description import CodeModeToolDefinition, CodeModeToolKind
    from pycodex.code_mode.runtime.callbacks import text_callback
    from pycodex.code_mode.runtime.globals import install_globals

    event = text_callback({"ok": True})
    assert event.type == "content_item"
    definition = CodeModeToolDefinition(
        name="lookup",
        tool_name=ToolName.plain("lookup"),
        description="Lookup",
        kind=CodeModeToolKind.FUNCTION,
        input_schema={"type": "object"},
    )
    projection = install_globals((definition,))
    assert projection["tools"] == {"lookup": "0"}


def test_runtime_module_loader_timer_and_value_helpers() -> None:
    # Rust: runtime/module_loader.rs, runtime/timers.rs, runtime/value.rs
    from pycodex.code_mode.runtime.module_loader import (
        unsupported_dynamic_import_error,
        unsupported_static_import_error,
    )
    from pycodex.code_mode.runtime.timers import normalize_timeout_delay_ms
    from pycodex.code_mode.runtime.value import serialize_output_text

    assert unsupported_static_import_error("pkg") == "Unsupported import in exec: pkg"
    assert unsupported_dynamic_import_error() == "unsupported import in exec"
    assert normalize_timeout_delay_ms(12.8) == 12
    assert serialize_output_text({"ok": True}) == '{"ok":true}'


def test_runtime_timer_schedule_and_clear_lifecycle() -> None:
    # Rust: code-mode/src/runtime/timers.rs
    from pycodex.code_mode.runtime.timers import RuntimeTimerScheduler
    from pycodex.code_mode.runtime.timers import clear_timeout, schedule_timeout

    scheduler = RuntimeTimerScheduler()
    fired = threading.Event()
    timeout_id = schedule_timeout(scheduler, fired.set, 5)
    assert fired.wait(1.0)
    assert not clear_timeout(scheduler, timeout_id)

    blocked = threading.Event()
    timeout_id = schedule_timeout(scheduler, blocked.set, 500)
    assert clear_timeout(scheduler, timeout_id)
    assert not blocked.wait(0.05)
    scheduler.close()


def test_service_executes_through_configured_host_boundary() -> None:
    # Rust: code-mode/src/service.rs
    from pycodex.code_mode.description import CodeModeToolDefinition, CodeModeToolKind
    from pycodex.code_mode.runtime import ExecuteRequest, RuntimeResponse
    from pycodex.code_mode.service import CodeModeService

    service = CodeModeService(
        execute_callback=lambda request: RuntimeResponse.result(
            cell_id=request.cell_id,
            content_items=(),
        )
    )
    response = service.execute(
        ExecuteRequest(
            cell_id="cell-1",
            tool_call_id="call-1",
            enabled_tools=(
                CodeModeToolDefinition(
                    name="lookup",
                    tool_name=ToolName.plain("lookup"),
                    description="Lookup",
                    kind=CodeModeToolKind.FUNCTION,
                ),
            ),
            source='text("ok")',
        )
    )
    assert response.type == "result"
    assert response.cell_id == "cell-1"
