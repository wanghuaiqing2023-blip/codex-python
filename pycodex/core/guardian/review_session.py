"""Reusable Guardian review sessions aligned with ``guardian/review_session.rs``."""

from __future__ import annotations

import asyncio
import copy
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from pycodex.analytics import GuardianReviewSessionKind
from pycodex.core.context.guardian_followup_review_reminder import GuardianFollowupReviewReminder
from pycodex.core.guardian.metrics import GuardianReviewAnalyticsResult
from pycodex.core.guardian.prompt import (
    GuardianPromptMode,
    GuardianTranscriptCursor,
    build_guardian_prompt_items,
    guardian_policy_prompt,
    guardian_policy_prompt_with_config,
)
from pycodex.core.guardian.review import GUARDIAN_REVIEWER_NAME
from pycodex.features import Feature
from pycodex.protocol import (
    AskForApproval,
    CollaborationMode,
    Event,
    InitialHistory,
    ModeKind,
    Op,
    PermissionProfile,
    SandboxPolicy,
    SessionSource,
    Settings,
    SubAgentSource,
    ThreadSettingsOverrides,
    TokenUsage,
    TurnAbortedEvent,
    TurnCompleteEvent,
)


GUARDIAN_REVIEW_TIMEOUT_SECONDS = 90.0
GUARDIAN_INTERRUPT_DRAIN_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class GuardianReviewSessionOutcome:
    kind: str
    value: str | None = None
    error: BaseException | None = None

    @classmethod
    def completed(
        cls,
        value: str | None = None,
        error: BaseException | None = None,
    ) -> "GuardianReviewSessionOutcome":
        return cls("completed", value=value, error=error)

    @classmethod
    def prompt_build_failed(cls, error: BaseException) -> "GuardianReviewSessionOutcome":
        return cls("prompt_build_failed", error=error)

    @classmethod
    def session_failed(cls, error: BaseException) -> "GuardianReviewSessionOutcome":
        return cls("session_failed", error=error)

    @classmethod
    def timed_out(cls) -> "GuardianReviewSessionOutcome":
        return cls("timed_out")

    @classmethod
    def aborted(cls) -> "GuardianReviewSessionOutcome":
        return cls("aborted")


class GuardianReviewDeadlineError(Exception):
    def __init__(self, outcome: GuardianReviewSessionOutcome) -> None:
        super().__init__(outcome.kind)
        self.outcome = outcome


@dataclass
class GuardianReviewSessionParams:
    parent_session: Any
    parent_turn: Any
    spawn_config: Any
    request: Any
    schema: Any
    model: str
    retry_reason: str | None = None
    reasoning_effort: Any = None
    reasoning_summary: Any = None
    personality: Any = None
    external_cancel: "CancellationToken | None" = None
    spawn_codex: Callable[..., Any] | None = None


@dataclass(slots=True)
class GuardianReviewState:
    prior_review_count: int = 0
    last_reviewed_transcript_cursor: GuardianTranscriptCursor | None = None
    last_committed_fork_snapshot: "GuardianReviewForkSnapshot | None" = None


@dataclass(frozen=True, slots=True)
class GuardianReviewForkSnapshot:
    initial_history: InitialHistory
    prior_review_count: int
    last_reviewed_transcript_cursor: GuardianTranscriptCursor | None


_REUSE_KEY_FIELDS = (
    "model",
    "model_provider_id",
    "model_provider",
    "model_context_window",
    "model_auto_compact_token_limit",
    "model_auto_compact_token_limit_scope",
    "model_reasoning_effort",
    "model_reasoning_summary",
    "permissions",
    "developer_instructions",
    "base_instructions",
    "user_instructions",
    "compact_prompt",
    "cwd",
    "mcp_servers",
    "codex_linux_sandbox_exe",
    "main_execve_wrapper_exe",
    "zsh_path",
    "features",
    "use_experimental_unified_exec_tool",
)


@dataclass(frozen=True, slots=True)
class GuardianReviewSessionReuseKey:
    values: tuple[tuple[str, Any], ...]

    @classmethod
    def from_spawn_config(cls, spawn_config: Any) -> "GuardianReviewSessionReuseKey":
        return cls(tuple((name, _freeze(_field(spawn_config, name))) for name in _REUSE_KEY_FIELDS))


@dataclass(slots=True)
class GuardianReviewSession:
    codex: Any
    cancel_token: "CancellationToken"
    reuse_key: GuardianReviewSessionReuseKey
    review_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state: GuardianReviewState = field(default_factory=GuardianReviewState)

    async def shutdown(self) -> None:
        self.cancel_token.cancel()
        target = _delegate_target(self.codex)
        shutdown = getattr(target, "shutdown_and_wait", None)
        if callable(shutdown):
            await _maybe_await(shutdown())
        else:
            submit = getattr(target, "submit", None)
            if callable(submit):
                try:
                    await _maybe_await(submit(Op.simple("shutdown")))
                except Exception:
                    pass
        if _is_delegate_io(self.codex):
            for task in (self.codex.event_task, self.codex.ops_task):
                if task is not None and not task.done():
                    task.cancel()

    def shutdown_in_background(self) -> None:
        asyncio.create_task(self.shutdown())

    async def fork_snapshot(self) -> GuardianReviewForkSnapshot | None:
        return self.state.last_committed_fork_snapshot

    async def refresh_last_committed_fork_snapshot(self) -> None:
        items = await load_rollout_items_for_fork(_child_session(self.codex))
        if items:
            self.state.last_committed_fork_snapshot = GuardianReviewForkSnapshot(
                InitialHistory.forked(items),
                self.state.prior_review_count,
                self.state.last_reviewed_transcript_cursor,
            )


SpawnReviewSession = Callable[..., Awaitable[GuardianReviewSession]]
RunReview = Callable[..., Awaitable[tuple[GuardianReviewSessionOutcome, bool, GuardianReviewAnalyticsResult]]]


@dataclass(slots=True)
class _GuardianReviewSessionState:
    trunk: GuardianReviewSession | None = None
    ephemeral_reviews: list[GuardianReviewSession] = field(default_factory=list)


class GuardianReviewSessionManager:
    def __init__(
        self,
        *,
        spawn_review_session: SpawnReviewSession | None = None,
        run_review: RunReview | None = None,
    ) -> None:
        self._state = _GuardianReviewSessionState()
        self._state_lock = asyncio.Lock()
        self._spawn_review_session = spawn_review_session or spawn_guardian_review_session
        self._run_review = run_review or run_review_on_session

    async def trunk_rollout_path(self) -> Path | None:
        async with self._state_lock:
            trunk = self._state.trunk
        if trunk is None:
            return None
        session = _child_session(trunk.codex)
        await _call_optional(session, "ensure_rollout_materialized")
        return await _call_optional(session, "current_rollout_path")

    async def shutdown(self) -> None:
        async with self._state_lock:
            sessions = ([self._state.trunk] if self._state.trunk is not None else []) + self._state.ephemeral_reviews
            self._state = _GuardianReviewSessionState()
        for review_session in sessions:
            await review_session.shutdown()

    async def run_review(
        self,
        params: GuardianReviewSessionParams,
    ) -> tuple[GuardianReviewSessionOutcome, GuardianReviewAnalyticsResult]:
        deadline = asyncio.get_running_loop().time() + GUARDIAN_REVIEW_TIMEOUT_SECONDS
        reuse_key = GuardianReviewSessionReuseKey.from_spawn_config(params.spawn_config)
        stale: GuardianReviewSession | None = None
        spawned_trunk = False
        fork_snapshot: GuardianReviewForkSnapshot | None = None

        try:
            async with self._state_lock:
                trunk = self._state.trunk
                if trunk is not None and trunk.reuse_key != reuse_key and not trunk.review_lock.locked():
                    stale = trunk
                    self._state.trunk = None
                    trunk = None
                if trunk is None:
                    spawn_cancel = _new_cancellation_token()
                    trunk = await run_before_review_deadline_with_cancel(
                        deadline,
                        params.external_cancel,
                        spawn_cancel,
                        self._spawn_review_session(
                            params,
                            _clone_config(params.spawn_config),
                            reuse_key,
                            spawn_cancel,
                            None,
                        ),
                    )
                    self._state.trunk = trunk
                    spawned_trunk = True
                if trunk.reuse_key == reuse_key and not trunk.review_lock.locked():
                    await trunk.review_lock.acquire()
                    selected_trunk = trunk
                else:
                    selected_trunk = None
                    fork_snapshot = await trunk.fork_snapshot() if trunk.reuse_key == reuse_key else None
        except GuardianReviewDeadlineError as exc:
            return exc.outcome, GuardianReviewAnalyticsResult.without_session()
        except Exception as exc:
            return GuardianReviewSessionOutcome.prompt_build_failed(exc), GuardianReviewAnalyticsResult.without_session()

        if stale is not None:
            stale.shutdown_in_background()
        if selected_trunk is None:
            return await self._run_ephemeral_review(params, reuse_key, deadline, fork_snapshot)

        kind = GuardianReviewSessionKind.TRUNK_NEW if spawned_trunk else GuardianReviewSessionKind.TRUNK_REUSED
        keep = False
        try:
            outcome, keep, analytics = await self._run_review(selected_trunk, params, kind, deadline)
            if keep and outcome.kind == "completed":
                await selected_trunk.refresh_last_committed_fork_snapshot()
        finally:
            selected_trunk.review_lock.release()
        if not keep:
            async with self._state_lock:
                if self._state.trunk is selected_trunk:
                    self._state.trunk = None
            selected_trunk.shutdown_in_background()
        return outcome, analytics

    async def _run_ephemeral_review(
        self,
        params: GuardianReviewSessionParams,
        reuse_key: GuardianReviewSessionReuseKey,
        deadline: float,
        fork_snapshot: GuardianReviewForkSnapshot | None,
    ) -> tuple[GuardianReviewSessionOutcome, GuardianReviewAnalyticsResult]:
        spawn_cancel = _new_cancellation_token()
        config = _clone_config(params.spawn_config)
        _set_field(config, "ephemeral", True)
        try:
            review_session = await run_before_review_deadline_with_cancel(
                deadline,
                params.external_cancel,
                spawn_cancel,
                self._spawn_review_session(params, config, reuse_key, spawn_cancel, fork_snapshot),
            )
        except GuardianReviewDeadlineError as exc:
            return exc.outcome, GuardianReviewAnalyticsResult.without_session()
        except Exception as exc:
            return GuardianReviewSessionOutcome.prompt_build_failed(exc), GuardianReviewAnalyticsResult.without_session()
        async with self._state_lock:
            self._state.ephemeral_reviews.append(review_session)
        try:
            outcome, _, analytics = await self._run_review(
                review_session,
                params,
                GuardianReviewSessionKind.EPHEMERAL_FORKED,
                deadline,
            )
            return outcome, analytics
        finally:
            async with self._state_lock:
                if review_session in self._state.ephemeral_reviews:
                    self._state.ephemeral_reviews.remove(review_session)
            review_session.shutdown_in_background()


def had_prior_review_context(prompt_mode: GuardianPromptMode) -> bool:
    return prompt_mode.type == "delta"


def token_usage_delta(start: TokenUsage, end: TokenUsage) -> TokenUsage:
    return TokenUsage(
        max(end.input_tokens - start.input_tokens, 0),
        max(end.cached_input_tokens - start.cached_input_tokens, 0),
        max(end.output_tokens - start.output_tokens, 0),
        max(end.reasoning_output_tokens - start.reasoning_output_tokens, 0),
        max(end.total_tokens - start.total_tokens, 0),
    )


def prompt_cache_key_override_for_review_session(
    session_source: SessionSource,
    parent_thread_id: Any | None,
) -> str | None:
    source = getattr(session_source, "subagent_source", None)
    if (
        getattr(session_source, "type", None) != "subagent"
        or getattr(source, "type", None) != "other"
        or getattr(source, "other", None) != GUARDIAN_REVIEWER_NAME
        or parent_thread_id is None
    ):
        return None
    return f"guardian:{parent_thread_id}"


async def spawn_guardian_review_session(
    params: GuardianReviewSessionParams,
    spawn_config: Any,
    reuse_key: GuardianReviewSessionReuseKey,
    cancel_token: "CancellationToken",
    fork_snapshot: GuardianReviewForkSnapshot | None,
) -> GuardianReviewSession:
    initial_history = fork_snapshot.initial_history if fork_snapshot is not None else None
    prior_count = fork_snapshot.prior_review_count if fork_snapshot is not None else 0
    cursor = fork_snapshot.last_reviewed_transcript_cursor if fork_snapshot is not None else None
    spawn_codex = params.spawn_codex or _required_spawn_codex(params.parent_session, params.parent_turn)
    from pycodex.core.codex_delegate import RunCodexThreadOptions, run_codex_thread_interactive

    codex = await run_codex_thread_interactive(
        RunCodexThreadOptions(
            config=spawn_config,
            auth_manager=_service(params.parent_session, "auth_manager"),
            models_manager=_service(params.parent_session, "models_manager"),
            parent_session=params.parent_session,
            parent_ctx=params.parent_turn,
            cancel_token=cancel_token,
            subagent_source=SubAgentSource.other_source(GUARDIAN_REVIEWER_NAME),
            initial_history=initial_history,
            spawn_codex=spawn_codex,
        )
    )
    return GuardianReviewSession(
        codex,
        cancel_token,
        reuse_key,
        state=GuardianReviewState(prior_count, cursor),
    )


async def run_review_on_session(
    review_session: GuardianReviewSession,
    params: GuardianReviewSessionParams,
    guardian_session_kind: GuardianReviewSessionKind,
    deadline: float,
) -> tuple[GuardianReviewSessionOutcome, bool, GuardianReviewAnalyticsResult]:
    state = review_session.state
    send_reminder = state.prior_review_count == 1
    prompt_mode = (
        GuardianPromptMode.full()
        if state.prior_review_count == 0 or state.last_reviewed_transcript_cursor is None
        else GuardianPromptMode.delta(state.last_reviewed_transcript_cursor)
    )
    child_session = _child_session(review_session.codex)
    analytics = GuardianReviewAnalyticsResult.from_session(
        str(_field(child_session, "conversation_id", "unknown")),
        guardian_session_kind,
        params.model,
        str(params.reasoning_effort) if params.reasoning_effort is not None else None,
        had_prior_review_context(prompt_mode),
    )
    if send_reminder:
        await append_guardian_followup_reminder(review_session)
    try:
        await _sync_approved_hosts(params.parent_session, child_session)
        prompt_items = await run_before_review_deadline(
            deadline,
            params.external_cancel,
            build_guardian_prompt_items(params.parent_session, params.retry_reason, params.request, prompt_mode),
        )
    except GuardianReviewDeadlineError as exc:
        return exc.outcome, False, analytics
    except Exception as exc:
        return GuardianReviewSessionOutcome.prompt_build_failed(exc), False, analytics

    usage_start = await _total_token_usage(child_session)
    thread_settings = ThreadSettingsOverrides(
        cwd=Path(_field(params.parent_turn, "cwd", ".")),
        approval_policy=AskForApproval.NEVER,
        sandbox_policy=SandboxPolicy.new_read_only_policy(),
        permission_profile=PermissionProfile.read_only(),
        summary=params.reasoning_summary,
        personality=params.personality,
        collaboration_mode=CollaborationMode(
            ModeKind.DEFAULT,
            Settings(params.model, params.reasoning_effort, None),
        ),
    )
    op = Op.user_input(
        prompt_items.items,
        final_output_json_schema=params.schema,
        thread_settings=thread_settings,
    )
    try:
        child_turn_id = await run_before_review_deadline(
            deadline,
            params.external_cancel,
            _submit_child(review_session.codex, op),
        )
    except GuardianReviewDeadlineError as exc:
        return exc.outcome, False, analytics
    except Exception as exc:
        return GuardianReviewSessionOutcome.session_failed(exc), False, analytics
    if not isinstance(child_turn_id, str) or not child_turn_id:
        return (
            GuardianReviewSessionOutcome.session_failed(
                RuntimeError("guardian child did not return a turn id")
            ),
            False,
            analytics,
        )

    analytics.reviewed_action_truncated = prompt_items.reviewed_action_truncated
    outcome, keep, completed = await wait_for_guardian_review(
        review_session,
        child_turn_id,
        deadline,
        params.external_cancel,
        analytics,
    )
    if outcome.kind == "completed":
        if completed:
            usage_end = await _total_token_usage(child_session)
            if usage_start is not None and usage_end is not None:
                analytics.token_usage = token_usage_delta(usage_start, usage_end)
        state.prior_review_count += 1
        state.last_reviewed_transcript_cursor = prompt_items.transcript_cursor
    return outcome, keep, analytics


async def append_guardian_followup_reminder(review_session: GuardianReviewSession) -> None:
    session = _child_session(review_session.codex)
    inject = getattr(session, "inject_no_new_turn", None)
    if callable(inject):
        reminder = GuardianFollowupReviewReminder().into_response_item()
        await _maybe_await(inject([reminder], None))


async def load_rollout_items_for_fork(session: Any) -> tuple[Any, ...] | None:
    if session is None:
        return None
    await _call_optional(session, "try_ensure_rollout_materialized")
    await _call_optional(session, "flush_rollout")
    live_thread = await _call_optional(session, "live_thread_for_persistence", "guardian review fork")
    if live_thread is None:
        return None
    history = await _call_optional(live_thread, "load_history", True)
    items = _field(history, "items")
    return tuple(items) if items is not None else None


async def wait_for_guardian_review(
    review_session: GuardianReviewSession,
    expected_turn_id: str,
    deadline: float,
    external_cancel: "CancellationToken | None",
    analytics_result: GuardianReviewAnalyticsResult,
) -> tuple[GuardianReviewSessionOutcome, bool, bool]:
    last_error: str | None = None
    while True:
        try:
            event = await run_before_review_deadline(
                deadline,
                external_cancel,
                _next_event(review_session.codex),
            )
        except GuardianReviewDeadlineError as exc:
            keep = await interrupt_and_drain_turn(review_session.codex, expected_turn_id)
            return exc.outcome, keep, False
        except Exception as exc:
            return GuardianReviewSessionOutcome.completed(error=exc), False, False
        if not event_matches_turn(event, expected_turn_id):
            continue
        kind = _event_kind(event)
        payload = _event_payload(event)
        if kind in {"task_complete", "turn_complete"}:
            analytics_result.time_to_first_token_ms = _field(payload, "time_to_first_token_ms")
            message = _field(payload, "last_agent_message")
            if message is None and last_error is not None:
                return GuardianReviewSessionOutcome.completed(error=RuntimeError(last_error)), True, True
            return GuardianReviewSessionOutcome.completed(message), True, True
        if kind == "error":
            last_error = str(_field(payload, "message", payload))
        elif kind in {"turn_aborted", "task_aborted"}:
            return GuardianReviewSessionOutcome.aborted(), True, False


def event_matches_turn(event: Event, expected_turn_id: str) -> bool:
    if getattr(event, "id", None) != expected_turn_id:
        return False
    payload = _event_payload(event)
    kind = _event_kind(event)
    if kind in {"task_complete", "turn_complete"} and isinstance(payload, TurnCompleteEvent):
        return payload.turn_id == expected_turn_id
    if kind in {"turn_aborted", "task_aborted"} and isinstance(payload, TurnAbortedEvent):
        return payload.turn_id == expected_turn_id
    return True


def build_guardian_review_session_config(
    parent_config: Any,
    live_network_config: Any,
    active_model: str,
    reasoning_effort: Any,
) -> Any:
    guardian = _clone_config(parent_config)
    policy = _field(parent_config, "guardian_policy_config")
    _set_field(guardian, "model", active_model)
    _set_field(guardian, "model_reasoning_effort", reasoning_effort)
    _set_field(guardian, "include_skill_instructions", False)
    _set_field(
        guardian,
        "base_instructions",
        guardian_policy_prompt_with_config(policy) if policy else guardian_policy_prompt(),
    )
    _set_field(guardian, "notify", None)
    _set_field(guardian, "developer_instructions", None)
    _set_field(guardian, "include_apps_instructions", False)
    permissions = _field(guardian, "permissions")
    preserve_network = _field(permissions, "network") is not None
    if isinstance(permissions, Mapping):
        restricted_permissions = dict(permissions)
        restricted_permissions["approval_policy"] = "never"
        restricted_permissions["permission_profile"] = "read_only"
        _set_field(guardian, "permissions", restricted_permissions)
        permissions = restricted_permissions
    elif permissions is not None:
        approval = _field(permissions, "approval_policy")
        setter = getattr(approval, "set", None)
        if callable(setter):
            setter(AskForApproval.NEVER)
        else:
            _set_field(permissions, "approval_policy", AskForApproval.NEVER)
        set_profile = getattr(permissions, "set_permission_profile", None)
        if callable(set_profile):
            set_profile(PermissionProfile.read_only())
        else:
            _set_field(permissions, "permission_profile", PermissionProfile.read_only())
    if live_network_config is not None and preserve_network:
        from pycodex.core.config.network_proxy_spec import NetworkProxySpec

        layer_stack = _field(guardian, "config_layer_stack")
        requirements = _field(layer_stack, "requirements")
        if callable(requirements):
            requirements = requirements()
        network_requirements = _field(requirements, "network")
        network_constraints = _field(network_requirements, "value", network_requirements)
        permission_profile = _field(permissions, "permission_profile", PermissionProfile.read_only())
        _set_field(
            permissions,
            "network",
            NetworkProxySpec.from_config_and_constraints(
                live_network_config,
                network_constraints,
                permission_profile,
            ),
        )
    mcp_servers = _field(guardian, "mcp_servers")
    setter = getattr(mcp_servers, "set", None)
    if callable(setter):
        setter({})
    else:
        _set_field(guardian, "mcp_servers", {})
    disabled = (
        "spawn_csv",
        "collab",
        "multi_agent_v2",
        "codex_hooks",
        "apps",
        "plugins",
        "web_search_request",
        "web_search_cached",
    )
    features = _field(guardian, "features")
    if isinstance(features, Mapping):
        mutable = dict(features)
        for name in disabled:
            mutable[name] = False
        _set_field(guardian, "features", mutable)
    elif features is not None:
        for name in disabled:
            feature = next((item for item in Feature if item.value == name), name)
            disable = getattr(features, "disable", None)
            if callable(disable):
                disable(feature)
    return guardian


async def run_before_review_deadline(
    deadline: float,
    external_cancel: "CancellationToken | None",
    future: Awaitable[Any],
) -> Any:
    task = asyncio.ensure_future(future)
    timeout = asyncio.create_task(asyncio.sleep(max(deadline - asyncio.get_running_loop().time(), 0)))
    cancel = asyncio.create_task(external_cancel.cancelled()) if external_cancel is not None else None
    waits = {task, timeout}
    if cancel is not None:
        waits.add(cancel)
    done, pending = await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    if task in done:
        for item in pending:
            item.cancel()
        return task.result()
    task.cancel()
    for item in pending:
        item.cancel()
    if cancel is not None and cancel in done:
        raise GuardianReviewDeadlineError(GuardianReviewSessionOutcome.aborted())
    raise GuardianReviewDeadlineError(GuardianReviewSessionOutcome.timed_out())


async def run_before_review_deadline_with_cancel(
    deadline: float,
    external_cancel: "CancellationToken | None",
    cancel_token: "CancellationToken",
    future: Awaitable[Any],
) -> Any:
    try:
        return await run_before_review_deadline(deadline, external_cancel, future)
    except GuardianReviewDeadlineError:
        cancel_token.cancel()
        raise


async def interrupt_and_drain_turn(codex: Any, expected_turn_id: str) -> bool:
    try:
        await _submit_child(codex, Op.simple("interrupt"))
        deadline = asyncio.get_running_loop().time() + GUARDIAN_INTERRUPT_DRAIN_TIMEOUT_SECONDS
        while True:
            event = await asyncio.wait_for(
                _next_event(codex),
                max(deadline - asyncio.get_running_loop().time(), 0),
            )
            if event_matches_turn(event, expected_turn_id) and _event_kind(event) in {
                "task_complete",
                "turn_complete",
                "turn_aborted",
                "task_aborted",
            }:
                return True
    except Exception:
        return False


async def _submit_child(codex: Any, op: Op) -> Any:
    target = _delegate_target(codex)
    submit = getattr(target, "submit", None)
    if not callable(submit):
        raise TypeError("guardian child must expose submit()")
    return await _maybe_await(submit(op))


async def _next_event(codex: Any) -> Event:
    next_event = getattr(codex, "next_event", None)
    if not callable(next_event):
        raise TypeError("guardian child must expose next_event()")
    return await _maybe_await(next_event())


async def _total_token_usage(session: Any) -> TokenUsage | None:
    value = await _call_optional(session, "total_token_usage")
    if value is None or isinstance(value, TokenUsage):
        return value
    if isinstance(value, Mapping):
        return TokenUsage.from_mapping(value)
    return None


async def _sync_approved_hosts(parent_session: Any, child_session: Any) -> None:
    parent = _service(parent_session, "network_approval")
    child = _service(child_session, "network_approval")
    sync = getattr(parent, "sync_session_approved_hosts_to", None)
    if callable(sync) and child is not None:
        await _maybe_await(sync(child))


def _child_session(codex: Any) -> Any:
    target = _delegate_target(codex)
    return _field(target, "session")


def _is_delegate_io(value: Any) -> bool:
    return all(hasattr(value, name) for name in ("codex", "events_rx", "ops_tx"))


def _delegate_target(value: Any) -> Any:
    return value.codex if _is_delegate_io(value) else value


def _new_cancellation_token() -> Any:
    from pycodex.core.codex_delegate import CancellationToken

    return CancellationToken()


def _event_kind(event: Any) -> str:
    msg = getattr(event, "msg", None)
    kind = getattr(msg, "type", None) or getattr(msg, "kind", None)
    if callable(kind):
        kind = kind()
    if kind is None and isinstance(msg, Mapping):
        kind = msg.get("type")
    return str(kind or "")


def _event_payload(event: Any) -> Any:
    msg = getattr(event, "msg", None)
    return getattr(msg, "payload", msg)


def _required_spawn_codex(parent_session: Any, parent_turn: Any) -> Callable[..., Any]:
    for source in (parent_turn, parent_session, _field(parent_session, "services")):
        spawn = _field(source, "spawn_codex")
        if callable(spawn):
            return spawn
    raise TypeError("Guardian review requires a spawn_codex callable")


def _service(value: Any, name: str) -> Any:
    return _field(_field(value, "services"), name, _field(value, name))


def _clone_config(config: Any) -> Any:
    clone = getattr(config, "clone", None)
    return clone() if callable(clone) else copy.deepcopy(config)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _set_field(value: Any, name: str, item: Any) -> None:
    if isinstance(value, dict):
        value[name] = item
    else:
        setattr(value, name, item)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_freeze(item) for item in value)
    if hasattr(value, "__dict__"):
        return _freeze(vars(value))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


async def _call_optional(value: Any, name: str, *args: Any) -> Any:
    method = getattr(value, name, None) if value is not None else None
    return await _maybe_await(method(*args)) if callable(method) else None


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


__all__ = [
    "GuardianReviewDeadlineError",
    "GuardianReviewForkSnapshot",
    "GuardianReviewSession",
    "GuardianReviewSessionManager",
    "GuardianReviewSessionOutcome",
    "GuardianReviewSessionParams",
    "GuardianReviewSessionReuseKey",
    "GuardianReviewState",
    "append_guardian_followup_reminder",
    "build_guardian_review_session_config",
    "event_matches_turn",
    "had_prior_review_context",
    "interrupt_and_drain_turn",
    "load_rollout_items_for_fork",
    "prompt_cache_key_override_for_review_session",
    "run_before_review_deadline",
    "run_before_review_deadline_with_cancel",
    "run_review_on_session",
    "spawn_guardian_review_session",
    "token_usage_delta",
    "wait_for_guardian_review",
]
