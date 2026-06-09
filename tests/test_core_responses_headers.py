from types import SimpleNamespace

from pycodex.core import (
    ModelClient,
    X_CODEX_INSTALLATION_ID_HEADER,
    X_CODEX_PARENT_THREAD_ID_HEADER,
    X_CODEX_TURN_METADATA_HEADER,
    X_CODEX_WINDOW_ID_HEADER,
    X_OPENAI_SUBAGENT_HEADER,
    build_responses_headers,
    serialize_responses_request,
)
from pycodex.core.client_common import Prompt
from pycodex.protocol import ReasoningSummary, SessionSource, SubAgentSource, ThreadId


TEST_INSTALLATION_ID = "11111111-1111-4111-8111-111111111111"


def _provider() -> SimpleNamespace:
    return SimpleNamespace(is_azure_responses_endpoint=lambda: False)


def _model_info(*, supports_reasoning_summaries: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        slug="gpt-test",
        supports_reasoning_summaries=supports_reasoning_summaries,
        default_reasoning_level=None,
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )


def test_responses_stream_includes_subagent_header_on_review():
    # Rust source: codex/codex-rs/core/tests/responses_headers.rs
    # Rust test: responses_stream_includes_subagent_header_on_review.
    thread_id = ThreadId.new()
    client = ModelClient(
        session_id=thread_id,
        thread_id=thread_id,
        installation_id=TEST_INSTALLATION_ID,
        session_source=SessionSource.subagent(SubAgentSource.review()),
    )

    headers = client.build_responses_identity_headers()
    request = client.build_responses_request(_provider(), Prompt.default(), _model_info())

    assert headers[X_OPENAI_SUBAGENT_HEADER] == "review"
    assert headers[X_CODEX_WINDOW_ID_HEADER] == f"{thread_id}:0"
    assert X_CODEX_PARENT_THREAD_ID_HEADER not in headers
    assert "x-codex-sandbox" not in headers
    assert request["client_metadata"][X_CODEX_INSTALLATION_ID_HEADER] == TEST_INSTALLATION_ID


def test_responses_stream_includes_subagent_header_on_other():
    # Rust source: codex/codex-rs/core/tests/responses_headers.rs
    # Rust test: responses_stream_includes_subagent_header_on_other.
    client = ModelClient(
        session_id="session",
        thread_id=ThreadId.new(),
        installation_id=TEST_INSTALLATION_ID,
        session_source=SessionSource.subagent(SubAgentSource.other_source("my-task")),
    )

    assert client.build_responses_identity_headers()[X_OPENAI_SUBAGENT_HEADER] == "my-task"


def test_responses_respects_model_info_overrides_from_config():
    # Rust source: codex/codex-rs/core/tests/responses_headers.rs
    # Rust test: responses_respects_model_info_overrides_from_config.
    client = ModelClient(
        session_id="session",
        thread_id=ThreadId.new(),
        installation_id=TEST_INSTALLATION_ID,
        session_source=SessionSource.subagent(SubAgentSource.other_source("override-check")),
    )

    request = client.build_responses_request(
        _provider(),
        Prompt.default(),
        _model_info(supports_reasoning_summaries=True),
        effort=None,
        summary=ReasoningSummary.DETAILED,
    )
    serialized = serialize_responses_request(request)

    assert serialized["reasoning"]["summary"] == "detailed"
    assert serialized["include"] == ["reasoning.encrypted_content"]


def test_responses_stream_includes_turn_metadata_header_for_git_workspace_e2e():
    # Rust source: codex/codex-rs/core/tests/responses_headers.rs
    # Rust test: responses_stream_includes_turn_metadata_header_for_git_workspace_e2e.
    first_turn_metadata = '{"turn_id":"turn-1","turn_started_at_unix_ms":123,"sandbox":"none"}'
    second_turn_metadata = '{"turn_id":"turn-2","turn_started_at_unix_ms":456,"sandbox":"none","workspaces":{"/repo":{"latest_git_commit_hash":"abc","associated_remote_urls":{"origin":"https://github.com/openai/codex.git"},"has_changes":false}}}'

    first_headers = build_responses_headers(None, None, first_turn_metadata)
    second_headers = build_responses_headers(None, None, second_turn_metadata)

    assert first_headers[X_CODEX_TURN_METADATA_HEADER] == first_turn_metadata
    assert second_headers[X_CODEX_TURN_METADATA_HEADER] == second_turn_metadata
