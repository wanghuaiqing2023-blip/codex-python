import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core import (
    build_collaboration_mode_update_item,
    build_contextual_user_message,
    build_developer_update_item,
    build_environment_update_item,
    build_initial_realtime_item,
    build_model_instructions_update_item,
    build_personality_update_item,
    build_permissions_update_item,
    build_realtime_update_item,
    build_settings_update_items,
    build_text_message,
    personality_message_for,
)
from pycodex.features import Feature
from pycodex.protocol import ApprovalsReviewer, AskForApproval, PermissionProfile, TurnEnvironmentSelection


class ApprovalCell:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class FeatureSet:
    def __init__(self, *features):
        self._features = set(features)

    def enabled(self, feature):
        return feature in self._features


class ModelMessages:
    def __init__(self, messages):
        self._messages = messages

    def get_personality_message(self, personality):
        return self._messages.get(personality)


class ModelInfo:
    def __init__(self, slug, instructions):
        self.slug = slug
        self._instructions = instructions

    def get_model_instructions(self, personality):
        return self._instructions.get(personality, self._instructions.get(None, ""))


class ContextUpdatesTests(unittest.TestCase):
    def test_environment_update_follows_config_previous_and_shell_ignored_rules(self) -> None:
        previous = SimpleNamespace(
            cwd=Path("/repo"),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
        )
        disabled = SimpleNamespace(
            config=SimpleNamespace(include_environment_context=False),
            cwd=Path("/other"),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
        )
        shell = SimpleNamespace(name=lambda: "bash")
        shell_only = SimpleNamespace(
            config=SimpleNamespace(include_environment_context=True),
            cwd=Path("/repo"),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
        )
        changed = SimpleNamespace(
            config=SimpleNamespace(include_environment_context=True),
            cwd=Path("/repo2"),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
        )

        self.assertIsNone(build_environment_update_item(None, changed, shell))
        self.assertIsNone(build_environment_update_item(previous, disabled, shell))
        self.assertIsNone(build_environment_update_item(previous, shell_only, SimpleNamespace(name=lambda: "zsh")))

        item = build_environment_update_item(previous, changed, shell)

        self.assertIsNotNone(item)
        self.assertEqual(item.role, "user")
        self.assertIn("<environment_context>", item.content[0].text)
        self.assertIn(f"<cwd>{Path('/repo2')}</cwd>", item.content[0].text)

    def test_settings_update_items_keep_rust_developer_order_and_contextual_user_last(self) -> None:
        previous = SimpleNamespace(
            permission_profile=lambda: PermissionProfile.disabled(),
            approval_policy=AskForApproval.NEVER,
            collaboration_mode="default",
            realtime_active=False,
            model="gpt-new",
            personality="pragmatic",
        )
        previous_turn_settings = SimpleNamespace(model="gpt-old", realtime_active=False)
        model_info = SimpleNamespace(
            slug="gpt-new",
            model_messages=ModelMessages({"friendly": "Be warm."}),
            get_model_instructions=lambda personality: "Use the new model policy.",
        )
        next_context = SimpleNamespace(
            permission_profile=PermissionProfile.disabled(),
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
            config=SimpleNamespace(
                approvals_reviewer=ApprovalsReviewer.USER,
                include_permissions_instructions=True,
                include_collaboration_mode_instructions=True,
                experimental_realtime_start_instructions=None,
            ),
            features=FeatureSet(Feature.EXEC_PERMISSION_APPROVALS, Feature.REQUEST_PERMISSIONS_TOOL),
            cwd=Path("/workspace"),
            collaboration_mode=SimpleNamespace(settings=SimpleNamespace(developer_instructions="collab")),
            realtime_active=True,
            model_info=model_info,
            personality="friendly",
        )
        contextual = build_contextual_user_message(["environment update"])

        items = build_settings_update_items(
            previous,
            previous_turn_settings,
            next_context,
            personality_feature_enabled=True,
            contextual_user_message=contextual,
        )

        self.assertEqual([item.role for item in items], ["developer", "user"])
        developer_sections = [content.text for content in items[0].content]
        self.assertEqual(len(developer_sections), 5)
        self.assertIn("<model_switch>", developer_sections[0])
        self.assertIn("<permissions instructions>", developer_sections[1])
        self.assertIn("<collaboration_mode>", developer_sections[2])
        self.assertIn("<realtime_conversation>", developer_sections[3])
        self.assertIn("<personality_spec>", developer_sections[4])
        self.assertEqual(items[1], contextual)

        with self.assertRaises(TypeError):
            build_settings_update_items(previous, previous_turn_settings, next_context, personality_feature_enabled=1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            build_settings_update_items(
                previous,
                previous_turn_settings,
                next_context,
                personality_feature_enabled=True,
                contextual_user_message="bad",  # type: ignore[arg-type]
            )

    def test_settings_update_items_builds_environment_context_when_shell_supplied(self) -> None:
        previous = SimpleNamespace(
            cwd=Path("C:/repo"),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
            permission_profile=lambda: PermissionProfile.disabled(),
            approval_policy=AskForApproval.ON_REQUEST,
            collaboration_mode="default",
            realtime_active=False,
            model="gpt-test",
            personality=None,
        )
        previous_turn_settings = SimpleNamespace(model="gpt-test", realtime_active=False)
        next_context = SimpleNamespace(
            config=SimpleNamespace(
                include_environment_context=True,
                include_permissions_instructions=True,
                approvals_reviewer=ApprovalsReviewer.USER,
                include_collaboration_mode_instructions=False,
                experimental_realtime_start_instructions=None,
            ),
            cwd=Path("C:/repo2"),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
            permission_profile=PermissionProfile.disabled(),
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
            features=FeatureSet(),
            collaboration_mode="default",
            realtime_active=False,
            model_info=ModelInfo("gpt-test", {None: ""}),
            personality=None,
        )

        items = build_settings_update_items(
            previous,
            previous_turn_settings,
            next_context,
            personality_feature_enabled=False,
            shell=SimpleNamespace(name=lambda: "bash"),
        )

        self.assertEqual([item.role for item in items], ["user"])
        self.assertIn(f"<cwd>{Path('C:/repo2')}</cwd>", items[0].content[0].text)

    def test_settings_update_items_builds_environment_context_from_turn_environments(self) -> None:
        previous = SimpleNamespace(
            cwd=Path("C:/repo"),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
            permission_profile=lambda: PermissionProfile.disabled(),
            approval_policy=AskForApproval.ON_REQUEST,
            collaboration_mode="default",
            realtime_active=False,
            model="gpt-test",
            personality=None,
        )
        previous_turn_settings = SimpleNamespace(model="gpt-test", realtime_active=False)
        next_context = SimpleNamespace(
            config=SimpleNamespace(
                include_environment_context=True,
                include_permissions_instructions=True,
                approvals_reviewer=ApprovalsReviewer.USER,
                include_collaboration_mode_instructions=False,
                experimental_realtime_start_instructions=None,
            ),
            cwd=Path("C:/repo2"),
            environments=(
                TurnEnvironmentSelection("local", Path("C:/repo2")),
                TurnEnvironmentSelection("remote", Path("C:/remote")),
            ),
            current_date="2026-05-30",
            timezone="UTC",
            network=None,
            permission_profile=PermissionProfile.disabled(),
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
            features=FeatureSet(),
            collaboration_mode="default",
            realtime_active=False,
            model_info=ModelInfo("gpt-test", {None: ""}),
            personality=None,
        )

        items = build_settings_update_items(
            previous,
            previous_turn_settings,
            next_context,
            personality_feature_enabled=False,
            shell=SimpleNamespace(name=lambda: "bash"),
        )

        self.assertEqual([item.role for item in items], ["user"])
        self.assertIn("<environments>", items[0].content[0].text)
        self.assertIn('<environment id="local">', items[0].content[0].text)
        self.assertIn(f"<cwd>{Path('C:/repo2')}</cwd>", items[0].content[0].text)
        self.assertIn('<environment id="remote">', items[0].content[0].text)
        self.assertIn(f"<cwd>{Path('C:/remote')}</cwd>", items[0].content[0].text)

    def test_text_update_messages_match_rust_empty_and_multi_section_behavior(self) -> None:
        self.assertIsNone(build_developer_update_item([]))
        self.assertIsNone(build_contextual_user_message(()))

        developer = build_developer_update_item(["one", "two"])
        user = build_contextual_user_message(["context"])

        self.assertEqual(developer.role, "developer")
        self.assertEqual([item.text for item in developer.content], ["one", "two"])
        self.assertEqual(user.role, "user")
        self.assertEqual([item.text for item in user.content], ["context"])

        with self.assertRaises(TypeError):
            build_text_message(123, ["text"])  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            build_text_message("developer", "text")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            build_text_message("developer", ["ok", 1])  # type: ignore[list-item]

    def test_model_instructions_update_matches_previous_settings_and_empty_rules(self) -> None:
        previous_settings = SimpleNamespace(model="gpt-old")
        next_context = SimpleNamespace(
            model_info=ModelInfo("gpt-new", {None: "Use the new model policy."}),
            personality=None,
        )

        self.assertIsNone(build_model_instructions_update_item(None, next_context))
        self.assertIsNone(
            build_model_instructions_update_item(
                SimpleNamespace(model="gpt-new"),
                next_context,
            )
        )
        self.assertIsNone(
            build_model_instructions_update_item(
                previous_settings,
                SimpleNamespace(model_info=ModelInfo("gpt-new", {None: ""}), personality=None),
            )
        )
        self.assertEqual(
            build_model_instructions_update_item(previous_settings, next_context),
            (
                "<model_switch>\n"
                "The user was previously using a different model. Please continue the conversation according to the following instructions:\n\n"
                "Use the new model policy.\n"
                "</model_switch>"
            ),
        )

    def test_personality_update_matches_feature_model_and_message_rules(self) -> None:
        model_info = SimpleNamespace(
            slug="gpt-test",
            model_messages=ModelMessages({"friendly": "Be warm.", "empty": ""}),
        )
        previous = SimpleNamespace(model="gpt-test", personality="pragmatic")
        next_context = SimpleNamespace(model_info=model_info, personality="friendly")

        self.assertIsNone(build_personality_update_item(previous, next_context, False))
        self.assertIsNone(build_personality_update_item(None, next_context, True))
        self.assertIsNone(
            build_personality_update_item(
                SimpleNamespace(model="other", personality="pragmatic"),
                next_context,
                True,
            )
        )
        self.assertIsNone(
            build_personality_update_item(
                SimpleNamespace(model="gpt-test", personality="friendly"),
                next_context,
                True,
            )
        )
        self.assertIsNone(
            build_personality_update_item(
                previous,
                SimpleNamespace(model_info=model_info, personality="empty"),
                True,
            )
        )
        self.assertEqual(personality_message_for(model_info, "friendly"), "Be warm.")
        self.assertEqual(
            build_personality_update_item(previous, next_context, True),
            "<personality_spec> The user has requested a new communication style. Future messages should adhere to the following personality: \nBe warm. </personality_spec>",
        )

        with self.assertRaises(TypeError):
            build_personality_update_item(previous, next_context, 1)  # type: ignore[arg-type]

    def test_realtime_update_matches_rust_state_transitions(self) -> None:
        config = SimpleNamespace(experimental_realtime_start_instructions=None)
        custom_config = SimpleNamespace(experimental_realtime_start_instructions="listen carefully")

        self.assertIn(
            "Realtime conversation ended.",
            build_realtime_update_item(
                SimpleNamespace(realtime_active=True),
                None,
                SimpleNamespace(realtime_active=False, config=config),
            ),
        )
        self.assertIn(
            "Realtime conversation started.",
            build_realtime_update_item(
                SimpleNamespace(realtime_active=False),
                None,
                SimpleNamespace(realtime_active=True, config=config),
            ),
        )
        self.assertEqual(
            build_realtime_update_item(
                None,
                None,
                SimpleNamespace(realtime_active=True, config=custom_config),
            ),
            "<realtime_conversation>\nlisten carefully\n</realtime_conversation>",
        )
        self.assertIsNone(
            build_realtime_update_item(
                SimpleNamespace(realtime_active=True),
                None,
                SimpleNamespace(realtime_active=True, config=config),
            )
        )
        self.assertIsNone(
            build_realtime_update_item(
                SimpleNamespace(realtime_active=False),
                None,
                SimpleNamespace(realtime_active=False, config=config),
            )
        )

    def test_initial_realtime_uses_previous_turn_settings_for_missing_previous_context(self) -> None:
        text = build_initial_realtime_item(
            None,
            SimpleNamespace(realtime_active=True),
            SimpleNamespace(
                realtime_active=False,
                config=SimpleNamespace(experimental_realtime_start_instructions=None),
            ),
        )

        self.assertIsNotNone(text)
        self.assertIn("Realtime conversation ended.", text)

    def test_collaboration_mode_update_follows_include_change_and_empty_instruction_rules(self) -> None:
        previous = SimpleNamespace(collaboration_mode="default")
        disabled = SimpleNamespace(
            config=SimpleNamespace(include_collaboration_mode_instructions=False),
            collaboration_mode=SimpleNamespace(settings=SimpleNamespace(developer_instructions="plan first")),
        )
        unchanged = SimpleNamespace(
            config=SimpleNamespace(include_collaboration_mode_instructions=True),
            collaboration_mode="default",
        )
        empty = SimpleNamespace(
            config=SimpleNamespace(include_collaboration_mode_instructions=True),
            collaboration_mode=SimpleNamespace(settings=SimpleNamespace(developer_instructions="")),
        )
        changed = SimpleNamespace(
            config=SimpleNamespace(include_collaboration_mode_instructions=True),
            collaboration_mode=SimpleNamespace(settings=SimpleNamespace(developer_instructions="plan first")),
        )

        self.assertIsNone(build_collaboration_mode_update_item(None, changed))
        self.assertIsNone(build_collaboration_mode_update_item(previous, disabled))
        self.assertIsNone(build_collaboration_mode_update_item(previous, unchanged))
        self.assertIsNone(build_collaboration_mode_update_item(previous, empty))
        self.assertEqual(
            build_collaboration_mode_update_item(previous, changed),
            "<collaboration_mode>plan first</collaboration_mode>",
        )

    def test_permissions_update_ignores_feature_only_changes_like_rust(self) -> None:
        profile = PermissionProfile.disabled()
        previous = SimpleNamespace(
            permission_profile=lambda: profile,
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
        )
        next_context = SimpleNamespace(
            permission_profile=profile,
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
            config=SimpleNamespace(
                include_permissions_instructions=True,
                approvals_reviewer=ApprovalsReviewer.USER,
            ),
            features=FeatureSet(Feature.REQUEST_PERMISSIONS_TOOL),
            cwd=Path("/workspace"),
        )

        self.assertIsNone(build_permissions_update_item(previous, next_context))

    def test_permissions_update_respects_include_permissions_instructions_flag(self) -> None:
        profile = PermissionProfile.disabled()
        previous = SimpleNamespace(
            permission_profile=lambda: profile,
            approval_policy=ApprovalCell(AskForApproval.NEVER),
        )
        next_context = SimpleNamespace(
            permission_profile=profile,
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
            config=SimpleNamespace(
                include_permissions_instructions=False,
                approvals_reviewer=ApprovalsReviewer.USER,
            ),
            features=FeatureSet(Feature.REQUEST_PERMISSIONS_TOOL),
            cwd=Path("/workspace"),
        )

        self.assertIsNone(build_permissions_update_item(previous, next_context))

    def test_permissions_update_unwraps_previous_and_next_approval_policy_cells(self) -> None:
        profile = PermissionProfile.disabled()
        previous = SimpleNamespace(
            permission_profile=lambda: profile,
            approval_policy=ApprovalCell(AskForApproval.ON_FAILURE),
        )
        next_context = SimpleNamespace(
            permission_profile=profile,
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
            config=SimpleNamespace(
                include_permissions_instructions=True,
                approvals_reviewer=ApprovalsReviewer.USER,
            ),
            features=FeatureSet(),
            cwd=Path("/workspace"),
        )

        text = build_permissions_update_item(previous, next_context)

        self.assertIsNotNone(text)
        self.assertIn("How to request escalation", text)

    def test_permissions_update_passes_request_permissions_feature_to_prompt(self) -> None:
        previous = SimpleNamespace(
            permission_profile=lambda: PermissionProfile.disabled(),
            approval_policy=AskForApproval.NEVER,
        )
        next_context = SimpleNamespace(
            permission_profile=PermissionProfile.disabled(),
            approval_policy=ApprovalCell(AskForApproval.ON_REQUEST),
            config=SimpleNamespace(
                include_permissions_instructions=True,
                approvals_reviewer=ApprovalsReviewer.USER,
            ),
            features=FeatureSet(
                Feature.EXEC_PERMISSION_APPROVALS,
                Feature.REQUEST_PERMISSIONS_TOOL,
            ),
            cwd=Path("/workspace"),
        )

        text = build_permissions_update_item(previous, next_context)

        self.assertIsNotNone(text)
        self.assertIn("<permissions instructions>", text)
        self.assertIn("# Permission Requests", text)
        self.assertIn("# request_permissions Tool", text)


if __name__ == "__main__":
    unittest.main()

