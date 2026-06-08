import unittest
from pathlib import Path

from pycodex.core.config import (
    AuthCredentialsStoreMode,
    GhostSnapshotConfig,
    LOCAL_DEV_BUILD_VERSION,
    OAuthCredentialsStoreMode,
    ThreadStoreConfig,
    ghost_snapshot_config,
    guardian_policy_config_from_requirements,
    normalize_guardian_policy_config,
    resolve_cli_auth_credentials_store_mode,
    resolve_default_permissions,
    resolve_mcp_oauth_credentials_store_mode,
    resolve_sqlite_home_env,
    thread_store_config,
    validate_required_permission_profile_catalog,
)


class CoreConfigRootTests(unittest.TestCase):
    def test_local_dev_builds_force_file_cli_auth_store_modes(self) -> None:
        # Rust: config_tests.rs::local_dev_builds_force_file_cli_auth_store_modes.
        self.assertEqual(
            resolve_cli_auth_credentials_store_mode(AuthCredentialsStoreMode.KEYRING, LOCAL_DEV_BUILD_VERSION),
            AuthCredentialsStoreMode.FILE,
        )
        self.assertEqual(
            resolve_cli_auth_credentials_store_mode(AuthCredentialsStoreMode.AUTO, LOCAL_DEV_BUILD_VERSION),
            AuthCredentialsStoreMode.FILE,
        )
        self.assertEqual(
            resolve_cli_auth_credentials_store_mode(AuthCredentialsStoreMode.EPHEMERAL, LOCAL_DEV_BUILD_VERSION),
            AuthCredentialsStoreMode.EPHEMERAL,
        )
        self.assertEqual(
            resolve_cli_auth_credentials_store_mode(AuthCredentialsStoreMode.KEYRING, "1.2.3"),
            AuthCredentialsStoreMode.KEYRING,
        )

    def test_local_dev_builds_force_file_mcp_oauth_store_modes(self) -> None:
        # Rust: config_tests.rs::local_dev_builds_force_file_mcp_oauth_store_modes.
        self.assertEqual(
            resolve_mcp_oauth_credentials_store_mode(OAuthCredentialsStoreMode.KEYRING, LOCAL_DEV_BUILD_VERSION),
            OAuthCredentialsStoreMode.FILE,
        )
        self.assertEqual(
            resolve_mcp_oauth_credentials_store_mode(OAuthCredentialsStoreMode.AUTO, LOCAL_DEV_BUILD_VERSION),
            OAuthCredentialsStoreMode.FILE,
        )
        self.assertEqual(
            resolve_mcp_oauth_credentials_store_mode(OAuthCredentialsStoreMode.KEYRING, "1.2.3"),
            OAuthCredentialsStoreMode.KEYRING,
        )

    def test_resolve_sqlite_home_env_matches_rust_trim_and_relative_join(self) -> None:
        # Rust: codex-rs/core/src/config/mod.rs::resolve_sqlite_home_env.
        cwd = Path("C:/work/project")

        self.assertIsNone(resolve_sqlite_home_env(cwd, {}))
        self.assertIsNone(resolve_sqlite_home_env(cwd, {"CODEX_SQLITE_HOME": "   "}))
        self.assertEqual(resolve_sqlite_home_env(cwd, {"CODEX_SQLITE_HOME": " state "}), cwd / "state")
        self.assertEqual(resolve_sqlite_home_env(cwd, {"CODEX_SQLITE_HOME": "C:/state"}), Path("C:/state"))

    def test_thread_store_config_maps_optional_toml(self) -> None:
        # Rust: codex-rs/core/src/config/mod.rs::thread_store_config.
        self.assertEqual(thread_store_config(None), ThreadStoreConfig.local())
        self.assertEqual(thread_store_config({"type": "local"}), ThreadStoreConfig.local())
        self.assertEqual(thread_store_config({"type": "in_memory", "id": "session-1"}), ThreadStoreConfig.in_memory("session-1"))

    def test_ghost_snapshot_config_preserves_legacy_compatibility_shape(self) -> None:
        # Rust: codex-rs/core/src/config/mod.rs GhostSnapshotConfig default and load block.
        self.assertEqual(ghost_snapshot_config(None), GhostSnapshotConfig())
        self.assertEqual(
            ghost_snapshot_config(
                {
                    "ignore_large_untracked_files": 0,
                    "ignore_large_untracked_dirs": -1,
                    "disable_warnings": True,
                }
            ),
            GhostSnapshotConfig(
                ignore_large_untracked_files=None,
                ignore_large_untracked_dirs=None,
                disable_warnings=True,
            ),
        )
        self.assertEqual(
            ghost_snapshot_config({"ignore_large_untracked_files": 42, "ignore_large_untracked_dirs": 7}),
            GhostSnapshotConfig(ignore_large_untracked_files=42, ignore_large_untracked_dirs=7),
        )

    def test_guardian_policy_config_is_trimmed_and_empty_is_ignored(self) -> None:
        # Rust: load_config_uses_requirements_guardian_policy_config and empty-policy tests.
        self.assertEqual(
            guardian_policy_config_from_requirements({"guardian_policy_config": "  Use managed policy.  "}),
            "Use managed policy.",
        )
        self.assertIsNone(guardian_policy_config_from_requirements({"guardian_policy_config": "   "}))
        self.assertIsNone(normalize_guardian_policy_config(None))

    def test_resolve_default_permissions_falls_back_to_allowed_non_builtin(self) -> None:
        # Rust: codex-rs/core/src/config/mod.rs::resolve_default_permissions.
        warnings: list[str] = []

        selected = resolve_default_permissions(
            "user-profile",
            None,
            {"allowed_permissions": ["managed-profile"]},
            warnings,
        )

        self.assertEqual(selected, "managed-profile")
        self.assertEqual(
            warnings,
            [
                "Configured value for `permission_profile` is disallowed by requirements; "
                "falling back from `user-profile` to required value `managed-profile`."
            ],
        )

    def test_resolve_default_permissions_keeps_builtin_even_when_not_listed(self) -> None:
        warnings: list[str] = []

        selected = resolve_default_permissions(":workspace", None, {"allowed_permissions": ["managed-profile"]}, warnings)

        self.assertEqual(selected, ":workspace")
        self.assertEqual(warnings, [])

    def test_validate_required_permission_profile_catalog_errors_like_rust(self) -> None:
        validate_required_permission_profile_catalog({"allowed_permissions": [":read-only", "custom"]}, {"custom": {}})
        with self.assertRaisesRegex(ValueError, "must include at least one profile"):
            validate_required_permission_profile_catalog({"allowed_permissions": []}, {})
        with self.assertRaisesRegex(ValueError, "refers to undefined profile `missing`"):
            validate_required_permission_profile_catalog({"allowed_permissions": ["missing"]}, {})


if __name__ == "__main__":
    unittest.main()
