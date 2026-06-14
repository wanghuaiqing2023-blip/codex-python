from pycodex.tui.bottom_pane.unified_exec_footer import FooterLine
from pycodex.tui.bottom_pane.unified_exec_footer import UnifiedExecFooter
from pycodex.tui.bottom_pane.unified_exec_footer import desired_height
from pycodex.tui.bottom_pane.unified_exec_footer import render


def test_new_empty_footer_has_no_summary_or_height():
    footer = UnifiedExecFooter.new()

    assert footer.is_empty()
    assert footer.summary_text() is None
    assert footer.desired_height(40) == 0
    assert desired_height(footer, 40) == 0
    assert footer.render_lines(40) == []


def test_set_processes_reports_only_real_changes_and_uses_copies():
    footer = UnifiedExecFooter.new()
    processes = ["rg foo src"]

    assert footer.set_processes(processes) is True
    assert footer.set_processes(["rg foo src"]) is False
    processes.append("cargo test")
    assert footer.processes == ["rg foo src"]
    assert footer.set_processes(processes) is True
    assert footer.processes == ["rg foo src", "cargo test"]


def test_summary_text_uses_singular_and_plural_grammar():
    footer = UnifiedExecFooter.new()

    footer.set_processes(["cmd 1"])
    assert footer.summary_text() == "1 background terminal running 路 /ps to view 路 /stop to close"

    footer.set_processes(["cmd 1", "cmd 2"])
    assert footer.summary_text() == "2 background terminals running 路 /ps to view 路 /stop to close"


def test_render_lines_width_boundaries_and_dim_semantics():
    footer = UnifiedExecFooter.new()
    footer.set_processes(["rg foo src"])

    assert footer.render_lines(3) == []
    assert footer.render_lines(4) == [FooterLine("  1 ", dim=True)]

    line = footer.render_lines(50)[0]
    assert line.dim is True
    assert line.text == "  1 background terminal running 路 /ps to view "


def test_many_sessions_summary_is_count_based_not_command_based():
    footer = UnifiedExecFooter.new()
    footer.set_processes([f"cmd {idx}" for idx in range(123)])

    line = footer.render_lines(80)[0]
    assert line.text.startswith("  123 background terminals running")
    assert "cmd 122" not in line.text


def test_render_clips_to_area_and_accepts_area_shapes():
    footer = UnifiedExecFooter.new()
    footer.set_processes(["rg foo src"])

    assert render(footer, {"width": 0, "height": 1}) == []
    assert render(footer, {"width": 50, "height": 0}) == []
    assert render(footer, (0, 0, 50, 1))[0].text.startswith("  1 background")
