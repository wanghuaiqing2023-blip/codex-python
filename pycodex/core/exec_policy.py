"""Core exec-policy manager ported from ``codex-core``.

This module mirrors the core-side orchestration in
``codex/codex-rs/core/src/exec_policy.rs``.  The lower-level command
classification and approval helpers live in :mod:`pycodex.execpolicy`; this
file owns loading policy rule files, holding the current policy, appending
amendments, and producing ``ExecApprovalRequirement`` values from the current
policy.
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any

from pycodex.core.network_policy_decision import ExecPolicyNetworkRuleProtocol
from pycodex.execpolicy import Decision, PrefixRule
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PermissionProfile,
    SandboxPermissions,
)
from pycodex.shell_command import (
    command_might_be_dangerous,
    is_dangerous_powershell_words,
    is_known_safe_command,
    is_safe_powershell_words,
    parse_powershell_command_into_plain_commands,
    parse_shell_lc_plain_commands,
    parse_shell_lc_single_command_prefix,
)

RULES_DIR_NAME = "rules"
RULE_EXTENSION = "rules"
DEFAULT_POLICY_FILE = "default.rules"


@dataclass(frozen=True)
class ExecPolicyNetworkRule:
    host: str
    protocol: ExecPolicyNetworkRuleProtocol
    decision: Decision
    justification: str | None = None

    def __post_init__(self) -> None:
        host = normalize_network_rule_host(self.host)
        object.__setattr__(self, "host", host)
        if not isinstance(self.protocol, ExecPolicyNetworkRuleProtocol):
            object.__setattr__(self, "protocol", ExecPolicyNetworkRuleProtocol(str(self.protocol)))
        if not isinstance(self.decision, Decision):
            object.__setattr__(self, "decision", Decision(str(self.decision)))
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")
        if self.justification is not None and not self.justification.strip():
            raise ExecPolicyUpdateError("invalid network rule: justification cannot be empty")


@dataclass(frozen=True)
class ExecPolicy:
    prefix_rules: tuple[PrefixRule, ...] = ()
    network_rules: tuple[ExecPolicyNetworkRule, ...] = ()

    @classmethod
    def empty(cls) -> "ExecPolicy":
        return cls()

    def merge_overlay(self, overlay: "ExecPolicy | Mapping[str, Any] | None") -> "ExecPolicy":
        if overlay is None:
            return self
        overlay_policy = coerce_exec_policy(overlay)
        return ExecPolicy(
            prefix_rules=self.prefix_rules + overlay_policy.prefix_rules,
            network_rules=self.network_rules + overlay_policy.network_rules,
        )

    def add_prefix_rule(self, prefix: Sequence[str], decision: Decision | str = Decision.ALLOW) -> "ExecPolicy":
        return replace(
            self,
            prefix_rules=self.prefix_rules + (PrefixRule.new(tuple(prefix), Decision(str(decision))),),
        )

    def add_network_rule(
        self,
        host: str,
        protocol: ExecPolicyNetworkRuleProtocol | str,
        decision: Decision | str,
        justification: str | None = None,
    ) -> "ExecPolicy":
        return replace(
            self,
            network_rules=self.network_rules
            + (ExecPolicyNetworkRule(host, ExecPolicyNetworkRuleProtocol(str(protocol)), Decision(str(decision)), justification),),
        )

    def matches_for_command(self, command: Sequence[str]) -> tuple[Mapping[str, object], ...]:
        return match_exec_policy_rules_for_command(command, self.prefix_rules)


@dataclass(frozen=True)
class ExecPolicyError(Exception):
    kind: str
    message: str
    path: Path | None = None
    source: BaseException | None = None

    def __str__(self) -> str:
        if self.kind == "read_dir" and self.path is not None:
            return f"failed to read rules files from {self.path}: {self.message}"
        if self.kind == "read_file" and self.path is not None:
            return f"failed to read rules file {self.path}: {self.message}"
        if self.kind == "parse_policy" and self.path is not None:
            return f"failed to parse rules file {self.path}: {self.message}"
        return self.message


class ExecPolicyUpdateError(Exception):
    pass


@dataclass(frozen=True)
class ExecPolicyLoadResult:
    policy: ExecPolicy
    warning: ExecPolicyError | None = None


@dataclass(frozen=True)
class ExecPolicyConfigLayer:
    config_folder: Path
    source: str | None = None
    disabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.config_folder, Path):
            object.__setattr__(self, "config_folder", Path(self.config_folder))


@dataclass(frozen=True)
class ExecPolicyConfigStack:
    layers: tuple[ExecPolicyConfigLayer, ...] = ()
    ignore_user_and_project_exec_policy_rules: bool = False
    requirements_exec_policy: ExecPolicy | None = None

    @classmethod
    def from_object(cls, value: Any) -> "ExecPolicyConfigStack":
        if isinstance(value, ExecPolicyConfigStack):
            return value
        layers = tuple(_config_layers_from_object(value))
        ignore_rules = bool(_call_or_attr(value, "ignore_user_and_project_exec_policy_rules", False))
        requirements = _requirements_exec_policy_from_object(value)
        return cls(layers, ignore_rules, requirements)


class ExecPolicyManager:
    def __init__(self, policy: ExecPolicy | Mapping[str, Any] | None = None) -> None:
        self._policy = coerce_exec_policy(policy)
        self._update_lock = Lock()

    @classmethod
    async def load(cls, config_stack: Any) -> "ExecPolicyManager":
        result = await load_exec_policy_with_warning(config_stack)
        return cls(result.policy)

    def current(self) -> ExecPolicy:
        return self._policy

    async def create_exec_approval_requirement_for_command(
        self,
        request: ExecApprovalRequest | Mapping[str, object],
    ) -> Any:
        if not isinstance(request, ExecApprovalRequest):
            request = ExecApprovalRequest(**dict(request))  # type: ignore[arg-type]
        matches = self._policy.matches_for_command(request.command)
        return create_exec_approval_requirement_for_command(
            replace(request, matched_rules=request.matched_rules + matches)
        )

    async def append_amendment_and_update(self, codex_home: Path | str, amendment: ExecPolicyAmendment) -> None:
        prefix = tuple(str(item) for item in amendment.command)
        if not prefix:
            raise ExecPolicyUpdateError("prefix rule requires at least one token")
        policy_path = default_policy_path(codex_home)
        line = _format_prefix_rule(prefix, Decision.ALLOW)
        with self._update_lock:
            _append_unique_rule_line(policy_path, line)
            if not self._policy.matches_for_command(prefix):
                self._policy = self._policy.add_prefix_rule(prefix, Decision.ALLOW)

    async def append_network_rule_and_update(
        self,
        codex_home: Path | str,
        host: str,
        protocol: ExecPolicyNetworkRuleProtocol | str,
        decision: Decision | str,
        justification: str | None = None,
    ) -> None:
        network_rule = ExecPolicyNetworkRule(host, ExecPolicyNetworkRuleProtocol(str(protocol)), Decision(str(decision)), justification)
        policy_path = default_policy_path(codex_home)
        line = _format_network_rule(network_rule)
        with self._update_lock:
            _append_unique_rule_line(policy_path, line)
            self._policy = self._policy.add_network_rule(
                network_rule.host,
                network_rule.protocol,
                network_rule.decision,
                network_rule.justification,
            )


async def check_execpolicy_for_warnings(config_stack: Any) -> ExecPolicyError | None:
    return (await load_exec_policy_with_warning(config_stack)).warning


async def load_exec_policy_with_warning(config_stack: Any) -> ExecPolicyLoadResult:
    try:
        return ExecPolicyLoadResult(await load_exec_policy(config_stack), None)
    except ExecPolicyError as error:
        if error.kind == "parse_policy":
            return ExecPolicyLoadResult(ExecPolicy.empty(), error)
        raise


async def load_exec_policy(config_stack: Any) -> ExecPolicy:
    stack = ExecPolicyConfigStack.from_object(config_stack)
    policy = ExecPolicy.empty()
    for policy_path in _policy_paths_for_stack(stack):
        try:
            contents = policy_path.read_text(encoding="utf-8")
        except OSError as source:
            raise ExecPolicyError("read_file", str(source), policy_path, source) from source
        try:
            policy = policy.merge_overlay(_parse_policy_file(policy_path, contents))
        except ExecPolicyError:
            raise
        except Exception as source:
            raise ExecPolicyError("parse_policy", str(source), policy_path, source) from source
    return policy.merge_overlay(stack.requirements_exec_policy)


def child_uses_parent_exec_policy(parent_config: Any, child_config: Any) -> bool:
    parent = ExecPolicyConfigStack.from_object(parent_config)
    child = ExecPolicyConfigStack.from_object(child_config)
    return (
        tuple(layer.config_folder for layer in parent.layers) == tuple(layer.config_folder for layer in child.layers)
        and parent.ignore_user_and_project_exec_policy_rules == child.ignore_user_and_project_exec_policy_rules
        and parent.requirements_exec_policy == child.requirements_exec_policy
    )


def format_exec_policy_error_with_source(error: ExecPolicyError) -> str:
    if error.kind == "parse_policy" and error.path is not None:
        parsed = parse_starlark_line_from_message(error.message)
        if parsed is not None:
            path, line = parsed
            return f"{path}:{line}: {exec_policy_message_for_display(error.message)} (problem is on or around line {line})"
        return f"{error.path}: {exec_policy_message_for_display(error.message)}"
    return str(error)


def exec_policy_message_for_display(message: str | BaseException) -> str:
    text = str(message)
    for line in text.splitlines():
        if line.lstrip().startswith("error: "):
            return line
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    marker = ": starlark error: "
    if marker in first:
        return first.rsplit(marker, 1)[1].strip()
    return first


def parse_starlark_line_from_message(message: str) -> tuple[Path, int] | None:
    first = message.splitlines()[0].strip() if message.splitlines() else ""
    if ": starlark error:" not in first:
        return None
    path_and_position = first.rsplit(": starlark error:", 1)[0]
    parts = path_and_position.rsplit(":", 2)
    if len(parts) != 3:
        return None
    path, line, column = parts
    if not line.isdigit() or not column.isdigit() or int(line) == 0:
        return None
    return Path(path), int(line)


def default_policy_path(codex_home: Path | str) -> Path:
    return Path(codex_home).joinpath(RULES_DIR_NAME, DEFAULT_POLICY_FILE)


def collect_policy_files(directory: Path | str) -> tuple[Path, ...]:
    path = Path(directory)
    if not path.exists():
        return ()
    try:
        return tuple(sorted(item for item in path.iterdir() if item.is_file() and item.suffix == f".{RULE_EXTENSION}"))
    except OSError as source:
        raise ExecPolicyError("read_dir", str(source), path, source) from source


def coerce_exec_policy(value: ExecPolicy | Mapping[str, Any] | None) -> ExecPolicy:
    if value is None:
        return ExecPolicy.empty()
    if isinstance(value, ExecPolicy):
        return value
    prefix_rules = tuple(
        rule if isinstance(rule, PrefixRule) else PrefixRule.new(rule["pattern"], rule["decision"], rule.get("justification"))
        for rule in value.get("prefix_rules", ())
    )
    network_rules = tuple(
        rule
        if isinstance(rule, ExecPolicyNetworkRule)
        else ExecPolicyNetworkRule(rule["host"], rule["protocol"], rule["decision"], rule.get("justification"))
        for rule in value.get("network_rules", ())
    )
    return ExecPolicy(prefix_rules, network_rules)


def normalize_network_rule_host(raw: str) -> str:
    host = raw.strip()
    if not host:
        raise ExecPolicyUpdateError("invalid network rule: network_rule host cannot be empty")
    if "://" in host or "/" in host or "?" in host or "#" in host:
        raise ExecPolicyUpdateError("invalid network rule: network_rule host must be a hostname or IP literal (without scheme or path)")
    if host.startswith("["):
        if "]" not in host:
            raise ExecPolicyUpdateError("invalid network rule: network_rule host has an invalid bracketed IPv6 literal")
        inside, rest = host[1:].split("]", 1)
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            raise ExecPolicyUpdateError(f"invalid network rule: network_rule host contains an unsupported suffix: {raw}")
        host = inside
    elif host.count(":") == 1:
        candidate, port = host.rsplit(":", 1)
        if candidate and port.isdigit():
            host = candidate
    if "*" in host:
        raise ExecPolicyUpdateError("invalid network rule: network_rule host must be a specific host; wildcards are not allowed")
    return host.lower()


def _policy_paths_for_stack(stack: ExecPolicyConfigStack) -> tuple[Path, ...]:
    paths: list[Path] = []
    for layer in stack.layers:
        if layer.disabled:
            continue
        if stack.ignore_user_and_project_exec_policy_rules and layer.source in {"user", "project"}:
            continue
        paths.extend(collect_policy_files(layer.config_folder / RULES_DIR_NAME))
    return tuple(paths)


def _parse_policy_file(path: Path, contents: str) -> ExecPolicy:
    policy = ExecPolicy.empty()
    for line_number, raw_line in enumerate(contents.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if line.startswith("prefix_rule(") and line.endswith(")"):
                policy = policy.merge_overlay(ExecPolicy(prefix_rules=(_parse_prefix_rule(line),)))
                continue
            if line.startswith("network_rule(") and line.endswith(")"):
                policy = policy.merge_overlay(ExecPolicy(network_rules=(_parse_network_rule(line),)))
                continue
        except Exception as source:
            raise ExecPolicyError("parse_policy", f"{path}:{line_number}: starlark error: {source}", path, source) from source
        raise ExecPolicyError("parse_policy", f"{path}:{line_number}: starlark error: unsupported exec policy rule", path)
    return policy


def _parse_prefix_rule(line: str) -> PrefixRule:
    args = _parse_call_args(line, "prefix_rule")
    pattern = args.get("pattern")
    decision = args.get("decision")
    justification = args.get("justification")
    if pattern is None or decision is None:
        raise ValueError("prefix_rule requires pattern and decision")
    return PrefixRule.new(pattern, _decision_from_policy_string(str(decision)), justification if isinstance(justification, str) else None)


def _parse_network_rule(line: str) -> ExecPolicyNetworkRule:
    args = _parse_call_args(line, "network_rule")
    host = args.get("host")
    protocol = args.get("protocol")
    decision = args.get("decision")
    justification = args.get("justification")
    if host is None or protocol is None or decision is None:
        raise ValueError("network_rule requires host, protocol, and decision")
    return ExecPolicyNetworkRule(
        str(host),
        ExecPolicyNetworkRuleProtocol(str(protocol)),
        _decision_from_policy_string(str(decision)),
        justification if isinstance(justification, str) else None,
    )


def _parse_call_args(line: str, name: str) -> dict[str, Any]:
    source = re.sub(rf"^{name}\(", "dict(", line)
    try:
        value = ast.literal_eval(source)
    except Exception as source_error:
        raise ValueError(f"failed to parse {name}: {source_error}") from source_error
    if not isinstance(value, dict):
        raise ValueError(f"{name} did not produce keyword arguments")
    return value


def _format_prefix_rule(prefix: Sequence[str], decision: Decision) -> str:
    pattern = ", ".join(repr(str(token)) for token in prefix)
    return f"prefix_rule(pattern=[{pattern}], decision={_policy_decision_literal(decision)})"


def _format_network_rule(rule: ExecPolicyNetworkRule) -> str:
    args = [
        f"host={rule.host!r}",
        f"protocol={rule.protocol.value!r}",
        f"decision={_policy_decision_literal(rule.decision)}",
    ]
    if rule.justification is not None:
        args.append(f"justification={rule.justification!r}")
    return f"network_rule({', '.join(args)})"


def _append_unique_rule_line(policy_path: Path, line: str) -> None:
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    contents = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""
    if line in contents.splitlines():
        return
    prefix = "" if not contents or contents.endswith("\n") else "\n"
    with policy_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}{line}\n")


def _decision_from_policy_string(value: str) -> Decision:
    if value == "deny":
        return Decision.FORBIDDEN
    return Decision(value)


def _policy_decision_literal(decision: Decision) -> str:
    return repr("deny" if decision is Decision.FORBIDDEN else decision.value)


def _config_layers_from_object(value: Any) -> Iterable[ExecPolicyConfigLayer]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        raw_layers = value.get("layers", ())
    else:
        raw_layers = _call_or_attr(value, "layers", ())
        if not raw_layers:
            get_layers = getattr(value, "get_layers", None)
            raw_layers = get_layers() if callable(get_layers) else ()
    return tuple(_coerce_config_layer(layer) for layer in raw_layers)


def _coerce_config_layer(value: Any) -> ExecPolicyConfigLayer:
    if isinstance(value, ExecPolicyConfigLayer):
        return value
    if isinstance(value, Mapping):
        folder = value.get("config_folder") or value.get("folder")
        source = value.get("source") or value.get("name")
        disabled = bool(value.get("disabled", False))
    else:
        folder = _call_or_attr(value, "config_folder", None) or _call_or_attr(value, "folder", None)
        source = _call_or_attr(value, "source", None) or _call_or_attr(value, "name", None)
        disabled = bool(_call_or_attr(value, "disabled", False))
    if folder is None:
        raise TypeError("exec policy config layer requires config_folder")
    return ExecPolicyConfigLayer(Path(folder), _normalize_layer_source(source), disabled)


def _requirements_exec_policy_from_object(value: Any) -> ExecPolicy | None:
    if value is None:
        return None
    raw: Any
    if isinstance(value, Mapping):
        raw = value.get("requirements_exec_policy") or value.get("exec_policy")
    else:
        requirements = _call_or_attr(value, "requirements", None)
        raw = _call_or_attr(requirements, "exec_policy", None) if requirements is not None else None
        if raw is None:
            raw = _call_or_attr(value, "requirements_exec_policy", None) or _call_or_attr(value, "exec_policy", None)
    if raw is None:
        return None
    if hasattr(raw, "policy"):
        raw = getattr(raw, "policy")
    return coerce_exec_policy(raw)


def _normalize_layer_source(source: Any) -> str | None:
    if source is None:
        return None
    text = str(getattr(source, "value", source)).lower()
    if "user" in text:
        return "user"
    if "project" in text:
        return "project"
    return text


def _call_or_attr(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    attr = value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)
    return attr() if callable(attr) else attr


__all__ = [
    "DEFAULT_POLICY_FILE",
    "RULES_DIR_NAME",
    "RULE_EXTENSION",
    "Decision",
    "ExecApprovalRequest",
    "ExecPolicy",
    "ExecPolicyConfigLayer",
    "ExecPolicyConfigStack",
    "ExecPolicyError",
    "ExecPolicyLoadResult",
    "ExecPolicyManager",
    "ExecPolicyNetworkRule",
    "ExecPolicyNetworkRuleProtocol",
    "ExecPolicyUpdateError",
    "child_uses_parent_exec_policy",
    "check_execpolicy_for_warnings",
    "collect_policy_files",
    "default_policy_path",
    "exec_policy_message_for_display",
    "format_exec_policy_error_with_source",
    "load_exec_policy",
    "load_exec_policy_with_warning",
    "normalize_network_rule_host",
    "parse_starlark_line_from_message",
    "prompt_is_rejected_by_policy",
]

# Rust parity: codex-core/src/exec_policy.rs command decision surface
from pycodex.shell_command import (
    command_might_be_dangerous,
    is_dangerous_powershell_words,
    is_known_safe_command,
    is_safe_powershell_words,
    parse_powershell_command_into_plain_commands,
    parse_shell_lc_plain_commands,
    parse_shell_lc_single_command_prefix,
)

PROMPT_CONFLICT_REASON = "approval required by policy, but AskForApproval is set to Never"
REJECT_SANDBOX_APPROVAL_REASON = "approval required by policy, but AskForApproval::Granular.sandbox_approval is false"
REJECT_RULES_APPROVAL_REASON = "approval required by policy rule, but AskForApproval::Granular.rules is false"
BANNED_PREFIX_SUGGESTIONS = (
    ("python3",),
    ("python3", "-"),
    ("python3", "-c"),
    ("python",),
    ("python", "-"),
    ("python", "-c"),
    ("py",),
    ("py", "-3"),
    ("pythonw",),
    ("pyw",),
    ("pypy",),
    ("pypy3",),
    ("git",),
    ("bash",),
    ("bash", "-lc"),
    ("sh",),
    ("sh", "-c"),
    ("sh", "-lc"),
    ("zsh",),
    ("zsh", "-lc"),
    ("/bin/zsh",),
    ("/bin/zsh", "-lc"),
    ("/bin/bash",),
    ("/bin/bash", "-lc"),
    ("pwsh",),
    ("pwsh", "-Command"),
    ("pwsh", "-c"),
    ("powershell",),
    ("powershell", "-Command"),
    ("powershell", "-c"),
    ("powershell.exe",),
    ("powershell.exe", "-Command"),
    ("powershell.exe", "-c"),
    ("env",),
    ("sudo",),
    ("node",),
    ("node", "-e"),
    ("perl",),
    ("perl", "-e"),
    ("ruby",),
    ("ruby", "-e"),
    ("php",),
    ("php", "-r"),
    ("lua",),
    ("lua", "-e"),
    ("osascript",),
)

class ExecPolicyCommandOrigin(str, Enum):
    GENERIC = "generic"
    POWERSHELL = "powershell"


@dataclass(frozen=True)
class UnmatchedCommandContext:
    approval_policy: AskForApproval | GranularApprovalConfig
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    sandbox_cwd: Path
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    used_complex_parsing: bool = False
    command_origin: ExecPolicyCommandOrigin = ExecPolicyCommandOrigin.GENERIC

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        if not isinstance(self.command_origin, ExecPolicyCommandOrigin):
            object.__setattr__(self, "command_origin", ExecPolicyCommandOrigin(str(self.command_origin)))


@dataclass(frozen=True)
class ExecPolicyCommands:
    commands: tuple[tuple[str, ...], ...]
    used_complex_parsing: bool
    command_origin: ExecPolicyCommandOrigin


@dataclass(frozen=True)
class ExecApprovalRequest:
    command: tuple[str, ...]
    approval_policy: AskForApproval | GranularApprovalConfig
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    sandbox_cwd: Path
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    prefix_rule: tuple[str, ...] | None = None
    matched_rules: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _commands_tuple((self.command,))[0])
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be PermissionProfile")
        if not isinstance(self.file_system_sandbox_policy, FileSystemSandboxPolicy):
            raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.prefix_rule is not None:
            object.__setattr__(self, "prefix_rule", _commands_tuple((self.prefix_rule,))[0])
        object.__setattr__(self, "matched_rules", tuple(self.matched_rules))


def prompt_is_rejected_by_policy(
    approval_policy: AskForApproval | GranularApprovalConfig,
    prompt_is_rule: bool,
) -> str | None:
    if approval_policy is AskForApproval.NEVER:
        return PROMPT_CONFLICT_REASON
    if isinstance(approval_policy, GranularApprovalConfig):
        if prompt_is_rule:
            return None if approval_policy.allows_rules_approval() else REJECT_RULES_APPROVAL_REASON
        return None if approval_policy.allows_sandbox_approval() else REJECT_SANDBOX_APPROVAL_REASON
    return None


def commands_for_exec_policy(command: Sequence[str]) -> ExecPolicyCommands:
    argv = tuple(str(item) for item in command)

    plain_commands = parse_shell_lc_plain_commands(argv)
    if _has_nonempty_commands(plain_commands):
        return ExecPolicyCommands(_commands_tuple(plain_commands), False, ExecPolicyCommandOrigin.GENERIC)

    if os.name == "nt":
        powershell_commands = parse_powershell_command_into_plain_commands(argv)
        if _has_nonempty_commands(powershell_commands):
            return ExecPolicyCommands(_commands_tuple(powershell_commands), False, ExecPolicyCommandOrigin.POWERSHELL)

    single_command = parse_shell_lc_single_command_prefix(argv)
    if single_command is not None:
        return ExecPolicyCommands((tuple(single_command),), True, ExecPolicyCommandOrigin.GENERIC)

    return ExecPolicyCommands((argv,), False, ExecPolicyCommandOrigin.GENERIC)


def commands_for_intercepted_exec_policy(
    program: str | Path,
    argv: Sequence[str],
    *,
    enable_shell_wrapper_parsing: bool = True,
) -> ExecPolicyCommands:
    if enable_shell_wrapper_parsing:
        from pycodex.core.tools.runtimes import commands_for_intercepted_exec_policy as runtime_candidates

        candidate = runtime_candidates(program, tuple(str(item) for item in argv))
        return ExecPolicyCommands(candidate.commands, candidate.used_complex_parsing, ExecPolicyCommandOrigin.GENERIC)
    joined = (str(program), *tuple(str(item) for item in argv)[1:])
    return ExecPolicyCommands((joined,), False, ExecPolicyCommandOrigin.GENERIC)


def render_decisions_for_intercepted_exec_policy(
    program: str | Path,
    argv: Sequence[str],
    context: UnmatchedCommandContext,
    *,
    enable_shell_wrapper_parsing: bool,
) -> tuple[Decision, ...]:
    commands = commands_for_intercepted_exec_policy(
        program,
        argv,
        enable_shell_wrapper_parsing=enable_shell_wrapper_parsing,
    )
    fallback_context = UnmatchedCommandContext(
        approval_policy=context.approval_policy,
        permission_profile=context.permission_profile,
        file_system_sandbox_policy=context.file_system_sandbox_policy,
        sandbox_cwd=context.sandbox_cwd,
        sandbox_permissions=context.sandbox_permissions,
        used_complex_parsing=commands.used_complex_parsing,
        command_origin=ExecPolicyCommandOrigin.GENERIC,
    )
    return tuple(render_decision_for_unmatched_command(command, fallback_context) for command in commands.commands)


def strongest_decision(decisions: Sequence[Decision | str]) -> Decision:
    normalized = tuple(Decision(decision) for decision in decisions)
    if not normalized:
        raise ValueError("decisions must not be empty")
    return max(normalized)


def render_intercepted_exec_policy_decision(
    program: str | Path,
    argv: Sequence[str],
    context: UnmatchedCommandContext,
    *,
    enable_shell_wrapper_parsing: bool,
) -> Decision:
    return strongest_decision(
        render_decisions_for_intercepted_exec_policy(
            program,
            argv,
            context,
            enable_shell_wrapper_parsing=enable_shell_wrapper_parsing,
        )
    )


def exec_approval_requirement_for_decision(
    decision: Decision | str,
    *,
    forbidden_reason: str,
    prompt_reason: str | None = None,
) -> ExecApprovalRequirement:
    from pycodex.core.tools.sandboxing import ExecApprovalRequirement

    decision = Decision(decision)
    if decision is Decision.FORBIDDEN:
        return ExecApprovalRequirement.forbidden(forbidden_reason)
    if decision is Decision.PROMPT:
        return ExecApprovalRequirement.needs_approval(reason=prompt_reason)
    return ExecApprovalRequirement.skip()


def create_exec_approval_requirement_for_command(
    request: ExecApprovalRequest | Mapping[str, object],
) -> ExecApprovalRequirement:
    from pycodex.core.tools.sandboxing import ExecApprovalRequirement

    if not isinstance(request, ExecApprovalRequest):
        request = ExecApprovalRequest(**dict(request))  # type: ignore[arg-type]
    parsed = commands_for_exec_policy(request.command)
    auto_amendment_allowed = not parsed.used_complex_parsing
    fallback_context = UnmatchedCommandContext(
        approval_policy=request.approval_policy,
        permission_profile=request.permission_profile,
        file_system_sandbox_policy=request.file_system_sandbox_policy,
        sandbox_cwd=request.sandbox_cwd,
        sandbox_permissions=request.sandbox_permissions,
        used_complex_parsing=parsed.used_complex_parsing,
        command_origin=parsed.command_origin,
    )
    fallback_decisions = tuple(render_decision_for_unmatched_command(command, fallback_context) for command in parsed.commands)
    policy_decisions = tuple(
        decision
        for rule in request.matched_rules
        for decision in (_policy_match_decision(rule),)
        if decision is not None
    )
    decisions = fallback_decisions + policy_decisions
    decision = strongest_decision(decisions)
    requested_amendment = (
        derive_requested_execpolicy_amendment_from_prefix_rule(
            request.prefix_rule,
            request.matched_rules,
            parsed.commands,
        )
        if auto_amendment_allowed
        else None
    )

    if decision is Decision.FORBIDDEN:
        return ExecApprovalRequirement.forbidden(derive_forbidden_reason(request.command, request.matched_rules))
    if decision is Decision.PROMPT:
        prompt_is_rule = any(_policy_match_decision(rule) is Decision.PROMPT for rule in request.matched_rules)
        rejected_reason = prompt_is_rejected_by_policy(request.approval_policy, prompt_is_rule)
        if rejected_reason is not None:
            return ExecApprovalRequirement.forbidden(rejected_reason)
        proposed = requested_amendment
        if proposed is None and auto_amendment_allowed:
            proposed = _first_amendment_for_decision(parsed.commands, fallback_decisions, Decision.PROMPT)
        return ExecApprovalRequirement.needs_approval(
            reason=derive_prompt_reason(request.command, request.matched_rules),
            proposed_execpolicy_amendment=proposed,
        )

    proposed = None
    if auto_amendment_allowed:
        proposed = _try_derive_execpolicy_amendment_for_allow_rules(request.matched_rules)
    return ExecApprovalRequirement.skip(
        bypass_sandbox=_all_commands_explicitly_allowed_by_policy(parsed.commands, request.matched_rules),
        proposed_execpolicy_amendment=proposed,
    )


def match_exec_policy_rules_for_command(
    command: Sequence[str],
    rules: Sequence[object] = (),
) -> tuple[Mapping[str, object], ...]:
    """Return Rust-shaped prefix rule matches for a shell command."""

    if not rules:
        return ()
    parsed = commands_for_exec_policy(command)
    matches: list[Mapping[str, object]] = []
    seen: set[tuple[tuple[str, ...], str, str | None]] = set()
    for plain_command in parsed.commands:
        for rule in rules:
            match = _exec_policy_prefix_rule_match(rule, plain_command)
            if match is None:
                continue
            key = (
                _matched_prefix(match),
                str(match.get("decision")),
                match.get("justification") if isinstance(match.get("justification"), str) else None,
            )
            if key in seen:
                continue
            seen.add(key)
            matches.append({"prefixRuleMatch": dict(match)})
    return tuple(matches)


def derive_requested_execpolicy_amendment_from_prefix_rule(
    prefix_rule: Sequence[str] | None,
    matched_rules: Sequence[object] = (),
    commands: Sequence[Sequence[str]] | None = None,
) -> ExecPolicyAmendment | None:
    if prefix_rule is None:
        return None
    prefix = _commands_tuple((prefix_rule,))[0]
    if not prefix:
        return None
    if prefix in BANNED_PREFIX_SUGGESTIONS:
        return None
    if any(_is_policy_match(rule) for rule in matched_rules):
        return None
    candidate_commands = commands if commands is not None else (prefix,)
    if not prefix_rule_would_approve_all_commands(prefix, candidate_commands):
        return None
    return ExecPolicyAmendment.new(list(prefix))


def prefix_rule_would_approve_all_commands(
    prefix_rule: Sequence[str],
    commands: Sequence[Sequence[str]],
) -> bool:
    prefix = _commands_tuple((prefix_rule,))[0]
    if not prefix:
        return False
    command_tuples = _commands_tuple(commands)
    return all(_command_starts_with(command, prefix) for command in command_tuples)


def derive_prompt_reason(command: Sequence[str], matched_rules: Sequence[object]) -> str | None:
    prompt_matches = tuple(
        match
        for rule in matched_rules
        for match in (_prefix_rule_match(rule),)
        if match is not None and match.get("decision") == Decision.PROMPT.value
    )
    if not prompt_matches:
        return None
    match = max(prompt_matches, key=lambda item: len(_matched_prefix(item)))
    justification = match.get("justification")
    rendered = _render_command(command)
    if isinstance(justification, str) and justification:
        return f"`{rendered}` requires approval: {justification}"
    return f"`{rendered}` requires approval by policy"


def derive_forbidden_reason(command: Sequence[str], matched_rules: Sequence[object]) -> str:
    forbidden_matches = tuple(
        match
        for rule in matched_rules
        for match in (_prefix_rule_match(rule),)
        if match is not None and match.get("decision") == Decision.FORBIDDEN.value
    )
    rendered = _render_command(command)
    if not forbidden_matches:
        return f"`{rendered}` rejected: blocked by policy"
    match = max(forbidden_matches, key=lambda item: len(_matched_prefix(item)))
    justification = match.get("justification")
    if isinstance(justification, str) and justification:
        return f"`{rendered}` rejected: {justification}"
    prefix = _render_command(_matched_prefix(match))
    return f"`{rendered}` rejected: policy forbids commands starting with `{prefix}`"


def render_decision_for_unmatched_command(
    command: Sequence[str],
    context: UnmatchedCommandContext,
) -> Decision:
    argv = tuple(str(item) for item in command)
    if context.command_origin is ExecPolicyCommandOrigin.POWERSHELL:
        known_safe = is_safe_powershell_words(argv)
    else:
        known_safe = is_known_safe_command(argv)

    environment_lacks_sandbox_protections = (
        os.name == "nt"
        and profile_is_managed_read_only(
            context.permission_profile,
            context.file_system_sandbox_policy,
            context.sandbox_cwd,
        )
    )

    if known_safe and not context.used_complex_parsing and (
        context.approval_policy is AskForApproval.UNLESS_TRUSTED or environment_lacks_sandbox_protections
    ):
        return Decision.ALLOW

    if context.command_origin is ExecPolicyCommandOrigin.POWERSHELL:
        command_is_dangerous = is_dangerous_powershell_words(argv)
    else:
        command_is_dangerous = command_might_be_dangerous(argv)

    if command_is_dangerous or environment_lacks_sandbox_protections:
        if context.approval_policy is AskForApproval.NEVER:
            if context.permission_profile.type in {"disabled", "external"}:
                return Decision.ALLOW
            return Decision.FORBIDDEN
        return Decision.PROMPT

    if context.approval_policy in {AskForApproval.NEVER, AskForApproval.ON_FAILURE}:
        return Decision.ALLOW
    if context.approval_policy is AskForApproval.UNLESS_TRUSTED:
        return Decision.PROMPT

    if context.file_system_sandbox_policy.kind in {
        FileSystemSandboxKind.UNRESTRICTED,
        FileSystemSandboxKind.EXTERNAL_SANDBOX,
    }:
        return Decision.ALLOW
    if context.sandbox_permissions.requests_sandbox_override():
        return Decision.PROMPT
    return Decision.ALLOW


def profile_is_managed_read_only(
    permission_profile: PermissionProfile,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    sandbox_cwd: Path | str,
) -> bool:
    return (
        permission_profile.type == "managed"
        and file_system_sandbox_policy.kind is FileSystemSandboxKind.RESTRICTED
        and not file_system_sandbox_policy.has_full_disk_write_access()
        and len(file_system_sandbox_policy.get_writable_roots_with_cwd(sandbox_cwd)) == 0
    )


def _has_nonempty_commands(commands: list[list[str]] | None) -> bool:
    return commands is not None and bool(commands) and all(bool(item) for item in commands)


def _commands_tuple(commands: Sequence[Sequence[str]] | None) -> tuple[tuple[str, ...], ...]:
    if commands is None:
        return ()
    return tuple(tuple(str(item) for item in command) for command in commands)


def _prefix_rule_pattern_tuple(pattern: Sequence[str | Sequence[str]]) -> tuple[str | tuple[str, ...], ...]:
    if not isinstance(pattern, Sequence) or isinstance(pattern, (str, bytes)) or not pattern:
        raise ValueError("prefix rule pattern must be a non-empty sequence")
    parsed: list[str | tuple[str, ...]] = []
    for token in pattern:
        if isinstance(token, str):
            parsed.append(token)
            continue
        if isinstance(token, Sequence) and not isinstance(token, (str, bytes)) and token:
            alternatives = tuple(str(item) for item in token)
            if not all(alternatives):
                raise ValueError("prefix rule alternatives must be non-empty strings")
            parsed.append(alternatives)
            continue
        raise ValueError("prefix rule pattern tokens must be strings or non-empty string sequences")
    return tuple(parsed)


def _exec_policy_prefix_rule_match(rule: object, command: tuple[str, ...]) -> Mapping[str, object] | None:
    prefix_match = _prefix_rule_match(rule)
    if prefix_match is not None:
        prefix = _matched_prefix(prefix_match)
        if prefix and _command_starts_with(command, prefix):
            return prefix_match
        return None
    parsed = _prefix_rule_from_object(rule)
    if parsed is None:
        return None
    pattern, decision, justification = parsed
    prefix = _rule_pattern_matched_prefix(pattern, command)
    if prefix is None:
        return None
    match: dict[str, object] = {"matchedPrefix": list(prefix), "decision": decision.value}
    if justification:
        match["justification"] = justification
    return match


def _prefix_rule_from_object(rule: object) -> tuple[tuple[str | tuple[str, ...], ...], Decision, str | None] | None:
    if isinstance(rule, PrefixRule):
        return rule.pattern, rule.decision, rule.justification
    if isinstance(rule, Mapping):
        pattern = rule.get("pattern")
        decision = rule.get("decision")
        justification = rule.get("justification")
    else:
        pattern = getattr(rule, "pattern", None)
        decision = getattr(rule, "decision", None)
        justification = getattr(rule, "justification", None)
    if pattern is None or decision is None:
        return None
    try:
        parsed_pattern = _prefix_rule_pattern_tuple(pattern)  # type: ignore[arg-type]
        parsed_decision = Decision(str(getattr(decision, "value", decision)))
    except (TypeError, ValueError):
        return None
    parsed_justification = justification if isinstance(justification, str) and justification else None
    return parsed_pattern, parsed_decision, parsed_justification


def _rule_pattern_matched_prefix(
    pattern: tuple[str | tuple[str, ...], ...],
    command: tuple[str, ...],
) -> tuple[str, ...] | None:
    if len(command) < len(pattern):
        return None
    matched: list[str] = []
    for pattern_token, command_token in zip(pattern, command, strict=False):
        if isinstance(pattern_token, tuple):
            if command_token not in pattern_token:
                return None
            matched.append(command_token)
            continue
        if command_token != pattern_token:
            return None
        matched.append(command_token)
    return tuple(matched)


def _command_starts_with(command: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(command) >= len(prefix) and command[: len(prefix)] == prefix


def _is_policy_match(rule: object) -> bool:
    if _prefix_rule_match(rule) is not None:
        return True
    kind = getattr(rule, "kind", None) or getattr(rule, "type", None)
    if kind in {"prefix_rule", "PrefixRuleMatch", "prefixRuleMatch"}:
        return True
    return rule.__class__.__name__ in {"PrefixRuleMatch", "PrefixRule"}


def _policy_match_decision(rule: object) -> Decision | None:
    match = _prefix_rule_match(rule)
    if match is None:
        decision = getattr(rule, "decision", None)
    else:
        decision = match.get("decision")
    try:
        return Decision(str(decision))
    except ValueError:
        return None


def _prefix_rule_match(rule: object) -> Mapping[str, object] | None:
    if isinstance(rule, Mapping):
        for key in ("prefixRuleMatch", "prefix_rule_match"):
            value = rule.get(key)
            if isinstance(value, Mapping):
                return value
        kind = rule.get("kind") or rule.get("type") or rule.get("rule_type")
        if kind in {"prefix_rule", "PrefixRuleMatch", "prefixRuleMatch"}:
            return rule
    for attr in ("prefixRuleMatch", "prefix_rule_match"):
        value = getattr(rule, attr, None)
        if isinstance(value, Mapping):
            return value
    kind = getattr(rule, "kind", None) or getattr(rule, "type", None)
    if kind in {"prefix_rule", "PrefixRuleMatch", "prefixRuleMatch"}:
        return _object_policy_match_mapping(rule)
    return None


def _object_policy_match_mapping(rule: object) -> Mapping[str, object]:
    data: dict[str, object] = {}
    for attr in ("matchedPrefix", "matched_prefix", "decision", "justification"):
        value = getattr(rule, attr, None)
        if value is not None:
            data[attr] = value
    return data


def _matched_prefix(match: Mapping[str, object]) -> tuple[str, ...]:
    value = match.get("matchedPrefix")
    if value is None:
        value = match.get("matched_prefix")
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def _first_amendment_for_decision(
    commands: Sequence[Sequence[str]],
    decisions: Sequence[Decision],
    decision: Decision,
) -> ExecPolicyAmendment | None:
    for command, command_decision in zip(commands, decisions, strict=False):
        if command_decision is decision:
            return ExecPolicyAmendment.new(list(command))
    return None


def _all_commands_explicitly_allowed_by_policy(
    commands: Sequence[Sequence[str]],
    matched_rules: Sequence[object],
) -> bool:
    if not commands or not matched_rules:
        return False
    normalized_commands = tuple(tuple(str(part) for part in command) for command in commands)
    for command in normalized_commands:
        command_allowed = False
        for rule in matched_rules:
            match = _prefix_rule_match(rule)
            if match is None:
                continue
            if _policy_match_decision(rule) is not Decision.ALLOW:
                continue
            prefix = _matched_prefix(match)
            if prefix and _command_starts_with(command, prefix):
                command_allowed = True
                break
        if not command_allowed:
            return False
    return True


def _try_derive_execpolicy_amendment_for_allow_rules(
    matched_rules: Sequence[object],
) -> ExecPolicyAmendment | None:
    if any(_prefix_rule_match(rule) is not None for rule in matched_rules):
        return None
    for rule in matched_rules:
        if _policy_match_decision(rule) is not Decision.ALLOW:
            continue
        command = None
        if isinstance(rule, Mapping):
            command = rule.get("command")
        else:
            command = getattr(rule, "command", None)
        if command:
            return ExecPolicyAmendment.new([str(part) for part in command])
    return None


def _render_command(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)
