import unittest
from pathlib import Path

from pycodex.protocol.models import AdditionalPermissionProfile, NetworkPermissions
from pycodex.protocol.request_permissions import (
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsEvent,
    RequestPermissionsResponse,
    permissions_request_approval_response,
)


class ProtocolRequestPermissionsTests(unittest.TestCase):
    # Rust source:
    # codex/codex-rs/protocol/src/request_permissions.rs

    def test_permission_grant_scope_matches_snake_case_default(self) -> None:
        # Rust behavior source: PermissionGrantScope derives Default and serde(rename_all = "snake_case").
        self.assertEqual(PermissionGrantScope.default(), PermissionGrantScope.TURN)
        self.assertEqual(PermissionGrantScope.TURN.value, "turn")
        self.assertEqual(PermissionGrantScope.SESSION.value, "session")

    def test_request_permission_profile_empty_and_conversion_contract(self) -> None:
        # Rust behavior source: RequestPermissionProfile::is_empty and From conversions
        # to/from AdditionalPermissionProfile.
        empty = RequestPermissionProfile()
        self.assertTrue(empty.is_empty())

        profile = RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertFalse(profile.is_empty())

        additional = profile.to_additional_permission_profile()
        self.assertEqual(
            additional,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )
        self.assertEqual(
            RequestPermissionProfile.from_additional_permission_profile(additional),
            profile,
        )

    def test_request_permission_profile_denies_unknown_fields(self) -> None:
        # Rust behavior source: #[serde(deny_unknown_fields)] on RequestPermissionProfile.
        with self.assertRaisesRegex(ValueError, "unknown field"):
            RequestPermissionProfile.from_mapping(
                {"network": {"enabled": True}, "unexpected": True}
            )

    def test_request_permissions_args_skips_none_reason(self) -> None:
        # Rust behavior source: RequestPermissionsArgs.reason has skip_serializing_if Option::is_none.
        profile = RequestPermissionProfile(network=NetworkPermissions(enabled=True))

        self.assertEqual(
            RequestPermissionsArgs(profile).to_mapping(),
            {"permissions": {"network": {"enabled": True}}},
        )
        self.assertEqual(
            RequestPermissionsArgs(profile, reason="Need network").to_mapping(),
            {
                "permissions": {"network": {"enabled": True}},
                "reason": "Need network",
            },
        )

    def test_request_permissions_response_defaults_and_strict_auto_review_skip(self) -> None:
        # Rust behavior source: RequestPermissionsResponse.scope default Turn and
        # strict_auto_review default false with skip_serializing_if false.
        profile = RequestPermissionProfile(network=NetworkPermissions(enabled=True))

        from_missing_scope = RequestPermissionsResponse.from_mapping(
            {"permissions": {"network": {"enabled": True}}}
        )
        self.assertEqual(from_missing_scope.scope, PermissionGrantScope.TURN)
        self.assertFalse(from_missing_scope.strict_auto_review)
        self.assertEqual(
            from_missing_scope.to_mapping(),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
            },
        )

        strict = RequestPermissionsResponse(
            profile,
            scope=PermissionGrantScope.SESSION,
            strict_auto_review=True,
        )
        self.assertEqual(
            strict.to_mapping(),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
                "strict_auto_review": True,
            },
        )

    def test_request_permissions_event_defaults_and_optional_fields(self) -> None:
        # Rust behavior source: RequestPermissionsEvent.turn_id has serde(default),
        # reason/cwd skip when None.
        event = RequestPermissionsEvent.from_mapping(
            {
                "call_id": "call-1",
                "started_at_ms": 123,
                "permissions": {"network": {"enabled": True}},
            }
        )
        self.assertEqual(event.turn_id, "")
        self.assertIsNone(event.reason)
        self.assertIsNone(event.cwd)
        self.assertEqual(
            event.to_mapping(),
            {
                "call_id": "call-1",
                "turn_id": "",
                "started_at_ms": 123,
                "permissions": {"network": {"enabled": True}},
            },
        )

        with_cwd = RequestPermissionsEvent.from_mapping(
            {
                "call_id": "call-2",
                "turn_id": "turn-2",
                "started_at_ms": 456,
                "reason": "Need workspace",
                "permissions": {"network": {"enabled": True}},
                "cwd": str(Path.cwd()),
            }
        )
        self.assertEqual(with_cwd.cwd, Path.cwd())
        self.assertEqual(with_cwd.to_mapping()["cwd"], str(Path.cwd()))

    def test_request_permissions_event_started_at_ms_is_i64(self) -> None:
        # Rust behavior source: started_at_ms is i64.
        with self.assertRaisesRegex(ValueError, "started_at_ms must fit in i64"):
            RequestPermissionsEvent.from_mapping(
                {
                    "call_id": "call-1",
                    "started_at_ms": 2**63,
                    "permissions": {},
                }
            )

    def test_app_server_response_uses_camel_case_compatibility_surface(self) -> None:
        # Python compatibility surface for app-server/client protocol v2 while preserving
        # the Rust request_permissions response contract internally.
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
            strict_auto_review=True,
        )

        self.assertEqual(
            permissions_request_approval_response(response),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
                "strictAutoReview": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
