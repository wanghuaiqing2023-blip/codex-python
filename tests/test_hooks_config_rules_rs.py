"""Rust-derived tests for ``codex-hooks/src/config_rules.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/config_rules.rs``

Rust tests mirrored:
- ``hook_states_from_stack_respects_layer_precedence``
- ``hook_states_from_stack_merges_fields_across_layers``
- ``hook_states_from_stack_ignores_malformed_hook_events``
- ``hook_states_from_stack_ignores_malformed_state_entries``
"""

from __future__ import annotations

from pathlib import Path

from pycodex.config import ConfigLayerEntry
from pycodex.config import ConfigLayerSource
from pycodex.config import ConfigLayerStack
from pycodex.config import HookStateToml
from pycodex.hooks import hook_states_from_stack


def _config_with_hook_state(key: str, state: HookStateToml) -> dict[str, object]:
    return {"hooks": {"state": {key: state.to_mapping()}}}


def _user_layer(config: dict[str, object]) -> ConfigLayerEntry:
    return ConfigLayerEntry.new(
        ConfigLayerSource.user(Path("/tmp/config.toml")),
        config,
    )


def _session_layer(config: dict[str, object]) -> ConfigLayerEntry:
    return ConfigLayerEntry.new(ConfigLayerSource.session_flags(), config)


def test_hook_states_from_stack_respects_layer_precedence() -> None:
    # Rust crate/module/test: codex-hooks/src/config_rules.rs
    # tests::hook_states_from_stack_respects_layer_precedence.
    # Contract: user and session flag layers are read lowest-to-highest, so
    # later session flags win field-by-field.
    key = "file:/tmp/hooks.json:pre_tool_use:0:0"
    stack = ConfigLayerStack.new(
        (
            _user_layer(_config_with_hook_state(key, HookStateToml(enabled=False))),
            _session_layer(_config_with_hook_state(key, HookStateToml(enabled=True))),
        )
    )

    assert hook_states_from_stack(stack) == {
        key: HookStateToml(enabled=True, trusted_hash=None)
    }


def test_hook_states_from_stack_merges_fields_across_layers() -> None:
    # Rust crate/module/test: codex-hooks/src/config_rules.rs
    # tests::hook_states_from_stack_merges_fields_across_layers.
    # Contract: a higher-precedence layer with one field does not erase a
    # lower-precedence field that it leaves as None.
    key = "file:/tmp/hooks.json:pre_tool_use:0:0"
    stack = ConfigLayerStack.new(
        (
            _user_layer(_config_with_hook_state(key, HookStateToml(enabled=False))),
            _session_layer(
                _config_with_hook_state(
                    key,
                    HookStateToml(trusted_hash="sha256:trusted"),
                )
            ),
        )
    )

    assert hook_states_from_stack(stack) == {
        key: HookStateToml(enabled=False, trusted_hash="sha256:trusted")
    }


def test_hook_states_from_stack_ignores_malformed_hook_events() -> None:
    # Rust crate/module/test: codex-hooks/src/config_rules.rs
    # tests::hook_states_from_stack_ignores_malformed_hook_events.
    # Contract: malformed hook event declarations do not prevent reading the
    # independent hooks.state table.
    key = "file:/tmp/hooks.json:pre_tool_use:0:0"
    stack = ConfigLayerStack.new(
        (
            _user_layer(
                {
                    "hooks": {
                        "state": {key: {"enabled": False}},
                        "SessionStart": "not a matcher list",
                    }
                }
            ),
        )
    )

    assert hook_states_from_stack(stack) == {
        key: HookStateToml(enabled=False, trusted_hash=None)
    }


def test_hook_states_from_stack_ignores_malformed_state_entries() -> None:
    # Rust crate/module/test: codex-hooks/src/config_rules.rs
    # tests::hook_states_from_stack_ignores_malformed_state_entries.
    # Contract: one invalid HookStateToml entry is skipped without dropping
    # valid sibling entries.
    key = "file:/tmp/hooks.json:pre_tool_use:0:0"
    stack = ConfigLayerStack.new(
        (
            _user_layer(
                {
                    "hooks": {
                        "state": {
                            key: {"enabled": False},
                            "malformed": {"enabled": "not a bool"},
                        }
                    }
                }
            ),
        )
    )

    assert hook_states_from_stack(stack) == {
        key: HookStateToml(enabled=False, trusted_hash=None)
    }


def test_hook_states_from_stack_ignores_project_and_system_layers() -> None:
    # Rust crate/module: codex-hooks/src/config_rules.rs
    # Contract: project/system/plugin-style config layers can discover hooks
    # but cannot write persisted user hook state.
    key = "file:/tmp/hooks.json:pre_tool_use:0:0"
    stack = ConfigLayerStack.new(
        (
            ConfigLayerEntry.new(
                ConfigLayerSource.system(Path("/tmp/system.toml")),
                _config_with_hook_state(key, HookStateToml(enabled=True)),
            ),
            _user_layer(_config_with_hook_state(key, HookStateToml(enabled=False))),
            ConfigLayerEntry.new(
                ConfigLayerSource.project(Path("/tmp/.codex")),
                _config_with_hook_state(key, HookStateToml(enabled=True)),
            ),
        )
    )

    assert hook_states_from_stack(stack) == {
        key: HookStateToml(enabled=False, trusted_hash=None)
    }
