"""Pure AgentControl helpers ported from ``core/src/agent/control.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.protocol import (
    AgentPath,
    CompactedItem,
    InterAgentCommunication,
    MessagePhase,
    Op,
    ResponseItem,
    RolloutItem,
    SessionSource,
    SubAgentSource,
    ThreadId,
)
from pycodex.protocol.user_input import UserInput


AGENT_NAMES = """Euclid
Archimedes
Ptolemy
Hypatia
Avicenna
Averroes
Aquinas
Copernicus
Kepler
Galileo
Bacon
Descartes
Pascal
Fermat
Huygens
Leibniz
Newton
Halley
Euler
Lagrange
Laplace
Volta
Gauss
Ampere
Faraday
Darwin
Lovelace
Boole
Pasteur
Maxwell
Mendel
Curie
Planck
Tesla
Poincare
Noether
Hilbert
Einstein
Raman
Bohr
Turing
Hubble
Feynman
Franklin
McClintock
Meitner
Herschel
Linnaeus
Wegener
Chandrasekhar
Sagan
Goodall
Carson
Carver
Socrates
Plato
Aristotle
Epicurus
Cicero
Confucius
Mencius
Zeno
Locke
Hume
Kant
Hegel
Kierkegaard
Mill
Nietzsche
Peirce
James
Dewey
Russell
Popper
Sartre
Beauvoir
Arendt
Rawls
Singer
Anscombe
Parfit
Kuhn
Boyle
Hooke
Harvey
Dalton
Ohm
Helmholtz
Gibbs
Lorentz
Schrodinger
Heisenberg
Pauli
Dirac
Bernoulli
Godel
Nash
Banach
Ramanujan
Erdos
Jason
"""
ROOT_LAST_TASK_MESSAGE = "Main thread"


def default_agent_nickname_list() -> list[str]:
    """Return the embedded default agent nickname list."""

    return [name.strip() for name in AGENT_NAMES.splitlines() if name.strip()]


def keep_forked_rollout_item(
    item: RolloutItem | Mapping[str, Any],
    preserve_reference_context_item: bool,
) -> bool:
    """Return whether a rollout item should be kept in forked history."""

    rollout_item = RolloutItem.from_mapping(item) if isinstance(item, Mapping) else item
    if rollout_item.type == "response_item":
        response_item = _response_item(rollout_item.payload)
        if response_item.type == "message":
            if response_item.role in {"system", "developer", "user"}:
                return True
            if response_item.role == "assistant":
                return response_item.phase == MessagePhase.FINAL_ANSWER
            return False
        return False
    if rollout_item.type == "turn_context":
        return preserve_reference_context_item
    return rollout_item.type in {"compacted", "event_msg", "session_meta"}


def is_multi_agent_v2_usage_hint_message(
    item: ResponseItem | Mapping[str, Any],
    usage_hint_texts: Iterable[str],
) -> bool:
    """Return whether a developer message is one of the multi-agent usage hints."""

    response_item = _response_item(item)
    if response_item.type != "message" or response_item.role != "developer":
        return False
    if len(response_item.content) != 1:
        return False
    only_item = response_item.content[0]
    if only_item.type != "input_text":
        return False
    return (only_item.text or "") in set(usage_hint_texts)


def filter_forked_rollout_items(
    items: Iterable[RolloutItem | Mapping[str, Any]],
    preserve_reference_context_item: bool,
    usage_hint_texts: Iterable[str] = (),
) -> list[RolloutItem]:
    """Filter forked rollout history like ``spawn_forked_thread`` does."""

    usage_hints = tuple(usage_hint_texts)
    filtered: list[RolloutItem] = []
    for raw_item in items:
        item = RolloutItem.from_mapping(raw_item) if isinstance(raw_item, Mapping) else raw_item
        if not keep_forked_rollout_item(item, preserve_reference_context_item):
            continue
        if item.type == "response_item" and is_multi_agent_v2_usage_hint_message(item.payload, usage_hints):
            continue
        if item.type == "compacted":
            item = _filter_compacted_replacement_history(item, usage_hints)
        filtered.append(item)
    return filtered


def agent_matches_prefix(agent_path: AgentPath | str | None, prefix: AgentPath | str) -> bool:
    """Return whether ``agent_path`` matches an agent-path prefix."""

    parsed_prefix = prefix if isinstance(prefix, AgentPath) else AgentPath.from_string(str(prefix))
    if parsed_prefix.is_root():
        return True
    if agent_path is None:
        return False
    parsed_path = agent_path if isinstance(agent_path, AgentPath) else AgentPath.from_string(str(agent_path))
    if parsed_path == parsed_prefix:
        return True
    suffix = parsed_path.as_str().removeprefix(parsed_prefix.as_str())
    return suffix != parsed_path.as_str() and suffix.startswith("/")


def thread_spawn_parent_thread_id(session_source: SessionSource) -> ThreadId | None:
    """Return the parent thread id from a thread-spawn session source."""

    if (
        session_source.type == "subagent"
        and isinstance(session_source.subagent_source, SubAgentSource)
        and session_source.subagent_source.type == "thread_spawn"
    ):
        return session_source.subagent_source.parent_thread_id
    return None


def thread_spawn_depth(session_source: SessionSource) -> int | None:
    """Return the depth from a thread-spawn session source."""

    if (
        session_source.type == "subagent"
        and isinstance(session_source.subagent_source, SubAgentSource)
        and session_source.subagent_source.type == "thread_spawn"
    ):
        return session_source.subagent_source.depth
    return None


def render_input_preview(initial_operation: Op | Mapping[str, Any]) -> str:
    """Render a compact preview for an initial agent operation."""

    operation = Op.from_mapping(initial_operation) if isinstance(initial_operation, Mapping) else initial_operation
    fields = operation.fields or {}
    if operation.type == "user_input":
        return "\n".join(_render_user_input_preview(item) for item in fields.get("items", ()))
    if operation.type == "inter_agent_communication":
        communication = fields.get("communication")
        if isinstance(communication, InterAgentCommunication):
            return communication.content
        if isinstance(communication, Mapping):
            return InterAgentCommunication.from_mapping(communication).content
    return ""


def _render_user_input_preview(item: UserInput | Mapping[str, Any]) -> str:
    user_input = UserInput.from_mapping(item) if isinstance(item, Mapping) else item
    if user_input.type == "text":
        return user_input.text or ""
    if user_input.type == "image":
        return "[image]"
    if user_input.type == "local_image":
        return f"[local_image:{user_input.path}]"
    if user_input.type == "skill":
        return f"[skill:${user_input.name}]({user_input.path})"
    if user_input.type == "mention":
        return f"[mention:${user_input.name}]({user_input.path})"
    return "[input]"


def _response_item(item: ResponseItem | Mapping[str, Any]) -> ResponseItem:
    return item if isinstance(item, ResponseItem) else ResponseItem.from_mapping(item)


def _filter_compacted_replacement_history(item: RolloutItem, usage_hint_texts: tuple[str, ...]) -> RolloutItem:
    compacted = item.payload if isinstance(item.payload, CompactedItem) else CompactedItem.from_mapping(item.payload)
    if compacted.replacement_history is None:
        return RolloutItem.compacted(compacted)
    replacement_history = tuple(
        raw_response_item
        for raw_response_item in compacted.replacement_history
        if not is_multi_agent_v2_usage_hint_message(_response_item(raw_response_item), usage_hint_texts)
    )
    return RolloutItem.compacted(
        CompactedItem(
            message=compacted.message,
            replacement_history=replacement_history,
        )
    )


__all__ = [
    "AGENT_NAMES",
    "ROOT_LAST_TASK_MESSAGE",
    "agent_matches_prefix",
    "default_agent_nickname_list",
    "filter_forked_rollout_items",
    "is_multi_agent_v2_usage_hint_message",
    "keep_forked_rollout_item",
    "render_input_preview",
    "thread_spawn_depth",
    "thread_spawn_parent_thread_id",
]
