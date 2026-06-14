"""Startup hook-review prompt semantics for Rust ``codex-tui::startup_hooks_review``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="startup_hooks_review",
    source="codex/codex-rs/tui/src/startup_hooks_review.rs",
)


class StartupHooksReviewOutcome(Enum):
    CONTINUE = "Continue"
    OPEN_HOOKS_BROWSER = "OpenHooksBrowser"


@dataclass(frozen=True)
class StartupHooksReviewResult:
    outcome: StartupHooksReviewOutcome
    entry: Any = None


class StartupHooksReviewSelection(Enum):
    REVIEW_HOOKS = "ReviewHooks"
    TRUST_ALL_AND_CONTINUE = "TrustAllAndContinue"
    CONTINUE_WITHOUT_TRUSTING = "ContinueWithoutTrusting"


@dataclass(frozen=True)
class SelectionItem:
    name: str
    dismiss_on_select: bool = True
    is_disabled: bool = False


@dataclass(frozen=True)
class SelectionViewParams:
    items: list[SelectionItem]
    header: list[str]
    footer_hint: str | None = None


@dataclass
class ListSelectionView:
    params: SelectionViewParams
    selected_index: int | None = None
    complete: bool = False

    def is_complete(self) -> bool:
        return self.complete

    def take_last_selected_index(self) -> int | None:
        index = self.selected_index
        self.selected_index = None
        self.complete = False
        return index

    def select(self, index: int | None) -> None:
        self.selected_index = index
        self.complete = True

    def desired_height(self, _width: int) -> int:
        return len(self.params.header) + len(self.params.items) + (1 if self.params.footer_hint else 0)

    def render_lines(self) -> list[str]:
        rows = list(self.params.header)
        rows.extend(item.name for item in self.params.items)
        if self.params.footer_hint is not None:
            rows.append(self.params.footer_hint)
        return rows


async def maybe_run_startup_hooks_review(
    app_server: Any,
    tui: Any,
    config: Any,
    bypass_hook_trust: bool,
    *,
    fetch_hooks_list_fn: Any = None,
    hooks_list_entry_for_cwd_fn: Any = None,
) -> StartupHooksReviewResult:
    cwd = Path(_field(config, "cwd"))
    if fetch_hooks_list_fn is None or hooks_list_entry_for_cwd_fn is None:
        return StartupHooksReviewResult(StartupHooksReviewOutcome.CONTINUE)
    try:
        response = await _maybe_await(fetch_hooks_list_fn(_request_handle(app_server), cwd))
    except Exception:
        return StartupHooksReviewResult(StartupHooksReviewOutcome.CONTINUE)
    entry_value = hooks_list_entry_for_cwd_fn(response, cwd)
    if not review_is_needed(bypass_hook_trust, entry_value):
        return StartupHooksReviewResult(StartupHooksReviewOutcome.CONTINUE)
    return await run_startup_hooks_review_app(app_server, tui, config, entry_value)


async def run_startup_hooks_review_app(
    app_server: Any,
    tui: Any,
    config: Any,
    entry_value: Any,
    *,
    write_hook_trusts_fn: Any = None,
) -> StartupHooksReviewResult:
    keymap = _field(config, "tui_keymap", None)
    view = selection_view(entry_value, None, False, None, keymap)
    draw_view(tui, view)
    events = tui.event_stream()
    async for event in events:
        kind = _field(event, "kind")
        if kind in {"Draw", "Resize"}:
            draw_view(tui, view)
            continue
        if kind != "Key":
            continue
        key = _field(event, "key")
        if _field(key, "kind", "Press") not in {"Press", "Repeat"}:
            continue
        index = _key_to_index(_field(key, "code"))
        if index is not None:
            view.select(index)
        choice = selected_choice(view)
        if choice is None:
            draw_view(tui, view)
            continue
        if choice is StartupHooksReviewSelection.REVIEW_HOOKS:
            return StartupHooksReviewResult(StartupHooksReviewOutcome.OPEN_HOOKS_BROWSER, entry_value)
        if choice is StartupHooksReviewSelection.CONTINUE_WITHOUT_TRUSTING:
            return StartupHooksReviewResult(StartupHooksReviewOutcome.CONTINUE)
        if write_hook_trusts_fn is None:
            return StartupHooksReviewResult(StartupHooksReviewOutcome.CONTINUE)
        updates = [
            {"key": _field(hook_value, "key"), "current_hash": _field(hook_value, "current_hash")}
            for hook_value in _hooks(entry_value)
            if hook_needs_review(hook_value)
        ]
        try:
            await _maybe_await(write_hook_trusts_fn(_request_handle(app_server), updates))
            return StartupHooksReviewResult(StartupHooksReviewOutcome.CONTINUE)
        except Exception as exc:
            view = selection_view(entry_value, f"Failed to trust hooks: {exc}", False, None, keymap)
            draw_view(tui, view)
    return StartupHooksReviewResult(StartupHooksReviewOutcome.CONTINUE)


def selected_choice(view: ListSelectionView) -> StartupHooksReviewSelection | None:
    if not view.is_complete():
        return None
    index = view.take_last_selected_index()
    if index == 0:
        return StartupHooksReviewSelection.REVIEW_HOOKS
    if index == 1:
        return StartupHooksReviewSelection.TRUST_ALL_AND_CONTINUE
    if index == 2 or index is None:
        return StartupHooksReviewSelection.CONTINUE_WITHOUT_TRUSTING
    return None


def selection_view(
    entry_value: Any,
    trust_all_error: str | None,
    trusting_all: bool,
    _app_event_tx: Any,
    keymap: Any,
) -> ListSelectionView:
    return ListSelectionView(selection_view_params(entry_value, trust_all_error, trusting_all, keymap))


def selection_view_params(
    entry_value: Any,
    trust_all_error: str | None,
    trusting_all: bool,
    _keymap: Any,
) -> SelectionViewParams:
    count = review_needed_count(entry_value)
    count_line = "1 hook is new or changed." if count == 1 else f"{count} hooks are new or changed."
    header = [
        "Hooks need review",
        count_line,
        "Hooks can run outside the sandbox after you trust them.",
    ]
    if trust_all_error is not None:
        header.append(trust_all_error)
    elif trusting_all:
        header.append("Trusting hooks...")
    return SelectionViewParams(
        footer_hint="Use arrows to move, Enter to select",
        items=[
            selection_item("Review hooks", trusting_all),
            selection_item("Trust all and continue", trusting_all),
            selection_item("Continue without trusting (hooks won't run)", trusting_all),
        ],
        header=header,
    )


def review_needed_count(entry_value: Any) -> int:
    return sum(1 for hook_value in _hooks(entry_value) if hook_needs_review(hook_value))


def review_is_needed(bypass_hook_trust: bool, entry_value: Any) -> bool:
    return (not bypass_hook_trust) and review_needed_count(entry_value) > 0


def hook_needs_review(hook_value: Any) -> bool:
    status = _field(hook_value, "trust_status")
    if isinstance(status, Enum):
        status = status.name if status.name else status.value
    status_text = str(status)
    return status_text.endswith("Untrusted") or status_text.endswith("Modified") or status_text in {"Untrusted", "Modified"}


def selection_item(name: str, is_disabled: bool) -> SelectionItem:
    return SelectionItem(name=name, dismiss_on_select=True, is_disabled=is_disabled)


def draw_view(tui: Any, view: ListSelectionView) -> None:
    draw = getattr(tui, "draw", None)
    if callable(draw):
        draw(view)


@dataclass(frozen=True)
class StandaloneSelectionView:
    view: ListSelectionView

    def render_ref(self, _area: Any = None, _buf: Any = None) -> list[str]:
        return self.view.render_lines()


def render_ref(view: StandaloneSelectionView, area: Any = None, buf: Any = None) -> list[str]:
    return view.render_ref(area, buf)


def hook(key: str, trust_status: Any) -> dict[str, Any]:
    return {"key": key, "current_hash": f"sha256:{key}", "trust_status": trust_status}


def entry() -> dict[str, Any]:
    return {"cwd": Path("/tmp"), "hooks": [hook("path:new", "Untrusted"), hook("path:changed", "Modified")]}


def render_lines(view: ListSelectionView, _width: int = 80) -> str:
    return "\n".join(view.render_lines())


def _hooks(entry_value: Any) -> list[Any]:
    return list(_field(entry_value, "hooks", []))


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _request_handle(app_server: Any) -> Any:
    handle = getattr(app_server, "request_handle", None)
    return handle() if callable(handle) else handle


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _key_to_index(code: Any) -> int | None:
    mapping = {"1": 0, "2": 1, "3": 2, 0: 0, 1: 1, 2: 2}
    return mapping.get(code)


__all__ = [
    "ListSelectionView",
    "RUST_MODULE",
    "SelectionItem",
    "SelectionViewParams",
    "StandaloneSelectionView",
    "StartupHooksReviewOutcome",
    "StartupHooksReviewResult",
    "StartupHooksReviewSelection",
    "draw_view",
    "entry",
    "hook",
    "hook_needs_review",
    "maybe_run_startup_hooks_review",
    "render_lines",
    "render_ref",
    "review_is_needed",
    "review_needed_count",
    "run_startup_hooks_review_app",
    "selected_choice",
    "selection_item",
    "selection_view",
    "selection_view_params",
]
