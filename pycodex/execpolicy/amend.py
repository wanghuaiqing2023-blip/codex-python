"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from collections.abc import Sequence

from .error import InvalidRuleError
from .rule import NetworkRuleProtocol, normalize_network_rule_host

class AmendError(Exception):
    """Raised when appending an exec policy amendment fails."""

def _json_policy_string(value: str) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _append_rule_line(policy_path: object, line: str) -> None:
    from pathlib import Path

    path = Path(policy_path)
    parent = path.parent
    if str(parent) in ("", "."):
        raise AmendError(f"policy path has no parent: {path}")
    try:
        parent.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        raise AmendError(f"failed to create policy directory {parent}: {exc}") from exc

    try:
        contents = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise AmendError(f"failed to read policy file {path}: {exc}") from exc

    if any(existing == line for existing in contents.splitlines()):
        return

    try:
        with path.open("a", encoding="utf-8") as handle:
            if contents and not contents.endswith("\n"):
                handle.write("\n")
            handle.write(f"{line}\n")
    except OSError as exc:
        raise AmendError(f"failed to write to policy file {path}: {exc}") from exc


def blocking_append_allow_prefix_rule(policy_path: object, prefix: Sequence[str]) -> None:
    tokens = [str(token) for token in prefix]
    if not tokens:
        raise AmendError("prefix rule requires at least one token")
    pattern = "[" + ", ".join(_json_policy_string(token) for token in tokens) + "]"
    _append_rule_line(policy_path, f'prefix_rule(pattern={pattern}, decision="allow")')


def blocking_append_network_rule(
    policy_path: object,
    host: str,
    protocol: object,
    decision: object,
    justification: str | None = None,
) -> None:
    try:
        normalized_host = normalize_network_rule_host(host)
    except InvalidRuleError as exc:
        raise AmendError(f"invalid network rule: {exc}") from exc
    if justification is not None and not justification.strip():
        raise AmendError("invalid network rule: justification cannot be empty")

    parsed_protocol = protocol if isinstance(protocol, NetworkRuleProtocol) else NetworkRuleProtocol.parse(protocol)
    decision_value = getattr(decision, "value", decision)
    if decision_value == "forbidden":
        decision_text = "deny"
    elif decision_value in ("allow", "prompt"):
        decision_text = str(decision_value)
    else:
        raise AmendError(f"invalid network rule: unknown decision: {decision}")

    args = [
        f"host={_json_policy_string(normalized_host)}",
        f"protocol={_json_policy_string(parsed_protocol.as_policy_string())}",
        f"decision={_json_policy_string(decision_text)}",
    ]
    if justification is not None:
        args.append(f"justification={_json_policy_string(justification)}")
    _append_rule_line(policy_path, "network_rule(" + ", ".join(args) + ")")

__all__ = ['AmendError', 'blocking_append_allow_prefix_rule', 'blocking_append_network_rule']
