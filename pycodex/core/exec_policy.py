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
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Lock
from typing import Any

from pycodex.core.network_policy_decision import ExecPolicyNetworkRuleProtocol
from pycodex.execpolicy import (
    Decision,
    ExecApprovalRequest,
    ExecPolicyPrefixRule,
    create_exec_approval_requirement_for_command,
    match_exec_policy_rules_for_command,
    prompt_is_rejected_by_policy,
)
from pycodex.protocol import ExecPolicyAmendment

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
    prefix_rules: tuple[ExecPolicyPrefixRule, ...] = ()
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
            prefix_rules=self.prefix_rules + (ExecPolicyPrefixRule.new(tuple(prefix), Decision(str(decision))),),
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
        rule if isinstance(rule, ExecPolicyPrefixRule) else ExecPolicyPrefixRule.new(rule["pattern"], rule["decision"], rule.get("justification"))
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


def _parse_prefix_rule(line: str) -> ExecPolicyPrefixRule:
    args = _parse_call_args(line, "prefix_rule")
    pattern = args.get("pattern")
    decision = args.get("decision")
    justification = args.get("justification")
    if pattern is None or decision is None:
        raise ValueError("prefix_rule requires pattern and decision")
    return ExecPolicyPrefixRule.new(pattern, _decision_from_policy_string(str(decision)), justification if isinstance(justification, str) else None)


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
