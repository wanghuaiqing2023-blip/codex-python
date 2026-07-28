from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pycodex" / "utils" / "cli"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_utils_cli_rust_modules_have_unique_python_owners() -> None:
    expected = {
        "approval_mode_cli_arg.py": {"ApprovalModeCliArg"},
        "config_override.py": {
            "CliConfigOverrides",
            "apply_single_override",
            "canonicalize_override_key",
        },
        "format_env_display.py": {"format_env_display"},
        "resume_command.py": {"resume_command", "resume_hint"},
        "sandbox_mode_cli_arg.py": {"SandboxModeCliArg"},
        "shared_options.py": {"SharedCliOptions"},
    }
    for relative, names in expected.items():
        path = PACKAGE / relative
        assert path.is_file(), f"missing Python owner for Rust module: {relative}"
        assert names <= _defined_names(path)


def test_utils_cli_crate_root_only_reexports_rust_public_api() -> None:
    assert not _defined_names(PACKAGE / "__init__.py")


def test_legacy_duplicate_package_is_removed() -> None:
    legacy = ROOT / "pycodex" / "utils_cli"
    assert not list(legacy.glob("*.py"))
