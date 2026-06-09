import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.config import (
    build_network_proxy_spec,
    guardian_policy_config_from_requirements,
    merge_managed_permission_profiles,
    resolve_effective_permission_selection,
    resolve_sqlite_home_env,
    validate_required_permission_profile_catalog,
)
from pycodex.network_proxy import NetworkProxyConfig


class CoreConfigLoaderParityTests(unittest.TestCase):
    def test_cli_and_env_relative_paths_resolve_against_cwd(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_loader_tests.rs
        # Rust tests: cli_overrides_resolve_relative_paths_against_cwd,
        # cli_overrides_with_relative_paths_do_not_break_trust_check.
        cwd = Path("C:/repo/project")

        self.assertEqual(resolve_sqlite_home_env(cwd, {"CODEX_SQLITE_HOME": " state "}), cwd / "state")
        self.assertEqual(resolve_sqlite_home_env(cwd, {"CODEX_SQLITE_HOME": "C:/codex/state"}), Path("C:/codex/state"))
        self.assertIsNone(resolve_sqlite_home_env(cwd, {"CODEX_SQLITE_HOME": "   "}))

    def test_requirements_permission_profiles_merge_and_take_precedence(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_loader_tests.rs
        # Rust tests: managed_preferences_requirements_are_applied,
        # managed_preferences_requirements_take_precedence,
        # system_requirements_define_managed_permission_profiles.
        configured = {
            "profiles": {
                "local": {"type": "managed", "filesystem": {"/repo": "read"}},
            }
        }
        requirements = {
            "permissions": {
                "profiles": {
                    "managed": {"type": "managed", "filesystem": {"/managed": "read"}},
                }
            },
            "allowed_permissions": ["managed"],
        }
        warnings: list[str] = []

        effective = resolve_effective_permission_selection(
            configured,
            "local",
            None,
            requirements,
            warnings,
        )

        self.assertEqual(set(effective.profiles or {}), {"local", "managed"})
        self.assertEqual(effective.selected_profile_id, "managed")
        self.assertTrue(effective.requirements_force_profile_selection)
        self.assertEqual(
            warnings,
            [
                "Configured value for `permission_profile` is disallowed by requirements; "
                "falling back from `local` to required value `managed`."
            ],
        )

    def test_requirements_reject_conflicting_or_missing_permission_profiles(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_loader_tests.rs
        # Rust tests: system_requirements_warn_for_disallowed_explicit_permission_override,
        # system_allowed_permissions_keep_builtin_permission_fallbacks,
        # system_allowed_permissions_keep_explicit_builtin_defaults.
        with self.assertRaisesRegex(ValueError, "conflicts with a config-defined profile"):
            merge_managed_permission_profiles(
                {"profiles": {"managed": {"type": "managed"}}},
                {"permissions": {"profiles": {"managed": {"type": "managed"}}}},
            )
        with self.assertRaisesRegex(ValueError, "must include at least one profile"):
            validate_required_permission_profile_catalog({"allowed_permissions": []}, {})
        with self.assertRaisesRegex(ValueError, "refers to undefined profile `missing`"):
            validate_required_permission_profile_catalog({"allowed_permissions": ["missing"]}, {})

    def test_requirements_guardian_policy_is_trimmed_and_empty_policy_is_ignored(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_loader_tests.rs
        # Rust tests: load_requirements_toml_produces_expected_constraints,
        # load_config_layers_includes_cloud_requirements,
        # cloud_requirements_take_precedence_over_mdm_requirements.
        self.assertEqual(
            guardian_policy_config_from_requirements({"guardian_policy_config": "  Use managed policy.  "}),
            "Use managed policy.",
        )
        self.assertIsNone(guardian_policy_config_from_requirements({"guardian_policy_config": "   "}))
        self.assertIsNone(guardian_policy_config_from_requirements(None))

    def test_network_proxy_requirements_are_applied_with_managed_source_errors(self) -> None:
        # Rust source: codex/codex-rs/core/src/config/config_loader_tests.rs
        # Rust tests: managed_preferences_expand_home_directory_in_workspace_write_roots,
        # load_config_layers_applies_matching_remote_sandbox_config,
        # load_config_layers_fails_when_cloud_requirements_loader_fails.
        profile = SimpleNamespace(type="managed", network={"enabled": False})
        configured = NetworkProxyConfig()
        disabled = build_network_proxy_spec(configured, None, profile)

        self.assertIsNone(disabled)
        with self.assertRaisesRegex(Exception, "failed to build managed network proxy from cloud"):
            build_network_proxy_spec(
                configured,
                {"value": {"invalid": object()}, "source": "cloud"},
                SimpleNamespace(type="read-only"),
            )


if __name__ == "__main__":
    unittest.main()
