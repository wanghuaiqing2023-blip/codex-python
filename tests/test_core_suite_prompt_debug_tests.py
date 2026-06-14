
"""Parity test for Rust core/tests/suite/prompt_debug_tests.rs."""

from __future__ import annotations

import pytest

from pycodex.core.prompt_debug import build_prompt_input_from_session
from pycodex.protocol import UserInput
from tests.test_core_prompt_debug import Session


@pytest.mark.asyncio
async def test_build_prompt_input_includes_context_and_user_message() -> None:
    """Rust test: build_prompt_input_includes_context_and_user_message."""

    session = Session()
    session.turn_context.user_instructions = "Project-specific test instructions"
    session.turn_context.cwd = "C:/debug-project"

    prompt_input = await build_prompt_input_from_session(
        session,
        (UserInput.text_input("hello from debug prompt"),),
    )

    assert prompt_input[-1].role == "user"
    assert prompt_input[-1].content[0].text == "hello from debug prompt"
    assert any(
        any("Project-specific test instructions" in (content.text or "") for content in item.content)
        for item in prompt_input
        if item.type == "message"
    )
