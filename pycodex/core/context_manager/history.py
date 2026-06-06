"""Conversation history helpers aligned with ``codex-rs/core/src/context_manager/history.rs``."""

from __future__ import annotations

import base64
import binascii
import json
import math
from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

from pycodex.core.context_manager.normalize import normalize_call_outputs, remove_corresponding_for, strip_images_when_unsupported
from pycodex.core.tools.context import truncate_function_output_payload as _truncate_function_output_payload
from pycodex.core.event_mapping import (
    has_non_contextual_dev_message_content,
    is_contextual_dev_message_content,
    is_contextual_user_message_content,
)
from pycodex.protocol import (
    BaseInstructions,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    InterAgentCommunication,
    ResponseItem,
    TokenUsage,
    TokenUsageInfo,
    TruncationPolicyConfig,
    TurnContextItem,
)
from pycodex.utils.string import approx_token_count, approx_tokens_from_byte_count


I64_MAX = 2**63 - 1


@dataclass(frozen=True)
class TotalTokenUsageBreakdown:
    last_api_response_total_tokens: int = 0
    all_history_items_model_visible_bytes: int = 0
    estimated_tokens_of_items_added_since_last_successful_api_response: int = 0
    estimated_bytes_of_items_added_since_last_successful_api_response: int = 0


def estimate_response_item_model_visible_bytes(item: ResponseItem) -> int:
    """Estimate model-visible response item bytes using Rust's compact JSON fallback."""

    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type in {"reasoning", "compaction"} and item.encrypted_content is not None:
        return estimate_reasoning_length(len(item.encrypted_content))
    if item.type == "context_compaction" and item.encrypted_content is not None:
        return estimate_reasoning_length(len(item.encrypted_content))
    raw = len(json.dumps(item.to_mapping(), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    image_payload_bytes, image_replacement_bytes = _image_data_url_estimate_adjustment(item)
    encrypted_payload_bytes, encrypted_replacement_bytes = _encrypted_function_output_estimate_adjustment(item)
    return max(raw - image_payload_bytes + image_replacement_bytes - encrypted_payload_bytes + encrypted_replacement_bytes, 0)


def estimate_reasoning_length(encoded_len: int) -> int:
    if isinstance(encoded_len, bool) or not isinstance(encoded_len, int):
        raise TypeError("encoded_len must be an integer")
    return max((max(encoded_len, 0) * 3) // 4 - 650, 0)


RESIZED_IMAGE_BYTES_ESTIMATE = 7373
ORIGINAL_IMAGE_PATCH_SIZE = 32
ORIGINAL_IMAGE_MAX_PATCHES = 10_000


def parse_base64_image_data_url(url: str) -> str | None:
    if not isinstance(url, str):
        return None
    if not url[:5].lower() == "data:":
        return None
    comma_index = url.find(",")
    if comma_index < 0:
        return None
    metadata = url[:comma_index]
    payload = url[comma_index + 1 :]
    metadata_without_scheme = metadata[5:]
    parts = metadata_without_scheme.split(";")
    mime_type = parts[0] if parts else ""
    if not mime_type[:6].lower() == "image/":
        return None
    if not any(part.lower() == "base64" for part in parts[1:]):
        return None
    return payload


def _estimate_encrypted_function_output_length(encoded_len: int) -> int:
    return max(encoded_len, 0) * 9 // 16 + (1 if (max(encoded_len, 0) * 9) % 16 else 0)


def _estimate_original_image_bytes(image_url: str) -> int | None:
    payload = parse_base64_image_data_url(image_url)
    if payload is None:
        return None
    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(image_bytes) < 24 or image_bytes[:8] != b"\x89PNG\r\n\x1a\n" or image_bytes[12:16] != b"IHDR":
        return None
    width = int.from_bytes(image_bytes[16:20], "big")
    height = int.from_bytes(image_bytes[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    patches_wide = (width + ORIGINAL_IMAGE_PATCH_SIZE - 1) // ORIGINAL_IMAGE_PATCH_SIZE
    patches_high = (height + ORIGINAL_IMAGE_PATCH_SIZE - 1) // ORIGINAL_IMAGE_PATCH_SIZE
    patch_count = min(patches_wide * patches_high, ORIGINAL_IMAGE_MAX_PATCHES)
    return _saturating_mul_i64(patch_count, 4)


def _is_original_image_detail(detail: object) -> bool:
    return getattr(detail, "value", detail) == "original"


def _image_data_url_estimate_adjustment(item: ResponseItem) -> tuple[int, int]:
    payload_bytes = 0
    replacement_bytes = 0

    def accumulate(image_url: object, detail: object = None) -> None:
        nonlocal payload_bytes, replacement_bytes
        payload = parse_base64_image_data_url(image_url) if isinstance(image_url, str) else None
        if payload is None:
            return
        payload_bytes = _saturating_add_i64(payload_bytes, len(payload.encode("utf-8")))
        replacement = (
            _estimate_original_image_bytes(image_url) if _is_original_image_detail(detail) and isinstance(image_url, str) else None
        )
        replacement_bytes = _saturating_add_i64(
            replacement_bytes,
            replacement if replacement is not None else RESIZED_IMAGE_BYTES_ESTIMATE,
        )

    if item.type == "message":
        for content_item in item.content:
            if getattr(content_item, "type", None) == "input_image":
                accumulate(getattr(content_item, "image_url", None), getattr(content_item, "detail", None))
    elif item.type in {"function_call_output", "custom_tool_call_output"}:
        output = item.output if isinstance(item.output, FunctionCallOutputPayload) else None
        if output is not None and output.content_items is not None:
            for content_item in output.content_items:
                if getattr(content_item, "type", None) == "input_image":
                    accumulate(getattr(content_item, "image_url", None), getattr(content_item, "detail", None))

    return payload_bytes, replacement_bytes


def _encrypted_function_output_estimate_adjustment(item: ResponseItem) -> tuple[int, int]:
    if item.type != "function_call_output":
        return 0, 0
    output = item.output if isinstance(item.output, FunctionCallOutputPayload) else None
    if output is None or output.content_items is None:
        return 0, 0

    payload_bytes = 0
    replacement_bytes = 0
    for content_item in output.content_items:
        if getattr(content_item, "type", None) != "encrypted_content":
            continue
        encrypted_content = getattr(content_item, "encrypted_content", None)
        if not isinstance(encrypted_content, str):
            continue
        payload_len = len(encrypted_content.encode("utf-8"))
        payload_bytes = _saturating_add_i64(payload_bytes, payload_len)
        replacement_bytes = _saturating_add_i64(
            replacement_bytes,
            _estimate_encrypted_function_output_length(payload_len),
        )
    return payload_bytes, replacement_bytes


def estimate_item_token_count(item: ResponseItem) -> int:
    """Estimate one history item's token count from its model-visible byte estimate."""

    return _clamp_i64(approx_tokens_from_byte_count(estimate_response_item_model_visible_bytes(item)))


def estimate_token_count_with_base_instructions(
    items: Sequence[ResponseItem],
    base_instructions: BaseInstructions | str,
) -> int | None:
    """Estimate token usage for explicit history items and base instructions."""

    history = ContextManager.from_items(items)
    return history.estimate_token_count_with_base_instructions(base_instructions)


def process_history_items(
    items: Iterable[ResponseItem],
    policy: TruncationPolicyConfig | None = None,
) -> tuple[ResponseItem, ...]:
    truncation_policy = _ensure_truncation_policy(policy)
    return tuple(process_history_item(item, truncation_policy) for item in _response_items(items, "items") if is_api_message(item))


def process_history_item(
    item: ResponseItem,
    policy: TruncationPolicyConfig | None = None,
) -> ResponseItem:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type not in {"function_call_output", "custom_tool_call_output"}:
        return item
    output = item.output
    if output is None:
        return item
    scaled_policy = _scaled_truncation_policy(_ensure_truncation_policy(policy), 1.2)
    return replace(item, output=truncate_function_output_payload(output, scaled_policy))


def truncate_function_output_payload(
    output: FunctionCallOutputPayload,
    policy: TruncationPolicyConfig | None = None,
) -> FunctionCallOutputPayload:
    return _truncate_function_output_payload(output, _ensure_truncation_policy(policy))


@dataclass
class ContextManager:
    """Transcript of thread history, ported in slices from Rust ``ContextManager``."""

    items: list[ResponseItem] = field(default_factory=list)
    history_version: int = 0
    _token_info: TokenUsageInfo | None = None
    _reference_context_item: TurnContextItem | None = None

    @classmethod
    def new(cls) -> "ContextManager":
        return cls()

    @classmethod
    def from_items(cls, items: Iterable[ResponseItem]) -> "ContextManager":
        return cls(list(_response_items(items, "items")))

    def record_items(self, items: Iterable[ResponseItem], policy: TruncationPolicyConfig | None = None) -> None:
        self.items.extend(process_history_items(items, policy))

    def raw_items(self) -> list[ResponseItem]:
        return list(self.items)

    def into_raw_items(self) -> list[ResponseItem]:
        items = self.raw_items()
        self.items.clear()
        return items

    def token_info(self) -> TokenUsageInfo | None:
        return self._token_info

    def set_token_info(self, info: TokenUsageInfo | None) -> None:
        if info is not None and not isinstance(info, TokenUsageInfo):
            raise TypeError("info must be TokenUsageInfo or None")
        self._token_info = info

    def set_token_usage_full(self, context_window: int) -> None:
        if isinstance(context_window, bool) or not isinstance(context_window, int):
            raise TypeError("context_window must be an integer")
        context_window = _clamp_i64(context_window)
        if self._token_info is None:
            self._token_info = TokenUsageInfo.full_context_window(context_window)
        else:
            self._token_info = self._token_info.fill_to_context_window(context_window)

    def update_token_info(self, usage: TokenUsage, model_context_window: int | None = None) -> None:
        if not isinstance(usage, TokenUsage):
            raise TypeError("usage must be TokenUsage")
        if model_context_window is not None and (isinstance(model_context_window, bool) or not isinstance(model_context_window, int)):
            raise TypeError("model_context_window must be an integer or None")
        self._token_info = TokenUsageInfo.new_or_append(self._token_info, usage, model_context_window)

    def reference_context_item(self) -> TurnContextItem | None:
        return self._reference_context_item

    def set_reference_context_item(self, item: TurnContextItem | None) -> None:
        if item is not None and not isinstance(item, TurnContextItem):
            raise TypeError("item must be TurnContextItem or None")
        self._reference_context_item = item

    def replace(self, items: Iterable[ResponseItem]) -> None:
        self.items = list(_response_items(items, "items"))
        self.history_version = _saturating_add_i64(self.history_version, 1)

    def normalize_history(self, input_modalities: Sequence[object] | None) -> None:
        self.items = list(strip_images_when_unsupported(input_modalities, normalize_call_outputs(tuple(self.items))))

    def for_prompt(self, input_modalities: Sequence[object] | None) -> list[ResponseItem]:
        normalized = normalize_call_outputs(tuple(self.items))
        return list(strip_images_when_unsupported(input_modalities, normalized))

    def remove_first_item(self) -> None:
        if self.items:
            removed = self.items.pop(0)
            remove_corresponding_for(self.items, removed)

    def remove_last_item(self) -> bool:
        if not self.items:
            return False
        removed = self.items.pop()
        remove_corresponding_for(self.items, removed)
        self.history_version = _saturating_add_i64(self.history_version, 1)
        return True

    def drop_last_n_user_turns(self, num_turns: int) -> None:
        if isinstance(num_turns, bool) or not isinstance(num_turns, int):
            raise TypeError("num_turns must be an integer")
        if num_turns <= 0:
            return
        snapshot = list(self.items)
        user_positions = user_message_positions(snapshot)
        if not user_positions:
            self.replace(snapshot)
            return
        first_instruction_turn_idx = user_positions[0]
        if num_turns >= len(user_positions):
            cut_idx = first_instruction_turn_idx
        else:
            cut_idx = user_positions[len(user_positions) - num_turns]
        cut_idx = self.trim_pre_turn_context_updates(snapshot, first_instruction_turn_idx, cut_idx)
        self.replace(snapshot[:cut_idx])

    def trim_pre_turn_context_updates(
        self,
        snapshot: Sequence[ResponseItem],
        first_instruction_turn_idx: int,
        cut_idx: int,
    ) -> int:
        if isinstance(first_instruction_turn_idx, bool) or not isinstance(first_instruction_turn_idx, int):
            raise TypeError("first_instruction_turn_idx must be an integer")
        if isinstance(cut_idx, bool) or not isinstance(cut_idx, int):
            raise TypeError("cut_idx must be an integer")
        items = _response_items(snapshot, "snapshot")
        cut_idx = max(0, min(cut_idx, len(items)))
        first_instruction_turn_idx = max(0, min(first_instruction_turn_idx, len(items)))
        while cut_idx > first_instruction_turn_idx:
            item = items[cut_idx - 1]
            if item.type == "message" and item.role == "developer":
                content = tuple(item.content)
                if is_contextual_dev_message_content(content):
                    if has_non_contextual_dev_message_content(content):
                        self._reference_context_item = None
                    cut_idx -= 1
                    continue
            if item.type == "message" and item.role == "user" and is_contextual_user_message_content(tuple(item.content)):
                cut_idx -= 1
                continue
            break
        return cut_idx

    def replace_last_turn_images(self, placeholder: str) -> bool:
        if not isinstance(placeholder, str):
            raise TypeError("placeholder must be a string")
        index = _last_index_matching(
            self.items,
            lambda item: item.type == "function_call_output" or is_user_turn_boundary(item),
        )
        if index is None:
            return False
        item = self.items[index]
        if item.type != "function_call_output":
            return False
        output = item.output if isinstance(item.output, FunctionCallOutputPayload) else None
        if output is None or output.content_items is None:
            return False
        replaced = False
        content_items: list[FunctionCallOutputContentItem] = []
        for content_item in output.content_items:
            if content_item.type == "input_image":
                content_items.append(FunctionCallOutputContentItem.input_text(placeholder))
                replaced = True
            else:
                content_items.append(content_item)
        if not replaced:
            return False
        new_output = FunctionCallOutputPayload.from_content_items(tuple(content_items), success=output.success)
        self.items[index] = replace(item, output=new_output)
        self.history_version = _saturating_add_i64(self.history_version, 1)
        return True

    def estimate_token_count_with_base_instructions(
        self,
        base_instructions: BaseInstructions | str,
    ) -> int | None:
        base_tokens = _clamp_i64(approx_token_count(_base_instructions_text(base_instructions)))
        items_tokens = 0
        for item in self.items:
            items_tokens = _saturating_add_i64(items_tokens, estimate_item_token_count(item))
        return _saturating_add_i64(base_tokens, items_tokens)

    def get_non_last_reasoning_items_tokens(self) -> int:
        last_user_index = _last_index_matching(self.items, is_user_turn_boundary)
        if last_user_index is None:
            return 0
        tokens = 0
        for item in self.items[:last_user_index]:
            if item.type == "reasoning" and item.encrypted_content is not None:
                tokens = _saturating_add_i64(tokens, estimate_item_token_count(item))
        return tokens

    def items_after_last_model_generated_item(self) -> list[ResponseItem]:
        last_model_index = _last_index_matching(self.items, is_model_generated_item)
        if last_model_index is None:
            return []
        return list(self.items[last_model_index + 1 :])

    def get_total_token_usage(self, server_reasoning_included: bool) -> int:
        last_tokens = self._token_info.last_token_usage.total_tokens if self._token_info is not None else 0
        items_after_last_model_generated_tokens = 0
        for item in self.items_after_last_model_generated_item():
            items_after_last_model_generated_tokens = _saturating_add_i64(
                items_after_last_model_generated_tokens,
                estimate_item_token_count(item),
            )
        if server_reasoning_included:
            return _saturating_add_i64(last_tokens, items_after_last_model_generated_tokens)
        return _saturating_add_i64(
            _saturating_add_i64(last_tokens, self.get_non_last_reasoning_items_tokens()),
            items_after_last_model_generated_tokens,
        )

    def get_total_token_usage_breakdown(self) -> TotalTokenUsageBreakdown:
        last_usage = self._token_info.last_token_usage if self._token_info is not None else TokenUsage()
        items_after_last_model_generated = self.items_after_last_model_generated_item()
        all_history_bytes = 0
        for item in self.items:
            all_history_bytes = _saturating_add_i64(all_history_bytes, estimate_response_item_model_visible_bytes(item))
        estimated_tail_tokens = 0
        estimated_tail_bytes = 0
        for item in items_after_last_model_generated:
            estimated_tail_tokens = _saturating_add_i64(estimated_tail_tokens, estimate_item_token_count(item))
            estimated_tail_bytes = _saturating_add_i64(
                estimated_tail_bytes,
                estimate_response_item_model_visible_bytes(item),
            )
        return TotalTokenUsageBreakdown(
            last_api_response_total_tokens=last_usage.total_tokens,
            all_history_items_model_visible_bytes=all_history_bytes,
            estimated_tokens_of_items_added_since_last_successful_api_response=estimated_tail_tokens,
            estimated_bytes_of_items_added_since_last_successful_api_response=estimated_tail_bytes,
        )


def is_user_turn_boundary(item: ResponseItem) -> bool:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type != "message":
        return False
    content = tuple(item.content)
    if item.role == "user":
        return not is_contextual_user_message_content(content)
    if item.role == "assistant":
        return InterAgentCommunication.from_message_content(content) is not None
    return False


def is_api_message(item: ResponseItem) -> bool:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type == "message":
        return item.role != "system"
    return item.type in {
        "function_call_output",
        "function_call",
        "tool_search_call",
        "tool_search_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "local_shell_call",
        "reasoning",
        "web_search_call",
        "image_generation_call",
        "compaction",
        "context_compaction",
    }


def is_model_generated_item(item: ResponseItem) -> bool:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type == "message":
        return item.role == "assistant"
    return item.type in {
        "reasoning",
        "function_call",
        "tool_search_call",
        "web_search_call",
        "image_generation_call",
        "custom_tool_call",
        "local_shell_call",
        "compaction",
        "context_compaction",
    }


def user_message_positions(items: Sequence[ResponseItem]) -> list[int]:
    return [index for index, item in enumerate(items) if is_user_turn_boundary(item)]


def _ensure_truncation_policy(policy: TruncationPolicyConfig | None) -> TruncationPolicyConfig:
    if policy is None:
        return TruncationPolicyConfig.tokens(10_000)
    if isinstance(policy, TruncationPolicyConfig):
        return policy
    return TruncationPolicyConfig.from_mapping(policy)


def _scaled_truncation_policy(policy: TruncationPolicyConfig, scale: float) -> TruncationPolicyConfig:
    limit = max(1, math.ceil(policy.limit * scale))
    if policy.mode.value == "bytes":
        return TruncationPolicyConfig.bytes(limit)
    return TruncationPolicyConfig.tokens(limit)


def _base_instructions_text(base_instructions: BaseInstructions | str) -> str:
    if isinstance(base_instructions, BaseInstructions):
        return base_instructions.text
    if isinstance(base_instructions, str):
        return base_instructions
    text = getattr(base_instructions, "text", None)
    if isinstance(text, str):
        return text
    raise TypeError("base_instructions must be BaseInstructions or string")


def _response_items(items: Iterable[ResponseItem], label: str) -> tuple[ResponseItem, ...]:
    if isinstance(items, ResponseItem) or isinstance(items, (str, bytes)):
        raise TypeError(f"{label} must be an iterable of ResponseItem")
    result: list[ResponseItem] = []
    for item in items:
        if not isinstance(item, ResponseItem):
            raise TypeError(f"{label} must contain ResponseItem values")
        result.append(item)
    return tuple(result)


def _last_index_matching(items: Sequence[ResponseItem], predicate: object) -> int | None:
    if not callable(predicate):
        raise TypeError("predicate must be callable")
    for index in range(len(items) - 1, -1, -1):
        if predicate(items[index]):
            return index
    return None


def _saturating_add_i64(left: int, right: int) -> int:
    return min(_clamp_i64(left) + _clamp_i64(right), I64_MAX)


def _saturating_mul_i64(left: int, right: int) -> int:
    return min(_clamp_i64(left) * _clamp_i64(right), I64_MAX)


def _clamp_i64(value: int) -> int:
    return min(max(value, 0), I64_MAX)


__all__ = [
    "ContextManager",
    "TotalTokenUsageBreakdown",
    "estimate_item_token_count",
    "estimate_reasoning_length",
    "estimate_response_item_model_visible_bytes",
    "estimate_token_count_with_base_instructions",
    "is_api_message",
    "is_model_generated_item",
    "is_user_turn_boundary",
    "parse_base64_image_data_url",
    "process_history_item",
    "process_history_items",
    "remove_corresponding_for",
    "truncate_function_output_payload",
    "user_message_positions",
]
