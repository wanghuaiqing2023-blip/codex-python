from __future__ import annotations

import ast
from pathlib import Path
import sys


ALLOWED_EXTERNAL_PREFIXES = (
    "pycodex",
    "tests",
)


TEST_PREFIX = Path(__file__).resolve().parent.parent / "pycodex"


class DependencyPolicyTests:
    def test_project_uses_only_stdlib_or_project_imports(self) -> None:
        stdlib_modules = set(sys.stdlib_module_names)
        stdlib_modules.add("__future__")

        violated: list[str] = []
        for path in sorted(TEST_PREFIX.glob("**/*.py")):
            if path.name == "__pycache__":
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".", 1)[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules = [node.module.split(".", 1)[0]]
                else:
                    continue

                for module in modules:
                    if module.startswith("_"):
                        continue
                    if module in stdlib_modules:
                        continue
                    if any(module.startswith(prefix) for prefix in ALLOWED_EXTERNAL_PREFIXES):
                        continue
                    violated.append(f"{module} imported in {path.relative_to(TEST_PREFIX.parent)}")

        assert not violated, "non-stdlib third-party imports found:\n" + "\n".join(violated)
