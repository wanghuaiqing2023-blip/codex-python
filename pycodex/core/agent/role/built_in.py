"""Built-in agent roles from ``core/src/agent/role.rs::built_in``."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path

from pycodex.core.config.agent_roles import AgentRoleConfig


EXPLORER_TOML = ""
AWAITER_TOML = '''background_terminal_max_timeout = 3600000
model_reasoning_effort = "low"
developer_instructions="""You are an awaiter.
Your role is to await the completion of a specific command or task and report its status only when it is finished.

Behavior rules:

1. When given a command or task identifier, you must:
   - Execute or await it using the appropriate tool
   - Continue awaiting until the task reaches a terminal state.

2. You must NOT:
   - Modify the task.
   - Interpret or optimize the task.
   - Perform unrelated actions.
   - Stop awaiting unless explicitly instructed.

3. Awaiting behavior:
   - If the task is still running, continue polling using tool calls.
   - Use repeated tool calls if necessary.
   - Do not hallucinate completion.
   - Use long timeouts when awaiting for something. If you need multiple awaits, increase the timeouts/yield times exponentially.

4. If asked for status:
   - Return the current known status.
   - Immediately resume awaiting afterward.

5. Termination:
   - Only exit awaiting when:
     - The task completes successfully, OR
     - The task fails, OR
     - You receive an explicit stop instruction.

You must behave deterministically and conservatively.
"""
'''


_CONFIGS: Mapping[str, AgentRoleConfig] = OrderedDict(
    (
        ("default", AgentRoleConfig(description="Default agent.")),
        (
            "explorer",
            AgentRoleConfig(
                description="""Use `explorer` for specific codebase questions.
Explorers are fast and authoritative.
They must be used to ask specific, well-scoped questions on the codebase.
Rules:
- In order to avoid redundant work, you should avoid exploring the same problem that explorers have already covered. Typically, you should trust the explorer results without additional verification. You are still allowed to inspect the code yourself to gain the needed context!
- You are encouraged to spawn up multiple explorers in parallel when you have multiple distinct questions to ask about the codebase that can be answered independently. This allows you to get more information faster without waiting for one question to finish before asking the next. While waiting for the explorer results, you can continue working on other local tasks that do not depend on those results. This parallelism is a key advantage of delegation, so use it whenever you have multiple questions to ask.
- Reuse existing explorers for related questions.""",
                config_file=Path("explorer.toml"),
            ),
        ),
        (
            "worker",
            AgentRoleConfig(
                description="""Use for execution and production work.
Typical tasks:
- Implement part of a feature
- Fix tests or bugs
- Split large refactors into independent chunks
Rules:
- Explicitly assign **ownership** of the task (files / responsibility). When the subtask involves code changes, you should clearly specify which files or modules the worker is responsible for. This helps avoid merge conflicts and ensures accountability. For example, you can say "Worker 1 is responsible for updating the authentication module, while Worker 2 will handle the database layer." By defining clear ownership, you can delegate more effectively and reduce coordination overhead.
- Always tell workers they are **not alone in the codebase**, and they should not revert the edits made by others, and they should adjust their implementation to accommodate the changes made by others. This is important because there may be multiple workers making changes in parallel, and they need to be aware of each other's work to avoid conflicts and ensure a cohesive final product.""",
            ),
        ),
    )
)


def configs() -> Mapping[str, AgentRoleConfig]:
    """Return the cached built-in role declarations in BTreeMap order."""

    return _CONFIGS


def config_file_contents(path: str | Path) -> str | None:
    """Resolve a built-in role config path to its embedded contents."""

    path_text = Path(path).as_posix()
    if path_text == "explorer.toml":
        return EXPLORER_TOML
    if path_text == "awaiter.toml":
        return AWAITER_TOML
    return None


__all__ = ["AWAITER_TOML", "EXPLORER_TOML", "config_file_contents", "configs"]
