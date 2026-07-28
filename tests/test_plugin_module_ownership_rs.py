from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.plugin import (
    LoadedPlugin,
    PluginId,
    PluginIdError,
    PluginLoadOutcome,
    prompt_safe_plugin_description,
    validate_plugin_segment,
)


def test_plugin_id_items_are_owned_by_rust_plugin_id_module() -> None:
    # Rust: codex-plugin/src/plugin_id.rs owns these items; lib.rs re-exports them.
    assert PluginId.__module__ == "pycodex.plugin.plugin_id"
    assert PluginIdError.__module__ == "pycodex.plugin.plugin_id"
    assert validate_plugin_segment.__module__ == "pycodex.plugin.plugin_id"


def test_load_outcome_items_are_owned_by_rust_load_outcome_module() -> None:
    # Rust: codex-plugin/src/load_outcome.rs owns these items; lib.rs re-exports them.
    assert LoadedPlugin.__module__ == "pycodex.plugin.load_outcome"
    assert PluginLoadOutcome.__module__ == "pycodex.plugin.load_outcome"
    assert prompt_safe_plugin_description.__module__ == "pycodex.plugin.load_outcome"


def test_plugin_id_parse_requires_rust_key_shape_and_uses_last_at() -> None:
    plugin_id = PluginId.parse("sample@openai-curated")
    assert plugin_id.plugin_name == "sample"
    assert plugin_id.marketplace_name == "openai-curated"
    assert plugin_id.as_key() == "sample@openai-curated"

    with pytest.raises(
        PluginIdError,
        match=r"^invalid plugin key `sample`; expected <plugin>@<marketplace>$",
    ):
        PluginId.parse("sample")

    with pytest.raises(
        PluginIdError,
        match=r"^invalid plugin name: only ASCII letters, digits, `_`, and `-` are allowed in `sample@nested@market`$",
    ):
        PluginId.parse("sample@nested@market")


@pytest.mark.parametrize("segment", ["a.b", "a/b", "space value", "中文"])
def test_validate_plugin_segment_matches_rust_character_set(segment: str) -> None:
    with pytest.raises(
        PluginIdError,
        match=r"only ASCII letters, digits, `_`, and `-` are allowed",
    ):
        validate_plugin_segment(segment, "plugin name")


def test_effective_plugin_skill_roots_preserves_first_plugin_for_shared_root(
    tmp_path: Path,
) -> None:
    # Rust: load_outcome::tests::effective_plugin_skill_roots_preserves_first_plugin_for_shared_root.
    shared = (tmp_path / "shared").resolve()
    first_root = (tmp_path / "zeta").resolve()
    second_root = (tmp_path / "alpha").resolve()
    outcome = PluginLoadOutcome.from_plugins(
        [
            LoadedPlugin(
                config_name="zeta@test",
                root=first_root,
                skill_roots=(shared,),
                has_enabled_skills=True,
            ),
            LoadedPlugin(
                config_name="alpha@test",
                root=second_root,
                skill_roots=(shared,),
                has_enabled_skills=True,
            ),
        ]
    )

    roots = outcome.effective_plugin_skill_roots()
    assert len(roots) == 1
    assert roots[0].path == shared
    assert roots[0].plugin_id == "zeta@test"
    assert roots[0].plugin_root == first_root

