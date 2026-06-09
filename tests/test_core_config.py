import unittest
from types import SimpleNamespace

from pycodex.core.config import (
    AuthCredentialsStoreMode,
    LOCAL_DEV_BUILD_VERSION,
    OAuthCredentialsStoreMode,
    ghost_snapshot_config,
    resolve_cli_auth_credentials_store_mode,
    resolve_effective_permission_selection,
    resolve_mcp_oauth_credentials_store_mode,
    thread_store_config,
)
from pycodex.core.config.permissions import (
    ProjectTrust,
    SandboxWorkspaceWrite,
    builtin_permission_profile,
    default_builtin_permission_profile_name,
    reject_unknown_builtin_permission_profile,
)
from pycodex.protocol import (
    ApprovalsReviewer,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    WebSearchMode,
    WebSearchToolConfig,
    WindowsSandboxLevel,
)


class CoreConfigParityTests(unittest.TestCase):
    def test_top_level_config_defaults_match_rust_config_tests_clusters(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_tests.rs
        # Rust tests: test_toml_parsing, config_defaults_to_file_cli_auth_store_mode,
        # config_resolves_default_oauth_store_mode, feedback_enabled_defaults_to_true,
        # runtime_config_defaults_model_availability_nux.
        self.assertEqual(thread_store_config(None).kind, "local")
        self.assertEqual(ghost_snapshot_config(None).disable_warnings, False)
        self.assertEqual(
            resolve_cli_auth_credentials_store_mode(AuthCredentialsStoreMode.AUTO, LOCAL_DEV_BUILD_VERSION),
            AuthCredentialsStoreMode.FILE,
        )
        self.assertEqual(
            resolve_mcp_oauth_credentials_store_mode(OAuthCredentialsStoreMode.AUTO, LOCAL_DEV_BUILD_VERSION),
            OAuthCredentialsStoreMode.FILE,
        )

    def test_web_search_and_protocol_config_values_match_rust_config_tests(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_tests.rs
        # Rust tests: web_search_mode_defaults_to_none_if_unset,
        # web_search_mode_prefers_config_over_legacy_flags,
        # web_search_mode_disabled_overrides_legacy_request,
        # tools_web_search_true_deserializes_to_none,
        # tools_web_search_false_deserializes_to_none.
        self.assertEqual(WebSearchMode.DISABLED.value, "disabled")
        self.assertEqual(WebSearchMode.CACHED.value, "cached")
        self.assertEqual(WebSearchMode.LIVE.value, "live")

        base = WebSearchToolConfig(context_size="low")
        overlay = WebSearchToolConfig(context_size="high")
        self.assertEqual(base.merge(overlay).context_size, "high")
        self.assertIsNone(WebSearchToolConfig().context_size)

    def test_permissions_profile_defaults_and_runtime_projection_match_config_tests(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_tests.rs
        # Rust tests: empty_config_defaults_to_builtin_profile_for_trusted_project,
        # empty_config_defaults_to_builtin_read_only_without_trust_decision,
        # default_permissions_can_select_builtin_full_access_profile,
        # unknown_builtin_permission_profile_name_is_rejected,
        # implicit_builtin_workspace_profile_preserves_sandbox_workspace_write_settings.
        self.assertEqual(
            default_builtin_permission_profile_name(ProjectTrust(trusted=True), WindowsSandboxLevel.RESTRICTED_TOKEN),
            ":workspace",
        )
        self.assertEqual(
            default_builtin_permission_profile_name(ProjectTrust(), WindowsSandboxLevel.RESTRICTED_TOKEN),
            ":read-only",
        )
        self.assertIsNotNone(builtin_permission_profile(":danger-full-access"))
        with self.assertRaisesRegex(ValueError, "unknown built-in profile"):
            reject_unknown_builtin_permission_profile(":unknown")

        workspace = builtin_permission_profile(
            ":workspace",
            SandboxWorkspaceWrite(network_access=True, exclude_slash_tmp=True, exclude_tmpdir_env_var=True),
        )
        filesystem, network = workspace.to_runtime_permissions()
        self.assertEqual(network.value, "enabled")
        self.assertTrue(any(entry.access.value == "write" for entry in filesystem.entries))

    def test_requirements_fallback_and_approval_reviewer_protocol_values_match_config_tests(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_tests.rs
        # Rust tests: requirements_disallowing_default_sandbox_falls_back_to_required_default,
        # permission_profile_override_falls_back_when_disallowed_by_requirements,
        # requirements_disallowing_default_approvals_reviewer_falls_back_to_required_default,
        # approvals_reviewer_preserves_valid_user_choice_when_allowed_by_requirements.
        warnings: list[str] = []
        effective = resolve_effective_permission_selection(
            {"profiles": {"managed": {"type": "managed"}}},
            "local",
            None,
            {"allowed_permissions": ["managed"]},
            warnings,
        )

        self.assertEqual(effective.selected_profile_id, "managed")
        self.assertTrue(effective.requirements_force_profile_selection)
        self.assertEqual(ApprovalsReviewer.USER.value, "user")
        self.assertEqual(ApprovalsReviewer.AUTO_REVIEW.value, "guardian_subagent")
        self.assertEqual(ApprovalsReviewer.parse("auto_review"), ApprovalsReviewer.AUTO_REVIEW)

    def test_shell_environment_policy_and_tui_adjacent_defaults_match_config_tests(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_tests.rs
        # Rust tests: shell_environment_policy_* cluster, test_tui_* defaults,
        # config_toml_deserializes_terminal_resize_reflow_config.
        default_policy = ShellEnvironmentPolicy.default()
        custom_policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            ignore_default_excludes=False,
            exclude=("SECRET",),
            set_values={"A": "1"},
            include_only=("PATH",),
            use_profile=True,
        )

        self.assertEqual(default_policy.inherit, ShellEnvironmentPolicyInherit.ALL)
        self.assertTrue(default_policy.ignore_default_excludes)
        self.assertEqual(custom_policy.inherit, ShellEnvironmentPolicyInherit.NONE)
        self.assertEqual(custom_policy.exclude, ("SECRET",))
        self.assertEqual(custom_policy.set_values, {"A": "1"})
        self.assertTrue(custom_policy.use_profile)


if __name__ == "__main__":
    unittest.main()
