import unittest

from pycodex.core.context import (
    ApprovedCommandPrefixSaved,
    NetworkRuleSaved,
    is_standard_contextual_user_text,
)
from pycodex.protocol import (
    ContentItem,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    ResponseInputItem,
    ResponseItem,
)


class CoreContextSavedFragmentsTests(unittest.TestCase):
    # Rust source contracts:
    # - codex/codex-rs/core/src/context/approved_command_prefix_saved.rs
    # - codex/codex-rs/core/src/context/network_rule_saved.rs
    # - codex/codex-rs/core/src/context/fragment.rs

    def test_approved_command_prefix_saved_is_unmarked_developer_context(self):
        fragment = ApprovedCommandPrefixSaved.new('- ["git", "pull"]')
        rendered = 'Approved command prefix saved:\n- ["git", "pull"]'

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), rendered)
        self.assertEqual(fragment.render(), rendered)
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(rendered),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(rendered),)),
        )

    def test_network_rule_saved_formats_allow_and_deny_execpolicy_messages(self):
        allow = NetworkRuleSaved.new(
            NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW)
        )
        deny = NetworkRuleSaved.new(
            NetworkPolicyAmendment("blocked.example.com", NetworkPolicyRuleAction.DENY)
        )

        self.assertEqual(allow.role(), "developer")
        self.assertEqual(allow.markers(), ("", ""))
        self.assertEqual(allow.type_markers(), ("", ""))
        self.assertEqual(
            allow.render(),
            "Allowed network rule saved in execpolicy (allowlist): api.example.com",
        )
        self.assertEqual(
            deny.render(),
            "Denied network rule saved in execpolicy (denylist): blocked.example.com",
        )
        self.assertFalse(is_standard_contextual_user_text(allow.render()))
        self.assertFalse(is_standard_contextual_user_text(deny.render()))


if __name__ == "__main__":
    unittest.main()
