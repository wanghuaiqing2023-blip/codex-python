"""Configuration and tool schemas owned by ``codex_tool_config.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.exec.cli import ExecCli
from pycodex.exec.config_plan import (
    build_exec_config_bootstrap_plan,
    exec_session_config_from_bootstrap_plan,
)
from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping
from pycodex.protocol import AskForApproval, SandboxMode
from pycodex.utils.home_dir import find_codex_home


_PARAM_FIELDS = {
    "prompt",
    "model",
    "cwd",
    "approval-policy",
    "sandbox",
    "config",
    "base-instructions",
    "developer-instructions",
    "compact-prompt",
}
_REPLY_FIELDS = {"conversationId", "threadId", "prompt"}


class CodexToolCallApprovalPolicy(str, Enum):
    UNTRUSTED = "untrusted"
    ON_FAILURE = "on-failure"
    ON_REQUEST = "on-request"
    NEVER = "never"

    def to_protocol(self) -> AskForApproval:
        return {
            self.UNTRUSTED: AskForApproval.UNLESS_TRUSTED,
            self.ON_FAILURE: AskForApproval.ON_FAILURE,
            self.ON_REQUEST: AskForApproval.ON_REQUEST,
            self.NEVER: AskForApproval.NEVER,
        }[self]


class CodexToolCallSandboxMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"

    def to_protocol(self) -> SandboxMode:
        return SandboxMode(self.value)


@dataclass(frozen=True, slots=True)
class CodexToolCallParam:
    prompt: str
    model: str | None = None
    cwd: str | None = None
    approval_policy: str | None = None
    sandbox: str | None = None
    config: Mapping[str, Any] | None = None
    base_instructions: str | None = None
    developer_instructions: str | None = None
    compact_prompt: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CodexToolCallParam":
        data = _mapping(value, "Codex tool parameters")
        _reject_unknown(data, _PARAM_FIELDS)
        prompt = data.get("prompt")
        if not isinstance(prompt, str):
            raise ValueError("field `prompt` must be a string")
        approval_policy = _enum_value(
            data.get("approval-policy"),
            CodexToolCallApprovalPolicy,
            "approval-policy",
        )
        sandbox = _enum_value(data.get("sandbox"), CodexToolCallSandboxMode, "sandbox")
        config = data.get("config")
        if config is not None and not isinstance(config, Mapping):
            raise ValueError("field `config` must be an object")
        return cls(
            prompt=prompt,
            model=_optional_str(data, "model"),
            cwd=_optional_str(data, "cwd"),
            approval_policy=approval_policy,
            sandbox=sandbox,
            config=dict(config) if config is not None else None,
            base_instructions=_optional_str(data, "base-instructions"),
            developer_instructions=_optional_str(data, "developer-instructions"),
            compact_prompt=_optional_str(data, "compact-prompt"),
        )

    async def into_config(self) -> tuple[str, Any]:
        config_toml = read_toml_mapping(find_codex_home() / CONFIG_TOML_FILE)
        _merge_mapping(config_toml, self.config or {})
        if self.base_instructions is not None:
            config_toml["base_instructions"] = self.base_instructions
        if self.developer_instructions is not None:
            config_toml["developer_instructions"] = self.developer_instructions
        if self.compact_prompt is not None:
            config_toml["compact_prompt"] = self.compact_prompt
        cli = ExecCli(
            model=self.model,
            cwd=self.cwd,
            approval_policy=(
                CodexToolCallApprovalPolicy(self.approval_policy).to_protocol()
                if self.approval_policy is not None
                else None
            ),
            sandbox=(
                CodexToolCallSandboxMode(self.sandbox).to_protocol()
                if self.sandbox is not None
                else None
            ),
        )
        plan = build_exec_config_bootstrap_plan(
            cli,
            config_toml=config_toml,
            current_dir=Path.cwd(),
            interactive=True,
        )
        return self.prompt, exec_session_config_from_bootstrap_plan(plan)


@dataclass(frozen=True, slots=True)
class CodexToolCallReplyParam:
    prompt: str
    conversation_id: str | None = None
    thread_id: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CodexToolCallReplyParam":
        data = _mapping(value, "Codex reply parameters")
        _reject_unknown(data, _REPLY_FIELDS)
        prompt = data.get("prompt")
        if not isinstance(prompt, str):
            raise ValueError("field `prompt` must be a string")
        return cls(
            prompt=prompt,
            conversation_id=_optional_str(data, "conversationId"),
            thread_id=_optional_str(data, "threadId"),
        )

    def get_thread_id(self) -> str:
        value = self.thread_id or self.conversation_id
        if value is None:
            raise ValueError("either threadId or conversationId must be provided")
        return value


def create_tool_for_codex_tool_call_param() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "prompt": {"type": "string", "description": "The initial user prompt to start the Codex conversation."},
        "model": {"type": "string"},
        "cwd": {"type": "string"},
        "approval-policy": {
            "type": "string",
            "enum": [member.value for member in CodexToolCallApprovalPolicy],
        },
        "sandbox": {
            "type": "string",
            "enum": [member.value for member in CodexToolCallSandboxMode],
        },
        "config": {"type": "object", "additionalProperties": True},
        "base-instructions": {"type": "string"},
        "developer-instructions": {"type": "string"},
        "compact-prompt": {"type": "string"},
    }
    return _tool(
        "codex",
        "Codex",
        "Run a Codex session. Accepts configuration parameters matching the Codex Config struct.",
        {"type": "object", "properties": properties, "required": ["prompt"], "additionalProperties": False},
    )


def create_tool_for_codex_tool_call_reply_param() -> dict[str, Any]:
    return _tool(
        "codex-reply",
        "Codex Reply",
        "Continue a Codex conversation by providing the thread id and prompt.",
        {
            "type": "object",
            "properties": {
                "conversationId": {"type": "string"},
                "threadId": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["prompt"],
        },
    )


def _tool(name: str, title: str, description: str, input_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": {
            "type": "object",
            "properties": {"threadId": {"type": "string"}, "content": {"type": "string"}},
            "required": ["threadId", "content"],
        },
    }


def _mapping(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _reject_unknown(data: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = next((str(key) for key in data if key not in allowed), None)
    if unknown is not None:
        raise ValueError(f"unknown field `{unknown}`")


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"field `{key}` must be a string")
    return value


def _enum_value(value: Any, enum_type: type[Enum], key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field `{key}` must be a string")
    try:
        return str(enum_type(value).value)
    except ValueError as exc:
        expected = ", ".join(str(member.value) for member in enum_type)
        raise ValueError(f"field `{key}` must be one of: {expected}") from exc


def _merge_mapping(target: dict[str, Any], overrides: Mapping[str, Any]) -> None:
    for key, value in overrides.items():
        current = target.get(str(key))
        if isinstance(current, dict) and isinstance(value, Mapping):
            _merge_mapping(current, value)
        else:
            target[str(key)] = value
