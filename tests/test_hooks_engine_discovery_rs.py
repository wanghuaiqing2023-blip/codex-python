"""Rust-derived tests for ``codex-hooks/src/engine/discovery.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/engine/discovery.rs``

Rust tests mirrored:
- ``user_prompt_submit_ignores_invalid_matcher_during_discovery``
- ``pre_tool_use_keeps_valid_matcher_during_discovery``
- ``bypass_hook_trust_allows_enabled_untrusted_handlers``
- ``bypass_hook_trust_respects_disabled_handlers``
- ``pre_tool_use_treats_star_matcher_as_match_all``
- ``post_tool_use_keeps_valid_matcher_during_discovery``
- ``toml_hook_discovery_ignores_malformed_state_entries``
- ``pre_tool_use_resolves_windows_command_override_during_discovery``
"""

from __future__ import annotations

import os
from pathlib import Path

import pycodex.hooks as hooks_mod
from pycodex.config import ConfigLayerEntry
from pycodex.config import ConfigLayerSource
from pycodex.config import HookHandlerConfig
from pycodex.config import HookStateToml
from pycodex.config import MatcherGroup
from pycodex.protocol import HookEventName
from pycodex.protocol import HookSource
from pycodex.protocol import HookTrustStatus


def _source_path() -> Path:
    return Path("C:/tmp/hooks.json") if os.name == "nt" else Path("/tmp/hooks.json")


def _command_group(matcher: str | None) -> MatcherGroup:
    return MatcherGroup(
        matcher=matcher,
        hooks=(HookHandlerConfig.command_handler("echo hello"),),
    )


def _managed_source(
    hook_states: dict[str, HookStateToml] | None = None,
) -> hooks_mod._HookHandlerSource:
    path = _source_path()
    return hooks_mod._HookHandlerSource(
        path=path,
        key_source=str(path),
        source=HookSource.SYSTEM,
        is_managed=True,
        bypass_hook_trust=False,
        hook_states=hook_states or {},
    )


def _unmanaged_source(
    hook_states: dict[str, HookStateToml] | None = None,
    *,
    bypass_hook_trust: bool,
) -> hooks_mod._HookHandlerSource:
    path = _source_path()
    return hooks_mod._HookHandlerSource(
        path=path,
        key_source=str(path),
        source=HookSource.USER,
        is_managed=False,
        bypass_hook_trust=bypass_hook_trust,
        hook_states=hook_states or {},
    )


def _append(
    source: hooks_mod._HookHandlerSource,
    event_name: HookEventName,
    groups: list[MatcherGroup],
) -> tuple[list[hooks_mod.ConfiguredHandler], list[hooks_mod.HookListEntry], list[str]]:
    handlers: list[hooks_mod.ConfiguredHandler] = []
    entries: list[hooks_mod.HookListEntry] = []
    warnings: list[str] = []
    hooks_mod._append_matcher_groups(
        handlers,
        entries,
        warnings,
        [0],
        source,
        event_name,
        groups,
    )
    return handlers, entries, warnings


def test_user_prompt_submit_ignores_invalid_matcher_during_discovery() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::user_prompt_submit_ignores_invalid_matcher_during_discovery.
    # Contract: UserPromptSubmit does not use matchers, so an invalid matcher
    # string is ignored and the command handler is still discovered.
    handlers, _entries, warnings = _append(
        _managed_source(),
        HookEventName.USER_PROMPT_SUBMIT,
        [_command_group("[")],
    )

    assert warnings == []
    assert len(handlers) == 1
    assert handlers[0].event_name == HookEventName.USER_PROMPT_SUBMIT
    assert handlers[0].matcher is None
    assert handlers[0].command == "echo hello"
    assert handlers[0].timeout_sec == 600


def test_pre_tool_use_keeps_valid_matcher_during_discovery() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::pre_tool_use_keeps_valid_matcher_during_discovery.
    # Contract: PreToolUse validates and keeps a valid matcher pattern.
    handlers, _entries, warnings = _append(
        _managed_source(),
        HookEventName.PRE_TOOL_USE,
        [_command_group("^Bash$")],
    )

    assert warnings == []
    assert len(handlers) == 1
    assert handlers[0].matcher == "^Bash$"


def test_bypass_hook_trust_allows_enabled_untrusted_handlers() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::bypass_hook_trust_allows_enabled_untrusted_handlers.
    # Contract: bypass_hook_trust admits enabled untrusted user hooks into the
    # runnable handler list while the list entry still records Untrusted.
    handlers, entries, warnings = _append(
        _unmanaged_source(bypass_hook_trust=True),
        HookEventName.PRE_TOOL_USE,
        [_command_group("Bash")],
    )

    assert warnings == []
    assert len(handlers) == 1
    assert len(entries) == 1
    assert entries[0].trust_status == HookTrustStatus.UNTRUSTED
    assert entries[0].enabled is True


def test_bypass_hook_trust_respects_disabled_handlers() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::bypass_hook_trust_respects_disabled_handlers.
    # Contract: bypass_hook_trust does not override persisted enabled=false.
    path = _source_path()
    key = f"{path}:pre_tool_use:0:0"
    handlers, entries, warnings = _append(
        _unmanaged_source(
            {key: HookStateToml(enabled=False)},
            bypass_hook_trust=True,
        ),
        HookEventName.PRE_TOOL_USE,
        [_command_group("Bash")],
    )

    assert warnings == []
    assert handlers == []
    assert len(entries) == 1
    assert entries[0].trust_status == HookTrustStatus.UNTRUSTED
    assert entries[0].enabled is False


def test_pre_tool_use_treats_star_matcher_as_match_all() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::pre_tool_use_treats_star_matcher_as_match_all.
    # Contract: ``*`` is accepted as a match-all matcher during discovery.
    handlers, _entries, warnings = _append(
        _managed_source(),
        HookEventName.PRE_TOOL_USE,
        [_command_group("*")],
    )

    assert warnings == []
    assert len(handlers) == 1
    assert handlers[0].matcher == "*"


def test_post_tool_use_keeps_valid_matcher_during_discovery() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::post_tool_use_keeps_valid_matcher_during_discovery.
    # Contract: PostToolUse keeps valid tool-name alternation matchers.
    handlers, _entries, warnings = _append(
        _managed_source(),
        HookEventName.POST_TOOL_USE,
        [_command_group("Edit|Write")],
    )

    assert warnings == []
    assert len(handlers) == 1
    assert handlers[0].event_name == HookEventName.POST_TOOL_USE
    assert handlers[0].matcher == "Edit|Write"


def test_toml_hook_discovery_ignores_malformed_state_entries() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::toml_hook_discovery_ignores_malformed_state_entries.
    # Contract: malformed hooks.state entries do not prevent valid hook event
    # declarations in the same TOML layer from loading.
    config_path = Path("C:/tmp/config.toml") if os.name == "nt" else Path("/tmp/config.toml")
    layer = ConfigLayerEntry.new(
        ConfigLayerSource.user(config_path),
        {
            "hooks": {
                "state": {
                    "some_key": {
                        "enabled": "not a bool",
                    }
                },
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "echo hello",
                            }
                        ]
                    }
                ],
            }
        },
    )
    warnings: list[str] = []

    loaded = hooks_mod._load_toml_hooks_from_layer(layer, warnings)

    assert warnings == []
    assert loaded is not None
    _source, hooks = loaded
    assert len(hooks.session_start) == 1
    assert hooks.session_start[0].hooks[0] == HookHandlerConfig.command_handler("echo hello")


def test_pre_tool_use_resolves_windows_command_override_during_discovery() -> None:
    # Rust crate/module/test: codex-hooks/src/engine/discovery.rs
    # tests::pre_tool_use_resolves_windows_command_override_during_discovery.
    # Contract: commandWindows replaces command only on Windows.
    handlers, _entries, warnings = _append(
        _managed_source(),
        HookEventName.PRE_TOOL_USE,
        [
            MatcherGroup(
                matcher="^Bash$",
                hooks=(
                    HookHandlerConfig.command_handler(
                        "echo unix",
                        command_windows="echo windows",
                    ),
                ),
            )
        ],
    )

    assert warnings == []
    assert len(handlers) == 1
    assert handlers[0].command == ("echo windows" if os.name == "nt" else "echo unix")

