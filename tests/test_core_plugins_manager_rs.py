from pathlib import Path

import pytest

from pycodex.config import ConfigLayerEntry, ConfigLayerSource, ConfigLayerStack
from pycodex.core_plugins import PluginsConfigInput, PluginsManager


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.asyncio
async def test_plugins_for_config_loads_manifest_paths_and_effective_capabilities(tmp_path: Path) -> None:
    # Rust: codex-core-plugins/src/manager_tests.rs
    # `load_plugins_loads_default_skills_and_mcp_servers` and
    # `effective_apps_dedupes_connector_ids_across_plugins`.
    codex_home = tmp_path / "codex-home"
    plugin_root = codex_home / "plugins" / "cache" / "test" / "sample" / "v1"
    _write(
        plugin_root / ".codex-plugin" / "plugin.json",
        """{
  "name": "sample-plugin",
  "description": "  Plugin   capability summary  ",
  "skills": "./extra-skills",
  "mcpServers": "./config/custom.mcp.json",
  "apps": "./config/custom.app.json",
  "interface": {"displayName": "Sample Plugin"}
}""",
    )
    _write(plugin_root / "skills" / "default" / "SKILL.md", "---\nname: default\ndescription: default\n---\n")
    _write(plugin_root / "extra-skills" / "extra" / "SKILL.md", "---\nname: extra\ndescription: extra\n---\n")
    _write(
        plugin_root / "config" / "custom.mcp.json",
        '{"mcpServers":{"docs":{"type":"http","url":"https://example.test/mcp"}}}',
    )
    _write(
        plugin_root / "config" / "custom.app.json",
        '{"apps":{"calendar":{"id":"connector_calendar"},"duplicate":{"id":"connector_calendar"}}}',
    )
    stack = ConfigLayerStack.new(
        (
            ConfigLayerEntry.new(
                ConfigLayerSource.user(codex_home / "config.toml"),
                {"plugins": {"sample@test": {"enabled": True}}},
            ),
        )
    )

    outcome = await PluginsManager.new(codex_home).plugins_for_config(
        PluginsConfigInput.new(stack, True, False, "https://chatgpt.com/backend-api/")
    )

    plugin = outcome.plugins()[0]
    assert plugin.is_active()
    assert plugin.manifest_name == "Sample Plugin"
    assert outcome.effective_skill_roots() == tuple(
        sorted((plugin_root / "extra-skills", plugin_root / "skills"), key=str)
    )
    assert tuple(outcome.effective_mcp_servers()) == ("docs",)
    assert outcome.effective_apps() == ("connector_calendar",)
    assert outcome.capability_summaries()[0].description == "Plugin capability summary"


@pytest.mark.asyncio
async def test_plugins_feature_gate_returns_empty_outcome(tmp_path: Path) -> None:
    # Rust: codex-core-plugins/src/manager.rs
    # `plugins_for_config_with_force_reload` returns default when the feature is disabled.
    stack = ConfigLayerStack.new(
        (
            ConfigLayerEntry.new(
                ConfigLayerSource.user(tmp_path / "config.toml"),
                {"plugins": {"sample@test": {"enabled": True}}},
            ),
        )
    )
    outcome = await PluginsManager.new(tmp_path).plugins_for_config(
        PluginsConfigInput.new(stack, False, False, "https://chatgpt.com/backend-api/")
    )
    assert outcome.plugins() == ()
    assert outcome.capability_summaries() == ()
