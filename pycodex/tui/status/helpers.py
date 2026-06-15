"""Semantic port of codex-rs/tui/src/status/helpers.rs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..exec_command import relativize_to_home
from ..text_formatting import center_truncate_path


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="status::helpers",
    source="codex/codex-rs/tui/src/status/helpers.rs",
    status="complete",
)

_TEAM_LIKE_PLANS = {"Team", "SelfServeBusinessUsageBased"}
_BUSINESS_LIKE_PLANS = {"Business", "EnterpriseCbpUsageBased", "Enterprise"}


def normalize_agents_display_path(path: str | Path) -> str:
    return Path(path).as_posix()


def compose_model_display(model_name: str, entries: Iterable[tuple[str, str]]) -> tuple[str, list[str]]:
    entries_list = list(entries)
    details: list[str] = []
    effort = next((value for key, value in entries_list if key == "reasoning effort"), None)
    if effort is not None:
        details.append(f"reasoning {str(effort).lower()}")
    summary = next((value for key, value in entries_list if key == "reasoning summaries"), None)
    if summary is not None:
        trimmed = str(summary).strip()
        if trimmed.lower() in {"none", "off"}:
            details.append("summaries off")
        elif trimmed:
            details.append(f"summaries {trimmed.lower()}")
    return str(model_name), details


def compose_agents_summary(config: Any, paths: Iterable[str | Path]) -> str:
    cwd = Path(_get(config, "cwd", "."))
    rels: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        file_name = path.name or "<unknown>"
        parent = path.parent if path.parent != Path("") else None
        if parent is None:
            display = normalize_agents_display_path(path)
        elif parent == cwd:
            display = file_name
        else:
            display = _relative_agent_path(path, cwd, file_name)
        rels.append(display)
    return "<none>" if not rels else ", ".join(rels)


def compose_account_display(account_display: Any | None) -> Any | None:
    return account_display


def plan_type_display_name(plan_type: Any) -> str:
    name = _variant_name(plan_type)
    if name in _TEAM_LIKE_PLANS:
        return "Business"
    if name in _BUSINESS_LIKE_PLANS:
        return "Enterprise"
    if name == "ProLite":
        return "Pro Lite"
    return title_case(name)


def format_tokens_compact(value: int) -> str:
    value = max(int(value), 0)
    if value == 0:
        return "0"
    if value < 1_000:
        return str(value)
    scaled, suffix = _scaled_token_value(value)
    decimals = 2 if scaled < 10 else 1 if scaled < 100 else 0
    formatted = f"{scaled:.{decimals}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return f"{formatted}{suffix}"


def format_directory_display(directory: str | Path, max_width: int | None = None) -> str:
    path = Path(directory)
    home = Path.home()
    try:
        rel_to_home = path.relative_to(home)
    except ValueError:
        rel_to_home = None
    if rel_to_home is not None:
        formatted = "~" if str(rel_to_home) in {"", "."} else f"~/{rel_to_home.as_posix()}"
    else:
        rel = relativize_to_home(path)
        if rel is not None:
            formatted = "~" if str(rel) in {"", "."} else f"~/{Path(rel).as_posix()}"
        else:
            formatted = path.as_posix()
    if max_width is not None:
        if max_width == 0:
            return ""
        if len(formatted) > max_width:
            return center_truncate_path(formatted, max_width)
    return formatted


def format_reset_timestamp(dt: datetime, captured_at: datetime) -> str:
    time = dt.strftime("%H:%M")
    if dt.date() == captured_at.date():
        return time
    return f"{time} on {dt.day} {dt.strftime('%b')}"


def title_case(s: str) -> str:
    if not s:
        return ""
    return s[0].upper() + s[1:].lower()


def _scaled_token_value(value: int) -> tuple[float, str]:
    if value >= 1_000_000_000_000:
        return value / 1_000_000_000_000.0, "T"
    if value >= 1_000_000_000:
        return value / 1_000_000_000.0, "B"
    if value >= 1_000_000:
        return value / 1_000_000.0, "M"
    return value / 1_000.0, "K"


def _relative_agent_path(path: Path, cwd: Path, file_name: str) -> str:
    cur = cwd
    ups = 0
    while cur.parent != cur:
        if cur == path.parent:
            return f"{'../' * ups}{file_name}"
        cur = cur.parent
        ups += 1
    try:
        return normalize_agents_display_path(path.relative_to(cwd))
    except ValueError:
        return format_directory_display(path, None)


def _variant_name(value: Any) -> str:
    if isinstance(value, str):
        return value.split(".")[-1]
    enum_value = getattr(value, "name", None)
    if enum_value:
        return str(enum_value)
    raw_value = getattr(value, "value", None)
    if raw_value:
        return str(raw_value).split(".")[-1]
    return str(value).split(".")[-1]


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


__all__ = [
    "RUST_MODULE",
    "compose_account_display",
    "compose_agents_summary",
    "compose_model_display",
    "format_directory_display",
    "format_reset_timestamp",
    "format_tokens_compact",
    "normalize_agents_display_path",
    "plan_type_display_name",
    "title_case",
]
