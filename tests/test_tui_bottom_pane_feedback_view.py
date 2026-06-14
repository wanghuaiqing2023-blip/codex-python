from pycodex.feedback import DOCTOR_REPORT_ATTACHMENT_FILENAME
from pycodex.feedback import FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME
from pycodex.feedback import WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME
from pycodex.feedback import FeedbackDiagnostic
from pycodex.feedback import FeedbackDiagnostics
from pycodex.tui.app_event import FeedbackCategory
from pycodex.tui.bottom_pane.feedback_view import BASE_CLI_BUG_ISSUE_URL
from pycodex.tui.bottom_pane.feedback_view import CODEX_FEEDBACK_INTERNAL_URL
from pycodex.tui.bottom_pane.feedback_view import FeedbackAudience
from pycodex.tui.bottom_pane.feedback_view import FeedbackNoteView
from pycodex.tui.bottom_pane.feedback_view import feedback_classification
from pycodex.tui.bottom_pane.feedback_view import feedback_disabled_params
from pycodex.tui.bottom_pane.feedback_view import feedback_selection_params
from pycodex.tui.bottom_pane.feedback_view import feedback_success_cell
from pycodex.tui.bottom_pane.feedback_view import feedback_title_and_placeholder
from pycodex.tui.bottom_pane.feedback_view import feedback_upload_consent_params
from pycodex.tui.bottom_pane.feedback_view import issue_url_for_category
from pycodex.tui.bottom_pane.feedback_view import should_show_feedback_connectivity_details


def test_feedback_title_placeholder_and_classification_matrix():
    assert feedback_title_and_placeholder(FeedbackCategory.BAD_RESULT)[0] == "Tell us more (bad result)"
    assert feedback_title_and_placeholder(FeedbackCategory.GOOD_RESULT)[0] == "Tell us more (good result)"
    assert feedback_title_and_placeholder(FeedbackCategory.BUG)[0] == "Tell us more (bug)"
    assert feedback_title_and_placeholder(FeedbackCategory.SAFETY_CHECK)[1].startswith("(optional) Share what was refused")
    assert feedback_classification(FeedbackCategory.OTHER) == "other"


def test_submit_feedback_emits_submit_event_with_trimmed_note_and_empty_note():
    events = []
    view = FeedbackNoteView.new(FeedbackCategory.BUG, "turn-123", events, True)
    view.textarea.insert_str("  something broke  ")

    view.submit()

    assert events == [
        {
            "type": "SubmitFeedback",
            "category": FeedbackCategory.BUG,
            "reason": "something broke",
            "turn_id": "turn-123",
            "include_logs": True,
        }
    ]
    assert view.is_complete()

    events = []
    empty = FeedbackNoteView.new(FeedbackCategory.GOOD_RESULT, None, events, False)
    empty.submit()
    assert events[0]["reason"] is None
    assert events[0]["include_logs"] is False


def test_key_paste_height_cursor_and_render_contracts():
    events = []
    view = FeedbackNoteView.new(FeedbackCategory.SAFETY_CHECK, None, events, True)

    assert view.handle_paste("") is False
    assert view.handle_paste("hello") is True
    assert view.cursor_pos((5, 10, 40, 6)) == (12, 12)
    assert view.desired_height(40) == 5

    lines = view.render((0, 0, 60, 10))
    assert lines[0].text.startswith("▌Tell us more (safety check)")
    assert "hello" in [line.text for line in lines]

    view.handle_key_event("esc")
    assert view.is_complete()


def test_connectivity_details_only_for_non_good_result_with_diagnostics():
    diagnostics = FeedbackDiagnostics.new(
        [
            FeedbackDiagnostic(
                headline="Proxy environment variables are set and may affect connectivity.",
                details=["HTTP_PROXY = http://proxy.example.com:8080"],
            )
        ]
    )

    assert should_show_feedback_connectivity_details(FeedbackCategory.BUG, diagnostics)
    assert not should_show_feedback_connectivity_details(FeedbackCategory.GOOD_RESULT, diagnostics)
    assert not should_show_feedback_connectivity_details(FeedbackCategory.BAD_RESULT, FeedbackDiagnostics())


def test_issue_url_and_feedback_success_copy_matrix():
    assert issue_url_for_category(FeedbackCategory.BUG, "thread-1", FeedbackAudience.OPEN_AI_EMPLOYEE) == CODEX_FEEDBACK_INTERNAL_URL
    assert issue_url_for_category(FeedbackCategory.GOOD_RESULT, "thread-1", FeedbackAudience.EXTERNAL) is None
    assert (
        issue_url_for_category(FeedbackCategory.BUG, "t", FeedbackAudience.EXTERNAL)
        == f"{BASE_CLI_BUG_ISSUE_URL}&steps=Uploaded%20thread:%20t"
    )

    external = feedback_success_cell(FeedbackCategory.BUG, True, "thread-1", FeedbackAudience.EXTERNAL).text()
    assert "Feedback uploaded. Please open an issue using the following URL:" in external
    assert "thread-1" in external

    employee = feedback_success_cell(FeedbackCategory.BUG, True, "thread-2", FeedbackAudience.OPEN_AI_EMPLOYEE).text()
    assert "Please report this in #codex-feedback" in employee
    assert "https://go/codex-feedback/thread-2" in employee

    good = feedback_success_cell(FeedbackCategory.GOOD_RESULT, False, "thread-3", FeedbackAudience.EXTERNAL).text()
    assert "Feedback recorded (no logs). Thanks for the feedback!" in good
    assert "Thread ID: thread-3" in good


def test_feedback_selection_disabled_and_upload_consent_params():
    events = []
    params = feedback_selection_params(events)
    assert params.title == "How was this?"
    assert [item.name for item in params.items] == ["bug", "bad result", "good result", "safety check", "other"]
    params.items[0].actions[0](None)
    assert events == [{"type": "OpenFeedbackConsent", "category": FeedbackCategory.BUG}]

    disabled = feedback_disabled_params()
    assert disabled.title == "Sending feedback is disabled"
    assert disabled.items[0].name == "Close"
    assert disabled.items[0].dismiss_on_select


def test_feedback_upload_consent_lists_attachments_and_diagnostics():
    diagnostics = FeedbackDiagnostics.new(
        [FeedbackDiagnostic("Proxy environment variables are set and may affect connectivity.", ["HTTP_PROXY = proxy"])]
    )
    events = []
    params = feedback_upload_consent_params(
        events,
        FeedbackCategory.BUG,
        "rollout.jsonl",
        "auto-review-rollout.jsonl",
        True,
        diagnostics,
    )

    header_text = "\n".join(line.text for line in params.header)
    assert DOCTOR_REPORT_ATTACHMENT_FILENAME in header_text
    assert WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME in header_text
    assert FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME in header_text
    assert "rollout.jsonl" in header_text
    assert "auto-review-rollout.jsonl" in header_text
    assert "Connectivity diagnostics" in header_text

    params.items[0].actions[0](None)
    params.items[1].actions[0](None)
    assert events == [
        {"type": "OpenFeedbackNote", "category": FeedbackCategory.BUG, "include_logs": True},
        {"type": "OpenFeedbackNote", "category": FeedbackCategory.BUG, "include_logs": False},
    ]
