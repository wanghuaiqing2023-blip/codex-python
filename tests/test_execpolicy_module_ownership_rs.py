from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pycodex" / "execpolicy"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_execpolicy_rust_modules_have_unique_python_owners() -> None:
    expected = {
        "amend.py": {"AmendError", "blocking_append_allow_prefix_rule", "blocking_append_network_rule"},
        "decision.py": {"Decision"},
        "error.py": {"ExecPolicyError", "ErrorLocation", "TextPosition", "TextRange"},
        "execpolicycheck.py": {"ExecPolicyCheckCommand", "format_matches_json", "load_policies"},
        "executable_name.py": {"executable_lookup_key", "executable_path_lookup_key"},
        "main.py": {"Cli", "main", "parse_execpolicy_cli"},
        "parser.py": {"PolicyParser"},
        "policy.py": {"Evaluation", "MatchOptions", "Policy"},
        "rule.py": {"NetworkRuleProtocol", "PatternToken", "PrefixPattern", "PrefixRule", "RuleMatch"},
    }
    for relative, names in expected.items():
        path = PACKAGE / relative
        assert path.is_file(), f"missing Python owner for Rust module: {relative}"
        assert names <= _defined_names(path)


def test_execpolicy_crate_root_does_not_define_child_or_core_items() -> None:
    names = _defined_names(PACKAGE / "__init__.py")
    assert not names
