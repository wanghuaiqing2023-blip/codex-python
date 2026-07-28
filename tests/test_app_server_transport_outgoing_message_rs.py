from __future__ import annotations

from pycodex.app_server_transport.outgoing_message import ConnectionId
from pycodex.app_server_transport.outgoing_message import OutgoingError
from pycodex.app_server_transport.outgoing_message import OutgoingMessage
from pycodex.app_server_transport.outgoing_message import OutgoingResponse
from pycodex.app_server_transport.outgoing_message import QueuedOutgoingMessage


def test_connection_id_display_matches_inner_integer() -> None:
    assert str(ConnectionId(42)) == "42"


def test_outgoing_response_serializes_untagged() -> None:
    message = OutgoingMessage.response(OutgoingResponse(id=7, result={"ok": True}))

    assert message.to_mapping() == {"id": 7, "result": {"ok": True}}


def test_outgoing_error_serializes_untagged() -> None:
    message = OutgoingMessage.error(
        OutgoingError(error={"code": -32001, "message": "busy"}, id=7)
    )

    assert message.to_mapping() == {
        "error": {"code": -32001, "message": "busy"},
        "id": 7,
    }


def test_queued_outgoing_message_new_has_no_completion_sender() -> None:
    queued = QueuedOutgoingMessage.new(
        OutgoingMessage.app_server_notification({"method": "initialized"})
    )

    assert queued.write_complete_tx is None
