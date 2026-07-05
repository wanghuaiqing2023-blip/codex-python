from __future__ import annotations

from pathlib import Path

from pycodex.tui.tui_alignment import CRITICAL_TERMINAL_TUI_MODULES, TUI_ALIGNMENT_ENTRIES


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_terminal_tui_alignment_manifest_paths_exist() -> None:
    for entry in TUI_ALIGNMENT_ENTRIES:
        assert (REPO_ROOT / entry.python_module).exists(), entry.python_module
        assert entry.python_tests, entry.python_module

        for rust_source in entry.rust_sources:
            assert (REPO_ROOT / rust_source).exists(), rust_source
        for python_test in entry.python_tests:
            assert (REPO_ROOT / python_test).exists(), python_test

        for responsibility in entry.responsibilities:
            assert (REPO_ROOT / responsibility.rust_source).exists(), responsibility.rust_source
            for python_test in responsibility.python_tests:
                assert (REPO_ROOT / python_test).exists(), python_test


def test_terminal_tui_alignment_manifest_has_unique_python_modules() -> None:
    python_modules = [entry.python_module for entry in TUI_ALIGNMENT_ENTRIES]
    assert len(python_modules) == len(set(python_modules))


def test_terminal_tui_python_only_adapters_are_explicitly_mapped() -> None:
    adapter_entries = {entry.python_module: entry for entry in TUI_ALIGNMENT_ENTRIES if entry.role != "direct"}

    assert "pycodex/tui/tui/terminal_runtime.py" in adapter_entries
    assert "pycodex/tui/bottom_pane/terminal_surface.py" in adapter_entries

    for entry in adapter_entries.values():
        assert not entry.rust_modules
        assert not entry.rust_sources
        assert "No Rust file named" in entry.notes
        assert entry.responsibilities, entry.python_module


def test_terminal_tui_adapter_responsibilities_are_one_rust_owner_each() -> None:
    for entry in TUI_ALIGNMENT_ENTRIES:
        if entry.role == "direct":
            assert not entry.responsibilities
            continue

        covered_rust_modules = set()
        for responsibility in entry.responsibilities:
            covered_rust_modules.add(responsibility.rust_module)
            assert responsibility.python_tests
            assert responsibility.description
            assert (REPO_ROOT / responsibility.rust_source).exists(), responsibility.rust_source
            for python_test in responsibility.python_tests:
                assert python_test in entry.python_tests or (REPO_ROOT / python_test).exists(), python_test

        assert len(covered_rust_modules) == len(entry.responsibilities)


def test_terminal_tui_direct_entries_are_one_to_one_with_rust_modules() -> None:
    for entry in TUI_ALIGNMENT_ENTRIES:
        if entry.role != "direct":
            continue

        assert len(entry.rust_modules) == 1, entry.python_module
        assert len(entry.rust_sources) == 1, entry.python_module


def test_terminal_tui_critical_modules_are_manifested() -> None:
    expected = {
        "pycodex/tui/tui/event_stream.py",
        "pycodex/tui/tui/terminal_runtime.py",
        "pycodex/tui/bottom_pane/chat_composer.py",
        "pycodex/tui/bottom_pane/command_popup.py",
        "pycodex/tui/bottom_pane/slash_commands.py",
        "pycodex/tui/chatwidget/slash_dispatch.py",
        "pycodex/tui/chatwidget/model_popups.py",
        "pycodex/tui/bottom_pane/list_selection_view.py",
        "pycodex/tui/bottom_pane/terminal_surface.py",
        "pycodex/tui/app/resize_reflow.py",
        "pycodex/tui/custom_terminal.py",
        "pycodex/tui/insert_history.py",
    }

    assert expected <= CRITICAL_TERMINAL_TUI_MODULES
