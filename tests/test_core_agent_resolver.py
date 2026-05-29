from types import SimpleNamespace

import pytest

from pycodex.core.agent_resolver import FunctionCallError, resolve_agent_target
from pycodex.protocol import SessionSource, ThreadId


class DummyAgentControl:
    def __init__(self):
        self.registered = []
        self.resolved = []

    def register_session_root(self, conversation_id, session_source):
        self.registered.append((conversation_id, session_source))

    async def resolve_agent_reference(self, conversation_id, session_source, target):
        self.resolved.append((conversation_id, session_source, target))
        return ThreadId.new()


@pytest.mark.asyncio
async def test_resolve_agent_target_accepts_direct_thread_id():
    agent_control = DummyAgentControl()
    session = SimpleNamespace(conversation_id=ThreadId.new(), services=SimpleNamespace(agent_control=agent_control))
    turn = SimpleNamespace(session_source=SessionSource.cli())
    target = ThreadId.new()

    resolved = await resolve_agent_target(session, turn, str(target))

    assert resolved == target
    assert agent_control.registered == [(session.conversation_id, turn.session_source)]
    assert agent_control.resolved == []


@pytest.mark.asyncio
async def test_resolve_agent_target_delegates_named_reference():
    agent_control = DummyAgentControl()
    session = SimpleNamespace(conversation_id=ThreadId.new(), services=SimpleNamespace(agent_control=agent_control))
    turn = SimpleNamespace(session_source=SessionSource.cli())

    resolved = await resolve_agent_target(session, turn, "Euclid")

    assert isinstance(resolved, ThreadId)
    assert agent_control.resolved == [(session.conversation_id, turn.session_source, "Euclid")]


@pytest.mark.asyncio
async def test_resolve_agent_target_maps_resolution_errors_to_model_response():
    class FailingAgentControl(DummyAgentControl):
        async def resolve_agent_reference(self, conversation_id, session_source, target):
            raise RuntimeError("unknown agent")

    session = SimpleNamespace(conversation_id=ThreadId.new(), services=SimpleNamespace(agent_control=FailingAgentControl()))
    turn = SimpleNamespace(session_source=SessionSource.cli())

    with pytest.raises(FunctionCallError) as exc_info:
        await resolve_agent_target(session, turn, "missing")

    assert str(exc_info.value) == "unknown agent"


@pytest.mark.asyncio
async def test_resolve_agent_target_reports_missing_agent_control():
    session = SimpleNamespace(conversation_id=ThreadId.new(), services=SimpleNamespace(agent_control=None))
    turn = SimpleNamespace(session_source=SessionSource.cli())

    with pytest.raises(FunctionCallError) as exc_info:
        await resolve_agent_target(session, turn, "Euclid")

    assert str(exc_info.value) == "agent control is not available"
