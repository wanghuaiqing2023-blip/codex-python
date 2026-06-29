import asyncio
from pathlib import Path

from pycodex.tui.resume_picker import (
    BackgroundEvent,
    LoadTrigger,
    LoadingState,
    PageCursor,
    PickerPage,
    PickerState,
    ProviderFilter,
    Row,
    SessionFilterMode,
    SessionListDensity,
    SessionPickerAction,
    SessionSelection,
    SessionTarget,
    list_viewport_width,
    local_picker_cwd_filter,
    normalize_pasted_query,
    picker_cwd_filter,
    picker_footer_percent,
    picker_footer_progress_label,
    picker_provider_filter,
    row_from_app_server_thread,
    sort_key_label,
    thread_list_params,
)


class Config:
    model_provider_id = "openai"
    show_raw_agent_reasoning = False


def test_session_target_action_filters_and_basic_helpers_match_rust_contract() -> None:
    target = SessionTarget(Path("/tmp/session.jsonl"), "thread-1")
    assert target.display_label() == str(Path("/tmp/session.jsonl"))
    assert SessionTarget(None, "thread-1").display_label() == "thread thread-1"

    selection = SessionPickerAction.RESUME.selection(Path("/tmp/a.jsonl"), "thread-1")
    assert selection == SessionSelection.resume(SessionTarget(Path("/tmp/a.jsonl"), "thread-1"))
    assert SessionPickerAction.FORK.action_label() == "fork"
    assert SessionPickerAction.RESUME.title() == "Resume a previous session"

    assert SessionFilterMode.from_show_all(False, Path("/repo")) is SessionFilterMode.CWD
    assert SessionFilterMode.CWD.toggle(Path("/repo")) is SessionFilterMode.ALL
    assert SessionListDensity.COMFORTABLE.toggle() is SessionListDensity.DENSE
    assert local_picker_cwd_filter(Path("/repo"), uses_remote_workspace=True) is None
    assert picker_cwd_filter(Path("/repo"), False, False, None) == Path("/repo")
    assert picker_cwd_filter(Path("/repo"), True, False, None) is None
    assert picker_provider_filter(Config(), uses_remote_workspace=True).kind == "Any"
    assert picker_provider_filter(Config(), uses_remote_workspace=False) == ProviderFilter.match_default("openai")
    assert normalize_pasted_query("  alpha\n beta\tgamma ") == "alpha beta gamma"
    assert normalize_pasted_query(" \n\t ") is None
    assert sort_key_label("CreatedAt") == "Created"
    assert sort_key_label("UpdatedAt") == "Updated"
    assert list_viewport_width(120) == 112


def test_row_from_thread_seen_key_display_preview_query_and_thread_list_params() -> None:
    row = row_from_app_server_thread(
        {
            "id": "thread-1",
            "path": "/tmp/session.jsonl",
            "preview": "hello world",
            "cwd": "/repo",
            "model_provider": "openai",
            "name": "Named thread",
        }
    )

    assert row.seen_key().value == "path:/tmp/session.jsonl"
    assert row.display_preview() == "Named thread"
    assert row.matches_query("repo")
    assert row.matches_query("named")

    params = thread_list_params(PageCursor("abc"), "/repo", ProviderFilter.match_default("openai"), "UpdatedAt", True)
    assert params == {
        "cursor": "abc",
        "cwd_filter": "/repo",
        "provider_filter": "openai",
        "sort_key": "UpdatedAt",
        "page_size": 25,
        "include_non_interactive": True,
    }


def test_picker_state_initial_load_ingests_pages_dedupes_filters_and_tracks_footer() -> None:
    requests = []
    state = PickerState(
        picker_loader=requests.append,
        provider_filter=ProviderFilter.match_default("openai"),
        show_all=False,
        filter_cwd=Path("/repo"),
    )

    state.start_initial_load()
    assert state.loading_state is LoadingState.LOADING
    assert requests[0].kind == "Page"
    assert requests[0].payload.cwd_filter == Path("/repo")

    state.ingest_page(
        PickerPage(
            rows=[
                Row(Path("/tmp/a.jsonl"), "a", "alpha", cwd=Path("/repo")),
                Row(Path("/tmp/a.jsonl"), "a", "duplicate", cwd=Path("/repo")),
                Row(Path("/tmp/b.jsonl"), "b", "beta", cwd=Path("/other")),
            ],
            next_cursor=PageCursor("next"),
            num_scanned_files=3,
        )
    )

    assert [row.thread_id for row in state.rows] == ["a"]
    assert state.pagination.next_cursor == PageCursor("next")
    assert picker_footer_progress_label(state) == "1/1 (100%)"

    state.set_query("missing")
    assert state.search_state.is_active()
    assert requests[-1].payload.search_token == state.search_state.token


def test_picker_state_background_page_event_search_paste_and_scan_cap() -> None:
    requests = []
    state = PickerState(picker_loader=requests.append, show_all=True)
    state.ingest_page(PickerPage([Row(None, "a", "alpha")], next_cursor=PageCursor("next")))

    state.set_query("target")
    request = requests[-1].payload
    asyncio.run(
        state.handle_background_event(
            BackgroundEvent.page(
                request.request_token,
                request.search_token,
                PickerPage([Row(None, "b", "target text")], reached_scan_cap=False),
            )
        )
    )

    assert [row.thread_id for row in state.filtered_rows] == ["b"]
    assert not state.search_state.is_active()

    state.handle_paste(" extra words ")
    assert state.query == "target extra words"

    state.set_query("absent")
    request = requests[-1].payload
    asyncio.run(
        state.handle_background_event(
            BackgroundEvent.page(
                request.request_token,
                request.search_token,
                PickerPage([], next_cursor=None, num_scanned_files=5, reached_scan_cap=True),
            )
        )
    )
    assert state.pagination.reached_scan_cap is True
    assert state.filtered_rows == []


def test_picker_key_handling_selection_viewport_density_and_expansion() -> None:
    state = PickerState(show_all=True)
    state.ingest_page(
        PickerPage(
            [
                Row(Path("/tmp/a.jsonl"), "a", "alpha"),
                Row(Path("/tmp/b.jsonl"), "b", "beta"),
                Row(Path("/tmp/c.jsonl"), "c", "gamma"),
            ]
        )
    )
    state.update_viewport(2, 80)

    asyncio.run(state.handle_key("down"))
    asyncio.run(state.handle_key("down"))
    assert state.selected == 2
    assert state.scroll_top == 1
    assert state.has_more_above()
    assert not state.has_more_below(2)

    asyncio.run(state.handle_key("ctrl-e"))
    assert state.filtered_rows[state.selected].expanded is True

    asyncio.run(state.handle_key("ctrl-o"))
    assert state.density is SessionListDensity.DENSE

    selection = asyncio.run(state.handle_key("enter"))
    assert selection == SessionSelection.resume(SessionTarget(Path("/tmp/c.jsonl"), "c"))

    state.set_query("beta")
    assert [row.thread_id for row in state.filtered_rows] == ["b"]
    assert asyncio.run(state.handle_key("esc")) is None
    assert state.query == ""
    assert state.filtered_rows[state.selected].thread_id == "b"

    assert asyncio.run(state.handle_key("ctrl-c")) == SessionSelection.exit()
    assert picker_footer_percent(state) == 100


def test_picker_transcript_loading_overlay_and_footer_percent() -> None:
    requests = []
    state = PickerState(picker_loader=requests.append, show_all=True)
    state.ingest_page(PickerPage([Row(None, "thread-1", "preview")]))

    state.open_selected_transcript()

    assert state.is_transcript_loading()
    assert requests[-1].kind == "Transcript"
    assert state.note_transcript_loading_frame_drawn() is True

    asyncio.run(state.handle_background_event(BackgroundEvent.transcript("thread-1", ["line"])))
    state.note_transcript_loading_frame_drawn()
    state.open_pending_transcript_if_ready()
    assert state.overlay == ["line"]

    state.handle_overlay_event(None, "esc")
    assert state.overlay is None


def test_picker_search_space_backspace_and_toolbar_reload_match_rust_contract() -> None:
    # Rust-derived contract:
    # codex-tui::resume_picker::PickerState::handle_key treats a literal
    # space as searchable text, backspace edits the search query, Tab moves
    # toolbar focus to Sort, and Right/Ctrl-L reload with the new sort/filter.
    # Rust tests:
    # - resume_picker.rs::space_appends_to_search_query.
    # - resume_picker.rs::toggle_sort_key_reloads_with_new_sort.
    # - resume_picker.rs::default_filter_focus_arrows_reload_with_new_filter.
    requests = []
    state = PickerState(picker_loader=requests.append, show_all=False, filter_cwd=Path("/repo"))
    state.ingest_page(PickerPage([Row(Path("/tmp/a.jsonl"), "a", "resize row", cwd=Path("/repo"))]))

    state.set_query("resize")
    asyncio.run(state.handle_key(" "))
    asyncio.run(state.handle_key("r"))
    assert state.query == "resize r"

    asyncio.run(state.handle_key("backspace"))
    assert state.query == "resize "

    state.start_initial_load()
    assert requests[-1].payload.sort_key == "UpdatedAt"
    assert requests[-1].payload.cwd_filter == Path("/repo")

    asyncio.run(state.handle_key("tab"))
    asyncio.run(state.handle_key("right"))
    assert state.sort_key == "CreatedAt"
    assert requests[-1].payload.sort_key == "CreatedAt"

    asyncio.run(state.handle_key("tab"))
    asyncio.run(state.handle_key("right"))
    assert requests[-1].payload.cwd_filter is None


def test_picker_transcript_loading_consumes_input_except_ctrl_c() -> None:
    # Rust-derived contract:
    # codex-tui::resume_picker::PickerState::handle_key delegates to
    # handle_transcript_loading_key while a transcript is pending; ordinary
    # navigation/text does not mutate selection/search, while Ctrl-C exits.
    # Rust tests:
    # - resume_picker.rs::transcript_loading_consumes_picker_input.
    # - resume_picker.rs::transcript_loading_still_allows_ctrl_c_exit.
    state = PickerState(show_all=True)
    state.ingest_page(
        PickerPage(
            [
                Row(Path("/tmp/a.jsonl"), "a", "alpha"),
                Row(Path("/tmp/b.jsonl"), "b", "beta"),
            ]
        )
    )
    state.begin_transcript_loading("a")

    assert asyncio.run(state.handle_key("down")) is None
    assert state.selected == 0
    assert state.query == ""

    assert asyncio.run(state.handle_key("x")) is None
    assert state.query == ""

    assert asyncio.run(state.handle_key("ctrl-c")) == SessionSelection.exit()
