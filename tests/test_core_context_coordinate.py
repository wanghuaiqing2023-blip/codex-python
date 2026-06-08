import unittest

from pycodex.core import context
from pycodex.protocol import ContentItem


class CoreContextCoordinateTests(unittest.TestCase):
    def test_context_root_reexports_rust_mod_surface(self):
        # Rust source: codex-rs/core/src/context/mod.rs
        # Rust contract: root module re-exports the fragment traits, fragment
        # registrations, fragment types, and visible-hook parsing helpers.
        expected = (
            "ApprovedCommandPrefixSaved",
            "AppsInstructions",
            "AvailablePluginsInstructions",
            "AvailableSkillsInstructions",
            "CollaborationModeInstructions",
            "ContextualUserFragment",
            "FragmentRegistration",
            "FragmentRegistrationProxy",
            "AdditionalContextDeveloperFragment",
            "AdditionalContextUserFragment",
            "EnvironmentContext",
            "GoalContext",
            "GuardianFollowupReviewReminder",
            "HookAdditionalContext",
            "ImageGenerationInstructions",
            "LegacyApplyPatchExecCommandWarning",
            "LegacyModelMismatchWarning",
            "LegacyUnifiedExecProcessLimitWarning",
            "ModelSwitchInstructions",
            "NetworkRuleSaved",
            "PermissionsInstructions",
            "PersonalitySpecInstructions",
            "PluginInstructions",
            "RealtimeEndInstructions",
            "RealtimeStartInstructions",
            "RealtimeStartWithInstructions",
            "SkillInstructions",
            "SubagentNotification",
            "TurnAborted",
            "UserInstructions",
            "UserShellCommand",
            "is_contextual_user_fragment",
            "parse_visible_hook_prompt_message",
        )
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(hasattr(context, name), name)
                self.assertIn(name, context.__all__)

    def test_context_root_fragment_smoke(self):
        fragment = context.TurnAborted.new(context.TurnAborted.INTERRUPTED_GUIDANCE)
        rendered = fragment.render()

        self.assertTrue(context.is_contextual_user_fragment(ContentItem.input_text(rendered)))
        self.assertIsNone(context.parse_visible_hook_prompt_message("visible-id", (ContentItem.input_text(rendered),)))


if __name__ == "__main__":
    unittest.main()
