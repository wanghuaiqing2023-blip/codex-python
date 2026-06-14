from pycodex.tui.model_migration import (
    MigrationMenuOption,
    ModelMigrationCopy,
    ModelMigrationOutcome,
    ModelMigrationScreen,
    fill_migration_markdown,
    is_ctrl_exit_combo,
    migration_copy_for_models,
    run_model_migration_prompt,
)


class FrameRequester:
    def __init__(self) -> None:
        self.count = 0

    def schedule_frame(self) -> None:
        self.count += 1


def test_migration_copy_prefers_markdown_and_fills_placeholders() -> None:
    # Rust source: migration_copy_for_models early markdown branch.
    copy = migration_copy_for_models(
        "old",
        "new",
        model_link=None,
        migration_copy="ignored",
        migration_markdown="from {model_from} to {model_to}",
        target_display_name="New",
        target_description=None,
        can_opt_out=True,
    )
    assert copy.heading == []
    assert copy.content == []
    assert copy.can_opt_out is True
    assert copy.markdown == "from old to new"
    assert fill_migration_markdown("{model_from}/{model_to}", "a", "b") == "a/b"


def test_migration_copy_default_content_and_no_opt_out_continue() -> None:
    copy = migration_copy_for_models(
        "gpt-5",
        "gpt-5.1",
        model_link="https://example.test/model",
        migration_copy=None,
        migration_markdown=None,
        target_display_name="gpt-5.1",
        target_description="Broad world knowledge.",
        can_opt_out=False,
    )
    assert copy.heading == ["Codex just got an upgrade. Introducing gpt-5.1."]
    assert copy.content[0] == "We recommend switching from gpt-5 to gpt-5.1."
    assert "Broad world knowledge. Learn more about gpt-5.1 at https://example.test/model" in copy.content
    assert copy.content[-1] == "Press enter to continue"


def test_migration_copy_empty_description_uses_recommended_fallback() -> None:
    copy = migration_copy_for_models(
        "gpt-5",
        "gpt-5.1",
        model_link=None,
        migration_copy=None,
        migration_markdown=None,
        target_display_name="gpt-5.1",
        target_description="",
        can_opt_out=False,
    )

    assert "gpt-5.1 is recommended for better performance and reliability." in copy.content


def test_migration_copy_custom_copy_and_opt_out_line() -> None:
    copy = migration_copy_for_models(
        "old",
        "new",
        model_link=None,
        migration_copy="Custom copy.",
        migration_markdown=None,
        target_display_name="New",
        target_description="ignored",
        can_opt_out=True,
    )
    assert "We recommend switching" not in "\n".join(copy.content)
    assert copy.content == ["Custom copy.", "", "You can continue using old if you prefer."]


def test_escape_key_accepts_prompt() -> None:
    # Rust test: escape_key_accepts_prompt.
    screen = ModelMigrationScreen.new(FrameRequester(), ModelMigrationCopy(can_opt_out=True))
    screen.handle_key("Esc")
    assert screen.is_done()
    assert screen.outcome() is ModelMigrationOutcome.ACCEPTED


def test_selecting_use_existing_model_rejects_upgrade() -> None:
    # Rust test: selecting_use_existing_model_rejects_upgrade.
    screen = ModelMigrationScreen.new(FrameRequester(), ModelMigrationCopy(can_opt_out=True))
    screen.handle_key("Down")
    screen.handle_key("Enter")
    assert screen.is_done()
    assert screen.outcome() is ModelMigrationOutcome.REJECTED


def test_menu_keys_and_ctrl_exit_combo() -> None:
    requester = FrameRequester()
    screen = ModelMigrationScreen.new(requester, ModelMigrationCopy(can_opt_out=True))
    screen.handle_key("j")
    assert screen.highlighted_option is MigrationMenuOption.USE_EXISTING_MODEL
    screen.handle_key("k")
    assert screen.highlighted_option is MigrationMenuOption.TRY_NEW_MODEL
    assert requester.count == 2

    screen = ModelMigrationScreen.new(requester, ModelMigrationCopy(can_opt_out=True))
    screen.handle_key("2")
    assert screen.outcome() is ModelMigrationOutcome.REJECTED

    assert is_ctrl_exit_combo({"code": "c", "modifiers": {"CONTROL"}})
    screen = ModelMigrationScreen.new(requester, ModelMigrationCopy(can_opt_out=True))
    screen.handle_key({"code": "d", "modifiers": {"CONTROL"}})
    assert screen.outcome() is ModelMigrationOutcome.EXIT


def test_non_opt_out_accepts_enter_or_escape_only_and_ignores_release() -> None:
    screen = ModelMigrationScreen.new(FrameRequester(), ModelMigrationCopy(can_opt_out=False))
    screen.handle_key({"code": "Enter", "kind": "Release"})
    assert not screen.is_done()
    screen.handle_key({"code": "Enter"})
    assert screen.outcome() is ModelMigrationOutcome.ACCEPTED


def test_semantic_render_keeps_long_url_tail_visible_when_narrow() -> None:
    long_url = "https://example.test/api/v1/projects/alpha/releases/2026/builds/1234567890/tail42"
    screen = ModelMigrationScreen.new(
        FrameRequester(),
        ModelMigrationCopy(can_opt_out=False, markdown=long_url),
    )
    rendered = "\n".join(screen.render_ref(area_width=24))
    assert "tail42" in rendered


def test_run_model_migration_prompt_enters_alt_screen_draws_and_leaves() -> None:
    class Tui:
        def __init__(self) -> None:
            self.entered = 0
            self.left = 0
            self.draws = 0
            self.requester = FrameRequester()

        def frame_requester(self) -> FrameRequester:
            return self.requester

        def enter_alt_screen(self) -> None:
            self.entered += 1

        def leave_alt_screen(self) -> None:
            self.left += 1

        def draw(self, _render) -> None:
            self.draws += 1

        async def event_stream(self):
            yield {"kind": "Draw"}
            yield {"kind": "Paste", "text": "ignored"}
            yield {"kind": "Key", "key": "Esc"}

    async def run() -> None:
        tui = Tui()
        outcome = await run_model_migration_prompt(tui, ModelMigrationCopy(can_opt_out=True))
        assert outcome is ModelMigrationOutcome.ACCEPTED
        assert tui.entered == 1
        assert tui.left == 1
        assert tui.draws == 2

    import asyncio

    asyncio.run(run())
