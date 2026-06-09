"""Pure AgentControl helpers ported from ``core/src/agent/control.rs``."""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.protocol import (
    AgentPath,
    AgentStatus,
    CompactedItem,
    InterAgentCommunication,
    MessagePhase,
    Op,
    ResponseItem,
    RolloutItem,
    SessionSource,
    SessionId,
    SubAgentSource,
    ThreadId,
)
from pycodex.protocol.error import CodexErr
from pycodex.protocol.user_input import UserInput
from pycodex.core.agent.registry import AgentMetadata, AgentRegistry
from pycodex.core.config.agent_roles import DEFAULT_ROLE_NAME, AgentRoleConfig, resolve_role_config


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


class SpawnAgentForkMode(str, Enum):
    FULL_HISTORY = "full_history"
    LAST_N_TURNS = "last_n_turns"


@dataclass(frozen=True)
class SpawnAgentOptions:
    fork_parent_spawn_call_id: str | None = None
    fork_mode: SpawnAgentForkMode | tuple[SpawnAgentForkMode, int] | None = None
    environments: tuple[Any, ...] | None = None


@dataclass(frozen=True)
class LiveAgent:
    thread_id: ThreadId
    metadata: AgentMetadata
    status: AgentStatus


@dataclass(frozen=True)
class ListedAgent:
    agent_name: str
    agent_status: AgentStatus
    last_task_message: str | None = None


def default_agent_nickname_list() -> list[str]:
    """Return the embedded default agent nickname list."""

    return [name.strip() for name in AGENT_NAMES.splitlines() if name.strip()]


def agent_nickname_candidates(
    config_or_roles: Any,
    role_name: str | None = None,
) -> list[str]:
    """Return role-specific nickname candidates or the default nickname list."""

    resolved_role_name = role_name or DEFAULT_ROLE_NAME
    roles = _agent_roles_mapping(config_or_roles)
    role = resolve_role_config(roles, resolved_role_name)
    if role is not None and role.nickname_candidates is not None:
        return list(role.nickname_candidates)
    return default_agent_nickname_list()


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


def _agent_roles_mapping(config_or_roles: Any) -> Mapping[str, AgentRoleConfig]:
    if isinstance(config_or_roles, Mapping):
        return config_or_roles
    roles = getattr(config_or_roles, "agent_roles", None)
    if isinstance(roles, Mapping):
        return roles
    raise TypeError("config_or_roles must be a mapping or expose agent_roles")


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


class AgentControl:
    """Control-plane handle for multi-agent operations.

    The heavy runtime is still supplied by the thread manager. This class owns
    the root-scoped registry and delegates thread creation, input delivery,
    status lookup, subscription, and shutdown through that manager, matching the
    Rust module boundary without re-implementing thread-manager internals here.
    """

    agent_matches_prefix = staticmethod(agent_matches_prefix)
    agent_nickname_candidates = staticmethod(agent_nickname_candidates)
    default_agent_nickname_list = staticmethod(default_agent_nickname_list)
    filter_forked_rollout_items = staticmethod(filter_forked_rollout_items)
    is_multi_agent_v2_usage_hint_message = staticmethod(is_multi_agent_v2_usage_hint_message)
    keep_forked_rollout_item = staticmethod(keep_forked_rollout_item)
    render_input_preview = staticmethod(render_input_preview)
    thread_spawn_depth = staticmethod(thread_spawn_depth)
    thread_spawn_parent_thread_id = staticmethod(thread_spawn_parent_thread_id)

    def __init__(
        self,
        manager: Any = None,
        *,
        session_id: SessionId | str | None = None,
        state: AgentRegistry | None = None,
    ) -> None:
        self.manager = manager
        self._session_id = _coerce_session_id(session_id)
        self.state = state or AgentRegistry()

    @classmethod
    def new(cls, manager: Any) -> "AgentControl":
        return cls(manager)

    def with_session_id(self, session_id: SessionId | str) -> "AgentControl":
        self._session_id = _coerce_session_id(session_id)
        return self

    def session_id(self) -> SessionId:
        return self._session_id

    async def spawn_agent(
        self,
        config: Any,
        initial_operation: Op | Iterable[UserInput] | Mapping[str, Any],
        session_source: SessionSource | None = None,
    ) -> ThreadId:
        live_agent = await self.spawn_agent_with_metadata(
            config,
            initial_operation,
            session_source,
            SpawnAgentOptions(),
        )
        return live_agent.thread_id

    async def spawn_agent_with_metadata(
        self,
        config: Any,
        initial_operation: Op | Iterable[UserInput] | Mapping[str, Any],
        session_source: SessionSource | None = None,
        options: SpawnAgentOptions | Mapping[str, Any] | None = None,
    ) -> LiveAgent:
        options = _coerce_spawn_options(options)
        if options.fork_mode is not None:
            raise CodexErr.unsupported_operation("spawn_agent fork is not implemented in Python AgentControl")

        manager = self._manager()
        reservation = self.state.reserve_spawn_slot(getattr(config, "agent_max_threads", None))
        committed = False
        try:
            session_source, metadata = self._prepare_spawn_metadata(
                reservation,
                config,
                session_source,
            )
            operation = _coerce_initial_operation(initial_operation, options.environments)
            new_thread = await _start_thread(
                manager,
                config,
                operation,
                session_source,
                options,
                self,
            )
            thread_id = _coerce_thread_id(getattr(new_thread, "thread_id", new_thread))
            metadata.agent_id = thread_id
            reservation.commit(metadata)
            committed = True
            await self.send_input(thread_id, operation)
            return LiveAgent(
                thread_id=thread_id,
                metadata=metadata,
                status=await self.get_status(thread_id),
            )
        finally:
            if not committed:
                reservation.release()

    async def resume_agent_from_rollout(
        self,
        config: Any,
        thread_id: ThreadId | str,
        session_source: SessionSource | None,
    ) -> ThreadId:
        _ = (config, thread_id, session_source)
        raise CodexErr.unsupported_operation("resume_agent_from_rollout is not implemented in Python AgentControl")

    async def send_input(self, agent_id: ThreadId | str, initial_operation: Op | Mapping[str, Any]) -> str:
        thread_id = _coerce_thread_id(agent_id)
        operation = Op.from_mapping(initial_operation) if isinstance(initial_operation, Mapping) else initial_operation
        last_task_message = render_input_preview(operation)
        result = await self._send_op(thread_id, operation)
        self.state.update_last_task_message(thread_id, last_task_message)
        return result

    async def send_inter_agent_communication(
        self,
        agent_id: ThreadId | str,
        communication: InterAgentCommunication | Mapping[str, Any],
    ) -> str:
        parsed = (
            communication
            if isinstance(communication, InterAgentCommunication)
            else InterAgentCommunication.from_mapping(communication)
        )
        result = await self._send_op(_coerce_thread_id(agent_id), Op.inter_agent_communication(parsed))
        self.state.update_last_task_message(_coerce_thread_id(agent_id), parsed.content)
        return result

    async def interrupt_agent(self, agent_id: ThreadId | str) -> str:
        return await self._send_op(_coerce_thread_id(agent_id), Op.simple("interrupt"))

    async def shutdown_live_agent(self, agent_id: ThreadId | str) -> str:
        thread_id = _coerce_thread_id(agent_id)
        manager = self._manager()
        thread = _get_thread_or_none(manager, thread_id)
        if thread is not None:
            ensure = getattr(thread, "ensure_rollout_materialized", None)
            if callable(ensure):
                await _maybe_await(ensure())
            flush = getattr(thread, "flush_rollout", None)
            if callable(flush):
                await _maybe_await(flush())
            status = await self.get_status(thread_id)
            result = "" if status.type == "shutdown" else await self._send_op(thread_id, Op.simple("shutdown"))
            waiter = getattr(thread, "wait_until_terminated", None)
            if callable(waiter):
                await _maybe_await(waiter())
        else:
            result = await self._send_op(thread_id, Op.simple("shutdown"))
        _remove_thread(manager, thread_id)
        self.state.release_spawned_thread(thread_id)
        return result

    async def close_agent(self, agent_id: ThreadId | str) -> str:
        return await self.shutdown_agent_tree(_coerce_thread_id(agent_id))

    async def shutdown_agent_tree(self, agent_id: ThreadId | str) -> str:
        thread_id = _coerce_thread_id(agent_id)
        descendants = await self.live_thread_spawn_descendants(thread_id)
        result = await self.shutdown_live_agent(thread_id)
        for descendant in descendants:
            try:
                await self.shutdown_live_agent(descendant)
            except CodexErr as err:
                if err.kind not in {"thread_not_found", "internal_agent_died"}:
                    raise
        return result

    async def get_status(self, agent_id: ThreadId | str) -> AgentStatus:
        thread = _get_thread_or_none(self._manager_or_none(), _coerce_thread_id(agent_id))
        if thread is None:
            return AgentStatus.not_found()
        status = getattr(thread, "agent_status", None)
        if callable(status):
            return AgentStatus.from_mapping(await _maybe_await(status()))
        status = getattr(thread, "status", None)
        if status is not None:
            return AgentStatus.from_mapping(status)
        return AgentStatus.running()

    def register_session_root(
        self,
        current_thread_id: ThreadId | str,
        current_session_source: SessionSource,
    ) -> None:
        if thread_spawn_parent_thread_id(current_session_source) is None:
            self.state.register_root_thread(_coerce_thread_id(current_thread_id))

    def get_agent_metadata(self, agent_id: ThreadId | str) -> AgentMetadata | None:
        return self.state.agent_metadata_for_thread(_coerce_thread_id(agent_id))

    async def list_live_agent_subtree_thread_ids(self, agent_id: ThreadId | str) -> list[ThreadId]:
        thread_id = _coerce_thread_id(agent_id)
        return [thread_id, *await self.live_thread_spawn_descendants(thread_id)]

    async def get_agent_config_snapshot(self, agent_id: ThreadId | str) -> Any | None:
        thread = _get_thread_or_none(self._manager_or_none(), _coerce_thread_id(agent_id))
        if thread is None:
            return None
        snapshot = getattr(thread, "config_snapshot", None)
        if callable(snapshot):
            return await _maybe_await(snapshot())
        snapshot = getattr(thread, "thread_config_snapshot", None)
        if callable(snapshot):
            return await _maybe_await(snapshot())
        return getattr(thread, "config", None)

    async def resolve_agent_reference(
        self,
        current_thread_id: ThreadId | str,
        current_session_source: SessionSource,
        agent_reference: str,
    ) -> ThreadId:
        _ = current_thread_id
        current_agent_path = _session_agent_path(current_session_source) or AgentPath.root()
        try:
            agent_path = current_agent_path.resolve(agent_reference)
        except Exception as err:
            raise CodexErr.unsupported_operation(str(err)) from err
        thread_id = self.state.agent_id_for_path(agent_path)
        if thread_id is not None:
            return thread_id
        raise CodexErr.unsupported_operation(f"live agent path `{agent_path.as_str()}` not found")

    async def subscribe_status(self, agent_id: ThreadId | str) -> Any:
        thread_id = _coerce_thread_id(agent_id)
        thread = _get_thread_or_none(self._manager(), thread_id)
        if thread is None:
            raise CodexErr.thread_not_found(str(thread_id))
        subscriber = getattr(thread, "subscribe_status", None)
        if callable(subscriber):
            return await _maybe_await(subscriber())
        return _StaticStatusSubscription(await self.get_status(thread_id))

    async def format_environment_context_subagents(self, parent_thread_id: ThreadId | str) -> str:
        agents = await self.open_thread_spawn_children(_coerce_thread_id(parent_thread_id))
        lines = []
        for thread_id, metadata in agents:
            reference = metadata.agent_path.name() if metadata.agent_path is not None else str(thread_id)
            nickname = metadata.agent_nickname
            lines.append(f"{reference} ({nickname})" if nickname else reference)
        return "\n".join(lines)

    async def list_agents(
        self,
        current_session_source: SessionSource,
        path_prefix: str | None = None,
    ) -> list[ListedAgent]:
        current_agent_path = _session_agent_path(current_session_source) or AgentPath.root()
        prefix = current_agent_path.resolve(path_prefix) if path_prefix else current_agent_path
        listed: list[ListedAgent] = []
        for metadata in self.state.live_agents():
            if metadata.agent_id is None:
                continue
            if metadata.agent_path is not None and not agent_matches_prefix(metadata.agent_path, prefix):
                continue
            listed.append(
                ListedAgent(
                    agent_name=str(metadata.agent_path or metadata.agent_id),
                    agent_status=await self.get_status(metadata.agent_id),
                    last_task_message=metadata.last_task_message,
                )
            )
        return listed

    async def open_thread_spawn_children(self, parent_thread_id: ThreadId | str) -> list[tuple[ThreadId, AgentMetadata]]:
        parent = _coerce_thread_id(parent_thread_id)
        parent_metadata = self.state.agent_metadata_for_thread(parent)
        parent_path = parent_metadata.agent_path if parent_metadata is not None else AgentPath.root()
        return [
            (metadata.agent_id, metadata)
            for metadata in self.state.live_agents()
            if metadata.agent_id is not None
            and metadata.agent_path is not None
            and _agent_path_parent(metadata.agent_path) == parent_path
        ]

    async def live_thread_spawn_descendants(self, root_thread_id: ThreadId | str) -> list[ThreadId]:
        root = _coerce_thread_id(root_thread_id)
        root_metadata = self.state.agent_metadata_for_thread(root)
        root_path = root_metadata.agent_path if root_metadata is not None else None
        if root_path is None:
            return []
        return [
            metadata.agent_id
            for metadata in self.state.live_agents()
            if metadata.agent_id is not None
            and metadata.agent_path is not None
            and agent_matches_prefix(metadata.agent_path, root_path)
            and metadata.agent_id != root
        ]

    def _prepare_spawn_metadata(
        self,
        reservation: Any,
        config: Any,
        session_source: SessionSource | None,
    ) -> tuple[SessionSource | None, AgentMetadata]:
        if (
            session_source is not None
            and session_source.type == "subagent"
            and isinstance(session_source.subagent_source, SubAgentSource)
            and session_source.subagent_source.type == "thread_spawn"
        ):
            source = session_source.subagent_source
            if source.depth == 1 and source.parent_thread_id is not None:
                self.state.register_root_thread(source.parent_thread_id)
            if source.agent_path is not None:
                reservation.reserve_agent_path(source.agent_path)
            nickname = reservation.reserve_agent_nickname_with_preference(
                agent_nickname_candidates(config, source.agent_role),
                source.agent_nickname,
            )
            updated_source = SubAgentSource.thread_spawn(
                source.parent_thread_id,
                int(source.depth or 0),
                source.agent_path,
                nickname,
                source.agent_role,
            )
            return SessionSource.subagent(updated_source), AgentMetadata(
                agent_path=source.agent_path,
                agent_nickname=nickname,
                agent_role=source.agent_role,
            )
        return session_source, AgentMetadata()

    async def _send_op(self, thread_id: ThreadId, op: Op) -> str:
        manager = self._manager()
        sender = getattr(manager, "send_op", None)
        try:
            if callable(sender):
                return str(await _maybe_await(sender(str(thread_id), op)))
            thread = _get_thread_or_none(manager, thread_id)
            if thread is None:
                raise CodexErr.thread_not_found(str(thread_id))
            submit = getattr(thread, "submit", None)
            if not callable(submit):
                raise CodexErr.unsupported_operation("thread does not support submit")
            return str(await _maybe_await(submit(op)))
        except CodexErr as err:
            if err.kind == "internal_agent_died":
                _remove_thread(manager, thread_id)
                self.state.release_spawned_thread(thread_id)
            raise

    def _manager(self) -> Any:
        manager = self._manager_or_none()
        if manager is None:
            raise CodexErr.unsupported_operation("thread manager dropped")
        return manager

    def _manager_or_none(self) -> Any:
        manager = self.manager
        if callable(getattr(manager, "upgrade", None)):
            return manager.upgrade()
        return manager


class _StaticStatusSubscription:
    def __init__(self, status: AgentStatus) -> None:
        self._status = status

    def has_changed(self) -> bool:
        return True

    def borrow(self) -> AgentStatus:
        return self._status

    async def changed(self) -> None:
        return None


def _coerce_session_id(value: SessionId | str | None) -> SessionId:
    if value is None:
        return SessionId.default()
    if isinstance(value, SessionId):
        return value
    return SessionId.from_string(str(value))


def _coerce_thread_id(value: ThreadId | str) -> ThreadId:
    if isinstance(value, ThreadId):
        return value
    return ThreadId.from_string(str(value))


def _coerce_spawn_options(options: SpawnAgentOptions | Mapping[str, Any] | None) -> SpawnAgentOptions:
    if options is None:
        return SpawnAgentOptions()
    if isinstance(options, SpawnAgentOptions):
        return options
    environments = options.get("environments")
    return SpawnAgentOptions(
        fork_parent_spawn_call_id=options.get("fork_parent_spawn_call_id"),
        fork_mode=options.get("fork_mode"),
        environments=tuple(environments) if environments is not None else None,
    )


def _coerce_initial_operation(
    initial_operation: Op | Iterable[UserInput] | Mapping[str, Any],
    environments: tuple[Any, ...] | None,
) -> Op:
    if isinstance(initial_operation, Op):
        return initial_operation
    if isinstance(initial_operation, Mapping):
        try:
            return Op.from_mapping(initial_operation)
        except Exception:
            pass
    return Op.user_input(initial_operation, environments=environments)


async def _start_thread(
    manager: Any,
    config: Any,
    operation: Op,
    session_source: SessionSource | None,
    options: SpawnAgentOptions,
    agent_control: AgentControl,
) -> Any:
    start_thread = getattr(manager, "start_thread", None)
    if callable(start_thread):
        from pycodex.core.thread_manager import StartThreadOptions

        return await _maybe_await(start_thread(StartThreadOptions(
            config=config,
            session_source=session_source,
            thread_source="subagent" if session_source is not None else None,
            environments=options.environments or (),
        )))

    spawn_new_thread_with_source = getattr(manager, "spawn_new_thread_with_source", None)
    if callable(spawn_new_thread_with_source) and session_source is not None:
        return await _maybe_await(spawn_new_thread_with_source(
            config,
            agent_control,
            session_source,
            thread_spawn_parent_thread_id(session_source),
            "subagent",
            False,
            None,
            None,
            None,
            options.environments,
        ))

    spawn_new_thread = getattr(manager, "spawn_new_thread", None)
    if callable(spawn_new_thread):
        return await _maybe_await(spawn_new_thread(config, agent_control))

    raise CodexErr.unsupported_operation("thread manager does not support spawning threads")


def _get_thread_or_none(manager: Any, thread_id: ThreadId) -> Any | None:
    if manager is None:
        return None
    getter = getattr(manager, "get_thread", None)
    if not callable(getter):
        return None
    try:
        return getter(str(thread_id))
    except Exception:
        try:
            return getter(thread_id)
        except Exception:
            return None


def _remove_thread(manager: Any, thread_id: ThreadId) -> None:
    remover = getattr(manager, "remove_thread", None)
    if callable(remover):
        try:
            remover(str(thread_id))
        except Exception:
            remover(thread_id)


def _session_agent_path(session_source: SessionSource) -> AgentPath | None:
    getter = getattr(session_source, "get_agent_path", None)
    if callable(getter):
        return getter()
    if (
        session_source.type == "subagent"
        and isinstance(session_source.subagent_source, SubAgentSource)
        and session_source.subagent_source.type == "thread_spawn"
    ):
        return session_source.subagent_source.agent_path
    return None


def _agent_path_parent(agent_path: AgentPath) -> AgentPath | None:
    text = agent_path.as_str()
    if text == AgentPath.ROOT:
        return None
    parent = text.rsplit("/", 1)[0]
    if parent == "":
        return None
    return AgentPath.from_string(parent)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "AGENT_NAMES",
    "AgentControl",
    "ListedAgent",
    "LiveAgent",
    "ROOT_LAST_TASK_MESSAGE",
    "SpawnAgentForkMode",
    "SpawnAgentOptions",
    "agent_matches_prefix",
    "agent_nickname_candidates",
    "default_agent_nickname_list",
    "filter_forked_rollout_items",
    "is_multi_agent_v2_usage_hint_message",
    "keep_forked_rollout_item",
    "render_input_preview",
    "thread_spawn_depth",
    "thread_spawn_parent_thread_id",
]
