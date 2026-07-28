from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_MODULE = REPO_ROOT / "pycodex" / "uds" / "__init__.py"
PLATFORM_MODULE = REPO_ROOT / "pycodex" / "uds" / "platform.py"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def test_rust_inline_platform_module_has_one_python_owner() -> None:
    # Rust crate/module: codex-uds crate::platform in uds/src/lib.rs.
    assert PLATFORM_MODULE.is_file()
    platform_names = _defined_names(PLATFORM_MODULE)
    assert {"SOCKET_DIR_MODE", "SOCKET_DIR_PERMISSION_BITS"} <= platform_names


def test_root_owner_does_not_flatten_platform_or_test_helpers() -> None:
    # Rust crate/module: codex-uds crate; platform details stay in crate::platform,
    # while the Rust-only rendezvous helper belongs in the Python test itself.
    root_names = _defined_names(ROOT_MODULE)
    assert "SOCKET_DIR_MODE" not in root_names
    assert "SOCKET_DIR_PERMISSION_BITS" not in root_names
    assert "run_connected_pair" not in root_names
    assert "unix_socket_support_available" not in root_names
