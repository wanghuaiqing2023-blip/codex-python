"""Response-item to turn-item mapping ported from ``core/src/event_mapping.rs``."""

from __future__ import annotations

import uuid

from pycodex.core.context import (
    is_contextual_user_fragment,
    parse_visible_hook_prompt_message,
)
from pycodex.core.web_search import web_search_action_detail
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageItem,
    COLLABORATION_MODE_OPEN_TAG,
    ContentItem,
    ImageGenerationItem,
    REALTIME_CONVERSATION_OPEN_TAG,
    ReasoningItem,
    ResponseItem,
    TurnItem,
    UserInput,
    UserMessageItem,
    WebSearchAction,
    WebSearchItem,
    is_image_close_tag_text,
    is_image_open_tag_text,
    is_local_image_close_tag_text,
    is_local_image_open_tag_text,
)


CONTEXTUAL_DEVELOPER_PREFIXES = (
    "<permissions instructions>",
    "<model_switch>",
    COLLABORATION_MODE_OPEN_TAG,
    REALTIME_CONVERSATION_OPEN_TAG,
    "<personality_spec>",
)


def is_contextual_user_message_content(message: tuple[ContentItem, ...] | list[ContentItem]) -> bool:
    return any(is_contextual_user_fragment(content_item) for content_item in message)


def is_contextual_dev_message_content(message: tuple[ContentItem, ...] | list[ContentItem]) -> bool:
    return any(_is_contextual_dev_fragment(content_item) for content_item in message)


def has_non_contextual_dev_message_content(message: tuple[ContentItem, ...] | list[ContentItem]) -> bool:
    return any(not _is_contextual_dev_fragment(content_item) for content_item in message)


def _is_contextual_dev_fragment(content_item: ContentItem) -> bool:
    if content_item.type != "input_text":
        return False
    trimmed = (content_item.text or "").lstrip()
    lowered = trimmed.lower()
    return any(lowered.startswith(prefix.lower()) for prefix in CONTEXTUAL_DEVELOPER_PREFIXES)


def _parse_user_message(message: tuple[ContentItem, ...] | list[ContentItem]) -> TurnItem | None:
    if is_contextual_user_message_content(message):
        return None

    content: list[UserInput] = []
    for index, content_item in enumerate(message):
        if content_item.type == "input_text":
            text = content_item.text or ""
            next_is_input_image = index + 1 < len(message) and message[index + 1].type == "input_image"
            previous_is_input_image = index > 0 and message[index - 1].type == "input_image"
            if (is_local_image_open_tag_text(text) or is_image_open_tag_text(text)) and next_is_input_image:
                continue
            if (is_local_image_close_tag_text(text) or is_image_close_tag_text(text)) and previous_is_input_image:
                continue
            content.append(UserInput.text_input(text))
        elif content_item.type == "input_image":
            content.append(UserInput.image(content_item.image_url or "", detail=content_item.detail))
    return TurnItem.user_message(UserMessageItem.new(tuple(content)))


def _parse_agent_message(
    id: str | None,
    message: tuple[ContentItem, ...] | list[ContentItem],
    phase: object | None,
) -> AgentMessageItem:
    content = [
        AgentMessageContent.text_content(content_item.text or "")
        for content_item in message
        if content_item.type in {"input_text", "output_text"}
    ]
    return AgentMessageItem(id or str(uuid.uuid4()), tuple(content), phase=phase)


def parse_turn_item(item: ResponseItem) -> TurnItem | None:
    if item.type == "message":
        if item.role == "user":
            hook_prompt = parse_visible_hook_prompt_message(item.id, item.content)
            if hook_prompt is not None:
                return TurnItem.hook_prompt(hook_prompt)
            return _parse_user_message(item.content)
        if item.role == "assistant":
            return TurnItem.agent_message(_parse_agent_message(item.id, item.content, item.phase))
        return None

    if item.type == "reasoning":
        summary_text = tuple(entry.text for entry in item.summary)
        raw_content = tuple(entry.text for entry in item.reasoning_content or ())
        return TurnItem.reasoning(ReasoningItem(item.id or "", summary_text, raw_content))

    if item.type == "web_search_call":
        if item.action is None:
            action = WebSearchAction.other()
            query = ""
        else:
            action = item.action
            query = web_search_action_detail(action)
        return TurnItem.web_search(WebSearchItem(item.id or "", query, action))

    if item.type == "image_generation_call":
        return TurnItem.image_generation(
            ImageGenerationItem(
                id=item.id or "",
                status=item.status or "",
                result=item.result or "",
                revised_prompt=item.revised_prompt,
            )
        )

    return None


__all__ = [
    "CONTEXTUAL_DEVELOPER_PREFIXES",
    "has_non_contextual_dev_message_content",
    "is_contextual_dev_message_content",
    "is_contextual_user_message_content",
    "parse_turn_item",
]
