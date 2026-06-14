import json
import re
from datetime import timedelta

from pycodex.apply_patch import apply_patch_action_to_disk, maybe_parse_apply_patch_verified
from pycodex.core.user_shell_command import format_exec_output_for_model
from pycodex.protocol import ExecToolCallOutput, StreamOutput, TruncationPolicyConfig

FIXTURE_JSON = """{
    "description": "This is an example JSON file.",
    "foo": "bar",
    "isTest": true,
    "testNumber": 123,
    "testArray": [1, 2, 3],
    "testObject": {
        "foo": "bar"
    }
}
"""


def _model_output(text: str, *, exit_code: int = 0, millis: int = 25, budget: int = 20_000) -> str:
    return format_exec_output_for_model(
        ExecToolCallOutput(
            exit_code=exit_code,
            aggregated_output=StreamOutput.new(text),
            duration=timedelta(milliseconds=millis),
        ),
        TruncationPolicyConfig.bytes(budget),
    )


def _wrapped_success_output(text: str, *, millis: int = 25) -> str:
    return _model_output(text, exit_code=0, millis=millis)


def _apply_patch(root, patch: str):
    result = maybe_parse_apply_patch_verified(("apply_patch", patch), root)
    assert result.type == "body", result
    return result.body


def test_shell_output_preserves_fixture_json_as_freeform():
    # Rust: core/tests/suite/shell_serialization.rs
    # test `shell_output_preserves_fixture_json_as_freeform`.
    output = _model_output(FIXTURE_JSON)

    assert json.loads(FIXTURE_JSON)["foo"] == "bar"
    try:
        json.loads(output)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("expected shell output to be plain text, not JSON")

    header, body = output.split("Output:\n", 1)
    assert re.match(r"(?s)^Exit code: 0\nWall time: [0-9]+(?:\.[0-9]+)? seconds\n$", header)
    assert body == FIXTURE_JSON


def test_shell_output_records_duration():
    # Rust: core/tests/suite/shell_serialization.rs
    # test `shell_output_records_duration`.
    output = _model_output("", millis=200)

    assert re.match(r"(?s)^Exit code: 0\nWall time: [0-9]+(?:\.[0-9]+)? seconds\nOutput:\n$", output)
    match = re.search(r"(?m)^Wall time: ([0-9]+(?:\.[0-9]+)?) seconds$", output)
    assert match is not None
    assert float(match.group(1)) > 0.1


def test_apply_patch_custom_tool_call_creates_file(tmp_path):
    # Rust: core/tests/suite/shell_serialization.rs
    # test `apply_patch_custom_tool_call_creates_file`.
    file_name = "custom_tool_apply_patch.txt"
    patch = f"*** Begin Patch\n*** Add File: {file_name}\n+custom tool content\n*** End Patch\n"

    summary = apply_patch_action_to_disk(_apply_patch(tmp_path, patch))
    output = _wrapped_success_output(summary)

    assert re.match(
        rf"(?s)^Exit code: 0\nWall time: [0-9]+(?:\.[0-9]+)? seconds\nOutput:\n"
        rf"Success\. Updated the following files:\nA .*(?:\\|/)?{re.escape(file_name)}\n?$",
        output,
    )
    assert (tmp_path / file_name).read_text() == "custom tool content\n"


def test_apply_patch_custom_tool_call_updates_existing_file(tmp_path):
    # Rust: core/tests/suite/shell_serialization.rs
    # test `apply_patch_custom_tool_call_updates_existing_file`.
    file_name = "custom_tool_apply_patch_existing.txt"
    (tmp_path / file_name).write_text("before\n")
    patch = f"*** Begin Patch\n*** Update File: {file_name}\n@@\n-before\n+after\n*** End Patch\n"

    summary = apply_patch_action_to_disk(_apply_patch(tmp_path, patch))
    output = _wrapped_success_output(summary)

    assert re.match(
        rf"(?s)^Exit code: 0\nWall time: [0-9]+(?:\.[0-9]+)? seconds\nOutput:\n"
        rf"Success\. Updated the following files:\nM .*(?:\\|/)?{re.escape(file_name)}\n?$",
        output,
    )
    assert (tmp_path / file_name).read_text() == "after\n"


def test_apply_patch_custom_tool_call_reports_failure_output(tmp_path):
    # Rust: core/tests/suite/shell_serialization.rs
    # test `apply_patch_custom_tool_call_reports_failure_output`.
    missing_file = "missing_custom_tool_apply_patch.txt"
    patch = f"*** Begin Patch\n*** Update File: {missing_file}\n@@\n-before\n+after\n*** End Patch\n"

    result = maybe_parse_apply_patch_verified(("apply_patch", patch), tmp_path)

    assert result.type == "correctness_error"
    assert str(result.error).startswith("Failed to read file to update")
    assert missing_file in str(result.error)


def test_shell_output_is_freeform_for_nonzero_exit():
    # Rust: core/tests/suite/shell_serialization.rs
    # test `shell_output_is_freeform_for_nonzero_exit`.
    output = _model_output("", exit_code=42)

    assert re.match(r"(?s)^Exit code: 42\nWall time: [0-9]+(?:\.[0-9]+)? seconds\nOutput:\n?$", output)


def test_shell_command_output_is_freeform():
    # Rust: core/tests/suite/shell_serialization.rs
    # test `shell_command_output_is_freeform`.
    output = _model_output("shell command")

    assert re.match(
        r"(?s)^Exit code: 0\nWall time: [0-9]+(?:\.[0-9]+)? seconds\nOutput:\nshell command\n?$",
        output,
    )


def test_shell_command_output_is_not_truncated_under_10k_bytes():
    # Rust: core/tests/suite/shell_serialization.rs
    # test `shell_command_output_is_not_truncated_under_10k_bytes`.
    payload = "1" * 10_000
    output = _model_output(payload, budget=20_000)

    assert output.endswith("Output:\n" + payload)
    assert "truncated" not in output


def test_shell_command_output_is_not_truncated_over_10k_bytes():
    # Rust: core/tests/suite/shell_serialization.rs
    # test `shell_command_output_is_not_truncated_over_10k_bytes`.
    output = _model_output("1" * 10_001, budget=10_000)

    assert output.startswith("Exit code: 0\nWall time:")
    assert "\nOutput:\n" in output
    assert "truncated" in output
