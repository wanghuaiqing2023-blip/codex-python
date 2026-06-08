from pathlib import Path
import unittest

from pycodex.core.config.resolved_permission_profile import (
    BuiltInPermissionProfileId,
    ConstrainedPermissionProfile,
    PermissionProfileSnapshot,
    PermissionProfileState,
    ResolvedPermissionProfile,
)
from pycodex.protocol import (
    ActivePermissionProfile,
    NetworkSandboxPolicy,
    PermissionProfile,
)


class CoreResolvedPermissionProfileTests(unittest.TestCase):
    def test_builtin_permission_profile_id_round_trips_rust_ids(self) -> None:
        # Rust source: codex-rs/core/src/config/resolved_permission_profile.rs
        # Rust methods: BuiltInPermissionProfileId::from_str/as_str.
        self.assertEqual(
            BuiltInPermissionProfileId.from_str(":read-only"),
            BuiltInPermissionProfileId.READ_ONLY,
        )
        self.assertEqual(
            BuiltInPermissionProfileId.from_str(":workspace"),
            BuiltInPermissionProfileId.WORKSPACE,
        )
        self.assertEqual(
            BuiltInPermissionProfileId.from_str(":danger-full-access"),
            BuiltInPermissionProfileId.DANGER_FULL_ACCESS,
        )
        self.assertIsNone(BuiltInPermissionProfileId.from_str("custom"))
        self.assertEqual(BuiltInPermissionProfileId.READ_ONLY.as_str(), ":read-only")
        self.assertEqual(BuiltInPermissionProfileId.WORKSPACE.as_str(), ":workspace")
        self.assertEqual(BuiltInPermissionProfileId.DANGER_FULL_ACCESS.as_str(), ":danger-full-access")

    def test_resolved_permission_profile_classifies_legacy_builtin_and_named(self) -> None:
        # Rust source: codex-rs/core/src/config/resolved_permission_profile.rs
        # Rust methods: ResolvedPermissionProfile::from_active_profile,
        # active_permission_profile, profile_workspace_roots.
        profile = PermissionProfile.read_only()
        self.assertEqual(
            ResolvedPermissionProfile.from_active_profile(profile, None).kind,
            "legacy",
        )
        self.assertIsNone(
            ResolvedPermissionProfile.from_active_profile(profile, None).active_permission_profile()
        )
        built_in = ResolvedPermissionProfile.from_active_profile(
            profile,
            ActivePermissionProfile(":workspace", extends="base"),
            ["/workspace"],
        )
        self.assertEqual(built_in.kind, "built_in")
        self.assertEqual(built_in.active_permission_profile(), ActivePermissionProfile(":workspace", "base"))
        self.assertEqual(built_in.profile_workspace_roots, (Path("/workspace"),))

        named = ResolvedPermissionProfile.from_active_profile(
            profile,
            ActivePermissionProfile("team-profile", extends=":workspace"),
            ["/repo"],
        )
        self.assertEqual(named.kind, "named")
        self.assertEqual(named.active_permission_profile(), ActivePermissionProfile("team-profile", ":workspace"))
        self.assertEqual(named.profile_workspace_roots, (Path("/repo"),))

    def test_permission_profile_snapshot_constructors_match_rust_contract(self) -> None:
        # Rust source: codex-rs/core/src/config/resolved_permission_profile.rs
        # Rust methods: PermissionProfileSnapshot::{legacy,active,
        # active_with_profile_workspace_roots,from_session_snapshot}.
        profile = PermissionProfile.workspace_write()
        legacy = PermissionProfileSnapshot.legacy(profile)
        self.assertEqual(legacy.permission_profile(), profile)
        self.assertIsNone(legacy.active_permission_profile())
        self.assertEqual(legacy.profile_workspace_roots(), ())

        active = PermissionProfileSnapshot.active(profile, ActivePermissionProfile(":workspace"))
        self.assertEqual(active.active_permission_profile(), ActivePermissionProfile(":workspace"))
        self.assertEqual(active.profile_workspace_roots(), ())

        active_with_roots = PermissionProfileSnapshot.active_with_profile_workspace_roots(
            profile,
            ActivePermissionProfile("workspace", extends=":workspace"),
            ["/repo", "/shared"],
        )
        self.assertEqual(active_with_roots.active_permission_profile(), ActivePermissionProfile("workspace", ":workspace"))
        self.assertEqual(active_with_roots.profile_workspace_roots(), (Path("/repo"), Path("/shared")))

        from_session = PermissionProfileSnapshot.from_session_snapshot(
            profile,
            ActivePermissionProfile("workspace", extends=":workspace"),
        )
        self.assertEqual(from_session.active_permission_profile(), ActivePermissionProfile("workspace", ":workspace"))
        self.assertEqual(
            from_session.profile_workspace_roots(),
            (),
            "Rust from_session_snapshot uses active(), so it does not reconstruct profile roots",
        )

    def test_permission_profile_state_enforces_permission_profile_constraint(self) -> None:
        # Rust source: codex-rs/core/src/config/resolved_permission_profile.rs
        # Rust methods: PermissionProfileState::from_constrained_* and setters.
        def managed_only(candidate: PermissionProfile) -> bool:
            return candidate.type == "managed"

        state = PermissionProfileState.from_constrained_active_profile(
            ConstrainedPermissionProfile(PermissionProfile.read_only(), managed_only),
            ActivePermissionProfile(":read-only"),
            ["/workspace"],
        )
        self.assertEqual(state.permission_profile(), PermissionProfile.read_only())
        self.assertEqual(state.active_permission_profile(), ActivePermissionProfile(":read-only"))
        self.assertEqual(state.profile_workspace_roots(), (Path("/workspace"),))

        state.can_set_legacy_permission_profile(PermissionProfile.workspace_write())
        state.set_permission_profile_snapshot(
            PermissionProfileSnapshot.active(
                PermissionProfile.workspace_write(network=NetworkSandboxPolicy.ENABLED),
                ActivePermissionProfile("dev", ":workspace"),
            )
        )
        self.assertEqual(state.active_permission_profile(), ActivePermissionProfile("dev", ":workspace"))

        with self.assertRaisesRegex(ValueError, "violates constraints"):
            state.can_set_legacy_permission_profile(PermissionProfile.disabled())
        with self.assertRaisesRegex(ValueError, "violates constraints"):
            state.set_permission_profile_snapshot(
                PermissionProfileSnapshot.active(
                    PermissionProfile.disabled(),
                    ActivePermissionProfile(":danger-full-access"),
                )
            )
        self.assertEqual(
            state.active_permission_profile(),
            ActivePermissionProfile("dev", ":workspace"),
            "failed updates should leave the previous resolved profile installed",
        )


if __name__ == "__main__":
    unittest.main()
