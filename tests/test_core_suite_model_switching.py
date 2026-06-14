"""Suite parity tests for ``codex-rs/core/tests/suite/model_switching.rs``.

The Rust file drives these behaviors through a mock Responses API server.  The
Python port keeps the same user-visible contract at the stable core boundaries:
settings-update developer messages, service-tier request normalization, prompt
history normalization across model modality changes, rollback, and model context
window selection.
"""

from __future__ import annotations

from types import SimpleNamespace

from pycodex.core.client import _service_tier_for_request
from pycodex.core.context_manager.history import ContextManager
from pycodex.core.context_manager.normalize import IMAGE_CONTENT_OMITTED_PLACEHOLDER, strip_images_when_unsupported
from pycodex.core.context_manager.updates import build_developer_update_item, build_model_instructions_update_item, build_personality_update_item
from pycodex.core.session.turn import runtime as turn_runtime
from pycodex.protocol import ContentItem, ResponseItem, ServiceTier


class _ModelMessages:
    def get_personality_message(self, personality: object) -> str:
        return f"separate personality message for {personality}"


def _model_info(slug: str, instructions: str) -> SimpleNamespace:
    return SimpleNamespace(
        slug=slug,
        model_messages=_ModelMessages(),
        get_model_instructions=lambda personality: f"{instructions} / personality={personality}",
    )


def _developer_text(item: ResponseItem) -> str:
    assert item.type == "message"
    assert item.role == "developer"
    return "\n".join(content.text or "" for content in item.content)


def test_model_change_appends_model_instructions_developer_message() -> None:
    """Rust test: ``model_change_appends_model_instructions_developer_message``."""

    previous_turn_settings = SimpleNamespace(model="gpt-5-codex", personality="friendly")
    next_context = SimpleNamespace(model_info=_model_info("gpt-5.1-codex", "new model instructions"), personality="friendly")

    model_section = build_model_instructions_update_item(previous_turn_settings, next_context)
    developer = build_developer_update_item([model_section])

    assert developer is not None
    text = _developer_text(developer)
    assert "new model instructions" in text
    assert "personality=friendly" in text


def test_model_and_personality_change_only_appends_model_instructions() -> None:
    """Rust test: ``model_and_personality_change_only_appends_model_instructions``."""

    previous_turn_settings = SimpleNamespace(model="gpt-5-codex", personality="friendly")
    next_context = SimpleNamespace(model_info=_model_info("gpt-5.1-codex", "new baked instructions"), personality="terse")

    model_section = build_model_instructions_update_item(previous_turn_settings, next_context)
    personality_section = build_personality_update_item(previous_turn_settings, next_context, True)
    developer = build_developer_update_item([model_section])

    assert personality_section is None
    assert developer is not None
    text = _developer_text(developer)
    assert "new baked instructions" in text
    assert "personality=terse" in text
    assert "separate personality message" not in text


def test_service_tier_change_is_applied_on_next_http_turn() -> None:
    """Rust test: ``service_tier_change_is_applied_on_next_http_turn``."""

    model_info = SimpleNamespace(service_tier_for_request=lambda tier: tier)

    assert _service_tier_for_request(model_info, ServiceTier.FAST) == "priority"


def test_flex_service_tier_is_applied_to_http_turn() -> None:
    """Rust test: ``flex_service_tier_is_applied_to_http_turn``."""

    model_info = SimpleNamespace(service_tier_for_request=lambda tier: tier)

    assert _service_tier_for_request(model_info, ServiceTier.FLEX) == "flex"


def test_unsupported_service_tier_is_omitted_from_http_turn() -> None:
    """Rust test: ``unsupported_service_tier_is_omitted_from_http_turn``."""

    model_info = SimpleNamespace(service_tier_for_request=lambda tier: tier if tier in {"priority", "flex"} else None)

    assert _service_tier_for_request(model_info, "standard") is None


def test_default_service_tier_override_is_omitted_from_http_turn() -> None:
    """Rust test: ``default_service_tier_override_is_omitted_from_http_turn``."""

    model_info = SimpleNamespace(service_tier_for_request=lambda tier: tier if tier in {"priority", "flex"} else None)

    assert _service_tier_for_request(model_info, "default") is None


def test_null_service_tier_override_is_omitted_from_http_turn_with_catalog_default() -> None:
    """Rust test: ``null_service_tier_override_is_omitted_from_http_turn_with_catalog_default``."""

    model_info = SimpleNamespace(service_tier_for_request=lambda tier: "priority" if tier == "fast" else tier)

    assert _service_tier_for_request(model_info, None) is None


def test_model_change_from_image_to_text_strips_prior_image_content() -> None:
    """Rust test: ``model_change_from_image_to_text_strips_prior_image_content``."""

    prior_image_turn = ResponseItem.message(
        "user",
        (
            ContentItem.input_text("describe this"),
            ContentItem.input_image("data:image/png;base64,Zm9v"),
        ),
    )

    normalized = strip_images_when_unsupported(("text",), (prior_image_turn,))

    assert normalized[0].content[0].text == "describe this"
    assert normalized[0].content[1].type == "input_text"
    assert normalized[0].content[1].text == IMAGE_CONTENT_OMITTED_PLACEHOLDER


def test_generated_image_is_replayed_for_image_capable_models() -> None:
    """Rust test: ``generated_image_is_replayed_for_image_capable_models``."""

    image_generation = ResponseItem.image_generation_call("ig_123", "completed", "Zm9v", revised_prompt="lobster")
    history = ContextManager.from_items((image_generation, ResponseItem.message("user", (ContentItem.input_text("again"),))))

    assert history.for_prompt(("text", "image"))[0] == image_generation


def test_model_change_from_generated_image_to_text_preserves_prior_generated_image_call() -> None:
    """Rust test: ``model_change_from_generated_image_to_text_preserves_prior_generated_image_call``."""

    image_generation = ResponseItem.image_generation_call("ig_123", "completed", "Zm9v", revised_prompt="lobster")
    history = ContextManager.from_items((ResponseItem.message("user", (ContentItem.input_text("draw"),)), image_generation))

    normalized = history.for_prompt(("text",))

    assert normalized[1] == ResponseItem.image_generation_call("ig_123", "completed", "", revised_prompt="lobster")


def test_thread_rollback_after_generated_image_drops_entire_image_turn_history() -> None:
    """Rust test: ``thread_rollback_after_generated_image_drops_entire_image_turn_history``."""

    prefix = ResponseItem.message("assistant", (ContentItem.output_text("ready"),))
    image_user = ResponseItem.message("user", (ContentItem.input_text("draw"), ContentItem.input_image("data:image/png;base64,Zm9v")))
    image_generation = ResponseItem.image_generation_call("ig_123", "completed", "Zm9v", revised_prompt="lobster")
    followup = ResponseItem.message("user", (ContentItem.input_text("undo"),))
    history = ContextManager.from_items((prefix, image_user, image_generation, followup))

    history.drop_last_n_user_turns(2)

    assert history.raw_items() == [prefix]


def test_model_switch_to_smaller_model_updates_token_context_window() -> None:
    """Rust test: ``model_switch_to_smaller_model_updates_token_context_window``."""

    large_turn = SimpleNamespace(model_info=SimpleNamespace(slug="gpt-large", context_window=200_000))
    small_turn = SimpleNamespace(model_info=SimpleNamespace(slug="gpt-small", context_window=64_000))

    assert turn_runtime._turn_context_model_context_window(large_turn) == 200_000
    assert turn_runtime._turn_context_model_context_window(small_turn) == 64_000

