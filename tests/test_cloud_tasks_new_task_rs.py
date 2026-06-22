from pycodex.cloud_tasks import NEW_TASK_HINT_ITEMS, NewTaskPage
from pycodex.tui.public_widgets.composer_input import ComposerInput


def test_new_task_page_new_sets_composer_hints_and_state():
    # Rust crate/module: codex-cloud-tasks/src/new_task.rs::NewTaskPage::new.
    page = NewTaskPage.new("env-1", 3)

    assert isinstance(page.composer, ComposerInput)
    assert page.composer.hint_items == NEW_TASK_HINT_ITEMS
    assert page.submitting is False
    assert page.env_id == "env-1"
    assert page.best_of_n == 3


def test_new_task_page_default_matches_rust_default_impl():
    # Rust crate/module: codex-cloud-tasks/src/new_task.rs::Default for NewTaskPage.
    page = NewTaskPage.default()

    assert page.composer.hint_items == NEW_TASK_HINT_ITEMS
    assert page.submitting is False
    assert page.env_id is None
    assert page.best_of_n == 1
