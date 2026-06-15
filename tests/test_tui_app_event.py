from pycodex.tui.app_event import (
    AppEvent,
    ConnectorsSnapshot,
    ConsolidationScrollbackReflow,
    ExitMode,
    FeedbackCategory,
    HistoryLookupResponse,
    KeymapEditIntent,
    PermissionProfileSelection,
    RateLimitRefreshOrigin,
    RealtimeAudioDeviceKind,
    RealtimeWebrtcOffer,
    ThreadGoalSetMode,
    WindowsSandboxEnableMode,
)


def test_realtime_audio_device_labels_match_rust_helpers() -> None:
    # Rust source: codex-tui app_event.rs RealtimeAudioDeviceKind::{title,noun}.
    assert RealtimeAudioDeviceKind.MICROPHONE.title() == "Microphone"
    assert RealtimeAudioDeviceKind.MICROPHONE.noun() == "microphone"
    assert RealtimeAudioDeviceKind.SPEAKER.title() == "Speaker"
    assert RealtimeAudioDeviceKind.SPEAKER.noun() == "speaker"


def test_struct_like_modes_preserve_variant_payloads() -> None:
    # Rust source: ThreadGoalSetMode, RateLimitRefreshOrigin, KeymapEditIntent.
    assert ThreadGoalSetMode.confirm_if_exists().kind == "ConfirmIfExists"
    assert ThreadGoalSetMode.replace_existing().kind == "ReplaceExisting"
    update = ThreadGoalSetMode.update_existing("paused", token_budget=123)
    assert update.kind == "UpdateExisting"
    assert update.status == "paused"
    assert update.token_budget == 123

    assert RateLimitRefreshOrigin.startup_prefetch().kind == "StartupPrefetch"
    origin = RateLimitRefreshOrigin.status_command(42)
    assert origin.kind == "StatusCommand"
    assert origin.request_id == 42

    assert KeymapEditIntent.replace_all().kind == "ReplaceAll"
    assert KeymapEditIntent.add_alternate().kind == "AddAlternate"
    assert KeymapEditIntent.replace_one("ctrl-x") == KeymapEditIntent("ReplaceOne", old_key="ctrl-x")


def test_app_event_constructors_match_variant_payloads() -> None:
    # Rust source: AppEvent enum variant names and payload fields.
    command = object()
    assert AppEvent.codex_op(command) == AppEvent("CodexOp", {"op": command})
    assert AppEvent.codex_op(command).is_codex_op()
    assert not AppEvent.commit_tick().is_codex_op()

    assert AppEvent.submit_thread_op("thread-1", command) == AppEvent(
        "SubmitThreadOp",
        {"thread_id": "thread-1", "op": command},
    )
    assert AppEvent.exit(ExitMode.SHUTDOWN_FIRST).payload == {"mode": ExitMode.SHUTDOWN_FIRST}
    assert AppEvent.insert_history_cell("cell") == AppEvent("InsertHistoryCell", {"cell": "cell"})
    assert AppEvent.update_model("gpt-5") == AppEvent("UpdateModel", {"model": "gpt-5"})
    assert AppEvent.open_keymap_capture("root", "submit", KeymapEditIntent.add_alternate()).kind == "OpenKeymapCapture"


def test_app_event_struct_payload_constructors_preserve_none_and_enum_payloads() -> None:
    # Rust source: AppEvent::RefreshRateLimits, RateLimitsLoaded, ConsolidateAgentMessage.
    origin = RateLimitRefreshOrigin.status_command(7)
    assert AppEvent.refresh_rate_limits(origin) == AppEvent("RefreshRateLimits", {"origin": origin})
    assert AppEvent.rate_limits_loaded(origin, result=["snapshot"]) == AppEvent(
        "RateLimitsLoaded",
        {"origin": origin, "result": ["snapshot"]},
    )

    event = AppEvent.consolidate_agent_message(
        source="**answer**",
        cwd="/workspace",
        scrollback_reflow=ConsolidationScrollbackReflow.REQUIRED,
    )

    assert event.kind == "ConsolidateAgentMessage"
    assert event.payload == {
        "source": "**answer**",
        "cwd": "/workspace",
        "scrollback_reflow": ConsolidationScrollbackReflow.REQUIRED,
        "deferred_history_cell": None,
    }

    assert ThreadGoalSetMode.update_existing("complete") == ThreadGoalSetMode(
        "UpdateExisting",
        status="complete",
        token_budget=None,
    )


def test_data_structs_preserve_rust_fields() -> None:
    response = HistoryLookupResponse(offset=3, log_id=99, entry=None)
    assert response.offset == 3
    assert response.log_id == 99
    assert response.entry is None

    assert ConnectorsSnapshot().connectors == []
    assert ConnectorsSnapshot(connectors=["app"]).connectors == ["app"]

    selection = PermissionProfileSelection(
        profile_id="agent",
        approval_policy="on-request",
        approvals_reviewer=None,
        display_label="Agent",
    )
    assert selection.profile_id == "agent"
    assert selection.approval_policy == "on-request"
    assert selection.approvals_reviewer is None
    assert selection.display_label == "Agent"

    offer = RealtimeWebrtcOffer(offer_sdp="v=0", handle="handle")
    assert offer.offer_sdp == "v=0"
    assert offer.handle == "handle"


def test_simple_enum_values_match_rust_variant_names() -> None:
    assert ConsolidationScrollbackReflow.IF_RESIZE_REFLOW_RAN.value == "IfResizeReflowRan"
    assert ConsolidationScrollbackReflow.REQUIRED.value == "Required"
    assert WindowsSandboxEnableMode.ELEVATED.value == "Elevated"
    assert WindowsSandboxEnableMode.LEGACY.value == "Legacy"
    assert ExitMode.SHUTDOWN_FIRST.value == "ShutdownFirst"
    assert ExitMode.IMMEDIATE.value == "Immediate"
    assert FeedbackCategory.BAD_RESULT.value == "BadResult"
    assert FeedbackCategory.GOOD_RESULT.value == "GoodResult"
    assert FeedbackCategory.BUG.value == "Bug"
    assert FeedbackCategory.SAFETY_CHECK.value == "SafetyCheck"
    assert FeedbackCategory.OTHER.value == "Other"
