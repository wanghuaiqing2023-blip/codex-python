"""Rust-derived tests for ``codex-hooks/src/engine/mod.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/engine/mod.rs``

These tests cover the engine facade contract from ``ClaudeHooksEngine``:
startup discovery/warnings, preview delegation, run delegation through the
dispatcher/event parsers, tool-use run-id decoration, and output spilling owned
by the engine wrapper.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pycodex import hooks as hooks_mod
from pycodex.hooks import CommandRunResult
from pycodex.hooks import ConfiguredHandler
from pycodex.hooks import HookOutputSpiller
from pycodex.hooks import PermissionRequestRequest
from pycodex.hooks import PermissionRequestDecisionKind
from pycodex.hooks import PostToolUseRequest
from pycodex.hooks import PreToolUseRequest
from pycodex.hooks import StopHookTarget
from pycodex.hooks import StopRequest
from pycodex.hooks import _ClaudeHooksEngine
from pycodex.hooks import _CommandShell
from pycodex.protocol import HookEventName
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler(
    event_name: HookEventName,
    matcher: str | None,
    display_order: int,
    command: str = "hook",
) -> ConfiguredHandler:
    return ConfiguredHandler(
        event_name=event_name,
        matcher=matcher,
        command=command,
        timeout_sec=5,
        status_message=None,
        source_path=Path("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=display_order,
    )


def _run(stdout: str, exit_code: int | None = 0, stderr: str = "") -> CommandRunResult:
    return CommandRunResult(
        started_at=1,
        completed_at=2,
        duration_ms=1,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )


def _pre_request(tmp_path: Path) -> PreToolUseRequest:
    return PreToolUseRequest(
        session_id="thread-1",
        turn_id="turn-1",
        subagent=None,
        cwd=tmp_path,
        transcript_path=None,
        model="gpt-test",
        permission_mode="default",
        tool_name="Bash",
        matcher_aliases=["shell"],
        run_id_suffix=None,
        tool_use_id="tool-call-1",
        tool_input={"command": "echo hi"},
    )


def test_new_disabled_skips_discovery_and_preserves_shell(monkeypatch) -> None:
    # Rust crate/module/test contract:
    # codex-hooks/src/engine/mod.rs::ClaudeHooksEngine::new disabled branch
    # returns an empty engine without discovery startup warnings.
    called = False

    def fake_discover(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("disabled engine should not discover handlers")

    monkeypatch.setattr(hooks_mod, "discover_handlers", fake_discover)

    engine = _ClaudeHooksEngine.new(
        enabled=False,
        bypass_hook_trust=False,
        config_layer_stack=None,
        plugin_hook_sources=[],
        plugin_hook_load_warnings=["plugin warning"],
        _shell=_CommandShell("pwsh", ["-NoLogo"]),
    )

    assert called is False
    assert engine.handlers == []
    assert engine.warnings() == []
    assert engine.shell.program == "pwsh"
    assert engine.shell.args == ["-NoLogo"]


def test_new_enabled_loads_schemas_and_exposes_discovery_warnings(monkeypatch) -> None:
    # Rust crate/module/test:
    # codex-hooks/src/engine/mod_tests.rs::plugin_hook_load_warnings_are_startup_warnings.
    schema_loaded = False

    def fake_schemas():
        nonlocal schema_loaded
        schema_loaded = True
        return object()

    def fake_discover(_stack, _sources, warnings, _bypass):
        return hooks_mod.DiscoveryResult(
            handlers=[],
            warnings=list(warnings),
        )

    monkeypatch.setattr(hooks_mod, "generated_hook_schemas", fake_schemas)
    monkeypatch.setattr(hooks_mod, "discover_handlers", fake_discover)

    engine = _ClaudeHooksEngine.new(
        enabled=True,
        bypass_hook_trust=False,
        config_layer_stack=None,
        plugin_hook_sources=[],
        plugin_hook_load_warnings=["failed plugin hook"],
        _shell=_CommandShell("", []),
    )

    assert schema_loaded is True
    assert engine.warnings() == ["failed plugin hook"]


def test_preview_pre_tool_use_delegates_selection_and_appends_tool_use_id(tmp_path) -> None:
    # Rust crate/module: codex-hooks/src/engine/mod.rs.
    # Rust source contract: preview_pre_tool_use delegates to the PreToolUse
    # event module, which selects matcher inputs and decorates run ids with the
    # tool_use_id.
    engine = _ClaudeHooksEngine(
        [
            _handler(HookEventName.PRE_TOOL_USE, "^Bash$", 0),
            _handler(HookEventName.PRE_TOOL_USE, "^Read$", 1),
            _handler(HookEventName.POST_TOOL_USE, "^Bash$", 2),
        ]
    )

    summaries = engine.preview_pre_tool_use(_pre_request(tmp_path))

    assert [summary.id for summary in summaries] == [
        f"pre-tool-use:0:{Path('/tmp/hooks.json')}:tool-call-1"
    ]
    assert summaries[0].status == HookRunStatus.RUNNING


def test_run_pre_tool_use_executes_handlers_decorates_completed_ids_and_spills_context(
    monkeypatch,
    tmp_path,
) -> None:
    # Rust crate/module: codex-hooks/src/engine/mod.rs.
    # Contract: run_pre_tool_use delegates execution/parsing to the event
    # module, appends tool_use_id to completed run ids, and spills additional
    # contexts through HookOutputSpiller.
    long_context = "remember this " * 5000
    seen_payloads: list[dict[str, object]] = []

    async def fake_run_command(_shell, _handler, input_json, cwd):
        assert cwd == tmp_path
        seen_payloads.append(json.loads(input_json))
        return _run(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "updatedInput": {"command": "echo rewritten"},
                        "additionalContext": long_context,
                    }
                }
            )
        )

    monkeypatch.setattr(hooks_mod, "run_command", fake_run_command)
    engine = _ClaudeHooksEngine(
        [_handler(HookEventName.PRE_TOOL_USE, "Bash|shell", 0)],
        output_spiller=HookOutputSpiller(tmp_path / "hook-outputs"),
    )

    outcome = asyncio.run(engine.run_pre_tool_use(_pre_request(tmp_path)))

    assert seen_payloads[0]["hook_event_name"] == "PreToolUse"
    assert outcome.updated_input == {"command": "echo rewritten"}
    assert outcome.hook_events[0].run.id.endswith(":tool-call-1")
    assert outcome.additional_contexts[0].endswith(".txt")
    assert "Full hook output saved to:" in outcome.additional_contexts[0]
    spilled_path = Path(outcome.additional_contexts[0].split("Full hook output saved to: ", 1)[1])
    assert spilled_path.read_text(encoding="utf-8") == long_context


def test_run_permission_request_decorates_suffix_and_resolves_deny(monkeypatch, tmp_path) -> None:
    # Rust crate/module: codex-hooks/src/engine/mod.rs.
    # Rust source contract: permission request engine run delegates to the
    # event module and preserves run-id suffix decoration from the request.
    async def fake_run_command(_shell, _handler, _input_json, _cwd):
        return _run(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "decision": {
                            "behavior": "deny",
                            "message": "no",
                        }
                    }
                }
            )
        )

    monkeypatch.setattr(hooks_mod, "run_command", fake_run_command)
    engine = _ClaudeHooksEngine([_handler(HookEventName.PERMISSION_REQUEST, "^Bash$", 0)])
    request = PermissionRequestRequest(
        session_id="thread-1",
        turn_id="turn-1",
        subagent=None,
        cwd=tmp_path,
        transcript_path=None,
        model="gpt-test",
        permission_mode="default",
        tool_name="Bash",
        matcher_aliases=[],
        run_id_suffix="approval-1",
        tool_input={"command": "rm -rf /"},
    )

    outcome = asyncio.run(engine.run_permission_request(request))

    assert outcome.hook_events[0].run.id.endswith(":approval-1")
    assert outcome.decision is not None
    assert outcome.decision.kind == PermissionRequestDecisionKind.DENY
    assert outcome.decision.message == "no"


def test_run_post_tool_use_spills_feedback_message(monkeypatch, tmp_path) -> None:
    # Rust crate/module: codex-hooks/src/engine/mod.rs.
    # Contract: run_post_tool_use spills both additional contexts and optional
    # feedback_message after the event module aggregates handler output.
    long_feedback = "feedback " * 5000

    async def fake_run_command(_shell, _handler, _input_json, _cwd):
        return _run(long_feedback, exit_code=2, stderr=long_feedback)

    monkeypatch.setattr(hooks_mod, "run_command", fake_run_command)
    engine = _ClaudeHooksEngine(
        [_handler(HookEventName.POST_TOOL_USE, "^Bash$", 0)],
        output_spiller=HookOutputSpiller(tmp_path / "hook-outputs"),
    )
    request = PostToolUseRequest(
        session_id="thread-1",
        turn_id="turn-1",
        subagent=None,
        cwd=tmp_path,
        transcript_path=None,
        model="gpt-test",
        permission_mode="default",
        tool_name="Bash",
        matcher_aliases=[],
        run_id_suffix=None,
        tool_use_id="tool-call-2",
        tool_input={"command": "echo hi"},
        tool_response={"output": "hi"},
    )

    outcome = asyncio.run(engine.run_post_tool_use(request))

    assert outcome.hook_events[0].run.id.endswith(":tool-call-2")
    assert outcome.feedback_message is not None
    assert "Full hook output saved to:" in outcome.feedback_message


def test_run_stop_spills_continuation_fragments(monkeypatch, tmp_path) -> None:
    # Rust crate/module: codex-hooks/src/engine/mod.rs.
    # Contract: run_stop delegates stop aggregation to the event module and
    # spills continuation fragments owned by the engine facade.
    long_reason = "continue please " * 5000

    async def fake_run_command(_shell, _handler, input_json, _cwd):
        assert json.loads(input_json)["hook_event_name"] == "Stop"
        return _run("", exit_code=2, stderr=long_reason)

    monkeypatch.setattr(hooks_mod, "run_command", fake_run_command)
    engine = _ClaudeHooksEngine(
        [_handler(HookEventName.STOP, None, 0)],
        output_spiller=HookOutputSpiller(tmp_path / "hook-outputs"),
    )
    request = StopRequest(
        session_id="thread-1",
        turn_id="turn-1",
        cwd=tmp_path,
        transcript_path=None,
        model="gpt-test",
        permission_mode="default",
        stop_hook_active=False,
        last_assistant_message="done",
        target=StopHookTarget.Stop(),
    )

    outcome = asyncio.run(engine.run_stop(request))

    assert outcome.should_block is True
    assert outcome.block_reason == long_reason.strip()
    assert len(outcome.continuation_fragments) == 1
    assert outcome.continuation_fragments[0].hook_run_id == outcome.hook_events[0].run.id
    assert "Full hook output saved to:" in outcome.continuation_fragments[0].text
