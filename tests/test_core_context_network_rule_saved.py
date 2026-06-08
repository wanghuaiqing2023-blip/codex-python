import unittest

from pycodex.core.context import NetworkRuleSaved
from pycodex.protocol import (
    ContentItem,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    ResponseInputItem,
    ResponseItem,
)


class NetworkRuleSavedTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/network_rule_saved.rs

    def test_network_rule_saved_allow_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = NetworkRuleSaved.new(
            NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW)
        )
        expected_body = "Allowed network rule saved in execpolicy (allowlist): api.example.com"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_body)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(expected_body),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(expected_body),)),
        )

    def test_network_rule_saved_deny_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = NetworkRuleSaved.new(
            NetworkPolicyAmendment("blocked.example.com", NetworkPolicyRuleAction.DENY)
        )
        expected_body = "Denied network rule saved in execpolicy (denylist): blocked.example.com"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_body)


if __name__ == "__main__":
    unittest.main()
