"""Behavior port for Rust ``codex-tui::resize_reflow_cap``.

Upstream source: ``codex/codex-rs/tui/src/resize_reflow_cap.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="resize_reflow_cap",
    source="codex/codex-rs/tui/src/resize_reflow_cap.rs",
)

DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS = 1_000
VSCODE_RESIZE_REFLOW_MAX_ROWS = 1_000
WINDOWS_TERMINAL_RESIZE_REFLOW_MAX_ROWS = 9_001
WEZTERM_RESIZE_REFLOW_MAX_ROWS = 3_500
ALACRITTY_RESIZE_REFLOW_MAX_ROWS = 10_000


class TerminalName(str, Enum):
    VSCODE = "vscode"
    WINDOWS_TERMINAL = "windows_terminal"
    WEZTERM = "wezterm"
    ALACRITTY = "alacritty"
    APPLE_TERMINAL = "apple_terminal"
    GHOSTTY = "ghostty"
    ITERM2 = "iterm2"
    WARP_TERMINAL = "warp_terminal"
    KITTY = "kitty"
    KONSOLE = "konsole"
    GNOME_TERMINAL = "gnome_terminal"
    VTE = "vte"
    DUMB = "dumb"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TerminalInfo:
    name: TerminalName = TerminalName.UNKNOWN
    term_program: str | None = None
    version: str | None = None
    term: str | None = None
    multiplexer: Any | None = None


class TerminalResizeReflowMaxRowsKind(str, Enum):
    AUTO = "auto"
    DISABLED = "disabled"
    LIMIT = "limit"


@dataclass(frozen=True)
class TerminalResizeReflowMaxRows:
    kind: TerminalResizeReflowMaxRowsKind
    limit: int | None = None

    @classmethod
    def auto(cls) -> "TerminalResizeReflowMaxRows":
        return cls(TerminalResizeReflowMaxRowsKind.AUTO)

    @classmethod
    def disabled(cls) -> "TerminalResizeReflowMaxRows":
        return cls(TerminalResizeReflowMaxRowsKind.DISABLED)

    @classmethod
    def limit_rows(cls, max_rows: int) -> "TerminalResizeReflowMaxRows":
        return cls(TerminalResizeReflowMaxRowsKind.LIMIT, int(max_rows))


@dataclass(frozen=True)
class TerminalResizeReflowConfig:
    max_rows: TerminalResizeReflowMaxRows = TerminalResizeReflowMaxRows.auto()


def _coerce_terminal_name(terminal_name: TerminalName | str) -> TerminalName:
    if isinstance(terminal_name, TerminalName):
        return terminal_name
    normalized = str(terminal_name)
    for name in TerminalName:
        if normalized in {name.value, name.name, name.name.lower()}:
            return name
    return TerminalName.UNKNOWN


def _coerce_max_rows(value: TerminalResizeReflowMaxRows | int | str | None) -> TerminalResizeReflowMaxRows:
    if isinstance(value, TerminalResizeReflowMaxRows):
        return value
    if value is None:
        return TerminalResizeReflowMaxRows.auto()
    if isinstance(value, int):
        if value == 0:
            return TerminalResizeReflowMaxRows.disabled()
        return TerminalResizeReflowMaxRows.limit_rows(value)
    lowered = str(value).lower()
    if lowered == "auto":
        return TerminalResizeReflowMaxRows.auto()
    if lowered in {"disabled", "none", "off", "0"}:
        return TerminalResizeReflowMaxRows.disabled()
    return TerminalResizeReflowMaxRows.limit_rows(int(value))


def resize_reflow_max_rows(
    config: TerminalResizeReflowConfig | TerminalResizeReflowMaxRows | int | str | None,
    *,
    terminal: TerminalInfo | None = None,
    running_in_vscode_terminal: bool = False,
) -> int | None:
    """Resolve the row cap for resize and initial replay.

    Rust reads terminal metadata from global probes. Python exposes those probes
    as injectable arguments so the module remains deterministic and testable.
    """

    if isinstance(config, TerminalResizeReflowConfig):
        effective_config = config
    else:
        effective_config = TerminalResizeReflowConfig(_coerce_max_rows(config))
    return resize_reflow_max_rows_for(
        effective_config,
        terminal or TerminalInfo(),
        running_in_vscode_terminal=running_in_vscode_terminal,
    )


def resize_reflow_max_rows_for(
    config: TerminalResizeReflowConfig,
    terminal: TerminalInfo,
    running_in_vscode_terminal: bool,
) -> int | None:
    max_rows = _coerce_max_rows(config.max_rows)
    if max_rows.kind is TerminalResizeReflowMaxRowsKind.AUTO:
        return auto_resize_reflow_max_rows(terminal.name, running_in_vscode_terminal)
    if max_rows.kind is TerminalResizeReflowMaxRowsKind.DISABLED:
        return None
    if max_rows.limit is None:
        raise ValueError("TerminalResizeReflowMaxRows.limit requires a max_rows value")
    return max_rows.limit


def auto_resize_reflow_max_rows(terminal_name: TerminalName | str, running_in_vscode_terminal: bool) -> int:
    if running_in_vscode_terminal:
        return VSCODE_RESIZE_REFLOW_MAX_ROWS

    name = _coerce_terminal_name(terminal_name)
    if name is TerminalName.VSCODE:
        return VSCODE_RESIZE_REFLOW_MAX_ROWS
    if name is TerminalName.WINDOWS_TERMINAL:
        return WINDOWS_TERMINAL_RESIZE_REFLOW_MAX_ROWS
    if name is TerminalName.WEZTERM:
        return WEZTERM_RESIZE_REFLOW_MAX_ROWS
    if name is TerminalName.ALACRITTY:
        return ALACRITTY_RESIZE_REFLOW_MAX_ROWS
    return DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS


def test_terminal(name: TerminalName | str) -> TerminalInfo:
    return TerminalInfo(name=_coerce_terminal_name(name))


def auto_resize_reflow_max_rows_uses_terminal_defaults() -> None:
    assert auto_resize_reflow_max_rows(TerminalName.VSCODE, False) == VSCODE_RESIZE_REFLOW_MAX_ROWS
    assert auto_resize_reflow_max_rows(TerminalName.WINDOWS_TERMINAL, False) == WINDOWS_TERMINAL_RESIZE_REFLOW_MAX_ROWS
    assert auto_resize_reflow_max_rows(TerminalName.WEZTERM, False) == WEZTERM_RESIZE_REFLOW_MAX_ROWS
    assert auto_resize_reflow_max_rows(TerminalName.ALACRITTY, False) == ALACRITTY_RESIZE_REFLOW_MAX_ROWS
    assert auto_resize_reflow_max_rows(TerminalName.GHOSTTY, False) == DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS
    assert auto_resize_reflow_max_rows(TerminalName.UNKNOWN, False) == DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS


def auto_resize_reflow_max_rows_prefers_vscode_probe() -> None:
    assert auto_resize_reflow_max_rows(TerminalName.WINDOWS_TERMINAL, True) == VSCODE_RESIZE_REFLOW_MAX_ROWS


def configured_resize_reflow_max_rows_overrides_auto_detection() -> None:
    config = TerminalResizeReflowConfig(TerminalResizeReflowMaxRows.limit_rows(42))
    assert resize_reflow_max_rows_for(config, test_terminal(TerminalName.VSCODE), False) == 42


def disabled_resize_reflow_max_rows_keeps_all_rows() -> None:
    config = TerminalResizeReflowConfig(TerminalResizeReflowMaxRows.disabled())
    assert resize_reflow_max_rows_for(config, test_terminal(TerminalName.VSCODE), False) is None


def unknown_terminal_uses_fallback_even_under_multiplexer() -> None:
    terminal = TerminalInfo(name=TerminalName.UNKNOWN, term="xterm-256color", multiplexer={"kind": "tmux"})
    assert (
        resize_reflow_max_rows_for(TerminalResizeReflowConfig(), terminal, False)
        == DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS
    )


__all__ = [
    "ALACRITTY_RESIZE_REFLOW_MAX_ROWS",
    "DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS",
    "RUST_MODULE",
    "TerminalInfo",
    "TerminalName",
    "TerminalResizeReflowConfig",
    "TerminalResizeReflowMaxRows",
    "TerminalResizeReflowMaxRowsKind",
    "VSCODE_RESIZE_REFLOW_MAX_ROWS",
    "WEZTERM_RESIZE_REFLOW_MAX_ROWS",
    "WINDOWS_TERMINAL_RESIZE_REFLOW_MAX_ROWS",
    "auto_resize_reflow_max_rows",
    "auto_resize_reflow_max_rows_prefers_vscode_probe",
    "auto_resize_reflow_max_rows_uses_terminal_defaults",
    "configured_resize_reflow_max_rows_overrides_auto_detection",
    "disabled_resize_reflow_max_rows_keeps_all_rows",
    "resize_reflow_max_rows",
    "resize_reflow_max_rows_for",
    "test_terminal",
    "unknown_terminal_uses_fallback_even_under_multiplexer",
]
