from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from pycodex.protocol import ElicitationAction
from pycodex.rmcp_client.elicitation_client_service import (
    ElicitationClientService,
    elicitation_response_result,
    restore_context_meta,
)
from pycodex.rmcp_client.logging_client_handler import LoggingClientHandler
from pycodex.rmcp_client.rmcp_client import ElicitationPauseState, ElicitationResponse


def test_restore_context_meta_removes_progress_token() -> None:
    # Rust: restore_context_meta_adds_elicitation_meta_and_removes_progress_token.
    request = {
        "message": "Confirm?",
        "requestedSchema": {"type": "object"},
    }
    restored = restore_context_meta(
        request,
        {
            "progressToken": "progress-token",
            "persist": ["session", "always"],
        },
    )

    assert restored == {
        "message": "Confirm?",
        "requestedSchema": {"type": "object"},
        "_meta": {"persist": ["session", "always"]},
    }


def test_elicitation_response_result_serializes_response_meta() -> None:
    # Rust: elicitation_response_result_serializes_response_meta.
    result = elicitation_response_result(
        ElicitationResponse(
            action=ElicitationAction.ACCEPT,
            content={"confirmed": True},
            meta={"persist": "always"},
        )
    )
    assert result == {
        "action": "accept",
        "content": {"confirmed": True},
        "_meta": {"persist": "always"},
    }


@pytest.mark.asyncio
async def test_elicitation_service_pauses_while_ui_response_is_pending() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    observed: list[tuple[Any, Any]] = []
    pause_state = ElicitationPauseState()

    async def send(request_id: Any, request: Any) -> ElicitationResponse:
        observed.append((request_id, request))
        entered.set()
        await release.wait()
        return ElicitationResponse(ElicitationAction.DECLINE)

    service = ElicitationClientService(
        {"name": "test-client"},
        send,
        pause_state,
    )
    task = asyncio.create_task(
        service.handle_request(
            {
                "method": "elicitation/create",
                "params": {"message": "Confirm?"},
            },
            request_id=7,
            context_meta={"progressToken": "p", "persist": "session"},
        )
    )
    await entered.wait()
    assert pause_state.is_paused
    release.set()
    result = await task

    assert not pause_state.is_paused
    assert observed == [
        (
            7,
            {
                "message": "Confirm?",
                "_meta": {"persist": "session"},
            },
        )
    ]
    assert result == {"action": "decline"}


@pytest.mark.asyncio
async def test_logging_handler_maps_mcp_levels(caplog: pytest.LogCaptureFixture) -> None:
    # Rust: LoggingClientHandler::on_logging_message level mapping.
    async def send(_request_id: Any, _request: Any) -> ElicitationResponse:
        return ElicitationResponse(ElicitationAction.CANCEL)

    handler = LoggingClientHandler({"name": "test"}, send)
    with caplog.at_level(logging.DEBUG):
        await handler.on_logging_message(
            {"level": "error", "logger": "fixture", "data": "bad"}
        )
        await handler.on_logging_message(
            {"level": "warning", "logger": "fixture", "data": "warn"}
        )
        await handler.on_logging_message(
            {"level": "info", "logger": "fixture", "data": "ok"}
        )
        await handler.on_logging_message(
            {"level": "debug", "logger": "fixture", "data": "trace"}
        )

    levels = [record.levelno for record in caplog.records]
    assert logging.ERROR in levels
    assert logging.WARNING in levels
    assert logging.INFO in levels
    assert logging.DEBUG in levels

