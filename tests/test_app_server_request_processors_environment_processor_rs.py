"""Rust parity tests for ``request_processors/environment_processor.rs``."""

import pytest

from pycodex.app_server.request_processors_environment_processor import (
    EnvironmentRequestProcessor,
    EnvironmentRequestProcessorError,
)
from pycodex.app_server_protocol import EnvironmentAddParams, EnvironmentAddResponse


class FakeEnvironmentManager:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str]] = []
        self.error: Exception | None = None

    def upsert_environment(self, environment_id: str, exec_server_url: str) -> None:
        if self.error is not None:
            raise self.error
        self.upserts.append((environment_id, exec_server_url))


def test_environment_request_processor_new_stores_environment_manager() -> None:
    # Rust: EnvironmentRequestProcessor::new stores the Arc<EnvironmentManager>.
    manager = FakeEnvironmentManager()

    processor = EnvironmentRequestProcessor.new(manager)

    assert processor.environment_manager is manager


def test_environment_add_upserts_environment_and_returns_empty_response() -> None:
    # Rust: environment_add delegates id/url and returns Some(EnvironmentAddResponse).
    manager = FakeEnvironmentManager()
    processor = EnvironmentRequestProcessor(manager)

    response = processor.environment_add(EnvironmentAddParams("env-1", "http://127.0.0.1:9000"))

    assert manager.upserts == [("env-1", "http://127.0.0.1:9000")]
    assert response == EnvironmentAddResponse()


def test_environment_add_accepts_camel_case_params_mapping() -> None:
    # Protocol dependency already owns parsing; this processor accepts that boundary shape.
    manager = FakeEnvironmentManager()
    processor = EnvironmentRequestProcessor(manager)

    processor.environment_add({"environmentId": "env-2", "execServerUrl": "http://localhost:7777"})

    assert manager.upserts == [("env-2", "http://localhost:7777")]


def test_environment_add_maps_manager_error_to_invalid_request() -> None:
    # Rust: .map_err(|err| invalid_request(err.to_string())).
    manager = FakeEnvironmentManager()
    manager.error = RuntimeError("cannot add environment")
    processor = EnvironmentRequestProcessor(manager)

    with pytest.raises(EnvironmentRequestProcessorError) as caught:
        processor.environment_add(EnvironmentAddParams("env-3", "http://localhost:8888"))

    assert caught.value.error.code == -32600
    assert caught.value.error.message == "cannot add environment"
    assert caught.value.error.data is None
