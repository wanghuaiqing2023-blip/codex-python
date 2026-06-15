"""Skill mention popup.

Python port of Rust ``codex-tui::bottom_pane::skill_popup``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from .popup_consts import MAX_POPUP_ROWS

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::skill_popup",
    source="codex/codex-rs/tui/src/bottom_pane/skill_popup.rs",
    status="complete",
)

MENTION_NAME_TRUNCATE_LEN = 28


@dataclass
class MentionItem:
    display_name: str
    description: Optional[str]
    insert_text: str
    search_terms: List[str] = field(default_factory=list)
    path: Optional[str] = None
    category_tag: Optional[str] = None
    sort_rank: int = 0


@dataclass(frozen=True)
class DisplayRow:
    name: str
    description: Optional[str] = None
    match_indices: Optional[List[int]] = None
    selected: bool = False


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class SkillPopup:
    mentions: List[MentionItem]
    query: str = ""
    selected_idx: Optional[int] = None
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

    def selected_mention(self) -> Optional[MentionItem]:
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

    def filtered_items(self) -> List[int]:
        return [idx for idx, _indices, _score in self.filtered()]

    def rows_from_matches(self, matches: List[Tuple[int, Optional[List[int]], int]]) -> List[DisplayRow]:
        rows = []
        for visible_idx, (idx, indices, _score) in enumerate(matches):
            mention = self.mentions[idx]
            rows.append(
                DisplayRow(
                    name=truncate_text(mention.display_name, MENTION_NAME_TRUNCATE_LEN),
                    description=_combined_description(mention.category_tag, mention.description),
                    match_indices=indices,
                    selected=self.selected_idx == visible_idx,
                )
            )
        return rows

    def filtered(self) -> List[Tuple[int, Optional[List[int]], int]]:
        filter_text = self.query.strip()
        out = []
        for idx, mention in enumerate(self.mentions):
            if not filter_text:
                out.append((idx, None, 0))
                continue

            display = fuzzy_match(mention.display_name, filter_text)
            if display is not None:
                indices, score = display
                out.append((idx, indices, score))
                continue

            term_scores = []
            for term in mention.search_terms:
                if term == mention.display_name:
                    continue
                matched = fuzzy_match(term, filter_text)
                if matched is not None:
                    _indices, score = matched
                    term_scores.append(score)
            if term_scores:
                out.append((idx, None, min(term_scores)))

        def key(row: Tuple[int, Optional[List[int]], int]) -> Tuple[Any, ...]:
            idx, indices, score = row
            mention = self.mentions[idx]
            if filter_text:
                return (indices is None, score, mention.sort_rank, mention.display_name)
            return (mention.sort_rank, mention.display_name)

        out.sort(key=key)
        return out

    def render_ref(self, area: Any = None, buf: Any = None) -> List[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width == 0 or height == 0:
            return []
        rows = self.rows_from_matches(self.filtered())
        visible_height = height - 2 if height > 2 else height
        lines = []
        if rows:
            for row in rows[self.scroll_top : self.scroll_top + min(MAX_POPUP_ROWS, visible_height)]:
                prefix = "> " if row.selected else "  "
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


def render_ref(popup: SkillPopup, area: Any = None, buf: Any = None) -> List[DisplayLine]:
    return popup.render_ref(area, buf)


def skill_popup_hint_line() -> str:
    return "Press Enter to insert or Esc to close"


def truncate_text(text: str, max_len: int) -> str:
    text = str(text)
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "."[:max_len]
    return text[: max_len - 1] + "."


def fuzzy_match(haystack: str, needle: str) -> Optional[Tuple[List[int], int]]:
    needle_lower = needle.lower()
    haystack_lower = haystack.lower()
    indices = []
    start = 0
    for char in needle_lower:
        found = haystack_lower.find(char, start)
        if found == -1:
            return None
        indices.append(found)
        start = found + 1
    return indices, _fuzzy_score(haystack, needle, indices)


def _fuzzy_score(haystack: str, needle: str, indices: List[int]) -> int:
    lower = haystack.lower()
    needle = needle.lower()
    if lower.startswith(needle):
        next_char = lower[len(needle) : len(needle) + 1]
        if next_char == " ":
            return 0
        if next_char in {"-", "_"}:
            return 1
        return 2
    spread = indices[-1] - indices[0] if indices else 0
    return 10 + indices[0] + spread + len(haystack)


def _combined_description(category_tag: Optional[str], description: Optional[str]) -> Optional[str]:
    if category_tag and description:
        return "{} {}".format(category_tag, description)
    if category_tag:
        return category_tag
    if description:
        return description
    return None


def mention_item(index: int) -> MentionItem:
    return MentionItem(
        display_name="Mention {:02}".format(index),
        description="Description {:02}".format(index),
        insert_text="$mention-{:02}".format(index),
        search_terms=["mention-{:02}".format(index)],
        path="skill://mention-{:02}".format(index),
        category_tag="[Skill]",
        sort_rank=1,
    )


def ranked_mention_item(
    display_name: str,
    search_terms: Iterable[str],
    category_tag: str,
    sort_rank: int,
) -> MentionItem:
    return MentionItem(
        display_name=display_name,
        description=None,
        insert_text="${}".format(display_name),
        search_terms=list(search_terms),
        path=None,
        category_tag=category_tag,
        sort_rank=sort_rank,
    )


def named_mention_item(display_name: str, search_terms: Iterable[str]) -> MentionItem:
    return ranked_mention_item(display_name, search_terms, "[Skill]", 1)


def plugin_mention_item(display_name: str, search_terms: Iterable[str]) -> MentionItem:
    return ranked_mention_item(display_name, search_terms, "[Plugin]", 0)


def filtered_mentions_preserve_results_beyond_popup_height() -> bool:
    popup = SkillPopup.new(mention_item(idx) for idx in range(MAX_POPUP_ROWS + 2))
    names = [popup.mentions[idx].display_name for idx in popup.filtered_items()]
    return names == ["Mention {:02}".format(idx) for idx in range(MAX_POPUP_ROWS + 2)] and popup.calculate_required_height(72) == MAX_POPUP_ROWS + 2


def scrolling_mentions_shifts_rendered_window_snapshot() -> bool:
    popup = SkillPopup.new(mention_item(idx) for idx in range(MAX_POPUP_ROWS + 2))
    for _ in range(MAX_POPUP_ROWS + 1):
        popup.move_down()
    rendered = popup.render_ref((0, 0, 72, popup.calculate_required_height(72)))
    return popup.selected_idx == MAX_POPUP_ROWS + 1 and popup.scroll_top == 2 and rendered[0].text.startswith("  Mention 02")


def display_name_match_sorting_beats_worse_secondary_search_term_matches() -> bool:
    popup = SkillPopup.new(
        [
            named_mention_item("pr-review-triage", ["pr-review-triage"]),
            named_mention_item("prd", ["prd"]),
            named_mention_item("PR Babysitter", ["babysit-pr", "PR Babysitter"]),
            named_mention_item("Plugin Creator", ["plugin-creator", "Plugin Creator"]),
            named_mention_item("Logging Best Practices", ["logging-best-practices", "Logging Best Practices"]),
        ]
    )
    popup.set_query("pr")
    return [popup.mentions[idx].display_name for idx in popup.filtered_items()] == [
        "PR Babysitter",
        "pr-review-triage",
        "prd",
        "Plugin Creator",
        "Logging Best Practices",
    ]


def query_match_score_sorts_before_plugin_rank_bias() -> bool:
    popup = SkillPopup.new(
        [
            plugin_mention_item("GitHub", ["github", "pull requests", "pr"]),
            named_mention_item("pr-review-triage", ["pr-review-triage"]),
            named_mention_item("prd", ["prd"]),
            named_mention_item("Plugin Creator", ["plugin-creator", "Plugin Creator"]),
            named_mention_item("Logging Best Practices", ["logging-best-practices", "Logging Best Practices"]),
            named_mention_item("PR Babysitter", ["babysit-pr", "PR Babysitter"]),
        ]
    )
    popup.set_query("pr")
    return [(popup.mentions[idx].display_name, popup.mentions[idx].category_tag) for idx in popup.filtered_items()] == [
        ("PR Babysitter", "[Skill]"),
        ("pr-review-triage", "[Skill]"),
        ("prd", "[Skill]"),
        ("Plugin Creator", "[Skill]"),
        ("Logging Best Practices", "[Skill]"),
        ("GitHub", "[Plugin]"),
    ]


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
    "display_name_match_sorting_beats_worse_secondary_search_term_matches",
    "filtered_mentions_preserve_results_beyond_popup_height",
    "fuzzy_match",
    "mention_item",
    "named_mention_item",
    "plugin_mention_item",
    "query_match_score_sorts_before_plugin_rank_bias",
    "ranked_mention_item",
    "render_ref",
    "scrolling_mentions_shifts_rendered_window_snapshot",
    "skill_popup_hint_line",
    "truncate_text",
]
