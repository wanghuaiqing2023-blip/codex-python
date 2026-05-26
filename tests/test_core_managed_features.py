import unittest

from pycodex.core import (
    ConstraintError,
    Feature,
    FeatureRequirementsToml,
    Features,
    FeaturesToml,
    ManagedFeatures,
    RequirementSource,
    Sourced,
    explicit_feature_settings_in_config,
    feature_requirements_display,
    normalize_candidate,
    parse_feature_requirements,
    validate_explicit_feature_settings_in_config_toml,
    validate_feature_requirements_for_config_toml,
    validate_feature_requirements_in_config_toml,
)


def sourced(entries: dict[str, bool]) -> Sourced[FeatureRequirementsToml]:
    return Sourced(
        FeatureRequirementsToml.from_entries(entries),
        RequirementSource.cloud_requirements(),
    )


class CoreManagedFeaturesTests(unittest.TestCase):
    def test_from_configured_normalizes_required_features(self) -> None:
        configured = Features.with_defaults()
        configured.disable(Feature.PERSONALITY)
        configured.enable(Feature.SHELL_TOOL)

        managed = ManagedFeatures.from_configured(
            configured,
            sourced({"personality": True, "shell_tool": False}),
        )

        self.assertTrue(managed.enabled(Feature.PERSONALITY))
        self.assertFalse(managed.enabled(Feature.SHELL_TOOL))

    def test_auto_review_requirement_maps_to_guardian_approval(self) -> None:
        managed = ManagedFeatures.from_configured(
            Features.with_defaults(),
            sourced({"auto_review": False}),
        )

        self.assertFalse(managed.enabled(Feature.GUARDIAN_APPROVAL))

    def test_runtime_mutations_are_normalized_to_requirements(self) -> None:
        managed = ManagedFeatures.from_configured(
            Features.with_defaults(),
            sourced({"personality": True, "shell_tool": False}),
        )
        requested = Features(managed.get().enabled_features(), managed.get().legacy_feature_usages())
        requested.disable(Feature.PERSONALITY)
        requested.enable(Feature.SHELL_TOOL)

        managed.can_set(requested)
        managed.set(requested)

        self.assertTrue(managed.enabled(Feature.PERSONALITY))
        self.assertFalse(managed.enabled(Feature.SHELL_TOOL))

    def test_impossible_requirements_raise_constraint_error_after_dependency_normalization(self) -> None:
        with self.assertRaises(ConstraintError) as caught:
            ManagedFeatures.from_configured(
                Features.with_defaults(),
                sourced({"code_mode": False, "code_mode_only": True}),
            )

        self.assertEqual(caught.exception.field_name, "features")
        self.assertEqual(caught.exception.candidate, "code_mode=true")
        self.assertEqual(
            caught.exception.allowed,
            "[code_mode=false, code_mode_only=true]",
        )
        self.assertIn("cloud requirements", str(caught.exception))

    def test_parse_feature_requirements_warns_for_legacy_alias_and_unknown_key(self) -> None:
        warnings: list[str] = []
        with self.assertLogs("pycodex.core.managed_features", level="WARNING"):
            parsed = parse_feature_requirements(
                FeatureRequirementsToml.from_entries({"collab": True, "made_up_feature": True}),
                RequirementSource.cloud_requirements(),
                warnings,
            )

        self.assertEqual(parsed, {Feature.COLLAB: True})
        self.assertTrue(
            any(
                "Using legacy `features` requirement `collab`" in warning
                and "prefer canonical feature key `multi_agent`" in warning
                for warning in warnings
            ),
            warnings,
        )
        self.assertTrue(
            any("Ignoring unknown `features` requirement `made_up_feature`" in warning for warning in warnings),
            warnings,
        )

    def test_feature_requirements_display_uses_feature_order_and_lowercase_bools(self) -> None:
        display = feature_requirements_display(
            {
                Feature.PERSONALITY: True,
                Feature.SHELL_TOOL: False,
            }
        )

        self.assertEqual(display, "[shell_tool=false, personality=true]")

    def test_explicit_feature_settings_collects_base_profile_and_legacy_toggle(self) -> None:
        cfg = {
            "features": {"personality": False},
            "experimental_use_unified_exec_tool": True,
            "profiles": {
                "work": {
                    "features": FeaturesToml.from_entries({"shell_tool": False}),
                    "experimental_use_unified_exec_tool": False,
                }
            },
        }

        self.assertEqual(
            explicit_feature_settings_in_config(cfg),
            [
                ("features.personality", Feature.PERSONALITY, False),
                ("experimental_use_unified_exec_tool", Feature.UNIFIED_EXEC, True),
                ("profiles.work.features.shell_tool", Feature.SHELL_TOOL, False),
                ("profiles.work.experimental_use_unified_exec_tool", Feature.UNIFIED_EXEC, False),
            ],
        )

    def test_validate_explicit_feature_settings_rejects_conflicting_config(self) -> None:
        cfg = {"features": {"personality": False}}

        with self.assertRaises(ConstraintError) as caught:
            validate_explicit_feature_settings_in_config_toml(cfg, sourced({"personality": True}))

        self.assertEqual(caught.exception.candidate, "features.personality=false")
        self.assertEqual(caught.exception.allowed, "[personality=true]")

    def test_validate_feature_requirements_normalizes_configured_values(self) -> None:
        cfg = {
            "features": {"personality": False, "shell_tool": True},
            "profiles": {
                "work": {
                    "features": {"personality": False, "shell_tool": True},
                }
            },
        }

        validate_feature_requirements_in_config_toml(
            cfg,
            sourced({"personality": True, "shell_tool": False}),
        )

    def test_validate_feature_requirements_prefixes_profile_errors(self) -> None:
        cfg = {
            "profiles": {
                "work": {
                    "features": {"code_mode_only": True},
                }
            }
        }

        with self.assertRaisesRegex(ValueError, "invalid feature configuration for profile `work`"):
            validate_feature_requirements_in_config_toml(
                cfg,
                sourced({"code_mode": False}),
            )

    def test_validate_feature_requirements_for_config_toml_runs_explicit_check_first(self) -> None:
        with self.assertRaises(ConstraintError) as caught:
            validate_feature_requirements_for_config_toml(
                {"features": {"personality": False}},
                sourced({"personality": True}),
            )

        self.assertEqual(caught.exception.candidate, "features.personality=false")

    def test_normalize_candidate_returns_independent_feature_set(self) -> None:
        original = Features.with_defaults()
        normalized = normalize_candidate(original, {Feature.SHELL_TOOL: False})

        self.assertTrue(original.enabled(Feature.SHELL_TOOL))
        self.assertFalse(normalized.enabled(Feature.SHELL_TOOL))


if __name__ == "__main__":
    unittest.main()
