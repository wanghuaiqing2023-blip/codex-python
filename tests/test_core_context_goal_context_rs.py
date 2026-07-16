'''Parity tests for codex-core::context::goal_context.'''

from pycodex.core.context.goal_context import GoalContext


def test_goal_context_renders_hidden_user_fragment() -> None:
    # Rust crate: codex-core
    # Rust module: src/context/goal_context.rs::GoalContext
    # Contract: context.goal_context.render
    context = GoalContext.new('continue the task')

    assert context.role() == 'user'
    assert context.markers() == ('<goal_context>', '</goal_context>')
    assert context.body() == '\ncontinue the task\n'
    assert context.render() == '<goal_context>\ncontinue the task\n</goal_context>'


def test_goal_context_response_item_keeps_rendered_prompt_hidden_in_user_input() -> None:
    # Rust crate: codex-core
    # Rust module: src/context/goal_context.rs::ContextualUserFragment impl
    # Contract: context.goal_context.response_input
    item = GoalContext.new('finish safely').into_response_input_item()

    assert item.role == 'user'
    assert item.content[0].text == '<goal_context>\nfinish safely\n</goal_context>'


def test_goal_context_marked_text_matching_uses_fragment_registration_rules() -> None:
    # Rust crate: codex-core
    # Rust module: src/context/goal_context.rs::GoalContext::type_markers
    # Contract: context.goal_context.markers
    assert GoalContext.matches_text('  <GOAL_CONTEXT>prompt</goal_context>\n')
    assert not GoalContext.matches_text('<goal_context>prompt</other_context>')
