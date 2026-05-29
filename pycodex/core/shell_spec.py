"""Shell tool specs ported from Codex core."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class CommandToolOptions:
    allow_login_shell: bool
    exec_permission_approvals_enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.allow_login_shell, bool):
            raise TypeError("allow_login_shell must be a bool")
        if not isinstance(self.exec_permission_approvals_enabled, bool):
            raise TypeError("exec_permission_approvals_enabled must be a bool")


def create_exec_command_tool(options: CommandToolOptions) -> dict[str, JsonValue]:
    return create_exec_command_tool_with_environment_id(options, include_environment_id=False)


def create_exec_command_tool_with_environment_id(
    options: CommandToolOptions,
    include_environment_id: bool,
) -> dict[str, JsonValue]:
    if not isinstance(options, CommandToolOptions):
        raise TypeError("options must be CommandToolOptions")
    if not isinstance(include_environment_id, bool):
        raise TypeError("include_environment_id must be a bool")
    properties = {
        "cmd": {"type": "string", "description": "Shell command to execute."},
        "workdir": {
            "type": "string",
            "description": "Optional working directory to run the command in; defaults to the turn cwd.",
        },
        "shell": {
            "type": "string",
            "description": "Shell binary to launch. Defaults to the user's default shell.",
        },
        "tty": {
            "type": "boolean",
            "description": "Whether to allocate a TTY for the command. Defaults to false (plain pipes); set to true to open a PTY and access TTY process.",
        },
        "yield_time_ms": {
            "type": "number",
            "description": "How long to wait (in milliseconds) for output before yielding.",
        },
        "max_output_tokens": {
            "type": "number",
            "description": "Maximum number of tokens to return. Excess output will be truncated.",
        },
    }
    if options.allow_login_shell:
        properties["login"] = {
            "type": "boolean",
            "description": "Whether to run the shell with -l/-i semantics. Defaults to true.",
        }
    if include_environment_id:
        properties["environment_id"] = {
            "type": "string",
            "description": "Optional environment id from the <environment_context> block. If omitted, uses the primary environment.",
        }
    properties.update(create_approval_parameters(options.exec_permission_approvals_enabled))
    description = "Runs a command in a PTY, returning output or a session ID for ongoing interaction."
    if _is_windows():
        description = f"{description}\n\n{windows_shell_guidance()}"
    return _function_tool(
        "exec_command",
        description,
        properties,
        ["cmd"],
        output_schema=unified_exec_output_schema(),
    )


def create_write_stdin_tool() -> dict[str, JsonValue]:
    properties = {
        "session_id": {
            "type": "number",
            "description": "Identifier of the running unified exec session.",
        },
        "chars": {
            "type": "string",
            "description": "Bytes to write to stdin (may be empty to poll).",
        },
        "yield_time_ms": {
            "type": "number",
            "description": "How long to wait (in milliseconds) for output before yielding.",
        },
        "max_output_tokens": {
            "type": "number",
            "description": "Maximum number of tokens to return. Excess output will be truncated.",
        },
    }
    return _function_tool(
        "write_stdin",
        "Writes characters to an existing unified exec session and returns recent output.",
        properties,
        ["session_id"],
        output_schema=unified_exec_output_schema(),
    )


def create_shell_command_tool(options: CommandToolOptions) -> dict[str, JsonValue]:
    if not isinstance(options, CommandToolOptions):
        raise TypeError("options must be CommandToolOptions")
    properties = {
        "command": {
            "type": "string",
            "description": "The shell script to execute in the user's default shell",
        },
        "workdir": {
            "type": "string",
            "description": "The working directory to execute the command in",
        },
        "timeout_ms": {
            "type": "number",
            "description": "The timeout for the command in milliseconds",
        },
    }
    if options.allow_login_shell:
        properties["login"] = {
            "type": "boolean",
            "description": "Whether to run the shell with login shell semantics. Defaults to true.",
        }
    properties.update(create_approval_parameters(options.exec_permission_approvals_enabled))

    if _is_windows():
        description = (
            "Runs a Powershell command (Windows) and returns its output.\n\n"
            "Examples of valid command strings:\n\n"
            '- ls -a (show hidden): "Get-ChildItem -Force"\n'
            '- recursive find by name: "Get-ChildItem -Recurse -Filter *.py"\n'
            "- recursive grep: \"Get-ChildItem -Path C:\\\\myrepo -Recurse | Select-String -Pattern 'TODO' -CaseSensitive\"\n"
            '- ps aux | grep python: "Get-Process | Where-Object { $_.ProcessName -like \'*python*\' }"\n'
            '- setting an env var: "$env:FOO=\'bar\'; echo $env:FOO"\n'
            '- running an inline Python script: "@\'\\\\nprint(\'Hello, world!\')\\\\n\'@ | python -"\n\n'
            f"{windows_shell_guidance()}"
        )
    else:
        description = (
            "Runs a shell command and returns its output.\n"
            "- Always set the `workdir` param when using the shell_command function. Do not use `cd` unless absolutely necessary."
        )
    return _function_tool("shell_command", description, properties, ["command"])


def create_request_permissions_tool(description: str) -> dict[str, JsonValue]:
    if not isinstance(description, str):
        raise TypeError("description must be a string")
    return _function_tool(
        "request_permissions",
        description,
        {
            "reason": {
                "type": "string",
                "description": "Optional short explanation for why additional permissions are needed.",
            },
            "permissions": permission_profile_schema(),
        },
        ["permissions"],
    )


def request_permissions_tool_description() -> str:
    return (
        "Request additional filesystem or network permissions from the user and wait for the client to grant a subset "
        "of the requested permission profile. Granted permissions apply automatically to later shell-like commands in "
        "the current turn, or for the rest of the session if the client approves them at session scope."
    )


def unified_exec_output_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "chunk_id": {
                "type": "string",
                "description": "Chunk identifier included when the response reports one.",
            },
            "wall_time_seconds": {
                "type": "number",
                "description": "Elapsed wall time spent waiting for output in seconds.",
            },
            "exit_code": {
                "type": "number",
                "description": "Process exit code when the command finished during this call.",
            },
            "session_id": {
                "type": "number",
                "description": "Session identifier to pass to write_stdin when the process is still running.",
            },
            "original_token_count": {
                "type": "number",
                "description": "Approximate token count before output truncation.",
            },
            "output": {
                "type": "string",
                "description": "Command output text, possibly truncated.",
            },
        },
        "required": ["wall_time_seconds", "output"],
        "additionalProperties": False,
    }


def create_approval_parameters(exec_permission_approvals_enabled: bool) -> dict[str, JsonValue]:
    if not isinstance(exec_permission_approvals_enabled, bool):
        raise TypeError("exec_permission_approvals_enabled must be a bool")
    permissions_description = (
        'Sandbox permissions for the command. Use "with_additional_permissions" to request additional sandboxed '
        'filesystem or network permissions (preferred), or "require_escalated" to request running without sandbox '
        'restrictions; defaults to "use_default".'
        if exec_permission_approvals_enabled
        else 'Sandbox permissions for the command. Set to "require_escalated" to request running without sandbox restrictions; defaults to "use_default".'
    )
    properties: dict[str, JsonValue] = {
        "sandbox_permissions": {"type": "string", "description": permissions_description},
        "justification": {
            "type": "string",
            "description": (
                'Only set if sandbox_permissions is \\"require_escalated\\".\n'
                "                    Request approval from the user to run this command outside the sandbox.\n"
                "                    Phrased as a simple question that summarizes the purpose of the\n"
                "                    command as it relates to the task at hand - e.g. 'Do you want to\n"
                "                    fetch and pull the latest version of this git branch?'"
            ),
        },
        "prefix_rule": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Only specify when sandbox_permissions is `require_escalated`.\n"
                "                        Suggest a prefix command pattern that will allow you to fulfill similar requests from the user in the future.\n"
                '                        Should be a short but reasonable prefix, e.g. [\\"git\\", \\"pull\\"] or [\\"uv\\", \\"run\\"] or [\\"pytest\\"].'
            ),
        },
    }
    if exec_permission_approvals_enabled:
        properties["additional_permissions"] = permission_profile_schema()
    return properties


def permission_profile_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "network": network_permissions_schema(),
            "file_system": file_system_permissions_schema(),
        },
        "additionalProperties": False,
    }


def network_permissions_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "Set to true to request network access.",
            }
        },
        "additionalProperties": False,
    }


def file_system_permissions_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "read": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Absolute paths to grant read access to.",
            },
            "write": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Absolute paths to grant write access to.",
            },
        },
        "additionalProperties": False,
    }


def windows_shell_guidance() -> str:
    return (
        "Windows safety rules:\n"
        "- Do not compose destructive filesystem commands across shells. Do not enumerate paths in PowerShell and then pass them to `cmd /c`, batch builtins, or another shell for deletion or moving. Use one shell end-to-end, prefer native PowerShell cmdlets such as `Remove-Item` / `Move-Item` with `-LiteralPath`, and avoid string-built shell commands for file operations.\n"
        "- Before any recursive delete or move on Windows, verify the resolved absolute target paths stay within the intended workspace or explicitly named target directory. Never issue a recursive delete or move against a computed path if the final target has not been checked.\n"
        "- When using `Start-Process` to launch a background helper or service, pass `-WindowStyle Hidden` unless the user explicitly asked for a visible interactive window. Use visible windows only for interactive tools the user needs to see or control."
    )


def _function_tool(
    name: str,
    description: str,
    properties: dict[str, JsonValue],
    required: list[str],
    *,
    output_schema: JsonValue | None = None,
) -> dict[str, JsonValue]:
    tool: dict[str, JsonValue] = {
        "type": "function",
        "name": name,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }
    if output_schema is not None:
        tool["output_schema"] = output_schema
    return tool


def _is_windows() -> bool:
    return sys.platform.startswith("win")
