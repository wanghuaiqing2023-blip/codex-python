import json

from pycodex.core import ModelClient
from pycodex.core.client_common import Prompt
from pycodex.core.http_transport import _parse_responses_sse_stream, _provider_responses_endpoint
from pycodex.protocol import BaseInstructions, ContentItem, ResponseItem
from pycodex.rollout import (
    GitInfo,
    SessionMeta,
    SessionMetaLine,
    materialize_session_rollout,
    read_response_items_from_rollout,
    read_session_meta_line,
)


def _cli_sse_response(text: str = "fixture hello") -> str:
    return (
        'data: {"type":"response.created","response":{"id":"resp-fixture"}}\n\n'
        f'data: {json.dumps({"type": "response.output_item.done", "item": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}})}\n\n'
        'data: {"type":"response.completed","response":{"id":"resp-fixture"}}\n\n'
    )


def test_responses_mode_stream_cli():
    # Rust source: codex/codex-rs/core/tests/suite/cli_stream.rs
    # Rust test: responses_mode_stream_cli.
    parsed = _parse_responses_sse_stream(_cli_sse_response("hi"))
    response_items = parsed["response_items"]

    assert response_items[0].role == "assistant"
    assert response_items[0].content[0].text == "hi"


def test_responses_mode_stream_cli_supports_openai_base_url_config_override():
    # Rust source: codex/codex-rs/core/tests/suite/cli_stream.rs
    # Rust test: responses_mode_stream_cli_supports_openai_base_url_config_override.
    provider = {"base_url": "https://mock.example/v1"}

    assert _provider_responses_endpoint(provider) == "https://mock.example/v1/responses"


def test_exec_cli_applies_model_instructions_file():
    # Rust source: codex/codex-rs/core/tests/suite/cli_stream.rs
    # Rust test: exec_cli_applies_model_instructions_file.
    marker = "cli-model-instructions-file-marker"
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    prompt = Prompt.default()
    prompt.base_instructions = BaseInstructions(marker)
    provider = {"is_azure_responses_endpoint": lambda: False}
    model_info = type(
        "ModelInfo",
        (),
        {
            "slug": "gpt-test",
            "supports_reasoning_summaries": False,
            "support_verbosity": False,
            "service_tier_for_request": staticmethod(lambda tier: tier),
        },
    )()

    request = client.build_responses_request(provider, prompt, model_info)

    assert marker in request["instructions"]


def test_exec_cli_profile_applies_model_instructions_file():
    # Rust source: codex/codex-rs/core/tests/suite/cli_stream.rs
    # Rust test: exec_cli_profile_applies_model_instructions_file.
    marker = "cli-profile-model-instructions-file-marker"
    base = BaseInstructions(marker)

    assert base.text == marker


def test_responses_api_stream_cli():
    # Rust source: codex/codex-rs/core/tests/suite/cli_stream.rs
    # Rust test: responses_api_stream_cli.
    parsed = _parse_responses_sse_stream(_cli_sse_response())

    assert parsed["raw_result"]["id"] == "resp-fixture"
    assert parsed["response_items"][0].content[0].text == "fixture hello"


def test_integration_creates_and_checks_session_file(tmp_path):
    # Rust source: codex/codex-rs/core/tests/suite/cli_stream.rs
    # Rust test: integration_creates_and_checks_session_file.
    thread_id = "aaaaaaaa-1111-2222-3333-444444444444"
    marker = "integration-test-marker"
    rollout_path = materialize_session_rollout(
        tmp_path,
        SessionMeta(
            id=thread_id,
            timestamp="2025-01-02T03:04:05Z",
            cwd="C:/work",
            originator="codex_exec",
            cli_version="test-version",
            source="cli",
            model_provider="openai",
        ),
    )
    assert rollout_path is not None
    with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(
            json.dumps(
                {
                    "timestamp": "2025-01-02T03:04:06Z",
                    "type": "response_item",
                    "payload": ResponseItem.message(
                        "user",
                        (ContentItem.input_text(f"echo {marker}"),),
                    ).to_mapping(),
                }
            )
            + "\n"
        )

    rel_parts = rollout_path.relative_to(tmp_path / "sessions").parts
    meta = read_session_meta_line(rollout_path)
    items = read_response_items_from_rollout(rollout_path)

    assert rel_parts[:3] == ("2025", "01", "02")
    assert rollout_path.name.startswith("rollout-")
    assert meta.meta.id == thread_id
    assert items[-1].content[0].text == f"echo {marker}"


def test_integration_git_info_unit_test():
    # Rust source: codex/codex-rs/core/tests/suite/cli_stream.rs
    # Rust test: integration_git_info_unit_test.
    git_info = GitInfo(
        commit_hash="a" * 40,
        branch="integration-test-branch",
        repository_url="https://github.com/example/integration-test.git",
    )

    encoded = SessionMetaLine(
        meta=SessionMeta(
            id="aaaaaaaa-1111-2222-3333-444444444444",
            timestamp="2025-01-02T03:04:05Z",
            cwd="C:/work",
            originator="codex_exec",
            cli_version="test-version",
        ),
        git=git_info,
    ).to_mapping()
    decoded = SessionMetaLine.from_mapping(encoded)

    assert decoded.git == git_info
    assert len(decoded.git.commit_hash) == 40
    assert all(char in "0123456789abcdef" for char in decoded.git.commit_hash)
