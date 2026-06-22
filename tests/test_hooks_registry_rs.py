"""Rust-derived tests for ``codex-hooks/src/registry.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/registry.rs``

Rust contracts mirrored:
- ``HooksConfig`` default field values.
- ``Hooks::new`` legacy-notify registration and engine construction.
- ``Hooks::dispatch`` preserves order and stops after abort.
- ``list_hooks`` feature gate and discovery forwarding.
- ``command_from_argv`` empty-command behavior and argv preservation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timezone
from pathlib import PurePosixPath
from types import SimpleNamespace

import pycodex.hooks as hooks_mod
from pycodex.hooks import Hook
from pycodex.hooks import HookEvent
from pycodex.hooks import HookEventAfterAgent
from pycodex.hooks import HookListEntry
from pycodex.hooks import HookListOutcome
from pycodex.hooks import HookPayload
from pycodex.hooks import HookResult
from pycodex.hooks import Hooks
from pycodex.hooks import HooksConfig
from pycodex.hooks import command_from_argv
from pycodex.hooks import list_hooks
from pycodex.protocol import HookEventName
from pycodex.protocol import HookHandlerType
from pycodex.protocol import HookSource
from pycodex.protocol import HookTrustStatus


def _payload() -> HookPayload:
    return HookPayload(
        session_id="session-1",
        cwd=PurePosixPath("/tmp"),
        client=None,
        triggered_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        hook_event=HookEvent.AfterAgent(
            HookEventAfterAgent("thread-1", "turn-1", [], None)
        ),
    )


def test_hooks_config_default_matches_rust_fields() -> None:
    # Rust crate/module: codex-hooks/src/registry.rs
    # Contract: HooksConfig derives Default with disabled feature, no legacy
    # notify argv, no config layer stack, no plugin sources, no shell program,
    # and empty shell args.
    config = HooksConfig()

    assert config.legacy_notify_argv is None
    assert config.feature_enabled is False
    assert config.bypass_hook_trust is False
    assert config.config_layer_stack is None
    assert config.plugin_hook_sources == []
    assert config.plugin_hook_load_warnings == []
    assert config.shell_program is None
    assert config.shell_args == []


def test_hooks_new_filters_empty_legacy_notify_argv() -> None:
    # Rust crate/module: codex-hooks/src/registry.rs
    # Contract: Hooks::new registers legacy_notify only when argv is non-empty
    # and argv[0] is non-empty.
    assert Hooks.new(HooksConfig(legacy_notify_argv=None)).after_agent == []
    assert Hooks.new(HooksConfig(legacy_notify_argv=[])).after_agent == []
    assert Hooks.new(HooksConfig(legacy_notify_argv=[""])).after_agent == []

    hooks = Hooks.new(HooksConfig(legacy_notify_argv=["notify-bin", "--flag"]))

    assert len(hooks.after_agent) == 1
    assert hooks.after_agent[0].name == "legacy_notify"


def test_hooks_new_constructs_engine_with_rust_config_projection(monkeypatch) -> None:
    # Rust crate/module: codex-hooks/src/registry.rs
    # Contract: Hooks::new constructs ClaudeHooksEngine::new with feature flag,
    # trust bypass flag, config stack, plugin sources/warnings, and a
    # CommandShell using shell_program.unwrap_or_default() and shell_args.
    captured: dict[str, object] = {}

    class FakeEngine:
        @classmethod
        def new(
            cls,
            enabled: bool,
            bypass_hook_trust: bool,
            config_layer_stack: object,
            plugin_hook_sources: list[object],
            plugin_hook_load_warnings: list[str],
            shell: object,
        ) -> "FakeEngine":
            captured.update(
                enabled=enabled,
                bypass_hook_trust=bypass_hook_trust,
                config_layer_stack=config_layer_stack,
                plugin_hook_sources=plugin_hook_sources,
                plugin_hook_load_warnings=plugin_hook_load_warnings,
                shell=shell,
            )
            return cls()

        def warnings(self) -> list[str]:
            return []

    monkeypatch.setattr(hooks_mod, "_ClaudeHooksEngine", FakeEngine)
    config_stack = object()
    plugin_sources = [object()]

    Hooks.new(
        HooksConfig(
            feature_enabled=True,
            bypass_hook_trust=True,
            config_layer_stack=config_stack,
            plugin_hook_sources=plugin_sources,
            plugin_hook_load_warnings=["warn"],
            shell_program=None,
            shell_args=["-lc"],
        )
    )

    assert captured["enabled"] is True
    assert captured["bypass_hook_trust"] is True
    assert captured["config_layer_stack"] is config_stack
    assert captured["plugin_hook_sources"] == plugin_sources
    assert captured["plugin_hook_load_warnings"] == ["warn"]
    assert captured["shell"].program == ""
    assert captured["shell"].args == ["-lc"]


def test_startup_preview_and_run_methods_delegate_to_engine() -> None:
    # Rust crate/module: codex-hooks/src/registry.rs
    # Contract: registry methods forward startup warnings, preview calls, and
    # run calls to the engine.
    class FakeEngine:
        def warnings(self) -> list[str]:
            return ["warn"]

        def preview_pre_tool_use(self, request: object) -> list[str]:
            return [f"preview:{request}"]

        async def run_pre_tool_use(self, request: object) -> object:
            return SimpleNamespace(result=f"run:{request}")

    hooks = Hooks.new(HooksConfig())
    hooks.engine = FakeEngine()

    assert hooks.startup_warnings() == ["warn"]
    assert hooks.preview_pre_tool_use("request") == ["preview:request"]
    assert asyncio.run(hooks.run_pre_tool_use("request")).result == "run:request"


def test_dispatch_preserves_order_and_stops_after_abort() -> None:
    # Rust crate/module: codex-hooks/src/registry.rs
    # Contract: dispatch executes hooks in order, records the aborting hook, and
    # stops before later hooks.
    calls: list[str] = []

    async def first(_payload: HookPayload) -> HookResult:
        calls.append("first")
        return HookResult.Success()

    async def second(_payload: HookPayload) -> HookResult:
        calls.append("second")
        return HookResult.FailedAbort("stop")

    async def third(_payload: HookPayload) -> HookResult:
        calls.append("third")
        return HookResult.Success()

    hooks = Hooks.new(HooksConfig())
    hooks.after_agent = [
        Hook("first", first),
        Hook("second", second),
        Hook("third", third),
    ]

    responses = asyncio.run(hooks.dispatch(_payload()))

    assert calls == ["first", "second"]
    assert [response.hook_name for response in responses] == ["first", "second"]
    assert responses[-1].result.should_abort_operation()


def test_list_hooks_feature_gate_and_discovery_forwarding(monkeypatch) -> None:
    # Rust crate/module: codex-hooks/src/registry.rs
    # Contract: list_hooks returns default when feature_enabled is false; when
    # true, it forwards the discovery outcome.
    entry = HookListEntry(
        key="file:/tmp/hooks.json:pre_tool_use:0:0",
        event_name=HookEventName.PRE_TOOL_USE,
        handler_type=HookHandlerType.COMMAND,
        matcher="Bash",
        command="echo ok",
        timeout_sec=10,
        status_message=None,
        source_path=PurePosixPath("/tmp/hooks.json"),
        source=HookSource.PROJECT,
        plugin_id=None,
        display_order=0,
        enabled=True,
        is_managed=False,
        current_hash="hash",
        trust_status=HookTrustStatus.TRUSTED,
    )

    def fake_discover(config: HooksConfig) -> HookListOutcome:
        assert config.feature_enabled is True
        return HookListOutcome([entry], ["warning"])

    monkeypatch.setattr(hooks_mod, "_discover_handlers", fake_discover)

    assert list_hooks(HooksConfig(feature_enabled=False)) == HookListOutcome()
    assert list_hooks(HooksConfig(feature_enabled=True)) == HookListOutcome(
        [entry],
        ["warning"],
    )


def test_command_from_argv_empty_program_and_args() -> None:
    # Rust crate/module: codex-hooks/src/registry.rs
    # Contract: command_from_argv returns None for an empty argv or empty
    # program, otherwise preserves program and args.
    assert command_from_argv([]) is None
    assert command_from_argv([""]) is None
    assert command_from_argv(["notify-bin", "--flag"]) == ["notify-bin", "--flag"]
