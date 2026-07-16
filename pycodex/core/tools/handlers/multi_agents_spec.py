"""Multi-agent tool specs ported from Codex core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

JsonValue = Any

MULTI_AGENT_V1_NAMESPACE = "multi_agent_v1"
MULTI_AGENT_V1_NAMESPACE_DESCRIPTION = "Tools for spawning and managing sub-agents."

SPAWN_AGENT_INHERITED_MODEL_GUIDANCE = (
    "Spawned agents inherit your current model by default. Omit `model` to use that "
    "preferred default; set `model` only when an explicit override is needed."
)
SPAWN_AGENT_MODEL_OVERRIDE_DESCRIPTION = (
    "Optional model override for the new agent. Leave unset to inherit the same model "
    "as the parent, which is the preferred default. Only set this when the user "
    "explicitly asks for a different model or the task clearly requires one."
)
SPAWN_AGENT_SERVICE_TIER_OVERRIDE_DESCRIPTION = (
    "Optional service tier override for the new agent. Leave unset unless the user explicitly asks for one."
)
MAX_MODEL_OVERRIDES_IN_SPAWN_AGENT_DESCRIPTION = 5

MIN_WAIT_TIMEOUT_MS = 10_000
DEFAULT_WAIT_TIMEOUT_MS = 30_000
MAX_WAIT_TIMEOUT_MS = 3_600_000


def _usize(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _i64(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{field_name} is outside i64 range")
    return value


@dataclass(frozen=True)
class SpawnAgentToolOptions:
    available_models: tuple[JsonValue, ...] = ()
    agent_type_description: str = ""
    hide_agent_type_model_reasoning: bool = False
    include_usage_hint: bool = False
    usage_hint_text: str | None = None
    max_concurrent_threads_per_session: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.available_models, str):
            raise TypeError("available_models must be an iterable of model presets")
        object.__setattr__(self, "available_models", tuple(self.available_models))
        if not isinstance(self.agent_type_description, str):
            raise TypeError("agent_type_description must be a string")
        if not isinstance(self.hide_agent_type_model_reasoning, bool):
            raise TypeError("hide_agent_type_model_reasoning must be a bool")
        if not isinstance(self.include_usage_hint, bool):
            raise TypeError("include_usage_hint must be a bool")
        if self.usage_hint_text is not None and not isinstance(self.usage_hint_text, str):
            raise TypeError("usage_hint_text must be a string or None")
        if self.max_concurrent_threads_per_session is not None:
            _usize(self.max_concurrent_threads_per_session, "max_concurrent_threads_per_session")


@dataclass(frozen=True)
class WaitAgentTimeoutOptions:
    default_timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS
    min_timeout_ms: int = MIN_WAIT_TIMEOUT_MS
    max_timeout_ms: int = MAX_WAIT_TIMEOUT_MS

    def __post_init__(self) -> None:
        _i64(self.default_timeout_ms, "default_timeout_ms")
        _i64(self.min_timeout_ms, "min_timeout_ms")
        _i64(self.max_timeout_ms, "max_timeout_ms")


def create_spawn_agent_tool_v1(options: SpawnAgentToolOptions = SpawnAgentToolOptions()) -> dict[str, JsonValue]:
    available_models_description = None if options.hide_agent_type_model_reasoning else spawn_agent_models_description(options.available_models)
    properties = spawn_agent_common_properties_v1(options.agent_type_description)
    if options.hide_agent_type_model_reasoning:
        hide_spawn_agent_metadata_options(properties)
    return _namespace_tool(
        {
            "type": "function",
            "name": "spawn_agent",
            "description": spawn_agent_tool_description(
                available_models_description,
                "Returns the spawned agent id plus the user-facing nickname when available.",
                options.include_usage_hint,
                options.usage_hint_text,
            ),
            "strict": False,
            "parameters": _object_schema(properties, None, False),
            "output_schema": spawn_agent_output_schema_v1(),
        }
    )


def create_spawn_agent_tool_v2(options: SpawnAgentToolOptions = SpawnAgentToolOptions()) -> dict[str, JsonValue]:
    available_models_description = None if options.hide_agent_type_model_reasoning else spawn_agent_models_description(options.available_models)
    properties = spawn_agent_common_properties_v2(options.agent_type_description)
    if options.hide_agent_type_model_reasoning:
        hide_spawn_agent_metadata_options(properties)
    properties["task_name"] = {
        "type": "string",
        "description": "Task name for the new agent. Use lowercase letters, digits, and underscores.",
    }
    return {
        "type": "function",
        "name": "spawn_agent",
        "description": spawn_agent_tool_description_v2(
            available_models_description,
            options.include_usage_hint,
            options.usage_hint_text,
            options.max_concurrent_threads_per_session,
        ),
        "strict": False,
        "parameters": _object_schema(properties, ["task_name", "message"], False),
        "output_schema": spawn_agent_output_schema_v2(options.hide_agent_type_model_reasoning),
    }


def create_send_input_tool_v1() -> dict[str, JsonValue]:
    return _namespace_tool(
        {
            "type": "function",
            "name": "send_input",
            "description": "Send a message to an existing agent. Use interrupt=true to redirect work immediately. You should reuse the agent by send_input if you believe your assigned task is highly dependent on the context of a previous task.",
            "strict": False,
            "parameters": _object_schema(
                {
                    "target": {"type": "string", "description": "Agent id to message (from spawn_agent)."},
                    "message": {"type": "string", "description": "Legacy plain-text message to send to the agent. Use either message or items."},
                    "items": create_collab_input_items_schema(),
                    "interrupt": {"type": "boolean", "description": "When true, stop the agent's current task and handle this immediately. When false (default), queue this message."},
                },
                ["target"],
                False,
            ),
            "output_schema": send_input_output_schema(),
        }
    )


def create_send_message_tool() -> dict[str, JsonValue]:
    return _function_tool(
        "send_message",
        "Send a message to an existing agent. The message will be delivered promptly. Does not trigger a new turn.",
        {
            "target": {"type": "string", "description": "Relative or canonical task name to message (from spawn_agent)."},
            "message": {"type": "string", "description": "Message text to queue on the target agent."},
        },
        ["target", "message"],
    )


def create_followup_task_tool() -> dict[str, JsonValue]:
    return _function_tool(
        "followup_task",
        "Send a message to an existing non-root target agent and trigger a turn in that target. If the target is currently mid-turn, the message is queued and will be used to start the target's next turn, after the current turn completes.",
        {
            "target": {"type": "string", "description": "Agent id or canonical task name to message (from spawn_agent)."},
            "message": {"type": "string", "description": "Message text to send to the target agent."},
        },
        ["target", "message"],
    )


def create_resume_agent_tool() -> dict[str, JsonValue]:
    return _namespace_tool(
        {
            "type": "function",
            "name": "resume_agent",
            "description": "Resume a previously closed agent by id so it can receive send_input and wait_agent calls.",
            "strict": False,
            "parameters": _object_schema(
                {"id": {"type": "string", "description": "Agent id to resume."}},
                ["id"],
                False,
            ),
            "output_schema": resume_agent_output_schema(),
        }
    )


def create_wait_agent_tool_v1(options: WaitAgentTimeoutOptions = WaitAgentTimeoutOptions()) -> dict[str, JsonValue]:
    return _namespace_tool(
        {
            "type": "function",
            "name": "wait_agent",
            "description": "Wait for agents to reach a final status. Completed statuses may include the agent's final message. Returns empty status when timed out. Once the agent reaches a final status, a notification message will be received containing the same completed status.",
            "strict": False,
            "parameters": wait_agent_tool_parameters_v1(options),
            "output_schema": wait_output_schema_v1(),
        }
    )


def create_wait_agent_tool_v2(options: WaitAgentTimeoutOptions = WaitAgentTimeoutOptions()) -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": "wait_agent",
        "description": "Wait for a mailbox update from any live agent, including queued messages and final-status notifications. Does not return the content; returns either a summary of which agents have updates (if any), or a timeout summary if no mailbox update arrives before the deadline.",
        "strict": False,
        "parameters": wait_agent_tool_parameters_v2(options),
        "output_schema": wait_output_schema_v2(),
    }


def create_list_agents_tool() -> dict[str, JsonValue]:
    return _function_tool(
        "list_agents",
        "List live agents in the current root thread tree. Optionally filter by task-path prefix.",
        {
            "path_prefix": {
                "type": "string",
                "description": "Optional task-path prefix (not ending with trailing slash). Accepts the same relative or absolute task-path syntax.",
            }
        },
        None,
        output_schema=list_agents_output_schema(),
    )


def create_close_agent_tool_v1() -> dict[str, JsonValue]:
    return _namespace_tool(
        {
            "type": "function",
            "name": "close_agent",
            "description": "Close an agent and any open descendants when they are no longer needed, and return the target agent's previous status before shutdown was requested. Don't keep agents open for too long if they are not needed anymore.",
            "strict": False,
            "parameters": _object_schema({"target": {"type": "string", "description": "Agent id to close (from spawn_agent)."}}, ["target"], False),
            "output_schema": close_agent_output_schema(),
        }
    )


def create_close_agent_tool_v2() -> dict[str, JsonValue]:
    return _function_tool(
        "close_agent",
        "Close an agent and any open descendants when they are no longer needed, and return the target agent's previous status before shutdown was requested. Don't keep agents open for too long if they are not needed anymore.",
        {"target": {"type": "string", "description": "Agent id or canonical task name to close (from spawn_agent)."}},
        ["target"],
        output_schema=close_agent_output_schema(),
    )


def agent_status_output_schema() -> dict[str, JsonValue]:
    return {
        "oneOf": [
            {"type": "string", "enum": ["pending_init", "running", "interrupted", "shutdown", "not_found"]},
            {"type": "object", "properties": {"completed": {"type": ["string", "null"]}}, "required": ["completed"], "additionalProperties": False},
            {"type": "object", "properties": {"errored": {"type": "string"}}, "required": ["errored"], "additionalProperties": False},
        ]
    }


def spawn_agent_output_schema_v1() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Thread identifier for the spawned agent."},
            "nickname": {"type": ["string", "null"], "description": "User-facing nickname for the spawned agent when available."},
        },
        "required": ["agent_id", "nickname"],
        "additionalProperties": False,
    }


def spawn_agent_output_schema_v2(hide_agent_metadata: bool) -> dict[str, JsonValue]:
    if hide_agent_metadata:
        return {
            "type": "object",
            "properties": {"task_name": {"type": "string", "description": "Canonical task name for the spawned agent."}},
            "required": ["task_name"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "task_name": {"type": "string", "description": "Canonical task name for the spawned agent."},
            "nickname": {"type": ["string", "null"], "description": "User-facing nickname for the spawned agent when available."},
        },
        "required": ["task_name", "nickname"],
        "additionalProperties": False,
    }


def send_input_output_schema() -> dict[str, JsonValue]:
    return {"type": "object", "properties": {"submission_id": {"type": "string", "description": "Identifier for the queued input submission."}}, "required": ["submission_id"], "additionalProperties": False}


def list_agents_output_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "agents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_name": {"type": "string", "description": "Canonical task name for the agent when available, otherwise the agent id."},
                        "agent_status": {"description": "Last known status of the agent.", "allOf": [agent_status_output_schema()]},
                        "last_task_message": {"type": ["string", "null"], "description": "Most recent user or inter-agent instruction received by the agent, when available."},
                    },
                    "required": ["agent_name", "agent_status", "last_task_message"],
                    "additionalProperties": False,
                },
                "description": "Live agents visible in the current root thread tree.",
            }
        },
        "required": ["agents"],
        "additionalProperties": False,
    }


def resume_agent_output_schema() -> dict[str, JsonValue]:
    return {"type": "object", "properties": {"status": agent_status_output_schema()}, "required": ["status"], "additionalProperties": False}


def wait_output_schema_v1() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "status": {"type": "object", "description": "Final statuses keyed by agent id.", "additionalProperties": agent_status_output_schema()},
            "timed_out": {"type": "boolean", "description": "Whether the wait call returned due to timeout before any agent reached a final status."},
        },
        "required": ["status", "timed_out"],
        "additionalProperties": False,
    }


def wait_output_schema_v2() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Brief wait summary without the agent's final content."},
            "timed_out": {"type": "boolean", "description": "Whether the wait call returned because no mailbox update arrived before the timeout."},
        },
        "required": ["message", "timed_out"],
        "additionalProperties": False,
    }


def close_agent_output_schema() -> dict[str, JsonValue]:
    return {"type": "object", "properties": {"previous_status": {"description": "The agent status observed before shutdown was requested.", "allOf": [agent_status_output_schema()]}}, "required": ["previous_status"], "additionalProperties": False}


def create_collab_input_items_schema() -> dict[str, JsonValue]:
    return {
        "type": "array",
        "description": "Structured input items. Use this to pass explicit mentions (for example app:// connector paths).",
        "items": _object_schema(
            {
                "type": {"type": "string", "description": "Input item type: text, image, local_image, skill, or mention."},
                "text": {"type": "string", "description": "Text content when type is text."},
                "image_url": {"type": "string", "description": "Image URL when type is image."},
                "path": {"type": "string", "description": "Path when type is local_image/skill, or structured mention target such as app://<connector-id> or plugin://<plugin-name>@<marketplace-name> when type is mention."},
                "name": {"type": "string", "description": "Display name when type is skill or mention."},
            },
            None,
            False,
        ),
    }


def spawn_agent_common_properties_v1(agent_type_description: str) -> dict[str, JsonValue]:
    return {
        "message": {"type": "string", "description": "Initial plain-text task for the new agent. Use either message or items."},
        "items": create_collab_input_items_schema(),
        "agent_type": {"type": "string", "description": agent_type_description},
        "fork_context": {"type": "boolean", "description": "When true, fork the current thread history into the new agent before sending the initial prompt. This must be used when you want the new agent to have exactly the same context as you."},
        "model": {"type": "string", "description": SPAWN_AGENT_MODEL_OVERRIDE_DESCRIPTION},
        "reasoning_effort": {"type": "string", "description": "Optional reasoning effort override for the new agent. Replaces the inherited reasoning effort."},
        "service_tier": {"type": "string", "description": SPAWN_AGENT_SERVICE_TIER_OVERRIDE_DESCRIPTION},
    }


def spawn_agent_common_properties_v2(agent_type_description: str) -> dict[str, JsonValue]:
    return {
        "message": {"type": "string", "description": "Initial plain-text task for the new agent."},
        "agent_type": {"type": "string", "description": agent_type_description},
        "fork_turns": {"type": "string", "description": "Optional number of turns to fork. Defaults to `all`. Use `none`, `all`, or a positive integer string such as `3` to fork only the most recent turns."},
        "model": {"type": "string", "description": SPAWN_AGENT_MODEL_OVERRIDE_DESCRIPTION},
        "reasoning_effort": {"type": "string", "description": "Optional reasoning effort override for the new agent. Replaces the inherited reasoning effort."},
        "service_tier": {"type": "string", "description": SPAWN_AGENT_SERVICE_TIER_OVERRIDE_DESCRIPTION},
    }


def hide_spawn_agent_metadata_options(properties: dict[str, JsonValue]) -> None:
    for key in ("agent_type", "model", "reasoning_effort", "service_tier"):
        properties.pop(key, None)


def spawn_agent_tool_description(available_models_description: str | None, return_value_description: str, include_usage_hint: bool, usage_hint_text: str | None) -> str:
    base = f"\n        {available_models_description or ''}\n        Spawn a sub-agent for a well-scoped task. {return_value_description} {SPAWN_AGENT_INHERITED_MODEL_GUIDANCE}"
    if include_usage_hint and usage_hint_text is not None:
        return f"\n        {base}\n{usage_hint_text}"
    if include_usage_hint:
        agent_role_usage_hint = (
            "Agent-role guidance below only helps choose which agent to use after spawning is already authorized; it never authorizes spawning by itself."
            if available_models_description is not None
            else ""
        )
        return (
            f"\n        {base}"
            + "\nThis spawn_agent tool provides you access to sub-agents that inherit your current model by default. Do not set the `model` field unless the user explicitly asks for a different model or there is a clear task-specific reason. You should follow the rules and guidelines below to use this tool.\n\n"
            + "Only use `spawn_agent` if and only if the user explicitly asks for sub-agents, delegation, or parallel agent work.\n"
            + "Requests for depth, thoroughness, research, investigation, or detailed codebase analysis do not count as permission to spawn.\n"
            + f"{agent_role_usage_hint}\n\n"
            + "### When to delegate vs. do the subtask yourself\n"
            + "- First, quickly analyze the overall user task and form a succinct high-level plan. Identify which tasks are immediate blockers on the critical path, and which tasks are sidecar tasks that are needed but can run in parallel without blocking the next local step. As part of that plan, explicitly decide what immediate task you should do locally right now. Do this planning step before delegating to agents so you do not hand off the immediate blocking task to a submodel and then waste time waiting on it.\n"
            + "- Use a subagent when a subtask is easy enough for it to handle and can run in parallel with your local work. Prefer delegating concrete, bounded sidecar tasks that materially advance the main task without blocking your immediate next local step.\n"
            + "- Do not delegate urgent blocking work when your immediate next step depends on that result. If the very next action is blocked on that task, the main rollout should usually do it locally to keep the critical path moving.\n"
            + "- Keep work local when the subtask is too difficult to delegate well and when it is tightly coupled, urgent, or likely to block your immediate next step.\n\n"
            + "### Designing delegated subtasks\n"
            + "- Subtasks must be concrete, well-defined, and self-contained.\n"
            + "- Delegated subtasks must materially advance the main task.\n"
            + "- Do not duplicate work between the main rollout and delegated subtasks.\n"
            + "- Avoid issuing multiple delegate calls on the same unresolved thread unless the new delegated task is genuinely different and necessary.\n"
            + "- Narrow the delegated ask to the concrete output you need next.\n"
            + "- For coding tasks, prefer delegating concrete code-change worker subtasks over read-only explorer analysis when the subagent can make a bounded patch in a clear write scope.\n"
            + "- When delegating coding work, instruct the submodel to edit files directly in its forked workspace and list the file paths it changed in the final answer.\n"
            + "- For code-edit subtasks, decompose work so each delegated task has a disjoint write set.\n\n"
            + "### After you delegate\n"
            + "- Call wait_agent very sparingly. Only call wait_agent when you need the result immediately for the next critical-path step and you are blocked until it returns.\n"
            + "- Do not redo delegated subagent tasks yourself; focus on integrating results or tackling non-overlapping work.\n"
            + "- While the subagent is running in the background, do meaningful non-overlapping work immediately.\n"
            + "- Do not repeatedly wait by reflex.\n"
            + "- When a delegated coding task returns, quickly review the uploaded changes, then integrate or refine them.\n\n"
            + "### Parallel delegation patterns\n"
            + "- Run multiple independent information-seeking subtasks in parallel when you have distinct questions that can be answered independently.\n"
            + "- Split implementation into disjoint codebase slices and spawn multiple agents for them in parallel when the write scopes do not overlap.\n"
            + "- Delegate verification only when it can run in parallel with ongoing implementation and is likely to catch a concrete risk before final integration.\n"
            + "- The key is to find opportunities to spawn multiple independent subtasks in parallel within the same round, while ensuring each subtask is well-defined, self-contained, and materially advances the main task."
        )
    return base


def spawn_agent_tool_description_v2(available_models_description: str | None, include_usage_hint: bool, usage_hint_text: str | None, max_concurrent_threads_per_session: int | None) -> str:
    concurrency = "" if max_concurrent_threads_per_session is None else f"This session is configured with `max_concurrent_threads_per_session = {max_concurrent_threads_per_session}` for concurrently open agent threads."
    base = (
        f"\n        {available_models_description or ''}\n"
        '        Spawns an agent to work on the specified task. If your current task is `/root/task1` and you spawn_agent with task_name "task_3" the agent will have canonical task name `/root/task1/task_3`.\n'
        "You are then able to refer to this agent as `task_3` or `/root/task1/task_3` interchangeably. However an agent `/root/task2/task_3` would only be able to communicate with this agent via its canonical name `/root/task1/task_3`.\n"
        "The spawned agent will have the same tools as you and the ability to spawn its own subagents.\n"
        f"{SPAWN_AGENT_INHERITED_MODEL_GUIDANCE}\n"
        "It will be able to send you and other running agents messages, and its final answer will be provided to you when it finishes.\n"
        "The new agent's canonical task name will be provided to it along with the message.\n"
        f"{concurrency}"
    )
    if include_usage_hint and usage_hint_text is not None:
        return f"\n        {base}\n{usage_hint_text}"
    return base


def spawn_agent_models_description(models: Iterable[JsonValue]) -> str:
    if isinstance(models, str):
        raise TypeError("models must be an iterable")
    visible = [model for model in models if _model_field(model, "show_in_picker", False)][:MAX_MODEL_OVERRIDES_IN_SPAWN_AGENT_DESCRIPTION]
    if not visible:
        return "No picker-visible model overrides are currently loaded."
    lines = []
    for model in visible:
        default_reasoning_effort = _string_value(_model_field(model, "default_reasoning_effort", ""))
        supported_efforts = []
        for preset in _model_field(model, "supported_reasoning_efforts", ()):
            effort = _string_value(_model_field(preset, "effort", ""))
            if effort == "":
                continue
            if effort == default_reasoning_effort:
                supported_efforts.append(f"{effort} (default)")
            else:
                supported_efforts.append(effort)
        reasoning_suffix = "" if not supported_efforts else f" Reasoning efforts: {', '.join(supported_efforts)}."
        service_tiers = [
            _string_value(_model_field(tier, "id", ""))
            for tier in _model_field(model, "service_tiers", ())
        ]
        service_tiers = [tier for tier in service_tiers if tier]
        service_suffix = "" if not service_tiers else f" Service tiers: {', '.join(service_tiers)}."
        lines.append(
            f"- `{_model_field(model, 'model', '')}`: {_model_field(model, 'description', '')}{reasoning_suffix}{service_suffix}"
        )
    return "Available model overrides (optional; inherited parent model is preferred):\n" + "\n".join(lines)


def wait_agent_tool_parameters_v1(options: WaitAgentTimeoutOptions) -> dict[str, JsonValue]:
    return _object_schema(
        {
            "targets": {"type": "array", "items": {"type": "string"}, "description": "Agent ids to wait on. Pass multiple ids to wait for whichever finishes first."},
            "timeout_ms": {"type": "number", "description": f"Optional timeout in milliseconds. Defaults to {options.default_timeout_ms}, min {options.min_timeout_ms}, max {options.max_timeout_ms}. Prefer longer waits (minutes) to avoid busy polling."},
        },
        ["targets"],
        False,
    )


def wait_agent_tool_parameters_v2(options: WaitAgentTimeoutOptions) -> dict[str, JsonValue]:
    return _object_schema({"timeout_ms": {"type": "number", "description": f"Optional timeout in milliseconds. Defaults to {options.default_timeout_ms}, min {options.min_timeout_ms}, max {options.max_timeout_ms}."}}, None, False)


def _namespace_tool(tool: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"type": "namespace", "name": MULTI_AGENT_V1_NAMESPACE, "description": MULTI_AGENT_V1_NAMESPACE_DESCRIPTION, "tools": [tool]}


def _function_tool(name: str, description: str, properties: dict[str, JsonValue], required: list[str] | None, *, output_schema: JsonValue | None = None) -> dict[str, JsonValue]:
    tool = {"type": "function", "name": name, "description": description, "strict": False, "parameters": _object_schema(properties, required, False)}
    if output_schema is not None:
        tool["output_schema"] = output_schema
    return tool


def _object_schema(properties: dict[str, JsonValue], required: list[str] | None, additional_properties: bool | None) -> dict[str, JsonValue]:
    schema: dict[str, JsonValue] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    if additional_properties is not None:
        schema["additionalProperties"] = additional_properties
    return schema


def _model_field(model: JsonValue, name: str, default: JsonValue) -> JsonValue:
    if isinstance(model, Mapping):
        return model.get(name, default)
    return getattr(model, name, default)


def _string_value(value: JsonValue) -> str:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return str(value)
