from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.config_lock import ConfigLockError, config_lockfile
from pycodex.core.session.config_lock import (
    export_config_lock_if_configured,
    session_configuration_to_lock_config_toml,
    to_config_lockfile_toml,
    validate_config_lock_if_configured,
)
from pycodex.features import Feature
from pycodex.protocol import ApprovalsReviewer, AskForApproval, ReasoningEffort, SessionSource


class FeatureSet:
    def __init__(self, enabled: set[Feature] | None = None) -> None:
        self._enabled = enabled or set()
        self.multi_agent_v2 = {
            "max_concurrent_threads_per_session": 4,
            "min_wait_timeout_ms": 10,
            "max_wait_timeout_ms": 100,
        }
        self.apps_mcp_path_override = {"path": "apps.json"}

    def enabled(self, feature: Feature) -> bool:
        return feature in self._enabled


class LayerStack:
    def __init__(self, config: dict[str, object]) -> None:
        self._config = config

    def effective_config(self) -> dict[str, object]:
        return dict(self._config)


@dataclass
class FakeConfig:
    config_layer_stack: LayerStack = field(
        default_factory=lambda: LayerStack(
            {
                "profile": "work",
                "profiles": {"work": {"model": "old"}},
                "debug": {"config_lockfile": {"path": "lock.toml"}, "keep": True},
                "model_instructions_file": "AGENTS.md",
                "sandbox_mode": "workspace-write",
            }
        )
    )
    config_lock_toml: object | None = None
    config_lock_allow_codex_version_mismatch: bool = False
    config_lock_export_dir: Path | None = None
    config_lock_save_fields_resolved_from_model_catalog: bool = True
    web_search_mode: str = "cached"
    model_provider_id: str = "openai"
    plan_mode_reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    model_verbosity: str = "low"
    include_permissions_instructions: bool = True
    include_apps_instructions: bool = False
    include_collaboration_mode_instructions: bool = True
    include_environment_context: bool = True
    background_terminal_max_timeout: int = 120000
    features: FeatureSet = field(default_factory=lambda: FeatureSet({Feature.GUARDIAN_APPROVAL}))
    memories: dict[str, object] = field(default_factory=lambda: {"enabled": True})
    multi_agent_v2: dict[str, object] = field(default_factory=dict)
    apps_mcp_path_override: str | None = "apps.json"
    agent_max_threads: int = 3
    agent_max_depth: int = 2
    agent_job_max_runtime_seconds: int = 60
    agent_interrupt_message_enabled: bool = True
    include_skill_instructions: bool = True


@dataclass
class FakeSessionConfiguration:
    original_config_do_not_use: FakeConfig
    session_source: SessionSource = field(default_factory=SessionSource.exec)
    collaboration_mode: object = field(
        default_factory=lambda: SimpleNamespace(
            settings=SimpleNamespace(model="gpt-5", reasoning_effort=ReasoningEffort.HIGH)
        )
    )
    model_reasoning_summary: str = "auto"
    service_tier: str = "flex"
    base_instructions: str = "resolved instructions"
    developer_instructions: str | None = "resolved developer instructions"
    compact_prompt: str | None = "resolved compact prompt"
    personality: str = "friendly"
    approval_policy: AskForApproval = AskForApproval.ON_REQUEST
    approvals_reviewer: ApprovalsReviewer = ApprovalsReviewer.USER


class SessionConfigLockTests(unittest.IsolatedAsyncioTestCase):
    def test_lock_contains_resolved_session_and_config_fields(self) -> None:
        # Rust source: codex-rs/core/src/session/config_lock.rs
        # Rust test: lock_contains_prompts_and_materializes_features.
        sc = FakeSessionConfiguration(FakeConfig())

        lock = session_configuration_to_lock_config_toml(sc)

        self.assertEqual(lock["model"], "gpt-5")
        self.assertEqual(lock["model_reasoning_effort"], "high")
        self.assertEqual(lock["model_reasoning_summary"], "auto")
        self.assertEqual(lock["service_tier"], "flex")
        self.assertEqual(lock["instructions"], "resolved instructions")
        self.assertEqual(lock["developer_instructions"], "resolved developer instructions")
        self.assertEqual(lock["compact_prompt"], "resolved compact prompt")
        self.assertEqual(lock["approval_policy"], "on-request")
        self.assertEqual(lock["approvals_reviewer"], "user")
        self.assertEqual(lock["web_search"], "cached")
        self.assertEqual(lock["model_provider"], "openai")
        self.assertEqual(lock["agents"]["max_threads"], 3)
        self.assertEqual(lock["agents"]["max_depth"], 2)
        self.assertEqual(lock["skills"]["include_instructions"], True)
        self.assertTrue(lock["features"]["guardian_approval"])
        self.assertIn("enabled", lock["features"]["multi_agent_v2"])
        self.assertNotIn("profile", lock)
        self.assertEqual(lock["profiles"], {})
        self.assertEqual(lock["debug"], {"keep": True})
        self.assertNotIn("model_instructions_file", lock)
        self.assertNotIn("sandbox_mode", lock)

    def test_lock_skips_session_resolved_fields_when_disabled(self) -> None:
        # Rust test: lock_skips_session_values_when_model_catalog_fields_are_not_saved.
        config = FakeConfig(config_lock_save_fields_resolved_from_model_catalog=False)
        sc = FakeSessionConfiguration(config)

        lock = session_configuration_to_lock_config_toml(sc)

        self.assertNotIn("model", lock)
        self.assertNotIn("model_reasoning_effort", lock)
        self.assertNotIn("model_reasoning_summary", lock)
        self.assertNotIn("service_tier", lock)
        self.assertNotIn("instructions", lock)
        self.assertNotIn("developer_instructions", lock)
        self.assertNotIn("compact_prompt", lock)
        self.assertNotIn("personality", lock)
        self.assertNotIn("approval_policy", lock)
        self.assertNotIn("approvals_reviewer", lock)

    async def test_validate_skips_non_root_agent_and_missing_lock(self) -> None:
        expected = config_lockfile({"model": "different"}, codex_version="old")
        config = FakeConfig(config_lock_toml=expected)
        sc = FakeSessionConfiguration(config, session_source=SessionSource.subagent(SimpleNamespace(type="review")))

        await validate_config_lock_if_configured(sc)
        await validate_config_lock_if_configured(FakeSessionConfiguration(FakeConfig(config_lock_toml=None)))

    async def test_validate_reports_config_diff_and_can_ignore_version_mismatch(self) -> None:
        sc = FakeSessionConfiguration(FakeConfig())
        actual = to_config_lockfile_toml(sc)
        drifted = config_lockfile({**actual.config, "model": "different"}, codex_version=actual.codex_version)
        sc.original_config_do_not_use.config_lock_toml = drifted

        with self.assertRaisesRegex(ConfigLockError, "config lock replay validation failed"):
            await validate_config_lock_if_configured(sc)

        sc.original_config_do_not_use.config_lock_toml = config_lockfile(actual.config, codex_version="older")
        with self.assertRaisesRegex(ConfigLockError, "Codex version mismatch"):
            await validate_config_lock_if_configured(sc)

        sc.original_config_do_not_use.config_lock_allow_codex_version_mismatch = True
        await validate_config_lock_if_configured(sc)

    async def test_export_writes_conversation_named_lockfile(self) -> None:
        # Rust source: export_config_lock_if_configured writes {ThreadId}.config.lock.toml.
        with tempfile.TemporaryDirectory() as tmpdir:
            config = FakeConfig(config_lock_export_dir=Path(tmpdir) / "locks")
            sc = FakeSessionConfiguration(config)

            path = await export_config_lock_if_configured(sc, "thread-123")

            assert path is not None
            self.assertEqual(path.name, "thread-123.config.lock.toml")
            text = path.read_text(encoding="utf-8")
            self.assertIn("version = 1", text)
            self.assertIn('[config]', text)
            self.assertIn('model = "gpt-5"', text)

    async def test_export_skips_when_unconfigured(self) -> None:
        self.assertIsNone(await export_config_lock_if_configured(FakeSessionConfiguration(FakeConfig()), "thread"))
        with self.assertRaisesRegex(TypeError, "conversation_id must be a string"):
            await export_config_lock_if_configured(FakeSessionConfiguration(FakeConfig()), 1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
