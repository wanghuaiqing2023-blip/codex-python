from __future__ import annotations

import asyncio

from pycodex.extension_api import (
    ExtensionData,
    ExtensionRegistryBuilder,
    PromptFragment,
    PromptSlot,
    empty_extension_registry,
)


class State:
    pass


def test_extension_data_is_type_keyed_and_scope_owned() -> None:
    # Rust source: codex-rs/ext/extension-api/src/state.rs
    store = ExtensionData("turn-1")
    first = State()

    assert store.level_id() == "turn-1"
    assert store.get(State) is None
    assert store.insert(first) is None
    assert store.get(State) is first
    assert store.get_or_init(State, State) is first
    assert store.remove(State) is first
    assert store.get(State) is None


def test_registry_builder_keeps_contributor_categories_separate() -> None:
    # Rust source: codex-rs/ext/extension-api/src/registry.rs
    contributor = object()
    builder = ExtensionRegistryBuilder.new()
    builder.turn_lifecycle_contributor(contributor)
    builder.token_usage_contributor(contributor)
    builder.tool_contributor(contributor)
    registry = builder.build()

    assert registry.turn_lifecycle_contributors() == (contributor,)
    assert registry.token_usage_contributors() == (contributor,)
    assert registry.tool_contributors() == (contributor,)
    assert registry.thread_lifecycle_contributors() == ()
    assert empty_extension_registry().tool_contributors() == ()


def test_approval_review_uses_first_claiming_contributor() -> None:
    calls: list[str] = []

    class Contributor:
        def __init__(self, name: str, result: str | None) -> None:
            self.name = name
            self.result = result

        async def contribute(self, session_store, thread_store, prompt):
            calls.append(self.name)
            return self.result

    builder = ExtensionRegistryBuilder.new()
    builder.approval_review_contributor(Contributor("first", None))
    builder.approval_review_contributor(Contributor("second", "approved"))
    builder.approval_review_contributor(Contributor("third", "denied"))
    registry = builder.build()

    result = asyncio.run(
        registry.approval_review(ExtensionData("session"), ExtensionData("thread"), "prompt")
    )

    assert result == "approved"
    assert calls == ["first", "second"]


def test_prompt_fragment_constructors_preserve_rust_slots() -> None:
    fragment = PromptFragment.developer_capability("tools")
    assert fragment == PromptFragment(PromptSlot.DEVELOPER_CAPABILITIES, "tools")
