from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pycodex.core.codex_delegate import CancellationToken
from pycodex.core.guardian.prompt import GuardianPromptMode, GuardianTranscriptCursor
from pycodex.core.guardian.review_session import (
    GuardianReviewDeadlineError,
    GuardianReviewSessionManager,
    GuardianReviewSessionOutcome,
    GuardianReviewSessionParams,
    GuardianReviewSessionReuseKey,
    append_guardian_followup_reminder,
    build_guardian_review_session_config,
    event_matches_turn,
    had_prior_review_context,
    prompt_cache_key_override_for_review_session,
    run_before_review_deadline,
    run_before_review_deadline_with_cancel,
    token_usage_delta,
    wait_for_guardian_review,
)
from pycodex.core.config.network_proxy_spec import NetworkProxySpec
from pycodex.network_proxy import NetworkProxyConfig
from pycodex.analytics import GuardianReviewSessionKind
from pycodex.core.guardian.metrics import GuardianReviewAnalyticsResult
from pycodex.protocol import (
    Event,
    EventMsg,
    SessionSource,
    SubAgentSource,
    TokenUsage,
    TurnAbortReason,
    TurnAbortedEvent,
    TurnCompleteEvent,
    ResponseItem,
)
from pycodex.core.session.session import Session


def test_guardian_prompt_cache_key_is_scoped_to_parent_thread() -> None:
    source = SessionSource.subagent(SubAgentSource.other_source("guardian"))

    assert prompt_cache_key_override_for_review_session(source, "parent-1") == "guardian:parent-1"
    assert prompt_cache_key_override_for_review_session(source, None) is None
    assert prompt_cache_key_override_for_review_session(SessionSource.cli(), "parent-1") is None
    assert (
        prompt_cache_key_override_for_review_session(
            SessionSource.subagent(SubAgentSource.other_source("other")),
            "parent-1",
        )
        is None
    )


def test_prompt_mode_and_token_delta_match_rust_contract() -> None:
    assert had_prior_review_context(GuardianPromptMode.full()) is False
    assert had_prior_review_context(GuardianPromptMode.delta(GuardianTranscriptCursor(7, 42))) is True

    start = TokenUsage(10, 8, 6, 4, 28)
    end = TokenUsage(15, 7, 10, 2, 34)
    assert token_usage_delta(start, end) == TokenUsage(5, 0, 4, 0, 6)


@pytest.mark.asyncio
async def test_deadline_and_external_cancel_produce_distinct_outcomes() -> None:
    with pytest.raises(GuardianReviewDeadlineError) as timed_out:
        await run_before_review_deadline(
            asyncio.get_running_loop().time() + 0.01,
            None,
            asyncio.sleep(1),
        )
    assert timed_out.value.outcome.kind == "timed_out"

    external_cancel = CancellationToken()
    external_cancel.cancel()
    with pytest.raises(GuardianReviewDeadlineError) as aborted:
        await run_before_review_deadline(
            asyncio.get_running_loop().time() + 1,
            external_cancel,
            asyncio.sleep(1),
        )
    assert aborted.value.outcome.kind == "aborted"


@pytest.mark.asyncio
async def test_deadline_with_cancel_only_cancels_child_on_failure() -> None:
    child = CancellationToken()
    assert await run_before_review_deadline_with_cancel(
        asyncio.get_running_loop().time() + 1,
        None,
        child,
        asyncio.sleep(0, result=42),
    ) == 42
    assert child.is_cancelled() is False

    child = CancellationToken()
    with pytest.raises(GuardianReviewDeadlineError):
        await run_before_review_deadline_with_cancel(
            asyncio.get_running_loop().time() + 0.01,
            None,
            child,
            asyncio.sleep(1),
        )
    assert child.is_cancelled() is True


def test_event_matches_expected_turn_on_both_envelope_and_terminal_payload() -> None:
    complete = Event("turn-1", EventMsg.with_payload("task_complete", TurnCompleteEvent("turn-1", "ok")))
    stale_complete = Event("turn-1", EventMsg.with_payload("task_complete", TurnCompleteEvent("old", "old")))
    aborted = Event(
        "turn-1",
        EventMsg.with_payload("turn_aborted", TurnAbortedEvent("turn-1", TurnAbortReason.INTERRUPTED)),
    )

    assert event_matches_turn(complete, "turn-1") is True
    assert event_matches_turn(stale_complete, "turn-1") is False
    assert event_matches_turn(aborted, "turn-1") is True
    assert event_matches_turn(Event("old", complete.msg), "turn-1") is False


def test_guardian_config_is_a_restricted_clone() -> None:
    parent = {
        "model": "parent-model",
        "model_reasoning_effort": "low",
        "include_skill_instructions": True,
        "include_apps_instructions": True,
        "guardian_policy_config": "tenant rules",
        "notify": ["notify-send"],
        "developer_instructions": "developer",
        "permissions": {"approval_policy": "on-request", "permission_profile": "full_access"},
        "mcp_servers": {"server": {"command": "server"}},
        "features": {
            "spawn_csv": True,
            "collab": True,
            "multi_agent_v2": True,
            "codex_hooks": True,
            "apps": True,
            "plugins": True,
            "web_search_request": True,
            "web_search_cached": True,
            "unrelated": True,
        },
    }

    guardian = build_guardian_review_session_config(parent, None, "guardian-model", "high")

    assert parent["mcp_servers"]
    assert guardian["model"] == "guardian-model"
    assert guardian["model_reasoning_effort"] == "high"
    assert guardian["include_skill_instructions"] is False
    assert guardian["include_apps_instructions"] is False
    assert guardian["notify"] is None
    assert guardian["developer_instructions"] is None
    assert guardian["permissions"] == {"approval_policy": "never", "permission_profile": "read_only"}
    assert guardian["mcp_servers"] == {}
    assert guardian["features"]["unrelated"] is True
    assert not any(guardian["features"][name] for name in guardian["features"] if name != "unrelated")
    assert "tenant rules" in guardian["base_instructions"]


def test_guardian_config_preserves_and_refreshes_parent_network_proxy() -> None:
    # Rust tests: guardian::tests::{guardian_review_session_config_preserves_parent_network_proxy,
    # guardian_review_session_config_uses_live_network_proxy_state}.
    parent_network = NetworkProxySpec.from_config_and_constraints(
        NetworkProxyConfig.from_mapping({"network": {"enabled": True}}),
        None,
        "full_access",
    )
    live_network = NetworkProxyConfig.from_mapping(
        {"network": {"enabled": True, "proxy_url": "http://127.0.0.1:4312"}}
    )
    parent = {
        "permissions": {
            "approval_policy": "on-request",
            "permission_profile": "full_access",
            "network": parent_network,
        },
        "config_layer_stack": {"requirements": {"network": None}},
        "features": {},
        "mcp_servers": {},
    }

    guardian = build_guardian_review_session_config(parent, live_network, "guardian-model", "high")

    assert parent["permissions"]["network"] is parent_network
    assert guardian["permissions"]["approval_policy"] == "never"
    assert guardian["permissions"]["permission_profile"] == "read_only"
    network = guardian["permissions"]["network"]
    assert isinstance(network, NetworkProxySpec)
    assert network is not parent_network
    assert network.base_config.network.proxy_url == "http://127.0.0.1:4312"


@pytest.mark.asyncio
async def test_followup_reminder_is_injected_as_response_item() -> None:
    # Rust source: guardian/review_session.rs::append_guardian_followup_reminder.
    injected: list[object] = []

    class ChildSession:
        async def inject_no_new_turn(self, items, current_turn_context):
            injected.extend(items)
            assert current_turn_context is None

    await append_guardian_followup_reminder(
        SimpleNamespace(codex=SimpleNamespace(session=ChildSession()))
    )

    assert len(injected) == 1
    assert isinstance(injected[0], ResponseItem)


@pytest.mark.asyncio
async def test_manager_reuses_matching_trunk_and_forks_when_trunk_is_busy() -> None:
    spawned: list[tuple[bool, object]] = []
    release = asyncio.Event()

    class FakeReviewSession:
        def __init__(self, reuse_key, ephemeral: bool) -> None:
            self.reuse_key = reuse_key
            self.review_lock = asyncio.Lock()
            self.ephemeral = ephemeral
            self.closed = False

        async def shutdown(self) -> None:
            self.closed = True

        def shutdown_in_background(self) -> None:
            self.closed = True

        async def fork_snapshot(self):
            return None

        async def refresh_last_committed_fork_snapshot(self) -> None:
            return None

    async def spawn(params, spawn_config, reuse_key, cancel_token, fork_snapshot):
        session = FakeReviewSession(reuse_key, bool(spawn_config.get("ephemeral")))
        spawned.append((session.ephemeral, fork_snapshot))
        return session

    async def run(session, params, kind, deadline):
        if params.request == "hold":
            await release.wait()
        return GuardianReviewSessionOutcome.completed("ok"), True, SimpleNamespace(kind=kind)

    manager = GuardianReviewSessionManager(spawn_review_session=spawn, run_review=run)
    base = GuardianReviewSessionParams(
        parent_session=SimpleNamespace(),
        parent_turn=SimpleNamespace(),
        spawn_config={"model": "guardian"},
        request="one",
        schema={},
        model="guardian",
    )

    first, _ = await manager.run_review(base)
    second, _ = await manager.run_review(base)
    assert first.kind == second.kind == "completed"
    assert [ephemeral for ephemeral, _ in spawned] == [False]

    holding = asyncio.create_task(manager.run_review(GuardianReviewSessionParams(**{**base.__dict__, "request": "hold"})))
    await asyncio.sleep(0)
    concurrent, _ = await manager.run_review(base)
    release.set()
    await holding

    assert concurrent.kind == "completed"
    assert [ephemeral for ephemeral, _ in spawned] == [False, True]


def test_reuse_key_changes_only_with_spawn_behavior() -> None:
    one = GuardianReviewSessionReuseKey.from_spawn_config({"model": "guardian", "cwd": "C:/work", "ephemeral": False})
    same = GuardianReviewSessionReuseKey.from_spawn_config({"model": "guardian", "cwd": "C:/work", "ephemeral": True})
    changed = GuardianReviewSessionReuseKey.from_spawn_config({"model": "other", "cwd": "C:/work"})

    assert one == same
    assert one != changed


def test_session_constructs_the_rust_owned_guardian_manager() -> None:
    session = Session(cwd=".")

    assert isinstance(session.guardian_review_session, GuardianReviewSessionManager)


@pytest.mark.asyncio
async def test_wait_ignores_terminal_events_from_prior_turns() -> None:
    events = asyncio.Queue()
    await events.put(Event("old", EventMsg.with_payload("task_complete", TurnCompleteEvent("old", "stale"))))
    await events.put(Event("turn-1", EventMsg.with_payload("error", {"message": "retrying"})))
    await events.put(Event("turn-1", EventMsg.with_payload("task_complete", TurnCompleteEvent("turn-1", "approved", time_to_first_token_ms=12))))

    class Child:
        async def next_event(self):
            return await events.get()

    session = SimpleNamespace(codex=Child())
    analytics = GuardianReviewAnalyticsResult.from_session(
        "guardian-thread",
        GuardianReviewSessionKind.TRUNK_NEW,
        "guardian",
        "high",
        False,
    )

    outcome, keep, completed = await wait_for_guardian_review(
        session,
        "turn-1",
        asyncio.get_running_loop().time() + 1,
        None,
        analytics,
    )

    assert outcome == GuardianReviewSessionOutcome.completed("approved")
    assert (keep, completed) == (True, True)
    assert analytics.time_to_first_token_ms == 12
