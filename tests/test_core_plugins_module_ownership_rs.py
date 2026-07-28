from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "pycodex" / "core_plugins"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_child_modules_have_continuous_python_owners() -> None:
    # Rust crate: codex-core-plugins. These source modules must not be flattened
    # into lib.rs's Python owner.
    for module in (
        "installed_marketplaces",
        "loader",
        "manager",
        "manifest",
        "marketplace",
        "toggles",
    ):
        assert (PACKAGE / f"{module}.py").is_file()
    assert (PACKAGE / "marketplace_upgrade" / "__init__.py").is_file()


def test_root_is_reexport_layer_not_manager_or_loader_owner() -> None:
    root_names = _defined_names(PACKAGE / "__init__.py")
    assert "PluginsManager" not in root_names
    assert "PluginHookSummary" not in root_names
    assert "_load_configured_plugin" not in root_names
    assert "LoadedPlugin" not in root_names
    assert "PluginLoadOutcome" not in root_names
