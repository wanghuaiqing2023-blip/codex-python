from pycodex.analytics import (
    AnalyticsReducer,
    CodexToolItemEventBase,
    FinalApprovalOutcome,
    GuardianApprovalRequestSource,
    GuardianReviewCompletedNotification,
    GuardianApprovalReviewStatus,
    GuardianReviewDecision,
    GuardianReviewEventParams,
    GuardianReviewFailureReason,
    GuardianReviewTerminalStatus,
    ReviewResolution,
    ReviewSubjectKind,
    ReviewStatus,
    ReviewTrigger,
    Reviewer,
    ToolItemTerminalStatus,
    ThreadMetadataState,
    apply_tool_item_review_summary,
    codex_review_event,
    codex_tool_item_event_base_params,
    effective_permissions_review_result,
    final_approval_outcome,
    guardian_review_event,
    guardian_review_result,
    PendingReviewState,
)


def test_review_status_and_resolution_serde_values_match_rust() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: ReviewStatus, ReviewResolution
    # Contract: review enums use serde rename_all = "snake_case".
    assert [status.value for status in ReviewStatus] == ["approved", "denied", "aborted", "timed_out"]
    assert [resolution.value for resolution in ReviewResolution] == [
        "none",
        "session_approval",
        "exec_policy_amendment",
        "network_policy_amendment",
    ]


def test_guardian_review_result_maps_terminal_statuses() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: reducer::tests::guardian_review_result_maps_terminal_statuses
    # Contract: in-progress guardian review has no analytics result; terminal statuses map with no resolution.
    assert guardian_review_result(GuardianApprovalReviewStatus.IN_PROGRESS) is None
    assert guardian_review_result(GuardianApprovalReviewStatus.APPROVED) == (
        ReviewStatus.APPROVED,
        ReviewResolution.NONE,
    )
    assert guardian_review_result(GuardianApprovalReviewStatus.DENIED) == (
        ReviewStatus.DENIED,
        ReviewResolution.NONE,
    )
    assert guardian_review_result(GuardianApprovalReviewStatus.TIMED_OUT) == (
        ReviewStatus.TIMED_OUT,
        ReviewResolution.NONE,
    )
    assert guardian_review_result(GuardianApprovalReviewStatus.ABORTED) == (
        ReviewStatus.ABORTED,
        ReviewResolution.NONE,
    )


def test_effective_permissions_review_result_matches_rust_mapping() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust item: effective_permissions_review_result
    # Contract: empty permissions deny; turn grants approve without session resolution; session grants use session_approval.
    assert effective_permissions_review_result({"permissions": {}, "scope": "Session"}) == (
        ReviewStatus.DENIED,
        ReviewResolution.NONE,
    )
    assert effective_permissions_review_result(
        {
            "permissions": {"network": {"enabled": True}, "file_system": None},
            "scope": "Turn",
        }
    ) == (ReviewStatus.APPROVED, ReviewResolution.NONE)
    assert effective_permissions_review_result(
        {
            "permissions": {"network": {"enabled": True}, "file_system": None},
            "scope": "Session",
        }
    ) == (ReviewStatus.APPROVED, ReviewResolution.SESSION_APPROVAL)


def test_review_event_serializes_expected_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust test: analytics_client_tests::review_event_serializes_expected_shape
    # Contract: CodexReviewEventRequest serializes the Rust review event field shape.
    payload = codex_review_event(
        thread_id="thread-1",
        turn_id="turn-1",
        item_id=None,
        review_id="review-1",
        app_server_client={
            "product_client_id": "codex_tui",
            "client_name": "codex-tui",
            "client_version": "1.2.3",
            "rpc_transport": "websocket",
            "experimental_api_enabled": True,
        },
        runtime={
            "codex_rs_version": "0.99.0",
            "runtime_os": "macos",
            "runtime_os_version": "15.3.1",
            "runtime_arch": "aarch64",
        },
        thread_source="subagent",
        subagent_source="thread_spawn",
        parent_thread_id="parent-thread-1",
        subject_kind=ReviewSubjectKind.NETWORK_ACCESS,
        subject_name="network_access",
        reviewer=Reviewer.USER,
        trigger=ReviewTrigger.NETWORK_POLICY_DENIAL,
        status=ReviewStatus.APPROVED,
        resolution=ReviewResolution.NETWORK_POLICY_AMENDMENT,
        started_at_ms=123,
        completed_at_ms=125,
        duration_ms=2,
    )

    assert payload == {
        "event_type": "codex_review_event",
        "event_params": {
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": None,
            "review_id": "review-1",
            "app_server_client": {
                "product_client_id": "codex_tui",
                "client_name": "codex-tui",
                "client_version": "1.2.3",
                "rpc_transport": "websocket",
                "experimental_api_enabled": True,
            },
            "runtime": {
                "codex_rs_version": "0.99.0",
                "runtime_os": "macos",
                "runtime_os_version": "15.3.1",
                "runtime_arch": "aarch64",
            },
            "thread_source": "subagent",
            "subagent_source": "thread_spawn",
            "parent_thread_id": "parent-thread-1",
            "subject_kind": "network_access",
            "subject_name": "network_access",
            "reviewer": "user",
            "trigger": "network_policy_denial",
            "status": "approved",
            "resolution": "network_policy_amendment",
            "started_at_ms": 123,
            "completed_at_ms": 125,
            "duration_ms": 2,
        },
    }


def sample_app_server_client_metadata(*, rpc_transport: str = "websocket", experimental_api_enabled: bool | None = False) -> dict:
    return {
        "product_client_id": "codex_cli_rs",
        "client_name": "codex-tui",
        "client_version": "1.0.0",
        "rpc_transport": rpc_transport,
        "experimental_api_enabled": experimental_api_enabled,
    }


def sample_runtime_metadata() -> dict:
    return {
        "codex_rs_version": "0.1.0",
        "runtime_os": "macos",
        "runtime_os_version": "15.3.1",
        "runtime_arch": "aarch64",
    }


def sample_guardian_review_params() -> GuardianReviewEventParams:
    return GuardianReviewEventParams(
        thread_id="thread-guardian",
        turn_id="turn-guardian",
        review_id="review-guardian",
        target_item_id=None,
        approval_request_source=GuardianApprovalRequestSource.DELEGATED_SUBAGENT,
        reviewed_action={
            "type": "network_access",
            "protocol": "https",
            "port": 443,
        },
        reviewed_action_truncated=False,
        decision=GuardianReviewDecision.DENIED,
        terminal_status=GuardianReviewTerminalStatus.TIMED_OUT,
        failure_reason=GuardianReviewFailureReason.TIMEOUT,
        risk_level=None,
        user_authorization=None,
        outcome=None,
        guardian_thread_id=None,
        guardian_session_kind=None,
        guardian_model=None,
        guardian_reasoning_effort=None,
        had_prior_review_context=None,
        review_timeout_ms=90_000,
        tool_call_count=None,
        time_to_first_token_ms=None,
        completion_latency_ms=90_000,
        started_at=100,
        completed_at=190,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        reasoning_output_tokens=None,
        total_tokens=None,
    )


def test_guardian_review_event_serializes_flattened_payload() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/events.rs
    # Rust item: GuardianReviewEventRequest, GuardianReviewEventPayload, GuardianReviewEventParams
    # Contract: Guardian review payload flattens metadata and review params, preserving optional fields as null.
    payload = guardian_review_event(
        sample_guardian_review_params(),
        session_id="session-thread-guardian",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
    )

    assert payload["event_type"] == "codex_guardian_review"
    params = payload["event_params"]
    assert params["session_id"] == "session-thread-guardian"
    assert params["thread_id"] == "thread-guardian"
    assert params["turn_id"] == "turn-guardian"
    assert params["review_id"] == "review-guardian"
    assert params["target_item_id"] is None
    assert params["approval_request_source"] == "delegated_subagent"
    assert params["app_server_client"]["product_client_id"] == "codex_cli_rs"
    assert params["runtime"]["codex_rs_version"] == "0.1.0"
    assert params["reviewed_action"] == {
        "type": "network_access",
        "protocol": "https",
        "port": 443,
    }
    assert "retry_reason" not in params
    assert "rationale" not in params
    assert "target" not in params["reviewed_action"]
    assert "host" not in params["reviewed_action"]
    assert params["terminal_status"] == "timed_out"
    assert params["failure_reason"] == "timeout"
    assert params["review_timeout_ms"] == 90_000
    assert params["completion_latency_ms"] == 90_000


def test_guardian_review_event_ingests_custom_fact_with_optional_target_item() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::guardian_review_event_ingests_custom_fact_with_optional_target_item
    # Contract: reducer guardian-review custom fact combines review fields with connection and thread metadata.
    events = AnalyticsReducer().ingest_guardian_review(
        sample_guardian_review_params(),
        session_id="session-thread-guardian",
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
    )

    assert len(events) == 1
    payload = events[0]
    assert payload["event_type"] == "codex_guardian_review"
    assert payload["event_params"]["session_id"] == "session-thread-guardian"
    assert payload["event_params"]["thread_id"] == "thread-guardian"
    assert payload["event_params"]["turn_id"] == "turn-guardian"
    assert payload["event_params"]["review_id"] == "review-guardian"
    assert payload["event_params"]["target_item_id"] is None
    assert payload["event_params"]["approval_request_source"] == "delegated_subagent"
    assert payload["event_params"]["app_server_client"]["product_client_id"] == "codex_cli_rs"
    assert payload["event_params"]["runtime"]["codex_rs_version"] == "0.1.0"
    assert payload["event_params"]["reviewed_action"]["type"] == "network_access"
    assert payload["event_params"]["reviewed_action"]["protocol"] == "https"
    assert payload["event_params"]["reviewed_action"]["port"] == 443
    assert "retry_reason" not in payload["event_params"]
    assert "rationale" not in payload["event_params"]
    assert "target" not in payload["event_params"]["reviewed_action"]
    assert "host" not in payload["event_params"]["reviewed_action"]
    assert payload["event_params"]["terminal_status"] == "timed_out"
    assert payload["event_params"]["failure_reason"] == "timeout"
    assert payload["event_params"]["review_timeout_ms"] == 90_000


def sample_pending_review(*, thread_id: str = "thread-1", item_id: str | None = "item-1") -> PendingReviewState:
    return PendingReviewState(
        thread_id=thread_id,
        turn_id="turn-1",
        item_id=item_id,
        review_id="review-1",
        subject_kind=ReviewSubjectKind.COMMAND_EXECUTION,
        subject_name="shell",
        trigger=ReviewTrigger.INITIAL,
        started_at_ms=1_000,
        requested_additional_permissions=True,
        requested_network_access=False,
    )


def sample_thread_metadata() -> ThreadMetadataState:
    return ThreadMetadataState(
        session_id="session-thread-1",
        thread_source="user",
        subagent_source=None,
        parent_thread_id=None,
    )


def sample_tool_item_base(*, thread_id: str = "thread-1", item_id: str = "item-1") -> CodexToolItemEventBase:
    return CodexToolItemEventBase(
        thread_id=thread_id,
        turn_id="turn-1",
        item_id=item_id,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_source="user",
        subagent_source=None,
        parent_thread_id=None,
        tool_name="shell",
        started_at_ms=1_000,
        completed_at_ms=1_042,
        duration_ms=42,
        execution_duration_ms=40,
        review_count=0,
        guardian_review_count=0,
        user_review_count=0,
        final_approval_outcome=FinalApprovalOutcome.UNKNOWN,
        terminal_status=ToolItemTerminalStatus.COMPLETED,
        failure_kind=None,
        requested_additional_permissions=False,
        requested_network_access=False,
    )


def test_final_approval_outcome_matches_rust_mapping() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust item: final_approval_outcome
    # Contract: reviewer/status/resolution triples map to the Rust FinalApprovalOutcome enum.
    assert final_approval_outcome(Reviewer.GUARDIAN, ReviewStatus.APPROVED, ReviewResolution.NONE) == (
        FinalApprovalOutcome.GUARDIAN_APPROVED
    )
    assert final_approval_outcome(Reviewer.GUARDIAN, ReviewStatus.DENIED, ReviewResolution.NONE) == (
        FinalApprovalOutcome.GUARDIAN_DENIED
    )
    assert final_approval_outcome(Reviewer.GUARDIAN, ReviewStatus.TIMED_OUT, ReviewResolution.NONE) == (
        FinalApprovalOutcome.GUARDIAN_ABORTED
    )
    assert final_approval_outcome(Reviewer.USER, ReviewStatus.APPROVED, ReviewResolution.SESSION_APPROVAL) == (
        FinalApprovalOutcome.USER_APPROVED_FOR_SESSION
    )
    assert final_approval_outcome(Reviewer.USER, ReviewStatus.APPROVED, ReviewResolution.NONE) == (
        FinalApprovalOutcome.USER_APPROVED
    )
    assert final_approval_outcome(Reviewer.USER, ReviewStatus.DENIED, ReviewResolution.NONE) == (
        FinalApprovalOutcome.USER_DENIED
    )
    assert final_approval_outcome(Reviewer.USER, ReviewStatus.ABORTED, ReviewResolution.NONE) == (
        FinalApprovalOutcome.USER_ABORTED
    )


def test_terminal_reviews_denormalize_counts_onto_tool_item_events() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::terminal_reviews_denormalize_counts_onto_tool_item_events
    # Contract: terminal item reviews increment review counters and project final approval outcome onto tool item base.
    reducer = AnalyticsReducer()
    pending = sample_pending_review()
    summary = reducer.record_item_review_summary(
        pending,
        reviewer=Reviewer.USER,
        status=ReviewStatus.APPROVED,
        resolution=ReviewResolution.SESSION_APPROVAL,
    )

    base = apply_tool_item_review_summary(sample_tool_item_base(), summary)
    payload = codex_tool_item_event_base_params(base)

    assert payload["review_count"] == 1
    assert payload["user_review_count"] == 1
    assert payload["guardian_review_count"] == 0
    assert payload["final_approval_outcome"] == "user_approved_for_session"
    assert payload["requested_additional_permissions"] is True
    assert payload["requested_network_access"] is False


def test_item_review_summaries_do_not_cross_threads_with_reused_item_ids() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::item_review_summaries_do_not_cross_threads_with_reused_item_ids
    # Contract: review summaries are keyed by thread id, turn id, and item id.
    reducer = AnalyticsReducer()
    reducer.record_item_review_summary(
        sample_pending_review(thread_id="thread-1", item_id="item-1"),
        reviewer=Reviewer.USER,
        status=ReviewStatus.APPROVED,
        resolution=ReviewResolution.NONE,
    )

    summary = reducer.review_summary_for_item("thread-2", "turn-1", "item-1")
    base = apply_tool_item_review_summary(sample_tool_item_base(thread_id="thread-2", item_id="item-1"), summary)
    payload = codex_tool_item_event_base_params(base)

    assert payload["thread_id"] == "thread-2"
    assert payload["item_id"] == "item-1"
    assert payload["review_count"] == 0
    assert payload["user_review_count"] == 0
    assert payload["guardian_review_count"] == 0
    assert payload["final_approval_outcome"] == "unknown"


def test_emit_review_event_publishes_user_review_and_records_summary() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::command_execution_approval_response_publishes_user_review_event
    # Contract: emit_review_event serializes a user review event and updates item review summary.
    reducer = AnalyticsReducer()
    pending = sample_pending_review()
    event = reducer.emit_review_event(
        pending,
        reviewer=Reviewer.USER,
        status=ReviewStatus.APPROVED,
        resolution=ReviewResolution.NONE,
        completed_at_ms=1_042,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert event["event_type"] == "codex_review_event"
    params = event["event_params"]
    assert params["thread_id"] == "thread-1"
    assert params["turn_id"] == "turn-1"
    assert params["item_id"] == "item-1"
    assert params["review_id"] == "review-1"
    assert params["thread_source"] == "user"
    assert params["subject_kind"] == "command_execution"
    assert params["subject_name"] == "shell"
    assert params["reviewer"] == "user"
    assert params["trigger"] == "initial"
    assert params["status"] == "approved"
    assert params["resolution"] == "none"
    assert params["started_at_ms"] == 1_000
    assert params["completed_at_ms"] == 1_042
    assert params["duration_ms"] == 42

    summary = reducer.review_summary_for_item("thread-1", "turn-1", "item-1")
    assert summary.review_count == 1
    assert summary.user_review_count == 1
    assert summary.guardian_review_count == 0
    assert summary.final_approval_outcome == FinalApprovalOutcome.USER_APPROVED


def test_emit_review_event_for_permissions_does_not_denormalize_onto_tool_item() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::permissions_reviews_emit_events_without_denormalizing_onto_tool_items
    # Contract: permissions reviews publish review events but are not keyed onto tool item summaries.
    reducer = AnalyticsReducer()
    pending = PendingReviewState(
        thread_id="thread-1",
        turn_id="turn-1",
        item_id="permissions-1",
        review_id="user:51",
        subject_kind=ReviewSubjectKind.PERMISSIONS,
        subject_name="permissions",
        trigger=ReviewTrigger.INITIAL,
        started_at_ms=1_000,
        requested_additional_permissions=False,
        requested_network_access=False,
    )
    event = reducer.emit_review_event(
        pending,
        reviewer=Reviewer.USER,
        status=ReviewStatus.DENIED,
        resolution=ReviewResolution.NONE,
        completed_at_ms=1_042,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert event["event_params"]["review_id"] == "user:51"
    assert event["event_params"]["subject_kind"] == "permissions"
    assert event["event_params"]["status"] == "denied"
    assert event["event_params"]["resolution"] == "none"
    summary = reducer.review_summary_for_item("thread-1", "turn-1", "permissions-1")
    assert summary.review_count == 0
    assert summary.user_review_count == 0
    assert summary.guardian_review_count == 0


def test_effective_session_permissions_response_publishes_session_user_review_event() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::effective_session_permissions_response_publishes_session_user_review_event
    # Contract: effective permissions approval responses resolve session approvals and publish a user review event.
    reducer = AnalyticsReducer()
    reducer.track_pending_review(
        52,
        PendingReviewState(
            thread_id="thread-1",
            turn_id="turn-1",
            item_id="permissions-1",
            review_id="user:52",
            subject_kind=ReviewSubjectKind.PERMISSIONS,
            subject_name="permissions",
            trigger=ReviewTrigger.NETWORK_POLICY_DENIAL,
            started_at_ms=1_000,
            requested_additional_permissions=True,
            requested_network_access=True,
        ),
    )

    events = reducer.ingest_effective_permissions_approval_response(
        request_id=52,
        completed_at_ms=1_042,
        response={
            "permissions": {
                "network": {"enabled": True},
                "file_system": None,
            },
            "scope": "Session",
            "strict_auto_review": False,
        },
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert len(events) == 1
    assert events[0]["event_type"] == "codex_review_event"
    params = events[0]["event_params"]
    assert params["review_id"] == "user:52"
    assert params["subject_kind"] == "permissions"
    assert params["reviewer"] == "user"
    assert params["status"] == "approved"
    assert params["resolution"] == "session_approval"
    assert params["started_at_ms"] == 1_000
    assert params["completed_at_ms"] == 1_042
    assert params["duration_ms"] == 42

    later = reducer.ingest_effective_permissions_approval_response(
        request_id=52,
        completed_at_ms=1_043,
        response={
            "permissions": {
                "network": {"enabled": True},
                "file_system": None,
            },
            "scope": "Session",
        },
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    assert later == []
    summary = reducer.review_summary_for_item("thread-1", "turn-1", "permissions-1")
    assert summary.review_count == 0
    assert summary.user_review_count == 0
    assert summary.guardian_review_count == 0


def test_aborted_server_request_publishes_aborted_user_review_event_once() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::aborted_server_request_publishes_aborted_user_review_event_once
    # Contract: abort removes the pending review, emits one aborted event, and later responses for the same request are ignored.
    reducer = AnalyticsReducer()
    reducer.track_pending_review(
        61,
        sample_pending_review(item_id="item-1"),
    )

    events = reducer.ingest_server_request_aborted(
        request_id=61,
        completed_at_ms=1_042,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert len(events) == 1
    assert events[0]["event_params"]["review_id"] == "review-1"
    assert events[0]["event_params"]["status"] == "aborted"
    assert events[0]["event_params"]["resolution"] == "none"
    assert events[0]["event_params"]["duration_ms"] == 42

    later = reducer.ingest_review_response(
        request_id=61,
        reviewer=Reviewer.USER,
        status=ReviewStatus.APPROVED,
        resolution=ReviewResolution.NONE,
        completed_at_ms=1_043,
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )
    assert later == []

    summary = reducer.review_summary_for_item("thread-1", "turn-1", "item-1")
    assert summary.review_count == 1
    assert summary.user_review_count == 1
    assert summary.final_approval_outcome == FinalApprovalOutcome.USER_ABORTED


def test_guardian_completed_notification_publishes_review_event_with_thread_metadata() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust test: analytics_client_tests::guardian_completed_notification_publishes_review_event_with_thread_metadata
    # Contract: terminal guardian completed notifications publish review events with thread metadata.
    reducer = AnalyticsReducer()

    events = reducer.ingest_guardian_review_completed(
        GuardianReviewCompletedNotification(
            thread_id="thread-1",
            turn_id="turn-1",
            started_at_ms=1_000,
            completed_at_ms=1_042,
            review_id="guardian-review-1",
            target_item_id="item-1",
            status=GuardianApprovalReviewStatus.DENIED,
            action={
                "type": "command",
                "source": "shell",
                "command": "echo hi",
                "cwd": "/tmp",
            },
        ),
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert len(events) == 1
    payload = events[0]
    assert payload["event_type"] == "codex_review_event"
    params = payload["event_params"]
    assert params["review_id"] == "guardian-review-1"
    assert params["item_id"] == "item-1"
    assert params["thread_source"] == "user"
    assert params["subject_kind"] == "command_execution"
    assert params["subject_name"] == "command_execution"
    assert params["reviewer"] == "guardian"
    assert params["trigger"] == "initial"
    assert params["status"] == "denied"
    assert params["resolution"] == "none"
    assert params["started_at_ms"] == 1_000
    assert params["completed_at_ms"] == 1_042
    assert params["duration_ms"] == 42

    summary = reducer.review_summary_for_item("thread-1", "turn-1", "item-1")
    assert summary.review_count == 1
    assert summary.guardian_review_count == 1
    assert summary.user_review_count == 0
    assert summary.final_approval_outcome == FinalApprovalOutcome.GUARDIAN_DENIED
    assert summary.requested_additional_permissions is False
    assert summary.requested_network_access is False


def test_guardian_completed_in_progress_review_does_not_publish_event() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/reducer.rs
    # Rust items: ingest_guardian_review_completed, guardian_review_result
    # Contract: in-progress guardian review completions are ignored because they have no terminal review result.
    events = AnalyticsReducer().ingest_guardian_review_completed(
        GuardianReviewCompletedNotification(
            thread_id="thread-1",
            turn_id="turn-1",
            started_at_ms=1_000,
            completed_at_ms=1_042,
            review_id="guardian-review-1",
            target_item_id="item-1",
            status=GuardianApprovalReviewStatus.IN_PROGRESS,
            action={"type": "command", "source": "shell", "command": "echo hi", "cwd": "/tmp"},
        ),
        app_server_client=sample_app_server_client_metadata(),
        runtime=sample_runtime_metadata(),
        thread_metadata=sample_thread_metadata(),
    )

    assert events == []
