"""Parity tests for ``codex-tui/src/onboarding/onboarding_screen.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pycodex.tui.onboarding.onboarding_screen import (
    ApiKeyEntryContext,
    FrameRequesterModel,
    OnboardingScreen,
    Step,
    StepState,
    persist_selected_trust,
    suppress_quit_while_typing_api_key,
)
from pycodex.tui.onboarding.trust_directory import TrustDirectorySelection, TrustDirectoryWidget


@dataclass
class DummyStep:
    state: StepState
    key_events: list | None = None
    pastes: list | None = None
    suppress: bool = False

    def __post_init__(self):
        self.key_events = [] if self.key_events is None else self.key_events
        self.pastes = [] if self.pastes is None else self.pastes

    def get_step_state(self):
        return self.state

    def handle_key_event(self, event):
        self.key_events.append(event)

    def handle_paste(self, text):
        self.pastes.append(text)

    def should_suppress_animations(self):
        return self.suppress


@dataclass
class AuthStep(DummyStep):
    api_active: bool = False
    api_has_text: bool = False
    cancelled: bool = False

    def is_api_key_entry_active(self):
        return self.api_active

    def api_key_entry_has_text(self):
        return self.api_has_text

    def cancel_active_attempt(self):
        self.cancelled = True


def test_suppress_quit_while_typing_api_key_contract():
    assert suppress_quit_while_typing_api_key({"key": "q"}, ApiKeyEntryContext(active=True, has_text=True))
    assert not suppress_quit_while_typing_api_key({"key": "q"}, ApiKeyEntryContext(active=True, has_text=False))
    assert not suppress_quit_while_typing_api_key({"key": "x", "modifiers": {"control"}}, ApiKeyEntryContext(active=True, has_text=True))
    assert not suppress_quit_while_typing_api_key({"key": "x"}, ApiKeyEntryContext(active=False, has_text=True))


def test_current_steps_stop_at_first_in_progress_and_skip_hidden():
    screen = OnboardingScreen(
        steps=[
            Step("welcome", DummyStep(StepState.Hidden)),
            Step("auth", DummyStep(StepState.Complete)),
            Step("trust", DummyStep(StepState.InProgress)),
            Step("later", DummyStep(StepState.InProgress)),
        ]
    )

    assert [step.kind for step in screen.current_steps()] == ["auth", "trust"]
    assert not screen.is_done()

    screen.steps[2].widget.state = StepState.Complete
    screen.steps[3].widget.state = StepState.Complete
    assert screen.is_done()


def test_quit_cancels_in_progress_auth_and_exits():
    requester = FrameRequesterModel()
    auth = AuthStep(StepState.InProgress)
    screen = OnboardingScreen(request_frame=requester, steps=[Step("auth", auth)])

    screen.handle_key_event({"kind": "press", "key": "q"})

    assert auth.cancelled
    assert screen.should_exit()
    assert screen.is_done_value
    assert requester.scheduled == 1


def test_printable_quit_is_routed_to_auth_when_api_key_has_text():
    requester = FrameRequesterModel()
    auth = AuthStep(StepState.InProgress, api_active=True, api_has_text=True)
    screen = OnboardingScreen(request_frame=requester, steps=[Step("auth", auth)])

    event = {"kind": "press", "key": "q"}
    screen.handle_key_event(event)

    assert not screen.should_exit()
    assert auth.key_events == [event]
    assert requester.scheduled == 1


def test_release_events_do_not_schedule_or_route():
    requester = FrameRequesterModel()
    step = DummyStep(StepState.InProgress)
    screen = OnboardingScreen(request_frame=requester, steps=[Step("trust", step)])

    screen.handle_key_event({"kind": "release", "key": "enter"})

    assert step.key_events == []
    assert requester.scheduled == 0


def test_welcome_always_receives_non_quit_keys_then_active_step():
    welcome = DummyStep(StepState.Complete)
    trust = DummyStep(StepState.InProgress)
    event = {"kind": "press", "key": "down"}
    screen = OnboardingScreen(steps=[Step("welcome", welcome), Step("trust", trust)])

    screen.handle_key_event(event)

    assert welcome.key_events == [event]
    assert trust.key_events == [event]


def test_handle_paste_routes_to_active_step_and_ignores_empty():
    requester = FrameRequesterModel()
    complete = DummyStep(StepState.Complete)
    active = DummyStep(StepState.InProgress)
    screen = OnboardingScreen(request_frame=requester, steps=[Step("welcome", complete), Step("auth", active)])

    screen.handle_paste("")
    assert requester.scheduled == 0
    screen.handle_paste("secret")

    assert complete.pastes == []
    assert active.pastes == ["secret"]
    assert requester.scheduled == 1


@pytest.mark.asyncio
async def test_trust_persistence_failure_keeps_trust_step_in_progress():
    widget = TrustDirectoryWidget(
        cwd=Path("/workspace/project"),
        trust_target=Path("/workspace/project"),
        selection=TrustDirectorySelection.Trust,
        highlighted=TrustDirectorySelection.Trust,
    )
    screen = OnboardingScreen(steps=[Step("trust", widget)])

    persisted = await persist_selected_trust(screen, None)

    assert not persisted
    assert widget.selection is None
    assert widget.get_step_state().value == "in_progress"
    assert widget.error is not None and "app server unavailable" in widget.error


@pytest.mark.asyncio
async def test_trust_persistence_success_returns_true():
    widget = TrustDirectoryWidget(
        cwd=Path("/workspace/project"),
        trust_target=Path("/workspace/project"),
        selection=TrustDirectorySelection.Trust,
        highlighted=TrustDirectorySelection.Trust,
    )
    screen = OnboardingScreen(steps=[Step("trust", widget)])
    calls = []

    async def write(handle, target):
        calls.append((handle, target))

    assert await persist_selected_trust(screen, "handle", write_trusted_project_fn=write)
    assert calls == [("handle", Path("/workspace/project"))]
