from __future__ import annotations

from types import SimpleNamespace
import unittest

from pycodex.core import usage_hint_text as root_usage_hint_text
from pycodex.core.session import usage_hint_text
from pycodex.features import Feature, Features, MultiAgentV2ConfigToml
from pycodex.protocol import InternalSessionSource, SessionSource, SubAgentSource, ThreadId


class SessionMultiAgentsTests(unittest.TestCase):
    def _turn_context(self, *, enabled: bool = True) -> SimpleNamespace:
        features = Features()
        features.set_enabled(Feature.MULTI_AGENT_V2, enabled)
        return SimpleNamespace(
            features=features,
            config=SimpleNamespace(
                multi_agent_v2=MultiAgentV2ConfigToml(
                    root_agent_usage_hint_text="Root hint",
                    subagent_usage_hint_text="Subagent hint",
                )
            ),
        )

    def test_usage_hint_text_requires_multi_agent_v2_feature(self) -> None:
        # Rust source: codex-core/src/session/multi_agents.rs usage_hint_text feature gate.
        self.assertIsNone(usage_hint_text(self._turn_context(enabled=False), SessionSource.cli()))

    def test_usage_hint_text_returns_root_hint_for_root_sources(self) -> None:
        # Rust source: codex-core/src/session/multi_agents.rs root SessionSource arms.
        ctx = self._turn_context()
        for source in (
            SessionSource.cli(),
            SessionSource.vscode(),
            SessionSource.exec(),
            SessionSource.mcp(),
            SessionSource.custom_source("desktop"),
            SessionSource.unknown(),
        ):
            with self.subTest(source=source):
                self.assertEqual(usage_hint_text(ctx, source), "Root hint")

    def test_usage_hint_text_returns_subagent_hint_only_for_thread_spawn(self) -> None:
        # Rust source: codex-core/src/session/multi_agents.rs subagent ThreadSpawn arm.
        ctx = self._turn_context()
        thread_spawn = SessionSource.subagent(SubAgentSource.thread_spawn(ThreadId.new(), 1))

        self.assertEqual(usage_hint_text(ctx, thread_spawn), "Subagent hint")
        self.assertIsNone(usage_hint_text(ctx, SessionSource.subagent(SubAgentSource.review())))
        self.assertIsNone(usage_hint_text(ctx, SessionSource.internal(InternalSessionSource.MEMORY_CONSOLIDATION)))

    def test_core_root_reexports_usage_hint_text(self) -> None:
        # Rust source: codex-core/src/session/multi_agents.rs helper is used from session-level code.
        self.assertIs(root_usage_hint_text, usage_hint_text)


if __name__ == "__main__":
    unittest.main()
