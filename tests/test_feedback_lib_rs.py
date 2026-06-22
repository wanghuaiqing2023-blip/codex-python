"""Parity tests for Rust ``codex-feedback/src/lib.rs``."""

from pathlib import Path

from pycodex.feedback import (
    DOCTOR_REPORT_ATTACHMENT_FILENAME,
    FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME,
    FeedbackAttachment,
    FeedbackAttachmentPath,
    FeedbackDiagnostic,
    FeedbackDiagnostics,
    FeedbackSnapshot,
    FeedbackUploadOptions,
    CodexFeedback,
    display_classification,
)


def test_ring_buffer_drops_front_when_full() -> None:
    """Rust: ring_buffer_drops_front_when_full."""

    feedback = CodexFeedback.with_capacity(8)
    writer = feedback.make_writer().make_writer()
    assert writer.write(b"abcdefgh") == 8
    assert writer.write(b"ij") == 2

    snapshot = feedback.snapshot(None)
    assert snapshot.as_bytes().decode("utf-8") == "cdefghij"
    assert snapshot.logs == "cdefghij"
    assert snapshot.thread_id.startswith("no-active-thread-")


def test_metadata_layer_records_tags_from_feedback_target() -> None:
    """Rust: metadata_layer_records_tags_from_feedback_target."""

    feedback = CodexFeedback.new()
    feedback.record_tags({"model": "gpt-5", "cached": True})

    snapshot = feedback.snapshot(None)
    assert snapshot.tags.get("model") == "gpt-5"
    assert snapshot.tags.get("cached") == "true"


def test_feedback_attachments_gate_connectivity_diagnostics(tmp_path: Path) -> None:
    """Rust: feedback_attachments_gate_connectivity_diagnostics."""

    extra_path = tmp_path / "codex-feedback-extra-thread.jsonl"
    extra_path.write_text("rollout", encoding="utf-8")
    extra_attachment_path = FeedbackAttachmentPath(path=extra_path)

    snapshot_with_diagnostics = CodexFeedback.new().snapshot(None).with_feedback_diagnostics(
        FeedbackDiagnostics.new(
            [
                FeedbackDiagnostic(
                    headline="Proxy environment variables are set and may affect connectivity.",
                    details=["HTTPS_PROXY = https://example.com:443"],
                )
            ]
        )
    )

    attachments_with_diagnostics = snapshot_with_diagnostics.feedback_attachments(
        True,
        [
            FeedbackAttachment(
                filename=DOCTOR_REPORT_ATTACHMENT_FILENAME,
                content_type="application/json",
                data=b'{"overallStatus":"ok"}',
            )
        ],
        [extra_attachment_path],
        b"\x01",
    )

    assert [attachment.filename for attachment in attachments_with_diagnostics] == [
        "codex-logs.log",
        DOCTOR_REPORT_ATTACHMENT_FILENAME,
        FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME,
        extra_path.name,
    ]
    assert attachments_with_diagnostics[0].buffer == b"\x01"
    assert attachments_with_diagnostics[1].buffer == b'{"overallStatus":"ok"}'
    assert (
        attachments_with_diagnostics[2].buffer
        == b"Connectivity diagnostics\n\n- Proxy environment variables are set and may affect connectivity.\n"
        b"  - HTTPS_PROXY = https://example.com:443"
    )
    assert attachments_with_diagnostics[3].buffer == b"rollout"

    attachments_without_diagnostics = (
        CodexFeedback.new()
        .snapshot(None)
        .with_feedback_diagnostics(FeedbackDiagnostics())
        .feedback_attachments(True, [], [], b"\x01")
    )

    assert [attachment.filename for attachment in attachments_without_diagnostics] == ["codex-logs.log"]
    assert attachments_without_diagnostics[0].buffer == b"\x01"


def test_upload_tags_include_client_tags_and_preserve_reserved_fields() -> None:
    """Rust: upload_tags_include_client_tags_and_preserve_reserved_fields."""

    snapshot = FeedbackSnapshot(
        thread_id="thread-123",
        tags={
            "thread_id": "wrong-thread",
            "turn_id": "wrong-turn",
            "classification": "wrong-classification",
            "cli_version": "wrong-version",
            "session_source": "wrong-source",
            "reason": "wrong-reason",
            "account_id": "actual-account",
            "model": "gpt-5",
        },
    )
    client_tags = {
        "thread_id": "wrong-client-thread",
        "turn_id": "turn-456",
        "classification": "wrong-client-classification",
        "cli_version": "wrong-client-version",
        "session_source": "wrong-client-source",
        "reason": "wrong-client-reason",
        "client_tag": "from-client",
    }

    upload_tags = snapshot.upload_tags("bug", "actual reason", client_tags, "cli")

    assert upload_tags["thread_id"] == "thread-123"
    assert upload_tags["turn_id"] == "turn-456"
    assert upload_tags["classification"] == "bug"
    assert upload_tags["session_source"] == "cli"
    assert upload_tags["reason"] == "actual reason"
    assert upload_tags["account_id"] == "actual-account"
    assert upload_tags["client_tag"] == "from-client"
    assert upload_tags["model"] == "gpt-5"


def test_display_classification_and_upload_feedback_event() -> None:
    """Rust: display_classification and upload_feedback event shaping."""

    assert display_classification("bug") == "Bug"
    assert display_classification("bad_result") == "Bad result"
    assert display_classification("good_result") == "Good result"
    assert display_classification("safety_check") == "Safety check"
    assert display_classification("unknown") == "Other"

    events = []
    snapshot = FeedbackSnapshot(thread_id="thread-1", bytes=b"log")
    snapshot.upload_feedback(
        FeedbackUploadOptions(
            classification="bug",
            reason="broken",
            include_logs=True,
            sender=events.append,
        )
    )

    assert len(events) == 1
    event = events[0]
    assert event.level == "error"
    assert event.message == "[Bug]: Codex session thread-1"
    assert event.exception_value == "broken"
    assert event.attachments[0].filename == "codex-logs.log"
    assert event.attachments[0].buffer == b"log"

