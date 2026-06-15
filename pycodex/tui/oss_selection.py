"""Behavior port slice for Rust ``codex-tui::oss_selection``.

Rust renders a pre-TUI alternate-screen provider picker. Python ports the local
selection state machine, provider auto-selection, and semantic status probing;
concrete terminal raw-mode/ratatui rendering remains a runtime boundary.
"""

from __future__ import annotations

import asyncio
import http.client
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, List, Optional, Sequence, Tuple, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="oss_selection",
    source="codex/codex-rs/tui/src/oss_selection.rs",
    status="complete",
)

DEFAULT_LMSTUDIO_PORT = 1234
DEFAULT_OLLAMA_PORT = 11434
LMSTUDIO_OSS_PROVIDER_ID = "lmstudio"
OLLAMA_OSS_PROVIDER_ID = "ollama"


@dataclass(frozen=True)
class ProviderOption:
    name: str
    status: "ProviderStatus"


class ProviderStatus(str, Enum):
    RUNNING = "running"
    NOT_RUNNING = "not_running"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SelectOption:
    label: str
    description: str
    key: str
    provider_id: str


OSS_SELECT_OPTIONS = [
    SelectOption(
        label="LM Studio",
        description="Local LM Studio server (default port 1234)",
        key="l",
        provider_id=LMSTUDIO_OSS_PROVIDER_ID,
    ),
    SelectOption(
        label="Ollama",
        description="Local Ollama server (Responses API, default port 11434)",
        key="o",
        provider_id=OLLAMA_OSS_PROVIDER_ID,
    ),
]

MOVE_LEFT_KEYS = ("left", "ctrl+h")
MOVE_RIGHT_KEYS = ("right", "ctrl+l")


@dataclass
class OssSelectionWidget:
    select_options: List[SelectOption]
    provider_statuses: List[ProviderOption]
    selected_option: int = 0
    done: bool = False
    selection: Optional[str] = None

    @classmethod
    def new(
        cls,
        lmstudio_status: Union[ProviderStatus, str],
        ollama_status: Union[ProviderStatus, str],
    ) -> "OssSelectionWidget":
        ollama = _status(ollama_status)
        providers = [
            ProviderOption("LM Studio", _status(lmstudio_status)),
            ProviderOption("Ollama (Responses)", ollama),
            ProviderOption("Ollama (Chat)", ollama),
        ]
        return cls(select_options=list(OSS_SELECT_OPTIONS), provider_statuses=providers)

    def get_confirmation_prompt_height(self, width: int) -> int:
        return len(self.confirmation_prompt_lines())

    def confirmation_prompt_lines(self) -> List[str]:
        lines = [
            "? Select an open-source provider",
            "",
            "  Choose which local AI server to use for your session.",
            "",
        ]
        for provider in self.provider_statuses:
            symbol, _color = get_status_symbol_and_color(provider.status)
            lines.append(f"  {symbol} {provider.name} ")
        lines.append("")
        lines.append("  * Running  x Not Running")
        lines.append("")
        lines.append("  Press Enter to select - Ctrl+C to exit")
        return lines

    def handle_key_event(self, key: Any) -> Optional[str]:
        if _key_kind(key) != "press":
            return self.selection if self.done else None
        self.handle_select_key(key)
        return self.selection if self.done else None

    @staticmethod
    def normalize_keycode(code: Any) -> str:
        return _key_code(code).lower()

    def handle_select_key(self, key_event: Any) -> None:
        key = _key_spec(key_event)
        if key == "ctrl+c":
            self.send_decision("__CANCELLED__")
        elif key in MOVE_LEFT_KEYS:
            self.selected_option = (self.selected_option + len(self.select_options) - 1) % len(self.select_options)
        elif key in MOVE_RIGHT_KEYS:
            self.selected_option = (self.selected_option + 1) % len(self.select_options)
        elif key == "enter":
            self.send_decision(self.select_options[self.selected_option].provider_id)
        elif key == "esc":
            self.send_decision(LMSTUDIO_OSS_PROVIDER_ID)
        else:
            normalized = self.normalize_keycode(key)
            for option in self.select_options:
                if self.normalize_keycode(option.key) == normalized:
                    self.send_decision(option.provider_id)
                    break

    def send_decision(self, selection: str) -> None:
        self.selection = str(selection)
        self.done = True

    def is_complete(self) -> bool:
        return self.done

    def desired_height(self, width: int) -> int:
        return self.get_confirmation_prompt_height(width) + len(self.select_options)

    def render_semantic(self) -> List[str]:
        lines = self.confirmation_prompt_lines()
        lines.append("Select provider?")
        buttons = []
        for idx, option in enumerate(self.select_options):
            marker = ">" if idx == self.selected_option else " "
            buttons.append(f"{marker}{option.label}")
        lines.append(" | ".join(buttons))
        lines.append(self.select_options[self.selected_option].description)
        return lines


def render_ref(widget: OssSelectionWidget, *args: Any, **kwargs: Any) -> List[str]:
    return widget.render_semantic()


def get_status_symbol_and_color(status: Union[ProviderStatus, str]) -> Tuple[str, str]:
    value = _status(status)
    if value is ProviderStatus.RUNNING:
        return "*", "green"
    if value is ProviderStatus.NOT_RUNNING:
        return "x", "red"
    return "?", "yellow"


@dataclass(frozen=True)
class OssProviderSelection:
    provider: str
    manually_selected: bool


async def select_oss_provider(
    *,
    lmstudio_status: Optional[Union[ProviderStatus, str]] = None,
    ollama_status: Optional[Union[ProviderStatus, str]] = None,
    selection_runner: Optional[Callable[[OssSelectionWidget], Union[str, Awaitable[str]]]] = None,
    selection_events: Optional[Sequence[Any]] = None,
) -> OssProviderSelection:
    lm_status = _status(lmstudio_status) if lmstudio_status is not None else await check_lmstudio_status()
    ol_status = _status(ollama_status) if ollama_status is not None else await check_ollama_status()

    if lm_status is ProviderStatus.RUNNING and ol_status is ProviderStatus.NOT_RUNNING:
        return OssProviderSelection(LMSTUDIO_OSS_PROVIDER_ID, manually_selected=False)
    if lm_status is ProviderStatus.NOT_RUNNING and ol_status is ProviderStatus.RUNNING:
        return OssProviderSelection(OLLAMA_OSS_PROVIDER_ID, manually_selected=False)

    widget = OssSelectionWidget.new(lm_status, ol_status)
    if selection_runner is not None:
        selection = selection_runner(widget)
        if hasattr(selection, "__await__"):
            selection = await selection
    else:
        selection = run_oss_selection_widget(widget, selection_events)
    return OssProviderSelection(str(selection), manually_selected=True)


def run_oss_selection_widget(widget: OssSelectionWidget, events: Optional[Sequence[Any]] = None) -> str:
    """Semantic equivalent of the Rust raw-mode key loop.

    Rust redraws the widget, blocks on crossterm key events, and exits only
    after ``handle_key_event`` returns a selection.  Python keeps that module
    behavior deterministic with an injected event sequence; an exhausted event
    stream follows Rust's Escape default to LM Studio.
    """

    for event in events or ():
        selection = widget.handle_key_event(event)
        if selection is not None:
            return selection
    widget.handle_key_event("esc")
    return widget.selection or LMSTUDIO_OSS_PROVIDER_ID


async def check_lmstudio_status() -> ProviderStatus:
    try:
        return ProviderStatus.RUNNING if await check_port_status(DEFAULT_LMSTUDIO_PORT) else ProviderStatus.NOT_RUNNING
    except Exception:
        return ProviderStatus.UNKNOWN


async def check_ollama_status() -> ProviderStatus:
    try:
        return ProviderStatus.RUNNING if await check_port_status(DEFAULT_OLLAMA_PORT) else ProviderStatus.NOT_RUNNING
    except Exception:
        return ProviderStatus.UNKNOWN


async def check_port_status(port: int) -> bool:
    def probe() -> bool:
        conn = http.client.HTTPConnection("localhost", int(port), timeout=2)
        try:
            conn.request("GET", "/")
            response = conn.getresponse()
            return 200 <= int(response.status) < 300
        except OSError:
            return False
        finally:
            conn.close()

    return await asyncio.to_thread(probe)


def ctrl_h_l_move_provider_selection() -> tuple[int, int, int]:
    widget = OssSelectionWidget.new(ProviderStatus.UNKNOWN, ProviderStatus.UNKNOWN)
    initial = widget.selected_option
    widget.handle_key_event({"code": "l", "modifiers": {"CONTROL"}})
    after_right = widget.selected_option
    widget.handle_key_event({"code": "h", "modifiers": {"CONTROL"}})
    after_left = widget.selected_option
    return initial, after_right, after_left


def _status(value: Union[ProviderStatus, str]) -> ProviderStatus:
    if isinstance(value, ProviderStatus):
        return value
    raw = str(value).lower().replace("-", "_")
    if raw in {"running", "providerstatus.running"}:
        return ProviderStatus.RUNNING
    if raw in {"not_running", "notrunning", "not running", "providerstatus.not_running"}:
        return ProviderStatus.NOT_RUNNING
    if raw in {"unknown", "providerstatus.unknown"}:
        return ProviderStatus.UNKNOWN
    raise ValueError(f"unknown provider status: {value}")


def _key_kind(key_event: Any) -> str:
    return str(_get(key_event, "kind", "press")).lower()


def _key_spec(key_event: Any) -> str:
    code = _key_code(_get(key_event, "code", key_event))
    modifiers = _get(key_event, "modifiers", set())
    if isinstance(modifiers, str):
        mods = {modifiers.lower()}
    else:
        mods = {str(modifier).lower() for modifier in modifiers}
    if "control" in mods or "ctrl" in mods:
        return f"ctrl+{code}"
    return code


def _key_code(code: Any) -> str:
    if isinstance(code, dict):
        code = code.get("char") or code.get("key") or code.get("code")
    raw = str(code).lower()
    aliases = {
        "keycode::left": "left",
        "keycode::right": "right",
        "keycode::enter": "enter",
        "keycode::esc": "esc",
        "escape": "esc",
        " ": " ",
        "space": " ",
    }
    if raw.startswith("char(") and raw.endswith(")"):
        return raw[5:-1].strip("'\"").lower()
    return aliases.get(raw, raw)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


__all__ = [
    "DEFAULT_LMSTUDIO_PORT",
    "DEFAULT_OLLAMA_PORT",
    "LMSTUDIO_OSS_PROVIDER_ID",
    "MOVE_LEFT_KEYS",
    "MOVE_RIGHT_KEYS",
    "OLLAMA_OSS_PROVIDER_ID",
    "OSS_SELECT_OPTIONS",
    "OssProviderSelection",
    "OssSelectionWidget",
    "ProviderOption",
    "ProviderStatus",
    "RUST_MODULE",
    "SelectOption",
    "check_lmstudio_status",
    "check_ollama_status",
    "check_port_status",
    "ctrl_h_l_move_provider_selection",
    "get_status_symbol_and_color",
    "render_ref",
    "select_oss_provider",
]
