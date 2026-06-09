"""Review task helpers aligned with ``codex-core::tasks::review``."""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
from dataclasses import dataclass
from typing import Any

from pycodex.core.client_common import REVIEW_EXIT_INTERRUPTED_TMPL, REVIEW_EXIT_SUCCESS_TMPL, REVIEW_PROMPT
from pycodex.core.codex_delegate import (
    CancellationToken,
    CodexDelegateIo,
    RunCodexThreadOptions,
    event_kind,
    event_payload,
    run_codex_thread_one_shot,
)
from pycodex.core.review_format import format_review_findings_block, render_review_output_text
from pycodex.core.state import TaskKind
from pycodex.features import Feature
from pycodex.protocol import (
    AskForApproval,
    ContentItem,
    Event,
    EventMsg,
    ExitedReviewModeEvent,
    ResponseItem,
    ReviewOutputEvent,
    SubAgentSource,
    TurnItem,
    WebSearchMode,
)


REVIEW_ROLLOUT_USER_MESSAGE_ID = "review_rollout_user"
REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID = "review_rollout_assistant"
REVIEW_INTERRUPTED_ASSISTANT_MESSAGE = "Review was interrupted. Please re-run /review and wait for it to complete."


@dataclass(frozen=True)
class ReviewExitMessages:
    user_message: str
    assistant_message: str


@dataclass(frozen=True)
class ReviewTask:
    """Python coordinate for Rust ``ReviewTask`` runtime behavior."""

    @classmethod
    def new(cls) -> "ReviewTask":
        return cls()

    def kind(self) -> TaskKind:
        return TaskKind.REVIEW

    def span_name(self) -> str:
        return "session_task.review"

    async def run(
        self,
        session: Any,
        ctx: Any,
        input: list[Any] | tuple[Any, ...],
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        token = cancellation_token or CancellationToken()
        _emit_review_metric(session)
        user_input = collect_review_user_input(input)
        output: ReviewOutputEvent | None = None
        receiver = await start_review_conversation(session, ctx, user_input, token)
        if receiver is not None:
            output = await process_review_events(session, ctx, receiver)
        if not token.is_cancelled():
            await exit_review_mode(_clone_session(session), output, ctx)
        return None

    async def abort(self, session: Any, ctx: Any) -> None:
        await exit_review_mode(_clone_session(session), None, ctx)


async def start_review_conversation(
    session: Any,
    ctx: Any,
    input: list[Any] | tuple[Any, ...],
    cancellation_token: CancellationToken | None = None,
) -> CodexDelegateIo | None:
    """Start the review sub-Codex conversation using the delegated-thread bridge."""

    token = cancellation_token or CancellationToken()
    config = _field(ctx, "config")
    sub_agent_config = _clone_config(config)
    _configure_review_sub_agent(sub_agent_config, config, ctx)
    spawn_codex = _required_spawn_codex(session, ctx)
    try:
        return await run_codex_thread_one_shot(
            RunCodexThreadOptions(
                config=sub_agent_config,
                auth_manager=_call_or_get(session, "auth_manager"),
                models_manager=_call_or_get(session, "models_manager"),
                parent_session=_clone_session(session),
                parent_ctx=ctx,
                cancel_token=token,
                subagent_source=SubAgentSource.review(),
                initial_history=None,
                spawn_codex=spawn_codex,
            ),
            input,
            final_output_json_schema=None,
        )
    except Exception:
        return None


async def process_review_events(
    session: Any,
    ctx: Any,
    receiver: CodexDelegateIo | asyncio.Queue[Event] | Any,
) -> ReviewOutputEvent | None:
    """Forward review child events and extract structured review output."""

    previous_agent_message: Event | None = None
    while True:
        event = await _recv_event(receiver)
        if event is None:
            return None
        kind = event_kind(event)
        payload = event_payload(event)

        if kind == "agent_message":
            if previous_agent_message is not None:
                await _send_event(_clone_session(session), ctx, previous_agent_message.msg)
            previous_agent_message = event
            continue

        if kind == "item_completed" and _is_completed_agent_message(payload):
            continue
        if kind == "agent_message_content_delta":
            continue

        if kind in {"task_complete", "turn_complete"}:
            last_message = _field(payload, "last_agent_message")
            return parse_review_output_event(last_message) if isinstance(last_message, str) else None

        if kind in {"turn_aborted", "task_aborted"}:
            return None

        await _send_event(_clone_session(session), ctx, _event_msg(event))


async def exit_review_mode(session: Any, review_output: ReviewOutputEvent | None, ctx: Any) -> None:
    """Emit review exit events and materialize review rollout items."""

    messages = review_exit_messages(review_output)
    await _call_method(
        session,
        "record_conversation_items",
        ctx,
        [
            ResponseItem.message(
                "user",
                (ContentItem.input_text(messages.user_message),),
                id=REVIEW_ROLLOUT_USER_MESSAGE_ID,
            )
        ],
    )
    await _send_event(
        session,
        ctx,
        EventMsg.with_payload("exited_review_mode", ExitedReviewModeEvent(review_output)),
    )
    await _call_method(
        session,
        "record_response_item_and_emit_turn_item",
        ctx,
        ResponseItem.message(
            "assistant",
            (ContentItem.output_text(messages.assistant_message),),
            id=REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID,
        ),
    )
    materialize = getattr(session, "ensure_rollout_materialized", None)
    if callable(materialize):
        await _maybe_await(materialize())


def parse_review_output_event(text: str) -> ReviewOutputEvent:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    try:
        return ReviewOutputEvent.from_mapping(json.loads(text))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        try:
            return ReviewOutputEvent.from_mapping(json.loads(text[start : end + 1]))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    return ReviewOutputEvent(overall_explanation=text)


def normalize_review_template_line_endings(template: str) -> str:
    if not isinstance(template, str):
        raise TypeError("template must be a string")
    if "\r" not in template:
        return template
    return template.replace("\r\n", "\n").replace("\r", "\n")


def render_review_exit_success(results: str) -> str:
    if not isinstance(results, str):
        raise TypeError("results must be a string")
    return normalize_review_template_line_endings(REVIEW_EXIT_SUCCESS_TMPL).replace("{{results}}", results)


def render_review_exit_interrupted() -> str:
    return normalize_review_template_line_endings(REVIEW_EXIT_INTERRUPTED_TMPL)


def review_exit_messages(review_output: ReviewOutputEvent | None) -> ReviewExitMessages:
    if review_output is None:
        return ReviewExitMessages(
            user_message=render_review_exit_interrupted(),
            assistant_message=REVIEW_INTERRUPTED_ASSISTANT_MESSAGE,
        )
    findings = _review_findings_text(review_output)
    return ReviewExitMessages(
        user_message=render_review_exit_success(findings),
        assistant_message=render_review_output_text(review_output),
    )


def _review_findings_text(review_output: ReviewOutputEvent) -> str:
    text = review_output.overall_explanation.strip()
    findings = text
    if review_output.findings:
        findings += f"\n{format_review_findings_block(review_output.findings)}"
    return findings


def collect_review_user_input(turn_input: list[Any] | tuple[Any, ...]) -> list[Any]:
    collected: list[Any] = []
    for item in turn_input:
        content = getattr(item, "items", None)
        if content is None:
            content = getattr(item, "content", None)
        if content is not None:
            collected.extend(content)
    return collected


def _configure_review_sub_agent(sub_agent_config: Any, parent_config: Any, ctx: Any) -> None:
    _set_constrained(_field(sub_agent_config, "web_search_mode"), WebSearchMode.DISABLED)
    features = _field(sub_agent_config, "features")
    for feature in (Feature.SPAWN_CSV, Feature.COLLAB, Feature.MULTI_AGENT_V2):
        disable = getattr(features, "disable", None)
        if callable(disable):
            disable(feature)
    setattr(sub_agent_config, "base_instructions", REVIEW_PROMPT)
    permissions = _field(sub_agent_config, "permissions")
    approval_policy = getattr(permissions, "approval_policy", None)
    if approval_policy is not None:
        _set_constrained(approval_policy, AskForApproval.NEVER)
    review_model = _field(parent_config, "review_model")
    model_info = _field(ctx, "model_info")
    model = review_model or _field(model_info, "slug")
    if model:
        setattr(sub_agent_config, "model", model)


def _clone_config(config: Any) -> Any:
    clone = getattr(config, "clone", None)
    if callable(clone):
        return clone()
    try:
        return copy.deepcopy(config)
    except Exception as exc:
        raise TypeError("review sub-agent config must be cloneable") from exc


def _set_constrained(target: Any, value: Any) -> None:
    setter = getattr(target, "set", None)
    if callable(setter):
        setter(value)
        return
    if target is None:
        return
    raise TypeError("review sub-agent constrained field must expose set()")


def _required_spawn_codex(session: Any, ctx: Any) -> Any:
    for source in (ctx, session, _clone_session(session), _field(_clone_session(session), "services")):
        spawn = _field(source, "spawn_codex")
        if callable(spawn):
            return spawn
    raise TypeError("ReviewTask requires a spawn_codex callable for delegated review execution")


def _emit_review_metric(session: Any) -> None:
    services = _field(_clone_session(session), "services")
    telemetry = _field(services, "session_telemetry")
    counter = getattr(telemetry, "counter", None)
    if callable(counter):
        counter("codex.task.review", 1, [])


async def _recv_event(receiver: CodexDelegateIo | asyncio.Queue[Event] | Any) -> Event | None:
    if isinstance(receiver, CodexDelegateIo):
        return await receiver.next_event()
    if isinstance(receiver, asyncio.Queue):
        return await receiver.get()
    next_event = getattr(receiver, "next_event", None)
    if callable(next_event):
        return await _maybe_await(next_event())
    recv = getattr(receiver, "recv", None)
    if callable(recv):
        return await _maybe_await(recv())
    get = getattr(receiver, "get", None)
    if callable(get):
        return await _maybe_await(get())
    raise TypeError("review event receiver must expose next_event(), recv(), or get()")


def _is_completed_agent_message(payload: Any) -> bool:
    item = _field(payload, "item")
    if isinstance(item, TurnItem):
        return item.type == "AgentMessage"
    return _field(item, "type") in {"AgentMessage", "agentMessage"}


def _event_msg(event: Event | Any) -> EventMsg:
    msg = getattr(event, "msg", event)
    if isinstance(msg, EventMsg):
        return msg
    if isinstance(msg, dict):
        return EventMsg.from_mapping(msg)
    kind = getattr(msg, "type", None) or getattr(msg, "kind", None)
    if callable(kind):
        kind = kind()
    payload = getattr(msg, "payload", msg)
    return EventMsg.with_payload(str(kind or ""), payload)


async def _send_event(session: Any, ctx: Any, msg: EventMsg | Any) -> None:
    await _call_method(session, "send_event", ctx, msg)


async def _call_method(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if not callable(method):
        raise TypeError(f"review runtime requires session.{name}()")
    return await _maybe_await(method(*args))


def _call_or_get(target: Any, name: str) -> Any:
    value = _field(target, name)
    if callable(value):
        return value()
    return value


def _clone_session(session: Any) -> Any:
    clone = getattr(session, "clone_session", None)
    if callable(clone):
        return clone()
    return getattr(session, "session", session)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "REVIEW_INTERRUPTED_ASSISTANT_MESSAGE",
    "REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID",
    "REVIEW_ROLLOUT_USER_MESSAGE_ID",
    "ReviewExitMessages",
    "ReviewTask",
    "collect_review_user_input",
    "exit_review_mode",
    "normalize_review_template_line_endings",
    "parse_review_output_event",
    "process_review_events",
    "render_review_exit_interrupted",
    "render_review_exit_success",
    "review_exit_messages",
    "start_review_conversation",
]
