import pytest

from pycodex.tui.onboarding.onboarding_screen import (
    ApiKeyEntryContext,
    DefaultAuthModeWidget,
    DefaultTrustDirectoryWidget,
    FrameRequesterModel,
    OnboardingScreen,
    OnboardingScreenArgs,
    Step,
    StepState,
    persist_selected_trust,
    run_onboarding_app,
    suppress_quit_while_typing_api_key,
)


class Config:
    cwd = "/workspace/project"
    forced_login_method = None
    animations = True


def test_suppress_quit_while_typing_api_key_matches_rust_rules() -> None:
    assert suppress_quit_while_typing_api_key(
        {"kind": "press", "key": "q"},
        ApiKeyEntryContext(active=True, has_text=True),
    )
    assert not suppress_quit_while_typing_api_key(
        {"kind": "press", "key": "q"},
        ApiKeyEntryContext(active=True, has_text=False),
    )
    assert not suppress_quit_while_typing_api_key(
        {"kind": "press", "key": "x", "modifiers": {"control"}},
        ApiKeyEntryContext(active=True, has_text=True),
    )
    assert not suppress_quit_while_typing_api_key(
        {"kind": "press", "key": "x"},
        ApiKeyEntryContext(active=False, has_text=True),
    )


@pytest.mark.asyncio
async def test_new_builds_visible_welcome_auth_and_trust_steps() -> None:
    requester = FrameRequesterModel()
    tui = type("Tui", (), {"frame_requester": lambda self: requester})()
    args = OnboardingScreenArgs(
        show_trust_screen=True,
        show_login_screen=True,
        login_status="NotAuthenticated",
        app_server_request_handle=object(),
        config=Config(),
    )

    screen = await OnboardingScreen.new(
        tui,
        args,
        resolve_trust_target_fn=lambda cwd: cwd / ".git",
    )

    assert [step.kind for step in screen.steps] == ["welcome", "auth", "trust"]
    assert screen.steps[1].widget.highlighted_mode == "ChatGpt"
    assert str(screen.steps[2].widget.trust_target).endswith(".git")


def test_key_and_paste_routing_cancel_auth_and_schedule_frame() -> None:
    requester = FrameRequesterModel()
    auth = DefaultAuthModeWidget(login_status="NotAuthenticated")
    screen = OnboardingScreen(request_frame=requester, steps=[Step("auth", auth)])

    screen.handle_paste("secret")
    screen.handle_key_event({"kind": "press", "key": "q"})

    assert auth.pasted == ["secret"]
    assert auth.cancelled
    assert screen.is_done()
    assert screen.should_exit()
    assert requester.scheduled == 2


@pytest.mark.asyncio
async def test_trust_persistence_failure_keeps_trust_step_in_progress() -> None:
    trust = DefaultTrustDirectoryWidget(
        cwd=Config.cwd,
        trust_target=Config.cwd,
        selection="Trust",
    )
    screen = OnboardingScreen(steps=[Step("trust", trust)])

    persisted = await persist_selected_trust(screen, request_handle=None)

    assert not persisted
    assert trust.selection is None
    assert trust.get_step_state() is StepState.InProgress
    assert "app server unavailable" in trust.error


@pytest.mark.asyncio
async def test_run_onboarding_app_routes_events_and_app_notifications() -> None:
    auth = DefaultAuthModeWidget(login_status="NotAuthenticated")
    screen = OnboardingScreen(steps=[Step("auth", auth)])

    result = await run_onboarding_app(
        OnboardingScreenArgs(app_server_request_handle=object(), config=Config()),
        None,
        None,
        onboarding_screen=screen,
        events=[{"kind": "Paste", "payload": "abc"}, {"kind": "Key", "payload": {"kind": "press", "key": "q"}}],
        app_events=[{"kind": "ServerNotification", "payload": {"kind": "AccountUpdated"}}],
    )

    assert auth.pasted == ["abc"]
    assert screen.should_exit()
    assert result.should_exit
