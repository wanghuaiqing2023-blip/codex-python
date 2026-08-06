"""MCP tool-call, inventory, and output history cells.

Upstream source: ``codex/codex-rs/tui/src/history_cell/mcp.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import base64
import json
from time import monotonic
from typing import Any, Iterable, Mapping

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from ..terminal_hyperlinks import HyperlinkLine, TerminalHyperlink, visible_lines
from .base import plain_lines
from .messages import raw_lines_from_source

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::mcp",
    source="codex/codex-rs/tui/src/history_cell/mcp.rs",
)

TOOL_CALL_MAX_LINES = 5
RAW_TOOL_OUTPUT_WIDTH = 10_000
MCP_DOCS_URL = "https://developers.openai.com/codex/mcp"


class McpAuthStatus(Enum):
    Unsupported = "Unsupported"
    NotLoggedIn = "Not logged in"
    BearerToken = "Bearer token"
    OAuth = "OAuth"

    @classmethod
    def coerce(cls, value: "McpAuthStatus | str | Any") -> "McpAuthStatus":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value)).replace("_", "").replace(" ", "").lower()
        mapping = {
            "unsupported": cls.Unsupported,
            "notloggedin": cls.NotLoggedIn,
            "bearertoken": cls.BearerToken,
            "oauth": cls.OAuth,
        }
        return mapping.get(name, cls.Unsupported)


class McpServerStatusDetail(Enum):
    Compact = "compact"
    Full = "full"

    @classmethod
    def coerce(cls, value: "McpServerStatusDetail | str | Any") -> "McpServerStatusDetail":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value)).lower()
        return cls.Full if name == "full" else cls.Compact


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def mcp_auth_status_label(status: McpAuthStatus | str | Any) -> str:
    return McpAuthStatus.coerce(status).value


@dataclass
class McpInventoryHistoryCell:
    """Styled `/mcp` inventory with semantic OSC-8 links.

    Rust stores these as styled ``Line`` values inside ``PlainHistoryCell``.
    The Python history facade carries links separately, so this cell preserves
    the same visible line styles while retaining the MCP documentation link.
    """

    lines: list[HyperlinkLine] = field(default_factory=list)

    def display_lines(self, _width: int) -> list[Line]:
        return visible_lines(self.lines)

    def display_hyperlink_lines(self, _width: int) -> list[HyperlinkLine]:
        return list(self.lines)

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(visible_lines(self.lines))


def _inventory_line(*spans: Span | str, style: Any = None) -> HyperlinkLine:
    return HyperlinkLine.new(Line.from_spans(spans, style=style))


@dataclass(frozen=True)
class McpInvocation:
    server: str
    tool: str
    arguments: Any | None = None

    @classmethod
    def coerce(cls, value: "McpInvocation | dict[str, Any] | Any") -> "McpInvocation":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(str(value.get("server", "")), str(value.get("tool", "")), value.get("arguments"))
        return cls(str(getattr(value, "server")), str(getattr(value, "tool")), getattr(value, "arguments", None))


def _json_compact(value: Any) -> str:
    if value is None:
        return ""
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return str(value)


def format_mcp_invocation(invocation: McpInvocation | dict[str, Any] | Any) -> Line:
    invocation = McpInvocation.coerce(invocation)
    args = _json_compact(invocation.arguments)
    return Line.from_text(f"{invocation.server}.{invocation.tool}({args})")


def _format_and_truncate_tool_result(text: str, line_limit: int, width: int) -> str:
    del width
    lines = str(text).splitlines() or [""]
    if len(lines) > line_limit:
        return "\n".join([*lines[:line_limit], f"... ({len(lines) - line_limit} more lines)"])
    return "\n".join(lines)


def _block_kind(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type", block.get("kind", ""))).lower()
    return str(getattr(block, "type", getattr(block, "kind", ""))).lower()


def _block_value(block: Any, name: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


@dataclass(frozen=True)
class CallToolResult:
    content: tuple[Any, ...] = ()
    is_error: bool | None = None

    @classmethod
    def coerce(cls, value: "CallToolResult | dict[str, Any] | Any") -> "CallToolResult":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(tuple(value.get("content", ())), value.get("is_error"))
        return cls(tuple(getattr(value, "content", ())), getattr(value, "is_error", None))


@dataclass
class CompletedMcpToolCallWithImageOutput:
    image: bytes | None = None

    def display_lines(self, _width: int) -> list[Line]:
        return [Line.from_text("tool result (image output)")]

    def raw_lines(self) -> list[Line]:
        return [Line.from_text("tool result (image output)")]


def _result_is_ok(result: Any) -> bool:
    return not isinstance(result, (str, Exception))


def _result_error_text(result: Any) -> str:
    return str(result)


@dataclass
class McpToolCallCell:
    call_id_value: str
    invocation: McpInvocation
    start_time: float = field(default_factory=monotonic)
    duration: float | None = None
    result: CallToolResult | str | Exception | None = None
    animations_enabled: bool = False

    @classmethod
    def new(
        cls, call_id: str, invocation: McpInvocation | dict[str, Any] | Any, animations_enabled: bool
    ) -> "McpToolCallCell":
        return cls(str(call_id), McpInvocation.coerce(invocation), animations_enabled=bool(animations_enabled))

    def call_id(self) -> str:
        return self.call_id_value

    def complete(self, duration: float, result: CallToolResult | dict[str, Any] | str | Exception) -> CompletedMcpToolCallWithImageOutput | None:
        self.duration = float(duration)
        self.result = result if isinstance(result, (str, Exception)) else CallToolResult.coerce(result)
        return try_new_completed_mcp_tool_call_with_image_output(self.result)

    def success(self) -> bool | None:
        if self.result is None:
            return None
        if not _result_is_ok(self.result):
            return False
        result = CallToolResult.coerce(self.result)
        return not bool(result.is_error)

    def mark_failed(self) -> None:
        self.duration = monotonic() - self.start_time
        self.result = "interrupted"

    @staticmethod
    def render_content_block(block: Any, width: int) -> str:
        kind = _block_kind(block)
        if kind == "text":
            text_obj = _block_value(block, "text", "")
            text = _block_value(text_obj, "text", text_obj)
            return _format_and_truncate_tool_result(str(text), TOOL_CALL_MAX_LINES, width)
        if kind == "image":
            return "<image content>"
        if kind == "audio":
            return "<audio content>"
        if kind == "resource":
            resource = _block_value(block, "resource", block)
            uri = _block_value(resource, "uri", "")
            return f"embedded resource: {uri}"
        if kind in {"resourcelink", "resource_link", "link"}:
            return f"link: {_block_value(block, 'uri', '')}"
        return _format_and_truncate_tool_result(_json_compact(block), TOOL_CALL_MAX_LINES, width)

    def display_lines(self, width: int) -> list[Line]:
        status = self.success()
        bullet = "*" if status is not None else "-"
        header = "Called" if status is not None else "Calling"
        invocation = line_text(format_mcp_invocation(self.invocation))
        lines = [Line.from_text(f"{bullet} {header} {invocation}")]
        detail_width = max(1, int(width) - 4)
        if self.result is not None:
            if _result_is_ok(self.result):
                result = CallToolResult.coerce(self.result)
                for block in result.content:
                    for segment in self.render_content_block(block, detail_width).split("\n"):
                        lines.append(Line.from_text(f"  | {segment}"))
            else:
                err_text = _format_and_truncate_tool_result(f"Error: {_result_error_text(self.result)}", TOOL_CALL_MAX_LINES, int(width))
                for segment in err_text.split("\n"):
                    lines.append(Line.from_text(f"  | {segment}"))
        return lines

    def raw_lines(self) -> list[Line]:
        header = "Called" if self.success() is not None else "Calling"
        lines = [Line.from_text(f"{header} {line_text(format_mcp_invocation(self.invocation))}")]
        if self.result is not None:
            if _result_is_ok(self.result):
                result = CallToolResult.coerce(self.result)
                for block in result.content:
                    lines.extend(raw_lines_from_source(self.render_content_block(block, RAW_TOOL_OUTPUT_WIDTH)))
            else:
                lines.append(Line.from_text(f"Error: {_result_error_text(self.result)}"))
        return lines

    def transcript_animation_tick(self) -> int | None:
        if not self.animations_enabled or self.result is not None:
            return None
        return int(((monotonic() - self.start_time) * 1000) // 50)


def new_active_mcp_tool_call(
    call_id: str, invocation: McpInvocation | dict[str, Any] | Any, animations_enabled: bool
) -> McpToolCallCell:
    return McpToolCallCell.new(call_id, invocation, animations_enabled)


def _image_data(block: Any) -> str | None:
    if _block_kind(block) != "image":
        return None
    data = _block_value(block, "data", None)
    image = _block_value(block, "image", None)
    if data is None and image is not None:
        data = _block_value(image, "data", None)
    return None if data is None else str(data)


def decode_mcp_image(block: Any) -> bytes | None:
    data = _image_data(block)
    if not data:
        return None
    if data.startswith("data:"):
        if "," not in data:
            return None
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=True)
    except Exception:
        return None
    if raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff") or raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return raw
    return None


def try_new_completed_mcp_tool_call_with_image_output(result: CallToolResult | dict[str, Any] | str | Exception) -> CompletedMcpToolCallWithImageOutput | None:
    if not _result_is_ok(result):
        return None
    coerced = CallToolResult.coerce(result)
    for block in coerced.content:
        image = decode_mcp_image(block)
        if image is not None:
            return CompletedMcpToolCallWithImageOutput(image)
    return None


def empty_mcp_output() -> McpInventoryHistoryCell:
    docs_prefix = "    See the "
    docs_label = "MCP docs"
    docs_line = _inventory_line(
        docs_prefix,
        Span(docs_label, "underlined"),
        " to configure them.",
        style="dim",
    )
    docs_line.hyperlinks.append(
        TerminalHyperlink(
            range(len(docs_prefix), len(docs_prefix) + len(docs_label)),
            MCP_DOCS_URL,
        )
    )
    return McpInventoryHistoryCell(
        [
            _inventory_line(Span("/mcp", "magenta")),
            _inventory_line(""),
            _inventory_line("🔌  ", Span("MCP Tools", "bold")),
            _inventory_line(""),
            _inventory_line("  • No MCP servers configured.", style="italic"),
            docs_line,
        ]
    )


@dataclass(frozen=True)
class Resource:
    name: str
    uri: str
    title: str | None = None

    @classmethod
    def coerce(cls, value: "Resource | dict[str, Any] | Any") -> "Resource":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(str(value.get("name", "")), str(value.get("uri", "")), value.get("title"))
        return cls(str(getattr(value, "name")), str(getattr(value, "uri")), getattr(value, "title", None))


@dataclass(frozen=True)
class ResourceTemplate:
    name: str
    uri_template: str
    title: str | None = None

    @classmethod
    def coerce(cls, value: "ResourceTemplate | dict[str, Any] | Any") -> "ResourceTemplate":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                str(value.get("name", "")),
                str(value.get("uri_template", value.get("uriTemplate", ""))),
                value.get("title"),
            )
        return cls(
            str(getattr(value, "name")),
            str(getattr(value, "uri_template", getattr(value, "uriTemplate", ""))),
            getattr(value, "title", None),
        )


@dataclass(frozen=True)
class McpServerStatus:
    name: str
    tools: Mapping[str, Any] = field(default_factory=dict)
    resources: tuple[Resource, ...] = ()
    resource_templates: tuple[ResourceTemplate, ...] = ()
    auth_status: McpAuthStatus = McpAuthStatus.Unsupported

    @classmethod
    def coerce(cls, value: "McpServerStatus | dict[str, Any] | Any") -> "McpServerStatus":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                str(value.get("name", "")),
                dict(value.get("tools", {})),
                tuple(Resource.coerce(item) for item in value.get("resources", ())),
                tuple(ResourceTemplate.coerce(item) for item in value.get("resource_templates", ())),
                McpAuthStatus.coerce(value.get("auth_status", "Unsupported")),
            )
        return cls(
            str(getattr(value, "name")),
            dict(getattr(value, "tools", {})),
            tuple(Resource.coerce(item) for item in getattr(value, "resources", ())),
            tuple(ResourceTemplate.coerce(item) for item in getattr(value, "resource_templates", ())),
            McpAuthStatus.coerce(getattr(value, "auth_status", "Unsupported")),
        )


def new_mcp_tools_output_from_statuses(
    statuses: Iterable[McpServerStatus | dict[str, Any] | Any],
    detail: McpServerStatusDetail | str | Any,
) -> McpInventoryHistoryCell:
    detail = McpServerStatusDetail.coerce(detail)
    status_list = sorted((McpServerStatus.coerce(status) for status in statuses), key=lambda item: item.name)
    lines = [
        _inventory_line(Span("/mcp", "magenta")),
        _inventory_line(""),
        _inventory_line("🔌  ", Span("MCP Tools", "bold")),
        _inventory_line(""),
    ]
    if not any(status.tools for status in status_list):
        lines.extend(
            [
                _inventory_line("  • No MCP tools available.", style="italic"),
                _inventory_line(""),
            ]
        )
    for status in status_list:
        lines.append(_inventory_line("  • ", status.name))
        lines.append(
            _inventory_line(
                "    • Auth: ", mcp_auth_status_label(status.auth_status)
            )
        )
        names = sorted(status.tools.keys())
        lines.append(
            _inventory_line(
                "    • Tools: ", ", ".join(names) if names else "(none)"
            )
        )
        if detail is McpServerStatusDetail.Full:
            resource_spans: list[Span | str] = ["    • Resources: "]
            if status.resources:
                for index, resource in enumerate(status.resources):
                    if index:
                        resource_spans.append(", ")
                    resource_spans.extend(
                        [
                            resource.title or resource.name,
                            " ",
                            Span(f"({resource.uri})", "dim"),
                        ]
                    )
            else:
                resource_spans.append("(none)")
            lines.append(_inventory_line(*resource_spans))

            template_spans: list[Span | str] = ["    • Resource templates: "]
            if status.resource_templates:
                for index, template in enumerate(status.resource_templates):
                    if index:
                        template_spans.append(", ")
                    template_spans.extend(
                        [
                            template.title or template.name,
                            " ",
                            Span(f"({template.uri_template})", "dim"),
                        ]
                    )
            else:
                template_spans.append("(none)")
            lines.append(_inventory_line(*template_spans))
        lines.append(_inventory_line(""))
    return McpInventoryHistoryCell(lines)


def new_mcp_tools_output(
    config: Any,
    tools: Mapping[str, Any],
    resources: Mapping[str, Iterable[Any]] | None = None,
    resource_templates: Mapping[str, Iterable[Any]] | None = None,
    auth_statuses: Mapping[str, Any] | None = None,
) -> McpInventoryHistoryCell:
    servers = getattr(getattr(config, "mcp_servers", config), "get", lambda: getattr(config, "mcp_servers", {}))()
    if isinstance(config, dict):
        servers = config.get("mcp_servers", servers)
    statuses = []
    for server in sorted(servers.keys()):
        prefix = f"{server}."
        server_tools = {name[len(prefix):]: tool for name, tool in tools.items() if name.startswith(prefix)}
        statuses.append(
            McpServerStatus(
                server,
                server_tools,
                tuple(Resource.coerce(item) for item in (resources or {}).get(server, ())),
                tuple(ResourceTemplate.coerce(item) for item in (resource_templates or {}).get(server, ())),
                McpAuthStatus.coerce((auth_statuses or {}).get(server, McpAuthStatus.Unsupported)),
            )
        )
    return new_mcp_tools_output_from_statuses(statuses, McpServerStatusDetail.Full)


@dataclass
class McpInventoryLoadingCell:
    animations_enabled: bool = False
    start_time: float = field(default_factory=monotonic)

    @classmethod
    def new(cls, animations_enabled: bool) -> "McpInventoryLoadingCell":
        return cls(bool(animations_enabled))

    def display_lines(self, _width: int) -> list[Line]:
        return [
            Line.from_spans(
                [
                    Span("•", "dim"),
                    " ",
                    Span("Loading MCP inventory", "bold"),
                    Span("…", "dim"),
                ]
            )
        ]

    def raw_lines(self) -> list[Line]:
        return [Line.from_text("Loading MCP inventory...")]

    def transcript_animation_tick(self) -> int | None:
        if not self.animations_enabled:
            return None
        return int(((monotonic() - self.start_time) * 1000) // 50)


def new_mcp_inventory_loading(animations_enabled: bool) -> McpInventoryLoadingCell:
    return McpInventoryLoadingCell.new(animations_enabled)


def display_lines(cell: Any, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: Any) -> list[Line]:
    return cell.raw_lines()


def transcript_animation_tick(cell: Any) -> int | None:
    method = getattr(cell, "transcript_animation_tick", None)
    return method() if callable(method) else None


__all__ = [
    "CallToolResult",
    "CompletedMcpToolCallWithImageOutput",
    "MCP_DOCS_URL",
    "McpAuthStatus",
    "McpInventoryLoadingCell",
    "McpInventoryHistoryCell",
    "McpInvocation",
    "McpServerStatus",
    "McpServerStatusDetail",
    "McpToolCallCell",
    "RAW_TOOL_OUTPUT_WIDTH",
    "RUST_MODULE",
    "Resource",
    "ResourceTemplate",
    "decode_mcp_image",
    "display_lines",
    "empty_mcp_output",
    "format_mcp_invocation",
    "line_text",
    "mcp_auth_status_label",
    "new_active_mcp_tool_call",
    "new_mcp_inventory_loading",
    "new_mcp_tools_output",
    "new_mcp_tools_output_from_statuses",
    "raw_lines",
    "transcript_animation_tick",
    "try_new_completed_mcp_tool_call_with_image_output",
]
