"""Rust-derived checks for codex-core re-export-only modules."""

from __future__ import annotations

import unittest


class CoreReexportModuleOwnershipTests(unittest.TestCase):
    def test_mention_syntax_reexports_the_utils_plugins_symbols(self) -> None:
        from pycodex.core import mention_syntax as core_module
        from pycodex.utils.plugins import mention_syntax as source_module

        self.assertIs(
            core_module.PLUGIN_TEXT_MENTION_SIGIL,
            source_module.PLUGIN_TEXT_MENTION_SIGIL,
        )
        self.assertIs(
            core_module.TOOL_MENTION_SIGIL,
            source_module.TOOL_MENTION_SIGIL,
        )

    def test_original_image_detail_reexports_the_codex_tools_functions(self) -> None:
        from pycodex.core import original_image_detail as core_module
        from pycodex.tools import original_image_detail as source_module

        self.assertIs(
            core_module.can_request_original_image_detail,
            source_module.can_request_original_image_detail,
        )
        self.assertIs(
            core_module.sanitize_original_image_detail,
            source_module.sanitize_original_image_detail,
        )


if __name__ == "__main__":
    unittest.main()
