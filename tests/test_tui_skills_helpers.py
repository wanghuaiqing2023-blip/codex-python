# Parity source: codex-rs/tui/src/skills_helpers.rs

from pycodex.tui.skills_helpers import (
    SKILL_NAME_TRUNCATE_LEN,
    SkillInterfaceMetadata,
    SkillMetadata,
    match_skill,
    skill_description,
    skill_display_name,
    truncate_skill_name,
)


def test_skill_display_name_prefers_interface_display_name():
    skill = SkillMetadata(
        name="plugin:canonical",
        description="long",
        interface=SkillInterfaceMetadata(display_name="Friendly name"),
    )

    assert skill_display_name(skill) == "Friendly name"


def test_skill_display_name_preserves_empty_interface_display_name_like_rust():
    skill = SkillMetadata(
        name="plugin:canonical",
        description="long",
        interface=SkillInterfaceMetadata(display_name=""),
    )

    assert skill_display_name(skill) == ""


def test_skill_display_name_formats_plugin_qualified_name():
    skill = SkillMetadata(name="browser:open", description="long")

    assert skill_display_name(skill) == "open (browser)"


def test_skill_display_name_keeps_unqualified_or_empty_split_names():
    assert skill_display_name(SkillMetadata(name="plain", description="long")) == "plain"
    assert skill_display_name(SkillMetadata(name=":skill", description="long")) == ":skill"
    assert skill_display_name(SkillMetadata(name="plugin:", description="long")) == "plugin:"


def test_skill_description_precedence_matches_rust_options():
    assert skill_description(
        SkillMetadata(
            name="s",
            description="description",
            short_description="skill short",
            interface=SkillInterfaceMetadata(short_description="interface short"),
        )
    ) == "interface short"
    assert skill_description(
        SkillMetadata(name="s", description="description", short_description="skill short")
    ) == "skill short"
    assert skill_description(SkillMetadata(name="s", description="description")) == "description"


def test_skill_description_preserves_empty_some_values_like_rust():
    assert skill_description(
        SkillMetadata(
            name="s",
            description="description",
            short_description="skill short",
            interface=SkillInterfaceMetadata(short_description=""),
        )
    ) == ""
    assert skill_description(
        SkillMetadata(name="s", description="description", short_description="")
    ) == ""


def test_truncate_skill_name_uses_rust_constant():
    assert SKILL_NAME_TRUNCATE_LEN == 21
    assert truncate_skill_name("x" * 21) == "x" * 21
    assert truncate_skill_name("x" * 22) == "x" * 18 + "..."


def test_match_skill_returns_indices_for_display_name_match():
    result = match_skill("fn", "Friendly Name", "plugin:canonical")

    assert result is not None
    indices, score = result
    assert indices == [0, 9]
    assert isinstance(score, int)


def test_match_skill_uses_canonical_name_without_display_indices():
    result = match_skill("can", "Friendly Name", "plugin:canonical")

    assert result is not None
    indices, score = result
    assert indices is None
    assert isinstance(score, int)


def test_match_skill_does_not_try_canonical_when_names_are_equal():
    assert match_skill("z", "same", "same") is None


def test_helpers_accept_mapping_shaped_skill_metadata():
    skill = {
        "name": "plugin:skill",
        "description": "description",
        "short_description": "short",
        "interface": {"display_name": "Display", "short_description": "iface"},
    }

    assert skill_display_name(skill) == "Display"
    assert skill_description(skill) == "iface"
