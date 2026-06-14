"""Runtime keymap resolution for Rust ``codex-tui::keymap``.

This module ports the Rust module's semantic resolver contract rather than its
macro-heavy implementation shape.  Python uses string key codes and frozenset
modifiers as the crossterm-compatible semantic model.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="keymap", source="codex/codex-rs/tui/src/keymap.rs")

MOD_CONTROL = "CONTROL"
MOD_ALT = "ALT"
MOD_SHIFT = "SHIFT"


@dataclass(frozen=True, order=True)
class KeyBinding:
    code: str
    modifiers: FrozenSet[str] = field(default_factory=frozenset)

    def parts(self) -> Tuple[str, FrozenSet[str]]:
        return self.code, self.modifiers


def _kb(code: str, *mods: str) -> KeyBinding:
    return KeyBinding(_canonical_key_code(code), frozenset(_canonical_modifier(mod) for mod in mods if mod))


def plain(code: str) -> KeyBinding:
    return _kb(code)


def ctrl(code: str) -> KeyBinding:
    return _kb(code, MOD_CONTROL)


def alt(code: str) -> KeyBinding:
    return _kb(code, MOD_ALT)


def shift(code: str) -> KeyBinding:
    return _kb(code, MOD_SHIFT)


def ctrl_shift(code: str) -> KeyBinding:
    return _kb(code, MOD_CONTROL, MOD_SHIFT)


@dataclass
class AppKeymap:
    open_transcript: List[KeyBinding] = field(default_factory=list)
    open_external_editor: List[KeyBinding] = field(default_factory=list)
    copy: List[KeyBinding] = field(default_factory=list)
    clear_terminal: List[KeyBinding] = field(default_factory=list)
    toggle_vim_mode: List[KeyBinding] = field(default_factory=list)
    toggle_fast_mode: List[KeyBinding] = field(default_factory=list)
    toggle_raw_output: List[KeyBinding] = field(default_factory=list)


@dataclass
class ChatKeymap:
    interrupt_turn: List[KeyBinding] = field(default_factory=list)
    decrease_reasoning_effort: List[KeyBinding] = field(default_factory=list)
    increase_reasoning_effort: List[KeyBinding] = field(default_factory=list)
    edit_queued_message: List[KeyBinding] = field(default_factory=list)


@dataclass
class ComposerKeymap:
    submit: List[KeyBinding] = field(default_factory=list)
    queue: List[KeyBinding] = field(default_factory=list)
    toggle_shortcuts: List[KeyBinding] = field(default_factory=list)
    history_search_previous: List[KeyBinding] = field(default_factory=list)
    history_search_next: List[KeyBinding] = field(default_factory=list)


@dataclass
class EditorKeymap:
    insert_newline: List[KeyBinding] = field(default_factory=list)
    move_left: List[KeyBinding] = field(default_factory=list)
    move_right: List[KeyBinding] = field(default_factory=list)
    move_up: List[KeyBinding] = field(default_factory=list)
    move_down: List[KeyBinding] = field(default_factory=list)
    move_word_left: List[KeyBinding] = field(default_factory=list)
    move_word_right: List[KeyBinding] = field(default_factory=list)
    move_line_start: List[KeyBinding] = field(default_factory=list)
    move_line_end: List[KeyBinding] = field(default_factory=list)
    delete_backward: List[KeyBinding] = field(default_factory=list)
    delete_forward: List[KeyBinding] = field(default_factory=list)
    delete_backward_word: List[KeyBinding] = field(default_factory=list)
    delete_forward_word: List[KeyBinding] = field(default_factory=list)
    kill_line_start: List[KeyBinding] = field(default_factory=list)
    kill_whole_line: List[KeyBinding] = field(default_factory=list)
    kill_line_end: List[KeyBinding] = field(default_factory=list)
    yank: List[KeyBinding] = field(default_factory=list)


@dataclass
class VimNormalKeymap:
    enter_insert: List[KeyBinding] = field(default_factory=list)
    append_after_cursor: List[KeyBinding] = field(default_factory=list)
    append_line_end: List[KeyBinding] = field(default_factory=list)
    insert_line_start: List[KeyBinding] = field(default_factory=list)
    open_line_below: List[KeyBinding] = field(default_factory=list)
    open_line_above: List[KeyBinding] = field(default_factory=list)
    move_left: List[KeyBinding] = field(default_factory=list)
    move_right: List[KeyBinding] = field(default_factory=list)
    move_up: List[KeyBinding] = field(default_factory=list)
    move_down: List[KeyBinding] = field(default_factory=list)
    move_word_forward: List[KeyBinding] = field(default_factory=list)
    move_word_backward: List[KeyBinding] = field(default_factory=list)
    move_word_end: List[KeyBinding] = field(default_factory=list)
    move_line_start: List[KeyBinding] = field(default_factory=list)
    move_line_end: List[KeyBinding] = field(default_factory=list)
    delete_char: List[KeyBinding] = field(default_factory=list)
    delete_to_line_end: List[KeyBinding] = field(default_factory=list)
    change_to_line_end: List[KeyBinding] = field(default_factory=list)
    yank_line: List[KeyBinding] = field(default_factory=list)
    paste_after: List[KeyBinding] = field(default_factory=list)
    start_delete_operator: List[KeyBinding] = field(default_factory=list)
    start_yank_operator: List[KeyBinding] = field(default_factory=list)
    start_change_operator: List[KeyBinding] = field(default_factory=list)
    cancel_operator: List[KeyBinding] = field(default_factory=list)


@dataclass
class VimOperatorKeymap:
    delete_line: List[KeyBinding] = field(default_factory=list)
    yank_line: List[KeyBinding] = field(default_factory=list)
    motion_left: List[KeyBinding] = field(default_factory=list)
    motion_right: List[KeyBinding] = field(default_factory=list)
    motion_up: List[KeyBinding] = field(default_factory=list)
    motion_down: List[KeyBinding] = field(default_factory=list)
    motion_word_forward: List[KeyBinding] = field(default_factory=list)
    motion_word_backward: List[KeyBinding] = field(default_factory=list)
    motion_word_end: List[KeyBinding] = field(default_factory=list)
    motion_line_start: List[KeyBinding] = field(default_factory=list)
    motion_line_end: List[KeyBinding] = field(default_factory=list)
    select_inner_text_object: List[KeyBinding] = field(default_factory=list)
    select_around_text_object: List[KeyBinding] = field(default_factory=list)
    cancel: List[KeyBinding] = field(default_factory=list)


@dataclass
class VimTextObjectKeymap:
    word: List[KeyBinding] = field(default_factory=list)
    big_word: List[KeyBinding] = field(default_factory=list)
    parentheses: List[KeyBinding] = field(default_factory=list)
    brackets: List[KeyBinding] = field(default_factory=list)
    braces: List[KeyBinding] = field(default_factory=list)
    double_quote: List[KeyBinding] = field(default_factory=list)
    single_quote: List[KeyBinding] = field(default_factory=list)
    backtick: List[KeyBinding] = field(default_factory=list)
    cancel: List[KeyBinding] = field(default_factory=list)


@dataclass
class PagerKeymap:
    scroll_up: List[KeyBinding] = field(default_factory=list)
    scroll_down: List[KeyBinding] = field(default_factory=list)
    page_up: List[KeyBinding] = field(default_factory=list)
    page_down: List[KeyBinding] = field(default_factory=list)
    half_page_up: List[KeyBinding] = field(default_factory=list)
    half_page_down: List[KeyBinding] = field(default_factory=list)
    jump_top: List[KeyBinding] = field(default_factory=list)
    jump_bottom: List[KeyBinding] = field(default_factory=list)
    close: List[KeyBinding] = field(default_factory=list)
    close_transcript: List[KeyBinding] = field(default_factory=list)


@dataclass
class ListKeymap:
    move_up: List[KeyBinding] = field(default_factory=list)
    move_down: List[KeyBinding] = field(default_factory=list)
    move_left: List[KeyBinding] = field(default_factory=list)
    move_right: List[KeyBinding] = field(default_factory=list)
    page_up: List[KeyBinding] = field(default_factory=list)
    page_down: List[KeyBinding] = field(default_factory=list)
    jump_top: List[KeyBinding] = field(default_factory=list)
    jump_bottom: List[KeyBinding] = field(default_factory=list)
    accept: List[KeyBinding] = field(default_factory=list)
    cancel: List[KeyBinding] = field(default_factory=list)


@dataclass
class ApprovalKeymap:
    open_fullscreen: List[KeyBinding] = field(default_factory=list)
    open_thread: List[KeyBinding] = field(default_factory=list)
    approve: List[KeyBinding] = field(default_factory=list)
    approve_for_session: List[KeyBinding] = field(default_factory=list)
    approve_for_prefix: List[KeyBinding] = field(default_factory=list)
    deny: List[KeyBinding] = field(default_factory=list)
    decline: List[KeyBinding] = field(default_factory=list)
    cancel: List[KeyBinding] = field(default_factory=list)


@dataclass
class RuntimeKeymap:
    app: AppKeymap
    chat: ChatKeymap
    composer: ComposerKeymap
    editor: EditorKeymap
    vim_normal: VimNormalKeymap
    vim_operator: VimOperatorKeymap
    vim_text_object: VimTextObjectKeymap
    pager: PagerKeymap
    list: ListKeymap
    approval: ApprovalKeymap

    @classmethod
    def defaults(cls) -> "RuntimeKeymap":
        return cls.built_in_defaults()

    @classmethod
    def built_in_defaults(cls) -> "RuntimeKeymap":
        return cls(
            app=AppKeymap(
                open_transcript=[ctrl("t")],
                open_external_editor=[ctrl("g")],
                copy=[ctrl("o")],
                clear_terminal=[ctrl("l")],
                toggle_vim_mode=[],
                toggle_fast_mode=[],
                toggle_raw_output=[alt("r")],
            ),
            chat=ChatKeymap(
                interrupt_turn=[plain("Esc")],
                decrease_reasoning_effort=[alt(",")],
                increase_reasoning_effort=[alt(".")],
                edit_queued_message=[alt("Up"), shift("Left")],
            ),
            composer=ComposerKeymap(
                submit=[plain("Enter")],
                queue=[plain("Tab")],
                toggle_shortcuts=[plain("?"), shift("?")],
                history_search_previous=[ctrl("r")],
                history_search_next=[ctrl("s")],
            ),
            editor=EditorKeymap(
                insert_newline=[ctrl("j"), ctrl("m"), plain("Enter"), shift("Enter"), alt("Enter")],
                move_left=[plain("Left"), ctrl("b")],
                move_right=[plain("Right"), ctrl("f")],
                move_up=[plain("Up"), ctrl("p")],
                move_down=[plain("Down"), ctrl("n")],
                move_word_left=[alt("b"), alt("Left"), ctrl("Left")],
                move_word_right=[alt("f"), alt("Right"), ctrl("Right")],
                move_line_start=[plain("Home"), ctrl("a")],
                move_line_end=[plain("End"), ctrl("e")],
                delete_backward=[plain("Backspace"), shift("Backspace"), ctrl("h")],
                delete_forward=[plain("Delete"), shift("Delete"), ctrl("d")],
                delete_backward_word=[
                    alt("Backspace"),
                    ctrl("Backspace"),
                    ctrl_shift("Backspace"),
                    ctrl("w"),
                    KeyBinding("h", frozenset(["CONTROL", "ALT"])),
                ],
                delete_forward_word=[alt("Delete"), ctrl("Delete"), ctrl_shift("Delete"), alt("d")],
                kill_line_start=[ctrl("u")],
                kill_whole_line=[],
                kill_line_end=[ctrl("k")],
                yank=[ctrl("y")],
            ),
            vim_normal=VimNormalKeymap(
                enter_insert=[plain("i"), plain("Insert")],
                append_after_cursor=[plain("a")],
                append_line_end=[shift("a"), plain("A")],
                insert_line_start=[shift("i"), plain("I")],
                open_line_below=[plain("o")],
                open_line_above=[shift("o"), plain("O")],
                move_left=[plain("h"), plain("Left")],
                move_right=[plain("l"), plain("Right")],
                move_up=[plain("k"), plain("Up")],
                move_down=[plain("j"), plain("Down")],
                move_word_forward=[plain("w")],
                move_word_backward=[plain("b")],
                move_word_end=[plain("e")],
                move_line_start=[plain("0")],
                move_line_end=[plain("$"), shift("$")],
                delete_char=[plain("x")],
                delete_to_line_end=[shift("d"), plain("D")],
                change_to_line_end=[shift("c"), plain("C")],
                yank_line=[shift("y"), plain("Y")],
                paste_after=[plain("p")],
                start_delete_operator=[plain("d")],
                start_yank_operator=[plain("y")],
                start_change_operator=[plain("c")],
                cancel_operator=[plain("Esc")],
            ),
            vim_operator=VimOperatorKeymap(
                delete_line=[plain("d")],
                yank_line=[plain("y")],
                motion_left=[plain("h")],
                motion_right=[plain("l")],
                motion_up=[plain("k")],
                motion_down=[plain("j")],
                motion_word_forward=[plain("w")],
                motion_word_backward=[plain("b")],
                motion_word_end=[plain("e")],
                motion_line_start=[plain("0")],
                motion_line_end=[plain("$"), shift("$")],
                select_inner_text_object=[plain("i")],
                select_around_text_object=[plain("a")],
                cancel=[plain("Esc")],
            ),
            vim_text_object=VimTextObjectKeymap(
                word=[plain("w")],
                big_word=[shift("w"), plain("W")],
                parentheses=[plain("("), shift("("), plain(")"), shift(")"), plain("b")],
                brackets=[plain("["), plain("]")],
                braces=[plain("{"), shift("{"), plain("}"), shift("}"), shift("b"), plain("B")],
                double_quote=[plain('"'), shift('"')],
                single_quote=[plain("'")],
                backtick=[plain("`")],
                cancel=[plain("Esc")],
            ),
            pager=PagerKeymap(
                scroll_up=[plain("Up"), plain("k")],
                scroll_down=[plain("Down"), plain("j")],
                page_up=[plain("PageUp"), shift(" "), ctrl("b")],
                page_down=[plain("PageDown"), plain(" "), ctrl("f")],
                half_page_up=[ctrl("u")],
                half_page_down=[ctrl("d")],
                jump_top=[plain("Home")],
                jump_bottom=[plain("End")],
                close=[plain("q"), ctrl("c")],
                close_transcript=[ctrl("t")],
            ),
            list=ListKeymap(
                move_up=[plain("Up"), ctrl("p"), ctrl("k"), plain("k")],
                move_down=[plain("Down"), ctrl("n"), ctrl("j"), plain("j")],
                move_left=[plain("Left"), ctrl("h")],
                move_right=[plain("Right"), ctrl("l")],
                page_up=[plain("PageUp"), ctrl("b")],
                page_down=[plain("PageDown"), ctrl("f")],
                jump_top=[plain("Home")],
                jump_bottom=[plain("End")],
                accept=[plain("Enter")],
                cancel=[plain("Esc")],
            ),
            approval=ApprovalKeymap(
                open_fullscreen=[ctrl("a"), ctrl_shift("a")],
                open_thread=[plain("o")],
                approve=[plain("y")],
                approve_for_session=[plain("a")],
                approve_for_prefix=[plain("p")],
                deny=[plain("d")],
                decline=[plain("Esc"), plain("n")],
                cancel=[plain("c")],
            ),
        )

    @classmethod
    def from_config(cls, keymap: Any) -> "RuntimeKeymap":
        runtime = cls.built_in_defaults()
        defaults = cls.built_in_defaults()
        global_config = _field(keymap, "global", {})

        _resolve_context(runtime.app, defaults.app, global_config, global_config, "global")
        _resolve_context(runtime.chat, defaults.chat, _field(keymap, "chat", {}), None, "chat")
        _resolve_context(runtime.composer, defaults.composer, _field(keymap, "composer", {}), global_config, "composer", _COMPOSER_GLOBAL_FALLBACK)
        _resolve_context(runtime.editor, defaults.editor, _field(keymap, "editor", {}), None, "editor")
        _resolve_context(runtime.vim_normal, defaults.vim_normal, _field(keymap, "vim_normal", {}), None, "vim_normal")
        _resolve_context(runtime.vim_operator, defaults.vim_operator, _field(keymap, "vim_operator", {}), None, "vim_operator")
        _resolve_context(runtime.vim_text_object, defaults.vim_text_object, _field(keymap, "vim_text_object", {}), None, "vim_text_object")
        _resolve_context(runtime.pager, defaults.pager, _field(keymap, "pager", {}), None, "pager")
        _resolve_context(runtime.list, defaults.list, _field(keymap, "list", {}), None, "list")
        _resolve_context(runtime.approval, defaults.approval, _field(keymap, "approval", {}), None, "approval")

        runtime._prune_new_default_overlaps(keymap)
        runtime.validate_conflicts()
        return runtime

    def _prune_new_default_overlaps(self, keymap: Any) -> None:
        app_config = _field(keymap, "global", {})
        list_config = _field(keymap, "list", {})
        approval_config = _field(keymap, "approval", {})
        vim_normal_config = _field(keymap, "vim_normal", {})
        vim_operator_config = _field(keymap, "vim_operator", {})

        # Rust preserves explicitly configured legacy bindings and prunes newer
        # defaults that would otherwise conflict with those configured keys.
        if _field(list_config, "page_up", None) is None:
            self.list.page_up = _prune_if_configured(self.list.page_up, list_config, ["move_up"])
        if _field(list_config, "page_down", None) is None:
            self.list.page_down = _prune_if_configured(self.list.page_down, list_config, ["move_down"])
            self.list.page_down = _prune_bindings(self.list.page_down, configured_bindings_to_preserve(_field(app_config, "copy", None), "tui.keymap.global.copy"))
        if _field(list_config, "jump_top", None) is None:
            self.list.jump_top = _prune_bindings(self.list.jump_top, configured_bindings_to_preserve(_field(approval_config, "approve", None), "tui.keymap.approval.approve"))
        if _field(vim_normal_config, "start_change_operator", None) is None:
            self.vim_normal.start_change_operator = _prune_bindings(
                self.vim_normal.start_change_operator,
                configured_bindings_to_preserve(_field(vim_normal_config, "move_left", None), "tui.keymap.vim_normal.move_left"),
            )
        op_preserved = set()
        op_preserved.update(configured_bindings_to_preserve(_field(vim_operator_config, "motion_left", None), "tui.keymap.vim_operator.motion_left"))
        op_preserved.update(configured_bindings_to_preserve(_field(vim_operator_config, "motion_right", None), "tui.keymap.vim_operator.motion_right"))
        if _field(vim_operator_config, "select_inner_text_object", None) is None:
            self.vim_operator.select_inner_text_object = _prune_bindings(self.vim_operator.select_inner_text_object, op_preserved)
        if _field(vim_operator_config, "select_around_text_object", None) is None:
            self.vim_operator.select_around_text_object = _prune_bindings(self.vim_operator.select_around_text_object, op_preserved)

    def validate_conflicts(self) -> None:
        validate_unique("editor", self.editor)
        validate_unique("vim_normal", self.vim_normal)
        validate_unique("vim_operator", self.vim_operator)
        validate_unique("vim_text_object", self.vim_text_object)
        validate_unique("pager", self.pager)
        validate_unique("list", self.list)
        validate_unique("approval", self.approval)
        validate_no_shadow_with_allowed_overlaps("main", [self.app, self.chat, self.composer])
        validate_no_shadow_pairs(
            "app",
            [
                ("open_transcript", self.app.open_transcript),
                ("open_external_editor", self.app.open_external_editor),
                ("copy", self.app.copy),
                ("clear_terminal", self.app.clear_terminal),
                ("toggle_vim_mode", self.app.toggle_vim_mode),
                ("toggle_fast_mode", self.app.toggle_fast_mode),
                ("toggle_raw_output", self.app.toggle_raw_output),
            ],
            [
                ("list.move_up", self.list.move_up),
                ("list.move_down", self.list.move_down),
                ("list.move_left", self.list.move_left),
                ("list.move_right", self.list.move_right),
                ("list.page_up", self.list.page_up),
                ("list.page_down", self.list.page_down),
                ("list.jump_top", self.list.jump_top),
                ("list.jump_bottom", self.list.jump_bottom),
                ("list.accept", self.list.accept),
                ("list.cancel", self.list.cancel),
                ("approval.open_fullscreen", self.approval.open_fullscreen),
                ("approval.open_thread", self.approval.open_thread),
                ("approval.approve", self.approval.approve),
                ("approval.approve_for_session", self.approval.approve_for_session),
                ("approval.approve_for_prefix", self.approval.approve_for_prefix),
                ("approval.deny", self.approval.deny),
                ("approval.decline", self.approval.decline),
                ("approval.cancel", self.approval.cancel),
            ],
            {("clear_terminal", "list.move_right", ctrl("l"))},
        )
        validate_no_shadow_pairs(
            "main",
            [
                ("open_transcript", self.app.open_transcript),
                ("open_external_editor", self.app.open_external_editor),
                ("copy", self.app.copy),
                ("clear_terminal", self.app.clear_terminal),
                ("chat.interrupt_turn", self.chat.interrupt_turn),
                ("chat.decrease_reasoning_effort", self.chat.decrease_reasoning_effort),
                ("chat.increase_reasoning_effort", self.chat.increase_reasoning_effort),
                ("composer.submit", self.composer.submit),
                ("toggle_vim_mode", self.app.toggle_vim_mode),
                ("toggle_fast_mode", self.app.toggle_fast_mode),
                ("toggle_raw_output", self.app.toggle_raw_output),
                ("composer.history_search_previous", self.composer.history_search_previous),
            ],
            [
                ("editor.insert_newline", self.editor.insert_newline),
                ("editor.move_left", self.editor.move_left),
                ("editor.move_right", self.editor.move_right),
                ("editor.move_up", self.editor.move_up),
                ("editor.move_down", self.editor.move_down),
                ("editor.move_word_left", self.editor.move_word_left),
                ("editor.move_word_right", self.editor.move_word_right),
                ("editor.move_line_start", self.editor.move_line_start),
                ("editor.move_line_end", self.editor.move_line_end),
                ("editor.delete_backward", self.editor.delete_backward),
                ("editor.delete_forward", self.editor.delete_forward),
                ("editor.delete_backward_word", self.editor.delete_backward_word),
                ("editor.delete_forward_word", self.editor.delete_forward_word),
                ("editor.kill_line_start", self.editor.kill_line_start),
                ("editor.kill_whole_line", self.editor.kill_whole_line),
                ("editor.kill_line_end", self.editor.kill_line_end),
                ("editor.yank", self.editor.yank),
            ],
            {("composer.submit", "editor.insert_newline", plain("Enter"))},
        )
        validate_no_shadow_pairs(
            "approval_overlay",
            [
                ("list.move_up", self.list.move_up),
                ("list.move_down", self.list.move_down),
                ("list.move_left", self.list.move_left),
                ("list.move_right", self.list.move_right),
                ("list.page_up", self.list.page_up),
                ("list.page_down", self.list.page_down),
                ("list.jump_top", self.list.jump_top),
                ("list.jump_bottom", self.list.jump_bottom),
                ("list.accept", self.list.accept),
                ("list.cancel", self.list.cancel),
            ],
            [
                ("approval.open_fullscreen", self.approval.open_fullscreen),
                ("approval.open_thread", self.approval.open_thread),
                ("approval.approve", self.approval.approve),
                ("approval.approve_for_session", self.approval.approve_for_session),
                ("approval.approve_for_prefix", self.approval.approve_for_prefix),
                ("approval.deny", self.approval.deny),
                ("approval.decline", self.approval.decline),
                ("approval.cancel", self.approval.cancel),
            ],
            {("list.cancel", "approval.decline", plain("Esc"))},
        )
        validate_no_reserved("main", [self.app, self.chat, self.composer], MAIN_RESERVED_BINDINGS, {"chat.interrupt_turn": {plain("Esc")}})
        validate_no_reserved("transcript", [self.pager], TRANSCRIPT_BACKTRACK_RESERVED_BINDINGS)
        validate_interrupt_turn_question_navigation(self.chat, self.list)


def primary_binding(bindings: Sequence[KeyBinding]) -> Optional[KeyBinding]:
    return bindings[0] if bindings else None


def validate_unique(scope: str, keymap: Any) -> None:
    seen = {}
    for action in _field_names(keymap):
        for binding in getattr(keymap, action):
            if binding in seen:
                raise ValueError(_conflict_message(scope, seen[binding], action))
            seen[binding] = action


def validate_no_shadow_with_allowed_overlaps(scope: str, keymaps: Sequence[Any]) -> None:
    seen = {}
    for keymap in keymaps:
        prefix = keymap.__class__.__name__.replace("Keymap", "").lower()
        for action in _field_names(keymap):
            for binding in getattr(keymap, action):
                name = "%s.%s" % (prefix, action)
                if binding in seen:
                    raise ValueError(_conflict_message(scope, seen[binding], name))
                seen[binding] = name


def validate_no_shadow_pairs(
    scope: str,
    primary: Sequence[Tuple[str, Sequence[KeyBinding]]],
    secondary: Sequence[Tuple[str, Sequence[KeyBinding]]],
    allowed: Optional[Set[Tuple[str, str, KeyBinding]]] = None,
) -> None:
    allowed = allowed or set()
    seen = {}
    for action, bindings in primary:
        for binding in bindings:
            if binding not in seen:
                seen[binding] = action
    for action, bindings in secondary:
        for binding in bindings:
            if binding not in seen:
                continue
            previous = seen[binding]
            if (previous, action, binding) in allowed or (action, previous, binding) in allowed:
                continue
            raise ValueError(_conflict_message(scope, previous, action))


def validate_no_reserved(scope: str, keymaps: Sequence[Any], reserved: Dict[str, KeyBinding], exceptions: Optional[Dict[str, Set[KeyBinding]]] = None) -> None:
    exceptions = exceptions or {}
    reserved_by_binding = {binding: name for name, binding in reserved.items()}
    for keymap in keymaps:
        prefix = keymap.__class__.__name__.replace("Keymap", "").lower()
        for action in _field_names(keymap):
            action_name = "%s.%s" % (prefix, action)
            for binding in getattr(keymap, action):
                if binding in exceptions.get(action_name, set()):
                    continue
                reserved_name = reserved_by_binding.get(binding)
                if reserved_name is not None:
                    raise ValueError(_conflict_message(scope, action_name, reserved_name))


def validate_interrupt_turn_question_navigation(chat: ChatKeymap, list_keymap: ListKeymap) -> None:
    """Reject interrupt bindings that collide with question navigation.

    Rust validates `chat.interrupt_turn` against the list left/right bindings
    used by request-user-input question navigation. This is narrower than a
    full chat-vs-list conflict pass: list up/down/page/jump keys are allowed to
    coexist elsewhere, but left/right question navigation must stay distinct
    from the interrupt shortcut.
    """

    navigation = set(list_keymap.move_left) | set(list_keymap.move_right)
    for binding in chat.interrupt_turn:
        if binding in navigation:
            raise ValueError(_conflict_message("request_user_input", "chat.interrupt_turn", "list.question_navigation"))


def resolve_bindings_with_global_fallback(configured: Any, global_configured: Any, defaults: Sequence[KeyBinding], path: str) -> List[KeyBinding]:
    if configured is not None:
        return parse_bindings(configured, path)
    if global_configured is not None:
        return parse_bindings(global_configured, path)
    return list(defaults)


def resolve_bindings(configured: Any, defaults: Sequence[KeyBinding], path: str) -> List[KeyBinding]:
    if configured is None:
        return list(defaults)
    return parse_bindings(configured, path)


def configured_bindings_to_preserve(configured: Any, path: str = "tui.keymap") -> Set[KeyBinding]:
    return set(parse_bindings(configured, path)) if configured is not None else set()


def resolve_new_default_bindings(defaults: Sequence[KeyBinding], configured_legacy: Any = None, path: str = "tui.keymap") -> List[KeyBinding]:
    return _prune_bindings(list(defaults), configured_bindings_to_preserve(configured_legacy, path))


def parse_bindings(spec: Any, path: str = "tui.keymap") -> List[KeyBinding]:
    if isinstance(spec, str):
        specs = [spec]
    elif isinstance(spec, (list, tuple)):
        specs = list(spec)
    elif hasattr(spec, "items"):
        specs = list(spec)
    elif hasattr(spec, "value"):
        return parse_bindings(spec.value, path)
    else:
        raise ValueError("%s: expected string or array of keybindings" % path)
    parsed = []
    for item in specs:
        text = item.value if hasattr(item, "value") else str(item)
        binding = parse_keybinding(text)
        if binding is None:
            raise ValueError("%s: invalid key binding %r" % (path, text))
        if binding not in parsed:
            parsed.append(binding)
    return parsed


def parse_keybinding(spec: str) -> Optional[KeyBinding]:
    text = spec.strip().lower()
    if text == "":
        return None
    parts = text.split("-")
    modifiers = set()
    while parts and parts[0] in {"ctrl", "control", "alt", "shift"}:
        head = parts.pop(0)
        modifiers.add(MOD_CONTROL if head in {"ctrl", "control"} else head.upper())
    if not parts:
        return None
    key_text = "-".join(parts)
    code = _parse_key_code(key_text)
    if code is None:
        return None
    return KeyBinding(code, frozenset(modifiers))


def _parse_key_code(text: str) -> Optional[str]:
    named = {
        "tab": "Tab",
        "backspace": "Backspace",
        "esc": "Esc",
        "escape": "Esc",
        "delete": "Delete",
        "insert": "Insert",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "home": "Home",
        "end": "End",
        "page-up": "PageUp",
        "pageup": "PageUp",
        "page-down": "PageDown",
        "pagedown": "PageDown",
        "enter": "Enter",
        "space": " ",
        "minus": "-",
        "-": "-",
        "?": "?",
    }
    if text in named:
        return named[text]
    if text.startswith("f") and text[1:].isdigit():
        value = int(text[1:])
        return "F%d" % value if 1 <= value <= 12 else None
    if len(text) == 1:
        return text
    return None


def one(spec: str) -> List[str]:
    return [spec]


def expect_conflict(keymap: Any, *_names: str) -> None:
    try:
        RuntimeKeymap.from_config(keymap)
    except ValueError:
        return
    raise AssertionError("expected conflict")


def _resolve_context(target: Any, defaults: Any, local_config: Any, global_config: Any, context: str, global_actions: Optional[Set[str]] = None) -> None:
    global_actions = global_actions or set()
    for action in _field_names(target):
        configured = _field(local_config, action, None)
        default = getattr(defaults, action)
        if context == "global":
            setattr(target, action, resolve_bindings(configured, default, "tui.keymap.global.%s" % action))
        elif action in global_actions:
            setattr(
                target,
                action,
                resolve_bindings_with_global_fallback(configured, _field(global_config, action, None), default, "tui.keymap.%s.%s" % (context, action)),
            )
        else:
            setattr(target, action, resolve_bindings(configured, default, "tui.keymap.%s.%s" % (context, action)))


def _prune_if_configured(bindings: List[KeyBinding], config: Any, legacy_actions: Sequence[str]) -> List[KeyBinding]:
    preserved = set()
    for action in legacy_actions:
        preserved.update(configured_bindings_to_preserve(_field(config, action, None), "tui.keymap.%s" % action))
    return _prune_bindings(bindings, preserved)


def _prune_bindings(bindings: Sequence[KeyBinding], preserved: Iterable[KeyBinding]) -> List[KeyBinding]:
    preserved_set = set(preserved)
    return [binding for binding in bindings if binding not in preserved_set]


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _field_names(obj: Any) -> List[str]:
    return [item.name for item in fields(obj)]


def _canonical_modifier(modifier: str) -> str:
    text = str(modifier).upper()
    if text in {"CTRL", "CONTROL"}:
        return MOD_CONTROL
    if text == "ALT":
        return MOD_ALT
    if text == "SHIFT":
        return MOD_SHIFT
    return text


def _canonical_key_code(code: str) -> str:
    text = str(code)
    named = {
        "esc": "Esc",
        "escape": "Esc",
        "enter": "Enter",
        "insert": "Insert",
        "left": "Left",
        "right": "Right",
        "up": "Up",
        "down": "Down",
        "home": "Home",
        "end": "End",
        "pageup": "PageUp",
        "page-up": "PageUp",
        "pagedown": "PageDown",
        "page-down": "PageDown",
        "backspace": "Backspace",
        "delete": "Delete",
        "tab": "Tab",
    }
    lower = text.lower()
    if lower in named:
        return named[lower]
    return text


def _conflict_message(scope: str, first: str, second: str) -> str:
    return "conflicting key binding in %s: %s conflicts with %s" % (scope, first, second)


MAIN_RESERVED_BINDINGS = {"fixed.paste_image": ctrl("v")}
TRANSCRIPT_BACKTRACK_RESERVED_BINDINGS = {"fixed.transcript_edit_previous": plain("Left")}


_COMPOSER_GLOBAL_FALLBACK = {"submit", "queue", "toggle_shortcuts"}


__all__ = [
    "AppKeymap",
    "ApprovalKeymap",
    "ChatKeymap",
    "ComposerKeymap",
    "EditorKeymap",
    "KeyBinding",
    "ListKeymap",
    "MAIN_RESERVED_BINDINGS",
    "PagerKeymap",
    "RUST_MODULE",
    "RuntimeKeymap",
    "TRANSCRIPT_BACKTRACK_RESERVED_BINDINGS",
    "VimNormalKeymap",
    "VimOperatorKeymap",
    "VimTextObjectKeymap",
    "alt",
    "configured_bindings_to_preserve",
    "ctrl",
    "ctrl_shift",
    "expect_conflict",
    "one",
    "parse_bindings",
    "parse_keybinding",
    "plain",
    "primary_binding",
    "resolve_bindings",
    "resolve_bindings_with_global_fallback",
    "resolve_new_default_bindings",
    "shift",
    "validate_interrupt_turn_question_navigation",
    "validate_no_reserved",
    "validate_no_shadow_pairs",
    "validate_no_shadow_with_allowed_overlaps",
    "validate_unique",
]
