from pathlib import Path

import pytest

from pycodex.core.guardian import (
    GuardianAssessment,
    GuardianApprovalRequest,
    format_guardian_action_pretty,
    guardian_output_contract_prompt,
    guardian_output_schema,
    guardian_policy_prompt_with_config,
    guardian_truncate_text,
    parse_guardian_assessment,
    split_guardian_truncation_bounds,
)
from pycodex.protocol import (
    GuardianAssessmentOutcome,
    GuardianRiskLevel,
    GuardianUserAuthorization,
)


def test_guardian_truncate_text_keeps_prefix_suffix_and_xml_marker():
    # Rust test: guardian_truncate_text_keeps_prefix_suffix_and_xml_marker.
    content = ("prefix " * 200) + (" suffix" * 200)

    truncated, was_truncated = guardian_truncate_text(content, 20)

    assert truncated.startswith("prefix")
    assert '<truncated omitted_approx_tokens="' in truncated
    assert truncated.endswith("suffix")
    assert was_truncated is True


def test_guardian_truncate_text_handles_empty_short_and_marker_only_cases():
    assert guardian_truncate_text("", 20) == ("", False)
    assert guardian_truncate_text("hello", 20) == ("hello", False)

    marker_only, was_truncated = guardian_truncate_text("abcdef", 0)

    assert marker_only == '<truncated omitted_approx_tokens="2" />'
    assert was_truncated is True


def test_split_guardian_truncation_bounds_respects_utf8_boundaries():
    # Rust source: split_guardian_truncation_bounds iterates char_indices.
    prefix, suffix = split_guardian_truncation_bounds("αβγδε", 4, 4)

    assert prefix == "αβ"
    assert suffix == "δε"


def test_parse_guardian_assessment_extracts_embedded_json():
    # Rust test: parse_guardian_assessment_extracts_embedded_json.
    parsed = parse_guardian_assessment(
        'preface {"risk_level":"medium","user_authorization":"low","outcome":"allow","rationale":"ok"}'
    )

    assert parsed == GuardianAssessment(
        risk_level=GuardianRiskLevel.MEDIUM,
        user_authorization=GuardianUserAuthorization.LOW,
        outcome=GuardianAssessmentOutcome.ALLOW,
        rationale="ok",
    )


def test_parse_guardian_assessment_defaults_bare_allow_and_deny():
    # Rust tests: bare allow defaults low risk; bare deny defaults high risk.
    allow = parse_guardian_assessment('{"outcome":"allow"}')
    deny = parse_guardian_assessment('{"outcome":"deny"}')

    assert allow == GuardianAssessment(
        GuardianRiskLevel.LOW,
        GuardianUserAuthorization.UNKNOWN,
        GuardianAssessmentOutcome.ALLOW,
        "Auto-review returned a low-risk allow decision.",
    )
    assert deny == GuardianAssessment(
        GuardianRiskLevel.HIGH,
        GuardianUserAuthorization.UNKNOWN,
        GuardianAssessmentOutcome.DENY,
        "Auto-review returned a deny decision without a rationale.",
    )


def test_parse_guardian_assessment_rejects_missing_or_non_json_payloads():
    with pytest.raises(ValueError, match="without an assessment payload"):
        parse_guardian_assessment(None)
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_guardian_assessment("not json")
    with pytest.raises(ValueError, match="outcome"):
        parse_guardian_assessment("{}")


def test_guardian_output_schema_requires_only_outcome():
    # Rust test: guardian_output_schema_requires_only_outcome_and_allows_optional_details.
    assert guardian_output_schema() == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "user_authorization": {
                "type": "string",
                "enum": ["unknown", "low", "medium", "high"],
            },
            "outcome": {
                "type": "string",
                "enum": ["allow", "deny"],
            },
            "rationale": {
                "type": "string",
            },
        },
        "required": ["outcome"],
    }


def test_guardian_policy_prompt_with_config_injects_tenant_config_and_contract():
    # Rust source: guardian_policy_prompt_with_config.
    prompt = guardian_policy_prompt_with_config("  ## Tenant\n- deny foo  ")

    assert "{tenant_policy_config}" not in prompt
    assert "## Tenant\n- deny foo" in prompt
    assert prompt.endswith(guardian_output_contract_prompt() + "\n")
    assert "You are judging one planned coding-agent action." in prompt


def test_format_guardian_action_pretty_uses_prompt_truncation_helper():
    # Rust test: format_guardian_action_pretty_truncates_large_string_fields.
    patch = "line\n" * 100_000
    rendered = format_guardian_action_pretty(
        GuardianApprovalRequest.apply_patch(
            id="patch-1",
            cwd=Path("/tmp"),
            files=(),
            patch=patch,
        )
    )

    assert '"tool": "apply_patch"' in rendered.text
    assert "<truncated omitted_approx_tokens=" in rendered.text
    assert len(rendered.text) < len(patch)
    assert rendered.truncated is True
