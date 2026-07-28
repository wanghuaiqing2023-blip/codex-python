from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pycodex" / "utils" / "stream_parser"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_stream_parser_rust_modules_have_unique_python_owners() -> None:
    expected = {
        "assistant_text.py": {"AssistantTextChunk", "AssistantTextStreamParser"},
        "citation.py": {"CitationStreamParser", "strip_citations"},
        "inline_hidden_tag.py": {
            "ExtractedInlineTag",
            "InlineHiddenTagParser",
            "InlineTagSpec",
        },
        "proposed_plan.py": {
            "ProposedPlanParser",
            "ProposedPlanSegment",
            "extract_proposed_plan_text",
            "strip_proposed_plan_blocks",
        },
        "stream_text.py": {"StreamTextChunk", "StreamTextParser"},
        "tagged_line_parser.py": {"TaggedLineParser"},
        "utf8_stream.py": {
            "Utf8StreamParser",
            "Utf8StreamParserError",
        },
    }
    for relative, names in expected.items():
        path = PACKAGE / relative
        assert path.is_file(), f"missing Python owner for Rust module: {relative}"
        assert names <= _defined_names(path)


def test_stream_parser_crate_root_only_reexports_rust_public_api() -> None:
    assert not _defined_names(PACKAGE / "__init__.py")
