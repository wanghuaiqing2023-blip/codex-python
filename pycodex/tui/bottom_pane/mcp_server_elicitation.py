"""Semantic port of Rust bottom_pane/mcp_server_elicitation.rs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Callable, Iterable, Mapping, MutableSequence, Sequence

from ..app_event_sender import AppEventSender
from .bottom_pane_view import BottomPaneViewDefaults
from .selection_popup_common import TerminalPopupLine

ANSWER_PLACEHOLDER = "Type your answer"
OPTIONAL_ANSWER_PLACEHOLDER = "Type your answer (optional)"
FOOTER_SEPARATOR = " | "
MIN_COMPOSER_HEIGHT = 3
MIN_OVERLAY_HEIGHT = 8

APPROVAL_FIELD_ID = "__approval"
APPROVAL_ACCEPT_ONCE_VALUE = "accept"
APPROVAL_ACCEPT_SESSION_VALUE = "accept_session"
APPROVAL_ACCEPT_ALWAYS_VALUE = "accept_always"
APPROVAL_DECLINE_VALUE = "decline"
APPROVAL_CANCEL_VALUE = "cancel"
APPROVAL_TOOL_PARAM_DISPLAY_LIMIT = 3
APPROVAL_TOOL_PARAM_VALUE_TRUNCATE_GRAPHEMES = 60

APPROVAL_META_KIND_KEY = "kind"
APPROVAL_KIND_MCP_TOOL_CALL = "mcp_tool_call"
APPROVAL_KIND_TOOL_SUGGESTION = "tool_suggestion"
APPROVAL_PERSIST_KEY = "persist"
APPROVAL_PERSIST_SESSION_VALUE = "session"
APPROVAL_PERSIST_ALWAYS_VALUE = "always"
TOOL_NAME_KEY = "tool_name"
APPROVAL_TOOL_PARAMS_DISPLAY_KEY = "tool_params_display"
APPROVAL_TOOL_PARAMS_KEY = "tool_params"
TOOL_TYPE_KEY = "tool_type"
TOOL_ID_KEY = "tool_id"
TOOL_SUGGEST_SUGGEST_TYPE_KEY = "suggest_type"
TOOL_SUGGEST_REASON_KEY = "suggest_reason"
TOOL_SUGGEST_INSTALL_URL_KEY = "install_url"


class McpServerElicitationResponseMode(Enum):
    FORM_CONTENT = "form_content"
    APPROVAL_ACTION = "approval_action"


class ToolSuggestionToolType(Enum):
    CONNECTOR = "connector"
    PLUGIN = "plugin"


class ToolSuggestionType(Enum):
    INSTALL = "install"
    ENABLE = "enable"


@dataclass
class ComposerDraft:
    text: str = ""
    text_elements: list[Any] = field(default_factory=list)
    local_image_paths: list[Any] = field(default_factory=list)
    pending_pastes: list[str] = field(default_factory=list)

    def text_with_pending(self) -> str:
        return self.text + "".join(str(item) for item in self.pending_pastes)


@dataclass(frozen=True)
class McpServerElicitationOption:
    label: str
    description: str | None = None
    value: Any = None


@dataclass
class McpServerElicitationFieldInput:
    kind: str
    options: list[McpServerElicitationOption] = field(default_factory=list)
    default_idx: int | None = None
    secret: bool = False

    @classmethod
    def select(cls, options: Sequence[McpServerElicitationOption], default_idx: int | None = None) -> "McpServerElicitationFieldInput":
        return cls("select", list(options), default_idx, False)

    @classmethod
    def text(cls, secret: bool = False) -> "McpServerElicitationFieldInput":
        return cls("text", [], None, secret)


@dataclass
class McpServerElicitationField:
    id: str
    label: str
    prompt: str | None
    required: bool
    input: McpServerElicitationFieldInput


@dataclass(frozen=True)
class ToolSuggestionRequest:
    tool_type: ToolSuggestionToolType
    suggest_type: ToolSuggestionType
    suggest_reason: str
    tool_id: str
    tool_name: str
    install_url: str | None = None


@dataclass(frozen=True)
class McpToolApprovalDisplayParam:
    name: str
    value: Any
    display_name: str


@dataclass
class McpServerElicitationFormRequest:
    thread_id: Any
    server_name: str
    request_id: str
    message: str
    approval_display_params: list[McpToolApprovalDisplayParam] = field(default_factory=list)
    response_mode: McpServerElicitationResponseMode = McpServerElicitationResponseMode.FORM_CONTENT
    fields: list[McpServerElicitationField] = field(default_factory=list)
    tool_suggestion: ToolSuggestionRequest | None = None

    @classmethod
    def from_parts(
        cls,
        *,
        thread_id: Any,
        server_name: str,
        request_id: str,
        message: str,
        schema: Mapping[str, Any] | None,
        meta: Mapping[str, Any] | None = None,
    ) -> "McpServerElicitationFormRequest | None":
        meta = dict(meta or {})
        tool_suggestion = parse_tool_suggestion_request(meta)
        approval_params = parse_tool_approval_display_params(meta)
        formatted_message = format_tool_approval_display_message(message, approval_params)
        is_tool_approval = meta.get(APPROVAL_META_KIND_KEY) == APPROVAL_KIND_MCP_TOOL_CALL
        if _schema_is_message_only(schema):
            if tool_suggestion is not None:
                return cls(thread_id, server_name, request_id, message.strip(), approval_params, McpServerElicitationResponseMode.FORM_CONTENT, [], tool_suggestion)
            return cls(thread_id, server_name, request_id, formatted_message, approval_params, McpServerElicitationResponseMode.APPROVAL_ACTION, [approval_action_field(meta, is_tool_approval=is_tool_approval)], None)
        fields = parse_fields_from_schema(schema)
        if fields is None:
            return None
        return cls(thread_id, server_name, request_id, message.strip(), approval_params, McpServerElicitationResponseMode.FORM_CONTENT, fields, tool_suggestion)

    @classmethod
    def from_app_server_request(cls, thread_id: Any, params: Mapping[str, Any]) -> "McpServerElicitationFormRequest | None":
        server_name = params.get("server_name")
        request = params.get("request") or {}
        if not server_name or not isinstance(request, Mapping):
            return None
        form = request.get("form") if isinstance(request.get("form"), Mapping) else request
        if not isinstance(form, Mapping):
            return None
        return cls.from_parts(
            thread_id=thread_id,
            server_name=str(server_name),
            request_id=str(form.get("request_id") or params.get("request_id") or ""),
            message=str(form.get("message") or ""),
            schema=form.get("requested_schema"),
            meta=form.get("meta") if isinstance(form.get("meta"), Mapping) else {},
        )


@dataclass
class McpServerElicitationAnswerState:
    selected_idx: int | None = None
    draft: ComposerDraft = field(default_factory=ComposerDraft)
    answer_committed: bool = False


@dataclass(frozen=True)
class FooterTip:
    text: str
    highlight: bool = False

    @classmethod
    def new(cls, text: str) -> "FooterTip":
        return cls(text=text, highlight=False)

    @classmethod
    def highlighted(cls, text: str) -> "FooterTip":
        return cls(text=text, highlight=True)


class McpServerElicitationOverlay(BottomPaneViewDefaults):
    def __init__(self, request: McpServerElicitationFormRequest, tx_event: Any | None = None, has_input_focus: bool = True, enhanced_keys_supported: bool = False, disable_paste_burst: bool = False) -> None:
        self.request = request
        self.tx_event = tx_event
        self.has_input_focus = has_input_focus
        self.enhanced_keys_supported = enhanced_keys_supported
        self.disable_paste_burst = disable_paste_burst
        self.pending_requests: list[McpServerElicitationFormRequest] = []
        self.current_idx = 0
        self.complete = False
        self.emitted_events: list[dict[str, Any]] = []
        self.answers = [_initial_answer_state(field) for field in request.fields]

    @classmethod
    def new(cls, request: McpServerElicitationFormRequest, tx_event: Any | None = None, has_input_focus: bool = True, enhanced_keys_supported: bool = False, disable_paste_burst: bool = False) -> "McpServerElicitationOverlay":
        return cls(request, tx_event, has_input_focus, enhanced_keys_supported, disable_paste_burst)

    @classmethod
    def new_with_keymap(cls, request: McpServerElicitationFormRequest, tx_event: Any | None = None, **kwargs: Any) -> "McpServerElicitationOverlay":
        return cls(request, tx_event, **kwargs)

    def is_complete(self) -> bool:
        return self.complete

    def terminal_title_requires_action(self) -> bool:
        return not self.complete

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        rows = [self.request.message]
        field = self.current_field()
        if field is not None:
            rows.append(field.label or field.id)
            if field.input.kind == "select":
                answer = self.current_answer()
                selected = None if answer is None else answer.selected_idx
                rows.extend(
                    f"{'>' if index == selected else ' '} {index + 1}. {option.label}"
                    for index, option in enumerate(field.input.options)
                )
        rows.append("Enter to submit | Esc to cancel")
        return [
            TerminalPopupLine(row[: max(1, width)], selected=row.startswith(">"))
            for row in rows
        ]

    def handle_key_event(self, key_event: Any) -> None:
        self.handle_key(str(getattr(key_event, "text", key_event)))

    def try_consume_mcp_server_elicitation_request(
        self,
        request: McpServerElicitationFormRequest,
    ) -> McpServerElicitationFormRequest | None:
        if self.complete:
            self._activate(request)
        else:
            self.pending_requests.append(request)
        return None

    def dismiss_app_server_request(self, request: Any, request_id: str | None = None) -> bool:
        server_name = str(request if request_id is not None else getattr(request, "server_name", ""))
        request_id = str(request_id if request_id is not None else getattr(request, "request_id", ""))
        if self.request.server_name == server_name and self.request.request_id == request_id:
            self._advance_or_complete()
            return True
        for index, pending in enumerate(self.pending_requests):
            if pending.server_name == server_name and pending.request_id == request_id:
                del self.pending_requests[index]
                return True
        return False

    def field_count(self) -> int:
        return len(self.request.fields)

    def current_index(self) -> int:
        return self.current_idx

    def current_field(self) -> McpServerElicitationField | None:
        if not self.request.fields:
            return None
        return self.request.fields[self.current_idx]

    def current_answer(self) -> McpServerElicitationAnswerState | None:
        if not self.answers:
            return None
        return self.answers[self.current_idx]

    def current_answer_mut(self) -> McpServerElicitationAnswerState | None:
        return self.current_answer()

    def current_field_is_select(self) -> bool:
        field = self.current_field()
        return bool(field and field.input.kind == "select")

    def selected_option_index(self) -> int | None:
        answer = self.current_answer()
        return None if answer is None else answer.selected_idx

    def current_options(self) -> list[McpServerElicitationOption]:
        field = self.current_field()
        return [] if field is None else list(field.input.options)

    def options_len(self) -> int:
        return len(self.current_options())

    def option_index_for_digit(self, digit: int) -> int | None:
        if digit <= 0:
            return None
        idx = digit - 1
        return idx if idx < self.options_len() else None

    def jump_to_field(self, index: int) -> None:
        if self.request.fields:
            self.current_idx = max(0, min(index, len(self.request.fields) - 1))

    def move_field(self, delta: int) -> None:
        self.jump_to_field(self.current_idx + delta)

    def select_option(self, index: int, committed: bool = True) -> bool:
        answer = self.current_answer()
        field = self.current_field()
        if answer is None or field is None or field.input.kind != "select":
            return False
        if not 0 <= index < len(field.input.options):
            return False
        answer.selected_idx = index
        answer.answer_committed = committed
        return True

    def select_current_option(self, committed: bool = True) -> bool:
        answer = self.current_answer()
        idx = 0 if answer is None or answer.selected_idx is None else answer.selected_idx
        return self.select_option(idx, committed=committed)

    def set_text_answer(self, text: str) -> None:
        answer = self.current_answer()
        if answer is not None:
            answer.draft.text = text
            answer.answer_committed = bool(text)

    def field_value(self, index: int) -> Any:
        field = self.request.fields[index]
        answer = self.answers[index]
        if field.input.kind == "select":
            if answer.selected_idx is None:
                return None
            return field.input.options[answer.selected_idx].value
        return answer.draft.text_with_pending()

    def is_current_field_answered(self) -> bool:
        field = self.current_field()
        if field is None:
            return True
        value = self.field_value(self.current_idx)
        return value is not None and (not isinstance(value, str) or bool(value.strip()))

    def required_unanswered_count(self) -> int:
        return sum(1 for idx, field in enumerate(self.request.fields) if field.required and not _is_answered(field, self.field_value(idx)))

    def first_required_unanswered_index(self) -> int | None:
        for idx, field in enumerate(self.request.fields):
            if field.required and not _is_answered(field, self.field_value(idx)):
                return idx
        return None

    def submit_answers(self) -> dict[str, Any] | None:
        missing = self.first_required_unanswered_index()
        if missing is not None:
            self.jump_to_field(missing)
            return None
        event = self._approval_event() if self.request.response_mode == McpServerElicitationResponseMode.APPROVAL_ACTION else self._form_event()
        self._emit(event)
        self._advance_or_complete()
        return event

    def dispatch_cancel(self) -> dict[str, Any]:
        event = resolve_elicitation_event(self.request, "Cancel", content=None, meta=None)
        self._emit(event)
        return event

    def on_ctrl_c(self) -> str:
        answer = self.current_answer()
        if (
            not self.current_field_is_select()
            and answer is not None
            and bool(answer.draft.text_with_pending())
        ):
            answer.draft = ComposerDraft()
            answer.answer_committed = False
            return "Handled"
        self.dispatch_cancel()
        self.complete = True
        return "Handled"

    def handle_key(self, key: str) -> str:
        normalized = key.lower()
        if normalized == "esc":
            self.dispatch_cancel()
            self.complete = True
            return "Handled"
        if normalized == "ctrl-c":
            return self.on_ctrl_c()
        if normalized in {"ctrl-l", "right", "tab"}:
            self.move_field(1)
            return "Handled"
        if normalized in {"ctrl-h", "left", "backtab"}:
            self.move_field(-1)
            return "Handled"
        if normalized == "enter":
            self.submit_answers()
            return "Handled"
        if normalized.isdigit():
            idx = self.option_index_for_digit(int(normalized))
            if idx is not None:
                self.select_option(idx)
                return "Handled"
        return "Ignored"

    def _approval_event(self) -> dict[str, Any]:
        value = self.field_value(0) if self.request.fields else APPROVAL_ACCEPT_ONCE_VALUE
        if value == APPROVAL_ACCEPT_SESSION_VALUE:
            return resolve_elicitation_event(self.request, "Accept", content=None, meta={APPROVAL_PERSIST_KEY: APPROVAL_PERSIST_SESSION_VALUE})
        if value == APPROVAL_ACCEPT_ALWAYS_VALUE:
            return resolve_elicitation_event(self.request, "Accept", content=None, meta={APPROVAL_PERSIST_KEY: APPROVAL_PERSIST_ALWAYS_VALUE})
        if value == APPROVAL_DECLINE_VALUE:
            return resolve_elicitation_event(self.request, "Decline", content=None, meta=None)
        if value == APPROVAL_CANCEL_VALUE:
            return resolve_elicitation_event(self.request, "Cancel", content=None, meta=None)
        return resolve_elicitation_event(self.request, "Accept", content=None, meta=None)

    def _form_event(self) -> dict[str, Any]:
        content = {field.id: self.field_value(idx) for idx, field in enumerate(self.request.fields)}
        return resolve_elicitation_event(self.request, "Accept", content=content, meta=None)

    def _emit(self, event: dict[str, Any]) -> None:
        self.emitted_events.append(event)
        if isinstance(self.tx_event, AppEventSender):
            self.tx_event.resolve_elicitation(
                event.get("thread_id"),
                str(event.get("server_name") or ""),
                event.get("request_id"),
                event.get("decision"),
                event.get("content"),
                event.get("meta"),
            )
            return
        _send(self.tx_event, event)

    def _advance_or_complete(self) -> None:
        if self.pending_requests:
            self._activate(self.pending_requests.pop(0))
        else:
            self.complete = True

    def _activate(self, request: McpServerElicitationFormRequest) -> None:
        self.request = request
        self.current_idx = 0
        self.complete = False
        self.answers = [_initial_answer_state(field) for field in request.fields]


@dataclass(frozen=True)
class McpServerElicitationViewProjector:
    """Project Rust MCP form requests into the shared bottom-pane stack."""

    app_event_sender: AppEventSender
    show_view: Callable[[McpServerElicitationOverlay], Any]
    render: Callable[[], Any]

    def __call__(self, request: McpServerElicitationFormRequest) -> McpServerElicitationOverlay:
        candidate = McpServerElicitationOverlay.new(request, self.app_event_sender)
        view = self.show_view(candidate) or candidate
        self.render()
        return view


def approval_action_field(meta: Mapping[str, Any], *, is_tool_approval: bool = False) -> McpServerElicitationField:
    options = [McpServerElicitationOption("Allow", value=APPROVAL_ACCEPT_ONCE_VALUE)]
    if approval_supports_persist_mode(meta, APPROVAL_PERSIST_SESSION_VALUE):
        options.append(McpServerElicitationOption("Allow for this session", value=APPROVAL_ACCEPT_SESSION_VALUE))
    if approval_supports_persist_mode(meta, APPROVAL_PERSIST_ALWAYS_VALUE):
        options.append(McpServerElicitationOption("Always allow", value=APPROVAL_ACCEPT_ALWAYS_VALUE))
    if is_tool_approval:
        options.append(McpServerElicitationOption("Cancel", value=APPROVAL_CANCEL_VALUE))
    else:
        options.append(McpServerElicitationOption("Deny", value=APPROVAL_DECLINE_VALUE))
        options.append(McpServerElicitationOption("Cancel", value=APPROVAL_CANCEL_VALUE))
    return McpServerElicitationField(APPROVAL_FIELD_ID, "Action", None, True, McpServerElicitationFieldInput.select(options, default_idx=0))


def parse_tool_suggestion_request(meta: Mapping[str, Any] | None) -> ToolSuggestionRequest | None:
    if not isinstance(meta, Mapping) or meta.get(APPROVAL_META_KIND_KEY) != APPROVAL_KIND_TOOL_SUGGESTION:
        return None
    tool_type = _enum_lookup(ToolSuggestionToolType, meta.get(TOOL_TYPE_KEY))
    suggest_type = _enum_lookup(ToolSuggestionType, meta.get(TOOL_SUGGEST_SUGGEST_TYPE_KEY))
    reason = meta.get(TOOL_SUGGEST_REASON_KEY)
    tool_id = meta.get(TOOL_ID_KEY)
    tool_name = meta.get(TOOL_NAME_KEY)
    if tool_type is None or suggest_type is None or not all(isinstance(v, str) and v for v in (reason, tool_id, tool_name)):
        return None
    install_url = meta.get(TOOL_SUGGEST_INSTALL_URL_KEY)
    return ToolSuggestionRequest(tool_type, suggest_type, reason, tool_id, tool_name, install_url if isinstance(install_url, str) else None)


def approval_supports_persist_mode(meta: Mapping[str, Any] | None, expected_mode: str) -> bool:
    if not isinstance(meta, Mapping):
        return False
    persist = meta.get(APPROVAL_PERSIST_KEY)
    if isinstance(persist, str):
        return persist == expected_mode
    if isinstance(persist, Sequence) and not isinstance(persist, (str, bytes, bytearray)):
        return expected_mode in persist
    return False


def parse_tool_approval_display_params(meta: Mapping[str, Any] | None) -> list[McpToolApprovalDisplayParam]:
    if not isinstance(meta, Mapping):
        return []
    explicit = meta.get(APPROVAL_TOOL_PARAMS_DISPLAY_KEY)
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes, bytearray)):
        parsed = [parse_tool_approval_display_param(item) for item in explicit]
        parsed = [item for item in parsed if item is not None]
        if parsed:
            return parsed
    params = meta.get(APPROVAL_TOOL_PARAMS_KEY)
    if not isinstance(params, Mapping):
        return []
    return [McpToolApprovalDisplayParam(str(name), value, str(name)) for name, value in sorted(params.items(), key=lambda item: str(item[0]))]


def parse_tool_approval_display_param(value: Any) -> McpToolApprovalDisplayParam | None:
    if not isinstance(value, Mapping):
        return None
    name = value.get("name")
    if not isinstance(name, str) or not name:
        return None
    display_name = value.get("display_name")
    if not isinstance(display_name, str) or not display_name:
        display_name = name
    if "value" not in value:
        return None
    return McpToolApprovalDisplayParam(name=name, value=value["value"], display_name=display_name)


def format_tool_approval_display_message(message: str, params: Sequence[McpToolApprovalDisplayParam]) -> str:
    sections: list[str] = []
    stripped = str(message).strip()
    if stripped:
        sections.append(stripped)
    if params:
        sections.append("\n".join(format_tool_approval_display_param_line(param) for param in params[:APPROVAL_TOOL_PARAM_DISPLAY_LIMIT]))
    if not sections:
        return ""
    return "\n\n".join(sections) + "\n"


def format_tool_approval_display_param_line(param: McpToolApprovalDisplayParam) -> str:
    return f"{param.display_name}: {format_tool_approval_display_param_value(param.value)}"


def format_tool_approval_display_param_value(value: Any) -> str:
    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(text) > APPROVAL_TOOL_PARAM_VALUE_TRUNCATE_GRAPHEMES:
        return text[:APPROVAL_TOOL_PARAM_VALUE_TRUNCATE_GRAPHEMES] + "..."
    return text


def parse_fields_from_schema(schema: Mapping[str, Any] | None) -> list[McpServerElicitationField] | None:
    if not isinstance(schema, Mapping) or schema.get("type") != "object":
        return None
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or not properties:
        return None
    required_values = schema.get("required", [])
    required = {str(item) for item in required_values} if isinstance(required_values, Sequence) and not isinstance(required_values, (str, bytes, bytearray)) else set()
    fields: list[McpServerElicitationField] = []
    for field_id, field_schema in properties.items():
        if not isinstance(field_schema, Mapping):
            return None
        field = parse_field(str(field_id), field_schema, str(field_id) in required)
        if field is None:
            return None
        fields.append(field)
    return fields or None


def parse_field(field_id: str, schema: Mapping[str, Any], required: bool) -> McpServerElicitationField | None:
    label = str(schema.get("title") or field_id)
    prompt = schema.get("description")
    prompt = prompt if isinstance(prompt, str) else None
    enum_values = schema.get("enum")
    if isinstance(enum_values, Sequence) and not isinstance(enum_values, (str, bytes, bytearray)):
        return parse_single_select_field(field_id, label, prompt, required, enum_values, schema.get("default"))
    schema_type = schema.get("type")
    if schema_type == "boolean":
        default = schema.get("default")
        options = [McpServerElicitationOption("Yes", value=True), McpServerElicitationOption("No", value=False)]
        default_idx = 0 if default is True else 1 if default is False else None
        return McpServerElicitationField(field_id, label, prompt, required, McpServerElicitationFieldInput.select(options, default_idx))
    if schema_type == "string" or schema_type is None:
        return McpServerElicitationField(field_id, label, prompt, required, McpServerElicitationFieldInput.text(secret=schema.get("format") == "password"))
    return None


def parse_single_select_field(field_id: str, label: str, prompt: str | None, required: bool, enum_values: Iterable[Any], default: Any = None) -> McpServerElicitationField | None:
    options = [McpServerElicitationOption(str(value), value=value) for value in enum_values]
    if not options:
        return None
    default_idx = next((idx for idx, option in enumerate(options) if option.value == default), None)
    return McpServerElicitationField(field_id, label, prompt, required, McpServerElicitationFieldInput.select(options, default_idx))


def empty_object_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


def tool_approval_meta(*, persist: Any = None, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {APPROVAL_META_KIND_KEY: APPROVAL_KIND_MCP_TOOL_CALL}
    if persist is not None:
        meta[APPROVAL_PERSIST_KEY] = persist
    if params is not None:
        meta[APPROVAL_TOOL_PARAMS_KEY] = dict(params)
    return meta


def form_request(**kwargs: Any) -> McpServerElicitationFormRequest | None:
    return McpServerElicitationFormRequest.from_parts(**kwargs)


def request_id(request: McpServerElicitationFormRequest) -> str:
    return request.request_id


def from_form_request(thread_id: Any, params: Mapping[str, Any]) -> McpServerElicitationFormRequest | None:
    return McpServerElicitationFormRequest.from_app_server_request(thread_id, params)


def resolve_elicitation_event(request: McpServerElicitationFormRequest, decision: str, *, content: Mapping[str, Any] | None, meta: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "type": "ResolveElicitation",
        "thread_id": request.thread_id,
        "server_name": request.server_name,
        "request_id": request.request_id,
        "decision": decision,
        "content": dict(content) if content is not None else None,
        "meta": dict(meta) if meta is not None else None,
    }


def try_consume_mcp_server_elicitation_request(
    overlay: McpServerElicitationOverlay,
    request: McpServerElicitationFormRequest,
) -> McpServerElicitationFormRequest | None:
    return overlay.try_consume_mcp_server_elicitation_request(request)


def dismiss_app_server_request(overlay: McpServerElicitationOverlay, server_name: str, request_id: str) -> bool:
    return overlay.dismiss_app_server_request(server_name, request_id)


def _schema_is_message_only(schema: Mapping[str, Any] | None) -> bool:
    if schema is None:
        return True
    return isinstance(schema, Mapping) and schema.get("type") == "object" and schema.get("properties") == {}


def _initial_answer_state(field: McpServerElicitationField) -> McpServerElicitationAnswerState:
    answer = McpServerElicitationAnswerState()
    if field.input.kind == "select":
        answer.selected_idx = field.input.default_idx
        answer.answer_committed = field.input.default_idx is not None
    return answer


def _is_answered(field: McpServerElicitationField, value: Any) -> bool:
    if value is None:
        return False
    if field.input.kind == "text":
        return bool(str(value).strip())
    return True


def _enum_lookup(enum_cls: type[Enum], value: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    for member in enum_cls:
        if member.value == value:
            return member
    return None


def _send(target: Any, event: dict[str, Any]) -> None:
    if target is None:
        return
    if hasattr(target, "send"):
        target.send(event)
    elif callable(target):
        target(event)
    elif isinstance(target, MutableSequence):
        target.append(event)


__all__ = [name for name in globals() if not name.startswith("_")]
