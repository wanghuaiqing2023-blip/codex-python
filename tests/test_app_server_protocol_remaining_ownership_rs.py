"""Ownership tests for remaining codex-app-server-protocol modules."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from pycodex.app_server_protocol.command_exec import CommandExecParams
from pycodex.app_server_protocol.permissions import SandboxPolicy as V2SandboxPolicy
from pycodex.app_server_protocol.v1 import ExecOneOffCommandParams
from pycodex.protocol.protocol import SandboxPolicy as V1SandboxPolicy


def test_remaining_rust_modules_have_python_owners() -> None:
    expected = (
        "pycodex.app_server_protocol.bin.export",
        "pycodex.app_server_protocol.bin.write_schema_fixtures",
        "pycodex.app_server_protocol.protocol",
        "pycodex.app_server_protocol.mappers",
        "pycodex.app_server_protocol.serde_helpers",
        "pycodex.app_server_protocol.v2",
    )
    for module_name in expected:
        assert importlib.import_module(module_name).__name__ == module_name


def test_mcp_elicitation_has_only_the_rust_v2_mcp_owner() -> None:
    mcp = importlib.import_module("pycodex.app_server_protocol.mcp")
    assert mcp.McpElicitationSchema.__module__ == mcp.__name__
    assert mcp.McpServerElicitationRequest.__module__ == mcp.__name__
    assert not Path("pycodex/app_server_protocol/elicitation.py").exists()


def test_mappers_rs_converts_v1_exec_params_to_v2() -> None:
    mappers = importlib.import_module("pycodex.app_server_protocol.mappers")
    source = ExecOneOffCommandParams(
        command=("pwsh", "-NoProfile"),
        timeout_ms=2**63,
        cwd=Path("workspace"),
        sandbox_policy=V1SandboxPolicy.read_only(network_access=True),
    )

    result = mappers.command_exec_params_from_v1(source)

    assert result == CommandExecParams(
        command=("pwsh", "-NoProfile"),
        timeout_ms=60_000,
        cwd=Path("workspace"),
        sandbox_policy=V2SandboxPolicy.read_only(network_access=True),
    )


def test_serde_helpers_rs_preserves_missing_null_and_value() -> None:
    helpers = importlib.import_module("pycodex.app_server_protocol.serde_helpers")

    assert helpers.deserialize_empty_path_as_none("") is None
    assert helpers.deserialize_empty_path_as_none(None) is None
    assert helpers.deserialize_empty_path_as_none("workspace") == Path("workspace")
    assert helpers.deserialize_double_option({}, "value") is helpers.MISSING
    assert helpers.deserialize_double_option({"value": None}, "value") is None
    assert helpers.deserialize_double_option({"value": "7"}, "value", int) == 7
    assert helpers.serialize_double_option(helpers.MISSING) is helpers.MISSING
    assert helpers.serialize_double_option(None) is None
    assert helpers.serialize_double_option(7, str) == "7"


def test_export_bin_rs_parses_and_forwards_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    export_bin = importlib.import_module("pycodex.app_server_protocol.bin.export")
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        export_bin,
        "generate_ts_with_options",
        lambda out, prettier, options: calls.append(("ts", out, prettier, options.experimental_api)),
    )
    monkeypatch.setattr(
        export_bin,
        "generate_json_with_experimental",
        lambda out, experimental: calls.append(("json", out, experimental)),
    )

    assert export_bin.main(["--out", str(tmp_path), "--prettier", "prettier", "--experimental"]) == 0
    assert calls == [
        ("ts", tmp_path, Path("prettier"), True),
        ("json", tmp_path, True),
    ]


def test_write_schema_fixtures_bin_rs_parses_and_forwards_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture_bin = importlib.import_module("pycodex.app_server_protocol.bin.write_schema_fixtures")
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        fixture_bin,
        "write_schema_fixtures_with_options",
        lambda root, prettier, options: calls.append(
            (root, prettier, options.experimental_api)
        ),
    )

    assert fixture_bin.main(
        ["--schema-root", str(tmp_path), "--prettier", "prettier", "--experimental"]
    ) == 0
    assert calls == [(tmp_path, Path("prettier"), True)]
