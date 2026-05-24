import unittest
from datetime import timedelta

from pycodex.protocol import (
    AltScreenMode,
    ApprovalsReviewer,
    AskForApproval,
    AutoCompactTokenLimitScope,
    CollaborationMode,
    CollaborationModeMask,
    ForcedLoginMethod,
    ModeKind,
    ModelProviderAuthInfo,
    Personality,
    ProfileV2Name,
    ProfileV2NameParseError,
    ReasoningEffort,
    ReasoningSummary,
    SandboxMode,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    ServiceTier,
    Settings,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    TrustLevel,
    TUI_VISIBLE_COLLABORATION_MODES,
    Verbosity,
    WebSearchConfig,
    WebSearchContextSize,
    WebSearchFilters,
    WebSearchLocation,
    WebSearchMode,
    WebSearchToolConfig,
    WebSearchUserLocation,
    WebSearchUserLocationType,
    WindowsSandboxLevel,
)
from pycodex.protocol.config_types import ConfigTypeParseError


class ProtocolConfigTypeTests(unittest.TestCase):
    def test_sandbox_mode_values_match_upstream_kebab_case(self):
        self.assertEqual(SandboxMode.READ_ONLY.to_json(), "read-only")
        self.assertEqual(SandboxMode.WORKSPACE_WRITE.to_json(), "workspace-write")
        self.assertEqual(SandboxMode.DANGER_FULL_ACCESS.to_json(), "danger-full-access")
        self.assertIs(SandboxMode.default(), SandboxMode.READ_ONLY)

    def test_sandbox_mode_parse_rejects_unknown_value(self):
        with self.assertRaisesRegex(ConfigTypeParseError, "invalid SandboxMode"):
            SandboxMode.parse("workspace_write")

    def test_approval_cli_values_map_to_protocol_values(self):
        self.assertIs(AskForApproval.parse_cli("untrusted"), AskForApproval.UNLESS_TRUSTED)
        self.assertIs(AskForApproval.parse_cli("on-failure"), AskForApproval.ON_FAILURE)
        self.assertIs(AskForApproval.parse_cli("on-request"), AskForApproval.ON_REQUEST)
        self.assertIs(AskForApproval.parse_cli("never"), AskForApproval.NEVER)
        self.assertIs(AskForApproval.default(), AskForApproval.ON_REQUEST)

    def test_approval_cli_rejects_granular_because_cli_arg_does_not_expose_it(self):
        with self.assertRaisesRegex(ConfigTypeParseError, "invalid AskForApproval"):
            AskForApproval.parse_cli("granular")

    def test_windows_sandbox_level_values_match_upstream_kebab_case(self):
        self.assertEqual(WindowsSandboxLevel.DISABLED.to_json(), "disabled")
        self.assertEqual(WindowsSandboxLevel.RESTRICTED_TOKEN.to_json(), "restricted-token")
        self.assertEqual(WindowsSandboxLevel.ELEVATED.to_json(), "elevated")
        self.assertIs(WindowsSandboxLevel.default(), WindowsSandboxLevel.DISABLED)

    def test_lowercase_enums_match_upstream_values(self):
        self.assertEqual(AutoCompactTokenLimitScope.BODY_AFTER_PREFIX.to_json(), "body_after_prefix")
        self.assertIs(AutoCompactTokenLimitScope.default(), AutoCompactTokenLimitScope.TOTAL)
        self.assertEqual(ReasoningSummary.DETAILED.to_json(), "detailed")
        self.assertIs(ReasoningSummary.default(), ReasoningSummary.AUTO)
        self.assertEqual(ReasoningEffort.XHIGH.to_json(), "xhigh")
        self.assertIs(ReasoningEffort.default(), ReasoningEffort.MEDIUM)
        self.assertEqual(Verbosity.LOW.to_json(), "low")
        self.assertIs(Verbosity.default(), Verbosity.MEDIUM)
        self.assertEqual(AltScreenMode.NEVER.to_json(), "never")
        self.assertIs(AltScreenMode.default(), AltScreenMode.AUTO)
        self.assertEqual(Personality.PRAGMATIC.to_json(), "pragmatic")
        self.assertEqual(WebSearchMode.LIVE.to_json(), "live")
        self.assertIs(WebSearchMode.default(), WebSearchMode.CACHED)
        self.assertEqual(WebSearchContextSize.HIGH.to_json(), "high")
        self.assertEqual(ForcedLoginMethod.CHATGPT.to_json(), "chatgpt")
        self.assertEqual(TrustLevel.UNTRUSTED.to_json(), "untrusted")

    def test_approvals_reviewer_accepts_legacy_and_current_names(self):
        self.assertIs(ApprovalsReviewer.default(), ApprovalsReviewer.USER)
        self.assertEqual(ApprovalsReviewer.USER.to_json(), "user")
        self.assertEqual(ApprovalsReviewer.AUTO_REVIEW.to_json(), "guardian_subagent")
        self.assertIs(ApprovalsReviewer.parse("guardian_subagent"), ApprovalsReviewer.AUTO_REVIEW)
        self.assertIs(ApprovalsReviewer.parse("auto_review"), ApprovalsReviewer.AUTO_REVIEW)

    def test_shell_environment_policy_defaults_match_upstream(self):
        policy = ShellEnvironmentPolicy.default()

        self.assertIs(policy.inherit, ShellEnvironmentPolicyInherit.ALL)
        self.assertTrue(policy.ignore_default_excludes)
        self.assertEqual(policy.exclude, ())
        self.assertEqual(policy.set_values, {})
        self.assertEqual(policy.include_only, ())
        self.assertFalse(policy.use_profile)

    def test_web_search_location_merge_prefers_overlay_values(self):
        base = WebSearchLocation(country="US", region="CA", timezone="America/Los_Angeles")
        overlay = WebSearchLocation(region="WA", city="Seattle")

        self.assertEqual(
            base.merge(overlay),
            WebSearchLocation(country="US", region="WA", city="Seattle", timezone="America/Los_Angeles"),
        )

    def test_web_search_tool_config_merge_prefers_overlay_values(self):
        base = WebSearchToolConfig(
            context_size=WebSearchContextSize.LOW,
            allowed_domains=("openai.com",),
            location=WebSearchLocation(country="US", region="CA", timezone="America/Los_Angeles"),
        )
        overlay = WebSearchToolConfig(
            context_size=WebSearchContextSize.HIGH,
            location=WebSearchLocation(region="WA", city="Seattle"),
        )

        self.assertEqual(
            base.merge(overlay),
            WebSearchToolConfig(
                context_size=WebSearchContextSize.HIGH,
                allowed_domains=("openai.com",),
                location=WebSearchLocation(country="US", region="WA", city="Seattle", timezone="America/Los_Angeles"),
            ),
        )

    def test_web_search_tool_config_converts_to_runtime_config(self):
        tool_config = WebSearchToolConfig(
            context_size=WebSearchContextSize.MEDIUM,
            allowed_domains=("openai.com", "platform.openai.com"),
            location=WebSearchLocation(country="US", city="San Francisco"),
        )

        self.assertEqual(
            WebSearchConfig.from_tool_config(tool_config),
            WebSearchConfig(
                filters=WebSearchFilters(("openai.com", "platform.openai.com")),
                user_location=WebSearchUserLocation(
                    type=WebSearchUserLocationType.APPROXIMATE,
                    country="US",
                    city="San Francisco",
                ),
                search_context_size=WebSearchContextSize.MEDIUM,
            ),
        )

    def test_service_tier_request_values_match_upstream(self):
        self.assertEqual(SERVICE_TIER_DEFAULT_REQUEST_VALUE, "default")
        self.assertEqual(ServiceTier.FAST.request_value(), "priority")
        self.assertEqual(ServiceTier.FLEX.request_value(), "flex")
        self.assertIs(ServiceTier.from_request_value("fast"), ServiceTier.FAST)
        self.assertIs(ServiceTier.from_request_value("priority"), ServiceTier.FAST)
        self.assertIs(ServiceTier.from_request_value("flex"), ServiceTier.FLEX)
        self.assertIsNone(ServiceTier.from_request_value("default"))

    def test_model_provider_auth_info_defaults_and_durations(self):
        auth = ModelProviderAuthInfo(command="token-helper")

        self.assertEqual(auth.args, ())
        self.assertEqual(auth.timeout(), timedelta(seconds=5))
        self.assertEqual(auth.refresh_interval(), timedelta(minutes=5))
        self.assertIsNone(ModelProviderAuthInfo(command="token-helper", refresh_interval_ms=0).refresh_interval())
        with self.assertRaisesRegex(ValueError, "timeout_ms must be non-zero"):
            ModelProviderAuthInfo(command="token-helper", timeout_ms=0)

    def test_mode_kind_aliases_and_visibility_match_upstream(self):
        for alias in ("code", "pair_programming", "execute", "custom"):
            with self.subTest(alias=alias):
                self.assertIs(ModeKind.parse(alias), ModeKind.DEFAULT)

        self.assertEqual(TUI_VISIBLE_COLLABORATION_MODES, (ModeKind.DEFAULT, ModeKind.PLAN))
        self.assertEqual(ModeKind.PLAN.display_name(), "Plan")
        self.assertEqual(ModeKind.DEFAULT.display_name(), "Default")
        self.assertTrue(ModeKind.PLAN.is_tui_visible())
        self.assertFalse(ModeKind.EXECUTE.is_tui_visible())
        self.assertTrue(ModeKind.PLAN.allows_request_user_input())
        self.assertFalse(ModeKind.DEFAULT.allows_request_user_input())

    def test_collaboration_mode_updates_and_masks_preserve_or_clear_fields(self):
        mode = CollaborationMode(
            mode=ModeKind.DEFAULT,
            settings=Settings(
                model="gpt-5.2-codex",
                reasoning_effort=ReasoningEffort.HIGH,
                developer_instructions="stay focused",
            ),
        )

        updated = mode.with_updates(model="gpt-5.3-codex", effort=None)
        masked = mode.apply_mask(
            CollaborationModeMask(
                name="Clear",
                reasoning_effort=None,
                developer_instructions=None,
            )
        )

        self.assertEqual(updated.model(), "gpt-5.3-codex")
        self.assertIsNone(updated.reasoning_effort())
        self.assertEqual(updated.settings.developer_instructions, "stay focused")
        self.assertEqual(
            masked,
            CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings(model="gpt-5.2-codex", reasoning_effort=None, developer_instructions=None),
            ),
        )

    def test_profile_v2_name_accepts_plain_ascii_names(self):
        profile = ProfileV2Name.parse("work_1-prod")

        self.assertEqual(profile.as_str(), "work_1-prod")
        self.assertIsInstance(profile, str)

    def test_profile_v2_name_rejects_empty_pathlike_or_non_ascii_values(self):
        for raw in ("", "work/prod", "work.prod", "中文"):
            with self.subTest(raw=raw):
                with self.assertRaises(ProfileV2NameParseError):
                    ProfileV2Name.parse(raw)


if __name__ == "__main__":
    unittest.main()
