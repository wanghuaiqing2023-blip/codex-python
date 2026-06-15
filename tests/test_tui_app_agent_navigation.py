from pycodex.tui.app.agent_navigation import (
    AgentNavigationDirection,
    AgentNavigationState,
    active_agent_label_tracks_current_thread,
    adjacent_thread_id_wraps_in_spawn_order,
    format_agent_picker_item_name,
    next_agent_shortcut,
    picker_subtitle_mentions_shortcuts,
    populated_state,
    previous_agent_shortcut,
    upsert_preserves_first_seen_order,
)


def test_upsert_preserves_first_seen_order_matches_rust() -> None:
    # Rust: codex-tui app/agent_navigation.rs upsert_preserves_first_seen_order
    assert upsert_preserves_first_seen_order()


def test_adjacent_thread_id_wraps_in_spawn_order_matches_rust() -> None:
    # Rust: codex-tui app/agent_navigation.rs adjacent_thread_id_wraps_in_spawn_order
    assert adjacent_thread_id_wraps_in_spawn_order()


def test_picker_subtitle_mentions_shortcuts_matches_rust() -> None:
    # Rust: codex-tui app/agent_navigation.rs picker_subtitle_mentions_shortcuts
    assert picker_subtitle_mentions_shortcuts()
    subtitle = AgentNavigationState.picker_subtitle()
    assert previous_agent_shortcut() in subtitle
    assert next_agent_shortcut() in subtitle


def test_active_agent_label_tracks_current_thread_matches_rust() -> None:
    # Rust: codex-tui app/agent_navigation.rs active_agent_label_tracks_current_thread
    assert active_agent_label_tracks_current_thread()


def test_mark_closed_remove_clear_and_non_primary_semantics() -> None:
    state, main_thread_id, first_agent_id, second_agent_id = populated_state()

    state.mark_closed(first_agent_id)
    assert state.get(first_agent_id).is_closed is True

    missing = "00000000-0000-0000-0000-000000000104"
    state.mark_closed(missing)
    assert state.get(missing).is_closed is True
    assert state.ordered_thread_ids()[-1] == missing

    assert state.has_non_primary_thread(main_thread_id)
    state.remove(second_agent_id)
    assert second_agent_id not in state.tracked_thread_ids()

    state.clear()
    assert state.is_empty()
    assert state.ordered_thread_ids() == []


def test_adjacent_thread_id_requires_current_and_two_entries() -> None:
    state = AgentNavigationState()
    one = "00000000-0000-0000-0000-000000000201"
    two = "00000000-0000-0000-0000-000000000202"

    state.upsert(one)
    assert state.adjacent_thread_id(one, AgentNavigationDirection.Next) is None

    state.upsert(two)
    assert state.adjacent_thread_id(None, AgentNavigationDirection.Next) is None
    assert (
        state.adjacent_thread_id(
            "00000000-0000-0000-0000-000000000203",
            AgentNavigationDirection.Next,
        )
        is None
    )


def test_ordered_threads_filters_order_entries_missing_metadata() -> None:
    # Rust: ordered_threads filters through the HashMap because teardown races can
    # leave historical ids in order without cached metadata.
    state, main_thread_id, first_agent_id, second_agent_id = populated_state()
    state.threads.pop(first_agent_id)

    assert state.ordered_thread_ids() == [main_thread_id, second_agent_id]
    assert state.tracked_thread_ids() == [main_thread_id, second_agent_id]
    assert state.adjacent_thread_id(main_thread_id, AgentNavigationDirection.Next) == second_agent_id


def test_active_agent_label_fallbacks_and_single_thread_suppression() -> None:
    primary = "00000000-0000-0000-0000-000000000301"
    other = "00000000-0000-0000-0000-000000000302"
    unknown = "00000000-0000-0000-0000-000000000303"
    state = AgentNavigationState()

    state.upsert(primary)
    assert state.active_agent_label(primary, primary) is None

    state.upsert(other, agent_role="worker")
    assert state.active_agent_label(other, primary) == "[worker]"
    assert state.active_agent_label(unknown, primary) == "Agent"


def test_format_agent_picker_item_name_matches_rust_cases() -> None:
    assert format_agent_picker_item_name("Robie", "explorer", False) == "Robie [explorer]"
    assert format_agent_picker_item_name("Robie", None, False) == "Robie"
    assert format_agent_picker_item_name(None, "worker", False) == "[worker]"
    assert format_agent_picker_item_name(None, None, False) == "Agent"
    assert format_agent_picker_item_name(None, None, True) == "Main [default]"
