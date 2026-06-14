
"""Parity tests for Rust core/tests/suite/personality.rs.

The Rust suite drives these through a mock Codex session and Responses API.  The
Python port exercises the same visible contract at the stable model/context
boundaries: model instructions template selection and turn-level developer
``<personality_spec>`` updates.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from pycodex.core.context import PersonalitySpecInstructions
from pycodex.core.context_manager.updates import build_personality_update_item
from pycodex.models_manager import ModelsManagerConfig
from pycodex.models_manager.test_support import (
    LOCAL_FRIENDLY_TEMPLATE,
    LOCAL_PRAGMATIC_TEMPLATE,
    construct_model_info_offline_for_tests,
    model_info_from_slug,
)
from pycodex.protocol import ModelInstructionsVariables, ModelMessages, Personality


REMOTE_FRIENDLY = "Friendly from remote template"
REMOTE_PRAGMATIC = "Pragmatic from remote template"
REMOTE_DEFAULT = "Default from remote template"


def _personality_config(*, enabled: bool = True, base_instructions: str | None = None) -> ModelsManagerConfig:
    return ModelsManagerConfig(personality_enabled=enabled, base_instructions=base_instructions)


def _local_personality_model(slug: str = "exp-codex-personality"):
    return construct_model_info_offline_for_tests(slug, _personality_config(enabled=True))


def _remote_model(*, default: str | None = REMOTE_DEFAULT):
    base = model_info_from_slug("remote-personality")
    return replace(
        base,
        model_messages=ModelMessages(
            instructions_template="Base instructions\n{{ personality }}\n",
            instructions_variables=ModelInstructionsVariables(
                personality_default=default,
                personality_friendly=REMOTE_FRIENDLY,
                personality_pragmatic=REMOTE_PRAGMATIC,
            ),
        ),
    )


def _developer_update(previous_personality, next_personality, model_info=None, *, enabled: bool = True) -> str | None:
    model_info = model_info or _local_personality_model()
    previous = SimpleNamespace(model=model_info.slug, personality=previous_personality)
    next_context = SimpleNamespace(model_info=model_info, personality=next_personality)
    return build_personality_update_item(previous, next_context, enabled)


def test_personality_does_not_mutate_base_instructions_without_template() -> None:
    """Rust test: personality_does_not_mutate_base_instructions_without_template."""

    model_info = construct_model_info_offline_for_tests("gpt-5.4", _personality_config(enabled=True))

    assert model_info.model_messages is None
    assert model_info.get_model_instructions(Personality.FRIENDLY) == model_info.base_instructions


def test_base_instructions_override_disables_personality_template() -> None:
    """Rust test: base_instructions_override_disables_personality_template."""

    model_info = construct_model_info_offline_for_tests(
        "exp-codex-personality",
        _personality_config(enabled=True, base_instructions="override instructions"),
    )

    assert model_info.base_instructions == "override instructions"
    assert model_info.model_messages is None
    assert model_info.get_model_instructions(Personality.FRIENDLY) == "override instructions"


def test_user_turn_personality_none_does_not_add_update_message() -> None:
    """Rust test: user_turn_personality_none_does_not_add_update_message."""

    assert _developer_update(None, None) is None
    assert _developer_update(Personality.FRIENDLY, Personality.NONE) is None


def test_config_personality_some_sets_instructions_template() -> None:
    """Rust test: config_personality_some_sets_instructions_template."""

    model_info = _local_personality_model()
    instructions = model_info.get_model_instructions(Personality.FRIENDLY)

    assert LOCAL_FRIENDLY_TEMPLATE in instructions
    assert "<personality_spec>" not in instructions


def test_config_personality_none_sends_no_personality() -> None:
    """Rust test: config_personality_none_sends_no_personality."""

    model_info = _local_personality_model()
    instructions = model_info.get_model_instructions(Personality.NONE)

    assert LOCAL_FRIENDLY_TEMPLATE not in instructions
    assert LOCAL_PRAGMATIC_TEMPLATE not in instructions
    assert "{{ personality }}" not in instructions
    assert _developer_update(None, Personality.NONE) is None


def test_default_personality_is_pragmatic_without_config_toml() -> None:
    """Rust test: default_personality_is_pragmatic_without_config_toml."""

    model_info = _local_personality_model()
    instructions = model_info.get_model_instructions(Personality.PRAGMATIC)

    assert LOCAL_PRAGMATIC_TEMPLATE in instructions


def test_user_turn_personality_some_adds_update_message() -> None:
    """Rust test: user_turn_personality_some_adds_update_message."""

    update = _developer_update(None, Personality.FRIENDLY)

    assert update is not None
    assert "<personality_spec>" in update
    assert "The user has requested a new communication style." in update
    assert LOCAL_FRIENDLY_TEMPLATE in update


def test_user_turn_personality_same_value_does_not_add_update_message() -> None:
    """Rust test: user_turn_personality_same_value_does_not_add_update_message."""

    assert _developer_update(Personality.PRAGMATIC, Personality.PRAGMATIC) is None


def test_instructions_uses_base_if_feature_disabled() -> None:
    """Rust test: instructions_uses_base_if_feature_disabled."""

    model_info = construct_model_info_offline_for_tests(
        "exp-codex-personality",
        _personality_config(enabled=False),
    )

    assert model_info.model_messages is None
    assert model_info.get_model_instructions(Personality.FRIENDLY) == model_info.base_instructions


def test_user_turn_personality_skips_if_feature_disabled() -> None:
    """Rust test: user_turn_personality_skips_if_feature_disabled."""

    assert _developer_update(None, Personality.PRAGMATIC, enabled=False) is None


def test_remote_model_friendly_personality_instructions_with_feature() -> None:
    """Rust test: remote_model_friendly_personality_instructions_with_feature."""

    model_info = _remote_model(default=REMOTE_DEFAULT)
    instructions = model_info.get_model_instructions(Personality.FRIENDLY)

    assert REMOTE_FRIENDLY in instructions
    assert REMOTE_DEFAULT not in instructions


def test_user_turn_personality_remote_model_template_includes_update_message() -> None:
    """Rust test: user_turn_personality_remote_model_template_includes_update_message."""

    model_info = _remote_model(default=None)
    update = _developer_update(Personality.PRAGMATIC, Personality.FRIENDLY, model_info)

    assert update == PersonalitySpecInstructions.new(REMOTE_FRIENDLY).render()
    assert "The user has requested a new communication style." in update
    assert REMOTE_FRIENDLY in update
