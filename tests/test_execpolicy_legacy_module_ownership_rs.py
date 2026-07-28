from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pycodex" / "execpolicy_legacy"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_execpolicy_legacy_rust_modules_have_unique_python_owners() -> None:
    expected = {
        "arg_matcher.py": {"ArgMatcher", "ArgMatcherCardinality"},
        "arg_resolver.py": {"PositionalArg", "resolve_observed_args_with_patterns"},
        "arg_type.py": {"ArgType"},
        "error.py": {"Error"},
        "exec_call.py": {"ExecCall"},
        "execv_checker.py": {"ExecvChecker"},
        "main.py": {"ExecArg", "check_command", "main"},
        "opt.py": {"Opt", "OptMeta"},
        "policy.py": {"Policy"},
        "policy_parser.py": {"ForbiddenProgramRegex", "PolicyParser"},
        "program.py": {"Forbidden", "MatchedExec", "ProgramSpec"},
        "sed_command.py": {"parse_sed_command"},
        "valid_exec.py": {"MatchedArg", "MatchedFlag", "MatchedOpt", "ValidExec"},
    }
    for relative, names in expected.items():
        path = PACKAGE / relative
        assert path.is_file(), f"missing Python owner for Rust module: {relative}"
        assert names <= _defined_names(path)


def test_execpolicy_legacy_crate_root_only_defines_root_items() -> None:
    assert _defined_names(PACKAGE / "__init__.py") == {
        "_default_policy_path",
        "get_default_policy",
    }
