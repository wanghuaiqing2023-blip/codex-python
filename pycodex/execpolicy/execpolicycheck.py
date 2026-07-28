"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path

from .parser import PolicyParser
from .policy import Policy
from .rule import RuleMatch

def _rule_match_to_json_object(rule: RuleMatch) -> dict[str, object]:
    if rule.kind == "prefixRuleMatch":
        payload: dict[str, object] = {
            "matchedPrefix": list(rule.matched_prefix),
            "decision": rule.decision.value,
        }
        if rule.resolved_program is not None:
            payload["resolvedProgram"] = rule.resolved_program
        if rule.justification is not None:
            payload["justification"] = rule.justification
        return {"prefixRuleMatch": payload}
    if rule.kind == "heuristicsRuleMatch":
        return {
            "heuristicsRuleMatch": {
                "command": list(rule.command),
                "decision": rule.decision.value,
            }
        }
    raise ValueError(f"unsupported rule match kind: {rule.kind}")


def format_matches_json(matched_rules: Sequence[RuleMatch], pretty: bool = False) -> str:
    import json

    rules = tuple(matched_rules)
    output: dict[str, object] = {"matchedRules": [_rule_match_to_json_object(rule) for rule in rules]}
    if rules:
        output["decision"] = max(rule.decision for rule in rules).value
    if pretty:
        return json.dumps(output, indent=2, ensure_ascii=False)
    return json.dumps(output, separators=(",", ":"), ensure_ascii=False)

@dataclass(frozen=True)
class ExecPolicyCheckCommand:
    rules: tuple[Path, ...]
    command: tuple[str, ...]
    pretty: bool = False
    resolve_host_executables: bool = False

    def __init__(
        self,
        rules: Sequence[object],
        command: Sequence[str],
        pretty: bool = False,
        resolve_host_executables: bool = False,
    ) -> None:
        object.__setattr__(self, "rules", tuple(Path(rule) for rule in rules))
        object.__setattr__(self, "command", tuple(str(token) for token in command))
        object.__setattr__(self, "pretty", bool(pretty))
        object.__setattr__(self, "resolve_host_executables", bool(resolve_host_executables))

    def run(self) -> str:
        policy = load_policies(self.rules)
        matched_rules = policy.matches_for_command(self.command, None)
        return format_matches_json(matched_rules, pretty=self.pretty)

def load_policies(policy_paths: Sequence[object]) -> Policy:
    parser = PolicyParser()
    for policy_path in policy_paths:
        path = Path(policy_path)
        try:
            contents = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OSError(f"failed to read policy at {path}: {exc}") from exc
        try:
            parser.parse(str(path), contents)
        except Exception as exc:
            if isinstance(exc, NotImplementedError):
                raise
            raise type(exc)(f"failed to parse policy at {path}: {exc}") from exc
    return parser.build()

__all__ = ['ExecPolicyCheckCommand', 'format_matches_json', 'load_policies']
