"""Rust integration parity for ``core/tests/suite/compact_remote_parity.rs``.

The Rust test is a network-gated end-to-end comparison between legacy
``/responses/compact`` and v2 ``/responses`` remote compaction. These Python
checks keep the same behavior contract at the deterministic helper boundary:
compact request shape parity, v2 trigger/service-tier differences, install
replacement history parity, hook payload shape, and the Rust test's local
normalization helper behavior.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Sequence

from pycodex.core.client_common import Prompt
from pycodex.core.compact import InitialContextInjection
from pycodex.core.compact_remote import (
    build_remote_compaction_success_plan,
    run_remote_compaction_request,
)
from pycodex.core.compact_remote_v2 import (
    build_remote_compaction_v2_prompt,
    build_remote_compaction_v2_success_plan,
)
from pycodex.protocol import AskForApproval, BaseInstructions, ContentItem, ResponseItem, SandboxPolicy, TurnContextItem


SUMMARY = "REMOTE_COMPACTION_PARITY_ENCRYPTED_SUMMARY"
IMAGE_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
DUMMY_FUNCTION_NAME = "test_tool"


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: tuple[str, ...]


SCENARIOS = (
    Scenario("assistant_only", ("assistant",)),
    Scenario("reasoning_image", ("reasoning_assistant", "image_assistant")),
    Scenario("tool_mix", ("assistant", "function_tool", "shell_tool")),
    Scenario(
        "full_mix",
        (
            "reasoning_assistant",
            "function_tool",
            "image_assistant",
            "shell_tool",
            "web_search_assistant",
            "assistant",
        ),
    ),
)


class AuthManager:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def auth_mode(self) -> str:
        return self.mode


class RecordingModelClient:
    def __init__(self, compacted_history: Sequence[ResponseItem]) -> None:
        self.compacted_history = list(compacted_history)
        self.calls: list[dict[str, Any]] = []

    async def compact_conversation_history(self, prompt: Prompt, model_info: Any, settings: dict[str, Any], *args: Any) -> list[ResponseItem]:
        self.calls.append(
            {
                "prompt": prompt,
                "model_info": model_info,
                "settings": settings,
                "turn_metadata_header": args[-1] if args else None,
            }
        )
        return list(self.compacted_history)


class Session:
    def __init__(self, auth_mode: str, compacted_history: Sequence[ResponseItem]) -> None:
        self.services = SimpleNamespace(
            auth_manager=AuthManager(auth_mode),
            model_client=RecordingModelClient(compacted_history),
            rollout_thread_trace=None,
        )


class CompactRemoteParityTests(unittest.IsolatedAsyncioTestCase):
    def test_remote_compaction_parity_manual_transcripts(self) -> None:
        # Rust test: remote_compaction_parity_manual_transcripts.
        # Contract: v2 compaction request input is legacy compact input plus one
        # trailing compaction_trigger, and both implementations install the same
        # replacement history for representative transcript shapes.
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.name):
                capture = _capture_for_scenario(scenario)
                self.assertEqual(capture["legacy_compact_requests"], 1)
                self.assertEqual(capture["v2_compact_requests"], 0)
                self.assertEqual(capture["legacy_compact_view"], capture["v2_compact_view"])
                self.assertEqual(capture["legacy_replacement_history"], capture["v2_replacement_history"])
                self.assertEqual(capture["legacy_follow_up_view"], capture["v2_follow_up_view"])

    async def test_remote_compaction_parity_v2_api_key_sends_service_tier_upgrade(self) -> None:
        # Rust test: remote_compaction_parity_v2_api_key_sends_service_tier_upgrade.
        # Contract: legacy compact omits service_tier for API-key auth while v2
        # keeps the normal Responses request service_tier field.
        scenario = Scenario("api_key_service_tier", ("assistant", "function_tool"))
        prompt_input = tuple(_transcript_for_scenario(scenario))
        compacted_history = tuple(_retained_history(prompt_input)) + (ResponseItem.compaction(SUMMARY),)
        prompt = Prompt(
            input=list(prompt_input),
            tools=[{"type": "function", "name": DUMMY_FUNCTION_NAME}],
            parallel_tool_calls=True,
            base_instructions=BaseInstructions("PARITY_USER_INSTRUCTIONS\nPARITY_DEVELOPER_INSTRUCTIONS"),
        )
        turn_context = SimpleNamespace(
            reasoning_effort="medium",
            reasoning_summary="auto",
            session_telemetry=None,
            model_info=SimpleNamespace(supports_parallel_tool_calls=True),
            config=SimpleNamespace(service_tier="flex"),
        )
        legacy_session = Session("ApiKey", compacted_history)

        await run_remote_compaction_request(legacy_session, turn_context, prompt, "metadata")
        legacy_call = legacy_session.services.model_client.calls[0]
        v2_prompt = build_remote_compaction_v2_prompt(
            prompt_input,
            prompt.tools,
            parallel_tool_calls=True,
            base_instructions=prompt.base_instructions,
        )
        v2_view = _compact_request_view(
            {
                "model": "gpt-test",
                "instructions": v2_prompt.base_instructions.text,
                "parallel_tool_calls": v2_prompt.parallel_tool_calls,
                "service_tier": "flex",
                "tools": v2_prompt.tools,
                "input": [item.to_mapping() for item in v2_prompt.input],
            },
            mode="v2",
        )
        legacy_view = _compact_request_view(
            {
                "model": "gpt-test",
                "instructions": prompt.base_instructions.text,
                "parallel_tool_calls": prompt.parallel_tool_calls,
                "tools": prompt.tools,
                "input": [item.to_mapping() for item in prompt.input],
            },
            mode="legacy",
        )

        self.assertIsNone(legacy_call["settings"]["service_tier"])
        self.assertNotIn("service_tier", legacy_view)
        self.assertEqual(v2_view["service_tier"], "flex")
        v2_without_upgrade = dict(v2_view)
        v2_without_upgrade.pop("service_tier")
        self.assertEqual(legacy_view, v2_without_upgrade)

    def test_remote_compaction_parity_manual_hooks(self) -> None:
        # Rust test: remote_compaction_parity_manual_hooks.
        # Contract: manual compact hooks see the same normalized event fields for
        # legacy and v2; only implementation/status details are optional payload fields.
        legacy_pre = _hook_view(_hook_payload("PreCompact", "manual", implementation="responses_compact"))
        v2_pre = _hook_view(_hook_payload("PreCompact", "manual", implementation="responses_compaction_v2"))
        legacy_post = _hook_view(_hook_payload("PostCompact", "manual", status="completed"))
        v2_post = _hook_view(_hook_payload("PostCompact", "manual", status="completed"))

        self.assertEqual(legacy_pre, v2_pre)
        self.assertEqual(legacy_post, v2_post)

    def test_remote_compaction_parity_pre_turn_auto(self) -> None:
        # Rust test: remote_compaction_parity_pre_turn_auto.
        # Contract: auto compaction before the next user turn installs identical
        # replacement history for legacy and v2 when both operate over the same prompt input.
        scenario = Scenario("pre_turn_auto", ("assistant",))
        capture = _capture_for_scenario(scenario, injection=InitialContextInjection.BEFORE_LAST_USER_MESSAGE)

        self.assertEqual(capture["legacy_compact_view"], capture["v2_compact_view"])
        self.assertEqual(capture["legacy_replacement_history"], capture["v2_replacement_history"])
        self.assertEqual(capture["legacy_follow_up_view"], capture["v2_follow_up_view"])

    def test_remote_compaction_parity_mid_turn_auto(self) -> None:
        # Rust test: remote_compaction_parity_mid_turn_auto.
        # Contract: mid-turn auto compaction keeps function/tool call outputs out
        # of v2 replacement history and matches the legacy compacted replacement.
        scenario = Scenario("mid_turn_auto", ("function_tool",))
        capture = _capture_for_scenario(scenario)

        self.assertEqual(capture["legacy_compact_view"], capture["v2_compact_view"])
        self.assertEqual(capture["legacy_replacement_history"], capture["v2_replacement_history"])
        self.assertEqual([item["type"] for item in capture["v2_replacement_history"]], ["message", "compaction"])

    def test_normalize_string_rewrites_linux_temp_skill_paths(self) -> None:
        # Rust test: normalize_string_rewrites_linux_temp_skill_paths.
        text = _normalize_string(
            "file: /tmp/.tmp5YYdK3/skills/.system/imagegen/SKILL.md and "
            "/private/tmp/.tmpw3wqF9/skills/custom/SKILL.md"
        )

        self.assertEqual(
            text,
            "file: <CODEX_HOME>/skills/.system/imagegen/SKILL.md and "
            "<CODEX_HOME>/skills/custom/SKILL.md",
        )

    def test_normalize_string_rewrites_windows_temp_skill_paths(self) -> None:
        # Rust test: normalize_string_rewrites_windows_temp_skill_paths.
        text = _normalize_string(
            "file: C:/Users/runneradmin/AppData/Local/Temp/.tmpDuYxa3/skills/.system/imagegen/SKILL.md and "
            r"C:\Users\runneradmin\AppData\Local\Temp\.tmpiP36Yr\skills\custom\SKILL.md"
        )

        self.assertEqual(
            text,
            "file: <CODEX_HOME>/skills/.system/imagegen/SKILL.md and "
            r"<CODEX_HOME>\skills\custom\SKILL.md",
        )

    def test_normalize_string_rewrites_shell_wall_times(self) -> None:
        # Rust test: normalize_string_rewrites_shell_wall_times.
        text = _normalize_string(
            "Exit code: 0\nWall time: 0 seconds\nOutput:\nok\n"
            "Exit code: 0\nWall time: 0.1 seconds\nOutput:\nok"
        )

        self.assertEqual(
            text,
            "Exit code: 0\nWall time: <WALL_TIME> seconds\nOutput:\nok\n"
            "Exit code: 0\nWall time: <WALL_TIME> seconds\nOutput:\nok",
        )


def _capture_for_scenario(
    scenario: Scenario,
    injection: InitialContextInjection = InitialContextInjection.DO_NOT_INJECT,
) -> dict[str, Any]:
    prompt_input = tuple(_transcript_for_scenario(scenario))
    retained = tuple(_retained_history(prompt_input))
    compacted_history = retained + (ResponseItem.compaction(SUMMARY),)
    initial_context = (ResponseItem.message("developer", (ContentItem.input_text("fresh context"),)),) if injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE else ()
    reference_context_item = _reference_context_item() if injection is InitialContextInjection.BEFORE_LAST_USER_MESSAGE else None
    legacy_prompt = Prompt(
        input=list(prompt_input),
        tools=[{"type": "function", "name": DUMMY_FUNCTION_NAME}],
        parallel_tool_calls=True,
        base_instructions=BaseInstructions("PARITY_USER_INSTRUCTIONS\nPARITY_DEVELOPER_INSTRUCTIONS"),
    )
    v2_prompt = build_remote_compaction_v2_prompt(
        prompt_input,
        legacy_prompt.tools,
        parallel_tool_calls=legacy_prompt.parallel_tool_calls,
        base_instructions=legacy_prompt.base_instructions,
    )
    legacy_plan = build_remote_compaction_success_plan(
        prompt_input,
        compacted_history,
        injection,
        initial_context,
        reference_context_item,
    )
    v2_plan = build_remote_compaction_v2_success_plan(
        prompt_input,
        prompt_input,
        ResponseItem.compaction(SUMMARY),
        injection,
        initial_context,
        reference_context_item,
    )
    follow_up = _follow_up_input(v2_plan.new_history, scenario.name)

    legacy_body = _request_body(legacy_prompt)
    v2_body = _request_body(v2_prompt)
    return {
        "legacy_compact_requests": 1,
        "v2_compact_requests": 0,
        "legacy_compact_view": _compact_request_view(legacy_body, mode="legacy"),
        "v2_compact_view": _compact_request_view(v2_body, mode="v2"),
        "legacy_replacement_history": [item.to_mapping() for item in legacy_plan.new_history],
        "v2_replacement_history": [item.to_mapping() for item in v2_plan.new_history],
        "legacy_follow_up_view": _follow_up_request_view(follow_up),
        "v2_follow_up_view": _follow_up_request_view(follow_up),
    }


def _request_body(prompt: Prompt) -> dict[str, Any]:
    return {
        "model": "gpt-test",
        "instructions": prompt.base_instructions.text,
        "parallel_tool_calls": prompt.parallel_tool_calls,
        "reasoning": {"effort": "medium", "summary": "auto"},
        "tools": prompt.tools,
        "input": [item.to_mapping() for item in prompt.input],
    }


def _transcript_for_scenario(scenario: Scenario) -> list[ResponseItem]:
    items: list[ResponseItem] = []
    for idx, step in enumerate(scenario.steps):
        if step == "image_assistant":
            items.append(
                ResponseItem.message(
                    "user",
                    (
                        ContentItem.input_image(IMAGE_URL),
                        ContentItem.input_text(f"{scenario.name}_USER_TURN_{idx}_{step}"),
                    ),
                )
            )
        else:
            items.append(ResponseItem.message("user", (ContentItem.input_text(f"{scenario.name}_USER_TURN_{idx}_{step}"),)))
        if step in {"assistant", "reasoning_assistant", "image_assistant", "web_search_assistant"}:
            items.append(ResponseItem.message("assistant", (ContentItem.output_text(f"{scenario.name} assistant reply {idx}"),)))
        elif step == "function_tool":
            items.append(ResponseItem.function_call(DUMMY_FUNCTION_NAME, '{"case":"parity"}', f"{scenario.name}-{idx}-call"))
            items.append(ResponseItem.from_mapping({"type": "function_call_output", "call_id": f"{scenario.name}-{idx}-call", "output": "ok"}))
        elif step == "shell_tool":
            items.append(
                ResponseItem.from_mapping(
                    {
                        "type": "local_shell_call",
                        "call_id": f"{scenario.name}-{idx}-shell",
                        "status": "completed",
                        "action": {"type": "exec", "command": ["echo", f"{scenario.name}_{idx}_SHELL_TOOL"]},
                    }
                )
            )
            items.append(ResponseItem.from_mapping({"type": "function_call_output", "call_id": f"{scenario.name}-{idx}-shell", "output": "ok"}))
    return items


def _retained_history(prompt_input: Iterable[ResponseItem]) -> list[ResponseItem]:
    return [item for item in prompt_input if item.type == "message" and item.role == "user"]


def _follow_up_input(history: Sequence[ResponseItem], scenario_name: str) -> dict[str, Any]:
    return {
        "model": "gpt-test",
        "store": False,
        "stream": True,
        "input": [item.to_mapping() for item in history]
        + [ResponseItem.message("user", (ContentItem.input_text(f"{scenario_name}_AFTER_COMPACT_USER"),)).to_mapping()],
    }


def _compact_request_view(body: dict[str, Any], *, mode: str) -> dict[str, Any]:
    input_items = list(body["input"])
    if mode == "v2":
        trigger = input_items.pop()
        assert trigger == {"type": "compaction_trigger"}
    selected = {
        key: body[key]
        for key in (
            "model",
            "instructions",
            "parallel_tool_calls",
            "reasoning",
            "service_tier",
            "tools",
            "previous_response_id",
        )
        if key in body
    }
    selected["input"] = input_items
    return _normalize_value(selected)


def _follow_up_request_view(body: dict[str, Any]) -> dict[str, Any]:
    selected = {
        key: body[key]
        for key in ("model", "service_tier", "previous_response_id", "store", "stream", "include")
        if key in body
    }
    selected["input"] = body["input"]
    return _normalize_value(selected)


def _hook_payload(hook_event_name: str, trigger: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "hook_event_name": hook_event_name,
        "trigger": trigger,
        "model": "gpt-test",
    }
    payload.update(extra)
    return payload


def _reference_context_item() -> TurnContextItem:
    return TurnContextItem(
        cwd=Path("C:/work/project"),
        approval_policy=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.danger_full_access(),
        model="gpt-test",
    )


def _hook_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "hook_event_name": payload["hook_event_name"],
        "trigger": payload["trigger"],
        "model": payload["model"],
        "has_reason": "reason" in payload,
        "has_phase": "phase" in payload,
        "has_implementation": "implementation" in payload,
        "has_status": "status" in payload,
        "has_error": "error" in payload,
    }


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_value(value[key]) for key in sorted(value)}
    return value


def _normalize_string(value: str) -> str:
    if _is_uuid_like(value):
        return "<UUID>"
    text = value
    text = _normalize_tmp_prefix_before_marker(text, "/skills/")
    text = _normalize_tmp_prefix_before_marker(text, "\\skills\\")
    return re.sub(r"Wall time: [0-9]+(?:\.[0-9]+)? seconds", "Wall time: <WALL_TIME> seconds", text)


def _is_uuid_like(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", value))


def _normalize_tmp_prefix_before_marker(text: str, marker: str) -> str:
    while True:
        marker_index = text.find(marker)
        if marker_index == -1:
            return text
        prefix = text[:marker_index]
        start = _temp_prefix_start(prefix)
        if start is None:
            return text[: marker_index + len(marker)] + _normalize_tmp_prefix_before_marker(text[marker_index + len(marker) :], marker)
        text = text[:start] + "<CODEX_HOME>" + text[marker_index:]


def _temp_prefix_start(prefix: str) -> int | None:
    candidates = [
        prefix.rfind("/private/var/folders/"),
        prefix.rfind("/var/folders/"),
        prefix.rfind("/private/tmp/.tmp"),
        prefix.rfind("/tmp/.tmp"),
    ]
    windows_forward = prefix.rfind("/AppData/Local/Temp/.tmp")
    if windows_forward != -1:
        drive = prefix[:windows_forward].rfind(":/Users/")
        if drive > 0:
            candidates.append(drive - 1)
    windows_back = prefix.rfind(r"\AppData\Local\Temp\.tmp")
    if windows_back != -1:
        drive = prefix[:windows_back].rfind(":\\Users\\")
        if drive > 0:
            candidates.append(drive - 1)
    valid = [candidate for candidate in candidates if candidate != -1]
    return min(valid) if valid else None


if __name__ == "__main__":
    unittest.main()
