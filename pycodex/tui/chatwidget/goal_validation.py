"""Semantic port of codex-rs/tui/src/chatwidget/goal_validation.rs.

Rust implements these helpers on ``ChatWidget``. Python keeps them as
widget-like functions plus a mixin so this module owns only the objective length
validation contract, including the live-vs-queued cleanup difference.
"""

from __future__ import annotations

from collections import defaultdict, deque
from enum import Enum
from typing import Any, Callable, Deque, DefaultDict, Iterable, List, Optional, Tuple, Union

from pycodex.protocol import MAX_THREAD_GOAL_OBJECTIVE_CHARS
from pycodex.protocol.user_input import ByteRange, TextElement

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::goal_validation",
    source="codex/codex-rs/tui/src/chatwidget/goal_validation.rs",
    status="complete",
)

GOAL_TOO_LONG_FILE_HINT = "Put longer instructions in a file and refer to that file in the goal, for example: /goal follow the instructions in docs/goal.md."


class GoalObjectiveValidationSource(str, Enum):
    LIVE = "Live"
    QUEUED = "Queued"


def goal_objective_with_pending_pastes_is_allowed(
    widget: Any,
    args: str,
    text_elements: Iterable[Any] = (),
    expand_pending_pastes: Optional[Callable[[str, List[Any], List[Any]], Tuple[str, Any]]] = None,
) -> bool:
    bottom_pane = getattr(widget, "bottom_pane")
    pending_pastes = list(bottom_pane.composer_pending_pastes())
    if not pending_pastes:
        objective_chars = len(args.strip())
    else:
        if expand_pending_pastes is None:
            expand_pending_pastes = getattr(bottom_pane, "expand_pending_pastes", None)
        if expand_pending_pastes is None:
            expand_pending_pastes = expand_pending_pastes_like_rust
        expanded, _ = expand_pending_pastes(args, list(text_elements), pending_pastes)
        objective_chars = len(str(expanded).strip())
    return goal_objective_char_count_is_allowed(
        widget,
        objective_chars,
        GoalObjectiveValidationSource.LIVE,
    )


def goal_objective_is_allowed(
    widget: Any,
    objective: str,
    source: Union[GoalObjectiveValidationSource, str],
) -> bool:
    return goal_objective_char_count_is_allowed(widget, len(objective), source)


def goal_objective_char_count_is_allowed(
    widget: Any,
    actual_chars: int,
    source: Union[GoalObjectiveValidationSource, str],
) -> bool:
    if actual_chars <= MAX_THREAD_GOAL_OBJECTIVE_CHARS:
        return True
    actual = f"{actual_chars:,}"
    limit = f"{MAX_THREAD_GOAL_OBJECTIVE_CHARS:,}"
    widget.add_error_message(
        f"Goal objective is too long: {actual} characters. Limit: {limit} characters. {GOAL_TOO_LONG_FILE_HINT}"
    )
    if _normalize_source(source) == GoalObjectiveValidationSource.LIVE:
        bottom_pane = getattr(widget, "bottom_pane")
        bottom_pane.set_composer_text("", [], [])
        bottom_pane.drain_pending_submission_state()
    return False


def expand_pending_pastes_like_rust(
    text: str,
    elements: List[Any],
    pending_pastes: List[Any],
) -> Tuple[str, List[TextElement]]:
    """Mirror ``ChatComposer::expand_pending_pastes`` for goal validation.

    Rust accepts UTF-8 byte ranges, indexes pending pastes by placeholder, then
    rebuilds text and surviving text elements in byte-range order. Matched
    placeholders are replaced with the actual paste payload and their text
    elements are dropped.
    """

    if not pending_pastes or not elements:
        return text, list(elements)

    pending_by_placeholder = _pending_paste_map(pending_pastes)
    sorted_elements = sorted(elements, key=lambda elem: _byte_range(elem)[0])
    text_bytes = text.encode("utf-8")
    rebuilt_parts = []
    rebuilt_byte_len = 0
    rebuilt_elements = []
    cursor = 0

    for elem in sorted_elements:
        start, end = _byte_range(elem)
        start = min(start, len(text_bytes))
        end = min(end, len(text_bytes))
        if start > end:
            continue
        if start > cursor:
            segment = text_bytes[cursor:start].decode("utf-8")
            rebuilt_parts.append(segment)
            rebuilt_byte_len += len(segment.encode("utf-8"))

        elem_text = text_bytes[start:end].decode("utf-8")
        placeholder = _placeholder(elem, text)
        replacement = None
        if placeholder is not None:
            queue = pending_by_placeholder.get(placeholder)
            if queue:
                replacement = queue.popleft()

        if replacement is not None:
            rebuilt_parts.append(replacement)
            rebuilt_byte_len += len(replacement.encode("utf-8"))
        else:
            new_start = rebuilt_byte_len
            rebuilt_parts.append(elem_text)
            rebuilt_byte_len += len(elem_text.encode("utf-8"))
            new_end = rebuilt_byte_len
            rebuilt_elements.append(
                TextElement.new(
                    ByteRange(new_start, new_end),
                    placeholder if placeholder is not None else elem_text,
                )
            )
        cursor = end

    if cursor < len(text_bytes):
        rebuilt_parts.append(text_bytes[cursor:].decode("utf-8"))

    return "".join(rebuilt_parts), rebuilt_elements


def _pending_paste_map(pending_pastes: List[Any]) -> DefaultDict[str, Deque[str]]:
    pending_by_placeholder = defaultdict(deque)  # type: DefaultDict[str, Deque[str]]
    for item in pending_pastes:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            placeholder, actual = item
        else:
            placeholder = item
            actual = item
        pending_by_placeholder[str(placeholder)].append(str(actual))
    return pending_by_placeholder


def _byte_range(element: Any) -> Tuple[int, int]:
    byte_range = getattr(element, "byte_range", None)
    if byte_range is None:
        byte_range = getattr(element, "range", None)
    start = getattr(byte_range, "start", None)
    end = getattr(byte_range, "end", None)
    if start is None and hasattr(byte_range, "__getitem__"):
        start = byte_range[0]
        end = byte_range[1]
    return int(start), int(end)


def _placeholder(element: Any, text: str) -> Optional[str]:
    placeholder = getattr(element, "placeholder", None)
    if callable(placeholder):
        return placeholder(text)
    if placeholder is not None:
        return str(placeholder)
    conversion_placeholder = getattr(element, "placeholder_for_conversion_only", None)
    if callable(conversion_placeholder):
        value = conversion_placeholder()
        return None if value is None else str(value)
    explicit = getattr(element, "_placeholder", None)
    if explicit is not None:
        return str(explicit)
    start, end = _byte_range(element)
    encoded = text.encode("utf-8")
    if start < 0 or end < start or end > len(encoded):
        return None
    return encoded[start:end].decode("utf-8")


def _normalize_source(source: Union[GoalObjectiveValidationSource, str]) -> GoalObjectiveValidationSource:
    if isinstance(source, GoalObjectiveValidationSource):
        return source
    return GoalObjectiveValidationSource(str(source).split(".")[-1])


class GoalValidationMixin:
    """Mixin shape matching the Rust ``impl ChatWidget`` helpers."""

    def goal_objective_with_pending_pastes_is_allowed(
        self,
        args: str,
        text_elements: Iterable[Any] = (),
        expand_pending_pastes: Optional[Callable[[str, List[Any], List[Any]], Tuple[str, Any]]] = None,
    ) -> bool:
        return goal_objective_with_pending_pastes_is_allowed(
            self,
            args,
            text_elements,
            expand_pending_pastes,
        )

    def goal_objective_is_allowed(
        self,
        objective: str,
        source: Union[GoalObjectiveValidationSource, str],
    ) -> bool:
        return goal_objective_is_allowed(self, objective, source)

    def goal_objective_char_count_is_allowed(
        self,
        actual_chars: int,
        source: Union[GoalObjectiveValidationSource, str],
    ) -> bool:
        return goal_objective_char_count_is_allowed(self, actual_chars, source)


__all__ = [
    "GOAL_TOO_LONG_FILE_HINT",
    "GoalObjectiveValidationSource",
    "GoalValidationMixin",
    "RUST_MODULE",
    "expand_pending_pastes_like_rust",
    "goal_objective_char_count_is_allowed",
    "goal_objective_is_allowed",
    "goal_objective_with_pending_pastes_is_allowed",
]
