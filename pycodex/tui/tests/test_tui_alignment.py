from __future__ import annotations

from pathlib import Path
import ast
import re
import subprocess

from pycodex.tui.tui_alignment import (
    CRITICAL_TERMINAL_TUI_MODULES,
    RUST_CODEX_BASELINE_COMMIT,
    TUI_ALIGNMENT_ENTRIES,
    TUI_MODULE_OWNERS,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_RUST_CODEX_BASELINE_COMMIT = "1c7832ffa37a3ab56f601497c00bfce120370bf9"


def test_terminal_tui_alignment_is_pinned_to_fixed_rust_commit() -> None:
    # Project contract: codex/ is an immutable behavior baseline. TUI parity
    # mappings must not silently follow another upstream commit.
    assert RUST_CODEX_BASELINE_COMMIT == EXPECTED_RUST_CODEX_BASELINE_COMMIT

    parent_gitlink = subprocess.check_output(
        ["git", "rev-parse", "HEAD:codex"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    checked_out_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT / "codex",
        text=True,
    ).strip()

    assert parent_gitlink == RUST_CODEX_BASELINE_COMMIT
    assert checked_out_commit == RUST_CODEX_BASELINE_COMMIT

    assert TUI_ALIGNMENT_ENTRIES
    assert TUI_MODULE_OWNERS
    for entry in TUI_ALIGNMENT_ENTRIES:
        assert entry.rust_commit == RUST_CODEX_BASELINE_COMMIT, entry.python_module
        for responsibility in entry.responsibilities:
            assert responsibility.rust_commit == RUST_CODEX_BASELINE_COMMIT, (
                entry.python_module,
                responsibility.name,
            )
    for owner in TUI_MODULE_OWNERS:
        assert owner.rust_commit == RUST_CODEX_BASELINE_COMMIT, owner.python_owner


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


def test_terminal_tui_module_owner_paths_exist() -> None:
    for owner in TUI_MODULE_OWNERS:
        assert owner.python_owner
        assert owner.implementation_files, owner.python_owner
        assert owner.python_tests, owner.python_owner
        assert (REPO_ROOT / owner.rust_source).exists(), owner.rust_source
        for implementation_file in owner.implementation_files:
            assert (REPO_ROOT / implementation_file).exists(), implementation_file
        for python_test in owner.python_tests:
            assert (REPO_ROOT / python_test).exists(), python_test


def test_terminal_tui_alignment_manifest_has_unique_python_modules() -> None:
    python_modules = [entry.python_module for entry in TUI_ALIGNMENT_ENTRIES]
    assert len(python_modules) == len(set(python_modules))


def test_terminal_tui_module_owner_groups_are_single_rust_boundaries() -> None:
    for owner in TUI_MODULE_OWNERS:
        assert owner.rust_module.startswith("codex-tui::"), owner.python_owner
        assert owner.rust_source.startswith("codex/codex-rs/tui/src/"), owner.python_owner
        assert len(set(owner.implementation_files)) == len(owner.implementation_files), owner.python_owner


def test_terminal_tui_python_only_adapters_are_explicitly_mapped() -> None:
    adapter_entries = {entry.python_module: entry for entry in TUI_ALIGNMENT_ENTRIES if entry.role != "direct"}

    assert "pycodex/tui/tui/terminal_runtime.py" in adapter_entries
    assert "pycodex/tui/bottom_pane/terminal_projection.py" in adapter_entries
    assert "pycodex/tui/bottom_pane/terminal_surface.py" not in adapter_entries

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


def test_terminal_projection_manifest_tracks_backend_metadata_projection() -> None:
    # Rust owner: custom_terminal consumes live-viewport backend metadata. The
    # terminal_projection adapter derives it from bottom-pane frames so
    # chatwidget.rendering remains the side-effect-free frame content owner.
    entry = next(
        entry
        for entry in TUI_ALIGNMENT_ENTRIES
        if entry.python_module == "pycodex/tui/bottom_pane/terminal_projection.py"
    )
    responsibility = next(
        responsibility
        for responsibility in entry.responsibilities
        if responsibility.rust_module == "codex-tui::custom_terminal"
    )

    assert responsibility.name == "live viewport request and backend metadata projection"
    assert "minimum visible row widths" in responsibility.description
    assert "intentional blank rows" in responsibility.description
    assert "zero-based ratatui cursor position" in responsibility.description


def test_terminal_controller_manifest_tracks_view_state_resize_reflow_boundary() -> None:
    # Rust owner: tui.rs owns inline viewport geometry and draw ordering. The
    # terminal controller only binds bottom-pane state into that owner.
    entry = next(
        entry
        for entry in TUI_ALIGNMENT_ENTRIES
        if entry.python_module == "pycodex/tui/bottom_pane/terminal_controller.py"
    )
    responsibility = next(
        responsibility
        for responsibility in entry.responsibilities
        if responsibility.name == "inline viewport bridge"
    )

    assert responsibility.rust_module == "codex-tui::tui"
    assert "bottom-pane owner state and cursor callbacks" in responsibility.description
    assert "viewport-cycle runner" in responsibility.description
    assert "desired-height draws" in responsibility.description
    assert "terminal-resize viewport updates" in responsibility.description
    assert "pre-insert scroll movement" in responsibility.description
    assert "prepare_history_insert" in responsibility.description
    assert "resize_reflow_replay" in responsibility.description
    assert "app::resize_reflow" in responsibility.description

    live_buffer_responsibility = next(
        responsibility
        for responsibility in entry.responsibilities
        if responsibility.name == "live buffer lifecycle invalidation"
    )
    assert live_buffer_responsibility.rust_module == "codex-tui::custom_terminal"
    assert "projection backend callbacks" in live_buffer_responsibility.description
    assert "constructing LiveViewportRenderer" in live_buffer_responsibility.description
    assert "resetting raw buffer state" in live_buffer_responsibility.description

    composer_responsibility = next(
        responsibility
        for responsibility in entry.responsibilities
        if responsibility.name == "composer popup key routing"
    )
    assert composer_responsibility.rust_module == "codex-tui::bottom_pane::chat_composer"
    assert "Synchronizes terminal-path composer draft text" in composer_responsibility.description
    assert "bottom_pane.view_stack's combined owner state" in composer_responsibility.description
    assert "does not expose draft state" in composer_responsibility.description
    assert "create active views directly" in composer_responsibility.description
    assert "Holds terminal-path draft text" not in composer_responsibility.description

    active_view_responsibility = next(
        responsibility
        for responsibility in entry.responsibilities
        if responsibility.name == "active bottom-pane view stack"
    )
    assert active_view_responsibility.rust_module == "codex-tui::bottom_pane::bottom_pane_view"
    assert "command-view factory and selection-event callbacks" in active_view_responsibility.description
    assert "bottom_pane.view_stack's owner boundary" in active_view_responsibility.description
    assert "delegates stack replacement" in active_view_responsibility.description


def test_terminal_tui_direct_entries_are_one_to_one_with_rust_modules() -> None:
    for entry in TUI_ALIGNMENT_ENTRIES:
        if entry.role != "direct":
            continue

        assert len(entry.rust_modules) == 1, entry.python_module
        assert len(entry.rust_sources) == 1, entry.python_module


def test_terminal_tui_critical_modules_are_manifested() -> None:
    expected = {
        "pycodex/tui/tui/__init__.py",
        "pycodex/tui/tui/event_stream.py",
        "pycodex/tui/ratatui_bridge/buffer.py",
        "pycodex/tui/ratatui_bridge/backend.py",
        "pycodex/tui/tui/terminal_runtime.py",
        "pycodex/tui/bottom_pane/chat_composer/__init__.py",
        "pycodex/tui/bottom_pane/chat_composer/attachment_state.py",
        "pycodex/tui/bottom_pane/chat_composer/draft_state.py",
        "pycodex/tui/bottom_pane/chat_composer/footer_state.py",
        "pycodex/tui/bottom_pane/chat_composer/history_search.py",
        "pycodex/tui/bottom_pane/chat_composer/popup_state.py",
        "pycodex/tui/bottom_pane/chat_composer/slash_input.py",
        "pycodex/tui/bottom_pane/command_popup.py",
        "pycodex/tui/bottom_pane/slash_commands.py",
        "pycodex/tui/chatwidget/slash_dispatch.py",
        "pycodex/tui/chatwidget/permission_popups.py",
        "pycodex/tui/chatwidget/permissions_menu.py",
        "pycodex/tui/chatwidget/model_popups.py",
        "pycodex/tui/chatwidget/rendering.py",
        "pycodex/tui/chatwidget/turn_runtime.py",
        "pycodex/tui/bottom_pane/list_selection_view.py",
        "pycodex/tui/bottom_pane/bottom_pane_view.py",
        "pycodex/tui/bottom_pane/view_stack.py",
        "pycodex/tui/bottom_pane/selection_popup_common.py",
        "pycodex/tui/bottom_pane/terminal_action.py",
        "pycodex/tui/bottom_pane/terminal_footprint.py",
        "pycodex/tui/chatwidget/status_surfaces.py",
        "pycodex/tui/status/card.py",
        "pycodex/tui/app/history_ui.py",
        "pycodex/tui/bottom_pane/terminal_projection.py",
        "pycodex/tui/bottom_pane/terminal_controller.py",
        "pycodex/tui/app/resize_reflow.py",
        "pycodex/tui/custom_terminal.py",
        "pycodex/tui/insert_history.py",
        "pycodex/tui/wrapping.py",
        "pycodex/tui/history_cell/base.py",
        "pycodex/tui/history_cell/approvals.py",
        "pycodex/tui/history_cell/messages.py",
        "pycodex/tui/history_cell/session.py",
    }

    assert expected <= CRITICAL_TERMINAL_TUI_MODULES


def test_terminal_tui_critical_modules_have_manifest_entries() -> None:
    manifest_modules = {entry.python_module for entry in TUI_ALIGNMENT_ENTRIES}

    assert CRITICAL_TERMINAL_TUI_MODULES <= manifest_modules


def test_terminal_tui_critical_modules_are_covered_by_module_owners() -> None:
    # Rust crate/module ownership is the acceptance unit.  File-level manifest
    # entries remain useful anchors, but every critical implementation file
    # must also sit under a module owner group so future refactors can split or
    # merge files without losing the Rust behavior boundary.
    owner_files = {
        implementation_file
        for owner in TUI_MODULE_OWNERS
        for implementation_file in owner.implementation_files
    }

    assert CRITICAL_TERMINAL_TUI_MODULES <= owner_files


def test_terminal_tui_no_stale_shadow_modules_for_manifested_packages() -> None:
    # Rust owner: project-level TUI alignment discipline.  If Python imports a
    # package, a sibling ``.py`` file with the same name is dead code that can
    # make the manifest point at a non-runtime implementation.
    for entry in TUI_ALIGNMENT_ENTRIES:
        module_path = REPO_ROOT / entry.python_module
        if module_path.name != "__init__.py":
            continue
        shadow_file = module_path.parent.with_suffix(".py")
        assert not shadow_file.exists(), shadow_file


def test_terminal_tui_no_tui_local_command_owner_shadow() -> None:
    # Rust owner: chatwidget::slash_dispatch owns slash/local command effect
    # categorization. codex-tui::tui may wire a dispatcher, but it must not
    # keep a parallel local-command parser in the tui package.
    assert not (REPO_ROOT / "pycodex/tui/tui/local_command.py").exists()
    assert not (REPO_ROOT / "pycodex/tui/tui/tests/test_local_command.py").exists()


def test_terminal_composer_editor_ownership_matches_rust_modules() -> None:
    # Rust sources: bottom_pane/chat_composer.rs, chat_composer/draft_state.rs,
    # and textarea.rs define ChatComposer -> DraftState -> TextArea/State.
    composer_source = (
        REPO_ROOT / "pycodex/tui/bottom_pane/chat_composer/__init__.py"
    ).read_text(encoding="utf-8-sig")
    draft_source = (
        REPO_ROOT / "pycodex/tui/bottom_pane/chat_composer/draft_state.py"
    ).read_text(encoding="utf-8-sig")
    view_source = (REPO_ROOT / "pycodex/tui/bottom_pane/view_stack.py").read_text(
        encoding="utf-8-sig"
    )
    controller_source = (
        REPO_ROOT / "pycodex/tui/bottom_pane/terminal_controller.py"
    ).read_text(encoding="utf-8-sig")
    runtime_source = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(
        encoding="utf-8-sig"
    )

    composer_tree = ast.parse(composer_source)
    draft_tree = ast.parse(draft_source)
    view_tree = ast.parse(view_source)
    composer_class = next(
        node for node in composer_tree.body if isinstance(node, ast.ClassDef) and node.name == "ChatComposer"
    )
    draft_class = next(
        node for node in draft_tree.body if isinstance(node, ast.ClassDef) and node.name == "DraftState"
    )
    view_class = next(
        node
        for node in view_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TerminalBottomPaneViewState"
    )

    composer_assignments = {
        node.targets[0].attr
        for node in ast.walk(composer_class)
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Attribute)
        and isinstance(node.targets[0].value, ast.Name)
        and node.targets[0].value.id == "self"
    }
    assert "draft" in composer_assignments
    assert "_text" not in composer_assignments
    assert "self.draft = DraftState.new()" in composer_source
    assert "self.draft.textarea.input(" in composer_source
    assert "cursor_pos_with_state(" in composer_source

    draft_fields = {
        node.target.id: ast.unparse(node.annotation)
        for node in draft_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert draft_fields["textarea"] == "TextArea"
    assert draft_fields["textarea_state"] == "TextAreaState"

    view_fields = {
        node.target.id
        for node in view_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert "composer" in view_fields
    assert view_fields.isdisjoint({"draft", "history", "command_popup_state", "cursor"})
    assert "def handle_composer_key(" not in view_source
    assert "def terminal_bottom_pane_handle_composer_key(" not in view_source
    assert "def terminal_composer_input_action(" not in composer_source
    assert "def terminal_composer_draft_after_" not in composer_source

    forbidden_editor_keys = tuple(
        f'"{key}"'
        for key in ("left", "right", "home", "end", "backspace", "delete", "ctrl-b", "ctrl-f")
    )
    for adapter_source in (controller_source, runtime_source):
        assert not any(key in adapter_source for key in forbidden_editor_keys)
    assert "def handle_composer_key(" not in controller_source
    assert "handle_key=" not in runtime_source
    assert "handle_active_input=" not in runtime_source
    assert "composer=self._bottom_pane.composer" in runtime_source
    assert "handle_event=self._handle_bottom_pane_composer_event" in runtime_source


def test_terminal_tui_deleted_runtime_adapters_do_not_return() -> None:
    # Rust owner: project-level terminal TUI module-owner alignment.  These
    # Python-only runtime layers were folded into Rust-owned module boundaries;
    # keeping them deleted prevents future fixes from recreating a parallel
    # scrollback/surface/frame architecture.
    deleted_paths = (
        "pycodex/tui/scrollback_runtime.py",
        "pycodex/tui/bottom_pane/terminal_surface.py",
        "pycodex/tui/bottom_pane/terminal_frame.py",
        "pycodex/tui/bottom_pane/tests/test_terminal_surface.py",
        "pycodex/tui/bottom_pane/tests/test_terminal_frame.py",
        "pycodex/tui/bottom_pane/tests/test_terminal_bottom_pane_adapter.py",
    )

    for deleted_path in deleted_paths:
        assert not (REPO_ROOT / deleted_path).exists(), deleted_path


def test_app_event_receive_and_drain_stay_in_app_module() -> None:
    # Fixed Rust commit 1c7832f:
    # - app_event_sender.rs only sends into UnboundedSender<AppEvent>;
    # - app.rs owns app_event_rx.recv() and App::handle_event;
    # - bottom_pane handles view input/completion without receiving AppEvents.
    app_source = (REPO_ROOT / "pycodex/tui/app/runtime.py").read_text(encoding="utf-8-sig")
    terminal_source = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(
        encoding="utf-8-sig"
    )
    controller_source = (
        REPO_ROOT / "pycodex/tui/bottom_pane/terminal_controller.py"
    ).read_text(encoding="utf-8-sig")
    app_tree = ast.parse(app_source)
    controller_tree = ast.parse(controller_source)
    controller_identifiers = {
        node.id
        for node in ast.walk(controller_tree)
        if isinstance(node, ast.Name)
    } | {
        node.attr
        for node in ast.walk(controller_tree)
        if isinstance(node, ast.Attribute)
    }

    app_runtime_class = next(
        node
        for node in app_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TuiAppRuntime"
    )
    app_runtime_methods = {
        node.name: node
        for node in app_runtime_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    loop_step = app_runtime_methods["run_app_event_loop_step"]
    assert "drain_app_events" in app_runtime_methods
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr == "drain_app_events"
        for node in ast.walk(loop_step)
    )
    assert "run_app_event_loop_step" in terminal_source
    assert ".drain_app_events(" not in terminal_source
    assert controller_identifiers.isdisjoint(
        {
            "app_event_sender",
            "pending_app_events",
            "drain_app_events",
            "_drain_app_events",
        }
    )


def test_app_event_sender_reuses_canonical_app_event_module() -> None:
    # Rust has one AppEvent enum in app_event.rs. app_event_sender.rs imports
    # it and must not define a shadow event type.
    sender_path = REPO_ROOT / "pycodex/tui/app_event_sender.py"
    sender_tree = ast.parse(sender_path.read_text(encoding="utf-8-sig"))

    assert not any(
        isinstance(node, ast.ClassDef) and node.name == "AppEvent"
        for node in sender_tree.body
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app_event"
        and any(alias.name == "AppEvent" for alias in node.names)
        for node in sender_tree.body
    )


def test_terminal_tui_product_sources_do_not_reintroduce_textual_path() -> None:
    # Rust owner: codex-tui terminal product path. This Python port no longer
    # maintains a Textual UI path; product TUI sources must keep using the
    # Rust-aligned terminal framework instead of reintroducing a parallel
    # runtime branch.
    forbidden_markers = (
        ("textual", re.compile(r"(?<![a-z0-9_])textual(?![a-z0-9_])")),
        ("textual_runtime", re.compile(r"textual_runtime")),
        ("run_textual", re.compile(r"run_textual")),
    )
    ignored_parts = {"tests", "__pycache__"}
    product_sources = [
        path
        for path in (REPO_ROOT / "pycodex/tui").rglob("*.py")
        if not ignored_parts.intersection(path.relative_to(REPO_ROOT / "pycodex/tui").parts)
    ]

    offenders: list[tuple[str, str]] = []
    for path in product_sources:
        source = path.read_text(encoding="utf-8-sig").lower()
        for marker, pattern in forbidden_markers:
            if pattern.search(source):
                offenders.append((str(path.relative_to(REPO_ROOT)), marker))

    assert offenders == []


def test_terminal_tui_manifest_tests_include_rust_evidence_comments() -> None:
    # Rust owner: this project-level guard enforces the TUI porting discipline
    # from AGENTS.md and pycodex/tui/tui_alignment.py. Manifested product-path
    # tests must name the Rust owner/source/behavior evidence they protect.
    evidence_markers = (
        "Rust owner:",
        "Rust owners:",
        "Rust crate",
        "Rust module",
        "Rust source:",
        "Rust sources:",
        "behavior contract",
        "Behavior contract",
    )
    manifested_tests = {
        python_test
        for entry in TUI_ALIGNMENT_ENTRIES
        for python_test in entry.python_tests
    } | {
        python_test
        for entry in TUI_ALIGNMENT_ENTRIES
        for responsibility in entry.responsibilities
        for python_test in responsibility.python_tests
    } | {
        python_test
        for owner in TUI_MODULE_OWNERS
        for python_test in owner.python_tests
    }

    for python_test in sorted(manifested_tests):
        source = (REPO_ROOT / python_test).read_text(encoding="utf-8-sig")
        assert any(marker in source for marker in evidence_markers), python_test


def test_terminal_product_path_contract_matrix_is_guarded() -> None:
    # Rust owners: tui::event_stream, bottom_pane::chat_composer,
    # command_popup, list_selection_view, chatwidget::model_popups,
    # chatwidget::status_surfaces, custom_terminal, insert_history, and
    # app::resize_reflow collectively define the real-terminal product path.
    # This guard makes the goal-level regression matrix explicit so future
    # refactors cannot silently drop one behavior category while preserving
    # unrelated green tests.
    runtime_tests = _test_function_names(REPO_ROOT / "pycodex/tui/tui/tests/test_terminal_runtime.py")
    chat_composer_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_chat_composer.py")
    slash_input_tests = _test_function_names(
        REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_chat_composer_slash_input.py"
    )
    view_stack_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_view_stack.py")
    controller_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_controller.py")
    projection_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_projection.py")

    required_runtime_tests = {
        "ascii_text_submit": "test_terminal_runtime_key_stream_submits_ascii_prompt",
        "middle_cursor_insert": "test_terminal_runtime_left_moves_real_composer_cursor_before_insertion",
        "ime_text_submit": "test_terminal_runtime_terminal_event_loop_submits_chinese_text_once",
        "slash_popup_filter_and_navigation": "test_terminal_runtime_slash_popup_renders_and_moves_selection",
        "model_picker": "test_terminal_runtime_model_command_opens_bottom_pane_selection_view",
        "model_reasoning_picker": "test_terminal_runtime_model_command_pushes_reasoning_selection_view",
        "reasoning_footer_update": "test_terminal_runtime_model_reasoning_text_enter_updates_footer_from_low_to_medium",
        "history_visible_during_stream": "test_terminal_runtime_keeps_user_prompt_visible_during_assistant_stream",
        "resize_history_single_copy": "test_terminal_runtime_grow_shrink_replay_has_single_transcript_copy",
        "footer_live_pane": "test_terminal_runtime_terminal_footer_is_live_not_history",
    }
    required_controller_tests = {
        "bottom_pane_viewport_resize_on_popup": "test_terminal_bottom_pane_controller_resizes_tui_viewport_for_active_view",
    }
    required_chat_composer_tests = {
        "popup_key_mapping": "test_terminal_popup_key_maps_rust_like_payloads",
        "popup_action_plan": "test_terminal_command_popup_input_action_plans_navigation_completion_and_command_view",
        "popup_state_sync": "test_terminal_command_popup_state_syncs_draft_and_hides_for_active_view",
        "popup_runner_completion_and_view": "test_terminal_command_popup_runner_applies_navigation_completion_and_model_view",
    }
    required_slash_input_tests = {
        "slash_command_name_editing": "test_terminal_draft_visibility_and_command_name_follow_slash_input_boundary",
    }
    required_view_stack_tests = {
        "child_selection_view_stack": "test_terminal_bottom_pane_view_state_pushes_child_selection_view_from_events",
        "text_enter_active_view": "test_terminal_bottom_pane_view_state_normalizes_text_enter_for_active_selection_view",
        "active_view_navigation": "test_bottom_pane_view_state_routes_active_view_before_command_popup",
    }
    required_projection_tests = {
        "bottom_pane_frame_diff": "test_terminal_projection_frame_update_diff_uses_custom_terminal_owner",
        "tui_viewport_clear_callback": "test_terminal_bottom_pane_request_runner_builds_tui_viewport_clear_callback",
        "tui_viewport_render_callback": "test_terminal_bottom_pane_request_runner_builds_tui_viewport_render_callback",
    }

    assert set(required_runtime_tests.values()) <= runtime_tests
    assert set(required_chat_composer_tests.values()) <= chat_composer_tests
    assert set(required_slash_input_tests.values()) <= slash_input_tests
    assert set(required_view_stack_tests.values()) <= view_stack_tests
    assert set(required_controller_tests.values()) <= controller_tests
    assert set(required_projection_tests.values()) <= projection_tests


def test_terminal_projection_owns_request_runner_without_surface_adapter() -> None:
    # Rust owners: bottom_pane owns request creation, chatwidget::rendering owns
    # frame/buffer content projection, and custom_terminal owns diff/flush
    # lifecycle. Python no longer keeps a separate terminal_surface layer; the
    # projection adapter may bind a bottom-pane request runner, but it must not
    # take over raw custom_terminal cycle execution.
    assert not (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_surface.py").exists()

    projection_path = REPO_ROOT / "pycodex/tui/bottom_pane/terminal_projection.py"
    source = projection_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    exported = _literal_all(tree)

    forbidden_lifecycle_imports = {
        "LiveViewportRenderer",
        "LiveViewportProjectionCycleRunner",
        "create_live_viewport_projection_cycle_runner",
        "run_prepared_live_viewport_projection_cycle",
        "render_live_viewport_buffer",
        "apply_live_viewport_update",
        "apply_live_viewport_update_with_cursor_move",
        "apply_live_viewport_projection",
        "check_live_viewport_resize",
        "flush_writer",
        "clear_live_viewport",
        "sync_live_viewport_cursor_visibility",
        "live_viewport_minimum_row_widths_for_writes",
        "live_viewport_blank_rows",
        "live_viewport_cursor_position",
    }
    assert imported_names.isdisjoint(forbidden_lifecycle_imports)
    assert exported == {
        "TerminalBottomPaneRequestRunner",
        "terminal_bottom_pane_live_viewport_projection_cycle",
    }
    assert "def render_bottom_pane" not in source
    assert "def render_bottom_pane_and_flush" not in source
    assert "def clear_bottom_pane" not in source
    assert "def clear_bottom_pane_and_flush" not in source
    assert "def render_terminal_bottom_pane_frame" not in source
    assert "TerminalBottomPaneBufferState" not in exported
    assert "class TerminalBottomPaneBufferState" not in source
    assert "def run_terminal_bottom_pane_request" not in source
    assert "class TerminalBottomPaneRequestRunner" in source
    assert "project=terminal_bottom_pane_live_viewport_projection_cycle" in source
    assert "create_live_viewport_projection_request_runner(" in source
    assert "self._request_runner.run(request, move_cursor=move_cursor)" in source
    assert "def run_clear(" in source
    assert "def clear_callback(" in source
    assert "def clear_factory_callback(" in source
    assert "def run_render_pass(" in source
    assert "def render_pass_callback(" in source
    assert "def render_pass_factory_callback(" in source
    assert "terminal_bottom_pane_clear_request(" in source
    assert "terminal_bottom_pane_render_request_for_pass(" in source
    assert "create_live_viewport_projection_cycle_runner(" not in source
    assert "def run_terminal_bottom_pane_clear" not in source
    assert "def run_terminal_bottom_pane_render" not in source
    assert "draft: str" not in source
    assert "popup_lines:" not in source
    assert "run_prepared_live_viewport_projection_cycle" not in imported_names
    assert "create_live_viewport_projection_request_runner" in imported_names
    assert "TerminalBottomPaneRequest" in imported_names
    assert "terminal_bottom_pane_clear_request" in imported_names
    assert "terminal_bottom_pane_render_request_for_pass" in imported_names
    assert "TerminalBottomPaneClearRequest" not in imported_names
    assert "TerminalBottomPaneRenderRequest" not in imported_names
    assert "terminal_bottom_pane_clear_plan" not in imported_names
    assert "terminal_bottom_pane_render_plan" not in imported_names
    assert "run_prepared_live_viewport_projection_cycle(" not in source
    assert "self._cycle_runner" not in source
    assert "ratatui_draw_buffer_to_ansi" not in source
    assert "ratatui_requires_full_redraw" not in source
    assert "def apply_terminal_bottom_pane_action_plan" not in source

    custom_terminal_source = (REPO_ROOT / "pycodex/tui/custom_terminal.py").read_text(encoding="utf-8-sig")
    assert "class LiveViewportProjectionPolicy" in custom_terminal_source
    assert "class LiveViewportProjection" in custom_terminal_source
    assert "class LiveViewportCursorMove" in custom_terminal_source
    assert "class LiveViewportCursorMoveCallback(Protocol)" in custom_terminal_source
    assert "def diff_buffers_does_not_emit_clear_to_end_for_full_width_row" not in custom_terminal_source
    assert "def diff_buffers_clear_to_end_starts_after_wide_char" not in custom_terminal_source
    assert "def terminal_draw_applies_requested_cursor_style" not in custom_terminal_source
    assert "def reset_cursor_style_emits_default_user_shape" not in custom_terminal_source
    assert "def set_cursor_style_ansi" in custom_terminal_source
    assert "def reset_cursor_style_ansi" in custom_terminal_source
    assert "class CaptureBackend" not in custom_terminal_source
    assert "class Terminal:" not in custom_terminal_source
    assert "class Position:" not in custom_terminal_source
    assert "class Rect:" not in custom_terminal_source
    assert "class Size:" not in custom_terminal_source
    assert "def diff_buffers(" not in custom_terminal_source
    assert '"CaptureBackend"' not in custom_terminal_source
    assert '"Terminal"' not in custom_terminal_source
    assert '"diff_buffers"' not in custom_terminal_source
    assert "def terminal_visible_history_rows_after_viewport_change" in custom_terminal_source
    assert "def terminal_visible_history_rows_after_insert" in custom_terminal_source
    assert "def terminal_visible_history_rows_after_clear" in custom_terminal_source
    assert "def terminal_clear_scrollback_cursor_position" in custom_terminal_source
    assert "def terminal_viewport_clear_should_run" in custom_terminal_source
    assert 'cursor_move: "LiveViewportCursorMove | None" = None' in custom_terminal_source
    assert "cursor_move: LiveViewportCursorMove | None" in custom_terminal_source
    assert "move_cursor: LiveViewportCursorMoveCallback | None" in custom_terminal_source
    assert "move_cursor: Callable[[int, int], Any]" not in custom_terminal_source
    assert "def _coerce_live_viewport_cursor_move" not in custom_terminal_source
    assert "_coerce_live_viewport_cursor_move(" not in custom_terminal_source
    assert "class LiveViewportProjectionCycle" in custom_terminal_source
    assert (
        "project: Callable[[os.terminal_size, LiveViewportProjectionPolicy], LiveViewportProjection | None]"
        in custom_terminal_source
    )
    assert (
        "projection: Callable[[os.terminal_size, LiveViewportProjectionPolicy], LiveViewportProjection | None]"
        in custom_terminal_source
    )
    assert (
        "Callable[[os.terminal_size, LiveViewportProjectionPolicy], Any | None]"
        not in custom_terminal_source
    )
    assert "external_cursor_move=move_cursor is not None" in custom_terminal_source
    assert "projection(size, policy)" in custom_terminal_source
    assert "def truncate_display_width" in custom_terminal_source
    assert "def live_viewport_buffer_area_for_rows" in custom_terminal_source
    assert "class LiveViewportWriteProtocol" in custom_terminal_source
    assert "def live_viewport_minimum_row_widths_for_writes" in custom_terminal_source
    assert "def live_viewport_blank_rows" in custom_terminal_source
    assert "def live_viewport_cursor_position" in custom_terminal_source
    assert "def live_viewport_requires_full_redraw" in custom_terminal_source
    assert "def _live_viewport_changed_rows_contain_wide_cells" in custom_terminal_source
    assert "def from_writes" in custom_terminal_source
    assert "Iterable[LiveViewportWriteProtocol]" in custom_terminal_source
    assert "def _field" not in custom_terminal_source
    assert "_field(write" not in custom_terminal_source
    assert "write.row" in custom_terminal_source
    assert "write.column" in custom_terminal_source
    assert "write.text" in custom_terminal_source
    assert "def run_prepared_live_viewport_projection_cycle" in custom_terminal_source
    assert "class LiveViewportProjectionCycleRunner" in custom_terminal_source
    assert "def create_live_viewport_projection_cycle_runner" in custom_terminal_source
    assert "class LiveViewportProjectionRequestRunner" in custom_terminal_source
    assert "def create_live_viewport_projection_request_runner" in custom_terminal_source
    assert "live_viewport: \"LiveViewportRenderer\"" in custom_terminal_source
    assert "return run_prepared_live_viewport_projection_cycle(" in custom_terminal_source
    assert "resize: Callable[[], None]" in custom_terminal_source
    assert "resize: Callable[[], Any]" not in custom_terminal_source
    assert "apply_update: Callable[[os.terminal_size], bool]" in custom_terminal_source
    assert "apply_update: Callable[[os.terminal_size], Any]" not in custom_terminal_source
    assert "def run_live_viewport_update_cycle(" in custom_terminal_source
    assert ") -> bool:\n    \"\"\"Run the live-viewport resize" in custom_terminal_source
    assert (
        "def terminal_size(default: tuple[int, int] = (80, 24)) -> os.terminal_size:"
        in custom_terminal_source
    )
    assert (
        "def terminal_size(default: tuple[int, int] = (80, 24)) -> Any:"
        not in custom_terminal_source
    )
    assert "return shutil.get_terminal_size(default)" in custom_terminal_source
    assert "class TerminalColumnProvider" in custom_terminal_source
    assert "def columns(self) -> int:" in custom_terminal_source
    assert "return int(self.current_size().columns)" in custom_terminal_source
    assert '"TerminalColumnProvider",' in custom_terminal_source
    assert "class TerminalScrollRegionResetter" in custom_terminal_source
    assert "def reset(self) -> None:" in custom_terminal_source
    assert '"TerminalScrollRegionResetter",' in custom_terminal_source
    assert 'getattr(cycle, "should_run", False)' not in custom_terminal_source
    assert 'getattr(cycle, "check_resize", False)' not in custom_terminal_source
    assert 'getattr(cycle, "cursor_visible", None)' not in custom_terminal_source
    assert 'getattr(cycle, "project")' not in custom_terminal_source
    assert "should_run=cycle.should_run" in custom_terminal_source
    assert "check_resize=cycle.check_resize" in custom_terminal_source
    assert "cursor_visible=cycle.cursor_visible" in custom_terminal_source
    assert "projection=cycle.project" in custom_terminal_source
    assert "class LiveViewportBufferState" in custom_terminal_source
    assert "def previous(self) -> _BridgeBuffer | None:" in custom_terminal_source
    assert "def update(self, buffer: _BridgeBuffer) -> None:" in custom_terminal_source
    assert "def previous(self) -> Any:" not in custom_terminal_source
    assert "def update(self, buffer: Any) -> None:" not in custom_terminal_source
    assert "def reset_buffer_state" not in custom_terminal_source
    assert "def _reset_buffer_state" in custom_terminal_source
    assert "def run_external_repaint" in custom_terminal_source
    assert "repaint: Callable[[], _ExternalRepaintResult]" in custom_terminal_source
    assert "def run_external_repaint(self, repaint: Callable[[], Any]) -> Any:" not in custom_terminal_source
    custom_terminal_tests = (REPO_ROOT / "tests/test_tui_custom_terminal.py").read_text(encoding="utf-8-sig")
    ratatui_bridge_tests = (
        REPO_ROOT / "pycodex/tui/ratatui_bridge/tests/test_ratatui_bridge.py"
    ).read_text(encoding="utf-8-sig")
    assert "    Buffer,\n" not in custom_terminal_tests
    assert "    diff_buffers,\n" not in custom_terminal_tests
    assert "commands = diff_buffers(" not in custom_terminal_tests
    assert "clear_scrollback_and_visible_screen_ansi(backend)" not in custom_terminal_tests
    assert "write_inline_status_line(backend" not in custom_terminal_tests
    assert "clear_inline_status_line(backend)" not in custom_terminal_tests
    assert "clear_lines_at(backend" not in custom_terminal_tests
    assert "Terminal.with_options(CaptureBackend.new(2, 1))" not in custom_terminal_tests
    assert "    CaptureBackend,\n" not in custom_terminal_tests
    assert "    Position,\n" not in custom_terminal_tests
    assert "    Rect,\n" not in custom_terminal_tests
    assert "    Size,\n" not in custom_terminal_tests
    assert "    Terminal,\n" not in custom_terminal_tests
    assert "CaptureBackend.new(" not in custom_terminal_tests
    assert "Terminal.with_" not in custom_terminal_tests
    assert "set_cursor_style_ansi(writer, \"SteadyBar\")" in custom_terminal_tests
    assert "reset_cursor_style_ansi(writer)" in custom_terminal_tests
    assert "def test_bridge_diff_buffers_does_not_clear_full_width_nonblank_row" in ratatui_bridge_tests
    assert "def test_bridge_diff_buffers_clear_to_end_starts_after_wide_char" in ratatui_bridge_tests

    rendering_source = (REPO_ROOT / "pycodex/tui/chatwidget/rendering.py").read_text(encoding="utf-8-sig")
    chat_composer_source = (REPO_ROOT / "pycodex/tui/bottom_pane/chat_composer/__init__.py").read_text(
        encoding="utf-8-sig"
    )
    selection_popup_source = (REPO_ROOT / "pycodex/tui/bottom_pane/selection_popup_common.py").read_text(
        encoding="utf-8-sig"
    )
    assert "class TerminalBottomPaneFrameWrite" in rendering_source
    assert "class TerminalBottomPaneFrame" in rendering_source
    assert "class TerminalBottomPaneFrameProjection" in rendering_source
    assert "def terminal_bottom_pane_frame(" in rendering_source
    assert "def terminal_bottom_pane_frame_buffer" in rendering_source
    assert "terminal_composer_projection(" in rendering_source
    assert "terminal_footer_projection(" in rendering_source
    assert "terminal_live_status_projection(" in rendering_source
    assert "terminal_popup_lines_for_width(" in rendering_source
    assert "terminal_bottom_pane_layout_rows(" in rendering_source
    assert "terminal_popup_line_style(selected=write.selected)" in rendering_source
    assert "live_viewport_buffer_area_for_rows(" in rendering_source
    assert "def terminal_composer_line_text" in chat_composer_source
    assert "def terminal_composer_projection" in chat_composer_source
    assert "TERMINAL_POPUP_SELECTED_ROW_STYLE" in selection_popup_source
    assert "def terminal_popup_line_style" in selection_popup_source
    assert "def terminal_popup_line_for_width" in selection_popup_source
    assert "def terminal_popup_lines_for_width" in selection_popup_source
    assert "RatatuiColor.LightBlue" in selection_popup_source
    assert not (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_frame.py").exists()
    assert not (REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_frame.py").exists()
    terminal_frame_importers = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "pycodex/tui").rglob("*.py")
        if any(
            isinstance(node, ast.ImportFrom) and node.module == "pycodex.tui.bottom_pane.terminal_frame"
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig")))
        )
    }
    assert terminal_frame_importers == set()

    projection_source = (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_projection.py").read_text(
        encoding="utf-8-sig"
    )
    projection_exports = _literal_all(ast.parse(projection_source))
    assert projection_exports == {
        "TerminalBottomPaneRequestRunner",
        "terminal_bottom_pane_live_viewport_projection_cycle",
    }
    assert "def terminal_bottom_pane_frame_projection" in projection_source
    assert "terminal_bottom_pane_frame_buffer(size, frame)" in projection_source
    assert "def terminal_bottom_pane_frame_minimum_row_widths" not in projection_source
    assert "def terminal_bottom_pane_frame_blank_rows" not in projection_source
    assert "def terminal_bottom_pane_frame_cursor_position" not in projection_source
    assert "display_width(" not in projection_source
    assert "row_widths:" not in projection_source
    assert "written_rows =" not in projection_source
    assert "RatatuiPosition" not in projection_source
    assert "LiveViewportRenderRequest.from_writes(" in projection_source
    assert "live_viewport_minimum_row_widths_for_writes(" not in projection_source
    assert "live_viewport_blank_rows(" not in projection_source
    assert "live_viewport_cursor_position(" not in projection_source

    footprint_source = (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_footprint.py").read_text(encoding="utf-8-sig")
    assert "class TerminalBottomPaneFootprint" in footprint_source
    assert "class TerminalBottomPaneLayoutRows" in footprint_source
    assert "def bottom_pane_height" in footprint_source
    assert "def bottom_pane_rows_for_size" in footprint_source
    assert "def status_row" in footprint_source
    assert "def composer_row" in footprint_source
    assert "def footer_row" in footprint_source
    assert "def terminal_bottom_pane_layout_rows" in footprint_source
    assert "def terminal_bottom_pane_clear_request" in footprint_source
    assert "class TerminalLiveStatusFootprintProtocol(Protocol)" in footprint_source
    assert "live_status: TerminalLiveStatusFootprintProtocol" in footprint_source
    assert "live_status: Any" not in footprint_source
    assert 'getattr(live_status, "footprint_active", False)' not in footprint_source

    action_source = (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_action.py").read_text(encoding="utf-8-sig")
    assert "class TerminalBottomPaneState" in action_source
    assert "class TerminalBottomPaneActionPlan" in action_source
    assert "class TerminalBottomPaneProjectionCleanup" in action_source
    assert "TerminalBottomPaneRequest: TypeAlias = TerminalBottomPaneClearRequest | TerminalBottomPaneRenderRequest" in action_source
    assert "class TerminalBottomPaneRenderContextProtocol" in action_source
    assert "class TerminalBottomPaneRenderPassProtocol" in action_source
    assert "def projection_cleanup" in action_source
    assert "def projection_cursor_visible" in action_source
    assert "flush: bool = False" in action_source
    assert "def terminal_bottom_pane_clear_request" in action_source
    assert "def terminal_bottom_pane_clear_plan" in action_source
    assert "def terminal_bottom_pane_render_request" in action_source
    assert "def terminal_bottom_pane_render_request_for_pass" in action_source
    assert "def terminal_bottom_pane_render_plan" in action_source
    assert 'getattr(render_context, "draft", "")' not in action_source
    assert 'getattr(render_context, "popup_lines", ())' not in action_source
    assert 'getattr(render_context, "cursor_visible", True)' not in action_source
    assert 'getattr(render_pass, "check_resize", True)' not in action_source
    assert 'getattr(render_pass, "clear_popup_height", 0)' not in action_source
    assert 'getattr(render_pass, "clear_live_status_active", False)' not in action_source
    assert "draft=str(render_context.draft)" in action_source
    assert "popup_lines=tuple(render_context.popup_lines)" in action_source
    assert "cursor_visible=bool(render_context.cursor_visible)" in action_source
    assert "check_resize=bool(render_pass.check_resize)" in action_source
    assert "clear_popup_height=int(render_pass.clear_popup_height)" in action_source
    assert "clear_live_status_active=bool(render_pass.clear_live_status_active)" in action_source
    assert "flush=True" in action_source

    projection_source = (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_projection.py").read_text(encoding="utf-8-sig")
    assert "class TerminalBottomPaneLiveViewportUpdate" not in projection_source
    assert "LiveViewportProjection(" in projection_source
    assert "class TerminalBottomPaneCursorMove" not in projection_source
    assert "LiveViewportCursorMove(" in projection_source
    assert "def terminal_bottom_pane_cursor_move" in projection_source
    assert "def terminal_bottom_pane_backend_cursor_position_enabled" not in projection_source
    assert "live_viewport_backend_cursor_position_enabled(" in projection_source
    assert "def terminal_bottom_pane_frame_live_viewport_update" in projection_source
    assert "def terminal_bottom_pane_live_viewport_request" in projection_source
    assert "def terminal_bottom_pane_live_viewport_update" in projection_source
    assert "def terminal_bottom_pane_live_viewport_update_for_cursor_policy" in projection_source
    assert "def terminal_bottom_pane_request_live_viewport_update" in projection_source
    assert "def terminal_bottom_pane_live_viewport_projection_cycle" in projection_source
    assert "class TerminalBottomPaneProjectionCycle" not in projection_source
    assert "TerminalBottomPaneProjectionCycle(" not in projection_source
    assert "LiveViewportProjectionCycle(" in projection_source
    assert "TerminalBottomPaneProjectionCleanup" not in projection_source
    assert "TerminalBottomPaneRequest" in projection_source
    assert "TerminalBottomPaneClearRequest" not in projection_source
    assert "TerminalBottomPaneRenderRequest" not in projection_source
    assert "LiveViewportProjectionPolicy" in projection_source
    assert "policy.external_cursor_move" in projection_source
    assert "policy.cursor_visible" in projection_source
    assert "class ProjectionCleanupShape" in projection_source
    assert "def _terminal_bottom_pane_request_live_viewport_update" in projection_source
    assert "cleanup: ProjectionCleanupShape," in projection_source
    assert "plan: TerminalBottomPaneActionPlan," in projection_source
    assert "cleanup: ProjectionCleanupShape | None = None" not in projection_source
    assert "plan: TerminalBottomPaneActionPlan | None = None" not in projection_source
    assert "plan = plan or request.action_plan()" not in projection_source
    assert "cleanup = cleanup or request.projection_cleanup()" not in projection_source
    assert "cleanup=None" not in projection_source
    assert "request.projection_cleanup()" in projection_source
    assert "request.projection_cursor_visible()" in projection_source
    assert "cleanup.clear_popup_height" in projection_source
    assert "cleanup.clear_live_status_active" in projection_source
    assert "cleanup.clear_external_blank_rows" in projection_source
    assert 'getattr(request, "clear_popup_height", 0)' not in projection_source
    assert 'getattr(request, "clear_external_blank_rows", False)' not in projection_source
    assert "request.cursor_visible" not in projection_source
    assert "isinstance(request, TerminalBottomPaneRenderRequest)" not in projection_source

    resize_reflow_source = (REPO_ROOT / "pycodex/tui/app/resize_reflow.py").read_text(encoding="utf-8-sig")
    tui_source = (REPO_ROOT / "pycodex/tui/tui/__init__.py").read_text(encoding="utf-8-sig")
    controller_source = (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_controller.py").read_text(
        encoding="utf-8-sig"
    )
    runtime_source = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(encoding="utf-8-sig")
    status_surface_source = (REPO_ROOT / "pycodex/tui/chatwidget/status_surfaces.py").read_text(
        encoding="utf-8-sig"
    )
    insert_history_source = (REPO_ROOT / "pycodex/tui/insert_history.py").read_text(encoding="utf-8-sig")

    # Rust app::resize_reflow owns terminal-size transcript rebuild only. The
    # inline viewport policy and draw lifecycle belong to tui.rs.
    forbidden_app_footprint_symbols = {
        "TerminalBottomPaneFootprintTracker",
        "TerminalBottomPaneFootprintCycleRunner",
        "TerminalBottomPaneFootprintRenderPass",
        "bottom_pane_footprint_transition",
        "bottom_pane_footprint",
        "terminal_history_bottom_row",
        "repaint_history_viewport_for_footprint",
        "popup_is_active_view",
    }
    assert all(symbol not in resize_reflow_source for symbol in forbidden_app_footprint_symbols)
    assert "class TerminalResizeCoordinator" in resize_reflow_source
    assert "def plan_terminal_size_change_reflow" in resize_reflow_source
    assert "def replay_terminal_history_scrollback_for_resize" in resize_reflow_source

    assert "class TerminalInlineViewport" in tui_source
    assert "def update_inline_viewport_for_resize_reflow" in tui_source
    assert "def draw_with_resize_reflow" in tui_source
    assert "class TerminalBottomPaneViewportCycleRunner" in tui_source
    assert "def create_terminal_bottom_pane_viewport_cycle_runner" in tui_source
    assert "self.viewport.draw_with_resize_reflow(" in tui_source
    assert "def prepare_history_insert" in tui_source
    assert "def prepare_resize_reflow" in tui_source
    assert "def resize_reflow_replay_callback_factory" in tui_source
    replay_factory = tui_source.split(
        "def resize_reflow_replay_callback_factory(",
        1,
    )[1].split("\n    def ", 1)[0]
    assert replay_factory.index("self.prepare_resize_reflow(") < replay_factory.index(
        "return replay_history_scrollback()"
    )

    assert "from ..tui import create_terminal_bottom_pane_viewport_cycle_runner" in controller_source
    assert "from ..app.resize_reflow" not in controller_source
    assert "repaint_footprint" not in controller_source
    assert "run_bottom_pane_footprint" not in runtime_source
    assert "repaint_footprint" not in status_surface_source
    assert "prepare_history_insert=self._bottom_pane.prepare_history_insert" in runtime_source
    assert "replay_history_scrollback=self._bottom_pane.resize_reflow_replay_callback(" in runtime_source
    assert "def _replay_history_scrollback_after_viewport_resize" not in runtime_source
    assert "prepare_history_insert: Callable[[int], None] | None" in insert_history_source
    assert "self.prepare_history_insert(max(0, int(inserted_rows)))" in insert_history_source

    assert "viewport_area: Rect" in action_source
    assert 'getattr(render_pass, "viewport_area", None)' in action_source
    assert "viewport_area=request.projection_viewport_area()" in projection_source

def test_terminal_bottom_pane_adapter_test_module_does_not_return() -> None:
    # Rust owners: chatwidget::rendering owns bottom-pane frame/buffer content,
    # terminal_projection bridges that frame into custom_terminal, and
    # custom_terminal owns diffing. The old catch-all adapter test module must
    # stay deleted so request-runner, controller, status, and frame projection
    # evidence remains attached to the Rust owner modules.
    assert not (REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_surface.py").exists()
    assert not (
        REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_bottom_pane_adapter.py"
    ).exists()
    rendering_tests = _test_function_names(REPO_ROOT / "pycodex/tui/chatwidget/tests/test_rendering.py")
    projection_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_projection.py")
    controller_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_controller.py")
    status_tests = _test_function_names(REPO_ROOT / "pycodex/tui/chatwidget/tests/test_status_surfaces.py")

    assert "test_terminal_bottom_pane_frame_projects_popup_rows_to_buffer" in rendering_tests
    assert "test_terminal_bottom_pane_frame_clear_rows_cover_previous_larger_popup_footprint" in rendering_tests
    assert "test_terminal_projection_pairs_frame_and_buffer" in projection_tests
    assert "test_terminal_bottom_pane_request_runner_executes_clear_and_render" in projection_tests
    assert "test_terminal_bottom_pane_request_runner_flushes_writer" in projection_tests
    assert "test_terminal_bottom_pane_request_runner_builds_tui_viewport_clear_factory" in projection_tests
    assert "test_terminal_bottom_pane_request_runner_builds_tui_viewport_render_factory" in projection_tests
    assert "test_terminal_projection_frame_update_diff_uses_custom_terminal_owner" in projection_tests
    assert "test_terminal_projection_paints_status_composer_footer_and_cursor" in projection_tests
    assert "test_terminal_projection_uses_bridge_cursor_lifecycle_by_default" in projection_tests
    assert "test_terminal_projection_paints_slash_popup_below_composer_with_highlight" in projection_tests
    assert "test_terminal_projection_buffer_state_skips_unchanged_second_render" in projection_tests
    assert "test_terminal_projection_clears_external_blank_row_without_footer_repaint" in projection_tests
    assert "test_terminal_projection_can_suppress_frame_cursor" in projection_tests
    assert "test_terminal_projection_preserves_empty_composer_prompt_space_through_buffer" in projection_tests
    assert "test_terminal_projection_clears_previous_larger_popup_footprint" in projection_tests
    assert "test_terminal_projection_frame_update_does_not_flush_without_policy" in projection_tests
    assert "test_terminal_bottom_pane_controller_syncs_draft_and_terminal_callbacks" in controller_tests
    assert "test_terminal_bottom_pane_controller_resizes_tui_viewport_for_active_view" in controller_tests
    assert "test_live_status_surface_controls_bottom_pane_footprint" in status_tests
    assert "test_run_live_status_show_and_hide_return_surface_state_and_execute_effects" in status_tests


def test_bottom_pane_popup_render_context_uses_typed_terminal_popup_lines() -> None:
    # Rust owners: bottom_pane::command_popup, list_selection_view, and
    # selection_popup_common own popup row projection. The bottom-pane render
    # context should carry the shared TerminalPopupLine shape instead of an
    # untyped adapter payload.
    view_stack_source = (REPO_ROOT / "pycodex/tui/bottom_pane/view_stack.py").read_text(encoding="utf-8-sig")
    chat_composer_source = (REPO_ROOT / "pycodex/tui/bottom_pane/chat_composer/__init__.py").read_text(
        encoding="utf-8-sig"
    )
    action_source = (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_action.py").read_text(encoding="utf-8-sig")

    assert "from .selection_popup_common import TerminalPopupLine" in view_stack_source
    assert "lines: tuple[TerminalPopupLine, ...]" in view_stack_source
    assert "popup_lines: tuple[TerminalPopupLine, ...]" in view_stack_source
    assert "def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]" in view_stack_source
    assert "def terminal_bottom_pane_popup_lines(" in view_stack_source
    assert ") -> list[TerminalPopupLine]:" in view_stack_source
    assert "popup_lines: tuple[Any" not in view_stack_source
    assert "lines: tuple[Any" not in view_stack_source

    assert "from ..selection_popup_common import TerminalPopupLine" in chat_composer_source
    assert "def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]" in chat_composer_source
    assert 'command == "model"' not in chat_composer_source

    assert "popup_lines: tuple[TerminalBottomPanePopupLine, ...]" in action_source
    assert "popup_lines: tuple[Any" not in action_source


def test_bottom_pane_view_stack_uses_typed_command_popup_state_protocol() -> None:
    # Rust owners: bottom_pane::BottomPane owns active-view precedence, while
    # chat_composer::sync_popups owns command-popup state. view_stack may route
    # across that boundary, but it should consume a typed state protocol instead
    # of reflectively probing command-popup internals from terminal adapters.
    source = (REPO_ROOT / "pycodex/tui/bottom_pane/view_stack.py").read_text(encoding="utf-8-sig")

    assert "class TerminalCommandPopupStateProtocol(Protocol)" in source
    assert "command_popup_state: TerminalCommandPopupStateProtocol" in source
    assert "command_popup_state.visible" in source
    assert "command_popup_state.terminal_lines(width=width)" in source
    assert "command_popup_state.sync_draft(" in source
    assert "command_popup_state.hide()" in source
    assert 'getattr(command_popup_state, "visible"' not in source
    assert 'getattr(command_popup_state, "terminal_lines"' not in source
    assert 'getattr(command_popup_state, "sync_draft"' not in source
    assert 'getattr(command_popup_state, "hide"' not in source


def test_bottom_pane_view_stack_uses_bottom_pane_view_trait_contract() -> None:
    # Rust owner: bottom_pane::bottom_pane_view defines BottomPaneView as the
    # active-view trait and extends Renderable. The terminal path projects that
    # renderable contract as typed TerminalPopupLine rows; view_stack should
    # call trait helpers instead of reflectively probing active-view objects.
    bottom_pane_view_source = (REPO_ROOT / "pycodex/tui/bottom_pane/bottom_pane_view.py").read_text(
        encoding="utf-8-sig"
    )
    list_selection_source = (REPO_ROOT / "pycodex/tui/bottom_pane/list_selection_view.py").read_text(
        encoding="utf-8-sig"
    )
    view_stack_source = (REPO_ROOT / "pycodex/tui/bottom_pane/view_stack.py").read_text(encoding="utf-8-sig")

    assert "def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]: ..." in bottom_pane_view_source
    assert "def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:" in bottom_pane_view_source
    assert "def terminal_lines(view: BottomPaneView, *, width: int) -> list[TerminalPopupLine]:" in bottom_pane_view_source
    assert "BottomPaneView," in view_stack_source
    assert "from .command_popup import CommandPopup" in view_stack_source
    assert "_views: list[BottomPaneView]" in view_stack_source
    assert "selection_events: list[object]" in view_stack_source
    assert "TerminalSelectionEventHandler: TypeAlias" in view_stack_source
    assert "TerminalCommandViewFactory: TypeAlias" in view_stack_source
    assert "on_selection_events: TerminalSelectionEventHandler | None = None" in view_stack_source
    assert "open_command_view: TerminalCommandViewFactory | None = None" in view_stack_source
    assert "open_model_view: TerminalSelectionViewFactory | None = None" not in view_stack_source
    assert "selection_events: list[Any]" not in view_stack_source
    assert "Callable[[tuple[Any, ...]], SelectionViewParams | None]" not in view_stack_source
    assert "def active_view(self) -> BottomPaneView | None:" in view_stack_source
    assert "def command_popup(self) -> CommandPopup:" in view_stack_source
    assert "return view_terminal_lines(view, width=width)" in view_stack_source
    assert "view_handle_key_event(view, key)" in view_stack_source
    assert "view_is_complete(self._views[-1])" in view_stack_source
    assert "completion = view_completion(completed)" in view_stack_source
    assert "completion_value: Optional[ViewCompletion]" in list_selection_source
    assert "self.completion_value = ViewCompletion.ACCEPTED" in list_selection_source
    assert "self.completion_value = ViewCompletion.CANCELLED" in list_selection_source
    assert "def completion(self) -> ViewCompletion | None:" in list_selection_source
    assert 'self.completion_value = "Submitted"' not in list_selection_source
    assert 'self.completion_value = "Cancelled"' not in list_selection_source
    assert "def _completion_is_accepted(value: ViewCompletion | None) -> bool:" in view_stack_source
    assert "def _completion_is_cancelled(value: ViewCompletion | None) -> bool:" in view_stack_source
    assert "value is ViewCompletion.ACCEPTED" in view_stack_source
    assert "value is ViewCompletion.CANCELLED" in view_stack_source
    assert "def _completion_name" not in view_stack_source
    assert '"submitted"' not in view_stack_source
    assert "from typing import Any" not in view_stack_source
    assert "view_dismiss_after_child_accept(self._views[-1])" in view_stack_source
    assert "clear_view_dismiss_after_child_accept(self._views[-1])" in view_stack_source
    assert 'getattr(view, "terminal_lines"' not in view_stack_source
    assert 'getattr(view, "is_complete"' not in view_stack_source
    assert 'getattr(view, "completion"' not in view_stack_source
    assert 'getattr(view, "dismiss_after_child_accept"' not in view_stack_source
    assert 'getattr(view, "clear_dismiss_after_child_accept"' not in view_stack_source
    assert "handle_key_event as handle_selection_key_event" not in view_stack_source
    assert "handle_selection_key_event(view, key)" not in view_stack_source


def test_terminal_controller_does_not_own_popup_row_projection() -> None:
    # Rust owners: bottom_pane::command_popup and
    # bottom_pane::list_selection_view own popup/list row projection.
    # terminal_controller may orchestrate key routing and view stack state, but
    # it must not import low-level row rendering helpers or layout geometry.
    controller_path = REPO_ROOT / "pycodex/tui/bottom_pane/terminal_controller.py"
    source = controller_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    exported = _literal_all(tree)
    controller_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TerminalBottomPaneController"
    )
    public_controller_methods = {
        node.name
        for node in controller_class.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    controller_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_controller.py")
    view_stack_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_view_stack.py")
    bottom_pane_owner_tests = {
        "test_terminal_bottom_pane_view_state_pushes_child_selection_view_from_events",
        "test_terminal_bottom_pane_view_state_normalizes_text_enter_for_active_selection_view",
    }
    old_controller_owner_tests = {
        "test_terminal_bottom_pane_surface_writer_pushes_child_selection_view",
        "test_terminal_bottom_pane_surface_writer_normalizes_text_enter_for_selection_view",
        "test_terminal_controller_moves_slash_highlight_and_tabs_selection",
        "test_terminal_controller_model_command_opens_active_selection_view",
        "test_terminal_bottom_pane_surface_writer_syncs_command_popup_and_selection",
        "test_terminal_bottom_pane_surface_writer_routes_model_to_active_selection_view",
    }

    assert bottom_pane_owner_tests <= view_stack_tests
    assert controller_tests.isdisjoint(bottom_pane_owner_tests | old_controller_owner_tests)
    assert public_controller_methods == {
        "sync_draft",
        "sync_active_tail",
        "sync_pending_thread_approvals",
            "show_shutdown",
            "show_view",
            "dismiss_app_server_request",
            "has_active_view",
            "handle_active_view_input",
            "composer",
            "handle_composer_event",
        "history_bottom_row",
        "prepare_history_insert",
        "resize_reflow_replay_callback",
        "clear",
        "clear_without_resize_check",
        "restore_cursor",
        "run_external_repaint",
        "render_after_history_repaint",
        "render_without_resize_check",
        "render",
    }

    forbidden_projection_imports = {
        "COMMAND_COLUMN_WIDTH",
        "MAX_POPUP_ROWS",
        "Rect",
        "FrameBufferState",
        "LiveViewportBufferState",
        "RatatuiFrameBufferState",
        "render_rows_with_col_width_mode",
        "terminal_bottom_pane_frame",
        "terminal_bottom_pane_frame_buffer",
        "render_terminal_bottom_pane_frame",
    }
    assert imported_names.isdisjoint(forbidden_projection_imports)
    assert "LiveViewportRenderer" not in imported_names
    assert "create_live_viewport_renderer" not in imported_names
    assert "check_live_viewport_resize" not in imported_names
    assert "flush_writer" not in imported_names
    assert "flush_live_viewport" not in imported_names
    assert "hide_cursor_ansi" not in imported_names
    assert "show_cursor_ansi" not in imported_names
    assert "apply_terminal_bottom_pane_action_plan" not in imported_names
    assert "run_terminal_bottom_pane_request" not in imported_names
    assert "TerminalBottomPaneRequestRunner" in imported_names
    assert "run_terminal_bottom_pane_clear" not in imported_names
    assert "run_terminal_bottom_pane_render" not in imported_names
    assert "TerminalBottomPaneClearRequest" not in imported_names
    assert "TerminalBottomPaneRenderRequest" not in imported_names
    assert "terminal_bottom_pane_clear_request" not in imported_names
    assert "terminal_bottom_pane_render_request" not in imported_names
    assert "terminal_bottom_pane_render_request_for_pass" not in imported_names
    assert "BottomPaneViewStack" not in imported_names
    assert "BottomPaneView" not in imported_names
    assert "CommandPopup" not in imported_names
    assert "TerminalBottomPaneViewState" in imported_names
    assert "SelectionViewParams" not in imported_names
    assert "TerminalSelectionEventHandler" in imported_names
    assert "TerminalCommandViewFactory" in imported_names
    assert "TerminalSelectionViewFactory" not in imported_names
    assert "from .list_selection_view import SelectionViewParams" not in source
    assert "The controller wires Rust-owned bottom-pane state" in source
    assert "This class is glue" in source
    assert "slash popup navigation" not in source
    assert "active selection views" not in source
    assert "terminal_bottom_pane_active_view_input" not in imported_names
    assert "terminal_bottom_pane_handle_composer_key" not in imported_names
    assert "terminal_bottom_pane_cursor_visible" not in imported_names
    assert "terminal_bottom_pane_popup_projection" not in imported_names
    assert "terminal_bottom_pane_popup_projection_for_size" not in imported_names
    assert "terminal_bottom_pane_popup_lines" not in imported_names
    assert "terminal_bottom_pane_show_selection_view" not in imported_names
    assert "terminal_bottom_pane_sync_command_popup" not in imported_names
    assert "TerminalCommandPopupState" not in imported_names
    assert "run_terminal_command_popup_input_action" not in imported_names
    assert "terminal_command_popup_input_action" not in imported_names
    assert "if not self.command_popup_visible" not in source
    assert "return run_terminal_command_popup_input_action(" not in source
    assert "terminal_bottom_pane_handle_composer_key(" not in source
    assert "self._view_state.handle_composer_event(" in source
    assert "def active_view(self)" not in source
    assert "def view_stack(self)" not in source
    assert "def command_popup(self)" not in source
    assert "def command_popup_visible(self)" not in source
    assert "def draft(self)" not in source
    assert "def show_selection_view(self" not in source
    assert "def sync_draft(self, draft: str) -> None:" in source
    assert "def apply_draft(self, draft: str) -> None:" not in source
    assert "def active_view(self) -> Any | None:" not in source
    assert "def view_stack(self) -> list[Any]:" not in source
    assert "def command_popup(self) -> Any:" not in source
    assert "return self._view_state.draft" not in source
    # Typed slash dispatch may hand a command-owned view to the terminal
    # adapter; the private method must remain a one-line delegation and must
    # not project rows or own command behavior.
    assert "def _show_selection_view(self, params: object) -> None:" in source
    assert "self._view_state.show_selection_view(params)" in source
    assert "open_command_view: TerminalCommandViewFactory | None = None" in source
    assert "open_model_view: TerminalSelectionViewFactory | None = None" not in source
    assert "on_selection_events: TerminalSelectionEventHandler | None = None" in source
    assert "on_selection_events: Callable[[tuple[object, ...]], SelectionViewParams | None]" not in source
    assert "on_selection_events: Callable[[tuple[Any, ...]], SelectionViewParams | None]" not in source
    assert "active_view_present=self.active_view is not None" not in source
    assert ".sync_draft(" not in source
    assert "self._command_popup_state.hide()" not in source
    assert "self._view_stack.replace_with_selection_view" not in source
    assert "self._command_popup_state" not in source
    assert "self._view_stack" not in source
    assert "self.selection_events" not in source
    assert "def _frame_cursor_visible" not in source
    assert "self.cursor_visible()" not in source
    for public_dependency in (
        "writer",
        "stdin_is_terminal",
        "layout_active",
        "live_status",
        "terminal_size",
        "resize",
        "footer_text",
        "open_command_view",
        "open_model_view",
        "on_selection_events",
        "repaint_footprint",
        "cursor_visible",
    ):
        assert f"self.{public_dependency} =" not in source
    for private_dependency in (
        "_open_command_view",
        "_on_selection_events",
        "_request_runner",
        "_viewport_runner",
        "_history_bottom_row",
        "_resize_reflow_replay_callback",
        "_clear_bottom_pane",
        "_render_for_view_state",
    ):
        assert f"self.{private_dependency} =" in source
    for request_environment_dependency in (
        "_stdin_is_terminal",
        "_layout_active",
        "_live_status",
        "_footer_text",
        "_repaint_footprint",
        "_cursor_visible",
    ):
        assert f"self.{request_environment_dependency} =" not in source
    assert "self.active_view is not None" not in source
    assert "TerminalBottomPaneRenderPassProtocol" not in imported_names
    assert "TerminalBottomPaneFootprintRenderPass" not in imported_names
    assert "TerminalBottomPaneFootprintTracker" not in imported_names
    assert "create_terminal_bottom_pane_viewport_cycle_runner" in imported_names
    assert "create_terminal_bottom_pane_footprint_cycle_runner" not in imported_names
    assert "create_terminal_bottom_pane_footprint_tracker" not in imported_names
    assert "create_live_viewport_renderer" not in imported_names
    assert "TerminalBottomPaneRenderContextProtocol" not in imported_names
    assert "from .terminal_footprint import TerminalBottomPaneFootprint" not in source
    assert "terminal_history_bottom_row" not in imported_names
    assert "terminal_history_bottom_row_for_context" not in imported_names
    assert "terminal_history_bottom_row_for_view_state" not in imported_names
    assert "run_terminal_bottom_pane_footprint_external_repaint" not in imported_names
    assert "run_terminal_bottom_pane_footprint_clear_cycle" not in imported_names
    assert "run_terminal_bottom_pane_footprint_render_cycle" not in imported_names
    assert "run_terminal_bottom_pane_footprint_render_cycle_for_context" not in imported_names
    assert "run_terminal_bottom_pane_footprint_render_cycle_for_view_state" not in imported_names
    assert "history_bottom_row" not in imported_names
    assert "terminal_command_popup_lines" not in exported
    assert "terminal_selection_view_lines" not in exported
    assert "run_terminal_bottom_pane_clear" not in exported
    assert "run_terminal_bottom_pane_render" not in exported
    assert "run_terminal_bottom_pane_action_plan" not in exported
    assert "def terminal_command_popup_lines" not in source
    assert "def terminal_selection_view_lines" not in source
    assert "def run_terminal_bottom_pane_clear" not in source
    assert "def run_terminal_bottom_pane_render" not in source
    assert "def run_terminal_bottom_pane_action_plan" not in source
    assert "self._request_runner = TerminalBottomPaneRequestRunner(" in source
    assert "terminal_size=self._request_runner.terminal_size" in source
    assert source.count("self._request_runner.terminal_size()") == 0
    assert "self._request_runner.clear_callback(" not in source
    assert "self._request_runner.clear_factory_callback(" in source
    assert "self._request_runner.run_clear(" not in source
    assert "self._request_runner.render_pass_callback(" not in source
    assert "self._request_runner.render_pass_factory_callback(" in source
    assert "self._request_runner.run_render_pass(" not in source
    assert "def render_pass(" not in source
    assert "self._request_runner.run(\n                terminal_bottom_pane_clear_request(" not in source
    assert "self._request_runner.run(\n                terminal_bottom_pane_render_request_for_pass(" not in source
    assert "run_terminal_bottom_pane_request(\n                self.writer,\n                stdin_is_terminal" not in source
    assert "render_context: TerminalBottomPaneRenderContextProtocol" not in source
    assert "render_context: object" not in source
    assert "pass_state: TerminalBottomPaneRenderPassProtocol" not in source
    assert "pass_state: Any" not in source
    assert "pass_state.check_resize" not in source
    assert "pass_state.clear_popup_height" not in source
    assert "pass_state.clear_live_status_active" not in source
    assert "draft=render_context.draft" not in source
    assert "popup_lines=render_context.popup_lines" not in source
    assert "cursor_visible=render_context.cursor_visible" not in source
    assert "self.view_stack =" not in source
    assert "self.active_view =" not in source
    assert ".view_stack.append" not in source
    assert ".view_stack.pop" not in source
    assert "draft_command_name" not in source
    assert "selected.command()" not in source
    assert "f\"/{selected.command()} \"" not in source
    assert 'action.kind == "move_up"' not in source
    assert 'action.kind == "move_down"' not in source
    assert 'action.kind == "complete"' not in source
    assert 'action.kind == "open_model"' not in source
    assert 'action.kind == "handled"' not in source
    assert "CommandPopupFlags" not in source
    assert "CommandPopup.new" not in source
    assert "on_composer_text_change" not in source
    assert "handle_selection_key_event" not in source
    assert "handle_key_event as" not in source
    assert "self._view_stack.handle_active_key" not in source
    assert 'str(event_kind).lower() in {"eof", "interrupt"}' not in source
    assert "def _drain_active_view_events" not in source
    assert "def _push_selection_view" not in source
    assert "def _pop_completed_views" not in source
    assert "render_rows_with_col_width_mode" not in source
    assert "render_bottom_pane_and_flush" not in source
    assert "render_terminal_bottom_pane_frame" not in source
    assert "terminal_bottom_pane_frame_buffer" not in source
    assert "terminal_bottom_pane_frame(" not in source
    assert "_last_popup_height" not in source
    assert "_last_live_status_active" not in source
    assert "_last_popup_was_active_view" not in source
    assert "_terminal_cursor_visible" not in source
    assert "def _sync_terminal_cursor_visibility" not in source
    assert "self._footprint_tracker.render_with_reflow_passes" not in source
    assert "TerminalBottomPaneFootprintTracker()" not in source
    assert "self._footprint_tracker" not in source
    assert "self._viewport_runner = create_terminal_bottom_pane_viewport_cycle_runner(" in source
    assert "self._history_bottom_row = self._viewport_runner.history_bottom_row_callback(" in source
    assert "self._history_bottom_row(reserve_active_bottom_pane)" in source
    assert "self._viewport_runner.history_bottom_row(" not in source
    assert "self._resize_reflow_replay_callback = (" in source
    assert "self._viewport_runner.resize_reflow_replay_callback_factory(" in source
    assert "return self._resize_reflow_replay_callback(replay_history_scrollback)" in source
    assert "self._viewport_runner.prepare_resize_reflow(" not in source
    assert "self._clear_bottom_pane = self._viewport_runner.clear_callback(" in source
    assert "clear_factory=self._request_runner.clear_factory_callback(" in source
    assert "def _clear_for_live_status(" not in source
    assert "self._clear_bottom_pane(check_resize)" in source
    assert "self._viewport_runner.clear(" not in source
    assert "self._render_for_view_state = self._viewport_runner.render_for_view_state_callback(" in source
    assert "render_factory=self._request_runner.render_pass_factory_callback(" in source
    assert "def _render_pass_for_live_status(" not in source
    assert "self._render_for_view_state(" in source
    assert "self._viewport_runner.render_for_view_state(" not in source
    assert "run_terminal_bottom_pane_footprint_render_cycle(" not in source
    assert "run_terminal_bottom_pane_footprint_render_cycle_for_context(" not in source
    assert "run_terminal_bottom_pane_footprint_render_cycle_for_view_state(" not in source
    assert "render_context.popup_height" not in source
    assert "render_context.popup_is_active_view" not in source
    assert "render_after_repaint=lambda" not in source
    assert "clear_popup_height=self._footprint_tracker.popup_height" not in source
    assert "clear_live_status_active=self._footprint_tracker.live_status_active" not in source
    assert "self._footprint_tracker.plan_reflow" not in source
    assert "self._footprint_tracker.update_after_render" not in source
    assert "self._footprint_tracker.clear_after_surface_clear" not in source
    assert "repaint_before_render" not in source
    assert "repaint_after_render" not in source
    assert "check_live_viewport_resize(" not in source
    assert "live_viewport.check_resize(resize)" not in source
    assert "LiveViewportRenderer(" not in source
    assert "self._live_viewport =" not in source
    assert "create_live_viewport_renderer(" not in source
    assert "\n            live_viewport.reset_buffer_state()" not in source
    assert "def reset_buffer_state" not in source
    assert "self._live_viewport.reset_buffer_state" not in source
    assert "self._request_runner.run_external_repaint" in source
    assert "run_terminal_bottom_pane_footprint_external_repaint(" not in source
    assert "if self.repaint_footprint is None" not in source
    assert "previous == current" not in source
    assert "self._live_viewport.reset_buffer_state()\n        self.repaint_footprint" not in source
    assert "def _repaint_footprint" not in source
    assert "self._live_viewport.hide_cursor()" not in source
    assert "self._live_viewport.show_cursor()" not in source
    assert "self._live_viewport.sync_cursor_visibility" not in source
    assert "self._request_runner.restore_cursor()" in source
    assert "self._command_popup_state.terminal_lines" not in source
    assert "self._view_stack.terminal_lines" not in source
    assert "return terminal_bottom_pane_popup_lines(" not in source
    assert "max(1, self.terminal_size().columns - 1)" not in source
    assert "self._view_state.popup_projection_for_size(" not in source
    assert "self._view_state.popup_height_for_size(" not in source
    assert "self._view_state.cursor_visible(" not in source
    assert "self._view_state.render_context_for_size(" not in source
    assert "terminal_history_bottom_row_for_context(" not in source
    assert "terminal_history_bottom_row_for_view_state(" not in source


def test_terminal_runtime_does_not_own_bottom_pane_ui_projection() -> None:
    # Rust owners: bottom_pane::chat_composer, command_popup,
    # list_selection_view, chatwidget::model_popups, chatwidget::rendering, and
    # custom_terminal own input interpretation, popup/view rows, frame
    # projection, and buffer redraw.  terminal_runtime may wire those modules
    # together, but it must not import their low-level projection/render types.
    runtime_path = REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py"
    source = runtime_path.read_text(encoding="utf-8-sig")
    insert_history_source = (REPO_ROOT / "pycodex/tui/insert_history.py").read_text(encoding="utf-8-sig")
    controller_source = (REPO_ROOT / "pycodex/tui/bottom_pane/terminal_controller.py").read_text(
        encoding="utf-8-sig"
    )
    status_source = (REPO_ROOT / "pycodex/tui/chatwidget/status_surfaces.py").read_text(encoding="utf-8-sig")
    turn_runtime_source = (REPO_ROOT / "pycodex/tui/chatwidget/turn_runtime.py").read_text(encoding="utf-8-sig")
    status_card_source = (REPO_ROOT / "pycodex/tui/status/card.py").read_text(encoding="utf-8-sig")
    status_controls_source = (REPO_ROOT / "pycodex/tui/chatwidget/status_controls.py").read_text(
        encoding="utf-8-sig"
    )
    history_ui_source = (REPO_ROOT / "pycodex/tui/app/history_ui.py").read_text(encoding="utf-8-sig")
    resize_source = (REPO_ROOT / "pycodex/tui/app/resize_reflow.py").read_text(encoding="utf-8-sig")
    messages_source = (REPO_ROOT / "pycodex/tui/history_cell/messages.py").read_text(encoding="utf-8-sig")
    session_source = (REPO_ROOT / "pycodex/tui/history_cell/session.py").read_text(encoding="utf-8-sig")
    footer_source = (REPO_ROOT / "pycodex/tui/bottom_pane/footer.py").read_text(encoding="utf-8-sig")
    slash_dispatch_source = (REPO_ROOT / "pycodex/tui/chatwidget/slash_dispatch.py").read_text(encoding="utf-8-sig")
    chat_composer_source = (REPO_ROOT / "pycodex/tui/bottom_pane/chat_composer/__init__.py").read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(source)
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    forbidden_ui_projection_imports = {
        "Buffer",
        "Color",
        "CommandPopup",
        "Line",
        "ListSelectionView",
        "Rect",
        "SelectionViewParams",
        "Span",
        "Style",
        "TerminalBottomPaneState",
        "TerminalPopupLine",
        "terminal_bottom_pane_frame",
        "terminal_bottom_pane_frame_buffer",
        "terminal_bottom_pane_frame_minimum_row_widths",
        "terminal_command_popup_lines",
        "terminal_selection_view_lines",
        "render_rows_with_col_width_mode",
    }
    forbidden_model_popup_state_imports = {
        "ModelPopupContext",
        "ModelPopupEvent",
        "ModelPreset",
        "open_model_popup",
        "terminal_apply_model_popup_event",
        "terminal_apply_model_popup_events",
        "terminal_model_popup_context_from_runtime",
        "terminal_model_presets_from_runtime",
        "TerminalModelPopupController",
    }
    assert imported_names.isdisjoint(forbidden_ui_projection_imports)
    assert imported_names.isdisjoint(forbidden_model_popup_state_imports)
    assert "terminal_bottom_pane_frame(" not in source
    assert "terminal_bottom_pane_frame_buffer(" not in source
    assert "render_rows_with_col_width_mode" not in source
    assert "reset_buffer_state" not in source
    assert "TerminalScrollRegionResetter" in imported_names
    assert "TerminalColumnProvider" in imported_names
    assert "reset_scroll_region" not in imported_names
    assert "self._scroll_region = TerminalScrollRegionResetter(stdout)" in source
    assert "self._terminal_columns = TerminalColumnProvider()" in source
    assert "reset_terminal_scroll_region=self._scroll_region.reset" in source
    assert "terminal_columns=self._terminal_columns.columns" in source
    assert "lambda: terminal_size().columns" not in source
    assert "lambda: reset_scroll_region(self.stdout)" not in source
    assert "run_external_repaint=self._bottom_pane.run_external_repaint" in source
    assert "self._bottom_pane.run_external_repaint(" not in source
    assert "def _replay_history_scrollback" not in source
    assert "repaint_history_viewport=self._resize_history.repaint_viewport" in source
    assert "TerminalChatWidgetStreamingRuntime" in source
    assert "assistant_delta=self._assistant_stream.handle_delta" in source
    assert "append_transcript_cell=self._transcript.append" in source
    assert "transcript_cells=lambda: tuple(self._transcript.cells)" in source
    assert "insert_stable_cell=self._agent_message_consolidation.append_transient" in source
    assert "apply_live_tail=self._bottom_pane.sync_active_tail" in source
    assert "consolidate_agent_message=self._agent_message_consolidation.consolidate" in source
    assert "TerminalAssistantStreamWriter" not in source
    assert "repaint_active_stream" not in source
    assert "TerminalAssistantStreamState" not in messages_source
    assert "terminal_assistant_stream_delta_plan" not in messages_source
    assert "write_terminal_history_stream_delta_and_flush" not in insert_history_source
    assert "finish_history_stream_projection_and_flush" not in insert_history_source
    assert "def _repaint_history_viewport_preserving_bottom_pane(" not in source
    assert "extra_projection_cell: str | None = None" not in source
    assert "*args: Any" not in source
    assert "**kwargs: Any" not in source
    assert "self._resize_history.repaint_viewport(*args, **kwargs)" not in source
    assert "def _set_exit_code(self, code: int) -> None:" in source
    assert "def _apply_history_state(" not in source
    assert "apply_history_state=self._history.apply_state" in source
    assert "apply_history_state=self._apply_history_state" not in source
    assert "def insert_replayed_lines(" in insert_history_source
    assert "insert_replayed_history_lines=self._history.insert_replayed_lines" in source
    assert "insert_replayed_history_lines=lambda materialized, reserve_active_bottom_pane" not in source
    assert "clear_bottom_pane=False" not in source
    assert "render_bottom_pane=False" not in source
    assert "class TerminalTurnSubmissionRunner" in turn_runtime_source
    assert "TerminalTurnSubmissionRunner" in imported_names
    assert "run_terminal_turn_submission" not in imported_names
    assert "self._turn_submission = TerminalTurnSubmissionRunner(" in source
    assert "self._turn_submission.submit(prompt)" in source
    assert "time.monotonic()" not in source
    assert "set_exit_code=self._set_exit_code" in source
    assert "apply_draft=self._bottom_pane.sync_draft" in source
    assert "apply_draft=self._bottom_pane.apply_draft" not in source
    assert "def clear_without_resize_check(" in controller_source
    assert "def render_without_resize_check(" in controller_source
    assert "clear_bottom_pane=self._bottom_pane.clear_without_resize_check" in source
    assert "render_bottom_pane=self._bottom_pane.render_without_resize_check" in source
    assert "render_bottom_pane=self._bottom_pane.render_after_history_repaint" in source
    assert "self._bottom_pane.clear(check_resize=False)" not in source
    assert "self._bottom_pane.render(check_resize=False)" not in source
    assert "self._bottom_pane.render_after_history_repaint(check_resize=False)" not in source
    assert "def hide_live_status(" in status_source
    assert "hide_live_status=self._status.hide_live_status" in source
    assert "hide_live_status=lambda: self._status.hide_inline_status(redraw_bottom_pane=True)" not in source
    assert "def render_turn_status_force(" in status_source
    assert "render_turn_status=self._status.render_turn_status_force" in source
    assert "render_turn_status=lambda: self._status.render_turn_status(force=True)" not in source
    assert "def composer_cursor_visible(" in status_source
    assert "def bind_render_bottom_pane(" in status_source
    assert "self._status.bind_render_bottom_pane(self._bottom_pane.render)" in source
    assert "render_bottom_pane=lambda: self._bottom_pane.render()" not in source
    assert "cursor_visible=self._status.composer_cursor_visible" in source
    assert "cursor_visible=lambda: not self._status.turn_active" not in source
    assert "class TerminalStatusCardWriter" in status_card_source
    assert "self._status_card = TerminalStatusCardWriter(" in source
    assert "class TerminalStatusCommandController" in status_controls_source
    assert "self._status_command = TerminalStatusCommandController(" in source
    assert "status=self._status_command.run" in source
    assert "status=self._status_card.run" not in source
    assert "RefreshRateLimits" not in source
    assert "status=lambda: run_terminal_status_card_from_runtime(" not in source
    assert "def for_terminal_runtime(" in history_ui_source
    assert "class TerminalSessionHeaderWriter" in history_ui_source
    assert "TerminalSessionHeaderWriter" in imported_names
    assert "self._session_header = TerminalSessionHeaderWriter(" in source
    assert "self._session_header.write()" in source
    assert "run_terminal_session_header_from_runtime" not in imported_names
    assert "run_terminal_session_header_from_runtime(" not in source
    assert "self._clear_ui = TerminalClearUiExecutor.for_terminal_runtime(" in source
    assert "clear_scrollback_and_visible_screen_ansi" not in source
    assert "clear_terminal=lambda:" not in source
    assert "render_header=lambda: run_terminal_session_header_from_runtime(" not in source
    assert "class TerminalIdleFooterTextProvider" in footer_source
    assert "TerminalIdleFooterTextProvider" in imported_names
    assert "run_terminal_idle_footer_text_from_runtime" not in imported_names
    assert "self._idle_footer = TerminalIdleFooterTextProvider(self.app_runtime)" in source
    assert "footer_text=self._idle_footer.text" in source
    assert "footer_text=lambda: run_terminal_idle_footer_text_from_runtime(" not in source
    assert "def run_terminal_composer_write_nonterminal_prompt(" in chat_composer_source
    assert "class TerminalComposerEffectRunner" in chat_composer_source
    assert "class TerminalComposerPromptReader" in chat_composer_source
    assert '"TerminalComposerPromptReader",' in chat_composer_source
    assert "self._composer_effects = TerminalComposerEffectRunner(" in source
    assert "self._composer_prompt = TerminalComposerPromptReader(" in source
    assert "writer=self.stdout" in source
    assert "def write_nonterminal_prompt(" in chat_composer_source
    assert "write_nonterminal_prompt=self._composer_effects.write_nonterminal_prompt" in source
    assert "write_nonterminal_prompt=self._write_nonterminal_prompt" not in source
    assert "submit=self._composer_effects.submit" in source
    assert "interrupt=self._composer_effects.interrupt" in source
    assert "eof=self._composer_effects.eof" in source
    assert "return self._composer_prompt.read()" in source
    assert "def _write_nonterminal_prompt(" not in source
    assert "submit=lambda line: run_terminal_composer_submit(" not in source
    assert "eof=lambda: run_terminal_composer_eof(" not in source
    assert "run_terminal_composer_read_prompt," not in source
    assert "run_terminal_composer_read_prompt(" not in source
    assert "run_terminal_composer_interrupt," not in source
    assert "run_terminal_composer_submit," not in source
    assert "run_terminal_composer_eof," not in source
    assert "run_terminal_composer_write_nonterminal_prompt," not in source
    assert 'stdout.write("\\n\\u203a ")' not in source
    assert 'stdout.write("\\n› ")' not in source
    assert 'lambda state: setattr(self._history, "state", state)' not in source
    assert 'lambda code: setattr(self, "exit_code", code)' not in source
    assert "TerminalBottomPaneController" in imported_names
    assert "TerminalLocalCommandDispatcher" in imported_names
    assert "TerminalPromptDispatcher" in imported_names
    assert "TerminalSlashCommandViewDispatcher" in imported_names
    assert "run_terminal_prompt_dispatch" not in imported_names
    assert "class TerminalPromptDispatcher" in slash_dispatch_source
    assert '"TerminalPromptDispatcher",' in slash_dispatch_source
    assert "self._prompt_dispatch = TerminalPromptDispatcher(" in source
    assert "prompt_dispatch = self._prompt_dispatch.dispatch(prompt)" in source
    assert "from .local_command import" not in source
    assert "command_result = self._local_commands.run(prompt)" not in source
    assert 'command_result == "exit"' not in source
    assert "if command_result:" not in source
    assert "prompt_dispatch = run_terminal_prompt_dispatch(" not in source
    assert "TerminalModelPopupController" not in imported_names
    assert "self._model_popup" not in source
    assert "TerminalSlashCommandViewDispatcher.for_model_popup" not in source
    assert "self._slash_command_views = TerminalSlashCommandViewDispatcher.for_runtime(" in source
    assert "submit_review=self._run_review_target" in source
    assert "open_command_view=self._slash_command_views.open_command_view" in source
    assert "on_selection_events=self._slash_command_views.handle_selection_events" in source
    assert "open_command_view=self._model_popup.open_command_view" not in source
    assert "on_selection_events=self._model_popup.handle_events" not in source
    assert "class TerminalUserPromptOutputWriter" in messages_source
    assert "TerminalUserPromptOutputWriter" in imported_names
    assert "run_terminal_user_prompt_output" not in imported_names
    assert "self._user_prompt_output = TerminalUserPromptOutputWriter(" in source
    user_prompt_writer_block = source.split("self._user_prompt_output = TerminalUserPromptOutputWriter(", 1)[1].split(
        "        self._protocol = TerminalProtocolEventDispatcher(",
        1,
    )[0]
    assert "def terminal_layout_active_state(" in resize_source
    assert "terminal_active=self._resize.terminal_layout_active_state" in user_prompt_writer_block
    assert "terminal_active=self._resize.terminal_layout_active," not in user_prompt_writer_block
    assert "self._user_prompt_output.write(prompt)" in source
    assert "run_terminal_user_prompt_output(" not in source
    assert "class TerminalStartupNoticesWriter" in session_source
    assert "TerminalStartupNoticesWriter" in imported_names
    assert "self._startup_notices = TerminalStartupNoticesWriter(" in source
    assert "self._startup_notices.write()" in source
    assert "run_terminal_startup_notices_from_runtime" not in imported_names
    assert "run_terminal_startup_notices_from_runtime(" not in source


def test_terminal_runtime_consumes_typed_turn_event_stream_boundary() -> None:
    # Rust owner: codex-tui::tui::event_stream owns submitted-turn event
    # polling and event/idle/closed classification. terminal_runtime may wire
    # callbacks into that loop, but the accepted stream shape should be the
    # typed event-stream boundary instead of an arbitrary adapter object.
    event_stream_source = (REPO_ROOT / "pycodex/tui/tui/event_stream.py").read_text(encoding="utf-8-sig")
    runtime_source = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(encoding="utf-8-sig")

    assert "class TerminalTurnEventStreamProtocol(Protocol)" in event_stream_source
    assert "def next_event(self, timeout: float | None = None) -> Any | None: ..." in event_stream_source
    assert "event_stream: TerminalTurnEventStreamProtocol" in event_stream_source
    assert "def terminal_stdin_is_terminal(stdin: TextIO) -> bool:" in event_stream_source
    assert "class TerminalTurnIdleTicker" in event_stream_source
    assert "class TerminalTurnEventLoopRunner" in event_stream_source
    assert '"terminal_stdin_is_terminal",' in event_stream_source
    assert '"TerminalTurnIdleTicker",' in event_stream_source
    assert '"TerminalTurnEventLoopRunner",' in event_stream_source
    assert '"TerminalTurnEventStreamProtocol",' in event_stream_source
    assert "TerminalTurnEventStreamProtocol," in runtime_source
    assert "TerminalTurnEventLoopRunner," in runtime_source
    assert "terminal_stdin_is_terminal," in runtime_source
    assert "self._stdin_is_terminal = terminal_stdin_is_terminal(stdin)" in runtime_source
    assert "self._turn_idle = TerminalTurnIdleTicker(" in runtime_source
    assert "self._turn_events = TerminalTurnEventLoopRunner(" in runtime_source
    assert "on_idle=self._turn_idle.tick" in runtime_source
    assert "self._turn_events.consume(event_stream)" in runtime_source
    assert 'getattr(stdin, "isatty", None)' not in runtime_source
    assert "on_idle=lambda: run_terminal_turn_idle_tick(" not in runtime_source
    assert "run_terminal_turn_idle_tick," not in runtime_source
    assert "run_terminal_turn_event_loop," not in runtime_source
    assert "run_terminal_turn_event_loop(" not in runtime_source
    assert "def _consume_events(self, event_stream: TerminalTurnEventStreamProtocol) -> None:" in runtime_source
    assert "event_stream: Any" not in event_stream_source
    assert "event_stream: Any" not in runtime_source


def test_terminal_approval_requests_use_rust_owned_typed_boundary() -> None:
    # Fixed Rust commit 1c7832f owners:
    # chatwidget::protocol_requests and chatwidget::tool_requests. Terminal
    # runtime may wire the generic request callback but must not own approval
    # variants or the former Python-only ExecApprovalRequested notification.
    app_runtime = (REPO_ROOT / "pycodex/tui/app/runtime.py").read_text(encoding="utf-8-sig")
    protocol = (REPO_ROOT / "pycodex/tui/chatwidget/protocol.py").read_text(encoding="utf-8-sig")
    protocol_requests = (REPO_ROOT / "pycodex/tui/chatwidget/protocol_requests.py").read_text(
        encoding="utf-8-sig"
    )
    tool_requests = (REPO_ROOT / "pycodex/tui/chatwidget/tool_requests.py").read_text(
        encoding="utf-8-sig"
    )
    request_user_input = (
        REPO_ROOT / "pycodex/tui/bottom_pane/request_user_input/__init__.py"
    ).read_text(encoding="utf-8-sig")
    view_stack = (REPO_ROOT / "pycodex/tui/bottom_pane/view_stack.py").read_text(
        encoding="utf-8-sig"
    )
    app_link_view = (REPO_ROOT / "pycodex/tui/bottom_pane/app_link_view.py").read_text(
        encoding="utf-8-sig"
    )
    terminal_runtime = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(
        encoding="utf-8-sig"
    )
    app_server_events = (
        REPO_ROOT / "pycodex/tui/app/app_server_events.py"
    ).read_text(encoding="utf-8-sig")
    thread_routing = (REPO_ROOT / "pycodex/tui/app/thread_routing.py").read_text(
        encoding="utf-8-sig"
    )
    thread_events = (REPO_ROOT / "pycodex/tui/app/thread_events.py").read_text(
        encoding="utf-8-sig"
    )
    pending_thread_approvals = (
        REPO_ROOT / "pycodex/tui/bottom_pane/pending_thread_approvals.py"
    ).read_text(encoding="utf-8-sig")

    assert "ExecApprovalRequested" not in app_runtime
    assert 'ServerRequest(\n                    "CommandExecutionRequestApproval"' in app_runtime
    assert "self.tool_requests = ToolRequestsModel(" in protocol
    assert "recent_auto_review_denials=self.review.recent_auto_review_denials" in protocol
    assert "def on_guardian_review_notification(" in protocol
    assert "self.tool_requests.history_sink = self.add_to_history" in protocol
    assert "SlashCommand.AUTO_REVIEW: TerminalAutoReviewDenialsPopupController" in (
        REPO_ROOT / "pycodex/tui/chatwidget/slash_dispatch.py"
    ).read_text(encoding="utf-8-sig")
    assert "AppCommand.approve_guardian_denied_action(event)" in (
        REPO_ROOT / "pycodex/tui/chatwidget/permission_popups.py"
    ).read_text(encoding="utf-8-sig")
    assert "handle_server_request(self, request)" in protocol
    assert "ExecApprovalRequestEvent.from_mapping(data)" in protocol_requests
    assert "elicitation_params_from_params(params)" in protocol_requests
    assert "user_input_params_from_params(params)" in protocol_requests
    assert "def on_elicitation_request(self, request_id: str, params: Any)" in protocol
    assert "def on_request_user_input(self, event: Any)" in protocol
    assert "self.user_input_request_sink(ev)" in tool_requests
    assert "self.mcp_form_request_sink(request)" in tool_requests
    assert "AppLinkViewParams.from_url_app_server_request(" in tool_requests
    assert "class AppLinkViewProjector" in app_link_view
    assert "target.open_url_in_browser(" in app_link_view
    assert "self.app_event_tx.user_input_answer(" in request_user_input
    assert "RequestUserInputResultCell.new(" in request_user_input
    assert "view_try_consume_user_input_request(active, view.request)" in view_stack
    assert "view_try_consume_mcp_request(active, view.request)" in view_stack
    assert "bind_interactive_request_sinks(" in terminal_runtime
    assert "handle_request=self.app_runtime.handle_server_request" in terminal_runtime
    assert 'else ("enqueue_thread_request",)' in app_server_events
    assert "def interactive_request_for_thread_request(" in thread_routing
    assert '"thread_label": thread_label' in thread_routing
    assert 'getattr(request, "id", None)' in thread_events
    assert "class PendingThreadApprovals" in pending_thread_approvals
    assert "bind_pending_thread_approvals_sink(" in terminal_runtime
    for approval_variant in (
        "CommandExecutionRequestApproval",
        "FileChangeRequestApproval",
        "PermissionsRequestApproval",
        "McpServerElicitationRequest",
        "ToolRequestUserInput",
    ):
        assert approval_variant not in terminal_runtime


def test_terminal_runtime_uses_typed_turn_history_append_boundary() -> None:
    # Rust owners: chatwidget::turn_runtime owns turn-start sequencing, while
    # app owns history mutation. terminal_runtime should pass the app-runtime
    # method through the typed callback boundary instead of reflectively
    # probing for optional history append behavior.
    runtime_source = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(encoding="utf-8-sig")
    turn_runtime_source = (REPO_ROOT / "pycodex/tui/chatwidget/turn_runtime.py").read_text(
        encoding="utf-8-sig"
    )

    assert "append_history=self.app_runtime.append_message_history_entry" in runtime_source
    assert 'getattr(self.app_runtime, "append_message_history_entry", None)' not in runtime_source
    assert "append_history: Callable[[str], Any] | None = None" in turn_runtime_source
    assert "append_history: Any = None" not in turn_runtime_source
    assert "if callable(append_history):" not in turn_runtime_source


def test_turn_input_and_side_approval_arbitration_use_rust_owned_anchors() -> None:
    # Fixed Rust commit 1c7832f owners: tui::event_stream multiplexes sources,
    # bottom_pane owns active-view Ctrl+C, app::side owns side return/discard,
    # and chatwidget::interaction owns Interrupt after bottom-pane refusal.
    event_stream = (REPO_ROOT / "pycodex/tui/tui/event_stream.py").read_text(
        encoding="utf-8-sig"
    )
    view_stack = (REPO_ROOT / "pycodex/tui/bottom_pane/view_stack.py").read_text(
        encoding="utf-8-sig"
    )
    app_runtime = (REPO_ROOT / "pycodex/tui/app/runtime.py").read_text(
        encoding="utf-8-sig"
    )
    terminal_runtime = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(
        encoding="utf-8-sig"
    )

    assert "class PrefixedTerminalInputSource" in event_stream
    assert "an approval request cannot be starved" in event_stream
    assert "def handle_ctrl_c(self) -> bool:" in view_stack
    assert "view_on_ctrl_c(view)" in view_stack
    assert "def active_side_parent_thread_id(self)" in app_runtime
    assert "def select_agent_thread_and_discard_side(" in app_runtime
    assert "if self.active_side_parent_thread_id() is None:" in app_runtime
    assert "self.app_runtime.maybe_return_from_side()" in terminal_runtime
    assert "self.app_runtime.submit_op(AppCommand.interrupt())" in terminal_runtime
    assert 'in {"interrupt", "escape"}' in terminal_runtime
    for variant in (
        "CommandExecutionRequestApproval",
        "FileChangeRequestApproval",
        "PermissionsRequestApproval",
    ):
        assert variant not in terminal_runtime


def test_structured_session_history_has_rust_owned_dynamic_anchors() -> None:
    # Fixed Rust commit 1c7832f owners: chatwidget protocol/command/tool/
    # streaming, exec_cell, history_cell patches/separators, and insert_history.
    protocol = (REPO_ROOT / "pycodex/tui/chatwidget/protocol.py").read_text(encoding="utf-8-sig")
    command = (REPO_ROOT / "pycodex/tui/chatwidget/command_lifecycle.py").read_text(encoding="utf-8-sig")
    patches = (REPO_ROOT / "pycodex/tui/history_cell/patches.py").read_text(encoding="utf-8-sig")
    runtime = (REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py").read_text(encoding="utf-8-sig")
    product_tests = _test_function_names(REPO_ROOT / "pycodex/tui/tui/tests/test_terminal_runtime.py")

    assert "class HistoryProjectionSink" in protocol
    assert "self.command_lifecycle.bind_history_projection(" in protocol
    assert "new_reasoning_summary_block(" in protocol
    assert "new_patch_event(" in protocol
    assert "FinalMessageSeparator.new(" in protocol
    assert "SemanticExecCell = ExecCell" in command
    assert "class SemanticExecCell" not in command
    assert "render_diff_summary(changes, cwd, int(wrap_cols))" in patches
    assert "command_started=self._history.write_cell" not in runtime
    assert "command_completed=self._history.write_cell" not in runtime
    assert "test_terminal_runtime_renders_structured_complex_task_history" in product_tests


def test_model_popup_consumes_opaque_selection_events_at_owner_boundary() -> None:
    # Rust owner: chatwidget::model_popups owns interpreting model-popup
    # selection actions. bottom_pane/list_selection_view may carry opaque
    # action events, but terminal adapters should not type those events as
    # model-specific values or inspect them locally.
    source = (REPO_ROOT / "pycodex/tui/chatwidget/model_popups.py").read_text(encoding="utf-8-sig")

    assert "def handle_events(self, events: Tuple[object, ...]) -> Any:" in source
    assert "events: Tuple[object, ...]," in source
    assert "def handle_events(self, events: Tuple[Any, ...]) -> Any:" not in source
    assert "events: Tuple[Any, ...]," not in source
    assert "def open_command_view(" not in source
    assert "if isinstance(event, ModelPopupEvent):" in source


def test_permissions_popup_routing_matches_rust_module_ownership() -> None:
    # Rust permission_popups::open_permissions_popup is the slash entry point;
    # permissions_menu is reached only from its explicit-profile-mode branch.
    slash_dispatch = (
        REPO_ROOT / "pycodex/tui/chatwidget/slash_dispatch.py"
    ).read_text(encoding="utf-8-sig")
    permission_popups = (
        REPO_ROOT / "pycodex/tui/chatwidget/permission_popups.py"
    ).read_text(encoding="utf-8-sig")
    list_selection = (
        REPO_ROOT / "pycodex/tui/bottom_pane/list_selection_view.py"
    ).read_text(encoding="utf-8-sig")

    assert "TerminalPermissionsPopupController" in permission_popups
    assert "from .permissions_menu import TerminalPermissionsPopupController" not in slash_dispatch
    assert "from .permission_popups import (" in slash_dispatch
    assert "if self._explicit_profile_mode:" in permission_popups
    assert "view.accept()" in list_selection


def _literal_all(tree: ast.AST) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        return {str(item) for item in value}
    return set()


def _test_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
