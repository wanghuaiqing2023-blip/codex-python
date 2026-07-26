"""Agent job helpers ported from Codex core."""

from __future__ import annotations

import csv
import asyncio
import inspect
import json
from datetime import datetime, timezone
import time
import threading
import uuid
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Protocol

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.core.agent import exceeds_thread_spawn_depth_limit, next_thread_spawn_depth
from pycodex.core.agent.status import is_final
from pycodex.protocol import (
    SessionSource,
    SubAgentSource,
    ThreadId,
    ToolName,
    UserInput,
)
from pycodex.protocol.error import CodexErr

JsonValue = Any

SPAWN_AGENTS_ON_CSV_TOOL_NAME = "spawn_agents_on_csv"
REPORT_AGENT_JOB_RESULT_TOOL_NAME = "report_agent_job_result"
DEFAULT_AGENT_JOB_CONCURRENCY = 16
MAX_AGENT_JOB_CONCURRENCY = 64
DEFAULT_AGENT_JOB_ITEM_TIMEOUT_SECONDS = 60 * 30
STATUS_POLL_INTERVAL_SECONDS = 0.25



def single_local_environment_cwd(turn: Any) -> Path:
    environments = getattr(turn, "environments", None)
    if environments is None:
        raise FunctionCallError.respond_to_model(
            "spawn_agents_on_csv requires exactly one local environment"
        )

    turn_environments = tuple(getattr(environments, "turn_environments", ()) or ())
    if len(turn_environments) != 1:
        raise FunctionCallError.respond_to_model(
            "spawn_agents_on_csv requires exactly one local environment"
        )
    environment = turn_environments[0]
    env_value = getattr(environment, "environment", None)
    if env_value is not None:
        is_remote = getattr(env_value, "is_remote", None)
        if callable(is_remote) and is_remote():
            raise FunctionCallError.respond_to_model(
                "spawn_agents_on_csv is not supported for remote environments"
            )

    cwd = getattr(environment, "cwd", None)
    if not isinstance(cwd, Path):
        raise TypeError("environment cwd must be a path")
    return cwd

