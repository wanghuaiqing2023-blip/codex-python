"""Pure compaction helpers.

Ported from the standalone helper portions of
``codex/codex-rs/core/src/compact.rs``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Sequence

from pycodex.core.event_mapping import parse_turn_item
from pycodex.core.tool_context import truncate_text
from pycodex.core.string_utils import approx_token_count
from pycodex.protocol import ContentItem, ResponseItem, TruncationPolicyConfig

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_RUST_CORE_ROOT = _WORKSPACE_ROOT / "codex" / "codex-rs" / "core"


def _include_rust_str(relative_path: str) -> str:
    return (_RUST_CORE_ROOT / relative_path).read_text(encoding="utf-8")


SUMMARIZATION_PROMPT = _include_rust_str("templates/compact/prompt.md")
SUMMARY_PREFIX = _include_rust_str("templates/compact/summary_prefix.md")
COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000


class InitialContextInjection(str, Enum):
    BEFORE_LAST_USER_MESSAGE = "before_last_user_message"
    DO_NOT_INJECT = "do_not_inject"


class CompactionStatus(str, Enum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


def should_use_remote_compact_task(provider: object) -> bool:
    method = getattr(provider, "supports_remote_compaction", None)
    if not callable(method):
        raise TypeError("provider must expose supports_remote_compaction()")
    result = method()
    if not isinstance(result, bool):
        raise TypeError("supports_remote_compaction() must return a bool")
    return result


def compaction_status_from_result(result: object) -> CompactionStatus:
    if isinstance(result, BaseException):
        kind = getattr(result, "kind", None)
        if kind in {"interrupted", "turn_aborted"}:
            return CompactionStatus.INTERRUPTED
        return CompactionStatus.FAILED
    return CompactionStatus.COMPLETED


def content_items_to_text(content: Sequence[ContentItem]) -> str | None:
    if isinstance(content, ContentItem) or not isinstance(content, Sequence):
        raise TypeError("content must be a sequence of ContentItem")
    pieces: list[str] = []
    for item in content:
        if not isinstance(item, ContentItem):
            raise TypeError("content must contain ContentItem values")
        if item.type in {"input_text", "output_text"} and item.text:
            pieces.append(item.text)
    return "\n".join(pieces) if pieces else None


def collect_user_messages(items: Sequence[ResponseItem]) -> list[str]:
    if isinstance(items, ResponseItem) or not isinstance(items, Sequence):
        raise TypeError("items must be a sequence of ResponseItem")
    collected: list[str] = []
    for item in items:
        if not isinstance(item, ResponseItem):
            raise TypeError("items must contain ResponseItem values")
        turn_item = parse_turn_item(item)
        if turn_item is None or turn_item.type != "UserMessage":
            continue
        message = turn_item.item.message()
        if not is_summary_message(message):
            collected.append(message)
    return collected


def is_summary_message(message: str) -> bool:
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    return message.startswith(f"{SUMMARY_PREFIX}\n")


def insert_initial_context_before_last_real_user_or_summary(
    compacted_history: Sequence[ResponseItem],
    initial_context: Sequence[ResponseItem],
) -> list[ResponseItem]:
    history = _response_items(compacted_history, "compacted_history")
    context = _response_items(initial_context, "initial_context")

    last_user_or_summary_index: int | None = None
    last_real_user_index: int | None = None
    for index in range(len(history) - 1, -1, -1):
        turn_item = parse_turn_item(history[index])
        if turn_item is None or turn_item.type != "UserMessage":
            continue
        if last_user_or_summary_index is None:
            last_user_or_summary_index = index
        if not is_summary_message(turn_item.item.message()):
            last_real_user_index = index
            break

    last_compaction_index = None
    for index in range(len(history) - 1, -1, -1):
        if history[index].type in {"compaction", "context_compaction"}:
            last_compaction_index = index
            break

    insertion_index = (
        last_real_user_index
        if last_real_user_index is not None
        else last_user_or_summary_index
        if last_user_or_summary_index is not None
        else last_compaction_index
    )
    if insertion_index is None:
        return [*history, *context]
    return [*history[:insertion_index], *context, *history[insertion_index:]]


def build_compacted_history(
    initial_context: Sequence[ResponseItem],
    user_messages: Sequence[str],
    summary_text: str,
) -> list[ResponseItem]:
    return build_compacted_history_with_limit(
        initial_context,
        user_messages,
        summary_text,
        COMPACT_USER_MESSAGE_MAX_TOKENS,
    )


def build_compacted_history_with_limit(
    initial_context: Sequence[ResponseItem],
    user_messages: Sequence[str],
    summary_text: str,
    max_tokens: int,
) -> list[ResponseItem]:
    history = _response_items(initial_context, "initial_context")
    messages = _string_sequence(user_messages, "user_messages")
    if not isinstance(summary_text, str):
        raise TypeError("summary_text must be a string")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise TypeError("max_tokens must be an integer")
    if max_tokens < 0:
        raise ValueError("max_tokens must be non-negative")

    selected_messages: list[str] = []
    if max_tokens > 0:
        remaining = max_tokens
        for message in reversed(messages):
            if remaining == 0:
                break
            tokens = approx_token_count(message)
            if tokens <= remaining:
                selected_messages.append(message)
                remaining = max(remaining - tokens, 0)
            else:
                selected_messages.append(truncate_text(message, TruncationPolicyConfig.tokens(remaining)))
                break
        selected_messages.reverse()

    for message in selected_messages:
        history.append(_user_message_response_item(message))
    history.append(_user_message_response_item(summary_text if summary_text else "(no summary available)"))
    return history


def _user_message_response_item(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _response_items(value: Sequence[ResponseItem], label: str) -> list[ResponseItem]:
    if isinstance(value, ResponseItem) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of ResponseItem")
    if not all(isinstance(item, ResponseItem) for item in value):
        raise TypeError(f"{label} must contain ResponseItem values")
    return list(value)


def _string_sequence(value: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must be a sequence of strings")
    return tuple(value)


__all__ = [
    "COMPACT_USER_MESSAGE_MAX_TOKENS",
    "CompactionStatus",
    "InitialContextInjection",
    "SUMMARIZATION_PROMPT",
    "SUMMARY_PREFIX",
    "build_compacted_history",
    "build_compacted_history_with_limit",
    "collect_user_messages",
    "compaction_status_from_result",
    "content_items_to_text",
    "insert_initial_context_before_last_real_user_or_summary",
    "is_summary_message",
    "should_use_remote_compact_task",
]
