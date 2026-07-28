from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pycodex" / "ext" / "memories"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_memories_extension_rust_modules_have_unique_python_owners() -> None:
    expected = {
        "backend.py": {"MemoriesBackend", "MemoryEntry", "MemoriesBackendError"},
        "extension.py": {"MemoriesExtension", "MemoriesExtensionConfig", "install"},
        "local/__init__.py": {"LocalMemoriesBackend"},
        "local/ad_hoc_note.py": {"validate_filename"},
        "local/list.py": set(),
        "local/path.py": {"display_relative_path", "reject_symlink"},
        "local/read.py": {"line_end_byte_offset", "line_start_byte_offset"},
        "local/search.py": {"SearchComparison", "SearchMatcher", "build_search_match"},
        "metrics.py": {"record_tool_call", "scope_from_path"},
        "prompts.py": {"parse_embedded_template"},
        "schema.py": {"input_schema_for", "output_schema_for", "schema_for"},
        "tools/__init__.py": {"memory_tools"},
        "tools/ad_hoc_note.py": {"AddAdHocNoteArgs", "AddAdHocNoteTool"},
        "tools/list.py": {"ListArgs", "ListTool"},
        "tools/read.py": {"ReadArgs", "ReadTool"},
        "tools/search.py": {"SearchArgs", "SearchTool"},
    }
    for relative, names in expected.items():
        path = PACKAGE / relative
        assert path.is_file(), f"missing Python owner for Rust module: {relative}"
        assert names <= _defined_names(path)


def test_memories_extension_crate_root_only_reexports_install() -> None:
    assert not _defined_names(PACKAGE / "__init__.py")
