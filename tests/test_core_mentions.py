from __future__ import annotations

import unittest

from pycodex.core import mentions
from pycodex.core.plugins import mentions as plugin_mentions
from pycodex.core.skills import build_skill_name_counts


class CoreMentionsFacadeTests(unittest.TestCase):
    def test_core_mentions_facade_reexports_rust_inline_module_helpers(self) -> None:
        # Rust source: codex-rs/core/src/lib.rs inline `pub(crate) mod mentions`.
        self.assertIs(
            mentions.build_connector_slug_counts,
            plugin_mentions.build_connector_slug_counts,
        )
        self.assertIs(
            mentions.collect_explicit_app_ids,
            plugin_mentions.collect_explicit_app_ids,
        )
        self.assertIs(
            mentions.collect_explicit_plugin_mentions,
            plugin_mentions.collect_explicit_plugin_mentions,
        )
        self.assertIs(
            mentions.collect_tool_mentions_from_messages,
            plugin_mentions.collect_tool_mentions_from_messages,
        )
        self.assertIs(mentions.build_skill_name_counts, build_skill_name_counts)


if __name__ == "__main__":
    unittest.main()
