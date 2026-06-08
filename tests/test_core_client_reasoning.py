from types import SimpleNamespace

from pycodex.core import ModelClient
from pycodex.core.client import build_reasoning
from pycodex.core.client_common import Prompt
from pycodex.protocol import ReasoningEffort, ReasoningSummary


def test_build_reasoning_returns_none_when_model_does_not_support_summaries():
    # Rust source: codex/codex-rs/core/src/client.rs::build_reasoning.
    # Source contract: unsupported models produce no reasoning payload.
    model_info = SimpleNamespace(
        supports_reasoning_summaries=False,
        default_reasoning_level="medium",
    )

    assert build_reasoning(model_info, effort="high", summary="auto") is None


def test_build_reasoning_uses_explicit_effort_before_model_default():
    # Rust source: codex/codex-rs/core/src/client.rs::build_reasoning.
    # Source contract: effort.or(model_info.default_reasoning_level).
    model_info = SimpleNamespace(
        supports_reasoning_summaries=True,
        default_reasoning_level="medium",
    )

    assert build_reasoning(model_info, effort="high", summary=None) == {"effort": "high"}


def test_build_reasoning_falls_back_to_model_default_effort():
    # Rust source: codex/codex-rs/core/src/client.rs::build_reasoning.
    # Source contract: default reasoning effort is used when no explicit effort is supplied.
    model_info = SimpleNamespace(
        supports_reasoning_summaries=True,
        default_reasoning_level="medium",
    )

    assert build_reasoning(model_info, effort=None, summary=None) == {"effort": "medium"}


def test_build_reasoning_omits_none_summary_and_preserves_non_none_summary():
    # Rust source: codex/codex-rs/core/src/client.rs::build_reasoning.
    # Source contract: ReasoningSummaryConfig::None is serialized as absent summary.
    model_info = SimpleNamespace(
        supports_reasoning_summaries=True,
        default_reasoning_level=None,
    )

    assert build_reasoning(model_info, effort=None, summary=ReasoningSummary.NONE) == {}
    assert build_reasoning(model_info, effort=None, summary="auto") == {"summary": "auto"}


def test_build_reasoning_preserves_enum_effort_until_request_serialization():
    # Rust source: codex/codex-rs/core/src/client.rs::build_reasoning.
    # Source contract: Reasoning stores config enum values and request serialization later
    # lowers them to API strings.
    model_info = SimpleNamespace(
        supports_reasoning_summaries=True,
        default_reasoning_level=None,
    )

    assert build_reasoning(model_info, effort=ReasoningEffort.HIGH, summary=None) == {
        "effort": ReasoningEffort.HIGH
    }


def test_build_responses_request_includes_reasoning_encrypted_content_only_when_reasoning_exists():
    # Rust source: codex/codex-rs/core/src/client.rs::build_responses_request.
    # Source contract: include contains reasoning.encrypted_content iff reasoning is Some(...).
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    unsupported_model = SimpleNamespace(
        slug="gpt-no-reasoning",
        supports_reasoning_summaries=False,
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )
    supported_model = SimpleNamespace(
        slug="gpt-reasoning",
        supports_reasoning_summaries=True,
        default_reasoning_level=None,
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )

    unsupported_request = client.build_responses_request(
        provider, Prompt.default(), unsupported_model, effort="high", summary="auto"
    )
    supported_request = client.build_responses_request(
        provider, Prompt.default(), supported_model, effort=None, summary=None
    )

    assert unsupported_request["reasoning"] is None
    assert unsupported_request["include"] == []
    assert supported_request["reasoning"] == {}
    assert supported_request["include"] == ["reasoning.encrypted_content"]
