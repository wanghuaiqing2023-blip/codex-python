"""Rust parity tests for ``request_processors/remote_control_processor.rs``."""

from __future__ import annotations

from dataclasses import dataclass

from pycodex.app_server.request_processors_remote_control_processor import (
    RemoteControlRequestProcessor,
    RemoteControlRequestProcessorError,
)


@dataclass
class FakeStatus:
    status: str = "connected"
    server_name: str = "desk"
    installation_id: str = "install-1"
    environment_id: str | None = "env-1"


class FakeUnavailable(Exception):
    pass


class FakeRemoteControlHandle:
    def __init__(self) -> None:
        self.enabled = False
        self.disabled = False

    def enable(self) -> FakeStatus:
        self.enabled = True
        return FakeStatus(status="connecting")

    def disable(self) -> FakeStatus:
        self.disabled = True
        return FakeStatus(status="disabled", environment_id=None)

    def status(self) -> FakeStatus:
        return FakeStatus(status="connected")


def test_remote_control_processor_missing_handle_maps_internal_error() -> None:
    # Rust source: handle() maps None to internal_error.
    processor = RemoteControlRequestProcessor.new(None)

    for method_name in ("enable", "disable", "status_read"):
        try:
            getattr(processor, method_name)()
        except RemoteControlRequestProcessorError as exc:
            assert exc.error.code == -32603
            assert exc.error.message == "remote control is unavailable for this app-server"
        else:
            raise AssertionError(f"expected missing-handle error for {method_name}")


def test_remote_control_enable_maps_handle_status_and_unavailable_error() -> None:
    # Rust source: enable() maps handle.enable() status through RemoteControlEnableResponse::from.
    handle = FakeRemoteControlHandle()
    processor = RemoteControlRequestProcessor(handle)

    response = processor.enable()

    assert handle.enabled is True
    assert response.to_mapping() == {
        "status": "connecting",
        "server_name": "desk",
        "installation_id": "install-1",
        "environment_id": "env-1",
    }

    class FailingHandle(FakeRemoteControlHandle):
        def enable(self) -> FakeStatus:
            raise FakeUnavailable("already claimed")

    try:
        RemoteControlRequestProcessor(FailingHandle()).enable()
    except RemoteControlRequestProcessorError as exc:
        assert exc.error.code == -32600
        assert exc.error.message == "already claimed"
    else:
        raise AssertionError("expected unavailable error")


def test_remote_control_disable_and_status_read_project_status_fields() -> None:
    # Rust source: disable() and status_read() copy handle status fields into protocol responses.
    handle = FakeRemoteControlHandle()
    processor = RemoteControlRequestProcessor(handle)

    disabled = processor.disable()
    status = processor.status_read()

    assert handle.disabled is True
    assert disabled.to_mapping() == {
        "status": "disabled",
        "server_name": "desk",
        "installation_id": "install-1",
        "environment_id": None,
    }
    assert status.to_mapping() == {
        "status": "connected",
        "server_name": "desk",
        "installation_id": "install-1",
        "environment_id": "env-1",
    }


def test_remote_control_processor_accepts_mapping_status_shapes() -> None:
    # Rust source: response constructors only need the four status snapshot fields.
    class MappingHandle:
        def enable(self) -> dict[str, str]:
            return {
                "status": "connected",
                "serverName": "srv",
                "installationId": "inst",
                "environmentId": "env",
            }

        def disable(self) -> dict[str, str | None]:
            return {
                "status": "disabled",
                "server_name": "srv",
                "installation_id": "inst",
                "environment_id": None,
            }

        def status(self) -> dict[str, str]:
            return {
                "status": "errored",
                "server_name": "srv",
                "installation_id": "inst",
                "environment_id": "env",
            }

    processor = RemoteControlRequestProcessor(MappingHandle())

    assert processor.enable().status.value == "connected"
    assert processor.disable().environment_id is None
    assert processor.status_read().status.value == "errored"
