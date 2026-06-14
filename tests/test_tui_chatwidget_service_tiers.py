from pycodex.tui.chatwidget.service_tiers import (
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    ChatWidgetServiceTierState,
    ModelPreset,
    ServiceTierCommand,
    ServiceTierPreset,
    ServiceTierSelectionEvent,
    fast_mode_config,
)


def _fast_model(default_service_tier: str | None = None) -> ModelPreset:
    return ModelPreset(
        model="gpt-5.4",
        service_tiers=(
            ServiceTierPreset(id="fast"),
        ),
        default_service_tier=default_service_tier,
    )


def _catalog_model() -> dict[str, object]:
    return {
        "model": "gpt-5.4",
        "service_tiers": [
            {"id": "fast", "name": "Fast", "description": "Quicker responses"},
        ],
        "default_service_tier": None,
    }


def test_service_tier_commands_lowercase_catalog_names() -> None:
    # Rust parity: chatwidget::tests::slash_commands::service_tier_commands_lowercase_catalog_names
    state = ChatWidgetServiceTierState(
        config=fast_mode_config(True),
        model="gpt-5.4",
        models=(_catalog_model(),),
    )

    assert state.current_model_service_tier_commands() == [
        ServiceTierCommand(id="fast", name="fast", description="Quicker responses")
    ]


def test_fast_toggle_updates_and_persists_local_service_tier() -> None:
    # Rust parity: chatwidget::tests::slash_commands::fast_keybinding_toggle_uses_same_events_as_fast_slash_command
    state = ChatWidgetServiceTierState(
        config=fast_mode_config(True),
        model="gpt-5.4",
        models=(_catalog_model(),),
    )

    state.toggle_fast_mode_from_ui()

    assert state.configured_service_tier() == "fast"
    assert state.events == [
        ServiceTierSelectionEvent.override_turn_context("fast"),
        ServiceTierSelectionEvent.persist_selection("fast"),
    ]


def test_service_tier_toggle_turns_selected_tier_back_to_default() -> None:
    # Rust parity: chatwidget::service_tiers::toggle_service_tier_from_ui
    state = ChatWidgetServiceTierState(
        config=fast_mode_config(True, service_tier="fast"),
        model="gpt-5.4",
        models=(_catalog_model(),),
    )

    state.toggle_service_tier_from_ui(
        ServiceTierCommand(id="fast", name="fast", description="Quicker responses")
    )

    assert state.configured_service_tier() == SERVICE_TIER_DEFAULT_REQUEST_VALUE
    assert state.events == [
        ServiceTierSelectionEvent.override_turn_context(SERVICE_TIER_DEFAULT_REQUEST_VALUE),
        ServiceTierSelectionEvent.persist_selection(SERVICE_TIER_DEFAULT_REQUEST_VALUE),
    ]


def test_fast_keybinding_toggle_requires_feature_and_idle_surface() -> None:
    # Rust parity: chatwidget::tests::slash_commands::fast_keybinding_toggle_requires_feature_and_idle_surface
    disabled = ChatWidgetServiceTierState(
        config=fast_mode_config(False),
        model="gpt-5.4",
        models=(_catalog_model(),),
    )
    assert not disabled.can_toggle_fast_mode_from_keybinding()

    enabled = ChatWidgetServiceTierState(
        config=fast_mode_config(True),
        model="gpt-5.4",
        models=(_catalog_model(),),
    )
    assert enabled.can_toggle_fast_mode_from_keybinding()

    enabled.user_turn_pending_or_running = True
    assert not enabled.can_toggle_fast_mode_from_keybinding()

    enabled.user_turn_pending_or_running = False
    enabled.modal_or_popup_active = True
    assert not enabled.can_toggle_fast_mode_from_keybinding()


def test_should_show_fast_status_requires_fast_supported_and_chatgpt_account() -> None:
    # Rust parity: chatwidget::service_tiers::should_show_fast_status
    state = ChatWidgetServiceTierState(
        config=fast_mode_config(True),
        model="gpt-5.4",
        models=(_fast_model(),),
        has_chatgpt_account=True,
    )

    assert state.should_show_fast_status("gpt-5.4", "fast")
    assert not state.should_show_fast_status("gpt-5.4", None)
    assert not state.should_show_fast_status("other", "fast")

    state.has_chatgpt_account = False
    assert not state.should_show_fast_status("gpt-5.4", "fast")


def test_set_service_tier_refreshes_effective_tier_and_surfaces() -> None:
    # Rust parity: chatwidget::service_tiers::set_service_tier
    state = ChatWidgetServiceTierState(
        config=fast_mode_config(True),
        model="gpt-5.4",
        models=(_fast_model(default_service_tier="fast"),),
    )

    assert state.current_service_tier() == "fast"
    state.set_service_tier(SERVICE_TIER_DEFAULT_REQUEST_VALUE)

    assert state.configured_service_tier() == SERVICE_TIER_DEFAULT_REQUEST_VALUE
    assert state.current_service_tier() == SERVICE_TIER_DEFAULT_REQUEST_VALUE
    assert state.model_dependent_surface_refreshes == 1
