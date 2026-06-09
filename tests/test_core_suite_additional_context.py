from types import SimpleNamespace

from pycodex.core.context import AdditionalContextDeveloperFragment, AdditionalContextUserFragment
from pycodex.core.session.turn.runtime import _additional_context_response_items
from pycodex.core.state.additional_context import AdditionalContextStore
from pycodex.protocol import AdditionalContextEntry, AdditionalContextKind, ContentItem, ResponseItem


def _texts_by_role(items: tuple[ResponseItem, ...], role: str) -> list[str]:
    return [
        content.text
        for item in items
        if item.type == "message" and item.role == role
        for content in item.content
        if content.type == "input_text"
    ]


def test_additional_context_is_model_visible_but_not_a_user_message_item():
    # Rust source: codex/codex-rs/core/tests/suite/additional_context.rs
    # Rust test: additional_context_is_model_visible_but_not_a_user_message_item.
    sess = SimpleNamespace()

    context_items = _additional_context_response_items(
        sess,
        {
            "browser_info": AdditionalContextEntry(value="tab one", kind=AdditionalContextKind.UNTRUSTED),
            "automation_info": AdditionalContextEntry(value="run one", kind=AdditionalContextKind.APPLICATION),
        },
    )
    user_message = ResponseItem.message("user", (ContentItem.input_text("inspect the active tab"),))

    assert _texts_by_role(context_items, "developer") == ["<automation_info>run one</automation_info>"]
    assert _texts_by_role(context_items + (user_message,), "user") == [
        "<external_browser_info>tab one</external_browser_info>",
        "inspect the active tab",
    ]
    assert user_message.content == (ContentItem.input_text("inspect the active tab"),)


def test_external_context_like_user_text_remains_a_user_message_item():
    # Rust source: codex/codex-rs/core/tests/suite/additional_context.rs
    # Rust test: external_context_like_user_text_remains_a_user_message_item.
    user_message = ResponseItem.message("user", (ContentItem.input_text("<external_api>"),))

    assert _texts_by_role((user_message,), "user") == ["<external_api>"]
    assert not AdditionalContextUserFragment.matches_text("<external_api>")


def test_additional_context_trust_controls_message_role():
    # Rust source: codex/codex-rs/core/tests/suite/additional_context.rs
    # Rust test: additional_context_trust_controls_message_role.
    store = AdditionalContextStore()

    items = tuple(
        ResponseItem.from_response_input_item(item)
        for item in store.merge(
            {
                "browser_info": AdditionalContextEntry(value="tab one", kind=AdditionalContextKind.UNTRUSTED),
                "automation_info": AdditionalContextEntry(value="run one", kind=AdditionalContextKind.APPLICATION),
            }
        )
    )

    assert _texts_by_role(items, "developer") == ["<automation_info>run one</automation_info>"]
    assert _texts_by_role(items, "user") == ["<external_browser_info>tab one</external_browser_info>"]


def test_additional_context_is_deduplicated_between_turns_while_retained():
    # Rust source: codex/codex-rs/core/tests/suite/additional_context.rs
    # Rust test: additional_context_is_deduplicated_between_turns_while_retained.
    sess = SimpleNamespace()
    additional_context = {
        "browser_info": AdditionalContextEntry(value="same tab", kind=AdditionalContextKind.UNTRUSTED)
    }

    first_items = _additional_context_response_items(sess, additional_context)
    second_items = _additional_context_response_items(sess, additional_context)

    assert _texts_by_role(first_items, "user") == ["<external_browser_info>same tab</external_browser_info>"]
    assert second_items == ()
    assert sess._additional_context_values == {"browser_info": ("untrusted", "same tab")}


def test_additional_context_removes_one_value_while_adding_another():
    # Rust source: codex/codex-rs/core/tests/suite/additional_context.rs
    # Rust test: additional_context_removes_one_value_while_adding_another.
    sess = SimpleNamespace()

    first_items = _additional_context_response_items(
        sess,
        {
            "automation_info": AdditionalContextEntry(value="run one", kind=AdditionalContextKind.UNTRUSTED),
            "browser_info": AdditionalContextEntry(value="tab one", kind=AdditionalContextKind.UNTRUSTED),
        },
    )
    second_items = _additional_context_response_items(
        sess,
        {
            "automation_info": AdditionalContextEntry(value="run one", kind=AdditionalContextKind.UNTRUSTED),
            "terminal_info": AdditionalContextEntry(value="pty one", kind=AdditionalContextKind.UNTRUSTED),
        },
    )
    third_items = _additional_context_response_items(
        sess,
        {
            "automation_info": AdditionalContextEntry(value="run one", kind=AdditionalContextKind.UNTRUSTED),
            "browser_info": AdditionalContextEntry(value="tab one", kind=AdditionalContextKind.UNTRUSTED),
            "terminal_info": AdditionalContextEntry(value="pty one", kind=AdditionalContextKind.UNTRUSTED),
        },
    )

    assert _texts_by_role(first_items, "user") == [
        "<external_automation_info>run one</external_automation_info>",
        "<external_browser_info>tab one</external_browser_info>",
    ]
    assert _texts_by_role(second_items, "user") == ["<external_terminal_info>pty one</external_terminal_info>"]
    assert _texts_by_role(third_items, "user") == ["<external_browser_info>tab one</external_browser_info>"]


def test_additional_context_values_are_truncated_before_model_input():
    # Rust source: codex/codex-rs/core/tests/suite/additional_context.rs
    # Rust test: additional_context_values_are_truncated_before_model_input.
    long_browser_value = f"browser-head-{'b' * 40_000}browser-tail"
    long_automation_value = f"automation-head-{'a' * 40_000}automation-tail"

    browser_text = AdditionalContextUserFragment.new("browser_info", long_browser_value).render()
    automation_text = AdditionalContextDeveloperFragment.new("automation_info", long_automation_value).render()

    assert browser_text.startswith(f"<external_browser_info>browser-head-{'b' * 1024}")
    assert browser_text.endswith("browser-tail</external_browser_info>")
    assert "tokens truncated" in browser_text
    assert len(browser_text) < len(f"<external_browser_info>{long_browser_value}</external_browser_info>")

    assert automation_text.startswith(f"<automation_info>automation-head-{'a' * 1024}")
    assert automation_text.endswith("automation-tail</automation_info>")
    assert "tokens truncated" in automation_text
    assert len(automation_text) < len(f"<automation_info>{long_automation_value}</automation_info>")
