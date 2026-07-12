"""App-link/action-required bottom-pane view.

Python port slice for Rust ``codex-tui::bottom_pane::app_link_view``.

The Rust module renders ratatui buffers and emits rich ``AppEvent`` variants.
Python keeps the same module-level behavior as semantic data: URL validation,
view parameters, action labels, state transitions, visible text lines, and
event dictionaries that preserve the user-visible/runtime decision contract.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .._porting import RustTuiModule
from ..app_event_sender import AppEventSender
from .bottom_pane_view import BottomPaneViewDefaults
from .selection_popup_common import TerminalPopupLine

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::app_link_view",
    source="codex/codex-rs/tui/src/bottom_pane/app_link_view.rs",
    status="complete",
)

MCP_CODEX_APPS_SERVER_NAME = "codex_apps"
MCP_TOOL_CODEX_APPS_META_KEY = "_codex_apps"
CONNECTOR_AUTH_FAILURE_META_KEY = "connector_auth_failure"
CONNECTOR_AUTH_FAILURE_IS_AUTH_FAILURE_KEY = "is_auth_failure"
CONNECTOR_AUTH_FAILURE_CONNECTOR_ID_KEY = "connector_id"
CONNECTOR_AUTH_FAILURE_CONNECTOR_NAME_KEY = "connector_name"


class AppLinkScreen(Enum):
    LINK = "Link"
    INSTALL_CONFIRMATION = "InstallConfirmation"


class AppLinkSuggestionType(Enum):
    INSTALL = "Install"
    ENABLE = "Enable"
    AUTH = "Auth"
    EXTERNAL_ACTION = "ExternalAction"


@dataclass(frozen=True)
class AppLinkElicitationTarget:
    thread_id: Any
    server_name: str
    request_id: Any


@dataclass(frozen=True)
class AppLinkViewParams:
    app_id: str
    title: str
    description: Optional[str]
    instructions: str
    url: str
    is_installed: bool
    is_enabled: bool
    suggest_reason: Optional[str] = None
    suggestion_type: Optional[AppLinkSuggestionType] = None
    elicitation_target: Optional[AppLinkElicitationTarget] = None

    @classmethod
    def from_url_app_server_request(
        cls,
        thread_id: Any,
        server_name: str,
        request_id: Any,
        request: Any,
    ) -> Optional["AppLinkViewParams"]:
        parts = _url_request_parts(request)
        if parts is None:
            return None
        meta, message, url, elicitation_id = parts
        parsed = validate_external_url(
            url,
            require_chatgpt_host=server_name == MCP_CODEX_APPS_SERVER_NAME,
        )
        if parsed is None:
            return None
        if server_name == MCP_CODEX_APPS_SERVER_NAME:
            return cls.from_codex_apps_auth_url_parts(
                thread_id,
                server_name,
                request_id,
                meta,
                message,
                parsed,
                elicitation_id,
            )
        return cls.from_generic_url_parts(
            thread_id,
            server_name,
            request_id,
            message,
            parsed,
            elicitation_id,
        )

    @classmethod
    def from_codex_apps_auth_url_parts(
        cls,
        thread_id: Any,
        server_name: str,
        request_id: Any,
        meta: Any,
        message: str,
        url: str,
        elicitation_id: str,
    ) -> Optional["AppLinkViewParams"]:
        auth_failure = _nested_dict(
            meta,
            MCP_TOOL_CODEX_APPS_META_KEY,
            CONNECTOR_AUTH_FAILURE_META_KEY,
        )
        if not isinstance(auth_failure, dict):
            return None
        if auth_failure.get(CONNECTOR_AUTH_FAILURE_IS_AUTH_FAILURE_KEY) is not True:
            return None

        app_id = _non_empty_str(auth_failure.get(CONNECTOR_AUTH_FAILURE_CONNECTOR_ID_KEY)) or elicitation_id
        title = _non_empty_str(auth_failure.get(CONNECTOR_AUTH_FAILURE_CONNECTOR_NAME_KEY)) or app_id
        return cls(
            app_id=app_id,
            title=title,
            description=None,
            instructions="Sign in to this app in your browser, then return here.",
            url=url,
            is_installed=True,
            is_enabled=True,
            suggest_reason=message,
            suggestion_type=AppLinkSuggestionType.AUTH,
            elicitation_target=AppLinkElicitationTarget(thread_id, server_name, request_id),
        )

    @classmethod
    def from_generic_url_parts(
        cls,
        thread_id: Any,
        server_name: str,
        request_id: Any,
        message: str,
        url: str,
        elicitation_id: str,
    ) -> "AppLinkViewParams":
        return cls(
            app_id=elicitation_id,
            title="Action required",
            description=f"Server: {server_name}",
            instructions="Complete the requested action in your browser, then return here.",
            url=url,
            is_installed=True,
            is_enabled=True,
            suggest_reason=message,
            suggestion_type=AppLinkSuggestionType.EXTERNAL_ACTION,
            elicitation_target=AppLinkElicitationTarget(thread_id, server_name, request_id),
        )


def validate_external_url(url: str, require_chatgpt_host: bool = False) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    if require_chatgpt_host and not is_allowed_chatgpt_auth_host(parsed.hostname):
        return None
    return parsed.geturl()


def is_allowed_chatgpt_auth_host(host: str) -> bool:
    host = host.lower()
    return (
        host == "chatgpt.com"
        or host == "chatgpt-staging.com"
        or host.endswith(".chatgpt.com")
        or host.endswith(".chatgpt-staging.com")
    )


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class AppLinkView(BottomPaneViewDefaults):
    app_id: str
    title: str
    description: Optional[str]
    instructions: str
    url: str
    is_installed: bool
    is_enabled: bool
    suggest_reason: Optional[str]
    suggestion_type: Optional[AppLinkSuggestionType]
    elicitation_target: Optional[AppLinkElicitationTarget]
    app_event_tx: Any = None
    screen: AppLinkScreen = AppLinkScreen.LINK
    selected_action: int = 0
    complete: bool = False
    list_keymap: Any = None

    @classmethod
    def new(cls, params: AppLinkViewParams, app_event_tx: Any = None) -> "AppLinkView":
        return cls.new_with_keymap(params, app_event_tx, None)

    @classmethod
    def new_with_keymap(
        cls,
        params: AppLinkViewParams,
        app_event_tx: Any = None,
        list_keymap: Any = None,
    ) -> "AppLinkView":
        return cls(
            app_id=params.app_id,
            title=params.title,
            description=params.description,
            instructions=params.instructions,
            url=params.url,
            is_installed=params.is_installed,
            is_enabled=params.is_enabled,
            suggest_reason=params.suggest_reason,
            suggestion_type=params.suggestion_type,
            elicitation_target=params.elicitation_target,
            app_event_tx=app_event_tx,
            list_keymap=list_keymap,
        )

    def action_labels(self) -> List[str]:
        if self.is_auth_suggestion():
            if self.screen is AppLinkScreen.LINK:
                return ["Open sign-in URL", "Back"]
            return ["I already signed in", "Back"]
        if self.is_external_action_suggestion():
            if self.screen is AppLinkScreen.LINK:
                return ["Open link", "Back"]
            return ["I finished", "Back"]
        if self.screen is AppLinkScreen.LINK:
            if self.is_installed:
                return [
                    "Manage on ChatGPT",
                    "Disable app" if self.is_enabled else "Enable app",
                    "Back",
                ]
            return ["Install on ChatGPT", "Back"]
        return ["I already Installed it", "Back"]

    def move_selection_prev(self) -> None:
        self.selected_action = max(0, self.selected_action - 1)

    def move_selection_next(self) -> None:
        self.selected_action = min(self.selected_action + 1, len(self.action_labels()) - 1)

    def is_tool_suggestion(self) -> bool:
        return self.elicitation_target is not None

    def is_auth_suggestion(self) -> bool:
        return self.is_tool_suggestion() and self.suggestion_type is AppLinkSuggestionType.AUTH

    def is_external_action_suggestion(self) -> bool:
        return self.is_tool_suggestion() and self.suggestion_type is AppLinkSuggestionType.EXTERNAL_ACTION

    def is_browser_action_suggestion(self) -> bool:
        return self.is_auth_suggestion() or self.is_external_action_suggestion()

    def resolve_elicitation(self, decision: str) -> None:
        if self.elicitation_target is None:
            return
        _send(
            self.app_event_tx,
            {
                "type": "ResolveElicitation",
                "thread_id": self.elicitation_target.thread_id,
                "server_name": self.elicitation_target.server_name,
                "request_id": self.elicitation_target.request_id,
                "decision": decision,
                "content": None,
                "meta": None,
            },
        )

    def decline_tool_suggestion(self) -> None:
        self.resolve_elicitation("Decline")
        self.complete = True

    def open_external_url(self) -> None:
        _send(self.app_event_tx, {"type": "OpenUrlInBrowser", "url": self.url})
        if not self.is_installed or self.is_browser_action_suggestion():
            self.screen = AppLinkScreen.INSTALL_CONFIRMATION
            self.selected_action = 0

    def complete_external_flow_and_close(self) -> None:
        should_refresh = (
            self.elicitation_target is None
            or self.elicitation_target.server_name == MCP_CODEX_APPS_SERVER_NAME
        )
        if should_refresh:
            _send(self.app_event_tx, {"type": "RefreshConnectors", "force_refetch": True})
        if self.is_tool_suggestion():
            self.resolve_elicitation("Accept")
        self.complete = True

    def back_to_link_screen(self) -> None:
        self.screen = AppLinkScreen.LINK
        self.selected_action = 0

    def toggle_enabled(self) -> None:
        self.is_enabled = not self.is_enabled
        _send(
            self.app_event_tx,
            {"type": "SetAppEnabled", "id": self.app_id, "enabled": self.is_enabled},
        )
        if self.is_tool_suggestion():
            self.resolve_elicitation("Accept")
            self.complete = True

    def activate_selected_action(self) -> None:
        if self.is_tool_suggestion():
            if self.suggestion_type is AppLinkSuggestionType.ENABLE:
                if self.screen is AppLinkScreen.LINK:
                    if self.selected_action == 0:
                        self.open_external_url()
                    elif self.selected_action == 1 and self.is_installed:
                        self.toggle_enabled()
                    else:
                        self.decline_tool_suggestion()
                elif self.selected_action == 0:
                    self.complete_external_flow_and_close()
                else:
                    self.decline_tool_suggestion()
                return

            if self.screen is AppLinkScreen.LINK:
                if self.selected_action == 0:
                    self.open_external_url()
                else:
                    self.decline_tool_suggestion()
            elif self.selected_action == 0:
                self.complete_external_flow_and_close()
            else:
                self.decline_tool_suggestion()
            return

        if self.screen is AppLinkScreen.LINK:
            if self.selected_action == 0:
                self.open_external_url()
            elif self.selected_action == 1 and self.is_installed:
                self.toggle_enabled()
            else:
                self.complete = True
        elif self.selected_action == 0:
            self.complete_external_flow_and_close()
        else:
            self.back_to_link_screen()

    def content_lines(self, width: int) -> List[DisplayLine]:
        if self.screen is AppLinkScreen.LINK:
            return self.link_content_lines(width)
        return self.install_confirmation_lines(width)

    def link_content_lines(self, width: int) -> List[DisplayLine]:
        usable_width = max(1, int(width))
        lines = [DisplayLine(self.title, "bold")]
        if _trimmed(self.description):
            lines.extend(DisplayLine(line, "dim") for line in _wrap(_trimmed(self.description), usable_width))
        lines.append(DisplayLine(""))

        if _trimmed(self.suggest_reason):
            lines.extend(DisplayLine(line, "italic") for line in _wrap(_trimmed(self.suggest_reason), usable_width))
            lines.append(DisplayLine(""))

        browser_action = self.is_browser_action_suggestion()
        if self.is_installed and not browser_action:
            lines.extend(DisplayLine(line) for line in _wrap("Use $ to insert this app into the prompt.", usable_width))
            lines.append(DisplayLine(""))

        if browser_action:
            lines.append(DisplayLine("URL", "dim"))
            lines.extend(DisplayLine(line) for line in _wrap(self.url, usable_width))
            lines.append(DisplayLine(""))

        instructions = self.instructions.strip()
        if instructions:
            lines.extend(DisplayLine(line) for line in _wrap(instructions, usable_width))
            if not browser_action:
                lines.extend(
                    DisplayLine(line)
                    for line in _wrap("Newly installed apps can take a few minutes to appear in /apps.", usable_width)
                )
                if not self.is_installed:
                    lines.extend(
                        DisplayLine(line)
                        for line in _wrap("After installed, use $ to insert this app into the prompt.", usable_width)
                    )
            lines.append(DisplayLine(""))
        return lines

    def install_confirmation_lines(self, width: int) -> List[DisplayLine]:
        usable_width = max(1, int(width))
        if self.is_auth_suggestion():
            title = "Sign-in complete?"
        elif self.is_external_action_suggestion():
            title = "Action complete?"
        else:
            title = "Install complete?"
        lines = [DisplayLine(title, "bold"), DisplayLine("")]
        if self.is_auth_suggestion():
            body = "After signing in in your browser, return here to continue."
        elif self.is_external_action_suggestion():
            body = "After completing the action in your browser, return here to continue."
        else:
            body = "After installing this app in your browser, return here to refresh available apps."
        lines.extend(DisplayLine(line) for line in _wrap(body, usable_width))
        lines.append(DisplayLine(""))
        lines.append(DisplayLine("URL", "dim"))
        lines.extend(DisplayLine(line) for line in _wrap(self.url, usable_width))
        lines.append(DisplayLine(""))
        return lines

    def action_rows(self) -> List[Dict[str, Any]]:
        return [
            {"label": label, "selected": idx == self.selected_action}
            for idx, label in enumerate(self.action_labels())
        ]

    def action_state(self) -> Dict[str, Any]:
        return {"selected": self.selected_action, "labels": self.action_labels()}

    def action_rows_height(self, width: int | None = None) -> int:
        return len(self.action_labels())

    def hint_line(self) -> str:
        return "Enter to select, Esc to cancel"

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if key in {"up", "left", "backtab"}:
            self.move_selection_prev()
        elif key in {"down", "right", "tab"}:
            self.move_selection_next()
        elif key in {"enter"}:
            self.activate_selected_action()
        elif key in {"esc"}:
            if self.is_tool_suggestion():
                self.decline_tool_suggestion()
            elif self.screen is AppLinkScreen.INSTALL_CONFIRMATION:
                self.back_to_link_screen()
            else:
                self.complete = True
        elif key.isdigit() and key != "0":
            idx = int(key) - 1
            if idx < len(self.action_labels()):
                self.selected_action = idx
                self.activate_selected_action()

    def on_ctrl_c(self) -> None:
        if self.is_tool_suggestion():
            self.decline_tool_suggestion()
        else:
            self.complete = True

    def is_complete(self) -> bool:
        return self.complete

    def dismiss_app_server_request(self, resolved: Any) -> bool:
        if self.elicitation_target is None:
            return False
        server_name = _get_value(resolved, "server_name")
        request_id = _get_value(resolved, "request_id")
        if server_name == self.elicitation_target.server_name and request_id == self.elicitation_target.request_id:
            self.complete = True
            return True
        return False

    def terminal_title_requires_action(self) -> bool:
        return self.is_tool_suggestion() and not self.complete

    def desired_height(self, width: int) -> int:
        return len(self.content_lines(width)) + self.action_rows_height(width) + 1

    def render(self, area: Any = None, buf: Any = None) -> List[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width <= 0 or height <= 0:
            return []
        lines = self.content_lines(width)
        lines.extend(DisplayLine(row["label"], "selected" if row["selected"] else "plain") for row in self.action_rows())
        lines.append(DisplayLine(self.hint_line(), "dim"))
        return lines[:height]

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        lines = self.content_lines(width)
        lines.extend(
            DisplayLine(row["label"], "selected" if row["selected"] else "plain")
            for row in self.action_rows()
        )
        lines.append(DisplayLine(self.hint_line(), "dim"))
        selected_labels = {
            row["label"] for row in self.action_rows() if row["selected"]
        }
        return [
            TerminalPopupLine(line.text[: max(1, width)], line.text in selected_labels)
            for line in lines
        ]


@dataclass(frozen=True)
class AppLinkViewProjector:
    app_event_sender: AppEventSender
    show_view: Callable[[AppLinkView], Any]
    render: Callable[[], Any]

    def __call__(self, params: AppLinkViewParams) -> AppLinkView:
        candidate = AppLinkView.new(params, self.app_event_sender)
        view = self.show_view(candidate) or candidate
        self.render()
        return view


def handle_key_event(view: AppLinkView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def on_ctrl_c(view: AppLinkView) -> None:
    view.on_ctrl_c()


def is_complete(view: AppLinkView) -> bool:
    return view.is_complete()


def dismiss_app_server_request(view: AppLinkView, resolved: Any) -> bool:
    return view.dismiss_app_server_request(resolved)


def terminal_title_requires_action(view: AppLinkView) -> bool:
    return view.terminal_title_requires_action()


def desired_height(view: AppLinkView, width: int) -> int:
    return view.desired_height(width)


def render(view: AppLinkView, area: Any = None, buf: Any = None) -> List[DisplayLine]:
    return view.render(area, buf)


def _url_request_parts(request: Any) -> Optional[Tuple[Any, str, str, str]]:
    if isinstance(request, dict):
        if request.get("type") not in {None, "Url", "url"}:
            return None
        return (
            request.get("meta"),
            str(request.get("message", "")),
            str(request.get("url", "")),
            str(request.get("elicitation_id", "")),
        )
    url = getattr(request, "url", None)
    if url is None:
        return None
    return (
        getattr(request, "meta", None),
        str(getattr(request, "message", "")),
        str(url),
        str(getattr(request, "elicitation_id", "")),
    )


def _nested_dict(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _non_empty_str(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _send(target: Any, event: Dict[str, Any]) -> None:
    if target is None:
        return
    if isinstance(target, AppEventSender):
        kind = str(event.get("type") or "")
        if kind == "ResolveElicitation":
            target.resolve_elicitation(
                event.get("thread_id"),
                str(event.get("server_name") or ""),
                event.get("request_id"),
                event.get("decision"),
                event.get("content"),
                event.get("meta"),
            )
        elif kind == "OpenUrlInBrowser":
            target.open_url_in_browser(str(event.get("url") or ""))
        elif kind == "RefreshConnectors":
            target.refresh_connectors(bool(event.get("force_refetch")))
        elif kind == "SetAppEnabled":
            target.set_app_enabled(str(event.get("id") or ""), bool(event.get("enabled")))
        return
    if hasattr(target, "send"):
        target.send(event)
    elif hasattr(target, "append"):
        target.append(event)
    elif callable(target):
        target(event)
    elif hasattr(target, "events"):
        target.events.append(event)


def _trimmed(value: Optional[str]) -> str:
    return value.strip() if value else ""


def _wrap(value: str, width: int) -> List[str]:
    if value == "":
        return [""]
    return textwrap.wrap(
        value,
        width=max(1, width),
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event.lower()
    for attr in ("key", "code", "name"):
        value = getattr(key_event, attr, None)
        if value is not None:
            return str(value).lower()
    return str(key_event).lower()


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


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
    "AppLinkElicitationTarget",
    "AppLinkScreen",
    "AppLinkSuggestionType",
    "AppLinkView",
    "AppLinkViewParams",
    "CONNECTOR_AUTH_FAILURE_CONNECTOR_ID_KEY",
    "CONNECTOR_AUTH_FAILURE_CONNECTOR_NAME_KEY",
    "CONNECTOR_AUTH_FAILURE_IS_AUTH_FAILURE_KEY",
    "CONNECTOR_AUTH_FAILURE_META_KEY",
    "DisplayLine",
    "MCP_CODEX_APPS_SERVER_NAME",
    "MCP_TOOL_CODEX_APPS_META_KEY",
    "RUST_MODULE",
    "desired_height",
    "dismiss_app_server_request",
    "handle_key_event",
    "is_allowed_chatgpt_auth_host",
    "is_complete",
    "on_ctrl_c",
    "render",
    "terminal_title_requires_action",
    "validate_external_url",
]
