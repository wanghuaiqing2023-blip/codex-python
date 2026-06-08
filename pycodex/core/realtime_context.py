"""Realtime startup context helpers ported from ``core/src/realtime_context.rs``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from pycodex.protocol import ContentItem, ResponseItem, TruncationPolicyConfig

from .context import is_contextual_user_fragment
from pycodex.utils.string import approx_token_count
from .tools.context import truncate_text

STARTUP_CONTEXT_HEADER = "Startup context from Codex.\nThis is background context about recent work and machine/workspace layout. It may be incomplete or stale. Use it to inform responses, and do not repeat it back unless relevant."
STARTUP_CONTEXT_OPEN_TAG = "<startup_context>"
STARTUP_CONTEXT_CLOSE_TAG = "</startup_context>"
CURRENT_THREAD_SECTION_TOKEN_BUDGET = 1_200
RECENT_WORK_SECTION_TOKEN_BUDGET = 2_200
WORKSPACE_SECTION_TOKEN_BUDGET = 1_600
NOTES_SECTION_TOKEN_BUDGET = 300
REALTIME_TURN_TOKEN_BUDGET = 300
MAX_RECENT_WORK_GROUPS = 8
MAX_CURRENT_CWD_ASKS = 8
MAX_OTHER_CWD_ASKS = 5
MAX_ASK_CHARS = 240
TREE_MAX_DEPTH = 2
DIR_ENTRY_LIMIT = 20
NOISY_DIR_NAMES = frozenset(
    {
        ".git",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "out",
        "target",
    }
)


def build_realtime_startup_context(
    current_thread_items: Iterable[ResponseItem | dict[str, object]] = (),
    recent_threads: Iterable[object] = (),
    cwd: Path | str | None = None,
    user_root: Path | str | None = None,
    budget_tokens: int = 0,
) -> str | None:
    """Build the startup context blob assembled by Rust ``build_realtime_startup_context``.

    The Rust implementation gathers these inputs from ``Session``.  The Python
    port keeps the same section ordering and per-section budgets while accepting
    already-loaded inputs so callers can wire in session/thread-store state
    incrementally.
    """

    del budget_tokens  # Rust currently logs the requested budget but applies fixed per-section caps.
    current_thread_section = build_current_thread_section(current_thread_items)
    cwd_path = Path(cwd) if cwd is not None else None
    recent_work_section = build_recent_work_section(cwd_path, recent_threads) if cwd_path is not None else None
    workspace_section = build_workspace_section_with_user_root(cwd_path, user_root) if cwd_path is not None else None

    if current_thread_section is None and recent_work_section is None and workspace_section is None:
        return None

    parts = [STARTUP_CONTEXT_HEADER]
    for title, body, budget in (
        ("Current Thread", current_thread_section, CURRENT_THREAD_SECTION_TOKEN_BUDGET),
        ("Recent Work", recent_work_section, RECENT_WORK_SECTION_TOKEN_BUDGET),
        ("Machine / Workspace Map", workspace_section, WORKSPACE_SECTION_TOKEN_BUDGET),
        (
            "Notes",
            "Built at realtime startup from the current thread history, local thread metadata, and a bounded local workspace scan. This excludes repo memory instructions, AGENTS files, project-doc prompt blends, and memory summaries.",
            NOTES_SECTION_TOKEN_BUDGET,
        ),
    ):
        section = format_section(title, body, budget)
        if section is not None:
            parts.append(section)
    return format_startup_context_blob("\n\n".join(parts))


def build_current_thread_section(items: Iterable[ResponseItem | dict[str, object]]) -> str | None:
    turns: list[tuple[list[str], list[str]]] = []
    current_user: list[str] = []
    current_assistant: list[str] = []

    for raw_item in items:
        item = raw_item if isinstance(raw_item, ResponseItem) else ResponseItem.from_mapping(raw_item)
        if item.type != "message":
            continue
        if item.role == "user":
            if _is_contextual_user_message_content(item.content):
                continue
            text = _content_items_to_text(item.content)
            if text is None:
                continue
            text = text.strip()
            if not text:
                continue
            if current_user or current_assistant:
                turns.append((current_user, current_assistant))
                current_user = []
                current_assistant = []
            current_user.append(text)
        elif item.role == "assistant":
            text = _content_items_to_text(item.content)
            if text is None:
                continue
            text = text.strip()
            if not text:
                continue
            if not current_user and not current_assistant:
                continue
            current_assistant.append(text)

    if current_user or current_assistant:
        turns.append((current_user, current_assistant))

    if not turns:
        return None

    lines = [
        "Most recent user/assistant turns from this exact thread. Use them for continuity when responding."
    ]
    remaining_budget = max(CURRENT_THREAD_SECTION_TOKEN_BUDGET - approx_token_count("\n".join(lines)), 0)
    retained_turn_count = 0

    for index, (user_messages, assistant_messages) in enumerate(reversed(turns)):
        if remaining_budget == 0:
            break

        turn_lines: list[str] = ["### Latest turn" if index == 0 else f"### Previous turn {index}"]
        if user_messages:
            turn_lines.append("User:")
            turn_lines.append("\n\n".join(user_messages))
        if assistant_messages:
            turn_lines.append("")
            turn_lines.append("Assistant:")
            turn_lines.append("\n\n".join(assistant_messages))

        turn_budget = min(REALTIME_TURN_TOKEN_BUDGET, remaining_budget)
        turn_text = truncate_realtime_text_to_token_budget("\n".join(turn_lines), turn_budget)
        turn_tokens = approx_token_count(turn_text)
        if turn_tokens == 0:
            continue
        lines.append("")
        lines.append(turn_text)
        remaining_budget = max(remaining_budget - turn_tokens, 0)
        retained_turn_count += 1

    return "\n".join(lines) if retained_turn_count > 0 else None


def truncate_realtime_text_to_token_budget(text: str, budget_tokens: int) -> str:
    truncation_budget = max(budget_tokens, 0)
    while True:
        candidate = truncate_text(str(text), TruncationPolicyConfig.tokens(truncation_budget))
        candidate_tokens = approx_token_count(candidate)
        if candidate_tokens <= budget_tokens:
            return candidate

        excess_tokens = max(candidate_tokens - budget_tokens, 0)
        next_budget = max(truncation_budget - max(excess_tokens, 1), 0)
        if next_budget == 0:
            candidate = truncate_text(str(text), TruncationPolicyConfig.tokens(0))
            if approx_token_count(candidate) <= budget_tokens:
                return candidate
            return ""
        truncation_budget = next_budget


def build_recent_work_section(cwd: Path | str, recent_threads: Iterable[object]) -> str | None:
    cwd_path = Path(cwd)
    current_group = _resolve_git_root(cwd_path) or cwd_path
    groups: dict[Path, list[object]] = {}
    for thread in recent_threads:
        thread_cwd = Path(_get_thread_field(thread, "cwd", ""))
        group = _resolve_git_root(thread_cwd) or thread_cwd
        groups.setdefault(group, []).append(thread)

    sorted_groups = sorted(
        groups.items(),
        key=lambda item: (
            item[0] != current_group,
            _reverse_sort_value(max((_get_thread_field(entry, "updated_at", "") for entry in item[1]), default="")),
            str(item[0]),
        ),
    )

    sections: list[str] = []
    for group, entries in sorted_groups[:MAX_RECENT_WORK_GROUPS]:
        entries = sorted(entries, key=lambda entry: _reverse_sort_value(_get_thread_field(entry, "updated_at", "")))
        section = _format_thread_group(current_group, group, entries)
        if section is not None:
            sections.append(section)
    return "\n\n".join(sections) if sections else None


def build_workspace_section_with_user_root(cwd: Path | str, user_root: Path | str | None = None) -> str | None:
    cwd_path = Path(cwd)
    git_root = _resolve_git_root(cwd_path)
    cwd_tree = render_tree(cwd_path)
    git_root_tree = render_tree(git_root) if git_root is not None and git_root != cwd_path else None
    user_root_path = Path(user_root) if user_root is not None else None
    user_root_tree = None
    if user_root_path is not None and user_root_path != cwd_path and user_root_path != git_root:
        user_root_tree = render_tree(user_root_path)

    if cwd_tree is None and git_root is None and user_root_tree is None:
        return None

    lines = [
        f"Current working directory: {cwd_path}",
        f"Working directory name: {_file_name_string(cwd_path)}",
    ]
    if git_root is not None:
        lines.append(f"Git root: {git_root}")
        lines.append(f"Git project: {_file_name_string(git_root)}")
    if user_root_path is not None:
        lines.append(f"User root: {user_root_path}")

    if cwd_tree is not None:
        lines.append("")
        lines.append("Working directory tree:")
        lines.extend(cwd_tree)
    if git_root_tree is not None:
        lines.append("")
        lines.append("Git root tree:")
        lines.extend(git_root_tree)
    if user_root_tree is not None:
        lines.append("")
        lines.append("User root tree:")
        lines.extend(user_root_tree)

    return "\n".join(lines)


def render_tree(root: Path | str) -> list[str] | None:
    root_path = Path(root)
    if not root_path.is_dir():
        return None
    lines: list[str] = []
    _collect_tree_lines(root_path, 0, lines)
    return lines or None


def format_section(title: str, body: str | None, budget_tokens: int) -> str | None:
    if body is None:
        return None
    body = body.strip()
    if not body:
        return None

    heading = f"## {title}\n"
    body_budget = max(budget_tokens - approx_token_count(heading), 0)
    if body_budget == 0:
        return None

    body = truncate_realtime_text_to_token_budget(body, body_budget)
    if not body:
        return None
    return f"{heading}{body}"


def format_startup_context_blob(body: str) -> str:
    return f"{STARTUP_CONTEXT_OPEN_TAG}\n{body}\n{STARTUP_CONTEXT_CLOSE_TAG}"


def _format_thread_group(current_group: Path, group: Path, entries: list[object]) -> str | None:
    if not entries:
        return None
    latest = entries[0]
    group_label = f"### Git repo: {group}" if (group / ".git").exists() else f"### Directory: {group}"
    lines = [
        group_label,
        f"Recent sessions: {len(entries)}",
        f"Latest activity: {_format_updated_at(_get_thread_field(latest, 'updated_at', ''))}",
    ]

    branch = _git_branch(latest)
    if branch:
        lines.append(f"Latest branch: {branch}")

    lines.append("")
    lines.append("User asks:")
    seen: set[str] = set()
    max_asks = MAX_CURRENT_CWD_ASKS if group == current_group else MAX_OTHER_CWD_ASKS

    for entry in entries:
        first_user_message = _get_thread_field(entry, "first_user_message", None)
        if not isinstance(first_user_message, str):
            continue
        ask = " ".join(first_user_message.split())
        entry_cwd = Path(_get_thread_field(entry, "cwd", ""))
        dedupe_key = f"{entry_cwd}:{ask}"
        if not ask or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        if len(ask) > MAX_ASK_CHARS:
            ask = ask[: max(MAX_ASK_CHARS - 3, 0)] + "..."
        lines.append(f"- {entry_cwd}: {ask}")
        if len(seen) == max_asks:
            break

    return "\n".join(lines) if len(lines) > 5 else None


def _collect_tree_lines(directory: Path, depth: int, lines: list[str]) -> None:
    if depth >= TREE_MAX_DEPTH:
        return
    entries = _read_sorted_entries(directory)
    total_entries = len(entries)
    for entry in entries[:DIR_ENTRY_LIMIT]:
        indent = "  " * depth
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{indent}- {_file_name_string(entry)}{suffix}")
        if entry.is_dir():
            _collect_tree_lines(entry, depth + 1, lines)
    if total_entries > DIR_ENTRY_LIMIT:
        lines.append(f"{'  ' * depth}- ... {total_entries - DIR_ENTRY_LIMIT} more entries")


def _read_sorted_entries(directory: Path) -> list[Path]:
    try:
        entries = [entry for entry in directory.iterdir() if not _is_noisy_name(entry.name)]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: (not entry.is_dir(), _file_name_string(entry)))


def _is_noisy_name(name: str) -> bool:
    return name.startswith(".") or name in NOISY_DIR_NAMES


def _resolve_git_root(cwd: Path) -> Path | None:
    current = cwd
    home = Path.home()
    while True:
        if current == home:
            return None
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _file_name_string(path: Path) -> str:
    return path.name or str(path)


def _get_thread_field(thread: object, name: str, default: object = None) -> object:
    if isinstance(thread, dict):
        return thread.get(name, default)
    return getattr(thread, name, default)


def _reverse_sort_value(value: object) -> tuple[int, object]:
    if isinstance(value, (int, float)):
        return (0, -value)
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        try:
            return (0, -timestamp())
        except (OverflowError, OSError, ValueError):
            pass
    return (1, str(value))


def _format_updated_at(value: object) -> str:
    formatter = getattr(value, "isoformat", None)
    if callable(formatter):
        return formatter()
    return str(value)


def _git_branch(thread: object) -> str | None:
    git_info = _get_thread_field(thread, "git_info", None)
    if git_info is None:
        return None
    branch = git_info.get("branch") if isinstance(git_info, dict) else getattr(git_info, "branch", None)
    return branch if isinstance(branch, str) and branch else None


def _content_items_to_text(content: Iterable[ContentItem | dict[str, object]]) -> str | None:
    parts: list[str] = []
    for item in content:
        parsed = item if isinstance(item, ContentItem) else ContentItem.from_mapping(item)
        if parsed.type in {"input_text", "output_text"} and parsed.text:
            parts.append(parsed.text)
    return "\n".join(parts) if parts else None


def _is_contextual_user_message_content(content: Iterable[ContentItem]) -> bool:
    return any(is_contextual_user_fragment(item) for item in content)


__all__ = [
    "CURRENT_THREAD_SECTION_TOKEN_BUDGET",
    "DIR_ENTRY_LIMIT",
    "MAX_ASK_CHARS",
    "MAX_CURRENT_CWD_ASKS",
    "MAX_OTHER_CWD_ASKS",
    "MAX_RECENT_WORK_GROUPS",
    "NOISY_DIR_NAMES",
    "NOTES_SECTION_TOKEN_BUDGET",
    "REALTIME_TURN_TOKEN_BUDGET",
    "RECENT_WORK_SECTION_TOKEN_BUDGET",
    "STARTUP_CONTEXT_CLOSE_TAG",
    "STARTUP_CONTEXT_HEADER",
    "STARTUP_CONTEXT_OPEN_TAG",
    "TREE_MAX_DEPTH",
    "WORKSPACE_SECTION_TOKEN_BUDGET",
    "build_current_thread_section",
    "build_recent_work_section",
    "build_realtime_startup_context",
    "build_workspace_section_with_user_root",
    "format_section",
    "format_startup_context_blob",
    "render_tree",
    "truncate_realtime_text_to_token_budget",
]
