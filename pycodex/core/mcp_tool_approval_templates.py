"""Consequential MCP tool approval message templates.

Ported from ``codex/codex-rs/core/src/mcp_tool_approval_templates.rs``. This
module keeps the pure template loading and rendering logic; logging/tracing and
MCP runtime integration stay outside this stdlib-only slice.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence


CONSEQUENTIAL_TOOL_MESSAGE_TEMPLATES_SCHEMA_VERSION = 4
CONNECTOR_NAME_TEMPLATE_VAR = "{connector_name}"


@dataclass(frozen=True)
class RenderedMcpToolApprovalParam:
    name: str
    value: Any
    display_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not isinstance(self.display_name, str):
            raise TypeError("display_name must be a string")


@dataclass(frozen=True)
class RenderedMcpToolApprovalTemplate:
    question: str
    elicitation_message: str
    tool_params: dict[str, Any] | None
    tool_params_display: tuple[RenderedMcpToolApprovalParam, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.question, str):
            raise TypeError("question must be a string")
        if not isinstance(self.elicitation_message, str):
            raise TypeError("elicitation_message must be a string")
        if self.tool_params is not None and not isinstance(self.tool_params, dict):
            raise TypeError("tool_params must be a dict or None")
        if isinstance(self.tool_params_display, (str, bytes)) or not isinstance(self.tool_params_display, Sequence):
            raise TypeError("tool_params_display must be a sequence")
        object.__setattr__(
            self,
            "tool_params_display",
            tuple(_rendered_param(param) for param in self.tool_params_display),
        )


@dataclass(frozen=True)
class ConsequentialToolTemplateParam:
    name: str
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not isinstance(self.label, str):
            raise TypeError("label must be a string")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConsequentialToolTemplateParam":
        if not isinstance(value, Mapping):
            raise TypeError("template param must be a mapping")
        return cls(name=_required_string(value, "name"), label=_required_string(value, "label"))


@dataclass(frozen=True)
class ConsequentialToolMessageTemplate:
    connector_id: str
    server_name: str
    tool_title: str
    template: str
    template_params: tuple[ConsequentialToolTemplateParam, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.connector_id, str):
            raise TypeError("connector_id must be a string")
        if not isinstance(self.server_name, str):
            raise TypeError("server_name must be a string")
        if not isinstance(self.tool_title, str):
            raise TypeError("tool_title must be a string")
        if not isinstance(self.template, str):
            raise TypeError("template must be a string")
        if isinstance(self.template_params, (str, bytes)) or not isinstance(self.template_params, Sequence):
            raise TypeError("template_params must be a sequence")
        object.__setattr__(
            self,
            "template_params",
            tuple(_template_param(param) for param in self.template_params),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConsequentialToolMessageTemplate":
        if not isinstance(value, Mapping):
            raise TypeError("message template must be a mapping")
        params = value.get("template_params")
        if isinstance(params, (str, bytes)) or not isinstance(params, Sequence):
            raise TypeError("template_params must be a sequence")
        return cls(
            connector_id=_required_string(value, "connector_id"),
            server_name=_required_string(value, "server_name"),
            tool_title=_required_string(value, "tool_title"),
            template=_required_string(value, "template"),
            template_params=tuple(ConsequentialToolTemplateParam.from_mapping(param) for param in params),
        )


def render_mcp_tool_approval_template(
    server_name: str,
    connector_id: str | None,
    connector_name: str | None,
    tool_title: str | None,
    tool_params: Mapping[str, Any] | None,
) -> RenderedMcpToolApprovalTemplate | None:
    templates = load_consequential_tool_message_templates()
    if templates is None:
        return None
    return render_mcp_tool_approval_template_from_templates(
        templates,
        server_name,
        connector_id,
        connector_name,
        tool_title,
        tool_params,
    )


@lru_cache(maxsize=1)
def load_consequential_tool_message_templates() -> tuple[ConsequentialToolMessageTemplate, ...] | None:
    path = _bundled_templates_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.warn(f"failed to parse consequential tool approval templates: {exc}", RuntimeWarning)
        return None

    try:
        schema_version = data["schema_version"]
        templates = data["templates"]
        if schema_version != CONSEQUENTIAL_TOOL_MESSAGE_TEMPLATES_SCHEMA_VERSION:
            warnings.warn(
                "unexpected consequential tool approval templates schema version",
                RuntimeWarning,
            )
            return None
        if isinstance(templates, (str, bytes)) or not isinstance(templates, Sequence):
            raise TypeError("templates must be a sequence")
        return tuple(ConsequentialToolMessageTemplate.from_mapping(template) for template in templates)
    except (KeyError, TypeError) as exc:
        warnings.warn(f"failed to parse consequential tool approval templates: {exc}", RuntimeWarning)
        return None


def render_mcp_tool_approval_template_from_templates(
    templates: Sequence[ConsequentialToolMessageTemplate],
    server_name: str,
    connector_id: str | None,
    connector_name: str | None,
    tool_title: str | None,
    tool_params: Mapping[str, Any] | None,
) -> RenderedMcpToolApprovalTemplate | None:
    if not isinstance(server_name, str):
        raise TypeError("server_name must be a string")
    if connector_id is not None and not isinstance(connector_id, str):
        raise TypeError("connector_id must be a string or None")
    if connector_name is not None and not isinstance(connector_name, str):
        raise TypeError("connector_name must be a string or None")
    if tool_title is not None and not isinstance(tool_title, str):
        raise TypeError("tool_title must be a string or None")
    if connector_id is None:
        return None
    title = tool_title.strip() if tool_title is not None else ""
    if not title:
        return None

    template = next(
        (
            item
            for item in _templates(templates)
            if item.server_name == server_name and item.connector_id == connector_id and item.tool_title == title
        ),
        None,
    )
    if template is None:
        return None

    elicitation_message = render_question_template(template.template, connector_name)
    if elicitation_message is None:
        return None

    if tool_params is None:
        rendered_params = None
        display_params: tuple[RenderedMcpToolApprovalParam, ...] = ()
    elif isinstance(tool_params, Mapping):
        rendered = render_tool_params(tool_params, template.template_params)
        if rendered is None:
            return None
        rendered_params, display_params = rendered
    else:
        return None

    return RenderedMcpToolApprovalTemplate(
        question=elicitation_message,
        elicitation_message=elicitation_message,
        tool_params=rendered_params,
        tool_params_display=display_params,
    )


def render_question_template(template: str, connector_name: str | None) -> str | None:
    if not isinstance(template, str):
        raise TypeError("template must be a string")
    if connector_name is not None and not isinstance(connector_name, str):
        raise TypeError("connector_name must be a string or None")
    trimmed = template.strip()
    if not trimmed:
        return None
    if CONNECTOR_NAME_TEMPLATE_VAR in trimmed:
        name = connector_name.strip() if connector_name is not None else ""
        if not name:
            return None
        return trimmed.replace(CONNECTOR_NAME_TEMPLATE_VAR, name)
    return trimmed


def render_tool_params(
    tool_params: Mapping[str, Any],
    template_params: Sequence[ConsequentialToolTemplateParam],
) -> tuple[dict[str, Any], tuple[RenderedMcpToolApprovalParam, ...]] | None:
    if not isinstance(tool_params, Mapping):
        raise TypeError("tool_params must be a mapping")
    display_params: list[RenderedMcpToolApprovalParam] = []
    display_names: set[str] = set()
    handled_names: set[str] = set()
    params = dict(tool_params)

    for template_param in (_template_param(param) for param in template_params):
        label = template_param.label.strip()
        if not label:
            return None
        if template_param.name not in params:
            continue
        if label in display_names:
            return None
        display_names.add(label)
        display_params.append(
            RenderedMcpToolApprovalParam(
                name=template_param.name,
                value=params[template_param.name],
                display_name=label,
            )
        )
        handled_names.add(template_param.name)

    for name in sorted(params):
        if not isinstance(name, str):
            raise TypeError("tool parameter names must be strings")
        if name in handled_names:
            continue
        if name in display_names:
            return None
        display_names.add(name)
        display_params.append(RenderedMcpToolApprovalParam(name=name, value=params[name], display_name=name))

    return params, tuple(display_params)


def _bundled_templates_path() -> Path:
    return Path(__file__).resolve().parents[2] / "codex" / "codex-rs" / "core" / "src" / "consequential_tool_message_templates.json"


def _templates(value: Sequence[ConsequentialToolMessageTemplate]) -> tuple[ConsequentialToolMessageTemplate, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("templates must be a sequence")
    return tuple(_template(template) for template in value)


def _template(value: ConsequentialToolMessageTemplate | Mapping[str, Any]) -> ConsequentialToolMessageTemplate:
    if isinstance(value, ConsequentialToolMessageTemplate):
        return value
    if isinstance(value, Mapping):
        return ConsequentialToolMessageTemplate.from_mapping(value)
    raise TypeError("templates must contain ConsequentialToolMessageTemplate values")


def _template_param(value: ConsequentialToolTemplateParam | Mapping[str, Any]) -> ConsequentialToolTemplateParam:
    if isinstance(value, ConsequentialToolTemplateParam):
        return value
    if isinstance(value, Mapping):
        return ConsequentialToolTemplateParam.from_mapping(value)
    raise TypeError("template_params must contain ConsequentialToolTemplateParam values")


def _rendered_param(value: RenderedMcpToolApprovalParam | Mapping[str, Any]) -> RenderedMcpToolApprovalParam:
    if isinstance(value, RenderedMcpToolApprovalParam):
        return value
    if isinstance(value, Mapping):
        return RenderedMcpToolApprovalParam(
            name=_required_string(value, "name"),
            value=value.get("value"),
            display_name=_required_string(value, "display_name"),
        )
    raise TypeError("tool_params_display must contain RenderedMcpToolApprovalParam values")


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


__all__ = [
    "CONNECTOR_NAME_TEMPLATE_VAR",
    "CONSEQUENTIAL_TOOL_MESSAGE_TEMPLATES_SCHEMA_VERSION",
    "ConsequentialToolMessageTemplate",
    "ConsequentialToolTemplateParam",
    "RenderedMcpToolApprovalParam",
    "RenderedMcpToolApprovalTemplate",
    "load_consequential_tool_message_templates",
    "render_mcp_tool_approval_template",
    "render_mcp_tool_approval_template_from_templates",
    "render_question_template",
    "render_tool_params",
]
