"""Rust-aligned owner for ``codex-rollout-trace::model.session``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

class RolloutStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"

class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABORTED = "aborted"

@dataclass(frozen=True)
class ExecutionWindow:
    started_at_unix_ms: int
    started_seq: RawEventSeq
    ended_at_unix_ms: int | None = None
    ended_seq: RawEventSeq | None = None
    status: ExecutionStatus = ExecutionStatus.RUNNING

@dataclass(frozen=True)
class AgentOrigin:
    type: str
    parent_thread_id: AgentThreadId | None = None
    spawn_edge_id: EdgeId | None = None
    task_name: str | None = None
    agent_role: str | None = None

    @classmethod
    def Root(cls) -> "AgentOrigin":
        return cls("root")

    @classmethod
    def Spawned(
        cls,
        *,
        parent_thread_id: AgentThreadId,
        spawn_edge_id: EdgeId,
        task_name: str,
        agent_role: str,
    ) -> "AgentOrigin":
        return cls(
            "spawned",
            parent_thread_id=parent_thread_id,
            spawn_edge_id=spawn_edge_id,
            task_name=task_name,
            agent_role=agent_role,
        )

@dataclass
class AgentThread:
    thread_id: AgentThreadId
    agent_path: AgentPath
    nickname: str | None
    origin: AgentOrigin
    execution: ExecutionWindow
    default_model: str | None
    conversation_item_ids: list[ConversationItemId] = field(default_factory=list)

@dataclass
class CodexTurn:
    codex_turn_id: CodexTurnId
    thread_id: AgentThreadId
    execution: ExecutionWindow
    input_item_ids: list[ConversationItemId] = field(default_factory=list)
