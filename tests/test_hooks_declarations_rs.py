"""Rust-derived tests for ``codex-hooks/src/declarations.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/declarations.rs``

Rust test mirrored:
- ``lists_declared_plugin_handlers_with_persisted_hook_keys``
"""

from __future__ import annotations

import unittest

from pycodex.config.hook_config import HookEventsToml
from pycodex.config.hook_config import HookHandlerConfig
from pycodex.config.hook_config import MatcherGroup
from pycodex.hooks import PluginHookDeclaration
from pycodex.hooks import plugin_hook_declarations
from pycodex.protocol import HookEventName


class _PluginId:
    def __init__(self, value: str) -> None:
        self.value = value

    def as_key(self) -> str:
        return self.value


class HooksDeclarationsRsTests(unittest.TestCase):
    def test_lists_declared_plugin_handlers_with_persisted_hook_keys(self) -> None:
        # Rust crate/module/test: codex-hooks/src/declarations.rs
        # tests::lists_declared_plugin_handlers_with_persisted_hook_keys.
        # Contract: declarations use plugin_id.as_key() plus source-relative
        # path as key source, preserve HookEventsToml event ordering, and emit
        # one persisted hook key per matcher-group handler.
        source = {
            "plugin_id": _PluginId("demo@test"),
            "source_relative_path": "hooks/hooks.json",
            "hooks": HookEventsToml(
                pre_tool_use=(
                    MatcherGroup(
                        matcher=None,
                        hooks=(
                            HookHandlerConfig.prompt(),
                            HookHandlerConfig.command_handler("echo hi"),
                        ),
                    ),
                ),
                session_start=(
                    MatcherGroup(
                        matcher=None,
                        hooks=(HookHandlerConfig.agent(),),
                    ),
                ),
            ),
        }

        self.assertEqual(
            plugin_hook_declarations([source]),
            [
                PluginHookDeclaration(
                    "demo@test:hooks/hooks.json:pre_tool_use:0:0",
                    HookEventName.PRE_TOOL_USE,
                ),
                PluginHookDeclaration(
                    "demo@test:hooks/hooks.json:pre_tool_use:0:1",
                    HookEventName.PRE_TOOL_USE,
                ),
                PluginHookDeclaration(
                    "demo@test:hooks/hooks.json:session_start:0:0",
                    HookEventName.SESSION_START,
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
