from pycodex.models_manager.collaboration_mode_presets import (
    builtin_collaboration_mode_presets,
    default_mode_instructions,
    format_mode_names,
)
from pycodex.protocol import ModeKind, ReasoningEffort


def test_builtin_collaboration_mode_presets_match_rust_shape() -> None:
    # Rust crate/module: codex-models-manager::collaboration_mode_presets
    plan, default = builtin_collaboration_mode_presets()

    assert plan.name == ModeKind.PLAN.display_name()
    assert plan.mode is ModeKind.PLAN
    assert plan.model is None
    assert plan.reasoning_effort is ReasoningEffort.MEDIUM
    assert "request_user_input" in plan.developer_instructions

    assert default.name == ModeKind.DEFAULT.display_name()
    assert default.mode is ModeKind.DEFAULT
    assert default.model is None
    assert default.reasoning_effort is None
    assert "Known mode names are Default and Plan." in default.developer_instructions
    assert "{{KNOWN_MODE_NAMES}}" not in default.developer_instructions


def test_default_mode_instructions_renders_known_mode_names() -> None:
    # Rust test evidence: collaboration_mode_presets_tests.rs template rendering.
    text = default_mode_instructions()

    assert "Known mode names are Default and Plan." in text
    assert "{{KNOWN_MODE_NAMES}}" not in text


def test_format_mode_names_matches_rust_edge_cases() -> None:
    # Rust module private helper behavior used by default_mode_instructions.
    assert format_mode_names(()) == "none"
    assert format_mode_names((ModeKind.DEFAULT,)) == "Default"
    assert format_mode_names((ModeKind.DEFAULT, ModeKind.PLAN)) == "Default and Plan"
    assert (
        format_mode_names((ModeKind.DEFAULT, ModeKind.PLAN, ModeKind.EXECUTE))
        == "Default, Plan, Execute"
    )
