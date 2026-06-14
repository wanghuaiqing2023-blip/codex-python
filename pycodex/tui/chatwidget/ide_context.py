"""Chat-widget IDE context command helpers for ``codex-tui::chatwidget::ide_context``.

The Rust module owns ChatWidget wiring for ``/ide`` and prompt injection.  This
Python port keeps the local state machine and command handling semantics while
injecting the lower-level IDE context fetch/apply functions as dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::ide_context",
    source="codex/codex-rs/tui/src/chatwidget/ide_context.rs",
)


@dataclass
class IdeContextState:
    enabled: bool = False
    prompt_fetch_warned: bool = False

    def is_enabled(self) -> bool:
        return self.enabled

    def enable(self) -> None:
        self.enabled = True
        self.prompt_fetch_warned = False

    def disable(self) -> None:
        self.enabled = False
        self.prompt_fetch_warned = False

    def mark_available(self) -> None:
        self.prompt_fetch_warned = False


@dataclass
class IdeContextDeps:
    fetch_ide_context: Callable[[Path], Any]
    apply_ide_context_to_user_input: Callable[[Any, list[Any]], None]
    has_prompt_context: Callable[[Any], bool]


@dataclass
class IdeContextWidgetState:
    cwd: Path
    deps: IdeContextDeps
    ide_context: IdeContextState = field(default_factory=IdeContextState)
    info_messages: list[tuple[str, str | None]] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    indicator_active: bool | None = None

    def handle_ide_command(self) -> None:
        if self.ide_context.is_enabled():
            self.ide_context.disable()
            self.sync_ide_context_status_indicator()
            self.add_info_message("IDE context is off.", None)
        else:
            self.ide_context.enable()
            self.add_ide_context_status_message()

    def handle_ide_command_args(self, args: str) -> None:
        arg = str(args).lower()
        if arg == "":
            self.handle_ide_command()
        elif arg == "on":
            self.ide_context.enable()
            self.add_ide_context_status_message()
        elif arg == "off":
            self.ide_context.disable()
            self.sync_ide_context_status_indicator()
            self.add_info_message("IDE context is off.", None)
        elif arg == "status":
            self.add_ide_context_status_message()
        else:
            self.add_error_message("Usage: /ide [on|off|status]")

    def maybe_apply_ide_context(self, items: list[Any]) -> None:
        if not self.ide_context.is_enabled():
            return
        try:
            context = self.deps.fetch_ide_context(self.cwd)
        except Exception as err:
            self.sync_ide_context_status_indicator()
            if not self.ide_context.prompt_fetch_warned:
                self.ide_context.prompt_fetch_warned = True
                self.add_info_message(
                    "IDE context was skipped for this message.",
                    _prompt_skip_hint(err),
                )
            return

        self.ide_context.mark_available()
        self.sync_ide_context_status_indicator()
        self.deps.apply_ide_context_to_user_input(context, items)

    def add_ide_context_status_message(self) -> None:
        if not self.ide_context.is_enabled():
            self.sync_ide_context_status_indicator()
            self.add_info_message("IDE context is off.", None)
            return
        try:
            context = self.deps.fetch_ide_context(self.cwd)
        except Exception as err:
            self.ide_context.disable()
            self.sync_ide_context_status_indicator()
            self.add_info_message("IDE context could not be enabled.", _user_facing_hint(err))
            return

        self.ide_context.mark_available()
        self.sync_ide_context_status_indicator()
        if self.deps.has_prompt_context(context):
            self.add_info_message(
                "IDE context is on.",
                "Future messages will include your current IDE selection and open tabs.",
            )
        else:
            self.add_info_message("IDE context is on.", "Connected to your IDE.")

    def sync_ide_context_status_indicator(self) -> None:
        self.indicator_active = self.ide_context.is_enabled()

    def add_info_message(self, message: str, hint: str | None = None) -> None:
        self.info_messages.append((message, hint))

    def add_error_message(self, message: str) -> None:
        self.error_messages.append(message)


def handle_ide_command(widget: Any) -> None:
    _adapter(widget).handle_ide_command()


def handle_ide_command_args(widget: Any, args: str) -> None:
    _adapter(widget).handle_ide_command_args(args)


def maybe_apply_ide_context(widget: Any, items: list[Any]) -> None:
    _adapter(widget).maybe_apply_ide_context(items)


def sync_ide_context_status_indicator(widget: Any) -> None:
    _adapter(widget).sync_ide_context_status_indicator()


def _adapter(widget: Any) -> IdeContextWidgetState:
    if isinstance(widget, IdeContextWidgetState):
        return widget
    raise TypeError("widget-like IDE context helpers require IdeContextWidgetState in this port slice")


def _prompt_skip_hint(err: Exception) -> str:
    method = getattr(err, "prompt_skip_hint", None)
    if callable(method):
        return str(method())
    return str(err)


def _user_facing_hint(err: Exception) -> str:
    method = getattr(err, "user_facing_hint", None)
    if callable(method):
        return str(method())
    return str(err)


__all__ = [
    "IdeContextDeps",
    "IdeContextState",
    "IdeContextWidgetState",
    "RUST_MODULE",
    "handle_ide_command",
    "handle_ide_command_args",
    "maybe_apply_ide_context",
    "sync_ide_context_status_indicator",
]
