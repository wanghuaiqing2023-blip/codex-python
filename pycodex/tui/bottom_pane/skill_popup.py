"""Skill mention popup.

Python port of Rust ``codex-tui::bottom_pane::skill_popup``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .._porting import RustTuiModule
from .popup_consts import MAX_POPUP_ROWS

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::skill_popup",
    source="codex/codex-rs/tui/src/bottom_pane/skill_popup.rs",
)

MENTION_NAME_TRUNCATE_LEN = 28


@dataclass
class MentionItem:
    display_name: str
    description: str | None
    insert_text: str
    search_terms: list[str] = field(default_factory=list)
    path: str | None = None
    category_tag: str | None = None
    sort_rank: int = 0


@dataclass(frozen=True)
class DisplayRow:
    name: str
    description: str | None = None
    match_indices: list[int] | None = None
    selected: bool = False


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class SkillPopup:
    mentions: list[MentionItem]
    query: str = ""
    selected_idx: int | None = None
    scroll_top: int = 0

    @classmethod
    def new(cls, mentions: Iterable[MentionItem]) -> "SkillPopup":
        popup = cls(list(mentions))
        popup.clamp_selection()
        return popup

    def set_mentions(self, mentions: Iterable[MentionItem]) -> None:
        self.mentions = list(mentions)
        self.clamp_selection()

    def set_query(self, query: str) -> None:
        self.query = str(query)
        self.clamp_selection()

    def calculate_required_height(self, width: int) -> int:
        rows = self.rows_from_matches(self.filtered())
        visible = min(MAX_POPUP_ROWS, max(1, len(rows)))
        return visible + 2

    def move_up(self) -> None:
        length = len(self.filtered_items())
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = (current - 1) % length
        self._ensure_visible(length)

    def move_down(self) -> None:
        length = len(self.filtered_items())
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = (current + 1) % length
        self._ensure_visible(length)

    def selected_mention(self) -> MentionItem | None:
        matches = self.filtered_items()
        if self.selected_idx is None or not (0 <= self.selected_idx < len(matches)):
            return None
        return self.mentions[matches[self.selected_idx]]

    def clamp_selection(self) -> None:
        length = len(self.filtered_items())
        if length == 0:
            self.selected_idx = None
            self.scroll_top = 0
            return
        if self.selected_idx is None:
            self.selected_idx = 0
        self.selected_idx = max(0, min(self.selected_idx, length - 1))
        self._ensure_visible(length)

    def filtered_items(self) -> list[int]:
        return [idx for idx, _indices, _score in self.filtered()]

    def rows_from_matches(self, matches: list[tuple[int, list[int] | None, int]]) -> list[DisplayRow]:
        rows: list[DisplayRow] = []
        for visible_idx, (idx, indices, _score) in enumerate(matches):
            mention = self.mentions[idx]
            description = _combined_description(mention.category_tag, mention.description)
            rows.append(
                DisplayRow(
                    name=truncate_text(mention.display_name, MENTION_NAME_TRUNCATE_LEN),
                    description=description,
                    match_indices=indices,
                    selected=self.selected_idx == visible_idx,
                )
            )
        return rows

    def filtered(self) -> list[tuple[int, list[int] | None, int]]:
        filter_text = self.query.strip()
        out: list[tuple[int, list[int] | None, int]] = []
        for idx, mention in enumerate(self.mentions):
            if not filter_text:
                out.append((idx, None, 0))
                continue

            display = fuzzy_match(mention.display_name, filter_text)
            if display is not None:
                indices, score = display
                out.append((idx, indices, score))
                continue

            term_scores = [
                score
                for term in mention.search_terms
                if term != mention.display_name
                for _indices, score in [fuzzy_match(term, filter_text) or (None, None)]
                if score is not None
            ]
            if term_scores:
                out.append((idx, None, min(term_scores)))

        def key(row: tuple[int, list[int] | None, int]) -> tuple[Any, ...]:
            idx, indices, score = row
            mention = self.mentions[idx]
            if filter_text:
                return (indices is None, score, mention.sort_rank, mention.display_name)
            return (mention.sort_rank, mention.display_name)

        out.sort(key=key)
        return out

    def render_ref(self, area: Any = None, buf: Any = None) -> list[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width == 0 or height == 0:
            return []
        rows = self.rows_from_matches(self.filtered())
        visible_height = height - 2 if height > 2 else height
        lines: list[DisplayLine] = []
        if rows:
            for row in rows[self.scroll_top : self.scroll_top + min(MAX_POPUP_ROWS, visible_height)]:
                prefix = "› " if row.selected else "  "
                lines.append(DisplayLine(prefix + row.name, "selected" if row.selected else "plain"))
                if row.description:
                    lines.append(DisplayLine("  " + row.description, "description"))
        else:
            lines.append(DisplayLine("no matches", "empty"))
        if height > 2:
            lines.append(DisplayLine(""))
            lines.append(DisplayLine(skill_popup_hint_line(), "hint"))
        return lines[:height]

    def _ensure_visible(self, length: int) -> None:
        if self.selected_idx is None or length == 0:
            self.scroll_top = 0
            return
        visible = min(MAX_POPUP_ROWS, length)
        if self.selected_idx < self.scroll_top:
            self.scroll_top = self.selected_idx
        elif self.selected_idx >= self.scroll_top + visible:
            self.scroll_top = self.selected_idx + 1 - visible
        self.scroll_top = max(0, min(self.scroll_top, max(0, length - visible)))


def render_ref(popup: SkillPopup, area: Any = None, buf: Any = None) -> list[DisplayLine]:
    return popup.render_ref(area, buf)


def skill_popup_hint_line() -> str:
    return "Press Enter to insert or Esc to close"


def truncate_text(text: str, max_len: int) -> str:
    text = str(text)
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"[:max_len]
    return text[: max_len - 1] + "…"


def fuzzy_match(haystack: str, needle: str) -> tuple[list[int], int] | None:
    needle_lower = needle.lower()
    haystack_lower = haystack.lower()
    indices: list[int] = []
    start = 0
    for ch in needle_lower:
        found = haystack_lower.find(ch, start)
        if found == -1:
            return None
        indices.append(found)
        start = found + 1
    return indices, _fuzzy_score(haystack, needle, indices)


def _fuzzy_score(haystack: str, needle: str, indices: list[int]) -> int:
    lower = haystack.lower()
    needle = needle.lower()
    if lower.startswith(needle):
        next_char = lower[len(needle) : len(needle) + 1]
        if next_char == " ":
            prefix_bonus = 0
        elif next_char in {"-", "_"}:
            prefix_bonus = 1
        else:
            prefix_bonus = 2
        return prefix_bonus
    spread = indices[-1] - indices[0] if indices else 0
    return 10 + indices[0] + spread + len(haystack)


def _combined_description(category_tag: str | None, description: str | None) -> str | None:
    if category_tag and description:
        return f"{category_tag} {description}"
    if category_tag:
        return category_tag
    if description:
        return description
    return None


def mention_item(index: int) -> MentionItem:
    return MentionItem(
        display_name=f"Mention {index:02}",
        description=f"Description {index:02}",
        insert_text=f"$mention-{index:02}",
        search_terms=[f"mention-{index:02}"],
        path=f"skill://mention-{index:02}",
        category_tag="[Skill]",
        sort_rank=1,
    )


def ranked_mention_item(
    display_name: str,
    search_terms: list[str] | tuple[str, ...],
    category_tag: str,
    sort_rank: int,
) -> MentionItem:
    return MentionItem(
        display_name=display_name,
        description=None,
        insert_text=f"${display_name}",
        search_terms=list(search_terms),
        path=None,
        category_tag=category_tag,
        sort_rank=sort_rank,
    )


def named_mention_item(display_name: str, search_terms: list[str] | tuple[str, ...]) -> MentionItem:
    return ranked_mention_item(display_name, search_terms, "[Skill]", 1)


def plugin_mention_item(display_name: str, search_terms: list[str] | tuple[str, ...]) -> MentionItem:
    return ranked_mention_item(display_name, search_terms, "[Plugin]", 0)


def _area_width(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("width", 0))
    if isinstance(area, tuple) and len(area) >= 3:
        return int(area[2])
    return int(getattr(area, "width", 0))


def _area_height(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("height", 0))
    if isinstance(area, tuple) and len(area) >= 4:
        return int(area[3])
    return int(getattr(area, "height", 0))


__all__ = [
    "DisplayLine",
    "DisplayRow",
    "MENTION_NAME_TRUNCATE_LEN",
    "MentionItem",
    "RUST_MODULE",
    "SkillPopup",
    "fuzzy_match",
    "mention_item",
    "named_mention_item",
    "plugin_mention_item",
    "ranked_mention_item",
    "render_ref",
    "skill_popup_hint_line",
    "truncate_text",
]
