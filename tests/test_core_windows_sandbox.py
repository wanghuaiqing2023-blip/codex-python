import unittest
from types import SimpleNamespace

from pycodex.core.features import Feature, Features, FeaturesToml
from pycodex.core.windows_sandbox import (
    ConfigToml,
    WindowsSandboxModeToml,
    WindowsSandboxSetupMode,
    WindowsToml,
    legacy_windows_sandbox_mode_from_entries,
    resolve_windows_sandbox_mode,
    resolve_windows_sandbox_private_desktop,
    sandbox_setup_is_complete,
    windows_sandbox_level_from_config,
    windows_sandbox_level_from_features,
    windows_sandbox_setup_mode_tag,
)
from pycodex.protocol import WindowsSandboxLevel


class WindowsSandboxTests(unittest.TestCase):
    def test_windows_sandbox_level_from_features_matches_flag_priority(self) -> None:
        features = Features.with_defaults()
        self.assertEqual(windows_sandbox_level_from_features(features), WindowsSandboxLevel.DISABLED)

        features = Features.with_defaults().enable(Feature.WINDOWS_SANDBOX)
        self.assertEqual(windows_sandbox_level_from_features(features), WindowsSandboxLevel.RESTRICTED_TOKEN)

        features.enable(Feature.WINDOWS_SANDBOX_ELEVATED)
        self.assertEqual(windows_sandbox_level_from_features(features), WindowsSandboxLevel.ELEVATED)

    def test_windows_sandbox_level_from_config_prefers_explicit_mode(self) -> None:
        config = SimpleNamespace(
            permissions=SimpleNamespace(windows_sandbox_mode=WindowsSandboxModeToml.UNELEVATED),
            features=Features.with_defaults().enable(Feature.WINDOWS_SANDBOX_ELEVATED),
        )

        self.assertEqual(windows_sandbox_level_from_config(config), WindowsSandboxLevel.RESTRICTED_TOKEN)

    def test_legacy_mode_prefers_elevated_and_supports_alias(self) -> None:
        self.assertEqual(
            legacy_windows_sandbox_mode_from_entries(
                {
                    "experimental_windows_sandbox": True,
                    "elevated_windows_sandbox": True,
                }
            ),
            WindowsSandboxModeToml.ELEVATED,
        )
        self.assertEqual(
            legacy_windows_sandbox_mode_from_entries({"enable_experimental_windows_sandbox": True}),
            WindowsSandboxModeToml.UNELEVATED,
        )

    def test_resolve_windows_sandbox_mode_falls_back_to_legacy_keys(self) -> None:
        cfg = ConfigToml(features=FeaturesToml.from_entries({"experimental_windows_sandbox": True}))

        self.assertEqual(resolve_windows_sandbox_mode(cfg), WindowsSandboxModeToml.UNELEVATED)

    def test_resolve_windows_sandbox_mode_prefers_windows_table(self) -> None:
        cfg = ConfigToml(
            windows=WindowsToml(sandbox=WindowsSandboxModeToml.ELEVATED),
            features=FeaturesToml.from_entries({"experimental_windows_sandbox": True}),
        )

        self.assertEqual(resolve_windows_sandbox_mode(cfg), WindowsSandboxModeToml.ELEVATED)

    def test_resolve_windows_sandbox_private_desktop_defaults_to_true(self) -> None:
        self.assertTrue(resolve_windows_sandbox_private_desktop(ConfigToml()))
        self.assertFalse(
            resolve_windows_sandbox_private_desktop(
                ConfigToml(windows=WindowsToml(sandbox_private_desktop=False))
            )
        )

    def test_setup_mode_tag_and_non_windows_setup_probe(self) -> None:
        self.assertEqual(windows_sandbox_setup_mode_tag(WindowsSandboxSetupMode.ELEVATED), "elevated")
        self.assertEqual(windows_sandbox_setup_mode_tag("unelevated"), "unelevated")
        self.assertFalse(sandbox_setup_is_complete("C:/Users/example/.codex"))


if __name__ == "__main__":
    unittest.main()
