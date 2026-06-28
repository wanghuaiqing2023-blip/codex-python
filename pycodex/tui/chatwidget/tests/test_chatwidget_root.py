from pycodex.tui.chatwidget import (
    DEFAULT_MODEL_DISPLAY_NAME,
    MEMORIES_ENABLE_NOTICE,
    ChatWidget,
    ChatWidgetInit,
    contains_plan_keyword,
    exec_approval_request_from_params,
    extract_first_bold,
    has_websocket_timing_metrics,
    patch_approval_request_from_params,
    queued_message_edit_binding_for_terminal,
    queued_message_edit_hint_binding,
    request_permissions_from_params,
    token_usage_info_from_app_server,
)


def test_chatwidget_root_constants_and_terminal_binding_contracts():
    # Rust: chatwidget.rs constants and queued_message_edit_binding_for_terminal.
    assert DEFAULT_MODEL_DISPLAY_NAME == "loading"
    assert queued_message_edit_binding_for_terminal({"name": "AppleTerminal"}) == "shift-left"
    assert queued_message_edit_binding_for_terminal({"name": "WindowsTerminal"}) == "alt-up"
    assert queued_message_edit_binding_for_terminal({"name": "xterm", "multiplexer": "tmux"}) == "shift-left"
    assert queued_message_edit_hint_binding({"name": "Warp"}) == "shift+left"


def test_chatwidget_root_widget_state_helpers():
    # Rust: ChatWidget root state helpers that delegate to smaller submodules in Python.
    widget = ChatWidget(ChatWidgetInit(thread_id="tid", thread_name="Thread", rollout_path="r.jsonl"))
    assert widget.thread_id() == "tid"
    assert widget.thread_name() == "Thread"
    assert widget.rollout_path() == "r.jsonl"
    assert widget.composer_is_empty()
    widget.insert_str("hello")
    assert not widget.composer_is_empty()
    widget.set_remote_image_urls(["https://img"])
    assert widget.remote_image_urls() == ["https://img"]
    assert widget.take_remote_image_urls() == ["https://img"]
    widget.set_token_info({"used_tokens": 12, "context_remaining_percent": 80})
    assert widget.context_used_tokens() == 12
    assert widget.context_remaining_percent() == 80
    widget.add_memories_enable_notice()
    assert MEMORIES_ENABLE_NOTICE in widget.info_messages


def test_chatwidget_root_transcript_and_raw_mode_helpers():
    widget = ChatWidget()
    widget.active_cell = ["live"]
    assert widget.active_cell_transcript_key().kind == "list"
    assert widget.active_cell_transcript_lines() == ["live"]
    widget.flush_active_cell()
    assert widget.history == [["live"]]
    assert (
        widget.toggle_raw_output_mode_and_notify()
        == "Raw output mode on: transcript text is shown for clean terminal selection."
    )
    assert widget.history_render_mode() == "raw"


def test_chatwidget_root_conversion_helpers():
    # Rust: helper conversion functions in chatwidget.rs.
    assert contains_plan_keyword("please make a plan")
    assert exec_approval_request_from_params({"command": ["echo", "hi"]})["kind"] == "exec"
    assert patch_approval_request_from_params({"changes": ["a"]})["kind"] == "patch"
    assert request_permissions_from_params({"permissions": ["write"]})["permissions"] == ["write"]
    assert token_usage_info_from_app_server({"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}) == {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
    }
    assert has_websocket_timing_metrics({"websocket_timing_metrics": {"connect_ms": 1}})
    assert extract_first_bold("hello **world**") == "world"
