import unittest

from pycodex.core.state.additional_context import (
    AdditionalContextEntry,
    AdditionalContextKind,
    AdditionalContextStore,
)
from pycodex.protocol import ContentItem, ResponseInputItem


class AdditionalContextStoreTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/state/additional_context.rs

    def test_merge_emits_sorted_changed_fragments_for_untrusted_and_application_entries(
        self,
    ) -> None:
        store = AdditionalContextStore()

        items = store.merge(
            {
                "browser_info": AdditionalContextEntry(
                    "tab one",
                    AdditionalContextKind.UNTRUSTED,
                ),
                "app": AdditionalContextEntry(
                    "state one",
                    AdditionalContextKind.APPLICATION,
                ),
            }
        )

        self.assertEqual(
            items,
            (
                ResponseInputItem.message(
                    "developer",
                    (ContentItem.input_text("<app>state one</app>"),),
                ),
                ResponseInputItem.message(
                    "user",
                    (
                        ContentItem.input_text(
                            "<external_browser_info>tab one</external_browser_info>"
                        ),
                    ),
                ),
            ),
        )

    def test_merge_suppresses_unchanged_entries_and_emits_changed_entries(self) -> None:
        store = AdditionalContextStore()
        initial = {
            "browser_info": {"kind": "untrusted", "value": "tab one"},
            "app": {"kind": "application", "value": "state one"},
        }

        self.assertEqual(len(store.merge(initial)), 2)
        self.assertEqual(store.merge(initial), ())

        changed = store.merge(
            {
                "browser_info": {"kind": "untrusted", "value": "tab two"},
                "app": {"kind": "application", "value": "state one"},
            }
        )

        self.assertEqual(
            changed,
            (
                ResponseInputItem.message(
                    "user",
                    (
                        ContentItem.input_text(
                            "<external_browser_info>tab two</external_browser_info>"
                        ),
                    ),
                ),
            ),
        )

    def test_merge_replaces_store_without_emitting_removed_values(self) -> None:
        store = AdditionalContextStore(
            {
                "browser_info": {"kind": "untrusted", "value": "tab one"},
                "app": {"kind": "application", "value": "state one"},
            }
        )

        self.assertEqual(store.merge({}), ())
        self.assertEqual(
            store.merge({"app": {"kind": "application", "value": "state one"}}),
            (
                ResponseInputItem.message(
                    "developer",
                    (ContentItem.input_text("<app>state one</app>"),),
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
