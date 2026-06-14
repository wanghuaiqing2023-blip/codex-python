from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/interrupts.rs
# Behavior contract: queue prompt/lifecycle interrupts, remove resolved prompt
# requests by variant-specific ids, keep lifecycle events, and flush FIFO through
# ChatWidget handler names.

from pycodex.tui.chatwidget.interrupts import InterruptManager, QueuedInterrupt, command_execution, exec_approval, resolved_request, user_input


def test_remove_resolved_prompt_removes_matching_user_input_only_matches_rust_test():
    manager = InterruptManager.new()
    manager.push_user_input(user_input("call-a", "turn"))
    manager.push_user_input(user_input("call-b", "turn"))

    assert manager.remove_resolved_prompt(resolved_request("UserInput", call_id="call-b")) is True

    assert len(manager.queue) == 1
    remaining = manager.queue[0]
    assert remaining.kind == "RequestUserInput"
    assert remaining.payload["item_id"] == "call-a"


def test_remove_resolved_prompt_matches_exec_approval_id_matches_rust_test():
    manager = InterruptManager.new()
    manager.push_exec_approval(exec_approval("call", "approval"))

    assert manager.remove_resolved_prompt(resolved_request("ExecApproval", id="call")) is False
    assert len(manager.queue) == 1

    assert manager.remove_resolved_prompt(resolved_request("ExecApproval", id="approval")) is True
    assert manager.is_empty() is True


def test_remove_resolved_prompt_keeps_lifecycle_events_matches_rust_test():
    manager = InterruptManager.new()
    manager.push_item_started(command_execution("call"))

    assert manager.remove_resolved_prompt(resolved_request("ExecApproval", id="call")) is False

    assert len(manager.queue) == 1
    assert manager.queue[0].kind == "ItemStarted"


def test_remove_resolved_prompt_matches_all_prompt_variants():
    manager = InterruptManager.new()
    manager.push_apply_patch_approval({"call_id": "patch"})
    manager.push_elicitation("req-1", {"server_name": "srv"})
    manager.push_request_permissions({"call_id": "perm"})

    assert manager.remove_resolved_prompt(resolved_request("FileChangeApproval", id="patch")) is True
    assert manager.remove_resolved_prompt(resolved_request("McpElicitation", server_name="other", request_id="req-1")) is False
    assert manager.remove_resolved_prompt(resolved_request("McpElicitation", server_name="srv", request_id="req-1")) is True
    assert manager.remove_resolved_prompt(resolved_request("PermissionsApproval", id="perm")) is True
    assert manager.is_empty() is True


def test_exec_approval_without_approval_id_falls_back_to_call_id():
    manager = InterruptManager.new()
    manager.push_exec_approval(exec_approval("call", None))

    assert manager.remove_resolved_prompt(resolved_request("ExecApproval", id="call")) is True


def test_flush_all_dispatches_fifo_and_clears_queue():
    class Chat:
        def __init__(self):
            self.calls = []

        def handle_exec_approval_now(self, event):
            self.calls.append(("exec", event["call_id"]))

        def handle_apply_patch_approval_now(self, event):
            self.calls.append(("patch", event["call_id"]))

        def handle_elicitation_request_now(self, request_id, params):
            self.calls.append(("elicitation", request_id, params["server_name"]))

        def handle_request_permissions_now(self, event):
            self.calls.append(("permissions", event["call_id"]))

        def handle_request_user_input_now(self, event):
            self.calls.append(("user_input", event["item_id"]))

        def handle_queued_item_started_now(self, item):
            self.calls.append(("started", item["id"]))

        def handle_queued_item_completed_now(self, item):
            self.calls.append(("completed", item["id"]))

    manager = InterruptManager.new()
    manager.push_exec_approval(exec_approval("exec"))
    manager.push_apply_patch_approval({"call_id": "patch"})
    manager.push_elicitation("req", {"server_name": "srv"})
    manager.push_request_permissions({"call_id": "perm"})
    manager.push_user_input(user_input("input"))
    manager.push_item_started(command_execution("start"))
    manager.push_item_completed(command_execution("done"))
    chat = Chat()

    flushed = manager.flush_all(chat)

    assert [item.kind for item in flushed] == [
        "ExecApproval",
        "ApplyPatchApproval",
        "Elicitation",
        "RequestPermissions",
        "RequestUserInput",
        "ItemStarted",
        "ItemCompleted",
    ]
    assert manager.is_empty() is True
    assert chat.calls == [
        ("exec", "exec"),
        ("patch", "patch"),
        ("elicitation", "req", "srv"),
        ("permissions", "perm"),
        ("user_input", "input"),
        ("started", "start"),
        ("completed", "done"),
    ]


def test_queued_interrupt_constructor_shapes_are_stable():
    assert QueuedInterrupt.ExecApproval({"call_id": "x"}).kind == "ExecApproval"
    assert QueuedInterrupt.Elicitation("req", {"server_name": "srv"}).request_id == "req"
