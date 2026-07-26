"""Rust-derived ownership checks for ``codex-core::context`` modules."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_ROOT = REPO_ROOT / "pycodex" / "core" / "context"

RUST_CONTEXT_OWNERS = {
    "approved_command_prefix_saved": "ApprovedCommandPrefixSaved",
    "apps_instructions": "AppsInstructions",
    "available_plugins_instructions": "AvailablePluginsInstructions",
    "available_skills_instructions": "AvailableSkillsInstructions",
    "collaboration_mode_instructions": "CollaborationModeInstructions",
    "guardian_followup_review_reminder": "GuardianFollowupReviewReminder",
    "hook_additional_context": "HookAdditionalContext",
    "image_generation_instructions": "ImageGenerationInstructions",
    "legacy_apply_patch_exec_command_warning": "LegacyApplyPatchExecCommandWarning",
    "legacy_model_mismatch_warning": "LegacyModelMismatchWarning",
    "legacy_unified_exec_process_limit_warning": "LegacyUnifiedExecProcessLimitWarning",
    "model_switch_instructions": "ModelSwitchInstructions",
    "network_rule_saved": "NetworkRuleSaved",
    "personality_spec_instructions": "PersonalitySpecInstructions",
    "plugin_instructions": "PluginInstructions",
    "realtime_start_with_instructions": "RealtimeStartWithInstructions",
    "skill_instructions": "SkillInstructions",
    "subagent_notification": "SubagentNotification",
    "turn_aborted": "TurnAborted",
    "user_instructions": "UserInstructions",
    "user_shell_command": "UserShellCommand",
}


def _defined_classes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


class CoreContextModuleOwnershipTests(unittest.TestCase):
    def test_rust_context_types_are_defined_by_their_coordinate_module(self) -> None:
        for module_name, type_name in RUST_CONTEXT_OWNERS.items():
            with self.subTest(module=module_name):
                owner = CONTEXT_ROOT / f"{module_name}.py"
                self.assertTrue(owner.is_file(), f"missing Python owner for context::{module_name}")
                self.assertIn(type_name, _defined_classes(owner))

    def test_context_parent_only_reexports_child_types(self) -> None:
        parent_definitions = _defined_classes(CONTEXT_ROOT / "__init__.py")
        self.assertEqual(
            parent_definitions.intersection(RUST_CONTEXT_OWNERS.values()),
            set(),
        )

    def test_plugin_summary_uses_the_codex_plugin_owner(self) -> None:
        from pycodex.core import plugins
        from pycodex.plugin import PluginCapabilitySummary

        self.assertIs(plugins.PluginCapabilitySummary, PluginCapabilitySummary)
        self.assertNotIn(
            "PluginCapabilitySummary",
            _defined_classes(CONTEXT_ROOT / "__init__.py"),
        )


if __name__ == "__main__":
    unittest.main()
