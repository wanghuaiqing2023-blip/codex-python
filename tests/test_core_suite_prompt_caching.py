
"""Parity tests for Rust core/tests/suite/prompt_caching.rs.

Rust observes Responses API request bodies.  The Python tests assert the same
stable request-body contracts: tools and instructions do not drift across turns,
prompt-cache keys stay stable, cached contextual prefixes are reused, and
settings changes append fresh context after the cached prefix.
"""

from __future__ import annotations

from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.client_common import Prompt
from pycodex.protocol import BaseInstructions, ContentItem, ResponseItem

ENV_OPEN = "<environment_context>"
ENV_CLOSE = "</environment_context>"
APPLY_PATCH_TOOL_INSTRUCTIONS = "Use the apply_patch tool to edit files."


def _message(role: str, *texts: str) -> ResponseItem:
    kind = ContentItem.output_text if role == "assistant" else ContentItem.input_text
    return ResponseItem.message(role, tuple(kind(text) for text in texts))


def _developer(text: str) -> ResponseItem:
    return _message("developer", text)


def _user(*texts: str) -> ResponseItem:
    return _message("user", *texts)


def _env(cwd: str = "C:/work/project") -> str:
    return f"{ENV_OPEN}\n<cwd>{cwd}</cwd>\n<shell>powershell</shell>\n<current_date>2026-06-11</current_date>\n<timezone>Asia/Shanghai</timezone>\n{ENV_CLOSE}"


def _permissions(policy: str = "on-request") -> ResponseItem:
    return _developer(f"<permissions instructions>approval_policy: {policy}</permissions instructions>")


def _model_info(slug: str = "gpt-5.2") -> SimpleNamespace:
    return SimpleNamespace(
        slug=slug,
        supports_reasoning_summaries=False,
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )


def _request(input_items, *, tools=None, instructions="base instructions", cache_key="stable-cache-key", model="gpt-5.2"):
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    client.with_prompt_cache_key_override(cache_key)
    prompt = Prompt(
        input=list(input_items),
        tools=list(tools or _default_tools()),
        base_instructions=BaseInstructions(instructions),
    )
    return client.build_responses_request(
        SimpleNamespace(is_azure_responses_endpoint=lambda: False),
        prompt,
        _model_info(model),
    )


def _default_tools():
    return [
        {"type": "function", "name": "exec_command"},
        {"type": "function", "name": "write_stdin"},
        {"type": "function", "name": "update_plan"},
        {"type": "function", "name": "apply_patch"},
        {"type": "function", "name": "web_search"},
    ]


def _tool_names(request) -> list[str]:
    return [tool.get("name") or tool.get("type") for tool in request["tools"]]


def _texts(item: ResponseItem) -> list[str]:
    return [content.text or "" for content in item.content]


def _cached_prefix() -> list[ResponseItem]:
    return [
        _permissions("on-request"),
        _user("<user_instructions>be consistent and helpful</user_instructions>", _env()),
    ]


def _first_request():
    return _request(_cached_prefix() + [_user("hello 1")])


def _second_request(extra_items=None):
    return _request(_cached_prefix() + [_user("hello 1")] + list(extra_items or ()) + [_user("hello 2")])


def test_prompt_tools_are_consistent_across_requests() -> None:
    """Rust test: prompt_tools_are_consistent_across_requests."""

    first = _first_request()
    second = _second_request()

    assert first["instructions"] == "base instructions"
    assert second["instructions"] == first["instructions"]
    assert _tool_names(first) == ["exec_command", "write_stdin", "update_plan", "apply_patch", "web_search"]
    assert _tool_names(second) == _tool_names(first)


def test_gpt_5_tools_without_apply_patch_append_apply_patch_instructions() -> None:
    """Rust test: gpt_5_tools_without_apply_patch_append_apply_patch_instructions."""

    tools_without_apply_patch = [tool for tool in _default_tools() if tool["name"] != "apply_patch"]
    instructions = "base instructions\n" + APPLY_PATCH_TOOL_INSTRUCTIONS
    first = _request(_cached_prefix() + [_user("hello 1")], tools=tools_without_apply_patch, instructions=instructions)
    second = _request(_cached_prefix() + [_user("hello 1"), _user("hello 2")], tools=tools_without_apply_patch, instructions=instructions)

    assert "base instructions" in first["instructions"]
    assert APPLY_PATCH_TOOL_INSTRUCTIONS in first["instructions"]
    assert second["instructions"].replace("\r\n", "\n") == first["instructions"].replace("\r\n", "\n")
    assert "apply_patch" not in _tool_names(first)


def test_prefixes_context_and_instructions_once_and_consistently_across_requests() -> None:
    """Rust test: prefixes_context_and_instructions_once_and_consistently_across_requests."""

    first = _first_request()
    second = _second_request()
    first_input = first["input"]
    second_input = second["input"]

    assert len(first_input) == 3
    assert "be consistent and helpful" in _texts(first_input[1])[0]
    assert _texts(first_input[1])[1].startswith(ENV_OPEN)
    assert "<cwd>C:/work/project</cwd>" in _texts(first_input[1])[1]
    assert second_input[: len(first_input)] == first_input
    assert _texts(second_input[-1]) == ["hello 2"]


def test_overrides_turn_context_but_keeps_cached_prefix_and_key_constant() -> None:
    """Rust test: overrides_turn_context_but_keeps_cached_prefix_and_key_constant."""

    first = _first_request()
    permissions_update = _permissions("never")
    second = _second_request([permissions_update])

    assert first["prompt_cache_key"] == second["prompt_cache_key"]
    assert second["input"][: len(first["input"])] == first["input"]
    assert second["input"][len(first["input"])] != first["input"][0]
    assert "never" in _texts(second["input"][len(first["input"])])[0]
    assert _texts(second["input"][-1]) == ["hello 2"]


def test_override_before_first_turn_emits_environment_context() -> None:
    """Rust test: override_before_first_turn_emits_environment_context."""

    request = _request([_permissions("never"), _user(_env("C:/override")), _user("first message")], model="gpt-5.4")
    texts = [text for item in request["input"] for text in _texts(item)]

    assert request["model"] == "gpt-5.4"
    assert any(text.startswith(ENV_OPEN) and "<cwd>C:/override</cwd>" in text for text in texts)
    assert any("approval_policy: never" in text for text in texts)
    assert "first message" in texts


def test_per_turn_overrides_keep_cached_prefix_and_key_constant() -> None:
    """Rust test: per_turn_overrides_keep_cached_prefix_and_key_constant."""

    first = _first_request()
    settings_update = _developer("<model_switch>o3 high reasoning</model_switch>\n<permissions instructions>approval_policy: never</permissions instructions>")
    env_update = _user(_env("C:/per-turn"))
    second = _second_request([settings_update, env_update])

    assert first["prompt_cache_key"] == second["prompt_cache_key"]
    assert second["input"][: len(first["input"])] == first["input"]
    assert "<model_switch>" in _texts(second["input"][len(first["input"])])[0]
    assert _texts(second["input"][len(first["input"]) + 1])[0].startswith(ENV_OPEN)
    assert _texts(second["input"][-1]) == ["hello 2"]


def test_send_user_turn_with_no_changes_does_not_send_environment_context() -> None:
    """Rust test: send_user_turn_with_no_changes_does_not_send_environment_context."""

    first = _first_request()
    second = _second_request()

    assert second["input"][:3] == first["input"]
    new_items = second["input"][len(first["input"]):]
    assert len(new_items) == 1
    assert _texts(new_items[0]) == ["hello 2"]
    assert all(not any(text.startswith(ENV_OPEN) for text in _texts(item)) for item in new_items)


def test_send_user_turn_with_changes_sends_environment_context() -> None:
    """Rust test: send_user_turn_with_changes_sends_environment_context."""

    first = _first_request()
    settings_update = _developer("<model_switch>o3</model_switch>\n<permissions instructions>approval_policy: never</permissions instructions>")
    second = _second_request([settings_update])

    assert second["input"][: len(first["input"])] == first["input"]
    assert second["input"][len(first["input"])] != first["input"][0]
    assert "<model_switch>" in _texts(second["input"][len(first["input"])])[0]
    assert _texts(second["input"][-1]) == ["hello 2"]
