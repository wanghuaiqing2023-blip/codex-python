"""Rust integration parity for ``core/tests/suite/hierarchical_agents.rs``.

The Rust integration tests enable ``Feature::ChildAgentsMd`` and inspect the
user-visible ``# AGENTS.md instructions for ...`` message sent to the model.
Python covers the same contract by composing ``AgentsMdManager`` output with the
``UserInstructions`` contextual wrapper.
"""

from __future__ import annotations

from pathlib import Path

from pycodex.core.agents_md import AgentsMdConfig, AgentsMdManager, HIERARCHICAL_AGENTS_MESSAGE
from pycodex.core.context import UserInstructions

HIERARCHICAL_AGENTS_SNIPPET = "Files called AGENTS.md commonly appear in many places inside a container"


def render_instructions_message(cwd: Path, text: str) -> str:
    return UserInstructions(str(cwd), text).render()


def test_hierarchical_agents_appends_to_project_doc_in_user_instructions(tmp_path: Path) -> None:
    # Rust test: hierarchical_agents_appends_to_project_doc_in_user_instructions.
    (tmp_path / "AGENTS.md").write_text("be nice", encoding="utf-8")
    manager = AgentsMdManager(AgentsMdConfig(cwd=tmp_path, child_agents_md=True))

    text = manager.user_instructions()
    assert text is not None
    instructions = render_instructions_message(tmp_path, text)

    assert instructions.startswith("# AGENTS.md instructions for ")
    assert "be nice" in instructions
    assert HIERARCHICAL_AGENTS_SNIPPET in instructions
    assert instructions.index(HIERARCHICAL_AGENTS_SNIPPET) > instructions.index("be nice")
    assert instructions.endswith("</INSTRUCTIONS>")


def test_hierarchical_agents_emits_when_no_project_doc(tmp_path: Path) -> None:
    # Rust test: hierarchical_agents_emits_when_no_project_doc.
    manager = AgentsMdManager(AgentsMdConfig(cwd=tmp_path, child_agents_md=True))

    text = manager.user_instructions()
    assert text == HIERARCHICAL_AGENTS_MESSAGE
    instructions = render_instructions_message(tmp_path, text)

    assert instructions.startswith("# AGENTS.md instructions for ")
    assert HIERARCHICAL_AGENTS_SNIPPET in instructions
    assert instructions.endswith("</INSTRUCTIONS>")
