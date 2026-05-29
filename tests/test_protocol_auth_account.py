import unittest

from pycodex.protocol import AccountPlanType, AuthPlanType, KnownPlan, ProviderAccount
from pycodex.protocol import RefreshTokenFailedError, RefreshTokenFailedReason


class ProtocolAuthAccountTests(unittest.TestCase):
    def test_auth_plan_type_deserializes_raw_aliases(self):
        self.assertEqual(AuthPlanType.from_raw_value("hc"), AuthPlanType.known_plan(KnownPlan.ENTERPRISE))
        self.assertEqual(AuthPlanType.from_raw_value("education"), AuthPlanType.known_plan(KnownPlan.EDU))
        self.assertEqual(AuthPlanType.from_raw_value("edu"), AuthPlanType.known_plan(KnownPlan.EDU))
        self.assertEqual(AuthPlanType.from_raw_value("mystery-tier"), AuthPlanType.unknown_plan("mystery-tier"))

    def test_auth_plan_type_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(ValueError, "exactly one variant"):
            AuthPlanType()
        with self.assertRaisesRegex(ValueError, "exactly one variant"):
            AuthPlanType(KnownPlan.PLUS, "plus")
        with self.assertRaisesRegex(TypeError, "known must be a KnownPlan"):
            AuthPlanType("plus")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "raw plan type must be a string"):
            AuthPlanType.from_raw_value(123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "plan must be a KnownPlan"):
            AuthPlanType.known_plan("plus")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "raw unknown plan must be a string"):
            AuthPlanType.unknown_plan(123)  # type: ignore[arg-type]

    def test_known_plan_display_raw_and_workspace_helpers(self):
        self.assertEqual(KnownPlan.PRO_LITE.display_name(), "Pro Lite")
        self.assertEqual(KnownPlan.SELF_SERVE_BUSINESS_USAGE_BASED.raw_value(), "self_serve_business_usage_based")
        self.assertTrue(KnownPlan.ENTERPRISE_CBP_USAGE_BASED.is_workspace_account())
        self.assertFalse(KnownPlan.PRO.is_workspace_account())

    def test_account_plan_wire_names_and_family_helpers(self):
        self.assertEqual(AccountPlanType.SELF_SERVE_BUSINESS_USAGE_BASED.to_json(), "self_serve_business_usage_based")
        self.assertEqual(AccountPlanType.ENTERPRISE_CBP_USAGE_BASED.to_json(), "enterprise_cbp_usage_based")
        self.assertEqual(AccountPlanType.PRO_LITE.to_json(), "prolite")

        self.assertTrue(AccountPlanType.TEAM.is_team_like())
        self.assertTrue(AccountPlanType.SELF_SERVE_BUSINESS_USAGE_BASED.is_team_like())
        self.assertFalse(AccountPlanType.BUSINESS.is_team_like())
        self.assertTrue(AccountPlanType.BUSINESS.is_business_like())
        self.assertTrue(AccountPlanType.ENTERPRISE_CBP_USAGE_BASED.is_business_like())
        self.assertFalse(AccountPlanType.TEAM.is_business_like())
        self.assertTrue(AccountPlanType.EDU.is_workspace_account())
        self.assertFalse(AccountPlanType.PRO.is_workspace_account())

    def test_auth_plan_type_converts_to_account_plan_type(self):
        self.assertIs(
            AccountPlanType.from_auth_plan_type(AuthPlanType.known_plan(KnownPlan.ENTERPRISE_CBP_USAGE_BASED)),
            AccountPlanType.ENTERPRISE_CBP_USAGE_BASED,
        )
        self.assertIs(
            AccountPlanType.from_auth_plan_type(AuthPlanType.known_plan(KnownPlan.ENTERPRISE)),
            AccountPlanType.ENTERPRISE,
        )
        self.assertIs(
            AccountPlanType.from_auth_plan_type(AuthPlanType.unknown_plan("mystery-tier")),
            AccountPlanType.UNKNOWN,
        )

    def test_account_plan_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "plan type must be a string"):
            AccountPlanType.parse(123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "plan_type must be an auth PlanType"):
            AccountPlanType.from_auth_plan_type("plus")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "plan must be a KnownPlan"):
            AccountPlanType.from_known_plan("plus")  # type: ignore[arg-type]

    def test_provider_account_shapes_match_upstream_variants(self):
        self.assertEqual(ProviderAccount.api_key(), ProviderAccount(kind="api_key"))
        self.assertEqual(
            ProviderAccount.chatgpt("user@example.com", AccountPlanType.PLUS),
            ProviderAccount(kind="chatgpt", email="user@example.com", plan_type=AccountPlanType.PLUS),
        )
        self.assertEqual(ProviderAccount.amazon_bedrock(), ProviderAccount(kind="amazon_bedrock"))

    def test_provider_account_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(ValueError, "unknown provider account kind"):
            ProviderAccount(kind="github")
        with self.assertRaisesRegex(ValueError, "api_key account cannot include"):
            ProviderAccount(kind="api_key", email="user@example.com")
        with self.assertRaisesRegex(ValueError, "amazon_bedrock account cannot include"):
            ProviderAccount(kind="amazon_bedrock", plan_type=AccountPlanType.PLUS)
        with self.assertRaisesRegex(TypeError, "chatgpt account email must be a string"):
            ProviderAccount(kind="chatgpt", email=None, plan_type=AccountPlanType.PLUS)
        with self.assertRaisesRegex(TypeError, "chatgpt account plan_type must be a PlanType"):
            ProviderAccount(kind="chatgpt", email="user@example.com", plan_type="plus")  # type: ignore[arg-type]

    def test_refresh_token_failed_error_carries_reason_and_message(self):
        err = RefreshTokenFailedError(RefreshTokenFailedReason.REVOKED, "token revoked")

        self.assertEqual(str(err), "token revoked")
        self.assertIs(err.reason, RefreshTokenFailedReason.REVOKED)
        self.assertEqual(err.message, "token revoked")

        with self.assertRaisesRegex(TypeError, "reason must be a RefreshTokenFailedReason"):
            RefreshTokenFailedError("revoked", "token revoked")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "message must be a string"):
            RefreshTokenFailedError(RefreshTokenFailedReason.REVOKED, 123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
