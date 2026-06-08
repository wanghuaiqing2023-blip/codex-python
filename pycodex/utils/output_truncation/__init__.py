"""Tool output truncation helpers ported from ``codex-utils-output-truncation``."""

from __future__ import annotations

from pycodex.protocol import (
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    TruncationMode,
    TruncationPolicyConfig,
)
from pycodex.utils.string import (
    approx_bytes_for_tokens,
    approx_token_count,
    approx_tokens_from_byte_count,
    truncate_middle_chars,
    truncate_middle_with_token_budget,
)


def formatted_truncate_text(content: str, policy: TruncationPolicyConfig) -> str:
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    if len(content.encode("utf-8")) <= _policy_byte_budget(policy):
        return content
    truncated = truncate_text(content, policy)
    return f"Total output lines: {len(content.splitlines()) or 1}\n\n{truncated}"


def truncate_text(content: str, policy: TruncationPolicyConfig) -> str:
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    if policy.mode is TruncationMode.BYTES:
        return truncate_middle_chars(content, policy.limit)
    truncated, _original_token_count = truncate_middle_with_token_budget(content, policy.limit)
    return truncated


def truncate_function_output_payload(
    payload: FunctionCallOutputPayload | object,
    policy: TruncationPolicyConfig,
) -> FunctionCallOutputPayload:
    output = FunctionCallOutputPayload.from_value(payload)
    if output.content_items is not None:
        return FunctionCallOutputPayload.from_content_items(
            truncate_function_output_items_with_policy(output.content_items, policy),
            output.success,
        )
    return FunctionCallOutputPayload.from_text(
        truncate_text(output.to_text() or "", policy),
        output.success,
    )


def formatted_truncate_text_content_items_with_policy(
    items: tuple[FunctionCallOutputContentItem, ...] | list[FunctionCallOutputContentItem],
    policy: TruncationPolicyConfig,
) -> tuple[tuple[FunctionCallOutputContentItem, ...], int | None]:
    content_items = tuple(FunctionCallOutputContentItem.from_mapping(item) for item in items)
    text_segments = tuple(
        item.text or ""
        for item in content_items
        if item.type == "input_text"
    )
    if not text_segments:
        return content_items, None

    combined = "\n".join(text_segments)
    if len(combined.encode("utf-8")) <= _policy_byte_budget(policy):
        return content_items, None

    output: list[FunctionCallOutputContentItem] = [
        FunctionCallOutputContentItem.input_text(
            formatted_truncate_text(combined, policy)
        )
    ]
    output.extend(
        item
        for item in content_items
        if item.type in ("input_image", "encrypted_content")
    )
    return tuple(output), approx_token_count(combined)


def truncate_function_output_items_with_policy(
    items: tuple[FunctionCallOutputContentItem, ...] | list[FunctionCallOutputContentItem],
    policy: TruncationPolicyConfig,
) -> tuple[FunctionCallOutputContentItem, ...]:
    content_items = tuple(FunctionCallOutputContentItem.from_mapping(item) for item in items)
    output: list[FunctionCallOutputContentItem] = []
    remaining_budget = _policy_budget_for_mode(policy)
    omitted_text_items = 0

    for item in content_items:
        if item.type == "input_text":
            text = item.text or ""
            if remaining_budget == 0:
                omitted_text_items += 1
                continue

            cost = (
                len(text.encode("utf-8"))
                if policy.mode is TruncationMode.BYTES
                else approx_token_count(text)
            )
            if cost <= remaining_budget:
                output.append(item)
                remaining_budget = max(remaining_budget - cost, 0)
            else:
                snippet_policy = (
                    TruncationPolicyConfig.bytes(remaining_budget)
                    if policy.mode is TruncationMode.BYTES
                    else TruncationPolicyConfig.tokens(remaining_budget)
                )
                snippet = truncate_text(text, snippet_policy)
                if snippet:
                    output.append(FunctionCallOutputContentItem.input_text(snippet))
                else:
                    omitted_text_items += 1
                remaining_budget = 0
        elif item.type in ("input_image", "encrypted_content"):
            output.append(item)

    if omitted_text_items > 0:
        output.append(
            FunctionCallOutputContentItem.input_text(
                f"[omitted {omitted_text_items} text items ...]"
            )
        )

    return tuple(output)


def approx_tokens_from_byte_count_i64(bytes_count: int) -> int:
    if isinstance(bytes_count, bool) or not isinstance(bytes_count, int):
        raise TypeError("bytes_count must be an integer")
    if bytes_count <= 0:
        return 0
    return approx_tokens_from_byte_count(bytes_count)


def _policy_byte_budget(policy: TruncationPolicyConfig) -> int:
    if policy.mode is TruncationMode.BYTES:
        return max(policy.limit, 0)
    return approx_bytes_for_tokens(policy.limit)


def _policy_budget_for_mode(policy: TruncationPolicyConfig) -> int:
    if policy.mode is TruncationMode.BYTES:
        return max(policy.limit, 0)
    return max(policy.limit, 0)


__all__ = [
    "approx_bytes_for_tokens",
    "approx_token_count",
    "approx_tokens_from_byte_count",
    "approx_tokens_from_byte_count_i64",
    "formatted_truncate_text",
    "formatted_truncate_text_content_items_with_policy",
    "truncate_function_output_items_with_policy",
    "truncate_function_output_payload",
    "truncate_text",
]
