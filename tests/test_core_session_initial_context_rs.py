from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.core.state.service import SessionServices
from pycodex.core_skills import SkillLoadOutcome, SkillMetadata
from pycodex.extension_api import ExtensionRegistryBuilder, PromptFragment


class _SkillsManager:
    def __init__(self, outcome: SkillLoadOutcome) -> None:
        self.outcome = outcome
        self.inputs = []

    async def skills_for_config(self, load_input, fs):
        self.inputs.append((load_input, fs))
        return self.outcome


class _PluginOutcome:
    def capability_summaries(self):
        return (
            SimpleNamespace(
                config_name="demo@local",
                display_name="Demo plugin",
                description="Plugin capability",
                has_skills=False,
                mcp_server_names=(),
                app_connector_ids=(),
            ),
        )

    def effective_plugin_skill_roots(self):
        return ()


class _PluginsManager:
    def __init__(self) -> None:
        self.inputs = []

    async def plugins_for_config(self, config):
        self.inputs.append(config)
        return _PluginOutcome()


class _ContextContributor:
    async def contribute(self, session_store, thread_store):
        assert session_store.level_id()
        assert thread_store.level_id()
        return [
            PromptFragment.developer_capability("extension capability"),
            PromptFragment.separate_developer("separate extension policy"),
            PromptFragment.contextual_user("extension user context"),
        ]


class InitialContextRustParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_context_uses_session_managers_and_rust_message_order(self) -> None:
        # Rust: codex-core::session::Session::build_initial_context appends
        # skills/plugins/context contributors before emitting developer,
        # separate-developer, then contextual-user messages.
        skill_path = Path("C:/skills/demo/SKILL.md")
        skills = SkillLoadOutcome(
            skills=(SkillMetadata("demo", "Demo skill", path_to_skills_md=skill_path),),
            skill_roots=(skill_path.parent.parent,),
            skill_root_by_path={skill_path: skill_path.parent.parent},
        )
        builder = ExtensionRegistryBuilder.new()
        builder.prompt_contributor(_ContextContributor())
        services = SessionServices(
            extensions=builder.build(),
            skills_manager=_SkillsManager(skills),
            plugins_manager=_PluginsManager(),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            services=services,
            user_instructions="workspace rules",
            model_info=SimpleNamespace(slug="gpt-test", context_window=128_000),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        self.assertEqual([item.role for item in session.history], ["developer", "developer", "user"])
        developer_text = "\n".join(content.text for content in session.history[0].content)
        self.assertIn("Demo skill", developer_text)
        self.assertIn("Demo plugin", developer_text)
        self.assertIn("extension capability", developer_text)
        self.assertIn("separate extension policy", session.history[1].content[0].text)
        contextual_text = "\n".join(content.text for content in session.history[2].content)
        self.assertIn("workspace rules", contextual_text)
        self.assertIn("extension user context", contextual_text)
        self.assertEqual(len(services.skills_manager.inputs), 1)
        self.assertGreaterEqual(len(services.plugins_manager.inputs), 1)


if __name__ == "__main__":
    unittest.main()
