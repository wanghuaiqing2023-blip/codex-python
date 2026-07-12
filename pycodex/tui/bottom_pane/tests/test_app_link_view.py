from pycodex.tui.bottom_pane.app_link_view import AppLinkScreen
from pycodex.tui.bottom_pane.app_link_view import AppLinkSuggestionType
from pycodex.tui.bottom_pane.app_link_view import AppLinkView
from pycodex.tui.bottom_pane.app_link_view import AppLinkViewParams
from pycodex.tui.bottom_pane.app_link_view import is_allowed_chatgpt_auth_host
from pycodex.tui.bottom_pane.app_link_view import validate_external_url


def _params(**overrides):
    base = dict(
        app_id="connector_google_calendar",
        title="Google Calendar",
        description="Plan events and schedules.",
        instructions="Install this app in your browser, then return here.",
        url="https://example.test/google-calendar",
        is_installed=False,
        is_enabled=False,
        suggest_reason=None,
        suggestion_type=None,
        elicitation_target=None,
    )
    base.update(overrides)
    return AppLinkViewParams(**base)


# Rust source: codex/codex-rs/tui/src/bottom_pane/app_link_view.rs
def test_validate_external_url_and_chatgpt_auth_hosts():
    assert validate_external_url("https://example.test/path") == "https://example.test/path"
    assert validate_external_url("http://example.test/path") is None
    assert validate_external_url("https://user@example.test/path") is None
    assert validate_external_url("https://evil.test/path", require_chatgpt_host=True) is None
    assert validate_external_url("https://apps.chatgpt.com/auth", require_chatgpt_host=True)
    assert is_allowed_chatgpt_auth_host("CHATGPT-STAGING.com")
    assert is_allowed_chatgpt_auth_host("foo.chatgpt.com")


def test_codex_apps_auth_url_elicitation_builds_auth_app_link_params():
    request = {
        "type": "Url",
        "message": "Reconnect Google Calendar on ChatGPT.",
        "url": "https://chatgpt.com/apps/google-calendar",
        "elicitation_id": "fallback_id",
        "meta": {
            "_codex_apps": {
                "connector_auth_failure": {
                    "is_auth_failure": True,
                    "connector_id": "connector_google_calendar",
                    "connector_name": "Google Calendar",
                }
            }
        },
    }

    params = AppLinkViewParams.from_url_app_server_request("thread-1", "codex_apps", "request-1", request)

    assert params is not None
    assert params.app_id == "connector_google_calendar"
    assert params.title == "Google Calendar"
    assert params.suggestion_type is AppLinkSuggestionType.AUTH
    assert params.elicitation_target is not None


def test_generic_url_elicitation_builds_generic_params_and_rejects_bad_url():
    request = {
        "type": "Url",
        "message": "Review payment.",
        "url": "https://payments.example/checkout/123",
        "elicitation_id": "payment-123",
    }

    params = AppLinkViewParams.from_url_app_server_request("thread-1", "payments", "request-2", request)

    assert params is not None
    assert params.title == "Action required"
    assert params.description == "Server: payments"
    assert params.suggestion_type is AppLinkSuggestionType.EXTERNAL_ACTION

    bad = dict(request, url="file:///tmp/nope")
    assert AppLinkViewParams.from_url_app_server_request("thread-1", "payments", "request-2", bad) is None


def test_installed_app_actions_toggle_and_emit_event():
    events = []
    view = AppLinkView.new(_params(is_installed=True, is_enabled=True), events)

    assert view.action_labels() == ["Manage on ChatGPT", "Disable app", "Back"]
    view.selected_action = 1
    view.activate_selected_action()

    assert view.is_enabled is False
    assert view.action_labels()[1] == "Enable app"
    assert events == [{"type": "SetAppEnabled", "id": "connector_google_calendar", "enabled": False}]


def test_tool_suggestion_open_confirm_accept_and_refresh_for_codex_apps():
    events = []
    target = {"thread_id": "thread-1", "server_name": "codex_apps", "request_id": "request-1"}
    params = _params(
        suggestion_type=AppLinkSuggestionType.INSTALL,
        elicitation_target=type("Target", (), target)(),
    )
    view = AppLinkView.new(params, events)

    view.activate_selected_action()
    assert events[0] == {"type": "OpenUrlInBrowser", "url": "https://example.test/google-calendar"}
    assert view.screen is AppLinkScreen.INSTALL_CONFIRMATION

    view.activate_selected_action()
    assert events[1] == {"type": "RefreshConnectors", "force_refetch": True}
    assert events[2]["type"] == "ResolveElicitation"
    assert events[2]["decision"] == "Accept"
    assert view.is_complete()


def test_generic_external_action_completion_accepts_without_connector_refresh():
    events = []
    target = type(
        "Target",
        (),
        {"thread_id": "thread-1", "server_name": "payments", "request_id": "request-2"},
    )()
    view = AppLinkView.new(
        _params(
            app_id="payment-123",
            title="Action required",
            description="Server: payments",
            instructions="Complete the requested action in your browser, then return here.",
            url="https://payments.example/checkout/123",
            is_installed=True,
            is_enabled=True,
            suggestion_type=AppLinkSuggestionType.EXTERNAL_ACTION,
            elicitation_target=target,
        ),
        events,
    )

    assert view.action_labels() == ["Open link", "Back"]
    view.activate_selected_action()
    assert view.screen is AppLinkScreen.INSTALL_CONFIRMATION
    assert view.action_labels() == ["I finished", "Back"]

    view.activate_selected_action()

    assert events == [
        {"type": "OpenUrlInBrowser", "url": "https://payments.example/checkout/123"},
        {
            "type": "ResolveElicitation",
            "thread_id": "thread-1",
            "server_name": "payments",
            "request_id": "request-2",
            "decision": "Accept",
            "content": None,
            "meta": None,
        },
    ]
    assert view.is_complete()


def test_decline_enable_suggestion_and_terminal_title_action():
    events = []
    target = type("Target", (), {"thread_id": "thread-1", "server_name": "codex_apps", "request_id": "request-1"})()
    view = AppLinkView.new(
        _params(
            is_installed=True,
            is_enabled=False,
            suggestion_type=AppLinkSuggestionType.ENABLE,
            elicitation_target=target,
        ),
        events,
    )

    assert view.terminal_title_requires_action()
    view.handle_key_event("2")
    assert events[0] == {"type": "SetAppEnabled", "id": "connector_google_calendar", "enabled": True}
    assert events[1]["decision"] == "Accept"
    assert view.is_complete()


def test_content_lines_include_browser_url_and_keep_url_like_token_unsplit():
    url_like = "example.test/api/v1/projects/alpha-team/releases/2026-02-17/builds/1234567890"
    view = AppLinkView.new(_params(is_installed=True, is_enabled=True, url=url_like))
    view.screen = AppLinkScreen.INSTALL_CONFIRMATION

    rendered = [line.text for line in view.content_lines(40)]

    assert sum(1 for line in rendered if url_like in line) == 1


def test_selection_navigation_back_and_dismiss_matching_request():
    view = AppLinkView.new(_params(is_installed=True, is_enabled=True))

    view.move_selection_next()
    view.move_selection_next()
    view.move_selection_next()
    assert view.selected_action == 2
    view.move_selection_prev()
    assert view.selected_action == 1

    target = type("Target", (), {"thread_id": "thread-1", "server_name": "codex_apps", "request_id": "request-1"})()
    tool_view = AppLinkView.new(_params(suggestion_type=AppLinkSuggestionType.ENABLE, elicitation_target=target))
    assert tool_view.dismiss_app_server_request({"server_name": "other", "request_id": "request-1"}) is False
    assert tool_view.dismiss_app_server_request({"server_name": "codex_apps", "request_id": "request-1"}) is True
    assert tool_view.is_complete()


def test_url_request_rejects_non_url_variant_and_missing_auth_meta():
    """Rust AppLinkViewParams::from_url_app_server_request only accepts Url requests and valid auth meta."""

    non_url = {"type": "Form", "message": "nope", "url": "https://chatgpt.com/auth", "elicitation_id": "id"}
    assert AppLinkViewParams.from_url_app_server_request("thread-1", "codex_apps", "request-1", non_url) is None

    missing_meta = {
        "type": "Url",
        "message": "Reconnect.",
        "url": "https://chatgpt.com/auth",
        "elicitation_id": "fallback_id",
        "meta": {},
    }
    assert AppLinkViewParams.from_url_app_server_request("thread-1", "codex_apps", "request-1", missing_meta) is None

    not_auth_failure = {
        "type": "Url",
        "message": "Reconnect.",
        "url": "https://chatgpt.com/auth",
        "elicitation_id": "fallback_id",
        "meta": {"_codex_apps": {"connector_auth_failure": {"is_auth_failure": False}}},
    }
    assert AppLinkViewParams.from_url_app_server_request("thread-1", "codex_apps", "request-1", not_auth_failure) is None


def test_codex_apps_auth_url_requires_allowed_chatgpt_host():
    """Rust validate_external_url requires chatgpt host for codex_apps auth URLs."""

    request = {
        "type": "Url",
        "message": "Reconnect.",
        "url": "https://evil.example/auth",
        "elicitation_id": "fallback_id",
        "meta": {
            "_codex_apps": {
                "connector_auth_failure": {
                    "is_auth_failure": True,
                    "connector_id": "connector_google_calendar",
                    "connector_name": "Google Calendar",
                }
            }
        },
    }

    assert AppLinkViewParams.from_url_app_server_request("thread-1", "codex_apps", "request-1", request) is None


def test_codex_apps_auth_url_trims_and_falls_back_connector_metadata():
    """Rust auth URL params trim connector id/name and fall back to elicitation id."""

    request = {
        "type": "Url",
        "message": "Reconnect.",
        "url": "https://chatgpt-staging.com/apps/auth",
        "elicitation_id": "fallback_id",
        "meta": {
            "_codex_apps": {
                "connector_auth_failure": {
                    "is_auth_failure": True,
                    "connector_id": "   ",
                    "connector_name": "  Pretty Connector  ",
                }
            }
        },
    }

    params = AppLinkViewParams.from_url_app_server_request("thread-1", "codex_apps", "request-1", request)

    assert params is not None
    assert params.app_id == "fallback_id"
    assert params.title == "Pretty Connector"
    assert params.is_installed is True
    assert params.is_enabled is True
    assert params.suggestion_type is AppLinkSuggestionType.AUTH


def test_generic_url_elicitation_accepts_non_chatgpt_https_host():
    """Rust generic URL elicitations validate HTTPS host without the ChatGPT-only restriction."""

    request = {
        "type": "Url",
        "message": "Review payment.",
        "url": "https://payments.example/checkout/123",
        "elicitation_id": "payment-123",
    }

    params = AppLinkViewParams.from_url_app_server_request("thread-1", "payments", "request-2", request)

    assert params is not None
    assert params.url == "https://payments.example/checkout/123"
    assert params.suggestion_type is AppLinkSuggestionType.EXTERNAL_ACTION
