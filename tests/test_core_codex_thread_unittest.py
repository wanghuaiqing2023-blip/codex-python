import unittest
from types import SimpleNamespace

from pycodex.core.codex_thread import CodexThread, CodexThreadSettingsOverrides, SETTINGS_UNSET
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.protocol import CollaborationMode, ModeKind, ReasoningEffort, Settings, ThreadSettingsOverrides


class CodexThreadUnittestTests(unittest.IsolatedAsyncioTestCase):
    async def test_thread_settings_update_preserves_absent_effort(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            collaboration_mode=CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings(
                    model="gpt-current",
                    reasoning_effort=ReasoningEffort.HIGH,
                    developer_instructions="keep this",
                ),
            ),
        )
        thread = CodexThread(SimpleNamespace(session=session), session_configured={"model": "gpt-base"})

        update = await thread.thread_settings_update(CodexThreadSettingsOverrides())

        self.assertIs(update.service_tier, SETTINGS_UNSET)
        self.assertEqual(update.collaboration_mode.mode, ModeKind.DEFAULT)
        self.assertEqual(update.collaboration_mode.settings.model, "gpt-current")
        self.assertEqual(update.collaboration_mode.settings.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(update.collaboration_mode.settings.developer_instructions, "keep this")

    async def test_thread_settings_update_allows_explicit_effort_clear(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            collaboration_mode=CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings(
                    model="gpt-current",
                    reasoning_effort=ReasoningEffort.HIGH,
                    developer_instructions="keep this",
                ),
            ),
        )
        thread = CodexThread(SimpleNamespace(session=session), session_configured={"model": "gpt-base"})

        update = await thread.thread_settings_update(CodexThreadSettingsOverrides(effort=None))

        self.assertEqual(update.collaboration_mode.mode, ModeKind.DEFAULT)
        self.assertEqual(update.collaboration_mode.settings.model, "gpt-current")
        self.assertIsNone(update.collaboration_mode.settings.reasoning_effort)
        self.assertEqual(update.collaboration_mode.settings.developer_instructions, "keep this")

    def test_from_protocol_thread_settings_overrides_preserves_double_option_settings(self) -> None:
        omitted = CodexThreadSettingsOverrides.from_thread_settings_overrides(ThreadSettingsOverrides.default())
        explicit_null = CodexThreadSettingsOverrides.from_thread_settings_overrides(
            ThreadSettingsOverrides(effort=None, service_tier=None)
        )
        explicit_values = CodexThreadSettingsOverrides.from_thread_settings_overrides(
            ThreadSettingsOverrides(effort=ReasoningEffort.HIGH, service_tier="priority")
        )

        self.assertIs(omitted.effort, SETTINGS_UNSET)
        self.assertIs(omitted.service_tier, SETTINGS_UNSET)
        self.assertIsNone(explicit_null.effort)
        self.assertIsNone(explicit_null.service_tier)
        self.assertEqual(explicit_values.effort, ReasoningEffort.HIGH)
        self.assertEqual(explicit_values.service_tier, "priority")


if __name__ == "__main__":
    unittest.main()

