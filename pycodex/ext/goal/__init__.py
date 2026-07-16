"""Python coordinate for the upstream ``codex-goal-extension`` crate."""

from .extension import GoalExtension, GoalExtensionConfig, install_with_backend
from .runtime import GoalRuntimeHandle, PreviousGoalSnapshot
from .spec import CREATE_GOAL_TOOL_NAME, GET_GOAL_TOOL_NAME, UPDATE_GOAL_TOOL_NAME
from .tool import CreateGoalRequest

__all__ = [
    "CREATE_GOAL_TOOL_NAME",
    "GET_GOAL_TOOL_NAME",
    "UPDATE_GOAL_TOOL_NAME",
    "CreateGoalRequest",
    "GoalExtension",
    "GoalExtensionConfig",
    "GoalRuntimeHandle",
    "PreviousGoalSnapshot",
    "install_with_backend",
]
