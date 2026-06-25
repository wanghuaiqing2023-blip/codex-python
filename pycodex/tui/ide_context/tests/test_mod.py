from pycodex.tui.ide_context import (
    ActiveFile,
    FileDescriptor,
    IdeContext,
    Position,
    Range,
    deserializes_existing_ide_context_shape,
)


def test_deserializes_existing_ide_context_shape_ignores_extra_fields() -> None:
    # Rust: codex-tui/src/ide_context.rs tests::deserializes_existing_ide_context_shape.
    value = {
        "activeFile": {
            "label": "lib.rs",
            "path": "src/lib.rs",
            "fsPath": "/repo/src/lib.rs",
            "selection": {
                "start": {"line": 1, "character": 2},
                "end": {"line": 3, "character": 4},
            },
            "activeSelectionContent": "selected",
            "selections": [],
        },
        "openTabs": [
            {
                "label": "main.rs",
                "path": "src/main.rs",
                "fsPath": "/repo/src/main.rs",
                "startLine": 2,
                "endLine": 10,
            }
        ],
        "processEnv": {"path": "/usr/bin"},
    }

    assert deserializes_existing_ide_context_shape(value) == IdeContext(
        active_file=ActiveFile(
            descriptor=FileDescriptor(label="lib.rs", path="src/lib.rs"),
            selection=Range(
                start=Position(line=1, character=2),
                end=Position(line=3, character=4),
            ),
            active_selection_content="selected",
            selections=(),
        ),
        open_tabs=(FileDescriptor(label="main.rs", path="src/main.rs"),),
    )
