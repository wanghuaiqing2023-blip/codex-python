import unittest
from datetime import timedelta
from pathlib import Path

from pycodex.core import (
    CONTEXTUAL_USER_FRAGMENTS,
    ApprovedCommandPrefixSaved,
    AppsInstructions,
    AvailablePluginsInstructions,
    AvailableSkillsInstructions,
    CollaborationModeInstructions,
    EnvironmentContext,
    EnvironmentContextEnvironment,
    FragmentRegistrationProxy,
    GoalContext,
    GuardianFollowupReviewReminder,
    HookAdditionalContext,
    ImageGenerationInstructions,
    LegacyApplyPatchExecCommandWarning,
    ModelSwitchInstructions,
    NetworkRuleSaved,
    PersonalitySpecInstructions,
    PluginCapabilitySummary,
    PluginInstructions,
    RealtimeEndInstructions,
    RealtimeStartInstructions,
    RealtimeStartWithInstructions,
    SkillInstructions,
    SubagentNotification,
    TurnAborted,
    UserInstructions,
    UserShellCommand,
    is_contextual_user_fragment,
    is_standard_contextual_user_text,
    parse_visible_hook_prompt_message,
)
from pycodex.protocol import (
    AgentStatus,
    CollaborationMode,
    ContentItem,
    HookPromptFragment,
    ModeKind,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    ResponseInputItem,
    ResponseItem,
    Settings,
    build_hook_prompt_message,
)


class CoreContextualUserMessageTests(unittest.TestCase):
    # Rust source:
    # - codex/codex-rs/core/src/context/contextual_user_message.rs
    # - codex/codex-rs/core/src/context/contextual_user_message_tests.rs

    def test_detects_standard_contextual_user_fragments(self):
        environment = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/repo"), "bash"),))
        instructions = UserInstructions("/repo", "prefer stdlib")
        skill = SkillInstructions("python-port", "/skills/python-port/SKILL.md", "mirror upstream behavior")

        self.assertTrue(is_standard_contextual_user_text(environment.render()))
        self.assertTrue(is_standard_contextual_user_text(instructions.render()))
        self.assertTrue(is_standard_contextual_user_text(skill.render()))
        self.assertFalse(is_standard_contextual_user_text("regular user text"))

    def test_detects_raw_environment_and_agents_instruction_fragments(self):
        # Rust tests: detects_environment_context_fragment and detects_agents_instructions_fragment
        self.assertTrue(
            is_contextual_user_fragment(
                ContentItem.input_text("<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>")
            )
        )
        self.assertTrue(
            is_contextual_user_fragment(
                ContentItem.input_text(
                    "# AGENTS.md instructions for /tmp\n\n<INSTRUCTIONS>\nbody\n</INSTRUCTIONS>"
                )
            )
        )

    def test_standard_contextual_user_fragments_use_registration_proxies(self):
        self.assertTrue(CONTEXTUAL_USER_FRAGMENTS)
        self.assertTrue(all(isinstance(fragment, FragmentRegistrationProxy) for fragment in CONTEXTUAL_USER_FRAGMENTS))
        self.assertTrue(
            any(
                fragment.matches_text("<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>")
                for fragment in CONTEXTUAL_USER_FRAGMENTS
            )
        )
        self.assertFalse(any(fragment.matches_text("regular user text") for fragment in CONTEXTUAL_USER_FRAGMENTS))

    def test_detects_subagent_notification_case_insensitively(self):
        notification = SubagentNotification.new("agent-a", AgentStatus.running())

        self.assertEqual(
            notification.render(),
            '<subagent_notification>\n{"agent_path":"agent-a","status":"running"}\n</subagent_notification>',
        )
        self.assertTrue(is_standard_contextual_user_text(notification.render().upper()))
        self.assertTrue(SubagentNotification.matches_text("<SUBAGENT_NOTIFICATION>{}</subagent_notification>"))
        self.assertTrue(
            is_contextual_user_fragment(ContentItem.input_text("<SUBAGENT_NOTIFICATION>{}</subagent_notification>"))
        )

    def test_detects_goal_context_and_keeps_response_conversions(self):
        goal = GoalContext("keep porting upstream Codex")
        rendered = "<goal_context>\nkeep porting upstream Codex\n</goal_context>"

        self.assertEqual(goal.render(), rendered)
        self.assertTrue(is_contextual_user_fragment(ContentItem.input_text(rendered)))
        self.assertEqual(goal.into_response_item(), ResponseItem.message("user", (ContentItem.input_text(rendered),)))
        self.assertEqual(
            goal.into_response_input_item(),
            ResponseInputItem.message("user", (ContentItem.input_text(rendered),)),
        )

    def test_ignores_regular_text_and_non_text_content(self):
        self.assertFalse(is_contextual_user_fragment(ContentItem.input_text("hello")))
        self.assertFalse(is_contextual_user_fragment(ContentItem.input_image("https://example.com/image.png")))
        self.assertIsNone(parse_visible_hook_prompt_message("visible", (ContentItem.input_text("hello"),)))

    def test_visible_hook_prompt_parse_skips_standard_context(self):
        fragment = HookPromptFragment.from_single_hook("hello <world> & friends", "run-1")
        hook_message = build_hook_prompt_message((fragment,))
        self.assertIsNotNone(hook_message)

        environment = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/repo"), "bash"),))
        content = (ContentItem.input_text(environment.render()),) + hook_message.content

        parsed = parse_visible_hook_prompt_message("visible-id", content)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.id, "visible-id")
        self.assertEqual(parsed.fragments, (fragment,))

    def test_visible_hook_prompt_parse_returns_none_for_only_standard_context(self):
        # Rust source: parse_visible_hook_prompt_message returns None when no hook fragments are present.
        environment = EnvironmentContext.new((EnvironmentContextEnvironment("local", Path("/repo"), "bash"),))
        instructions = UserInstructions("/repo", "prefer stdlib")

        self.assertIsNone(
            parse_visible_hook_prompt_message(
                "visible-id",
                (
                    ContentItem.input_text(environment.render()),
                    ContentItem.input_text(instructions.render()),
                ),
            )
        )

    def test_detects_hook_prompt_fragment_and_roundtrips_escaping(self):
        # Rust test: detects_hook_prompt_fragment_and_roundtrips_escaping
        fragment = HookPromptFragment.from_single_hook('Retry with "waves" & <tides>', "hook-run-1")
        hook_message = build_hook_prompt_message((fragment,))
        self.assertIsNotNone(hook_message)
        assert hook_message is not None
        (content_item,) = hook_message.content

        self.assertTrue(is_contextual_user_fragment(content_item))

        parsed = parse_visible_hook_prompt_message(None, hook_message.content)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.fragments, (fragment,))
        self.assertNotIn('&quot;waves&quot; & <tides>', content_item.text or "")

    def test_visible_hook_prompt_parse_rejects_mixed_regular_content(self):
        fragment = HookPromptFragment.from_single_hook("hello", "run-1")
        hook_message = build_hook_prompt_message((fragment,))
        self.assertIsNotNone(hook_message)

        content = hook_message.content + (ContentItem.input_text("regular user text"),)

        self.assertIsNone(parse_visible_hook_prompt_message("visible-id", content))
        self.assertIsNone(
            parse_visible_hook_prompt_message(
                "visible-id",
                hook_message.content + (ContentItem.input_image("https://example.com/image.png"),),
            )
        )
        self.assertIsNone(
            parse_visible_hook_prompt_message(
                "visible-id",
                hook_message.content + (ContentItem.output_text("assistant-shaped text"),),
            )
        )

    def test_shell_turn_aborted_and_legacy_warning_fragments(self):
        shell = UserShellCommand.new("python -m unittest", 0, timedelta(milliseconds=25), "OK\n")
        self.assertEqual(
            shell.render(),
            "<user_shell_command>\n"
            "<command>\npython -m unittest\n</command>\n<result>\n"
            "Exit code: 0\nDuration: 0.0250 seconds\nOutput:\nOK\n\n</result>\n"
            "</user_shell_command>",
        )
        self.assertTrue(is_standard_contextual_user_text(shell.render()))

        turn_aborted = TurnAborted(TurnAborted.INTERRUPTED_GUIDANCE)
        self.assertTrue(is_standard_contextual_user_text(turn_aborted.render()))

        self.assertTrue(
            LegacyApplyPatchExecCommandWarning.matches_text(
                "Warning: apply_patch was requested via exec_command. Use the apply_patch tool instead of exec_command."
            )
        )

    def test_developer_context_fragments_without_markers(self):
        approved = ApprovedCommandPrefixSaved.new('- ["git", "pull"]')
        self.assertEqual(approved.render(), 'Approved command prefix saved:\n- ["git", "pull"]')
        self.assertEqual(approved.role(), "developer")
        self.assertFalse(is_standard_contextual_user_text(approved.render()))
        self.assertEqual(
            approved.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(approved.render()),)),
        )

        allow = NetworkRuleSaved.new(NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW))
        deny = NetworkRuleSaved(NetworkPolicyRuleAction.DENY, "blocked.example.com")
        self.assertEqual(allow.render(), "Allowed network rule saved in execpolicy (allowlist): api.example.com")
        self.assertEqual(deny.render(), "Denied network rule saved in execpolicy (denylist): blocked.example.com")

        reminder = GuardianFollowupReviewReminder()
        self.assertIn("Use prior reviews as context, not binding precedent.", reminder.render())
        self.assertIn('set outcome to "allow"', reminder.render())
        self.assertEqual(reminder.role(), "developer")

        additional = HookAdditionalContext.new("hook supplied this context")
        self.assertEqual(additional.render(), "hook supplied this context")
        self.assertEqual(
            additional.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text("hook supplied this context"),)),
        )

    def test_instruction_fragments_for_plugins_skills_apps_and_modes(self):
        self.assertIsNone(AppsInstructions.from_connectors(({"is_accessible": True, "is_enabled": False},)))
        apps = AppsInstructions.from_connectors(({"is_accessible": True, "is_enabled": True},))
        self.assertIsNotNone(apps)
        self.assertIn("`codex_apps` MCP", apps.render())
        self.assertTrue(apps.render().startswith("<apps_instructions>\n## Apps (Connectors)"))

        plugins = AvailablePluginsInstructions.from_plugins(
            (PluginCapabilitySummary("imagegen", "Imagegen", "Generate images"), {"display_name": "Browser"},)
        )
        self.assertIsNotNone(plugins)
        self.assertIn("- `Imagegen`: Generate images", plugins.render())
        self.assertIn("- `Browser`", plugins.render())
        self.assertIn("### How to use plugins", plugins.render())

        skills = AvailableSkillsInstructions(
            ("- `$system`: C:/skills",),
            ("- imagegen: Generate images. (file: C:/skills/imagegen/SKILL.md)",),
        )
        self.assertIn("### Skill roots", skills.render())
        self.assertIn("after expanding the matching alias", skills.render())

        collaboration = CollaborationModeInstructions.from_collaboration_mode(
            CollaborationMode(ModeKind.DEFAULT, Settings("gpt-5", developer_instructions="stay focused"))
        )
        self.assertIsNotNone(collaboration)
        self.assertEqual(collaboration.render(), "<collaboration_mode>stay focused</collaboration_mode>")
        self.assertIsNone(
            CollaborationModeInstructions.from_collaboration_mode(
                CollaborationMode(ModeKind.DEFAULT, Settings("gpt-5", developer_instructions=""))
            )
        )

    def test_realtime_model_personality_plugin_and_image_fragments(self):
        image = ImageGenerationInstructions.new("C:/tmp/images", "image.png")
        self.assertEqual(
            image.render(),
            "Generated images are saved to C:/tmp/images as image.png by default.\n"
            "If you need to use a generated image at another path, copy it and leave the original in place unless the user explicitly asks you to delete it.",
        )

        model = ModelSwitchInstructions.new("Prefer terse output.")
        self.assertEqual(
            model.render(),
            "<model_switch>\nThe user was previously using a different model. Please continue the conversation according to the following instructions:\n\nPrefer terse output.\n</model_switch>",
        )

        personality = PersonalitySpecInstructions.new("Be direct.")
        self.assertEqual(
            personality.render(),
            "<personality_spec> The user has requested a new communication style. Future messages should adhere to the following personality: \nBe direct. </personality_spec>",
        )

        self.assertEqual(PluginInstructions.new("plugin says hello").render(), "plugin says hello")
        self.assertIn("Realtime conversation started.", RealtimeStartInstructions().render())
        self.assertIn("Reason: microphone closed", RealtimeEndInstructions.new("microphone closed").render())
        self.assertEqual(
            RealtimeStartWithInstructions.new("listen carefully").render(),
            "<realtime_conversation>\nlisten carefully\n</realtime_conversation>",
        )


if __name__ == "__main__":
    unittest.main()
