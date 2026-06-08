from __future__ import annotations

import unittest
from types import SimpleNamespace

from pycodex.core import thread_manager
from pycodex.core.test_support import (
    all_model_presets,
    auth_manager_from_auth_with_home,
    builtin_collaboration_mode_presets,
    construct_model_info_offline,
    get_model_offline,
    set_deterministic_process_ids,
    set_thread_manager_test_mode,
    thread_manager_with_models_provider_home_and_state,
)
from pycodex.core.unified_exec import (
    UnifiedExecProcessManager,
    deterministic_process_ids_for_tests,
)
from pycodex.models_manager import ModelsManagerConfig
from pycodex.models_manager.test_support import construct_model_info_from_candidates
from pycodex.protocol import (
    ConfigShellToolType,
    ModelInfo,
    ModelVisibility,
    ModelsResponse,
    ModeKind,
    ReasoningEffort,
    ReasoningSummary,
    TruncationPolicyConfig,
)


def _model(slug: str, *, priority: int = 1, visibility: ModelVisibility = ModelVisibility.LIST) -> ModelInfo:
    return ModelInfo(
        slug=slug,
        display_name=slug,
        description=None,
        supported_reasoning_levels=(),
        shell_type=ConfigShellToolType.DEFAULT,
        visibility=visibility,
        supported_in_api=True,
        priority=priority,
        upgrade=None,
        base_instructions="base",
        model_messages=None,
        supports_reasoning_summaries=False,
        truncation_policy=TruncationPolicyConfig.bytes(10_000),
        supports_parallel_tool_calls=False,
        default_reasoning_summary=ReasoningSummary.AUTO,
    )


class CoreTestSupportTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_thread_manager_test_mode(False)
        set_deterministic_process_ids(True)

    def test_thread_manager_and_unified_exec_test_toggles_delegate(self) -> None:
        # Rust source: codex-core/src/test_support.rs delegates these two
        # helpers to thread_manager and unified_exec test-only switches.
        set_thread_manager_test_mode(True)
        self.assertTrue(thread_manager.should_use_test_thread_manager_behavior())

        set_deterministic_process_ids(False)
        self.assertFalse(deterministic_process_ids_for_tests())
        random_manager = UnifiedExecProcessManager()
        self.assertFalse(random_manager.deterministic_process_ids)

        set_deterministic_process_ids(True)
        deterministic_manager = UnifiedExecProcessManager()
        self.assertTrue(deterministic_manager.deterministic_process_ids)
        self.assertEqual(deterministic_manager.allocate_process_id(), 1000)

    def test_get_model_offline_uses_provided_model_or_first_picker_model(self) -> None:
        # Rust source: codex-models-manager/src/test_support.rs
        self.assertEqual(get_model_offline("custom-model"), "custom-model")
        self.assertEqual(get_model_offline(), all_model_presets()[0].model)
        self.assertTrue(all_model_presets()[0].is_default)
        self.assertTrue(all_model_presets()[0].show_in_picker)

    def test_construct_model_info_from_candidates_uses_longest_prefix_and_namespace_retry(self) -> None:
        # Rust source: construct_model_info_from_candidates in models-manager/src/manager.rs.
        short = _model("gpt-5")
        long = _model("gpt-5.2-codex")
        config = ModelsManagerConfig()

        exact = construct_model_info_from_candidates("gpt-5.2-codex-extra", [short, long], config)
        self.assertEqual(exact.slug, "gpt-5.2-codex-extra")
        self.assertEqual(exact.display_name, "gpt-5.2-codex")
        self.assertFalse(exact.used_fallback_model_metadata)

        namespaced = construct_model_info_from_candidates("provider/gpt-5.2-codex", [long], config)
        self.assertEqual(namespaced.slug, "provider/gpt-5.2-codex")
        self.assertEqual(namespaced.display_name, "gpt-5.2-codex")

        nested_namespace = construct_model_info_from_candidates("provider/nested/gpt-5.2-codex", [long], config)
        self.assertTrue(nested_namespace.used_fallback_model_metadata)

    def test_construct_model_info_offline_applies_config_overrides(self) -> None:
        base = _model("gpt-test")
        config = ModelsManagerConfig(
            model_catalog=ModelsResponse((base,)),
            model_context_window=1234,
            model_auto_compact_token_limit=1000,
            tool_output_token_limit=42,
            base_instructions="override",
            model_supports_reasoning_summaries=True,
        )

        info = construct_model_info_offline("gpt-test", config)
        self.assertEqual(info.context_window, 1234)
        self.assertEqual(info.auto_compact_token_limit_value, 1000)
        self.assertEqual(info.truncation_policy.limit, 42 * 4)
        self.assertEqual(info.base_instructions, "override")
        self.assertTrue(info.supports_reasoning_summaries)

    def test_construct_model_info_offline_accepts_config_converter(self) -> None:
        converted = ModelsManagerConfig(model_catalog=ModelsResponse((_model("gpt-test"),)))
        config = SimpleNamespace(to_models_manager_config=lambda: converted)
        self.assertEqual(construct_model_info_offline("gpt-test", config).display_name, "gpt-test")

    def test_builtin_collaboration_mode_presets_match_rust_shape(self) -> None:
        # Rust tests: collaboration_mode_presets_tests.rs.
        plan, default = builtin_collaboration_mode_presets()
        self.assertEqual(plan.name, ModeKind.PLAN.display_name())
        self.assertEqual(plan.mode, ModeKind.PLAN)
        self.assertIsNone(plan.model)
        self.assertEqual(plan.reasoning_effort, ReasoningEffort.MEDIUM)
        self.assertIn("request_user_input", plan.developer_instructions)

        self.assertEqual(default.name, ModeKind.DEFAULT.display_name())
        self.assertEqual(default.mode, ModeKind.DEFAULT)
        self.assertIsNone(default.model)
        self.assertIn("Known mode names are Default and Plan.", default.developer_instructions)
        self.assertNotIn("{{KNOWN_MODE_NAMES}}", default.developer_instructions)

    def test_core_test_support_constructors_preserve_test_handles(self) -> None:
        auth_manager = auth_manager_from_auth_with_home("auth", "home")
        manager = thread_manager_with_models_provider_home_and_state(
            "auth",
            "provider",
            "home",
            environment_manager="env",
            state_db="state",
        )
        self.assertEqual(auth_manager.auth, "auth")
        self.assertEqual(str(auth_manager.codex_home), "home")
        self.assertEqual(manager.environment_manager(), "env")
        self.assertEqual(manager.models_manager().provider, "provider")
        self.assertEqual(manager._state_db, "state")

    def test_core_package_reexports_test_support_helpers(self) -> None:
        # Rust source: codex-core/src/lib.rs exposes `pub mod test_support`.
        import pycodex.core as core

        self.assertIs(core.get_model_offline, get_model_offline)
        self.assertIs(core.all_model_presets, all_model_presets)
        self.assertIs(core.set_thread_manager_test_mode, set_thread_manager_test_mode)
        self.assertIs(core.set_deterministic_process_ids, set_deterministic_process_ids)


if __name__ == "__main__":
    unittest.main()
