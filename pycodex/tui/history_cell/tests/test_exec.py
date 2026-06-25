from pycodex.tui.history_cell.base import line_text
from pycodex.tui.history_cell.exec import (
    MAX_PROCESSES,
    UnifiedExecProcessDetails,
    new_unified_exec_interaction,
    new_unified_exec_processes_output,
)


def rendered(cell, width=80):
    return [line_text(line) for line in cell.display_lines(width)]


def raw(cell):
    return [line_text(line) for line in cell.raw_lines()]


def test_unified_exec_interaction_cell_renders_input_like_rust_transcript():
    # Rust: codex-tui history_cell::tests::unified_exec_interaction_cell_renders_input.
    cell = new_unified_exec_interaction("echo hello", "ls\npwd")

    assert rendered(cell) == [
        "→ Interacted with background terminal · echo hello",
        "  └ ls",
        "    pwd",
    ]
    assert raw(cell) == [
        "Interacted with background terminal: echo hello",
        "ls",
        "pwd",
    ]


def test_unified_exec_interaction_cell_renders_wait_like_rust_transcript():
    # Rust: codex-tui history_cell::tests::unified_exec_interaction_cell_renders_wait.
    cell = new_unified_exec_interaction(None, "")

    assert rendered(cell) == ["• Waited for background terminal"]
    assert raw(cell) == ["Waited for background terminal"]


def test_unified_exec_processes_output_empty_matches_ps_summary_shape():
    # Rust: codex-tui history_cell::tests::ps_output_empty_snapshot.
    cell = new_unified_exec_processes_output([])

    assert rendered(cell, 60) == [
        "/ps",
        "",
        "Background terminals",
        "",
        "  • No background terminals running.",
    ]


def test_unified_exec_processes_truncates_commands_chunks_and_remaining_count():
    processes = [
        UnifiedExecProcessDetails(
            command_display=f"cmd-{index}-" + ("x" * 120),
            recent_chunks=["chunk-" + ("y" * 80)] if index == 0 else [],
        )
        for index in range(MAX_PROCESSES + 2)
    ]

    lines = rendered(new_unified_exec_processes_output(processes), 32)

    assert lines[0] == "/ps"
    assert any(line.endswith(" [...]") for line in lines)
    assert "  • ... and 2 more running" in lines
    assert not any("cmd-16" in line for line in lines)


def test_unified_exec_processes_tiny_width_keeps_prefix_only():
    cell = new_unified_exec_processes_output(
        [UnifiedExecProcessDetails(command_display="long command", recent_chunks=["chunk"])]
    )

    lines = rendered(cell, 3)

    assert "  • " in lines
    assert "    → " in lines
