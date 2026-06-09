"""Integration guard for core module test coverage.

The porting contract is module-scoped.  This test keeps that discipline honest:
each Python module under ``pycodex.core`` must have either a direct
``test_core_<path>.py`` / ``test_core_<module>.py`` file or an explicit alias
to a broader focused test file.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT / "pycodex" / "core"
TEST_ROOT = REPO_ROOT / "tests"


MODULE_TEST_ALIASES: dict[str, set[str]] = {
    "__init__": {"test_core_smoke_suite.py", "test_core_tools_root.py"},
    "agent.__init__": {"test_core_agent_coordinate.py"},
    "agent.role": {"test_core_agent_role_coordinate.py", "test_core_agent_roles.py"},
    "apps.__init__": {"test_core_apps_coordinate.py"},
    "apps.render": {"test_core_app_plugin_rendering.py"},
    "config.__init__": {"test_core_config_root.py"},
    "context.__init__": {"test_core_context.py", "test_core_context_coordinate.py"},
    "context_manager.__init__": {"test_core_context_manager_coordinate.py"},
    "guardian.__init__": {"test_core_guardian_root.py"},
    "http_transport.__init__": {"test_core_http_transport.py"},
    "plugins.__init__": {"test_core_plugins_coordinate.py"},
    "session.__init__": {"test_core_session_runtime.py"},
    "session.turn.__init__": {"test_core_turn_runtime.py"},
    "state.__init__": {"test_core_state_coordinate.py"},
    "tasks.__init__": {"test_core_tasks_root.py"},
    "tools.__init__": {"test_core_tools_root.py"},
    "tools.code_mode.__init__": {"test_core_code_mode.py"},
    "tools.handlers.__init__": {"test_core_handler_utils.py"},
    "tools.handlers.goal.__init__": {"test_core_goal_handler.py"},
    "tools.runtimes.__init__": {"test_core_tool_runtimes.py"},
    "unified_exec.__init__": {"test_core_unified_exec.py"},
    "utils.__init__": {"test_core_utils_path_utils.py"},
    "bin.__init__": {"test_core_bin_config_schema.py"},
    "plugins.render": {"test_core_app_plugin_rendering.py"},
    "session.rollout_reconstruction": {"test_core_rollout_reexport.py"},
    "session.turn.prompt": {"test_core_turn_prompt.py"},
    "session.turn.request": {"test_core_turn_request.py"},
    "session.turn.runtime": {"test_core_turn_runtime.py"},
    "session.turn.sampler": {"test_core_turn_sampler.py"},
    "spawn": {"test_core_spawn_landlock.py"},
    "state.service": {"test_core_state_session.py"},
    "tools.context": {"test_core_tools_context.py", "test_core_tool_context.py"},
    "tools.events": {"test_core_tool_events.py"},
    "tools.handlers.dynamic": {"test_core_dynamic_tool_handler.py"},
    "tools.handlers.extension_tools": {"test_core_extension_tools.py"},
    "tools.handlers.list_available_plugins_to_install": {
        "test_core_list_available_plugins_to_install_handler.py"
    },
    "tools.handlers.mcp": {"test_core_mcp_tool_handler.py"},
    "tools.handlers.mcp_resource": {"test_core_mcp_resource_handler.py"},
    "tools.handlers.multi_agents": {"test_core_multi_agents_v1_handler.py"},
    "tools.handlers.multi_agents_v2": {"test_core_multi_agents_v2_handler.py"},
    "tools.handlers.plan": {"test_core_plan_handler.py"},
    "tools.handlers.request_permissions": {"test_core_request_permissions_handler.py"},
    "tools.handlers.request_user_input": {"test_core_request_user_input_handler.py"},
    "tools.handlers.shell": {"test_core_shell_handler.py"},
    "tools.handlers.test_sync": {"test_core_test_sync_handler.py"},
    "tools.handlers.tool_search": {"test_core_tool_search_handler.py"},
    "tools.handlers.unified_exec": {"test_core_unified_exec_handler.py"},
    "tools.handlers.utils": {"test_core_handler_utils.py"},
    "tools.handlers.view_image": {"test_core_view_image_handler.py"},
    "tools.lifecycle": {"test_core_tool_lifecycle.py"},
    "tools.orchestrator": {"test_core_tool_orchestrator.py"},
    "tools.parallel": {"test_core_tool_parallel.py"},
    "tools.registry": {"test_core_tool_registry.py"},
    "tools.router": {"test_core_tool_router.py"},
}


def _module_key(path: Path) -> str:
    rel = path.relative_to(CORE_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _direct_test_candidates(module_key: str) -> set[str]:
    parts = module_key.split(".")
    if parts[-1] == "__init__":
        package_parts = parts[:-1]
        if not package_parts:
            return {"test_core_smoke_suite.py"}
        return {
            f"test_core_{'_'.join(package_parts)}.py",
            f"test_core_{package_parts[-1]}.py",
            f"test_core_{package_parts[-1]}_coordinate.py",
        }
    return {
        f"test_core_{'_'.join(parts)}.py",
        f"test_core_{parts[-1]}.py",
    }


def test_each_core_module_has_focused_test_file() -> None:
    test_files = {path.name for path in TEST_ROOT.glob("test_core*.py")}
    missing: list[str] = []

    for module_path in sorted(CORE_ROOT.rglob("*.py")):
        module_key = _module_key(module_path)
        candidates = _direct_test_candidates(module_key)
        candidates.update(MODULE_TEST_ALIASES.get(module_key, set()))
        if candidates.isdisjoint(test_files):
            missing.append(module_key)

    assert missing == []
