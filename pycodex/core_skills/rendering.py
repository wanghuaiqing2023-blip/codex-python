"""Skill metadata rendering helpers ported from Codex core-skills.

This module covers the dependency-free budgeted rendering and alias-table
planning slices of ``codex-rs/core-skills/src/render.rs``. Telemetry side
effects are kept outside this slice.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core.context import render_available_skills_body
from pycodex.core_skills.model import SkillMetadata
from pycodex.core_skills.invocation_utils import SkillLoadOutcome

JsonValue = Any

DEFAULT_SKILL_METADATA_CHAR_BUDGET = 8000
SKILL_METADATA_CONTEXT_WINDOW_PERCENT = 2
SKILL_DESCRIPTION_TRUNCATION_WARNING_THRESHOLD_CHARS = 100
APPROX_BYTES_PER_TOKEN = 4
SKILL_DESCRIPTION_TRUNCATED_WARNING = "Skill descriptions were shortened to fit the skills context budget. Codex can still see every skill, but some descriptions are shorter. Disable unused skills or plugins to leave more room for the rest."
SKILL_DESCRIPTION_TRUNCATED_WARNING_WITH_PERCENT = "Skill descriptions were shortened to fit the 2% skills context budget. Codex can still see every skill, but some descriptions are shorter. Disable unused skills or plugins to leave more room for the rest."
SKILL_DESCRIPTIONS_REMOVED_WARNING_PREFIX = "Exceeded skills context budget. All skill descriptions were removed and"


class SkillMetadataBudgetKind(str, Enum):
    TOKENS = "tokens"
    CHARACTERS = "characters"


@dataclass(frozen=True)
class SkillMetadataBudget:
    kind: SkillMetadataBudgetKind
    limit: int

    def __post_init__(self) -> None:
        kind = self.kind if isinstance(self.kind, SkillMetadataBudgetKind) else SkillMetadataBudgetKind(str(self.kind))
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "limit", max(int(self.limit), 0))

    @classmethod
    def tokens(cls, limit: int) -> "SkillMetadataBudget":
        return cls(SkillMetadataBudgetKind.TOKENS, max(int(limit), 0))

    @classmethod
    def characters(cls, limit: int) -> "SkillMetadataBudget":
        return cls(SkillMetadataBudgetKind.CHARACTERS, max(int(limit), 0))

    def cost(self, text: str) -> int:
        if self.kind is SkillMetadataBudgetKind.TOKENS:
            return approx_token_count(text)
        return len(text)

    def cost_from_counts(self, chars: int, bytes_count: int) -> int:
        if self.kind is SkillMetadataBudgetKind.TOKENS:
            return approx_token_count_from_bytes(bytes_count)
        return chars


@dataclass(frozen=True)
class SkillRenderReport:
    total_count: int
    included_count: int
    omitted_count: int
    truncated_description_chars: int
    truncated_description_count: int

    def average_truncated_description_chars(self) -> int:
        if self.total_count == 0 or self.truncated_description_chars == 0:
            return 0
        return (self.truncated_description_chars + self.total_count - 1) // self.total_count


@dataclass(frozen=True)
class AvailableSkills:
    skill_root_lines: tuple[str, ...] = ()
    skill_lines: tuple[str, ...] = ()
    report: SkillRenderReport = SkillRenderReport(0, 0, 0, 0, 0)
    warning_message: str | None = None


@dataclass(frozen=True)
class SkillPathAliases:
    skill_root_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class AliasPlan:
    aliases: SkillPathAliases
    root_aliases: Mapping[Path, str]
    alias_root_by_path: Mapping[Path, Path]
    table_cost: int


@dataclass(frozen=True)
class SkillLine:
    name: str
    description: str
    path: str

    @classmethod
    def from_skill(cls, skill: SkillMetadata | Mapping[str, JsonValue] | Any) -> "SkillLine":
        metadata = _coerce_skill_metadata(skill)
        path = "" if metadata.path_to_skills_md is None else str(metadata.path_to_skills_md).replace("\\", "/")
        return cls(metadata.name, metadata.description or "", path)

    @classmethod
    def with_path(cls, skill: SkillMetadata | Mapping[str, JsonValue] | Any, path: str) -> "SkillLine":
        metadata = _coerce_skill_metadata(skill)
        return cls(metadata.name, metadata.description or "", path)

    def full_cost(self, budget: SkillMetadataBudget) -> int:
        return line_cost(budget, self.render_full())

    def minimum_cost(self, budget: SkillMetadataBudget) -> int:
        return line_cost(budget, self.render_minimum())

    def description_char_count(self) -> int:
        return len(self.description)

    def render_full(self) -> str:
        return self.render_with_description(self.description)

    def render_minimum(self) -> str:
        return self.render_with_description("")

    def render_with_description_chars(self, description_chars: int) -> str:
        if description_chars <= 0:
            return self.render_minimum()
        return self.render_with_description(self.description[:description_chars])

    def render_with_description(self, description: str) -> str:
        if not description:
            return f"- {self.name}: (file: {self.path})"
        return f"- {self.name}: {description} (file: {self.path})"


@dataclass(frozen=True)
class RenderedSkillLine:
    line: str
    truncated_chars: int


@dataclass(frozen=True)
class _DescriptionBudgetLine:
    line: SkillLine
    description_char_count: int
    extra_costs: tuple[int, ...]

    @classmethod
    def new(cls, line: SkillLine, budget: SkillMetadataBudget) -> "_DescriptionBudgetLine":
        minimum_line = line.render_minimum()
        minimum_chars = len(minimum_line) + 1
        minimum_bytes = len(minimum_line.encode("utf-8")) + 1
        minimum_cost = budget.cost_from_counts(minimum_chars, minimum_bytes)

        extra_costs = [0]
        prefix_chars = 0
        prefix_bytes = 0
        for char in line.description:
            prefix_chars += 1
            prefix_bytes += len(char.encode("utf-8"))
            rendered_chars = minimum_chars + prefix_chars + 1
            rendered_bytes = minimum_bytes + prefix_bytes + 1
            cost = max(budget.cost_from_counts(rendered_chars, rendered_bytes) - minimum_cost, 0)
            extra_costs.append(cost)
        return cls(line, line.description_char_count(), tuple(extra_costs))


def default_skill_metadata_budget(context_window: int | None) -> SkillMetadataBudget:
    if context_window is not None and context_window > 0:
        return SkillMetadataBudget.tokens(max(context_window * SKILL_METADATA_CONTEXT_WINDOW_PERCENT // 100, 1))
    return SkillMetadataBudget.characters(DEFAULT_SKILL_METADATA_CHAR_BUDGET)


def approx_token_count_from_bytes(bytes_count: int) -> int:
    return (max(bytes_count, 0) + APPROX_BYTES_PER_TOKEN - 1) // APPROX_BYTES_PER_TOKEN


def approx_token_count(text: str) -> int:
    return approx_token_count_from_bytes(len(text.encode("utf-8")))


def line_cost(budget: SkillMetadataBudget, line: str) -> int:
    return budget.cost(f"{line}\n")


def lines_cost(budget: SkillMetadataBudget, lines: Iterable[str]) -> int:
    return sum(line_cost(budget, line) for line in lines)


def aliased_metadata_overhead_cost(budget: SkillMetadataBudget, skill_root_lines: Iterable[str]) -> int:
    roots = tuple(skill_root_lines)
    absolute_body = render_available_skills_body((), ())
    aliased_body = render_available_skills_body(roots, ())
    return max(budget.cost(aliased_body) - budget.cost(absolute_body), 0)


def available_skills_cost(budget: SkillMetadataBudget, available: AvailableSkills) -> int:
    metadata_cost = 0
    if available.skill_root_lines:
        metadata_cost = aliased_metadata_overhead_cost(budget, available.skill_root_lines)
    return metadata_cost + lines_cost(budget, available.skill_lines)


def aliased_render_is_better(
    aliased: AvailableSkills,
    absolute: AvailableSkills,
    budget: SkillMetadataBudget,
) -> bool:
    if aliased.report.included_count != absolute.report.included_count:
        return aliased.report.included_count > absolute.report.included_count
    if aliased.report.truncated_description_chars != absolute.report.truncated_description_chars:
        return aliased.report.truncated_description_chars < absolute.report.truncated_description_chars
    return available_skills_cost(budget, aliased) < available_skills_cost(budget, absolute)


def build_skill_root_lines(roots: Iterable[Path | str]) -> tuple[str, ...]:
    return tuple(f"- `r{index}` = `{_normalized_path(root)}`" for index, root in enumerate(roots))


def ordered_alias_roots(
    used_roots: Iterable[Path | str],
    alias_root_by_skill_root: Mapping[Path, Path],
) -> tuple[Path, ...] | None:
    seen: set[Path] = set()
    alias_roots: list[Path] = []
    for raw_root in used_roots:
        root = Path(str(raw_root))
        alias_root = alias_root_by_skill_root.get(root)
        if alias_root is None:
            return None
        if alias_root not in seen:
            seen.add(alias_root)
            alias_roots.append(alias_root)
    return tuple(alias_roots)


def alias_root_for_skill_root(
    root: Path | str,
    plugin_version_skill_counts: Mapping[Path, int],
) -> Path:
    root_path = Path(str(root))
    plugin_base = plugin_version_base(root_path)
    if plugin_base is None:
        return root_path
    if plugin_version_skill_counts.get(plugin_base, 0) > 1:
        return root_path
    return plugin_marketplace_base(root_path) or root_path


def plugin_version_skill_counts_for_skill_roots(skill_roots: Iterable[Path | str]) -> dict[Path, int]:
    counts: dict[Path, int] = {}
    for root in skill_roots:
        plugin_base = plugin_version_base(Path(str(root)))
        if plugin_base is not None:
            counts[plugin_base] = counts.get(plugin_base, 0) + 1
    return counts


def plugin_marketplace_base(path: Path | str) -> Path | None:
    candidate = Path(str(path))
    while True:
        parent = candidate.parent
        grandparent = parent.parent
        if parent != candidate and parent.name == "cache" and grandparent.name == "plugins":
            return candidate
        if parent == candidate:
            return None
        candidate = parent


def plugin_version_base(path: Path | str) -> Path | None:
    path_obj = Path(str(path))
    marketplace_base = plugin_marketplace_base(path_obj)
    if marketplace_base is None:
        return None
    try:
        relative_parts = path_obj.relative_to(marketplace_base).parts
    except ValueError:
        return None
    if len(relative_parts) < 2:
        return None
    return marketplace_base / relative_parts[0] / relative_parts[1]


def render_skill_path_with_aliases(
    skill: SkillMetadata | Mapping[str, JsonValue] | Any,
    plan: AliasPlan,
) -> str:
    metadata = _coerce_skill_metadata(skill)
    relative = outcome_relative_skill_path(metadata, plan)
    if relative is not None:
        return relative
    return "" if metadata.path_to_skills_md is None else _normalized_path(metadata.path_to_skills_md)


def outcome_relative_skill_path(skill: SkillMetadata, plan: AliasPlan) -> str | None:
    if skill.path_to_skills_md is None:
        return None
    path = Path(str(skill.path_to_skills_md))
    alias_root = plan.alias_root_by_path.get(path)
    if alias_root is None:
        return None
    alias = plan.root_aliases.get(alias_root)
    if alias is None:
        return None
    try:
        relative_path = path.relative_to(alias_root)
    except ValueError:
        return None
    return f"{alias}/{_normalized_path(relative_path)}"


def build_available_skills_from_metadata(
    skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
    budget: SkillMetadataBudget,
) -> AvailableSkills | None:
    skill_items = tuple(_coerce_skill_metadata(skill) for skill in skills)
    if not skill_items:
        return None
    ordered = sorted(skill_items, key=_budget_sort_key)
    skill_lines = tuple(SkillLine.from_skill(skill) for skill in ordered)
    return build_available_skills_from_lines(skill_lines, len(skill_items), budget)


def build_available_skills(
    outcome: SkillLoadOutcome,
    budget: SkillMetadataBudget,
) -> AvailableSkills | None:
    skills = outcome.allowed_skills_for_implicit_invocation()
    if not skills:
        return None

    absolute = build_available_skills_from_metadata(skills, budget)
    if absolute is None:
        return None
    if absolute.report.omitted_count == 0 and absolute.report.truncated_description_chars == 0:
        return absolute

    aliased = build_aliased_available_skills(outcome, skills, budget)
    if aliased is not None and aliased_render_is_better(aliased, absolute, budget):
        return aliased
    return absolute


def build_aliased_available_skills(
    outcome: SkillLoadOutcome,
    skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
    budget: SkillMetadataBudget,
) -> AvailableSkills | None:
    skill_items = tuple(_coerce_skill_metadata(skill) for skill in skills)
    plan = build_alias_plan(outcome, skill_items, budget)
    if plan is None or plan.table_cost >= budget.limit:
        return None

    adjusted_limit = max(budget.limit - plan.table_cost, 0)
    adjusted_budget = SkillMetadataBudget(budget.kind, adjusted_limit)
    ordered = sorted(skill_items, key=_budget_sort_key)
    skill_lines = tuple(SkillLine.with_path(skill, render_skill_path_with_aliases(skill, plan)) for skill in ordered)
    return build_available_skills_from_lines(
        skill_lines,
        len(skill_items),
        adjusted_budget,
        plan.aliases.skill_root_lines,
    )


def build_alias_plan(
    outcome: SkillLoadOutcome,
    skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
    budget: SkillMetadataBudget,
) -> AliasPlan | None:
    skill_items = tuple(_coerce_skill_metadata(skill) for skill in skills)
    skill_paths = {Path(str(skill.path_to_skills_md)) for skill in skill_items if skill.path_to_skills_md is not None}
    skill_root_by_path = {
        Path(str(path)): Path(str(root))
        for path, root in outcome.skill_root_by_path.items()
        if Path(str(path)) in skill_paths
    }
    used_roots = tuple(root for root in outcome.skill_roots if Path(str(root)) in set(skill_root_by_path.values()))
    if not used_roots:
        return None

    plugin_version_skill_counts = plugin_version_skill_counts_for_skill_roots(skill_root_by_path.values())
    alias_root_by_skill_root = {
        Path(str(root)): alias_root_for_skill_root(Path(str(root)), plugin_version_skill_counts)
        for root in used_roots
    }
    alias_roots = ordered_alias_roots(used_roots, alias_root_by_skill_root)
    if alias_roots is None:
        return None

    root_aliases = {alias_root: f"r{index}" for index, alias_root in enumerate(alias_roots)}
    alias_root_by_path = {
        path: alias_root_by_skill_root[skill_root]
        for path, skill_root in skill_root_by_path.items()
        if skill_root in alias_root_by_skill_root
    }
    skill_root_lines = build_skill_root_lines(alias_roots)
    table_cost = aliased_metadata_overhead_cost(budget, skill_root_lines)
    return AliasPlan(
        aliases=SkillPathAliases(skill_root_lines),
        root_aliases=root_aliases,
        alias_root_by_path=alias_root_by_path,
        table_cost=table_cost,
    )


def build_available_skills_from_lines(
    skill_lines: Iterable[SkillLine],
    total_count: int,
    budget: SkillMetadataBudget,
    skill_root_lines: Iterable[str] = (),
) -> AvailableSkills | None:
    lines = tuple(skill_lines)
    if total_count == 0:
        return None
    rendered_lines, report = render_skill_lines_from_lines(lines, total_count, budget)
    warning_message = _warning_message(report, budget)
    return AvailableSkills(tuple(skill_root_lines), tuple(rendered_lines), report, warning_message)


def render_skill_lines_from_lines(
    skill_lines: Iterable[SkillLine],
    total_count: int,
    budget: SkillMetadataBudget,
) -> tuple[tuple[str, ...], SkillRenderReport]:
    lines = tuple(skill_lines)
    full_cost = sum(line.full_cost(budget) for line in lines)
    if full_cost <= budget.limit:
        return (
            tuple(line.render_full() for line in lines),
            SkillRenderReport(total_count, len(lines), 0, 0, 0),
        )

    minimum_cost = sum(line.minimum_cost(budget) for line in lines)
    if minimum_cost <= budget.limit:
        rendered = render_lines_with_description_budget(budget, lines, budget.limit - minimum_cost)
        truncated_chars, truncated_count = sum_description_truncation(rendered)
        return (
            tuple(line.line for line in rendered),
            SkillRenderReport(total_count, len(lines), 0, truncated_chars, truncated_count),
        )

    return render_minimum_skill_lines_until_budget(budget, lines, total_count)


def render_minimum_skill_lines_until_budget(
    budget: SkillMetadataBudget,
    skill_lines: Iterable[SkillLine],
    total_count: int,
) -> tuple[tuple[str, ...], SkillRenderReport]:
    included: list[str] = []
    used = 0
    omitted_count = 0
    truncated_description_chars = 0
    truncated_description_count = 0
    for line in skill_lines:
        line_minimum_cost = line.minimum_cost(budget)
        description_chars = line.description_char_count()
        if used + line_minimum_cost <= budget.limit:
            used += line_minimum_cost
            included.append(line.render_minimum())
        else:
            omitted_count += 1
        truncated_description_chars += description_chars
        if description_chars > 0:
            truncated_description_count += 1
    return (
        tuple(included),
        SkillRenderReport(
            total_count,
            len(included),
            omitted_count,
            truncated_description_chars,
            truncated_description_count,
        ),
    )


def render_lines_with_description_budget(
    budget: SkillMetadataBudget,
    skill_lines: Iterable[SkillLine],
    limit: int,
) -> tuple[RenderedSkillLine, ...]:
    budget_lines = tuple(_DescriptionBudgetLine.new(line, budget) for line in skill_lines)
    char_allocations = [0] * len(budget_lines)
    current_extra_costs = [0] * len(budget_lines)
    remaining = max(limit, 0)

    while True:
        changed = False
        for index, line in enumerate(budget_lines):
            if char_allocations[index] >= line.description_char_count:
                continue
            current_cost = current_extra_costs[index]
            next_chars = char_allocations[index] + 1
            next_cost = line.extra_costs[next_chars]
            delta = max(next_cost - current_cost, 0)
            if delta <= remaining:
                char_allocations[index] = next_chars
                current_extra_costs[index] = next_cost
                remaining -= delta
                changed = True
        if not changed:
            break

    return tuple(
        RenderedSkillLine(
            line.line.render_with_description_chars(description_chars),
            max(line.description_char_count - description_chars, 0),
        )
        for line, description_chars in zip(budget_lines, char_allocations)
    )


def sum_description_truncation(rendered: Iterable[RenderedSkillLine]) -> tuple[int, int]:
    chars = 0
    count = 0
    for line in rendered:
        if line.truncated_chars:
            chars += line.truncated_chars
            count += 1
    return chars, count


def budget_warning_prefix(budget: SkillMetadataBudget, warning: str) -> str:
    if budget.kind is SkillMetadataBudgetKind.TOKENS:
        return warning.replace("skills context budget", "2% skills context budget")
    return warning


def _warning_message(report: SkillRenderReport, budget: SkillMetadataBudget) -> str | None:
    if report.omitted_count > 0:
        skill_word = "skill" if report.omitted_count == 1 else "skills"
        verb = "was" if report.omitted_count == 1 else "were"
        return (
            f"{budget_warning_prefix(budget, SKILL_DESCRIPTIONS_REMOVED_WARNING_PREFIX)} "
            f"{report.omitted_count} additional {skill_word} {verb} not included in the model-visible skills list."
        )
    if report.average_truncated_description_chars() > SKILL_DESCRIPTION_TRUNCATION_WARNING_THRESHOLD_CHARS:
        if budget.kind is SkillMetadataBudgetKind.TOKENS:
            return SKILL_DESCRIPTION_TRUNCATED_WARNING_WITH_PERCENT
        return SKILL_DESCRIPTION_TRUNCATED_WARNING
    return None


def _normalized_path(path: Path | str) -> str:
    return str(Path(str(path))).replace("\\", "/")


def _budget_sort_key(skill: SkillMetadata) -> tuple[int, str, str]:
    return (
        _prompt_scope_rank(str(skill.scope)),
        skill.name,
        str(skill.path_to_skills_md or ""),
    )


def _prompt_scope_rank(scope: str) -> int:
    return {
        "system": 0,
        "admin": 1,
        "repo": 2,
        "user": 3,
    }.get(scope.lower(), 3)


def _coerce_skill_metadata(value: SkillMetadata | Mapping[str, JsonValue] | Any) -> SkillMetadata:
    if isinstance(value, SkillMetadata):
        return value
    if isinstance(value, Mapping):
        path = value.get("path_to_skills_md", value.get("path"))
        return SkillMetadata(
            name=str(value["name"]),
            description=str(value.get("description", "")),
            path_to_skills_md=None if path is None else Path(str(path)),
        )
    path = getattr(value, "path_to_skills_md", getattr(value, "path", None))
    return SkillMetadata(
        name=str(getattr(value, "name")),
        description=str(getattr(value, "description", "")),
        path_to_skills_md=None if path is None else Path(str(path)),
    )


__all__ = [
    "APPROX_BYTES_PER_TOKEN",
    "AliasPlan",
    "AvailableSkills",
    "DEFAULT_SKILL_METADATA_CHAR_BUDGET",
    "RenderedSkillLine",
    "SKILL_DESCRIPTION_TRUNCATED_WARNING",
    "SKILL_DESCRIPTION_TRUNCATED_WARNING_WITH_PERCENT",
    "SKILL_DESCRIPTION_TRUNCATION_WARNING_THRESHOLD_CHARS",
    "SKILL_DESCRIPTIONS_REMOVED_WARNING_PREFIX",
    "SKILL_METADATA_CONTEXT_WINDOW_PERCENT",
    "SkillLine",
    "SkillMetadataBudget",
    "SkillMetadataBudgetKind",
    "SkillPathAliases",
    "SkillRenderReport",
    "alias_root_for_skill_root",
    "aliased_metadata_overhead_cost",
    "aliased_render_is_better",
    "approx_token_count",
    "approx_token_count_from_bytes",
    "available_skills_cost",
    "build_alias_plan",
    "build_aliased_available_skills",
    "build_available_skills",
    "build_available_skills_from_lines",
    "build_available_skills_from_metadata",
    "build_skill_root_lines",
    "budget_warning_prefix",
    "default_skill_metadata_budget",
    "line_cost",
    "lines_cost",
    "ordered_alias_roots",
    "outcome_relative_skill_path",
    "plugin_marketplace_base",
    "plugin_version_base",
    "plugin_version_skill_counts_for_skill_roots",
    "render_lines_with_description_budget",
    "render_minimum_skill_lines_until_budget",
    "render_skill_path_with_aliases",
    "render_skill_lines_from_lines",
    "sum_description_truncation",
]
