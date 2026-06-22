import dataclasses

import pytest

from pycodex.hooks import GeneratedHookSchemas
from pycodex.hooks import generated_hook_schemas
from pycodex.hooks import parse_json_schema


def test_loads_generated_hook_schemas():
    # Rust crate/module/test:
    # codex-hooks/src/engine/schema_loader.rs::tests::loads_generated_hook_schemas.
    schemas = generated_hook_schemas()

    assert schemas.post_tool_use_command_input["type"] == "object"
    assert schemas.post_tool_use_command_output["type"] == "object"
    assert schemas.permission_request_command_input["type"] == "object"
    assert schemas.permission_request_command_output["type"] == "object"
    assert schemas.post_compact_command_input["type"] == "object"
    assert schemas.post_compact_command_output["type"] == "object"
    assert schemas.pre_tool_use_command_input["type"] == "object"
    assert schemas.pre_tool_use_command_output["type"] == "object"
    assert schemas.pre_compact_command_input["type"] == "object"
    assert schemas.pre_compact_command_output["type"] == "object"
    assert schemas.session_start_command_input["type"] == "object"
    assert schemas.session_start_command_output["type"] == "object"
    assert schemas.subagent_start_command_input["type"] == "object"
    assert schemas.subagent_start_command_output["type"] == "object"
    assert schemas.subagent_stop_command_input["type"] == "object"
    assert schemas.subagent_stop_command_output["type"] == "object"
    assert schemas.user_prompt_submit_command_input["type"] == "object"
    assert schemas.user_prompt_submit_command_output["type"] == "object"
    assert schemas.stop_command_input["type"] == "object"
    assert schemas.stop_command_output["type"] == "object"


def test_generated_hook_schemas_exposes_rust_field_inventory_and_caches():
    # Rust source contract: GeneratedHookSchemas has a fixed field inventory
    # and generated_hook_schemas uses OnceLock to return one static value.
    assert [field.name for field in dataclasses.fields(GeneratedHookSchemas)] == [
        "post_tool_use_command_input",
        "post_tool_use_command_output",
        "permission_request_command_input",
        "permission_request_command_output",
        "post_compact_command_input",
        "post_compact_command_output",
        "pre_tool_use_command_input",
        "pre_tool_use_command_output",
        "pre_compact_command_input",
        "pre_compact_command_output",
        "session_start_command_input",
        "session_start_command_output",
        "subagent_start_command_input",
        "subagent_start_command_output",
        "subagent_stop_command_input",
        "subagent_stop_command_output",
        "user_prompt_submit_command_input",
        "user_prompt_submit_command_output",
        "stop_command_input",
        "stop_command_output",
    ]
    assert generated_hook_schemas() is generated_hook_schemas()


def test_parse_json_schema_reports_named_invalid_schema():
    # Rust source contract: parse_json_schema panics with the generated schema
    # name when embedded JSON is invalid. Python raises the equivalent error.
    with pytest.raises(ValueError, match="invalid generated hooks schema demo"):
        parse_json_schema("demo", "{")

    with pytest.raises(ValueError, match="expected object"):
        parse_json_schema("array", "[]")
