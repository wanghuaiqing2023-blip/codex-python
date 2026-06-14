# Parity source: codex-rs/tui/src/hooks_rpc.rs

import pytest

from pycodex.tui.hooks_rpc import (
    HookMetadata,
    HookTrustUpdate,
    HooksListEntry,
    HooksListResponse,
    fetch_hooks_list,
    hook_needs_review,
    hooks_list_entry_for_cwd,
    write_hook_trust,
    write_hook_trusts,
)


class RequestHandle:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.requests = []

    async def request_typed(self, request):
        self.requests.append(request)
        if self.exc is not None:
            raise self.exc
        return self.response


@pytest.mark.asyncio
async def test_fetch_hooks_list_sends_hooks_list_request_with_cwd(tmp_path):
    response = HooksListResponse([HooksListEntry(cwd=tmp_path)])
    handle = RequestHandle(response=response)

    result = await fetch_hooks_list(handle, tmp_path)

    assert result == response
    request = handle.requests[0]
    assert request["type"] == "HooksList"
    assert request["request_id"].startswith("hooks-list-")
    assert request["params"] == {"cwds": [str(tmp_path)]}


@pytest.mark.asyncio
async def test_fetch_hooks_list_wraps_request_errors(tmp_path):
    handle = RequestHandle(exc=ValueError("boom"))

    with pytest.raises(RuntimeError, match="hooks/list failed in TUI"):
        await fetch_hooks_list(handle, tmp_path)


def test_hooks_list_entry_for_cwd_returns_matching_entry(tmp_path):
    target = tmp_path / "target"
    other = tmp_path / "other"
    response = HooksListResponse([
        HooksListEntry(cwd=other, warnings=["w"]),
        HooksListEntry(cwd=target, hooks=["hook"]),
    ])

    assert hooks_list_entry_for_cwd(response, target) == HooksListEntry(cwd=target, hooks=["hook"])


def test_hooks_list_entry_for_cwd_returns_empty_entry_when_missing(tmp_path):
    response = HooksListResponse([])

    entry = hooks_list_entry_for_cwd(response, tmp_path)

    assert entry == HooksListEntry(cwd=tmp_path, hooks=[], warnings=[], errors=[])


def test_hooks_list_entry_for_cwd_accepts_mapping_response_and_preserves_lists(tmp_path):
    response = {
        "data": [
            {
                "cwd": str(tmp_path),
                "hooks": ["hook"],
                "warnings": ["warning"],
                "errors": ["error"],
            }
        ]
    }

    entry = hooks_list_entry_for_cwd(response, tmp_path)

    assert entry == HooksListEntry(
        cwd=tmp_path,
        hooks=["hook"],
        warnings=["warning"],
        errors=["error"],
    )


def test_hook_needs_review_matches_untrusted_or_modified_only():
    assert hook_needs_review(HookMetadata("Untrusted")) is True
    assert hook_needs_review(HookMetadata("Modified")) is True
    assert hook_needs_review({"trust_status": "Trusted"}) is False
    assert hook_needs_review({"trust_status": "Unknown"}) is False


@pytest.mark.asyncio
async def test_write_hook_trusts_sends_config_batch_write_upsert():
    handle = RequestHandle(response={"ok": True})

    result = await write_hook_trusts(
        handle,
        [HookTrustUpdate("hook-a", "hash-a"), HookTrustUpdate("hook-b", "hash-b")],
    )

    assert result == {"ok": True}
    request = handle.requests[0]
    assert request["type"] == "ConfigBatchWrite"
    assert request["request_id"].startswith("hooks-config-write-")
    params = request["params"]
    assert params["file_path"] is None
    assert params["expected_version"] is None
    assert params["reload_user_config"] is True
    assert params["edits"] == [
        {
            "key_path": "hooks.state",
            "value": {
                "hook-a": {"trusted_hash": "hash-a"},
                "hook-b": {"trusted_hash": "hash-b"},
            },
            "merge_strategy": "Upsert",
        }
    ]


@pytest.mark.asyncio
async def test_write_hook_trust_wraps_single_update():
    handle = RequestHandle(response="written")

    result = await write_hook_trust(handle, "hook-key", "hash")

    assert result == "written"
    value = handle.requests[0]["params"]["edits"][0]["value"]
    assert value == {"hook-key": {"trusted_hash": "hash"}}


@pytest.mark.asyncio
async def test_write_hook_trusts_wraps_request_errors():
    handle = RequestHandle(exc=ValueError("boom"))

    with pytest.raises(RuntimeError, match="config/batchWrite failed"):
        await write_hook_trusts(handle, [])
