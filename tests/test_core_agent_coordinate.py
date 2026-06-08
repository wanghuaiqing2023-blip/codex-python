import unittest

from pycodex.core import agent
from pycodex.core.agent.control import AgentControl
from pycodex.core.agent.registry import (
    exceeds_thread_spawn_depth_limit,
    next_thread_spawn_depth,
)
from pycodex.core.agent.status import agent_status_from_event
from pycodex.protocol import AgentStatus, EventMsg, Op, TurnStartedEvent
from pycodex.protocol.user_input import UserInput


class CoreAgentCoordinateTests(unittest.TestCase):
    def test_agent_root_reexports_rust_mod_surface(self):
        # Rust source: codex-rs/core/src/agent/mod.rs
        # Rust contract: root module re-exports AgentStatus, AgentControl,
        # spawn-depth helpers, and agent_status_from_event.
        self.assertIs(agent.AgentStatus, AgentStatus)
        self.assertIs(agent.AgentControl, AgentControl)
        self.assertIs(agent.next_thread_spawn_depth, next_thread_spawn_depth)
        self.assertIs(agent.exceeds_thread_spawn_depth_limit, exceeds_thread_spawn_depth_limit)
        self.assertIs(agent.agent_status_from_event, agent_status_from_event)

    def test_agent_control_facade_exposes_completed_pure_helpers(self):
        # Rust source: codex-rs/core/src/agent/mod.rs re-exports control::AgentControl.
        self.assertEqual(agent.AgentControl.default_agent_nickname_list()[0], "Euclid")
        self.assertEqual(
            agent.AgentControl.render_input_preview(Op.user_input((UserInput.text_input("hello"),))),
            "hello",
        )

    def test_agent_root_status_helper_smoke(self):
        event = EventMsg.with_payload("turn_started", TurnStartedEvent(turn_id="turn-1", model_context_window=None))
        self.assertEqual(agent.agent_status_from_event(event), AgentStatus.running())


if __name__ == "__main__":
    unittest.main()
