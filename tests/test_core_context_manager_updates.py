"""Parity tests for ``codex-rs/core/src/context_manager/updates.rs``."""

from types import SimpleNamespace

from pycodex.core.context import ModelSwitchInstructions, RealtimeEndInstructions, RealtimeStartInstructions
from pycodex.core.context_manager.updates import (
    build_contextual_user_message,
    build_developer_update_item,
    build_model_instructions_update_item,
    build_realtime_update_item,
    build_settings_update_items,
    build_text_message,
)
from pycodex.protocol import ContentItem, ResponseItem


class _ModelInfo:
    slug = "gpt-next"
    model_messages = None

    def get_model_instructions(self, personality: object = None) -> str:
        return "next model instructions"


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        include_environment_context=False,
        include_permissions_instructions=False,
        include_collaboration_mode_instructions=False,
        experimental_realtime_start_instructions=None,
        approvals_reviewer=None,
    )


def _next_context(*, realtime_active: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        config=_config(),
        model_info=_ModelInfo(),
        personality=None,
        realtime_active=realtime_active,
    )


def test_build_text_message_returns_none_for_empty_sections() -> None:
    """Rust source contract: ``build_text_message`` emits no message for empty sections."""

    assert build_text_message("developer", []) is None
    assert build_developer_update_item(()) is None
    assert build_contextual_user_message(()) is None


def test_build_text_message_maps_sections_to_input_text_content() -> None:
    """Rust source contract: text update helpers build role messages with one input_text per section."""

    item = build_text_message("developer", ["first", "second"])

    assert item == ResponseItem.message(
        "developer",
        (
            ContentItem.input_text("first"),
            ContentItem.input_text("second"),
        ),
    )


def test_realtime_update_uses_previous_turn_settings_when_no_reference_context() -> None:
    """Rust source contract: previous realtime turn state can emit an inactive update without reference context."""

    previous_turn_settings = SimpleNamespace(realtime_active=True)

    assert build_realtime_update_item(None, previous_turn_settings, _next_context(realtime_active=False)) == (
        RealtimeEndInstructions.new("inactive").render()
    )


def test_realtime_update_starts_when_reference_context_was_inactive() -> None:
    """Rust source contract: inactive-to-active realtime transition emits start instructions."""

    previous = SimpleNamespace(realtime_active=False)

    assert build_realtime_update_item(previous, None, _next_context(realtime_active=True)) == RealtimeStartInstructions().render()


def test_model_instructions_update_requires_model_change_and_non_empty_instructions() -> None:
    """Rust source contract: model switch instructions are emitted only when model slug changes."""

    assert build_model_instructions_update_item(SimpleNamespace(model="gpt-prev"), _next_context()) == (
        ModelSwitchInstructions.new("next model instructions").render()
    )
    assert build_model_instructions_update_item(SimpleNamespace(model="gpt-next"), _next_context()) is None


def test_build_settings_update_items_orders_developer_before_contextual_user() -> None:
    """Rust source contract: developer updates precede contextual user updates."""

    contextual_user = ResponseItem.message("user", (ContentItem.input_text("<environment_context>diff</environment_context>"),))

    items = build_settings_update_items(
        None,
        SimpleNamespace(model="gpt-prev", realtime_active=None),
        _next_context(realtime_active=True),
        contextual_user_message=contextual_user,
        personality_feature_enabled=False,
    )

    assert len(items) == 2
    assert items[0].role == "developer"
    assert items[0].content == (
        ContentItem.input_text(ModelSwitchInstructions.new("next model instructions").render()),
        ContentItem.input_text(RealtimeStartInstructions().render()),
    )
    assert items[1] is contextual_user
