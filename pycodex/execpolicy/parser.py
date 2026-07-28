"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .decision import Decision
from .error import InvalidExampleError, InvalidPatternError, InvalidRuleError
from .executable_name import executable_lookup_key, executable_path_lookup_key
from .policy import Policy
from .rule import NetworkRuleProtocol, PatternToken, PrefixPattern, PrefixRule, validate_match_examples, validate_not_match_examples

def _literal_string(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise InvalidRuleError(f"{context} must be a string")
    return value


def _literal_string_list(value: object, context: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InvalidRuleError(f"{context} must be a list of strings")
    return list(value)


def _parse_pattern_literal(value: object) -> tuple[PatternToken, ...]:
    if not isinstance(value, list):
        raise InvalidPatternError(f"pattern must be a list (got {type(value).__name__})")
    if not value:
        raise InvalidPatternError("pattern cannot be empty")
    tokens: list[PatternToken] = []
    for item in value:
        if isinstance(item, str):
            tokens.append(PatternToken.single(item))
        elif isinstance(item, list):
            if not item:
                raise InvalidPatternError("pattern alternatives cannot be empty")
            if not all(isinstance(alt, str) for alt in item):
                raise InvalidPatternError("pattern alternative must be a string")
            tokens.append(PatternToken.single(item[0]) if len(item) == 1 else PatternToken.alts(item))
        else:
            raise InvalidPatternError(
                f"pattern element must be a string or list of strings (got {type(item).__name__})"
            )
    return tuple(tokens)


def _parse_example_literal(value: object) -> list[str]:
    import shlex

    if isinstance(value, str):
        parsed = shlex.split(value)
        if not parsed:
            raise InvalidExampleError("example cannot be an empty string")
        return parsed
    if isinstance(value, list):
        if not value:
            raise InvalidExampleError("example cannot be an empty list")
        if not all(isinstance(item, str) for item in value):
            raise InvalidExampleError("example tokens must be strings")
        return list(value)
    raise InvalidExampleError(f"example must be a string or list of strings (got {type(value).__name__})")


def _parse_examples_literal(value: object | None) -> list[list[str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidExampleError("examples must be a list")
    return [_parse_example_literal(item) for item in value]


def _literal_eval_node(node: object) -> object:
    import ast

    try:
        return ast.literal_eval(node)
    except Exception as exc:
        raise InvalidRuleError("policy parser slice only supports literal arguments") from exc


def _parse_policy_source_to_calls(policy_identifier: str, policy_source: str) -> list[object]:
    import ast

    try:
        module = ast.parse(policy_source, filename=policy_identifier)
    except SyntaxError as exc:
        raise InvalidRuleError(str(exc)) from exc
    calls: list[object] = []
    for statement in module.body:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            raise InvalidRuleError("policy parser slice only supports top-level rule calls")
        calls.append(statement.value)
    return calls


def _call_keyword_map(call: object) -> dict[str, object]:
    keywords: dict[str, object] = {}
    for keyword in call.keywords:  # type: ignore[attr-defined]
        if keyword.arg is None:
            raise InvalidRuleError("policy rule calls do not support **kwargs")
        keywords[keyword.arg] = _literal_eval_node(keyword.value)
    if call.args:  # type: ignore[attr-defined]
        raise InvalidRuleError("policy rule calls require keyword arguments")
    return keywords


class PolicyParser:
    """Restricted Python parser for the common execpolicy Starlark subset."""

    def __init__(self) -> None:
        self._policy = Policy.empty()

    def parse(self, policy_identifier: str, policy_source: str) -> None:
        import ast

        for call in _parse_policy_source_to_calls(str(policy_identifier), str(policy_source)):
            name = call.func.id if isinstance(call.func, ast.Name) else None  # type: ignore[attr-defined]
            kwargs = _call_keyword_map(call)
            if name == "prefix_rule":
                self._parse_prefix_rule(kwargs)
            elif name == "network_rule":
                self._parse_network_rule(kwargs)
            elif name == "host_executable":
                raise NotImplementedError(
                    "codex-execpolicy host_executable parser support is tracked as a separate contract"
                )
            else:
                raise InvalidRuleError(f"unknown policy rule function: {name}")

    def _parse_prefix_rule(self, kwargs: Mapping[str, object]) -> None:
        pattern = _parse_pattern_literal(kwargs.get("pattern"))
        raw_decision = kwargs.get("decision", Decision.ALLOW.value)
        decision = Decision.parse(_literal_string(raw_decision, "decision"))
        raw_justification = kwargs.get("justification")
        justification = None
        if raw_justification is not None:
            justification = _literal_string(raw_justification, "justification")
            if not justification.strip():
                raise InvalidRuleError("justification cannot be empty")
        matches = _parse_examples_literal(kwargs.get("match"))
        not_matches = _parse_examples_literal(kwargs.get("not_match"))

        first, *rest = pattern
        rules: list[PrefixRule] = []
        for head in first.alternatives():
            rule = PrefixRule(
                pattern=PrefixPattern(first=head, rest=tuple(rest)),
                decision=decision,
                justification=justification,
            )
            self._policy._rules_by_program.setdefault(head, []).append(rule)
            rules.append(rule)
        validate_not_match_examples(self._policy, rules, not_matches)
        validate_match_examples(self._policy, rules, matches)

    def _parse_network_rule(self, kwargs: Mapping[str, object]) -> None:
        host = _literal_string(kwargs.get("host"), "host")
        protocol = NetworkRuleProtocol.parse(_literal_string(kwargs.get("protocol"), "protocol"))
        raw_decision = _literal_string(kwargs.get("decision"), "decision")
        decision = Decision.FORBIDDEN if raw_decision == "deny" else Decision.parse(raw_decision)
        justification_value = kwargs.get("justification")
        justification = None
        if justification_value is not None:
            justification = _literal_string(justification_value, "justification")
        self._policy.add_network_rule(host, protocol, decision, justification)

    def build(self) -> Policy:
        return self._policy

def _validate_host_executable_name(name: str) -> None:
    raw = str(name)
    if not raw:
        raise InvalidRuleError("host_executable name cannot be empty")
    if Path(raw).name != raw or any(separator in raw for separator in ("/", "\\")):
        raise InvalidRuleError(f"host_executable name must be a bare executable name (got {raw})")


def _parse_literal_absolute_path(raw: str) -> Path:
    path = Path(str(raw))
    if not path.is_absolute():
        raise InvalidRuleError(f"host_executable paths must be absolute (got {raw})")
    return path

_old_policy_parser_parse_prefix = PolicyParser._parse_prefix_rule
_old_policy_parser_parse_network = PolicyParser._parse_network_rule


def _policy_parser_parse(self: PolicyParser, policy_identifier: str, policy_source: str) -> None:
    import ast

    for call in _parse_policy_source_to_calls(str(policy_identifier), str(policy_source)):
        name = call.func.id if isinstance(call.func, ast.Name) else None  # type: ignore[attr-defined]
        kwargs = _call_keyword_map(call)
        if name == "prefix_rule":
            self._parse_prefix_rule(kwargs)
        elif name == "network_rule":
            self._parse_network_rule(kwargs)
        elif name == "host_executable":
            self._parse_host_executable(kwargs)
        else:
            raise InvalidRuleError(f"unknown policy rule function: {name}")


def _policy_parser_parse_host_executable(self: PolicyParser, kwargs: Mapping[str, object]) -> None:
    name = _literal_string(kwargs.get("name"), "name")
    _validate_host_executable_name(name)
    paths_value = kwargs.get("paths")
    paths = _literal_string_list(paths_value, "host_executable paths")
    parsed_paths: list[Path] = []
    lookup_name = executable_lookup_key(name)
    for raw in paths:
        path = _parse_literal_absolute_path(raw)
        path_name = executable_path_lookup_key(path)
        if path_name != lookup_name:
            raise InvalidRuleError(f"host_executable path `{raw}` must have basename `{name}`")
        if path not in parsed_paths:
            parsed_paths.append(path)
    self._policy.set_host_executable_paths(lookup_name, parsed_paths)


PolicyParser.parse = _policy_parser_parse  # type: ignore[method-assign]
PolicyParser._parse_host_executable = _policy_parser_parse_host_executable  # type: ignore[attr-defined]

__all__ = ['PolicyParser']
