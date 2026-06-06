import unittest

from pycodex.core.context import GuardianFollowupReviewReminder, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class GuardianFollowupReviewReminderTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/guardian_followup_review_reminder.rs

    def test_guardian_followup_review_reminder_empty_markers_do_not_match_arbitrary_text(
        self,
    ) -> None:
        text = GuardianFollowupReviewReminder().render()

        self.assertFalse(GuardianFollowupReviewReminder.matches_text(text))
        self.assertFalse(is_standard_contextual_user_text(text))

    def test_guardian_followup_review_reminder_matches_rust_contextual_fragment_contract(
        self,
    ) -> None:
        fragment = GuardianFollowupReviewReminder()
        expected_body = (
            "Use prior reviews as context, not binding precedent. "
            "Follow the Workspace Policy. "
            "If the user explicitly approves a previously rejected action after being informed of the "
            'concrete risks, set outcome to "allow" unless the policy explicitly disallows user '
            "overwrites in such cases."
        )

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


if __name__ == "__main__":
    unittest.main()
