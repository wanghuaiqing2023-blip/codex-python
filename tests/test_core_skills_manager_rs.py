from pathlib import Path

import pytest

from pycodex.config import ConfigLayerEntry, ConfigLayerSource, ConfigLayerStack
from pycodex.core.skills import SkillsLoadInput
from pycodex.core_skills import SkillsManager
from pycodex.core_plugins import PluginSkillRoot


def _skill(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {name}\n---\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_skills_for_config_uses_layer_plugin_and_repo_roots(tmp_path: Path, monkeypatch) -> None:
    # Rust: codex-core-skills/src/manager_tests.rs and loader.rs::skill_roots.
    codex_home = tmp_path / "codex-home"
    home = tmp_path / "home"
    cwd = tmp_path / "repo" / "nested"
    cwd.mkdir(parents=True)
    (tmp_path / "repo" / ".git").mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    _skill(codex_home / "skills" / "user" / "SKILL.md", "user")
    _skill(tmp_path / "repo" / ".agents" / "skills" / "repo" / "SKILL.md", "repo")

    plugin_root = tmp_path / "plugin"
    _skill(plugin_root / "skills" / "search" / "SKILL.md", "search")
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name":"sample-plugin"}', encoding="utf-8")

    stack = ConfigLayerStack.new(
        (
            ConfigLayerEntry.new(ConfigLayerSource.user(codex_home / "config.toml"), {}),
        )
    )
    load_input = SkillsLoadInput(
        cwd=cwd,
        effective_skill_roots=(
            PluginSkillRoot(plugin_root / "skills", "sample@test", plugin_root),
        ),
        config_layer_stack=stack,
        bundled_skills_enabled=False,
    )

    outcome = await SkillsManager.new(codex_home, False).skills_for_config(load_input, True)

    assert {skill.name for skill in outcome.skills} == {
        "user",
        "repo",
        "sample-plugin:search",
    }
    assert all(skill.scope != "system" for skill in outcome.skills)


@pytest.mark.asyncio
async def test_repo_roots_require_executor_filesystem(tmp_path: Path) -> None:
    # Rust: codex-core-skills/src/loader.rs::repo_agents_skill_roots.
    cwd = tmp_path / "repo"
    _skill(cwd / ".agents" / "skills" / "repo" / "SKILL.md", "repo")
    stack = ConfigLayerStack.new(
        (ConfigLayerEntry.new(ConfigLayerSource.user(tmp_path / "config.toml"), {}),)
    )
    load_input = SkillsLoadInput(cwd, (), stack, False)

    outcome = await SkillsManager.new(tmp_path, False).skills_for_config(load_input, None)

    assert all(skill.name != "repo" for skill in outcome.skills)


@pytest.mark.asyncio
async def test_skill_name_uses_nearest_manifest_without_plugin_root_annotation(tmp_path: Path) -> None:
    # Rust: codex-core-skills::loader::namespaced_skill_name delegates every
    # canonical SKILL.md path to codex-utils-plugins manifest discovery.
    plugin_root = tmp_path / "plugin"
    _skill(plugin_root / "skills" / "search" / "SKILL.md", "search")
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name":"nearest-plugin"}', encoding="utf-8")
    stack = ConfigLayerStack.new(
        (ConfigLayerEntry.new(ConfigLayerSource.user(tmp_path / "config.toml"), {}),)
    )
    load_input = SkillsLoadInput(
        cwd=tmp_path,
        effective_skill_roots=(plugin_root / "skills",),
        config_layer_stack=stack,
        bundled_skills_enabled=False,
    )

    outcome = await SkillsManager.new(tmp_path / "home", False).skills_for_config(load_input, None)

    assert "nearest-plugin:search" in {skill.name for skill in outcome.skills}
