import json
from pathlib import Path
import asyncio
import os
import re
import socket
import sqlite3
import tempfile
import threading
import unittest
import types
from pycodex.core import RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE
from pycodex.codex_api.endpoint.responses_websocket import (
    ResponsesWebsocketCloseMessage,
    ResponsesWebsocketMemoryStream,
)
from pycodex.codex_api.error import ApiError
from pycodex.codex_client import TransportError
from pycodex.protocol.config_types import AskForApproval, SandboxMode

import pycodex.cli.doctor_updates as doctor_updates
from pycodex.exec.websocket import WebSocketFrame
from pycodex.cli import (
    GITHUB_LATEST_RELEASE_URL,
    HOMEBREW_CASK_API_URL,
    NpmRootCheck,
    StateCheckInputs,
    SystemCheckInputs,
    TerminalCheckInputs,
    TerminalTitleCheckInputs,
    UpdateAction,
    VersionInfo,
    WebsocketCheckInputs,
    build_doctor_update_check,
    cached_version_details,
    codex_path_entries,
    compare_npm_package_roots,
    detect_update_action,
    describe_install_context,
    doctor_background_server_check,
    doctor_auth_check,
    doctor_config_check,
    default_reachability_plan,
    doctor_fallback_state_check,
    doctor_git_check,
    doctor_installation_check,
    doctor_managed_by_npm,
    doctor_mcp_check,
    doctor_network_check,
    doctor_provider_reachability_check,
    doctor_runtime_check,
    doctor_sandbox_check,
    doctor_search_check,
    doctor_state_check,
    doctor_system_check,
    doctor_terminal_check,
    doctor_terminal_title_check,
    doctor_thread_inventory_check,
    doctor_updates_check,
    doctor_updates_check_from_config,
    doctor_websocket_check,
    fetch_homebrew_cask_version,
    fetch_latest_github_release_version,
    fetch_latest_version,
    GitCheckInputs,
    http_get_json,
    inherited_managed_env_for_cargo_binary,
    latest_version_probe_error_details,
    latest_version_details,
    npm_global_root_check,
    provider_auth_reachability_mode_from_auth,
    provider_reachability_plan_from_config,
    provider_reachability_plan_from_parts,
    push_cached_version_details,
    push_latest_version_probe_error_details,
    push_latest_version_details,
    redact_doctor_detail,
    redacted_doctor_check_mapping,
    redacted_doctor_checks_mapping,
    redacted_doctor_report_mapping,
    run_command,
    parse_args,
    update_action_label,
)


class DoctorUpdateDetailsTests(unittest.TestCase):
    def test_doctor_overall_status_prefers_fail(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: overall_status_prefers_fail
        # Contract: overall doctor status chooses fail before warning.
        status = doctor_updates._doctor_overall_status(
            [
                {"id": "a", "category": "config", "status": "warning", "summary": "warning"},
                {"id": "b", "category": "auth", "status": "fail", "summary": "fail"},
            ]
        )

        self.assertEqual(status, "fail")

    def test_doctor_json_status_matches_rust_check_status_wire_values(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: CheckStatus / redacted_json_check
        # Contract: doctor JSON statuses use Rust snake_case wire values; local warn aliases normalize to warning.
        self.assertEqual(doctor_updates._doctor_json_status("ok"), "ok")
        self.assertEqual(doctor_updates._doctor_json_status("warning"), "warning")
        self.assertEqual(doctor_updates._doctor_json_status("fail"), "fail")
        self.assertEqual(doctor_updates._doctor_json_status("warn"), "warning")
        self.assertEqual(doctor_updates._doctor_json_status("unexpected"), "warning")

    def test_doctor_update_check_mapping_matches_rust_optional_fields(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: DoctorCheck::new / DoctorCheck::remediation / DoctorCheck::issue
        # Contract: doctor checks omit absent remediation/issues and include present optional fields.
        minimal = doctor_updates.DoctorUpdateCheck(
            status="ok",
            summary="config loaded",
            details=("config.toml: missing",),
        ).to_mapping()

        self.assertEqual(
            minimal,
            {
                "status": "ok",
                "summary": "config loaded",
                "details": ["config.toml: missing"],
            },
        )

        issue = {
            "severity": "warning",
            "cause": "narrow terminal",
            "fields": ["terminal size"],
        }
        full = doctor_updates.DoctorUpdateCheck(
            status="warn",
            summary="terminal may be hard to use",
            details=("terminal size: 80 columns x 24 rows",),
            remediation="increase terminal width",
            issues=(issue,),
        ).to_mapping()

        self.assertEqual(full["remediation"], "increase terminal width")
        self.assertEqual(full["issues"], [issue])
        self.assertIsNot(full["issues"][0], issue)

    def test_doctor_run_sync_check_notifies_progress(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: run_sync_check_notifies_progress
        # Contract: sync doctor check orchestration emits begin and finish events around the check.
        events: list[str] = []

        class Progress:
            def begin(self, label: str) -> None:
                events.append(f"begin {label}")

            def finish(self, label: str, status: str) -> None:
                events.append(f"finish {label} {status}")

        check = doctor_updates._doctor_run_sync_check(
            "test",
            Progress(),
            lambda: {"id": "test", "category": "test", "status": "ok", "summary": "ok"},
        )

        self.assertEqual(check["status"], "ok")
        self.assertEqual(events, ["begin test", "finish test Ok"])

    def test_doctor_run_async_check_notifies_progress(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: run_async_check_notifies_progress
        # Contract: async doctor check orchestration emits begin and finish events around the awaited check.
        events: list[str] = []

        class Progress:
            def begin(self, label: str) -> None:
                events.append(f"begin {label}")

            def finish(self, label: str, status: str) -> None:
                events.append(f"finish {label} {status}")

        async def check_coro() -> dict[str, str]:
            return {"id": "test", "category": "test", "status": "warning", "summary": "warning"}

        check = asyncio.run(doctor_updates._doctor_run_async_check("test", Progress(), check_coro()))

        self.assertEqual(check["status"], "warning")
        self.assertEqual(events, ["begin test", "finish test Warning"])

    def test_doctor_progress_visibility_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/progress.rs should_show_progress.
        self.assertFalse(
            doctor_updates._should_show_doctor_progress(
                json_output=True,
                term="xterm-256color",
                stderr_is_tty=True,
            )
        )
        self.assertFalse(
            doctor_updates._should_show_doctor_progress(
                json_output=False,
                term="xterm-256color",
                stderr_is_tty=False,
            )
        )
        self.assertFalse(
            doctor_updates._should_show_doctor_progress(
                json_output=False,
                term="dumb",
                stderr_is_tty=True,
            )
        )
        self.assertTrue(
            doctor_updates._should_show_doctor_progress(
                json_output=False,
                term="xterm-256color",
                stderr_is_tty=True,
            )
        )

    def test_doctor_output_ascii_status_markers_match_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/output.rs status_marker with ascii output.
        self.assertEqual(doctor_updates._doctor_output_ascii_status_marker("ok"), "[ok]")
        self.assertEqual(doctor_updates._doctor_output_ascii_status_marker("update"), "[up]")
        self.assertEqual(doctor_updates._doctor_output_ascii_status_marker("note"), "[!!]")
        self.assertEqual(doctor_updates._doctor_output_ascii_status_marker("warning"), "[!!]")
        self.assertEqual(doctor_updates._doctor_output_ascii_status_marker("fail"), "[XX]")
        self.assertEqual(doctor_updates._doctor_output_ascii_status_marker("idle"), "[--]")
        with self.assertRaisesRegex(ValueError, "Unknown doctor output status"):
            doctor_updates._doctor_output_ascii_status_marker("pending")

    def test_doctor_output_ascii_separator_matches_rust_width(self) -> None:
        # Rust parity: codex-cli/src/doctor/output.rs SEPARATOR_WIDTH.
        separator = doctor_updates._doctor_output_ascii_separator()
        self.assertEqual(separator, "-" * 61)
        self.assertEqual(len(separator), 61)

    def test_doctor_output_column_widths_match_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/output.rs NAME_WIDTH and DETAIL_LABEL_WIDTH.
        self.assertEqual(
            doctor_updates._doctor_output_column_widths(),
            {"name": 12, "detail_label": 24},
        )

    def test_doctor_output_detail_number_formatters_match_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/output/detail.rs format_bytes/format_count.
        self.assertEqual(doctor_updates._doctor_detail_format_bytes(999), "999 B")
        self.assertEqual(doctor_updates._doctor_detail_format_bytes(1024), "1.00 KB")
        self.assertEqual(doctor_updates._doctor_detail_format_bytes(1024 * 1024), "1.00 MB")
        self.assertEqual(doctor_updates._doctor_detail_format_bytes(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(doctor_updates._doctor_detail_format_count(1234567), "1,234,567")

    def test_doctor_output_detail_rollout_summary_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/output/detail.rs rollout_summary.
        self.assertEqual(
            doctor_updates._doctor_detail_rollout_summary(
                "1515 files, 2702146365 total bytes, 1783594 average bytes"
            ),
            "1,515 files \u00b7 2.52 GB (avg 1.70 MB)",
        )
        self.assertIsNone(doctor_updates._doctor_detail_rollout_summary("not rollout stats"))

    def test_redact_doctor_detail_hides_secret_values_and_url_credentials(self) -> None:
        self.assertEqual(redact_doctor_detail("OPENAI_API_KEY: sk-live-secret"), "OPENAI_API_KEY: <redacted>")
        self.assertEqual(
            redact_doctor_detail(
                "optional reachability failed: remote: https://user:pass@example.com/mcp/path?x=abc (connect failed)"
            ),
            "optional reachability failed: remote: https://example.com/mcp/<redacted> (connect failed)",
        )

    def test_redacted_doctor_check_mapping_structures_repeated_details_and_notes(self) -> None:
        redacted = redacted_doctor_check_mapping(
            {
                "status": "warn",
                "summary": "MCP configuration has optional issues",
                "details": [
                    "zeta: last",
                    "OPENAI_API_KEY: sk-live-secret",
                    "duplicate: one",
                    "duplicate: two",
                    "alpha: first",
                    "freeform note",
                ],
                "issues": [
                    {
                        "severity": "warn",
                        "cause": "remote https://user:pass@example.com/mcp?x=abc is unreachable",
                        "measured": "https://user:pass@example.com/mcp?x=abc",
                        "expected": "reachable",
                        "remedy": "Check https://user:pass@example.com/help?x=abc.",
                        "fields": ["Authorization: bearer-token"],
                    }
                ],
                "remediation": "Open https://user:pass@example.com/help?x=abc.",
            }
        )

        self.assertEqual(redacted["details"]["OPENAI_API_KEY"], "<redacted>")
        self.assertEqual(
            list(redacted.keys()),
            ["id", "category", "status", "summary", "details", "issues", "notes", "remediation", "durationMs"],
        )
        self.assertEqual(list(redacted["details"].keys()), ["OPENAI_API_KEY", "alpha", "duplicate", "zeta"])
        self.assertEqual(redacted["id"], "unknown")
        self.assertEqual(redacted["category"], "unknown")
        self.assertEqual(redacted["durationMs"], 0)
        self.assertEqual(redacted["details"]["alpha"], "first")
        self.assertEqual(redacted["details"]["zeta"], "last")
        self.assertEqual(redacted["details"]["duplicate"], ["one", "two"])
        self.assertEqual(redacted["notes"], ["freeform note"])
        self.assertEqual(redacted["issues"][0]["severity"], "warning")
        self.assertEqual(redacted["issues"][0]["cause"], "remote https://example.com/mcp is unreachable")
        self.assertEqual(redacted["issues"][0]["measured"], "https://example.com/mcp")
        self.assertEqual(redacted["issues"][0]["expected"], "reachable")
        self.assertEqual(redacted["issues"][0]["remedy"], "Check https://example.com/help.")
        self.assertEqual(redacted["issues"][0]["fields"], ["Authorization: <redacted>"])
        self.assertEqual(redacted["remediation"], "Open https://example.com/help.")

    def test_redacted_doctor_check_mapping_preserves_explicit_identity_and_duration(self) -> None:
        redacted = redacted_doctor_check_mapping(
            {
                "id": "custom.id",
                "category": "custom",
                "status": "ok",
                "summary": "fine",
                "details": [],
                "duration_ms": "12",
                "raw_secret_extra": "sk-live-secret",
            },
            check_key="auth",
        )

        self.assertEqual(redacted["id"], "custom.id")
        self.assertEqual(redacted["category"], "custom")
        self.assertEqual(redacted["durationMs"], 12)
        self.assertIsNone(redacted["remediation"])
        self.assertNotIn("issues", redacted)
        self.assertNotIn("notes", redacted)
        self.assertNotIn("raw_secret_extra", redacted)

    def test_redacted_doctor_check_mapping_clamps_invalid_duration(self) -> None:
        redacted = redacted_doctor_check_mapping(
            {
                "status": "ok",
                "summary": "fine",
                "details": [],
                "durationMs": -1,
            }
        )

        self.assertEqual(redacted["durationMs"], 0)

    def test_redacted_doctor_check_mapping_saturates_huge_duration(self) -> None:
        redacted = redacted_doctor_check_mapping(
            {
                "status": "ok",
                "summary": "fine",
                "details": [],
                "durationMs": str(1 << 80),
            }
        )

        self.assertEqual(redacted["durationMs"], (1 << 64) - 1)

    def test_redacted_doctor_check_mapping_normalizes_unknown_status_to_warning(self) -> None:
        redacted = redacted_doctor_check_mapping(
            {
                "status": " FAIL ",
                "summary": "fine",
                "details": [],
                "issues": [{"severity": "unexpected", "cause": "odd"}],
            }
        )

        self.assertEqual(redacted["status"], "fail")
        self.assertEqual(redacted["issues"][0]["severity"], "warning")

    def test_redacted_doctor_issue_mapping_keeps_null_options_and_empty_fields(self) -> None:
        redacted = redacted_doctor_check_mapping(
            {
                "status": "warn",
                "summary": "issue has optional fields",
                "details": [],
                "issues": [{"severity": "fail", "cause": "something failed"}],
            }
        )

        issue = redacted["issues"][0]
        self.assertEqual(issue["severity"], "fail")
        self.assertEqual(issue["cause"], "something failed")
        self.assertIsNone(issue["measured"])
        self.assertIsNone(issue["expected"])
        self.assertIsNone(issue["remedy"])
        self.assertEqual(issue["fields"], [])

    def test_redacted_doctor_check_mapping_stringifies_string_fields(self) -> None:
        redacted = redacted_doctor_check_mapping(
            {
                "id": 123,
                "category": None,
                "status": "ok",
                "summary": 456,
                "details": [],
            },
            check_key="auth",
        )

        self.assertEqual(redacted["id"], "123")
        self.assertEqual(redacted["category"], "auth")
        self.assertEqual(redacted["summary"], "456")

    def test_redacted_doctor_checks_mapping_redacts_each_check(self) -> None:
        redacted = redacted_doctor_checks_mapping(
            {
                "auth": {
                    "status": "warn",
                    "summary": "token present",
                    "details": ["CODEX_ACCESS_TOKEN: secret-token"],
                },
                "background_server": {
                    "status": "ok",
                    "summary": "background server is not running",
                    "details": ["status: not running"],
                },
                "network": {
                    "status": "ok",
                    "summary": "reachable",
                    "details": ["endpoint: https://user:pass@example.com/api/v1?token=secret"],
                },
                "runtime": {
                    "status": "ok",
                    "summary": "running local build",
                    "details": [],
                },
                "search": {
                    "status": "ok",
                    "summary": "search is OK",
                    "details": [],
                },
                "system": {
                    "status": "ok",
                    "summary": "OS language en-US",
                    "details": [],
                },
            }
        )

        self.assertEqual(
            list(redacted.keys()),
            [
                "app_server.status",
                "auth.credentials",
                "network.env",
                "runtime.provenance",
                "runtime.search",
                "system.environment",
            ],
        )
        self.assertEqual(redacted["app_server.status"]["id"], "app_server.status")
        self.assertEqual(redacted["app_server.status"]["category"], "app-server")
        self.assertEqual(redacted["auth.credentials"]["details"]["CODEX_ACCESS_TOKEN"], "<redacted>")
        self.assertEqual(redacted["auth.credentials"]["id"], "auth.credentials")
        self.assertEqual(redacted["auth.credentials"]["category"], "auth")
        self.assertEqual(redacted["auth.credentials"]["status"], "warning")
        self.assertIsNone(redacted["auth.credentials"]["remediation"])
        self.assertEqual(redacted["network.env"]["details"]["endpoint"], "https://example.com/api/<redacted>")
        self.assertEqual(redacted["network.env"]["id"], "network.env")
        self.assertEqual(redacted["network.env"]["category"], "network")
        self.assertEqual(redacted["runtime.provenance"]["category"], "runtime")
        self.assertEqual(redacted["runtime.search"]["category"], "search")
        self.assertEqual(redacted["system.environment"]["category"], "system")

    def test_redacted_doctor_report_mapping_uses_rust_shaped_top_level_fields(self) -> None:
        report = redacted_doctor_report_mapping(
            checks={
                "auth": {
                    "status": "warn",
                    "summary": "token present",
                    "details": ["CODEX_ACCESS_TOKEN: secret-token"],
                }
            },
            overall_status="warn",
            codex_version="0.0.0",
            generated_at="0s since unix epoch",
        )

        self.assertEqual(
            list(report.keys()),
            ["schemaVersion", "generatedAt", "overallStatus", "codexVersion", "checks"],
        )
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["generatedAt"], "0s since unix epoch")
        self.assertEqual(report["overallStatus"], "warning")
        self.assertEqual(report["codexVersion"], "0.0.0")
        self.assertNotIn("summary", report)
        self.assertEqual(report["checks"]["auth.credentials"]["id"], "auth.credentials")
        self.assertEqual(report["checks"]["auth.credentials"]["category"], "auth")
        self.assertEqual(report["checks"]["auth.credentials"]["status"], "warning")
        self.assertEqual(report["checks"]["auth.credentials"]["durationMs"], 0)
        self.assertEqual(report["checks"]["auth.credentials"]["details"]["CODEX_ACCESS_TOKEN"], "<redacted>")

    def test_redacted_doctor_report_mapping_stringifies_top_level_strings(self) -> None:
        report = redacted_doctor_report_mapping(
            checks={},
            overall_status="unexpected",
            codex_version=123,
            generated_at=456,
        )

        self.assertEqual(report["generatedAt"], "456")
        self.assertEqual(report["overallStatus"], "warning")
        self.assertEqual(report["codexVersion"], "123")

    def test_redacted_doctor_report_mapping_defaults_generated_at_like_rust(self) -> None:
        report = redacted_doctor_report_mapping(
            checks={},
            overall_status="ok",
            codex_version="0.0.0",
        )

        self.assertRegex(report["generatedAt"], r"^\d+s since unix epoch$")

    def test_doctor_generated_at_matches_rust_epoch_format_and_unknown_fallback(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: generated_at
        # Contract: generated_at returns integer Unix-epoch seconds or unknown on clock failure.
        original_time = doctor_updates.time.time
        try:
            doctor_updates.time.time = lambda: 42.9
            self.assertEqual(doctor_updates._doctor_generated_at(), "42s since unix epoch")

            def failing_time() -> float:
                raise OSError("clock failed")

            doctor_updates.time.time = failing_time
            self.assertEqual(doctor_updates._doctor_generated_at(), "unknown")
        finally:
            doctor_updates.time.time = original_time

    def test_redacted_json_report_structures_and_sanitizes_details(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: redacted_json_report_structures_and_sanitizes_details
        # Contract: redacted JSON report sanitizes secrets/URLs while preserving structured details.
        report = redacted_doctor_report_mapping(
            checks={
                "mcp.config": {
                    "id": "mcp.config",
                    "category": "mcp",
                    "status": "warning",
                    "summary": "MCP configuration has optional issues",
                    "details": [
                        "optional reachability failed: remote: https://user:pass@example.com/mcp?x=abc (connect failed)",
                        "OPENAI_API_KEY: sk-live-secret",
                        "duplicate: one",
                        "duplicate: two",
                        "freeform note",
                    ],
                    "issues": [
                        {
                            "severity": "warning",
                            "cause": "remote https://user:pass@example.com/mcp?x=abc is unreachable",
                            "measured": "https://user:pass@example.com/mcp?x=abc",
                            "expected": "reachable MCP endpoint",
                            "remedy": "Check https://user:pass@example.com/help?x=abc.",
                            "fields": ["optional reachability failed"],
                        }
                    ],
                    "remediation": "Open https://user:pass@example.com/help?x=abc.",
                }
            },
            overall_status="warning",
            codex_version="0.0.0",
            generated_at="0s since unix epoch",
        )
        redacted = json.dumps(report, sort_keys=True)
        check = report["checks"]["mcp.config"]

        self.assertNotIn("user:pass", redacted)
        self.assertNotIn("x=abc", redacted)
        self.assertNotIn("sk-live-secret", redacted)
        self.assertIn("https://example.com/mcp", redacted)
        self.assertIsInstance(report["checks"], dict)
        self.assertEqual(check["id"], "mcp.config")
        self.assertEqual(check["details"]["OPENAI_API_KEY"], "<redacted>")
        self.assertEqual(check["details"]["duplicate"], ["one", "two"])
        self.assertEqual(check["notes"], ["freeform note"])
        self.assertEqual(check["issues"][0]["measured"], "https://example.com/mcp")
        self.assertEqual(check["issues"][0]["remedy"], "Check https://example.com/help.")

    def test_doctor_background_server_check_reports_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_background_server_check(codex_home=codex_home)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "background server is not running")
        self.assertIn(f"daemon state dir: {codex_home / 'app-server-daemon'}", check.details)
        self.assertIn("status: not running", check.details)
        self.assertIn("mode: ephemeral", check.details)
        self.assertFalse(any(detail.startswith("app-server version:") for detail in check.details))

    def test_doctor_background_server_check_reports_running_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            state_dir = codex_home / "app-server-daemon"
            state_dir.mkdir()
            (state_dir / "settings.json").write_text("{}", encoding="utf-8")
            socket_path = codex_home / "app-server-control" / "app-server-control.sock"
            socket_path.parent.mkdir()
            socket_path.write_text("", encoding="utf-8")

            check = doctor_background_server_check(
                codex_home=codex_home,
                version_probe=lambda _path: "1.2.3",
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "background server is running")
        self.assertIn("status: running", check.details)
        self.assertIn("app-server version: 1.2.3", check.details)
        self.assertIn("mode: persistent", check.details)

    def test_doctor_background_server_check_uses_default_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            state_dir = codex_home / "app-server-daemon"
            state_dir.mkdir()
            (state_dir / "settings.json").write_text("{}", encoding="utf-8")
            socket_path = codex_home / "app-server-control" / "app-server-control.sock"
            socket_path.parent.mkdir()
            socket_path.write_text("", encoding="utf-8")

            class FakeWebSocket:
                def __init__(self) -> None:
                    self.sent_text: list[str] = []
                    self.closed = False

                def send_text(self, text: str) -> None:
                    self.sent_text.append(text)

                def recv_text(self, expect_masked: bool | None = False) -> str:
                    return json.dumps(
                        {
                            "id": 1,
                            "result": {"userAgent": "codex_app_server_daemon/1.2.3 (Linux)"},
                        }
                    )

                def close(self) -> None:
                    self.closed = True

            fake_websocket = FakeWebSocket()
            original_connect = doctor_updates.StdlibWebSocket.connect_unix_socket

            def fake_connect_unix_socket(
                path: Path,
                websocket_url: str = "",
                timeout: float = 10.0,
            ) -> object:
                self.assertEqual(path, socket_path)
                self.assertTrue(websocket_url.startswith("ws://localhost"))
                self.assertEqual(timeout, 10.0)
                return fake_websocket

            doctor_updates.StdlibWebSocket.connect_unix_socket = fake_connect_unix_socket  # type: ignore[method-assign]

            try:
                check = doctor_background_server_check(codex_home=codex_home)
            finally:
                doctor_updates.StdlibWebSocket.connect_unix_socket = original_connect

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "background server is running")
        self.assertIn("status: running", check.details)
        self.assertIn("app-server version: 1.2.3", check.details)
        self.assertIn("mode: persistent", check.details)
        self.assertEqual(len(fake_websocket.sent_text), 1)
        request = json.loads(fake_websocket.sent_text[0])
        self.assertEqual(request["id"], 1)
        self.assertEqual(request["method"], "initialize")
        self.assertEqual(request["params"]["clientInfo"]["name"], "codex")

    def test_doctor_background_server_check_warns_for_stale_socket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            socket_path = codex_home / "app-server-control" / "app-server-control.sock"
            socket_path.parent.mkdir()
            socket_path.write_text("", encoding="utf-8")

            def probe(path: Path) -> str:
                raise RuntimeError(f"failed to connect to {path}")

            check = doctor_background_server_check(codex_home=codex_home, version_probe=probe)

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "background server socket is stale or unreachable")
        self.assertIn("status: stale or unreachable", check.details)
        self.assertTrue(any(detail.startswith("app-server version: unavailable (") for detail in check.details))
        self.assertTrue(any("control socket" in detail for detail in check.details))
        self.assertEqual(check.remediation, "Run codex app-server daemon version for more details.")

    def test_doctor_background_server_concise_probe_error_matches_rust(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor/background.rs
        # Rust item: concise_probe_error
        # Contract: probe errors replace the socket path, collapse whitespace, and truncate after 120 chars.
        socket_path = Path("/tmp/codex/app-server-control/app-server-control.sock")
        message = f"failed   to connect\n  to {socket_path} because " + ("x" * 160)

        concise = doctor_updates._concise_probe_error(RuntimeError(message), socket_path)

        self.assertIn("control socket", concise)
        self.assertNotIn(str(socket_path), concise)
        self.assertNotIn("\n", concise)
        self.assertEqual(len(concise), 123)
        self.assertTrue(concise.endswith("..."))

    def test_doctor_thread_inventory_check_ok_when_no_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_thread_inventory_check(codex_home=codex_home, default_provider="test-provider")

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "no rollout/state DB inventory to compare")
        self.assertIn("default model provider: test-provider", check.details)
        self.assertIn("rollout DB active files: 0", check.details)
        self.assertIn("rollout DB rows: skipped (state DB missing)", check.details)

    def test_doctor_thread_inventory_check_ok_when_rollouts_match_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            rollout_dir = codex_home / "sessions" / "2025" / "01" / "02"
            rollout_dir.mkdir(parents=True)
            thread_id = "00000000-0000-0000-0000-000000000001"
            rollout_path = rollout_dir / f"rollout-2025-01-02T10-00-00-{thread_id}.jsonl"
            rollout_path.write_text("{}\n", encoding="utf-8")
            db_path = codex_home / "state_5.sqlite"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE threads (id TEXT, rollout_path TEXT, archived INTEGER, model_provider TEXT, source TEXT)"
                )
                conn.execute(
                    "INSERT INTO threads (id, rollout_path, archived, model_provider, source) VALUES (?, ?, ?, ?, ?)",
                    (thread_id, str(rollout_path), 0, "test-provider", "cli"),
                )

            check = doctor_thread_inventory_check(codex_home=codex_home, default_provider="test-provider")

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "rollout files and state DB thread inventory agree")
        self.assertIn("rollout DB active files: 1", check.details)
        self.assertIn("rollout DB rows: 1", check.details)
        self.assertIn("rollout DB missing active rows: 0", check.details)
        self.assertIn("rollout DB stale rows: 0", check.details)
        self.assertIn("rollout DB archive mismatches: 0", check.details)
        self.assertIn("rollout DB model providers: test-provider=1", check.details)

    def test_doctor_thread_inventory_check_prefers_session_meta_id_over_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            rollout_dir = codex_home / "sessions" / "2025" / "01" / "02"
            rollout_dir.mkdir(parents=True)
            filename_id = "00000000-0000-0000-0000-000000000001"
            meta_id = "00000000-0000-0000-0000-000000000099"
            rollout_path = rollout_dir / f"rollout-2025-01-02T10-00-00-{filename_id}.jsonl"
            rollout_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2025-01-02T10-00-00",
                        "type": "session_meta",
                        "payload": {
                            "id": meta_id,
                            "timestamp": "2025-01-02T10-00-00",
                            "cwd": str(codex_home),
                            "originator": "test",
                            "cli_version": "test",
                            "source": "cli",
                            "model_provider": "test-provider",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            db_path = codex_home / "state_5.sqlite"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE threads (id TEXT, rollout_path TEXT, archived INTEGER, model_provider TEXT, source TEXT)"
                )
                conn.execute(
                    "INSERT INTO threads (id, rollout_path, archived, model_provider, source) VALUES (?, ?, ?, ?, ?)",
                    (meta_id, str(rollout_path), 0, "test-provider", "cli"),
                )

            check = doctor_thread_inventory_check(codex_home=codex_home, default_provider="test-provider")

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "rollout files and state DB thread inventory agree")
        self.assertIn("rollout DB missing active rows: 0", check.details)
        self.assertIn("rollout DB duplicate rollout thread ids: 0", check.details)

    def test_doctor_thread_inventory_check_reports_empty_rollout_as_scan_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            rollout_dir = codex_home / "sessions" / "2025" / "01" / "02"
            rollout_dir.mkdir(parents=True)
            thread_id = "00000000-0000-0000-0000-000000000001"
            rollout_path = rollout_dir / f"rollout-2025-01-02T10-00-00-{thread_id}.jsonl"
            rollout_path.write_text("", encoding="utf-8")

            check = doctor_thread_inventory_check(codex_home=codex_home, default_provider="test-provider")

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "rollout scan was incomplete or found bad files")
        self.assertIn("rollout DB scan errors: 1", check.details)
        self.assertIn("rollout DB rows: skipped (state DB missing)", check.details)
        self.assertTrue(any("no parseable rollout items" in detail for detail in check.details))

    def test_doctor_thread_inventory_check_reports_bad_json_as_scan_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            rollout_dir = codex_home / "sessions" / "2025" / "01" / "02"
            rollout_dir.mkdir(parents=True)
            thread_id = "00000000-0000-0000-0000-000000000001"
            rollout_path = rollout_dir / f"rollout-2025-01-02T10-00-00-{thread_id}.jsonl"
            rollout_path.write_text("{not-json}\n", encoding="utf-8")

            check = doctor_thread_inventory_check(codex_home=codex_home, default_provider="test-provider")

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "rollout scan was incomplete or found bad files")
        self.assertIn("rollout DB scan errors: 1", check.details)
        self.assertTrue(any("Expecting property name enclosed in double quotes" in detail for detail in check.details))

    def test_doctor_thread_inventory_check_warns_for_missing_stale_and_mismatched_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            active_dir = codex_home / "sessions" / "2025" / "01" / "02"
            active_dir.mkdir(parents=True)
            missing_id = "00000000-0000-0000-0000-000000000001"
            missing_path = active_dir / f"rollout-2025-01-02T10-00-00-{missing_id}.jsonl"
            missing_path.write_text("{}\n", encoding="utf-8")
            archived_dir = codex_home / "archived_sessions"
            archived_dir.mkdir()
            mismatch_id = "00000000-0000-0000-0000-000000000002"
            mismatch_path = archived_dir / f"rollout-2025-01-02T11-00-00-{mismatch_id}.jsonl"
            mismatch_path.write_text("{}\n", encoding="utf-8")
            stale_path = active_dir / "rollout-2025-01-02T12-00-00-00000000-0000-0000-0000-000000000003.jsonl"
            db_path = codex_home / "state_5.sqlite"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE threads (id TEXT, rollout_path TEXT, archived INTEGER, model_provider TEXT, source TEXT)"
                )
                conn.execute(
                    "INSERT INTO threads (id, rollout_path, archived, model_provider, source) VALUES (?, ?, ?, ?, ?)",
                    (mismatch_id, str(mismatch_path), 0, "test-provider", "cli"),
                )
                conn.execute(
                    "INSERT INTO threads (id, rollout_path, archived, model_provider, source) VALUES (?, ?, ?, ?, ?)",
                    ("00000000-0000-0000-0000-000000000003", str(stale_path), 0, "test-provider", "cli"),
                )

            check = doctor_thread_inventory_check(codex_home=codex_home, default_provider="test-provider")

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "rollout files and state DB thread inventory differ")
        self.assertIn("rollout DB missing active rows: 1", check.details)
        self.assertIn("rollout DB stale rows: 1", check.details)
        self.assertIn("rollout DB archive mismatches: 1", check.details)

    def test_doctor_thread_inventory_check_summarizes_sources_like_rust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            rollout_dir = codex_home / "sessions" / "2025" / "01" / "02"
            rollout_dir.mkdir(parents=True)
            db_path = codex_home / "state_5.sqlite"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE threads (id TEXT, rollout_path TEXT, archived INTEGER, model_provider TEXT, source TEXT)"
                )
                sources = [
                    "cli",
                    "cli",
                    '"vscode"',
                    '{"type":"custom","name":"x"}',
                    '{"type":"internal","source":"memory_consolidation"}',
                    '{"type":"subagent","subagent_source":"review"}',
                    '{"type":"subagent","subagent_source":"compact"}',
                    '{"type":"subagent","subagent_source":{"type":"thread_spawn"}}',
                    '{"type":"subagent","subagent_source":"memory_consolidation"}',
                    '{"type":"subagent","subagent_source":{"type":"other","value":"x"}}',
                    "not-json",
                ]
                for index, source in enumerate(sources):
                    thread_id = f"00000000-0000-0000-0000-{index + 1:012d}"
                    rollout_path = rollout_dir / f"rollout-2025-01-02T10-00-{index:02d}-{thread_id}.jsonl"
                    rollout_path.write_text(
                        json.dumps({"timestamp": "t", "type": "session_meta", "payload": {"id": thread_id}}) + "\n",
                        encoding="utf-8",
                    )
                    provider = "alpha" if index < 3 else f"provider-{index}"
                    conn.execute(
                        "INSERT INTO threads (id, rollout_path, archived, model_provider, source) VALUES (?, ?, ?, ?, ?)",
                        (thread_id, str(rollout_path), 0, provider, source),
                    )

            check = doctor_thread_inventory_check(codex_home=codex_home, default_provider="test-provider")

        self.assertEqual(check.status, "ok")
        self.assertIn(
            "rollout DB model providers: alpha=3, provider-10=1, provider-3=1, provider-4=1, provider-5=1, provider-6=1, provider-7=1, provider-8=1, other=1 across 1 categories",
            check.details,
        )
        self.assertIn(
            "rollout DB sources: cli=2, custom=1, internal:memory_consolidation=1, subagent:compact=1, subagent:memory_consolidation=1, subagent:other=1, subagent:review=1, subagent:thread_spawn=1, other=2 across 2 categories",
            check.details,
        )

    def test_doctor_thread_inventory_count_summary_caps_distinct_values(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor/thread_inventory.rs
        # Rust test: count_summary_caps_distinct_values
        # Contract: thread inventory count summaries keep the first 8 categories and fold the rest.
        summary = doctor_updates._count_summary(["a", "b", "c", "d", "e", "f", "g", "h", "i"])

        self.assertEqual(
            summary,
            "a=1, b=1, c=1, d=1, e=1, f=1, g=1, h=1, other=1 across 1 categories",
        )

    def test_doctor_mcp_check_reports_no_servers(self) -> None:
        check = doctor_mcp_check(config={})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "no MCP servers configured")
        self.assertEqual(check.details, ())

    def test_doctor_mcp_check_ignores_disabled_servers(self) -> None:
        check = doctor_mcp_check(
            config={
                "mcp_servers": {
                    "disabled": {
                        "url": "http://127.0.0.1:9/mcp",
                        "enabled": False,
                        "required": True,
                        "bearer_token_env_var": "CODEX_DOCTOR_DISABLED_MCP_TOKEN",
                    }
                }
            },
            env={},
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "MCP configuration is locally consistent")
        self.assertIn("configured servers: 1", check.details)
        self.assertIn("disabled servers: 1", check.details)
        self.assertIn("streamable_http servers: 1", check.details)
        self.assertFalse(any("CODEX_DOCTOR_DISABLED_MCP_TOKEN" in detail for detail in check.details))

    def test_mcp_check_ignores_disabled_servers(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: mcp_check_ignores_disabled_servers
        # Contract: disabled MCP servers are counted but skip env and reachability validation.
        check = doctor_mcp_check(
            servers={
                "disabled": {
                    "url": "http://127.0.0.1:9/mcp",
                    "enabled": False,
                    "required": True,
                    "bearer_token_env_var": "CODEX_DOCTOR_DISABLED_MCP_TOKEN",
                }
            },
            env={},
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "MCP configuration is locally consistent")
        self.assertIn("disabled servers: 1", check.details)
        self.assertFalse(any("CODEX_DOCTOR_DISABLED_MCP_TOKEN" in detail for detail in check.details))
        self.assertFalse(any("reachability failed" in detail for detail in check.details))

    def test_doctor_mcp_check_warns_for_optional_http_reachability(self) -> None:
        def probe(_url: str, _method: str) -> int:
            raise TimeoutError("request timed out")

        check = doctor_mcp_check(
            config={"mcp_servers": {"optional": {"url": "http://127.0.0.1:9/mcp"}}},
            env={},
            http_status_probe=probe,
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "MCP configuration has optional issues")
        self.assertTrue(any(detail.startswith("optional reachability failed: optional:") for detail in check.details))

    def test_mcp_check_warns_for_optional_http_reachability(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: mcp_check_warns_for_optional_http_reachability
        # Contract: optional streamable HTTP MCP reachability failures warn instead of failing.
        def probe(_url: str, _method: str) -> int:
            raise TimeoutError("request timed out")

        check = doctor_mcp_check(
            servers={"optional": {"url": "http://127.0.0.1:9/mcp"}},
            env={},
            http_status_probe=probe,
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "MCP configuration has optional issues")
        self.assertTrue(any("optional reachability failed: optional:" in detail for detail in check.details))

    def test_doctor_mcp_check_fails_required_remote_stdio_env_var(self) -> None:
        check = doctor_mcp_check(
            config={
                "mcp_servers": {
                    "required": {
                        "command": "python",
                        "required": True,
                        "env_vars": [{"name": "REMOTE_ONLY_TOKEN", "source": "remote"}],
                    }
                }
            },
            env={},
        )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "MCP configuration has failing required inputs or reachability")
        self.assertIn(
            "required: env_vars entry `REMOTE_ONLY_TOKEN` uses source `remote`, which requires remote MCP stdio",
            check.details,
        )

    def test_mcp_check_fails_required_remote_stdio_env_var(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: mcp_check_fails_required_remote_stdio_env_var
        # Contract: required stdio MCP servers fail when env_vars use source=remote.
        check = doctor_mcp_check(
            servers={
                "required": {
                    "command": "python",
                    "required": True,
                    "env_vars": [{"name": "REMOTE_ONLY_TOKEN", "source": "remote"}],
                }
            },
            env={},
        )

        self.assertEqual(check.status, "fail")
        self.assertTrue(
            any(
                "required: env_vars entry `REMOTE_ONLY_TOKEN` uses source `remote`, which requires remote MCP stdio"
                in detail
                for detail in check.details
            )
        )

    def test_mcp_check_fails_required_missing_stdio_command(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: mcp_check_fails_required_missing_stdio_command
        # Contract: required stdio MCP servers fail when the command cannot be resolved.
        check = doctor_mcp_check(
            servers={
                "required": {
                    "command": "definitely-missing-codex-doctor-mcp",
                    "required": True,
                }
            },
            env={},
        )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "MCP configuration has failing required inputs or reachability")
        self.assertTrue(
            any(
                'required: stdio command "definitely-missing-codex-doctor-mcp" is not resolvable'
                in detail
                for detail in check.details
            )
        )

    def test_stdio_command_resolves_relative_path_against_cwd(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stdio_command_resolves
        # Contract: stdio commands with path components resolve relative to the configured cwd.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            tool = cwd / "tools" / "codex-doctor-mcp"
            tool.parent.mkdir()
            tool.write_text("#!/bin/sh\n", encoding="utf-8")
            tool.chmod(0o700)

            self.assertTrue(
                doctor_updates._stdio_command_resolves("tools/codex-doctor-mcp", str(cwd), server_env={})
            )
            self.assertFalse(
                doctor_updates._stdio_command_resolves("tools/missing-codex-doctor-mcp", str(cwd), server_env={})
            )

    def test_executable_path_exists_matches_rust_file_checks(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: executable_path_exists_rejects_non_executable_file
        # Rust item: executable_path_exists
        # Contract: executable path checks require a file and, on Unix, executable permission bits.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "bin-dir"
            directory.mkdir()
            tool = root / "codex-doctor-mcp"
            tool.write_text("#!/bin/sh\n", encoding="utf-8")
            tool.chmod(0o700)
            non_executable = root / "not-executable"
            non_executable.write_text("#!/bin/sh\n", encoding="utf-8")
            non_executable.chmod(0o600)

            self.assertIsNone(doctor_updates._executable_path_exists(tool))
            self.assertEqual(doctor_updates._executable_path_exists(directory), "path is not a file")
            if doctor_updates.os.name != "nt":
                self.assertIn("is not executable", doctor_updates._executable_path_exists(non_executable) or "")

    def test_stdio_command_resolves_server_env_path_override(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stdio_command_resolves
        # Contract: stdio command lookup honors the MCP server env PATH before falling back elsewhere.
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            tool = bin_dir / "codex-doctor-mcp.cmd"
            tool.write_text("@echo off\n", encoding="utf-8")
            tool.chmod(0o700)

            self.assertTrue(
                doctor_updates._stdio_command_resolves(
                    "codex-doctor-mcp.cmd",
                    cwd=None,
                    server_env={"PATH": str(bin_dir)},
                )
            )
            self.assertFalse(
                doctor_updates._stdio_command_resolves(
                    "codex-doctor-mcp.cmd",
                    cwd=None,
                    server_env={"PATH": str(Path(tmp) / "missing-bin")},
                )
            )

    def test_stdio_command_resolves_empty_server_path_does_not_check_cwd_for_bare_command(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stdio_command_resolves
        # Contract: a server-provided PATH, even empty, controls bare command lookup.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            tool = cwd / "codex-doctor-mcp.cmd"
            tool.write_text("@echo off\n", encoding="utf-8")
            tool.chmod(0o700)

            self.assertFalse(
                doctor_updates._stdio_command_resolves(
                    "codex-doctor-mcp.cmd",
                    cwd=str(cwd),
                    server_env={"PATH": ""},
                )
            )

    def test_provider_auth_reachability_mode_uses_api_key_auth(self) -> None:
        mode = provider_auth_reachability_mode_from_auth(
            requires_openai_auth=True,
            env={},
            stored_auth={"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-test"},
        )
        env_mode = provider_auth_reachability_mode_from_auth(
            requires_openai_auth=True,
            env={"OPENAI_API_KEY": "sk-test"},
            stored_auth=None,
        )

        self.assertEqual(mode, "API key auth")
        self.assertEqual(env_mode, "API key auth")

    def test_provider_reachability_mode_uses_api_key_auth(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_mode_uses_api_key_auth
        # Contract: stored API-key auth or OPENAI_API_KEY env selects API-key reachability mode.
        self.assertEqual(
            provider_auth_reachability_mode_from_auth(
                requires_openai_auth=True,
                env={},
                stored_auth={"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-test"},
            ),
            "API key auth",
        )
        self.assertEqual(
            provider_auth_reachability_mode_from_auth(
                requires_openai_auth=True,
                env={"OPENAI_API_KEY": "sk-test"},
                stored_auth=None,
            ),
            "API key auth",
        )

    def test_provider_reachability_mode_handles_codex_env_auth(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_auth_reachability_mode_from_auth
        # Contract: CODEX_API_KEY selects API key auth; CODEX_ACCESS_TOKEN selects ChatGPT auth.
        self.assertEqual(
            provider_auth_reachability_mode_from_auth(
                requires_openai_auth=True,
                env={"CODEX_API_KEY": "sk-codex"},
                stored_auth=None,
            ),
            "API key auth",
        )
        self.assertEqual(
            provider_auth_reachability_mode_from_auth(
                requires_openai_auth=True,
                env={"CODEX_ACCESS_TOKEN": "chatgpt-token"},
                stored_auth=None,
            ),
            "ChatGPT auth",
        )
        self.assertEqual(
            provider_auth_reachability_mode_from_auth(
                requires_openai_auth=False,
                env={"CODEX_API_KEY": "sk-codex"},
                stored_auth=None,
            ),
            "provider auth",
        )

    def test_provider_reachability_mode_api_key_env_precedes_access_token_and_stored_auth(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_auth_reachability_mode_from_auth
        # Contract: API-key env vars are checked before CODEX_ACCESS_TOKEN and stored auth.
        for env in (
            {"OPENAI_API_KEY": "sk-openai", "CODEX_ACCESS_TOKEN": "chatgpt-token"},
            {"CODEX_API_KEY": "sk-codex", "CODEX_ACCESS_TOKEN": "chatgpt-token"},
        ):
            with self.subTest(env=env):
                self.assertEqual(
                    provider_auth_reachability_mode_from_auth(
                        requires_openai_auth=True,
                        env=env,
                        stored_auth={"auth_mode": "chatgptAuthTokens"},
                    ),
                    "API key auth",
                )

    def test_provider_reachability_mode_ignores_empty_api_key_env_before_access_token(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_auth_reachability_mode_from_auth / env_var_present
        # Contract: empty API-key env vars are absent, so CODEX_ACCESS_TOKEN can select ChatGPT reachability.
        for env in (
            {"OPENAI_API_KEY": "", "CODEX_ACCESS_TOKEN": "chatgpt-token"},
            {"CODEX_API_KEY": "", "CODEX_ACCESS_TOKEN": "chatgpt-token"},
        ):
            with self.subTest(env=env):
                self.assertEqual(
                    provider_auth_reachability_mode_from_auth(
                        requires_openai_auth=True,
                        env=env,
                        stored_auth={"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-stored"},
                    ),
                    "ChatGPT auth",
                )

    def test_provider_reachability_mode_access_token_precedes_stored_api_key(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_auth_reachability_mode_from_auth
        # Contract: CODEX_ACCESS_TOKEN is checked before stored auth, including stored API-key auth.
        self.assertEqual(
            provider_auth_reachability_mode_from_auth(
                requires_openai_auth=True,
                env={"CODEX_ACCESS_TOKEN": "chatgpt-token"},
                stored_auth={"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-test"},
            ),
            "ChatGPT auth",
        )

    def test_provider_reachability_mode_infers_api_key_from_stored_key_without_auth_mode(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_auth_reachability_mode_from_auth / stored_auth_mode_value
        # Contract: stored auth without explicit mode uses API-key reachability when OPENAI_API_KEY is present.
        self.assertEqual(
            provider_auth_reachability_mode_from_auth(
                requires_openai_auth=True,
                env={},
                stored_auth={"OPENAI_API_KEY": "sk-stored"},
            ),
            "API key auth",
        )

    def test_provider_reachability_mode_not_required_ignores_stored_auth(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_auth_reachability_mode_from_auth
        # Contract: providers that do not require OpenAI auth use provider reachability regardless of stored auth.
        for stored_auth in (
            {"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-test"},
            {"auth_mode": "chatgptAuthTokens"},
            {"auth_mode": "agentIdentity", "agent_identity": "token"},
        ):
            with self.subTest(stored_auth=stored_auth):
                self.assertEqual(
                    provider_auth_reachability_mode_from_auth(
                        requires_openai_auth=False,
                        env={},
                        stored_auth=stored_auth,
                    ),
                    "provider auth",
                )

    def test_provider_reachability_mode_treats_non_api_stored_auth_as_chatgpt(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_auth_reachability_mode_from_auth
        # Contract: stored ChatGPT auth-token and agent-identity modes use ChatGPT reachability.
        for stored_auth in (
            {"auth_mode": "chatgptAuthTokens"},
            {"auth_mode": "agentIdentity", "agent_identity": "token"},
            {},
            None,
        ):
            with self.subTest(stored_auth=stored_auth):
                self.assertEqual(
                    provider_auth_reachability_mode_from_auth(
                        requires_openai_auth=True,
                        env={},
                        stored_auth=stored_auth,
                    ),
                    "ChatGPT auth",
                )

    def test_provider_reachability_plan_uses_active_provider_endpoint(self) -> None:
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="azure",
            provider_name="azure",
            provider_base_url="https://example.openai.azure.com/openai/v1",
        )

        self.assertEqual(plan.description, "provider auth")
        self.assertEqual(len(plan.endpoints), 1)
        self.assertEqual(plan.endpoints[0].label, "azure API")
        self.assertEqual(plan.endpoints[0].url, "https://example.openai.azure.com/openai/v1")
        self.assertIsNone(plan.endpoints[0].route_probe_url)

    def test_provider_reachability_plan_omits_endpoint_when_provider_auth_has_no_base_url(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_plan_from_parts
        # Contract: provider-auth mode without a provider base URL has no endpoint to probe.
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="local",
            provider_name="Local",
            provider_base_url=None,
        )

        self.assertEqual(plan.description, "provider auth")
        self.assertEqual(plan.endpoints, ())

    def test_provider_reachability_check_ok_when_no_endpoint_to_probe(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check
        # Contract: empty reachability plans are ok and report that no endpoint is configured.
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="local",
            provider_name="Local",
            provider_base_url=None,
        )

        check = doctor_provider_reachability_check(plan=plan)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "active provider has no HTTP endpoint to probe")
        self.assertEqual(
            check.details,
            (
                "reachability mode: provider auth",
                "active provider endpoint: none configured",
            ),
        )
        self.assertIsNone(check.remediation)
        self.assertEqual(check.issues, ())

    def test_provider_reachability_optional_base_failure_warns(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check
        # Contract: optional endpoint base probe failures warn instead of failing the reachability check.
        plan = doctor_updates.ReachabilityPlan(
            description="provider auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="optional API",
                    url="https://example.com/v1",
                    required=False,
                ),
            ),
        )

        def probe(url: str, method: str) -> int:
            raise TimeoutError()

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "provider endpoint checks returned warnings")
        self.assertEqual(
            check.details,
            (
                "reachability mode: provider auth",
                "optional API base URL: https://example.com/v1 request timed out (optional)",
            ),
        )
        self.assertEqual(check.issues, ())
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")

    def test_provider_reachability_optional_failure_survives_later_success(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check / provider_reachability_outcome
        # Contract: optional base failures remain warnings while later endpoints are still probed normally.
        plan = doctor_updates.ReachabilityPlan(
            description="provider auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="optional API",
                    url="https://optional.example.com/v1",
                    required=False,
                ),
                doctor_updates.ReachabilityEndpoint(
                    label="required API",
                    url="https://required.example.com/v1",
                    required=True,
                    route_probe_url="https://required.example.com/v1/models",
                ),
            ),
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if url == "https://optional.example.com/v1":
                raise TimeoutError()
            return 401 if method == "GET" else 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "provider endpoint checks returned warnings")
        self.assertIn(
            "optional API base URL: https://optional.example.com/v1 request timed out (optional)",
            check.details,
        )
        self.assertIn(
            "required API route probe: https://required.example.com/v1/models route exists (HTTP 401)",
            check.details,
        )
        self.assertEqual(check.issues, ())
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")
        self.assertEqual(
            calls,
            [
                ("https://optional.example.com/v1", "HEAD"),
                ("https://required.example.com/v1", "HEAD"),
                ("https://required.example.com/v1/models", "GET"),
            ],
        )

    def test_provider_reachability_required_base_failure_fails_without_issue(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check
        # Contract: required endpoint base probe failures fail, skip route probing, and do not add structured issues.
        plan = doctor_updates.ReachabilityPlan(
            description="API key auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="required API",
                    url="https://example.com/v1",
                    required=True,
                    route_probe_url="https://example.com/v1/models",
                ),
            ),
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            raise TimeoutError()

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "one or more required provider endpoints are unreachable over HTTP")
        self.assertEqual(
            check.details,
            (
                "reachability mode: API key auth",
                "required API base URL: https://example.com/v1 request timed out (required)",
            ),
        )
        self.assertEqual(check.issues, ())
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")
        self.assertEqual(calls, [("https://example.com/v1", "HEAD")])

    def test_provider_reachability_required_failure_precedes_later_route_warning(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check / provider_reachability_outcome
        # Contract: later route warnings are still recorded, but required base failures determine fail status.
        plan = doctor_updates.ReachabilityPlan(
            description="API key auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="required API",
                    url="https://required.example.com/v1",
                    required=True,
                ),
                doctor_updates.ReachabilityEndpoint(
                    label="warning API",
                    url="https://warning.example.com/v1",
                    required=True,
                    route_probe_url="https://warning.example.com/v1/models",
                ),
            ),
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if url == "https://required.example.com/v1":
                raise TimeoutError()
            return 500 if method == "GET" else 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "one or more required provider endpoints are unreachable over HTTP")
        self.assertIn(
            "required API base URL: https://required.example.com/v1 request timed out (required)",
            check.details,
        )
        self.assertIn(
            "warning API route probe: https://warning.example.com/v1/models returned HTTP 500 (warning)",
            check.details,
        )
        self.assertEqual(check.issues, ())
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")
        self.assertEqual(
            calls,
            [
                ("https://required.example.com/v1", "HEAD"),
                ("https://warning.example.com/v1", "HEAD"),
                ("https://warning.example.com/v1/models", "GET"),
            ],
        )

    def test_provider_reachability_base_http_statuses_still_probe_route(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: http_probe_url / provider_reachability_check
        # Contract: successful base probes are considered reachable regardless of HTTP status code.
        plan = doctor_updates.ReachabilityPlan(
            description="API key auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="required API",
                    url="https://example.com/v1",
                    required=True,
                    route_probe_url="https://example.com/v1/models",
                ),
            ),
        )

        for base_status in (302, 500):
            with self.subTest(base_status=base_status):
                calls: list[tuple[str, str]] = []

                def probe(url: str, method: str) -> int:
                    calls.append((url, method))
                    return 401 if method == "GET" else base_status

                check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

                self.assertEqual(check.status, "ok")
                self.assertEqual(check.summary, "active provider endpoints are reachable over HTTP")
                self.assertIn(
                    f"required API base URL: https://example.com/v1 reachable (HTTP {base_status})",
                    check.details,
                )
                self.assertIn(
                    "required API route probe: https://example.com/v1/models route exists (HTTP 401)",
                    check.details,
                )
                self.assertEqual(check.issues, ())
                self.assertIsNone(check.remediation)
                self.assertEqual(
                    calls,
                    [
                        ("https://example.com/v1", "HEAD"),
                        ("https://example.com/v1/models", "GET"),
                    ],
                )

    def test_provider_reachability_uses_active_provider_endpoint(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_uses_active_provider_endpoint
        # Contract: provider-auth reachability probes the active provider base URL.
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="azure",
            provider_name="azure",
            provider_base_url="https://example.openai.azure.com/openai/v1",
        )

        self.assertEqual(plan.description, "provider auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "azure API")
        self.assertEqual(endpoint.url, "https://example.openai.azure.com/openai/v1")
        self.assertTrue(endpoint.required)
        self.assertIsNone(endpoint.route_probe_url)

    def test_provider_reachability_plan_adds_models_route_probe(self) -> None:
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="custom",
            provider_name="Custom",
            provider_base_url="https://example.com/openai/v1/",
            provider_query_params={"api-version": "2026-01-01"},
        )

        self.assertEqual(
            plan.endpoints[0].route_probe_url,
            "https://example.com/openai/v1/models?api-version=2026-01-01",
        )

    def test_provider_reachability_plan_uses_default_api_key_endpoint_and_route_probe(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_plan_from_parts
        # Contract: API-key mode without a provider base URL probes the default OpenAI API and /models route.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
            provider_base_url=None,
        )

        self.assertEqual(plan.description, "API key auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "openai API")
        self.assertEqual(endpoint.url, "https://api.openai.com/v1")
        self.assertTrue(endpoint.required)
        self.assertEqual(endpoint.route_probe_url, "https://api.openai.com/v1/models")

    def test_provider_reachability_plan_uses_configured_api_key_endpoint_and_route_probe(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_plan_from_parts
        # Contract: API-key mode uses a configured provider base URL instead of the default OpenAI endpoint.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="custom",
            provider_name="Custom",
            provider_base_url="https://example.com/openai/v1/",
            provider_query_params={"api-version": "2026-01-01"},
        )

        self.assertEqual(plan.description, "API key auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "custom API")
        self.assertEqual(endpoint.url, "https://example.com/openai/v1/")
        self.assertTrue(endpoint.required)
        self.assertEqual(
            endpoint.route_probe_url,
            "https://example.com/openai/v1/models?api-version=2026-01-01",
        )

    def test_provider_reachability_plan_api_key_skips_azure_route_probe(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_plan_from_parts
        # Contract: API-key plans reuse Rust's route-probe filter and skip Azure Responses /models probes.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="azure",
            provider_name="azure",
            provider_base_url="https://example.openai.azure.com/openai/v1",
            provider_query_params={"api-version": "2026-01-01"},
        )

        self.assertEqual(plan.description, "API key auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "azure API")
        self.assertEqual(endpoint.url, "https://example.openai.azure.com/openai/v1")
        self.assertTrue(endpoint.required)
        self.assertIsNone(endpoint.route_probe_url)

    def test_provider_reachability_plan_api_key_skips_bedrock_route_probe(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_plan_from_parts
        # Contract: API-key plans reuse Rust's route-probe filter and skip Amazon Bedrock /models probes.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="amazon-bedrock",
            provider_name="Amazon Bedrock",
            provider_base_url="https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1",
            provider_query_params={"api-version": "2026-01-01"},
            is_amazon_bedrock=True,
        )

        self.assertEqual(plan.description, "API key auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "amazon-bedrock API")
        self.assertEqual(endpoint.url, "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1")
        self.assertTrue(endpoint.required)
        self.assertIsNone(endpoint.route_probe_url)

    def test_provider_reachability_plan_uses_configured_chatgpt_endpoint_without_route_probe(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_plan_from_parts
        # Contract: ChatGPT auth probes the configured ChatGPT base URL and never adds a /models route probe.
        plan = provider_reachability_plan_from_parts(
            mode="ChatGPT auth",
            provider_id="openai",
            provider_name="OpenAI",
            chatgpt_base_url="https://chatgpt.example.test/backend-api/",
        )

        self.assertEqual(plan.description, "ChatGPT auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "ChatGPT")
        self.assertEqual(endpoint.url, "https://chatgpt.example.test/backend-api/")
        self.assertTrue(endpoint.required)
        self.assertIsNone(endpoint.route_probe_url)

    def test_provider_reachability_plan_chatgpt_ignores_provider_endpoint(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_plan_from_parts
        # Contract: ChatGPT auth ignores provider base/query route planning and probes only chatgpt_base_url.
        plan = provider_reachability_plan_from_parts(
            mode="ChatGPT auth",
            provider_id="custom",
            provider_name="Custom",
            provider_base_url="https://example.com/openai/v1/",
            provider_query_params={"api-version": "2026-01-01"},
            chatgpt_base_url="https://chatgpt.example.test/backend-api/",
        )

        self.assertEqual(plan.description, "ChatGPT auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "ChatGPT")
        self.assertEqual(endpoint.url, "https://chatgpt.example.test/backend-api/")
        self.assertTrue(endpoint.required)
        self.assertIsNone(endpoint.route_probe_url)

    def test_provider_url_for_path_matches_rust_slash_and_query_rules(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_url_for_path
        # Contract: trims join slashes, preserves empty path as the trimmed base, and appends query params with ? or &.
        self.assertEqual(
            doctor_updates._provider_url_for_path(
                "https://example.com/openai/v1/",
                "/models",
                {"api-version": "2026-01-01"},
            ),
            "https://example.com/openai/v1/models?api-version=2026-01-01",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path(
                "https://example.com/openai/v1///",
                "///models",
                {"api-version": "2026-01-01"},
            ),
            "https://example.com/openai/v1/models?api-version=2026-01-01",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path(
                "https://example.com/openai/v1/?existing=true",
                "models",
                {"api-version": "2026-01-01"},
            ),
            "https://example.com/openai/v1/?existing=true/models&api-version=2026-01-01",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path("https://example.com/openai/v1/", "", None),
            "https://example.com/openai/v1",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path("https://example.com/openai/v1///", "///", None),
            "https://example.com/openai/v1",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path(
                "https://example.com/openai/v1///",
                "///",
                {"api-version": "2026-01-01"},
            ),
            "https://example.com/openai/v1?api-version=2026-01-01",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path(
                "https://example.com/openai/v1/",
                "",
                {"api-version": "2026-01-01"},
            ),
            "https://example.com/openai/v1?api-version=2026-01-01",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path(
                "https://example.com/openai/v1?existing=true",
                "",
                {"api-version": "2026-01-01"},
            ),
            "https://example.com/openai/v1?existing=true&api-version=2026-01-01",
        )
        self.assertEqual(
            doctor_updates._provider_url_for_path("https://example.com/openai/v1/", "models", {}),
            "https://example.com/openai/v1/models",
        )

    def test_should_probe_models_route_matches_rust_provider_filters(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: should_probe_models_route
        # Contract: /models route probes are skipped for Bedrock and Azure Responses providers only.
        self.assertFalse(
            doctor_updates._should_probe_models_route(
                "Amazon Bedrock",
                "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1",
                True,
            )
        )
        self.assertFalse(
            doctor_updates._should_probe_models_route(
                "azure",
                "https://example.openai.azure.com/openai/v1",
                False,
            )
        )
        self.assertTrue(
            doctor_updates._should_probe_models_route(
                "Custom",
                "https://example.com/openai/v1",
                False,
            )
        )

    def test_provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_adds_models_route_probe_for_openai_compatible_base_urls
        # Contract: OpenAI-compatible provider base URLs get a required /models route probe with query params.
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="custom",
            provider_name="Custom",
            provider_base_url="https://example.com/openai/v1/",
            provider_query_params={"api-version": "2026-01-01"},
        )

        self.assertEqual(plan.description, "provider auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "custom API")
        self.assertEqual(endpoint.url, "https://example.com/openai/v1/")
        self.assertTrue(endpoint.required)
        self.assertEqual(
            endpoint.route_probe_url,
            "https://example.com/openai/v1/models?api-version=2026-01-01",
        )

    def test_provider_reachability_skips_route_probe_for_bedrock(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_skips_route_probe_for_bedrock
        # Contract: Amazon Bedrock OpenAI-compatible endpoints skip the /models route probe.
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="amazon-bedrock",
            provider_name="Amazon Bedrock",
            provider_base_url="https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1",
            is_amazon_bedrock=True,
        )

        self.assertEqual(len(plan.endpoints), 1)
        self.assertIsNone(plan.endpoints[0].route_probe_url)

    def test_provider_reachability_plan_from_config_uses_active_provider_and_auth(self) -> None:
        plan = provider_reachability_plan_from_config(
            config={
                "model_provider_id": "custom",
                "model_provider": {
                    "name": "Custom",
                    "base_url": "https://example.com/api/v1",
                    "query_params": {"api-version": "2026-01-01"},
                    "requires_openai_auth": False,
                },
            },
            env={},
            stored_auth=None,
        )

        self.assertEqual(plan.description, "provider auth")
        self.assertEqual(plan.endpoints[0].label, "custom API")
        self.assertEqual(plan.endpoints[0].url, "https://example.com/api/v1")
        self.assertEqual(
            plan.endpoints[0].route_probe_url,
            "https://example.com/api/v1/models?api-version=2026-01-01",
        )

    def test_provider_reachability_plan_from_config_uses_stored_api_key_mode(self) -> None:
        plan = provider_reachability_plan_from_config(
            config={},
            env={},
            stored_auth={"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-test"},
        )

        self.assertEqual(plan.description, "API key auth")
        self.assertEqual(plan.endpoints[0].url, "https://api.openai.com/v1")
        self.assertEqual(plan.endpoints[0].route_probe_url, "https://api.openai.com/v1/models")

    def test_provider_reachability_api_key_does_not_require_chatgpt(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_api_key_does_not_require_chatgpt
        # Contract: API-key reachability probes the OpenAI API endpoint instead of ChatGPT.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
        )

        self.assertEqual(plan.description, "API key auth")
        self.assertEqual(len(plan.endpoints), 1)
        endpoint = plan.endpoints[0]
        self.assertEqual(endpoint.label, "openai API")
        self.assertEqual(endpoint.url, "https://api.openai.com/v1")
        self.assertTrue(endpoint.required)
        self.assertEqual(endpoint.route_probe_url, "https://api.openai.com/v1/models")

    def test_provider_reachability_outcome_reports_required_failures(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_outcome_reports_required_failures
        # Contract: reachability warnings are warnings, but required failures take fail status.
        self.assertEqual(
            doctor_updates._provider_reachability_outcome(required_failures=0, warnings=1),
            ("warn", "provider endpoint checks returned warnings"),
        )
        self.assertEqual(
            doctor_updates._provider_reachability_outcome(required_failures=1, warnings=0),
            ("fail", "one or more required provider endpoints are unreachable over HTTP"),
        )
        self.assertEqual(
            doctor_updates._provider_reachability_outcome(required_failures=1, warnings=1),
            ("fail", "one or more required provider endpoints are unreachable over HTTP"),
        )

    def test_http_probe_error_text_matches_rust_error_classes(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: http_probe_url_with_timeout / http_get_probe_status_with_timeout
        # Contract: HTTP probe errors collapse timeout/connect/builder classes to stable Rust messages.
        self.assertEqual(doctor_updates._http_probe_error_text(TimeoutError()), "request timed out")
        self.assertEqual(
            doctor_updates._http_probe_error_text(doctor_updates.URLError(TimeoutError())),
            "request timed out",
        )
        self.assertEqual(
            doctor_updates._http_probe_error_text(ConnectionRefusedError("refused")),
            "connect failed",
        )
        self.assertEqual(
            doctor_updates._http_probe_error_text(doctor_updates.URLError(ConnectionRefusedError("refused"))),
            "connect failed",
        )
        self.assertEqual(
            doctor_updates._http_probe_error_text(ValueError("bad url")),
            "request could not be built",
        )
        self.assertEqual(
            doctor_updates._http_probe_error_text(RuntimeError("tls handshake failed")),
            "tls handshake failed",
        )
        self.assertEqual(
            doctor_updates._http_probe_error_text(doctor_updates.URLError("dns lookup failed")),
            "dns lookup failed",
        )

    def test_default_reachability_plan_uses_chatgpt_without_env_auth(self) -> None:
        plan = default_reachability_plan()

        self.assertEqual(plan.description, "ChatGPT auth")
        self.assertEqual(len(plan.endpoints), 1)
        self.assertEqual(plan.endpoints[0].label, "ChatGPT")
        self.assertEqual(plan.endpoints[0].url, "https://chatgpt.com/backend-api/")
        self.assertTrue(plan.endpoints[0].required)
        self.assertIsNone(plan.endpoints[0].route_probe_url)

    def test_doctor_provider_reachability_check_probes_base_and_models_route(self) -> None:
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if method == "GET":
                return 401
            return 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "active provider endpoints are reachable over HTTP")
        self.assertIn("reachability mode: API key auth", check.details)
        self.assertIn("openai API base URL: https://api.openai.com/v1 reachable (HTTP 200)", check.details)
        self.assertIn("openai API route probe: https://api.openai.com/v1/models route exists (HTTP 401)", check.details)
        self.assertEqual(
            calls,
            [
                ("https://api.openai.com/v1", "HEAD"),
                ("https://api.openai.com/v1/models", "GET"),
            ],
        )

    def test_provider_reachability_multiple_success_endpoints_stays_ok(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check / provider_reachability_outcome
        # Contract: multiple successful endpoints stay ok and do not attach remediation or issues.
        plan = doctor_updates.ReachabilityPlan(
            description="API key auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="first API",
                    url="https://first.example.com/v1",
                    required=True,
                    route_probe_url="https://first.example.com/v1/models",
                ),
                doctor_updates.ReachabilityEndpoint(
                    label="second API",
                    url="https://second.example.com/v1",
                    required=True,
                    route_probe_url="https://second.example.com/v1/models",
                ),
            ),
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if url == "https://first.example.com/v1/models":
                return 204
            if url == "https://second.example.com/v1/models":
                return 403
            return 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "active provider endpoints are reachable over HTTP")
        self.assertIn(
            "first API route probe: https://first.example.com/v1/models route exists (HTTP 204)",
            check.details,
        )
        self.assertIn(
            "second API route probe: https://second.example.com/v1/models route exists (HTTP 403)",
            check.details,
        )
        self.assertEqual(check.issues, ())
        self.assertIsNone(check.remediation)
        self.assertEqual(
            calls,
            [
                ("https://first.example.com/v1", "HEAD"),
                ("https://first.example.com/v1/models", "GET"),
                ("https://second.example.com/v1", "HEAD"),
                ("https://second.example.com/v1/models", "GET"),
            ],
        )

    def test_provider_reachability_route_401_keeps_reachability_ok(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_route_401_keeps_reachability_ok
        # Contract: a 401 /models route probe still proves provider route reachability.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
            provider_base_url="http://127.0.0.1:9876/v1",
        )

        def probe(url: str, method: str) -> int:
            return 401 if method == "GET" else 404

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "ok")
        self.assertIn("openai API base URL: http://127.0.0.1:9876/v1 reachable (HTTP 404)", check.details)
        self.assertIn(
            "openai API route probe: http://127.0.0.1:9876/v1/models route exists (HTTP 401)",
            check.details,
        )

    def test_provider_reachability_route_403_keeps_reachability_ok(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_route_probe_url / provider_reachability_check
        # Contract: a 403 /models route probe also proves provider route reachability.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
            provider_base_url="http://127.0.0.1:9876/v1",
        )

        def probe(url: str, method: str) -> int:
            return 403 if method == "GET" else 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "active provider endpoints are reachable over HTTP")
        self.assertIn(
            "openai API route probe: http://127.0.0.1:9876/v1/models route exists (HTTP 403)",
            check.details,
        )
        self.assertEqual(check.issues, ())
        self.assertIsNone(check.remediation)

    def test_provider_reachability_route_204_keeps_reachability_ok(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_route_probe_url / provider_reachability_check
        # Contract: any 2xx /models route probe proves provider route reachability.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
            provider_base_url="http://127.0.0.1:9876/v1",
        )

        for route_status in (200, 204, 299):
            with self.subTest(route_status=route_status):

                def probe(url: str, method: str) -> int:
                    return route_status if method == "GET" else 200

                check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

                self.assertEqual(check.status, "ok")
                self.assertEqual(check.summary, "active provider endpoints are reachable over HTTP")
                self.assertIn(
                    f"openai API route probe: http://127.0.0.1:9876/v1/models route exists (HTTP {route_status})",
                    check.details,
                )
                self.assertEqual(check.issues, ())
                self.assertIsNone(check.remediation)

    def test_provider_reachability_route_404_fails_bad_base_url_path(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_reachability_route_404_fails_bad_base_url_path
        # Contract: a 404 /models route probe fails reachability and reports Rust issue metadata.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
            provider_base_url="http://127.0.0.1:9876/xxxx",
        )

        def probe(url: str, method: str) -> int:
            return 404

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "fail")
        self.assertTrue(any("route probe:" in detail and "HTTP 404" in detail for detail in check.details))
        self.assertEqual(len(check.issues), 1)
        self.assertEqual(check.issues[0]["severity"], "fail")
        self.assertEqual(
            check.issues[0]["cause"],
            "provider base URL route returned 404 - verify the configured API prefix",
        )
        self.assertEqual(
            check.issues[0]["measured"],
            "http://127.0.0.1:9876/xxxx/models returned HTTP 404",
        )
        self.assertEqual(check.issues[0]["expected"], "GET /models returns 2xx, 401, or 403")
        self.assertEqual(
            check.issues[0]["remedy"],
            "Set base_url to the provider API root, for example https://api.openai.com/v1",
        )
        self.assertEqual(check.issues[0]["fields"], ["route probe"])

    def test_provider_reachability_route_failure_allows_later_success(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check
        # Contract: a route failure records an issue but does not stop later endpoints from being probed.
        plan = doctor_updates.ReachabilityPlan(
            description="API key auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="bad API",
                    url="https://bad.example.com/v1",
                    required=True,
                    route_probe_url="https://bad.example.com/v1/models",
                ),
                doctor_updates.ReachabilityEndpoint(
                    label="ok API",
                    url="https://ok.example.com/v1",
                    required=True,
                    route_probe_url="https://ok.example.com/v1/models",
                ),
            ),
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if url == "https://bad.example.com/v1/models":
                return 404
            if url == "https://ok.example.com/v1/models":
                return 401
            return 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "one or more required provider endpoints are unreachable over HTTP")
        self.assertIn(
            "bad API route probe: https://bad.example.com/v1/models returned HTTP 404 (required)",
            check.details,
        )
        self.assertIn(
            "ok API route probe: https://ok.example.com/v1/models route exists (HTTP 401)",
            check.details,
        )
        self.assertEqual(len(check.issues), 1)
        self.assertEqual(
            check.issues[0]["measured"],
            "https://bad.example.com/v1/models returned HTTP 404",
        )
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")
        self.assertEqual(
            calls,
            [
                ("https://bad.example.com/v1", "HEAD"),
                ("https://bad.example.com/v1/models", "GET"),
                ("https://ok.example.com/v1", "HEAD"),
                ("https://ok.example.com/v1/models", "GET"),
            ],
        )

    def test_provider_reachability_route_probe_transport_error_reports_issue(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check
        # Contract: provider route-probe transport errors fail reachability and include structured issue metadata.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
            provider_base_url="http://127.0.0.1:9876/v1",
        )

        def probe(url: str, method: str) -> int:
            if method == "GET":
                raise ConnectionRefusedError("refused")
            return 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "fail")
        self.assertIn(
            "openai API route probe: http://127.0.0.1:9876/v1/models connect failed (required)",
            check.details,
        )
        self.assertEqual(len(check.issues), 1)
        self.assertEqual(
            check.issues[0],
            {
                "severity": "fail",
                "cause": "provider route probe could not connect - verify network access to the provider API",
                "measured": "http://127.0.0.1:9876/v1/models connect failed",
                "expected": "GET /models completes",
                "remedy": "Check proxy, VPN, firewall, DNS, and custom CA configuration.",
                "fields": ["route probe"],
            },
        )
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")

    def test_provider_reachability_route_transport_error_allows_later_success(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check
        # Contract: route transport errors record an issue but do not stop later endpoints from being probed.
        plan = doctor_updates.ReachabilityPlan(
            description="API key auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="bad API",
                    url="https://bad.example.com/v1",
                    required=True,
                    route_probe_url="https://bad.example.com/v1/models",
                ),
                doctor_updates.ReachabilityEndpoint(
                    label="ok API",
                    url="https://ok.example.com/v1",
                    required=True,
                    route_probe_url="https://ok.example.com/v1/models",
                ),
            ),
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if url == "https://bad.example.com/v1/models":
                raise ConnectionRefusedError("refused")
            if url == "https://ok.example.com/v1/models":
                return 403
            return 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "one or more required provider endpoints are unreachable over HTTP")
        self.assertIn(
            "bad API route probe: https://bad.example.com/v1/models connect failed (required)",
            check.details,
        )
        self.assertIn(
            "ok API route probe: https://ok.example.com/v1/models route exists (HTTP 403)",
            check.details,
        )
        self.assertEqual(len(check.issues), 1)
        self.assertEqual(
            check.issues[0]["measured"],
            "https://bad.example.com/v1/models connect failed",
        )
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")
        self.assertEqual(
            calls,
            [
                ("https://bad.example.com/v1", "HEAD"),
                ("https://bad.example.com/v1/models", "GET"),
                ("https://ok.example.com/v1", "HEAD"),
                ("https://ok.example.com/v1/models", "GET"),
            ],
        )

    def test_provider_reachability_route_probe_unexpected_status_warns(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_route_probe_url / provider_reachability_check
        # Contract: route probes outside 2xx/401/403/404 warn instead of failing reachability.
        plan = provider_reachability_plan_from_parts(
            mode="API key auth",
            provider_id="openai",
            provider_name="OpenAI",
            provider_base_url="http://127.0.0.1:9876/v1",
        )

        for route_status in (302, 500):
            with self.subTest(route_status=route_status):

                def probe(url: str, method: str) -> int:
                    return route_status if method == "GET" else 200

                check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

                self.assertEqual(check.status, "warn")
                self.assertEqual(check.summary, "provider endpoint checks returned warnings")
                self.assertIn(
                    f"openai API route probe: http://127.0.0.1:9876/v1/models returned HTTP {route_status} (warning)",
                    check.details,
                )
                self.assertEqual(check.issues, ())
                self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")

    def test_provider_reachability_route_warning_allows_later_success(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_reachability_check / provider_reachability_outcome
        # Contract: route warnings remain warnings while later endpoints are still probed successfully.
        plan = doctor_updates.ReachabilityPlan(
            description="API key auth",
            endpoints=(
                doctor_updates.ReachabilityEndpoint(
                    label="warning API",
                    url="https://warning.example.com/v1",
                    required=True,
                    route_probe_url="https://warning.example.com/v1/models",
                ),
                doctor_updates.ReachabilityEndpoint(
                    label="ok API",
                    url="https://ok.example.com/v1",
                    required=True,
                    route_probe_url="https://ok.example.com/v1/models",
                ),
            ),
        )
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if url == "https://warning.example.com/v1/models":
                return 500
            if url == "https://ok.example.com/v1/models":
                return 401
            return 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "provider endpoint checks returned warnings")
        self.assertIn(
            "warning API route probe: https://warning.example.com/v1/models returned HTTP 500 (warning)",
            check.details,
        )
        self.assertIn(
            "ok API route probe: https://ok.example.com/v1/models route exists (HTTP 401)",
            check.details,
        )
        self.assertEqual(check.issues, ())
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")
        self.assertEqual(
            calls,
            [
                ("https://warning.example.com/v1", "HEAD"),
                ("https://warning.example.com/v1/models", "GET"),
                ("https://ok.example.com/v1", "HEAD"),
                ("https://ok.example.com/v1/models", "GET"),
            ],
        )

    def test_doctor_provider_reachability_check_fails_for_missing_models_route(self) -> None:
        plan = provider_reachability_plan_from_parts(
            mode="provider auth",
            provider_id="custom",
            provider_name="Custom",
            provider_base_url="https://example.com/openai",
        )

        def probe(url: str, method: str) -> int:
            return 404 if method == "GET" else 200

        check = doctor_provider_reachability_check(plan=plan, http_status_probe=probe)

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "one or more required provider endpoints are unreachable over HTTP")
        self.assertIn("custom API base URL: https://example.com/openai reachable (HTTP 200)", check.details)
        self.assertIn(
            "custom API route probe: https://example.com/openai/models returned HTTP 404 (required)",
            check.details,
        )
        self.assertEqual(check.remediation, "Check proxy, VPN, firewall, DNS, and custom CA configuration.")

    def test_doctor_fallback_state_check_reports_resolved_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_fallback_state_check(codex_home=codex_home)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "CODEX_HOME was resolved without config")
        self.assertEqual(check.details, (f"CODEX_HOME: {codex_home}",))

    def test_doctor_fallback_state_check_reports_resolution_error(self) -> None:
        check = doctor_fallback_state_check(error="home unavailable")

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "CODEX_HOME could not be resolved")
        self.assertEqual(check.details, ("home unavailable",))

    def test_fallback_state_check_uses_resolver_success_and_error_paths(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: fallback_state_check
        # Contract: CODEX_HOME resolver success reports ok detail; resolver failure reports warning detail.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            ok = doctor_fallback_state_check(resolver=lambda: codex_home)

        def failing_resolver() -> Path:
            raise RuntimeError("home unavailable")

        warning = doctor_fallback_state_check(resolver=failing_resolver)

        self.assertEqual(ok.status, "ok")
        self.assertEqual(ok.summary, "CODEX_HOME was resolved without config")
        self.assertEqual(ok.details, (f"CODEX_HOME: {codex_home}",))
        self.assertEqual(warning.status, "warn")
        self.assertEqual(warning.summary, "CODEX_HOME could not be resolved")
        self.assertEqual(warning.details, ("home unavailable",))

    def test_websocket_probe_warning_matches_rust_shape(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: websocket_probe_warning
        # Contract: warning checks preserve existing details, append the error detail, and use Rust remediation text.
        check = doctor_updates._websocket_probe_warning(
            "Responses WebSocket timed out; HTTPS fallback may still work",
            ["model provider: openai", "wire API: responses"],
            "handshake timed out",
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Responses WebSocket timed out; HTTPS fallback may still work")
        self.assertEqual(
            check.details,
            ("model provider: openai", "wire API: responses", "handshake timed out"),
        )
        self.assertEqual(
            check.remediation,
            "Check proxy, VPN, firewall, DNS, custom CA, and WebSocket policy support.",
        )

    def test_websocket_error_detail_matches_rust_api_error_branches(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: websocket_error_detail
        # Contract: websocket probe errors are classified by ApiError variant before being appended to doctor details.
        self.assertEqual(
            doctor_updates._websocket_error_detail(
                ApiError.transport_error(TransportError.network("dns failed"))
            ),
            "handshake transport error: network error: dns failed",
        )
        self.assertEqual(
            doctor_updates._websocket_error_detail(ApiError.api(401, "bad key")),
            "handshake API error: 401 bad key",
        )
        self.assertEqual(
            doctor_updates._websocket_error_detail(ApiError.stream("bad frame")),
            "handshake stream error: bad frame",
        )
        self.assertEqual(
            doctor_updates._websocket_error_detail(ApiError.quota_exceeded()),
            "handshake error: quota exceeded",
        )

    def test_doctor_websocket_check_reports_disabled_provider(self) -> None:
        check = doctor_websocket_check(
            inputs=WebsocketCheckInputs(
                model_provider_id="local",
                provider_name="Local",
                wire_api="responses",
                supports_websockets=False,
                env={},
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "Responses WebSocket is not enabled for the active provider")
        self.assertIn("model provider: local", check.details)
        self.assertIn("provider name: Local", check.details)
        self.assertIn("supports websockets: false", check.details)
        self.assertIn("proxy env vars: none", check.details)

    def test_doctor_websocket_check_reports_static_supported_provider_with_handshake(self) -> None:
        connect_state: dict[str, object] = {}

        def fake_connect(
            websocket_url: str,
            headers: dict[str, str],
            turn_state: object,
            *,
            timeout: float | None = None,
        ) -> tuple[ResponsesWebsocketMemoryStream, int, bool, str | None, str | None]:
            del turn_state
            connect_state["websocket_url"] = websocket_url
            connect_state["timeout"] = timeout
            connect_state["headers"] = headers
            return (ResponsesWebsocketMemoryStream(), 101, True, "abc123", "gpt-test")

        original_connect = doctor_updates.responses_connect_websocket
        doctor_updates.responses_connect_websocket = fake_connect
        try:
            check = doctor_websocket_check(
                inputs=WebsocketCheckInputs(
                    model_provider_id="openai",
                    provider_name="OpenAI",
                    wire_api="responses",
                    supports_websockets=True,
                    connect_timeout_ms=30000,
                    auth_mode="api_key",
                    endpoint="wss://api.openai.com/v1/responses",
                    env={"HTTPS_PROXY": "http://proxy.example", "OPENAI_API_KEY": "k"},
                )
            )
        finally:
            doctor_updates.responses_connect_websocket = original_connect

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "Responses WebSocket handshake succeeded")
        self.assertIn("connect timeout: 30000 ms", check.details)
        self.assertIn("auth mode: api_key", check.details)
        self.assertIn("endpoint: wss://api.openai.com/v1/responses", check.details)
        self.assertIn("proxy env vars present: HTTPS_PROXY", check.details)
        self.assertIn("handshake result: HTTP 101", check.details)
        self.assertIn("reasoning header: true", check.details)
        self.assertIn("models etag present: true", check.details)
        self.assertIn("server model present: true", check.details)
        self.assertEqual(connect_state["websocket_url"], "wss://api.openai.com/v1/responses")
        self.assertEqual(connect_state["timeout"], 30.0)
        headers = connect_state["headers"]
        self.assertIsInstance(headers, dict)
        self.assertIn("OpenAI-Beta", headers)
        self.assertEqual(headers["OpenAI-Beta"], RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE)
        self.assertEqual(headers["Authorization"], "Bearer k")

    def test_doctor_websocket_check_preserves_endpoint_query_through_codex_api_provider(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: websocket_reachability_check -> Provider::websocket_url_for_path("responses")
        # Contract: doctor delegates websocket URL construction to codex-api Provider, preserving provider query params.
        connect_state: dict[str, object] = {}

        def fake_connect(
            websocket_url: str,
            headers: dict[str, str],
            turn_state: object,
            *,
            timeout: float | None = None,
        ) -> tuple[ResponsesWebsocketMemoryStream, int, bool, str | None, str | None]:
            del headers, turn_state, timeout
            connect_state["websocket_url"] = websocket_url
            return (ResponsesWebsocketMemoryStream(), 101, False, None, None)

        original_connect = doctor_updates.responses_connect_websocket
        doctor_updates.responses_connect_websocket = fake_connect
        try:
            check = doctor_websocket_check(
                inputs=WebsocketCheckInputs(
                    model_provider_id="azure",
                    provider_name="Azure",
                    wire_api="responses",
                    supports_websockets=True,
                    auth_mode="none",
                    endpoint="wss://example.openai.azure.com/openai/responses?api-version=2026-02-06",
                    env={},
                )
            )
        finally:
            doctor_updates.responses_connect_websocket = original_connect

        self.assertEqual(check.status, "ok")
        self.assertIn(
            "endpoint: wss://example.openai.azure.com/openai/responses?api-version=2026-02-06",
            check.details,
        )
        self.assertEqual(
            connect_state["websocket_url"],
            "wss://example.openai.azure.com/openai/responses?api-version=2026-02-06",
        )

    def test_doctor_websocket_check_reports_dns_family_details(self) -> None:
        def fake_connect(
            websocket_url: str,
            headers: dict[str, str],
            turn_state: object,
            *,
            timeout: float | None = None,
        ) -> tuple[ResponsesWebsocketMemoryStream, int, bool, str | None, str | None]:
            del websocket_url, headers, turn_state, timeout
            return (ResponsesWebsocketMemoryStream(), 101, False, None, None)

        original_connect = doctor_updates.responses_connect_websocket
        original_getaddrinfo = socket.getaddrinfo
        doctor_updates.responses_connect_websocket = fake_connect
        socket.getaddrinfo = lambda _host, _port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),
        ]
        try:
            check = doctor_websocket_check(
                inputs=WebsocketCheckInputs(
                    model_provider_id="openai",
                    provider_name="OpenAI",
                    wire_api="responses",
                    supports_websockets=True,
                    auth_mode="none",
                    endpoint="wss://api.openai.com/v1/responses",
                )
            )
        finally:
            doctor_updates.responses_connect_websocket = original_connect
            socket.getaddrinfo = original_getaddrinfo

        self.assertEqual(check.status, "ok")
        self.assertIn("DNS: 1 IPv4, 1 IPv6, first IPv4", check.details)

    def test_dns_address_family_details_matches_rust_empty_and_failure_shapes(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: dns_address_family_details
        # Contract: DNS details report empty successful lookups as first none and lookup failures as a single detail.
        original_getaddrinfo = socket.getaddrinfo
        try:
            socket.getaddrinfo = lambda _host, _port: []
            self.assertEqual(
                doctor_updates._dns_address_family_details("example.com", 443),
                ("DNS: 0 IPv4, 0 IPv6, first none",),
            )

            def failing_getaddrinfo(_host: str, _port: int) -> list[object]:
                raise OSError("lookup boom")

            socket.getaddrinfo = failing_getaddrinfo  # type: ignore[assignment]
            self.assertEqual(
                doctor_updates._dns_address_family_details("example.com", 443),
                ("DNS: lookup failed (lookup boom)",),
            )
        finally:
            socket.getaddrinfo = original_getaddrinfo

    def test_dns_address_family_details_counts_and_first_ipv6(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: dns_address_family_details
        # Contract: DNS details count IPv4/IPv6 addresses and report the first returned address family.
        original_getaddrinfo = socket.getaddrinfo
        try:
            socket.getaddrinfo = lambda _host, _port: [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.2", 443)),
            ]

            self.assertEqual(
                doctor_updates._dns_address_family_details("example.com", 443),
                ("DNS: 2 IPv4, 1 IPv6, first IPv6",),
            )
        finally:
            socket.getaddrinfo = original_getaddrinfo

    def test_doctor_websocket_check_uses_default_connect_timeout_when_unset(self) -> None:
        original_connect = doctor_updates.responses_connect_websocket
        connect_state: dict[str, object] = {}

        def fake_connect(
            websocket_url: str,
            headers: dict[str, str],
            turn_state: object,
            *,
            timeout: float | None = None,
        ) -> tuple[ResponsesWebsocketMemoryStream, int, bool, str | None, str | None]:
            del websocket_url, headers, turn_state
            connect_state["timeout"] = timeout
            return (ResponsesWebsocketMemoryStream(), 101, False, None, None)

        doctor_updates.responses_connect_websocket = fake_connect
        try:
            check = doctor_websocket_check(
                inputs=WebsocketCheckInputs(
                    model_provider_id="openai",
                    provider_name="OpenAI",
                    wire_api="responses",
                    supports_websockets=True,
                    auth_mode="none",
                    connect_timeout_ms=None,
                    endpoint="wss://api.openai.com/v1/responses",
                )
            )
        finally:
            doctor_updates.responses_connect_websocket = original_connect

        self.assertEqual(check.status, "ok")
        self.assertIn("connect timeout: 15000 ms", check.details)
        self.assertIn("timeout", connect_state)
        self.assertEqual(connect_state["timeout"], 15.0)

    def test_doctor_websocket_check_reports_static_supported_provider_with_immediate_close(self) -> None:
        def fake_connect(
            websocket_url: str,
            headers: dict[str, str],
            turn_state: object,
            *,
            timeout: float | None = None,
        ) -> tuple[ResponsesWebsocketMemoryStream, int, bool, str | None, str | None]:
            del websocket_url, headers, turn_state, timeout
            stream = ResponsesWebsocketMemoryStream(
                [ResponsesWebsocketCloseMessage("1008", "policy disallowed")]
            )
            return (stream, 101, False, None, "gpt-test")

        original_connect = doctor_updates.responses_connect_websocket
        doctor_updates.responses_connect_websocket = fake_connect
        try:
            check = doctor_websocket_check(
                inputs=WebsocketCheckInputs(
                    model_provider_id="openai",
                    provider_name="OpenAI",
                    wire_api="responses",
                    supports_websockets=True,
                    auth_mode="none",
                )
            )
        finally:
            doctor_updates.responses_connect_websocket = original_connect

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Responses WebSocket closed immediately after handshake")
        self.assertIn("immediate close code: 1008", check.details)
        self.assertIn("immediate close reason: policy disallowed", check.details)
        self.assertIn("endpoint: wss://api.openai.com/v1/responses", check.details)

    def test_doctor_websocket_check_reports_timeout(self) -> None:
        original_connect = doctor_updates.responses_connect_websocket
        doctor_updates.responses_connect_websocket = (
            lambda *args, **kwargs: (_ for _ in ()).throw(socket.timeout("timed out"))
        )
        try:
            check = doctor_websocket_check(
                inputs=WebsocketCheckInputs(
                    model_provider_id="openai",
                    provider_name="OpenAI",
                    wire_api="responses",
                    supports_websockets=True,
                    connect_timeout_ms=1,
                    auth_mode="none",
                )
            )
        finally:
            doctor_updates.responses_connect_websocket = original_connect

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Responses WebSocket timed out; HTTPS fallback may still work")

    def test_doctor_websocket_check_formats_api_error_details_like_rust(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: websocket_reachability_check / websocket_error_detail
        # Contract: probe_handshake ApiError failures are rendered with Rust websocket_error_detail prefixes.
        original_connect = doctor_updates.responses_connect_websocket
        doctor_updates.responses_connect_websocket = (
            lambda *args, **kwargs: (_ for _ in ()).throw(ApiError.stream("bad websocket frame"))
        )
        try:
            check = doctor_websocket_check(
                inputs=WebsocketCheckInputs(
                    model_provider_id="openai",
                    provider_name="OpenAI",
                    wire_api="responses",
                    supports_websockets=True,
                    auth_mode="none",
                )
            )
        finally:
            doctor_updates.responses_connect_websocket = original_connect

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Responses WebSocket failed; HTTPS fallback may still work")
        self.assertIn("handshake stream error: bad websocket frame", check.details)

    def test_doctor_terminal_title_check_reports_default_project_name(self) -> None:
        check = doctor_terminal_title_check(
            inputs=TerminalTitleCheckInputs(
                configured_items=None,
                cwd=Path("/work/repo"),
                project_root=Path("/work/repo"),
                project_source="git repo root",
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal title default")
        self.assertIn("terminal title source: default", check.details)
        self.assertIn("terminal title items: activity, project-name", check.details)
        self.assertIn("terminal title activity: true", check.details)
        self.assertIn("terminal title project source: git repo root", check.details)
        self.assertIn("terminal title project value: repo", check.details)

    def test_doctor_terminal_title_check_reports_disabled_configuration(self) -> None:
        check = doctor_terminal_title_check(
            inputs=TerminalTitleCheckInputs(configured_items=(), cwd=Path("/work/repo"))
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal title disabled")
        self.assertIn("terminal title items: none", check.details)
        self.assertIn("terminal title activity: false", check.details)
        self.assertFalse(any(detail.startswith("terminal title project ") for detail in check.details))

    def test_display_list_matches_rust_none_and_join_text(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: display_list
        # Contract: empty lists display as "none"; non-empty values join with comma+space.
        self.assertEqual(doctor_updates._display_list([]), "none")
        self.assertEqual(doctor_updates._display_list(["alpha"]), "alpha")
        self.assertEqual(doctor_updates._display_list(["alpha", "beta", "gamma"]), "alpha, beta, gamma")

    def test_doctor_terminal_title_check_reports_project_config_fallback(self) -> None:
        # Rust parity: codex-cli/src/doctor/title.rs terminal_title_reports_project_config_fallback.
        check = doctor_terminal_title_check(
            inputs=TerminalTitleCheckInputs(
                configured_items=("project",),
                cwd=Path("/workspace/project/subdir"),
                project_root=Path("/workspace/project"),
                project_source="project config",
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal title configured")
        self.assertIn("terminal title items: project-name", check.details)
        self.assertIn("terminal title project source: project config", check.details)
        self.assertIn("terminal title project value: project", check.details)

    def test_doctor_terminal_title_check_omits_project_when_not_selected(self) -> None:
        # Rust parity: codex-cli/src/doctor/title.rs terminal_title_omits_project_when_project_item_is_not_selected.
        check = doctor_terminal_title_check(
            inputs=TerminalTitleCheckInputs(
                configured_items=("model",),
                cwd=Path("/workspace/project"),
                project_root=Path("/workspace/project"),
                project_source="project config",
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal title configured")
        self.assertIn("terminal title items: model", check.details)
        self.assertFalse(any(detail.startswith("terminal title project ") for detail in check.details))

    def test_doctor_terminal_title_check_normalizes_item_aliases(self) -> None:
        # Rust parity: codex-cli/src/doctor/title.rs terminal_title_item_id.
        check = doctor_terminal_title_check(
            inputs=TerminalTitleCheckInputs(
                configured_items=(
                    "spinner",
                    "status",
                    "thread",
                    "context-usage",
                    "session-id",
                    "model-name",
                ),
                cwd=Path("/workspace/project"),
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal title configured")
        self.assertIn(
            "terminal title items: activity, run-state, thread-title, context-used, thread-id, model",
            check.details,
        )
        self.assertIn("terminal title activity: true", check.details)

    def test_doctor_terminal_title_check_warns_for_invalid_items(self) -> None:
        check = doctor_terminal_title_check(
            inputs=TerminalTitleCheckInputs(
                configured_items=("project", "spinner", "bogus", "bogus"),
                cwd=Path("/work/abcdefghijklmnopqrstuvwxy"),
            )
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "terminal title configured with invalid items")
        self.assertIn("terminal title items: project-name, activity", check.details)
        self.assertIn('terminal title invalid items: "bogus"', check.details)
        self.assertIn("terminal title project source: cwd", check.details)
        self.assertIn("terminal title project value: abcdefghijklmnopqrstu...", check.details)
        self.assertEqual(check.remediation, "Remove or replace the unknown entries in [tui].terminal_title.")

    def test_doctor_terminal_title_check_warns_when_all_items_invalid(self) -> None:
        # Rust parity: codex-cli/src/doctor/title.rs terminal_title_warns_when_all_configured_items_are_invalid.
        check = doctor_terminal_title_check(
            inputs=TerminalTitleCheckInputs(
                configured_items=("bogus",),
                cwd=Path("/workspace/project"),
            )
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "terminal title configured with invalid items")
        self.assertIn("terminal title items: none", check.details)
        self.assertIn('terminal title invalid items: "bogus"', check.details)
        self.assertFalse(any(detail.startswith("terminal title project ") for detail in check.details))

    def test_doctor_git_check_reports_git_metadata_from_inputs(self) -> None:
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=Path("/usr/bin/git"),
                git_candidates=(Path("/usr/bin/git"), Path("/opt/bin/git")),
                git_version="git version 2.45.0",
                git_exec_path="/usr/libexec/git-core",
                git_build_options="cpu: x86_64",
                repo_root=Path("/repo"),
                git_entry="directory",
                branch="main",
                core_fsmonitor="false",
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "git version 2.45.0")
        self.assertIn("selected git: /usr/bin/git", check.details)
        self.assertIn("PATH git entries: 2", check.details)
        self.assertIn("PATH git #2: /opt/bin/git", check.details)
        self.assertIn("repo detected: true", check.details)
        self.assertIn("git branch: main", check.details)
        self.assertIn("core.fsmonitor: false", check.details)

    def test_doctor_git_check_normalizes_detached_head_branch(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs normalized_branch.
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=Path("/usr/bin/git"),
                git_version="git version 2.45.0",
                branch="HEAD",
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertIn("git branch: detached HEAD", check.details)

    def test_doctor_git_check_omits_empty_branch(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs normalized_branch.
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=Path("/usr/bin/git"),
                git_version="git version 2.45.0",
                branch="",
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertFalse(any(detail.startswith("git branch:") for detail in check.details))

    def test_doctor_git_check_omits_empty_core_fsmonitor(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs core.fsmonitor optional detail filtering.
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=Path("/usr/bin/git"),
                git_version="git version 2.45.0",
                core_fsmonitor="",
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertFalse(any(detail.startswith("core.fsmonitor:") for detail in check.details))

    def test_doctor_git_parse_windows_version_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs parses_git_for_windows_version.
        self.assertEqual(doctor_updates._parse_git_version("git version 2.34.1.windows.1"), (2, 34, 1))
        self.assertEqual(doctor_updates._parse_git_version("git version 2.54.0.windows.1"), (2, 54, 0))

    def test_doctor_git_command_output_text_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs command_output_text.
        self.assertEqual(
            doctor_updates._git_command_output_text("  first line  \n\n second line\n"),
            "first line; second line",
        )
        self.assertIsNone(doctor_updates._git_command_output_text(" \n\t\n"))
        self.assertIsNone(doctor_updates._git_command_output_text("ok\n", success=False))

    def test_doctor_git_entry_summary_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs git_entry_summary.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(doctor_updates._git_entry_summary(root), "missing")

            (root / ".git").mkdir()
            self.assertEqual(doctor_updates._git_entry_summary(root), "directory")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").write_text("gitdir: ../real-git-dir\n", encoding="utf-8")
            self.assertEqual(doctor_updates._git_entry_summary(root), "file -> ../real-git-dir")

    def test_doctor_git_entry_summary_plain_file_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs git_entry_summary.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").write_text("not a gitdir pointer\n", encoding="utf-8")
            self.assertEqual(doctor_updates._git_entry_summary(root), "file")

    def test_doctor_git_check_warns_when_selected_git_cannot_run(self) -> None:
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=Path("/bad/git"),
                git_candidates=(Path("/bad/git"),),
                git_version=None,
            )
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Git executable found but could not be run")
        self.assertEqual(
            check.remediation,
            "Fix the selected Git executable or PATH so Codex can inspect Git metadata.",
        )

    def test_doctor_git_check_warns_for_repo_without_git_executable(self) -> None:
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=None,
                git_candidates=(),
                repo_root=Path("/repo"),
            )
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Git repository detected but git executable was not found")
        self.assertIn("repo root: /repo", check.details)
        self.assertEqual(check.remediation, "Install Git or fix PATH so Codex can inspect repository metadata.")

    def test_doctor_git_check_reports_no_git_and_no_repo_as_ok(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs git_summary/git_check_from_inputs.
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=None,
                git_candidates=(),
                repo_root=None,
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "git executable not found")
        self.assertIn("selected git: not found", check.details)
        self.assertIn("repo detected: false", check.details)
        self.assertIsNone(check.remediation)

    def test_doctor_git_check_warns_for_old_windows_git(self) -> None:
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=Path("C:/Git/bin/git.exe"),
                git_candidates=(Path("C:/Git/bin/git.exe"),),
                git_version="git version 2.34.1.windows.1",
            ),
            is_windows=True,
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "old Git for Windows may corrupt Windows TUI rendering")
        self.assertEqual(
            check.remediation,
            "Update Git for Windows or the bundled Git executable Codex resolves first.",
        )

    def test_doctor_git_check_warns_for_msysgit(self) -> None:
        # Rust parity: codex-cli/src/doctor/git.rs classifies_old_windows_git.
        check = doctor_git_check(
            inputs=GitCheckInputs(
                selected_git=Path("C:/Git/bin/git.exe"),
                git_candidates=(Path("C:/Git/bin/git.exe"),),
                git_version="git version 1.9.5.msysgit.0",
            ),
            is_windows=True,
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "old msysgit installation may corrupt Windows TUI rendering")
        self.assertEqual(
            check.remediation,
            "Update Git for Windows or the bundled Git executable Codex resolves first.",
        )

    def test_doctor_sandbox_check_reports_policy_and_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "codex-linux-sandbox"
            helper.write_text("", encoding="utf-8")

            check = doctor_sandbox_check(
                approval_policy="on-request",
                filesystem_sandbox="workspace-write",
                network_sandbox="false",
                codex_linux_sandbox_helper=helper,
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "sandbox configuration is readable")
        self.assertIn("approval policy: on-request", check.details)
        self.assertIn("filesystem sandbox: workspace-write", check.details)
        self.assertIn("network sandbox: false", check.details)
        self.assertIn(f"codex-linux-sandbox helper: {helper}", check.details)
        self.assertIn("execve wrapper helper: none", check.details)

    def test_doctor_sandbox_check_warns_for_missing_linux_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "missing-codex-linux-sandbox"

            check = doctor_sandbox_check(codex_linux_sandbox_helper=helper)

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Linux sandbox helper path does not exist")
        self.assertIn(f"codex-linux-sandbox helper: {helper}", check.details)

    def test_doctor_sandbox_check_does_not_warn_for_missing_execve_wrapper(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: sandbox_check
        # Contract: only the Linux sandbox helper path is existence-checked; the execve wrapper is informational.
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / "missing-codex-execve-wrapper"

            check = doctor_sandbox_check(execve_wrapper_helper=wrapper)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "sandbox configuration is readable")
        self.assertIn("codex-linux-sandbox helper: none", check.details)
        self.assertIn(f"execve wrapper helper: {wrapper}", check.details)

    def test_doctor_sandbox_check_reads_simple_config_values(self) -> None:
        check = doctor_sandbox_check(
            config={
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "network_sandbox": True,
            }
        )

        self.assertEqual(check.status, "ok")
        self.assertIn("approval policy: never", check.details)
        self.assertIn("filesystem sandbox: read-only", check.details)
        self.assertIn("network sandbox: true", check.details)

    def test_doctor_network_check_reports_proxy_env_absence(self) -> None:
        check = doctor_network_check(env={})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "network-related environment looks readable")
        self.assertEqual(check.details, ("proxy env vars: none",))

    def test_push_proxy_env_details_matches_rust_order_and_empty_filter(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: push_proxy_env_details
        # Contract: proxy env vars are listed in Rust PROXY_ENV_VARS order and empty values are absent.
        details: list[str] = []

        doctor_updates._push_proxy_env_details(
            details,
            {
                "no_proxy": "localhost",
                "HTTP_PROXY": "",
                "HTTPS_PROXY": "https://proxy.example",
                "ALL_PROXY": "socks://proxy.example",
                "http_proxy": "http://lower.example",
            },
        )

        self.assertEqual(
            details,
            ["proxy env vars present: HTTPS_PROXY, ALL_PROXY, http_proxy, no_proxy"],
        )

    def test_doctor_network_check_reports_proxy_env_presence_and_readable_ca_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ca_file = Path(tmp) / "ca.pem"
            ca_file.write_text("x", encoding="utf-8")

            check = doctor_network_check(
                env={"HTTPS_PROXY": "http://proxy.example", "CODEX_CA_CERTIFICATE": str(ca_file)}
            )

        self.assertEqual(check.status, "ok")
        self.assertIn("proxy env vars present: HTTPS_PROXY", check.details)
        self.assertIn(f"CODEX_CA_CERTIFICATE: readable file {ca_file}", check.details)

    def test_doctor_network_check_warns_for_custom_ca_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            check = doctor_network_check(env={"SSL_CERT_FILE": tmp})

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "custom CA env var does not point at a file")
        self.assertIn(f"SSL_CERT_FILE: not a file {Path(tmp)}", check.details)

    def test_doctor_network_check_warns_for_missing_custom_ca_path(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: network_check
        # Contract: custom CA env vars pointing at unreadable paths produce the Rust warning summary.
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-ca.pem"
            check = doctor_network_check(env={"CODEX_CA_CERTIFICATE": str(missing)})

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "custom CA env var points at an unreadable path")
        self.assertEqual(check.details[0], "proxy env vars: none")
        self.assertTrue(any(detail.startswith(f"CODEX_CA_CERTIFICATE: {missing}") for detail in check.details))

    def test_doctor_network_check_warns_for_unreadable_custom_ca_file(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: network_check
        # Contract: custom CA env vars pointing at unreadable files produce the Rust warning summary.
        with tempfile.TemporaryDirectory() as tmp:
            ca_file = Path(tmp) / "ca.pem"
            ca_file.write_text("x", encoding="utf-8")
            original_open = Path.open

            def failing_open(path: Path, *args: object, **kwargs: object) -> object:
                if path == ca_file:
                    raise OSError("permission denied")
                return original_open(path, *args, **kwargs)

            Path.open = failing_open  # type: ignore[assignment]
            try:
                check = doctor_network_check(env={"SSL_CERT_FILE": str(ca_file)})
            finally:
                Path.open = original_open  # type: ignore[assignment]

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "custom CA env var points at an unreadable file")
        self.assertEqual(check.details[0], "proxy env vars: none")
        self.assertIn(f"SSL_CERT_FILE: {ca_file} (permission denied)", check.details)

    def test_doctor_auth_check_fails_when_no_credentials_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "no Codex credentials were found")
        self.assertIn(f"auth file: {codex_home / 'auth.json'}", check.details)
        self.assertEqual(
            check.remediation,
            "Run codex login or provide an API key through a supported auth env var.",
        )

    def test_doctor_auth_check_no_credentials_reports_storage_mode_and_auth_file(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check
        # Contract: no-credential failures retain the pre-collected auth storage mode and auth file details.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "no Codex credentials were found")
        self.assertEqual(
            check.details,
            (
                "auth storage mode: file",
                f"auth file: {codex_home / 'auth.json'}",
            ),
        )
        self.assertEqual(
            check.remediation,
            "Run codex login or provide an API key through a supported auth env var.",
        )

    def test_doctor_auth_check_uses_environment_auth_without_stored_credentials(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check
        # Contract: supported auth env vars are sufficient when auth.json is absent.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_auth_check(codex_home=codex_home, env={"CODEX_ACCESS_TOKEN": "token"})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is provided by environment")
        self.assertIn("auth env vars present: CODEX_ACCESS_TOKEN", check.details)
        self.assertIsNone(check.remediation)

    def test_doctor_auth_check_allows_multiple_env_auth_without_stored_credentials(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check
        # Contract: multiple auth env vars still pass when no stored auth exists; the warning branch is stored-auth-only.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_auth_check(
                codex_home=codex_home,
                env={
                    "OPENAI_API_KEY": "openai",
                    "CODEX_API_KEY": "codex",
                    "CODEX_ACCESS_TOKEN": "token",
                },
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is provided by environment")
        self.assertIn(
            "auth env vars present: OPENAI_API_KEY, CODEX_API_KEY, CODEX_ACCESS_TOKEN",
            check.details,
        )
        self.assertIsNone(check.remediation)

    def test_doctor_auth_check_fails_when_stored_auth_cannot_be_read(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check
        # Contract: unreadable or invalid stored auth fails with only the Rust error detail and auth-storage remediation.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text("{not valid json", encoding="utf-8")

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "stored credentials could not be read")
        self.assertEqual(check.details, ("Invalid auth file format.",))
        self.assertEqual(check.remediation, "Fix auth storage access or run codex login again.")

    def test_doctor_auth_check_reports_environment_auth_and_multiple_env_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "apiKey", "OPENAI_API_KEY": "stored"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(
                codex_home=codex_home,
                env={"OPENAI_API_KEY": "one", "CODEX_API_KEY": "two"},
            )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "auth is configured, but multiple auth env vars are present")
        self.assertIn("auth env vars present: OPENAI_API_KEY, CODEX_API_KEY", check.details)
        self.assertIn("stored auth mode: api_key", check.details)
        self.assertIsNone(check.remediation)

    def test_doctor_auth_check_reports_auth_env_vars_in_rust_order(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check
        # Contract: auth_check reports present auth env vars in Rust's fixed OPENAI/CODEX key/token order.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "apiKey", "OPENAI_API_KEY": "stored"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(
                codex_home=codex_home,
                env={
                    "CODEX_ACCESS_TOKEN": "token",
                    "CODEX_API_KEY": "codex",
                    "OPENAI_API_KEY": "openai",
                },
            )

        self.assertEqual(check.status, "warn")
        self.assertIn(
            "auth env vars present: OPENAI_API_KEY, CODEX_API_KEY, CODEX_ACCESS_TOKEN",
            check.details,
        )

    def test_doctor_auth_check_fails_for_incomplete_stored_chatgpt_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": ""}}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "stored credentials are incomplete")
        self.assertIn("stored auth issue: ChatGPT auth is missing an access token", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing a refresh token", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing refresh metadata", check.details)
        self.assertEqual(check.remediation, "Run codex login again or provide a supported auth env var.")

    def test_doctor_auth_check_warns_when_env_auth_covers_incomplete_stored_auth(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check
        # Contract: incomplete stored credentials are a warning, not a fail, when an auth env var is present.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": ""}}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={"OPENAI_API_KEY": "env-key"})

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "auth is provided by environment, but stored credentials are incomplete")
        self.assertIn("auth env vars present: OPENAI_API_KEY", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing an access token", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing a refresh token", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing refresh metadata", check.details)
        self.assertIsNone(check.remediation)

    def test_doctor_auth_check_prioritizes_incomplete_stored_summary_over_multiple_env_warning(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check
        # Contract: auth_issues choose the warning summary before the multiple-env warning branch.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": ""}}),
                encoding="utf-8",
            )

            check = doctor_auth_check(
                codex_home=codex_home,
                env={"OPENAI_API_KEY": "env-key", "CODEX_API_KEY": "codex-key"},
            )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "auth is provided by environment, but stored credentials are incomplete")
        self.assertIn("auth env vars present: OPENAI_API_KEY, CODEX_API_KEY", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing an access token", check.details)
        self.assertIsNone(check.remediation)

    def test_stored_auth_validation_rejects_missing_api_key(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: stored_auth_validation_rejects_missing_api_key
        # Contract: API-key stored auth requires a stored or environment API key.
        auth = {"auth_mode": "apiKey"}

        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            ["API key auth is missing an API key"],
        )
        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {"OPENAI_API_KEY": "present"}),
            [],
        )

    def test_stored_auth_validation_accepts_codex_api_key_env(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: API-key stored auth accepts CODEX_API_KEY env fallback just like OPENAI_API_KEY.
        auth = {"auth_mode": "apiKey", "OPENAI_API_KEY": "   "}

        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {"CODEX_API_KEY": "present"}),
            [],
        )

    def test_stored_auth_mode_infers_api_key_from_empty_stored_key(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_mode_value / stored_auth_issues
        # Contract: a present stored OPENAI_API_KEY field selects API-key mode even when the value is empty.
        auth = {"OPENAI_API_KEY": ""}

        self.assertEqual(doctor_updates._stored_auth_mode(auth), "api_key")
        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            ["API key auth is missing an API key"],
        )

    def test_doctor_auth_check_reports_empty_stored_api_key_as_present(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value
        # Contract: stored API key detail reflects field presence, not whether the key is non-empty.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": ""}), encoding="utf-8")

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "stored credentials are incomplete")
        self.assertIn("stored auth mode: api_key", check.details)
        self.assertIn("stored API key: true", check.details)
        self.assertIn("stored auth issue: API key auth is missing an API key", check.details)

    def test_doctor_auth_check_accepts_codex_api_key_env_for_blank_stored_api_key(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_issues
        # Contract: CODEX_API_KEY env auth satisfies API-key stored auth even when the stored OPENAI_API_KEY is blank.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "apiKey", "OPENAI_API_KEY": "   "}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={"CODEX_API_KEY": "sk-codex"})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is configured")
        self.assertIn("auth env vars present: CODEX_API_KEY", check.details)
        self.assertIn("stored auth mode: api_key", check.details)
        self.assertIn("stored API key: true", check.details)
        self.assertFalse(any(detail.startswith("stored auth issue:") for detail in check.details))
        self.assertIsNone(check.remediation)

    def test_doctor_auth_check_accepts_openai_api_key_env_for_missing_stored_api_key(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_issues
        # Contract: OPENAI_API_KEY env auth satisfies API-key stored auth when the stored key field is absent.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "apiKey"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={"OPENAI_API_KEY": "sk-env"})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is configured")
        self.assertIn("auth env vars present: OPENAI_API_KEY", check.details)
        self.assertIn("stored auth mode: api_key", check.details)
        self.assertIn("stored API key: false", check.details)
        self.assertFalse(any(detail.startswith("stored auth issue:") for detail in check.details))
        self.assertIsNone(check.remediation)

    def test_doctor_auth_check_accepts_complete_api_key_auth(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value / stored_auth_issues
        # Contract: complete API-key auth is reported as configured stored credentials.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-stored"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is configured")
        self.assertIn("stored auth mode: api_key", check.details)
        self.assertIn("stored API key: true", check.details)
        self.assertFalse(any(detail.startswith("stored auth issue:") for detail in check.details))

    def test_stored_auth_mode_prefers_explicit_auth_mode_over_stored_key_field(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_mode_value / stored_auth_issues
        # Contract: an explicit auth_mode is used before inferring API-key mode from the stored key field.
        auth = {"auth_mode": "chatgpt", "OPENAI_API_KEY": "sk-stored"}

        self.assertEqual(doctor_updates._stored_auth_mode(auth), "chatgpt")
        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            [
                "ChatGPT auth is missing token data",
                "ChatGPT auth is missing refresh metadata",
            ],
        )

    def test_doctor_auth_check_prefers_explicit_chatgpt_mode_over_stored_api_key_field(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value / stored_auth_issues
        # Contract: explicit chatgpt auth_mode wins over a present stored OPENAI_API_KEY field.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgpt", "OPENAI_API_KEY": "sk-stored"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "stored credentials are incomplete")
        self.assertIn("stored auth mode: chatgpt", check.details)
        self.assertIn("stored API key: true", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing token data", check.details)
        self.assertIn("stored auth issue: ChatGPT auth is missing refresh metadata", check.details)

    def test_stored_auth_validation_rejects_missing_chatgpt_tokens(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: stored_auth_validation_rejects_missing_chatgpt_tokens
        # Contract: default ChatGPT auth requires token data and refresh metadata.
        auth: dict[str, object] = {}

        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            [
                "ChatGPT auth is missing token data",
                "ChatGPT auth is missing refresh metadata",
            ],
        )

    def test_stored_auth_validation_rejects_blank_chatgpt_refresh_token(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: ChatGPT auth trims refresh_token and reports refresh metadata independently.
        auth = {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": "access", "refresh_token": "  "},
        }

        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            [
                "ChatGPT auth is missing a refresh token",
                "ChatGPT auth is missing refresh metadata",
            ],
        )

    def test_stored_auth_validation_rejects_blank_chatgpt_access_token(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: ChatGPT auth trims access_token and reports it independently from refresh metadata.
        auth = {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": "  ", "refresh_token": "refresh"},
            "last_refresh": "2026-06-16T00:00:00Z",
        }

        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            ["ChatGPT auth is missing an access token"],
        )

    def test_doctor_auth_check_accepts_complete_chatgpt_auth(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value / stored_auth_issues
        # Contract: complete ChatGPT auth is reported as configured stored credentials.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {
                            "access_token": "access",
                            "refresh_token": "refresh",
                        },
                        "last_refresh": "2026-06-16T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is configured")
        self.assertIn("stored auth mode: chatgpt", check.details)
        self.assertIn("stored ChatGPT tokens: true", check.details)
        self.assertFalse(any(detail.startswith("stored auth issue:") for detail in check.details))

    def test_doctor_auth_check_prefers_explicit_external_chatgpt_mode_over_stored_api_key_field(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value / stored_auth_issues
        # Contract: explicit chatgptAuthTokens auth_mode wins over a present stored OPENAI_API_KEY field.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgptAuthTokens", "OPENAI_API_KEY": "sk-stored"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "stored credentials are incomplete")
        self.assertIn("stored auth mode: chatgpt_auth_tokens", check.details)
        self.assertIn("stored API key: true", check.details)
        self.assertIn("stored auth issue: external ChatGPT auth is missing token data", check.details)
        self.assertIn("stored auth issue: external ChatGPT auth is missing refresh metadata", check.details)

    def test_stored_auth_validation_accepts_external_id_token_account_id(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: external ChatGPT auth accepts either tokens.account_id or id_token.chatgpt_account_id.
        auth = {
            "auth_mode": "chatgptAuthTokens",
            "tokens": {
                "access_token": "access",
                "id_token": {"chatgpt_account_id": "account-from-id-token"},
            },
            "last_refresh": "2026-06-16T00:00:00Z",
        }
        missing_account_auth = {
            "auth_mode": "chatgptAuthTokens",
            "tokens": {"access_token": "access", "id_token": {}},
            "last_refresh": "2026-06-16T00:00:00Z",
        }

        self.assertEqual(doctor_updates._stored_auth_issues(auth, {}), [])
        self.assertEqual(
            doctor_updates._stored_auth_issues(missing_account_auth, {}),
            ["external ChatGPT auth is missing a ChatGPT account id"],
        )

    def test_stored_auth_validation_accepts_external_top_level_account_id(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: external ChatGPT auth accepts tokens.account_id without requiring id_token account metadata.
        auth = {
            "auth_mode": "chatgptAuthTokens",
            "tokens": {
                "access_token": "access",
                "account_id": "account-from-token",
                "id_token": {},
            },
            "last_refresh": "2026-06-16T00:00:00Z",
        }
        missing_refresh_auth = {
            "auth_mode": "chatgptAuthTokens",
            "tokens": {
                "access_token": "access",
                "account_id": "account-from-token",
                "id_token": {},
            },
        }

        self.assertEqual(doctor_updates._stored_auth_issues(auth, {}), [])
        self.assertEqual(
            doctor_updates._stored_auth_issues(missing_refresh_auth, {}),
            ["external ChatGPT auth is missing refresh metadata"],
        )

    def test_stored_auth_validation_rejects_external_blank_access_token(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: external ChatGPT auth trims access_token before deciding whether it is present.
        auth = {
            "auth_mode": "chatgptAuthTokens",
            "tokens": {
                "access_token": "   ",
                "account_id": "account-from-token",
                "id_token": {},
            },
            "last_refresh": "2026-06-16T00:00:00Z",
        }

        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            ["external ChatGPT auth is missing an access token"],
        )

    def test_stored_auth_validation_rejects_external_missing_token_data(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: external ChatGPT auth without token data still checks refresh metadata independently.
        auth = {"auth_mode": "chatgptAuthTokens"}

        self.assertEqual(
            doctor_updates._stored_auth_issues(auth, {}),
            [
                "external ChatGPT auth is missing token data",
                "external ChatGPT auth is missing refresh metadata",
            ],
        )

    def test_doctor_auth_check_accepts_complete_external_chatgpt_auth_tokens(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value / stored_auth_issues
        # Contract: complete external ChatGPT auth tokens are reported as configured stored credentials.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgptAuthTokens",
                        "tokens": {
                            "access_token": "access",
                            "account_id": "account-from-token",
                            "id_token": {},
                        },
                        "last_refresh": "2026-06-16T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is configured")
        self.assertIn("stored auth mode: chatgpt_auth_tokens", check.details)
        self.assertIn("stored ChatGPT tokens: true", check.details)
        self.assertFalse(any(detail.startswith("stored auth issue:") for detail in check.details))

    def test_stored_auth_validation_rejects_missing_agent_identity_token(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: stored_auth_issues
        # Contract: agent identity auth requires a non-empty, non-whitespace agent identity token.
        self.assertEqual(
            doctor_updates._stored_auth_issues({"auth_mode": "agentIdentity"}, {}),
            ["agent identity auth is missing an agent identity token"],
        )
        self.assertEqual(
            doctor_updates._stored_auth_issues({"auth_mode": "agentIdentity", "agent_identity": "   "}, {}),
            ["agent identity auth is missing an agent identity token"],
        )
        self.assertEqual(
            doctor_updates._stored_auth_issues({"auth_mode": "agentIdentity", "agent_identity": "token"}, {}),
            [],
        )

    def test_doctor_auth_check_reports_blank_agent_identity_as_present(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_issues
        # Contract: stored agent identity detail reflects field presence, not whether the token is non-empty.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "agentIdentity", "agent_identity": "   "}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "stored credentials are incomplete")
        self.assertIn("stored auth mode: agent_identity", check.details)
        self.assertIn("stored agent identity: true", check.details)
        self.assertIn(
            "stored auth issue: agent identity auth is missing an agent identity token",
            check.details,
        )

    def test_doctor_auth_check_accepts_complete_agent_identity_auth(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value / stored_auth_issues
        # Contract: complete agent identity auth is reported as configured stored credentials.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "agentIdentity", "agent_identity": "agent-token"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is configured")
        self.assertIn("stored auth mode: agent_identity", check.details)
        self.assertIn("stored agent identity: true", check.details)
        self.assertFalse(any(detail.startswith("stored auth issue:") for detail in check.details))

    def test_doctor_auth_check_prefers_explicit_agent_identity_mode_over_stored_api_key_field(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / stored_auth_mode_value / stored_auth_issues
        # Contract: explicit agentIdentity auth_mode wins over a present stored OPENAI_API_KEY field.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "agentIdentity", "OPENAI_API_KEY": "sk-stored"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(codex_home=codex_home, env={})

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "stored credentials are incomplete")
        self.assertIn("stored auth mode: agent_identity", check.details)
        self.assertIn("stored API key: true", check.details)
        self.assertIn("stored agent identity: false", check.details)
        self.assertIn(
            "stored auth issue: agent identity auth is missing an agent identity token",
            check.details,
        )

    def test_doctor_auth_check_handles_provider_specific_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            ok = doctor_auth_check(
                codex_home=codex_home,
                provider_requires_openai_auth=False,
                provider_env_key="CUSTOM_API_KEY",
                env={"CUSTOM_API_KEY": "present"},
            )
            missing = doctor_auth_check(
                codex_home=codex_home,
                provider_requires_openai_auth=False,
                provider_env_key="CUSTOM_API_KEY",
                provider_env_key_instructions="Set CUSTOM_API_KEY first.",
                env={},
            )

        self.assertEqual(ok.status, "ok")
        self.assertEqual(ok.summary, "auth is provided by the active model provider")
        self.assertIn("provider auth env var: CUSTOM_API_KEY (present)", ok.details)
        self.assertEqual(missing.status, "fail")
        self.assertEqual(missing.summary, "active model provider auth env var is missing")
        self.assertEqual(missing.remediation, "Set CUSTOM_API_KEY first.")

    def test_doctor_auth_check_provider_specific_preserves_auth_env_details(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / provider_specific_auth_check
        # Contract: provider-specific auth checks preserve auth env var details collected before the short-circuit.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_auth_check(
                codex_home=codex_home,
                provider_requires_openai_auth=False,
                provider_env_key="CUSTOM_API_KEY",
                env={"OPENAI_API_KEY": "sk-env", "CUSTOM_API_KEY": "provider"},
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is provided by the active model provider")
        self.assertIn("auth env vars present: OPENAI_API_KEY", check.details)
        self.assertIn("provider auth env var: CUSTOM_API_KEY (present)", check.details)

    def test_doctor_auth_check_allows_non_openai_provider_without_env_key(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / provider_specific_auth_check
        # Contract: auth_check short-circuits before auth.json when the active provider does not require OpenAI auth.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_auth_check(
                codex_home=codex_home,
                provider_requires_openai_auth=False,
                provider_env_key=None,
                env={},
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "OpenAI auth is not required for the active model provider")
        self.assertEqual(
            check.details,
            (
                "auth storage mode: file",
                f"auth file: {codex_home / 'auth.json'}",
                "model provider requires OpenAI auth: false",
            ),
        )
        self.assertIsNone(check.remediation)

    def test_provider_specific_auth_allows_non_openai_provider_without_env_key(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_specific_auth_allows_non_openai_provider_without_env_key
        # Contract: non-OpenAI providers without their own env key still produce an OK provider-specific check.
        check = doctor_updates._provider_specific_auth_check(
            False,
            None,
            None,
            [],
            {},
        )

        self.assertIsNotNone(check)
        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "OpenAI auth is not required for the active model provider")

    def test_provider_specific_auth_uses_present_provider_env_key_and_skips_openai_required(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_specific_auth_check
        # Contract: provider-specific auth only short-circuits when OpenAI auth is not required.
        self.assertIsNone(
            doctor_updates._provider_specific_auth_check(
                True,
                "PROVIDER_API_KEY",
                None,
                ["base detail"],
                {"PROVIDER_API_KEY": "present"},
            )
        )

        check = doctor_updates._provider_specific_auth_check(
            False,
            "PROVIDER_API_KEY",
            None,
            ["base detail"],
            {"PROVIDER_API_KEY": "present"},
        )

        self.assertIsNotNone(check)
        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is provided by the active model provider")
        self.assertEqual(
            check.details,
            (
                "base detail",
                "model provider requires OpenAI auth: false",
                "provider auth env var: PROVIDER_API_KEY (present)",
            ),
        )
        self.assertIsNone(check.remediation)

    def test_provider_specific_auth_fails_when_provider_env_key_is_missing(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: provider_specific_auth_fails_when_provider_env_key_is_missing
        # Contract: missing required provider auth env key produces a failing check with instructions.
        check = doctor_updates._provider_specific_auth_check(
            False,
            "PROVIDER_API_KEY",
            "Set PROVIDER_API_KEY before running Codex.",
            [],
            {},
        )

        self.assertIsNotNone(check)
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "active model provider auth env var is missing")
        self.assertEqual(check.remediation, "Set PROVIDER_API_KEY before running Codex.")

    def test_provider_specific_auth_uses_default_missing_env_remediation(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: provider_specific_auth_check
        # Contract: missing provider env keys use the Rust default remediation when no instructions are configured.
        check = doctor_updates._provider_specific_auth_check(
            False,
            "PROVIDER_API_KEY",
            None,
            ["base detail"],
            {},
        )

        self.assertIsNotNone(check)
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "active model provider auth env var is missing")
        self.assertEqual(
            check.details,
            (
                "base detail",
                "model provider requires OpenAI auth: false",
                "provider auth env var: PROVIDER_API_KEY (missing)",
            ),
        )
        self.assertEqual(check.remediation, "Set PROVIDER_API_KEY for the active model provider.")

    def test_doctor_auth_check_missing_provider_env_uses_default_remediation(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / provider_specific_auth_check
        # Contract: the public auth_check path uses Rust's default remediation when provider env instructions are absent.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_auth_check(
                codex_home=codex_home,
                provider_requires_openai_auth=False,
                provider_env_key="PROVIDER_API_KEY",
                provider_env_key_instructions=None,
                env={},
            )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "active model provider auth env var is missing")
        self.assertEqual(
            check.details,
            (
                "auth storage mode: file",
                f"auth file: {codex_home / 'auth.json'}",
                "model provider requires OpenAI auth: false",
                "provider auth env var: PROVIDER_API_KEY (missing)",
            ),
        )
        self.assertEqual(check.remediation, "Set PROVIDER_API_KEY for the active model provider.")

    def test_doctor_auth_check_requires_openai_auth_ignores_provider_env_key(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: auth_check / provider_specific_auth_check
        # Contract: provider_specific_auth_check returns None when the active provider still requires OpenAI auth.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "auth.json").write_text(
                json.dumps({"auth_mode": "apiKey", "OPENAI_API_KEY": "stored"}),
                encoding="utf-8",
            )

            check = doctor_auth_check(
                codex_home=codex_home,
                provider_requires_openai_auth=True,
                provider_env_key="PROVIDER_API_KEY",
                env={"PROVIDER_API_KEY": "provider"},
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "auth is configured")
        self.assertIn("stored auth mode: api_key", check.details)
        self.assertNotIn("model provider requires OpenAI auth: true", check.details)
        self.assertFalse(any("provider auth env var:" in detail for detail in check.details))

    def test_doctor_config_check_reports_loaded_config_and_toml_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "config.toml").write_text(
                'model = "gpt-5"\nmodel_provider = "openai"\n[features]\nfoo = true\n',
                encoding="utf-8",
            )

            check = doctor_config_check(
                codex_home=codex_home,
                cwd=codex_home / "workspace",
                config={
                    "model": "gpt-5",
                    "model_provider": "openai",
                    "mcp_servers": {"local": {}},
                    "features": {"foo": True, "bar": False},
                },
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "config loaded")
        self.assertIn(f"cwd: {codex_home / 'workspace'}", check.details)
        self.assertIn("model: gpt-5", check.details)
        self.assertIn("model provider: openai", check.details)
        self.assertIn("mcp servers: 1", check.details)
        self.assertIn("feature flags enabled: 1", check.details)
        self.assertIn("enabled feature flags: foo", check.details)
        self.assertIn("feature flag overrides: bar=false, foo=true", check.details)
        self.assertIn("config.toml parse: ok", check.details)

    def test_doctor_config_check_warns_with_startup_warning_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            check = doctor_config_check(
                codex_home=codex_home,
                startup_warnings=("deprecated setting used", "MCP server failed"),
            )

        self.assertEqual(check.status, "warn")
        self.assertIn("config.toml: missing", check.details)
        self.assertIn("startup warnings: 2", check.details)
        self.assertIn("startup warning MCP: 1", check.details)
        self.assertIn("startup warning deprecated: 1", check.details)

    def test_feature_flag_details_reports_legacy_usage(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: feature_flag_details
        # Contract: feature flag details include enabled count/list, overrides, and legacy usage mappings.
        details: list[str] = []

        doctor_updates._push_feature_flag_details(
            details,
            {
                "features": {"beta": False, "alpha": True},
                "legacy_feature_usages": [{"alias": "old-alpha", "feature_key": "alpha"}],
            },
        )

        self.assertEqual(
            details,
            [
                "feature flags enabled: 1",
                "enabled feature flags: alpha",
                "feature flag overrides: alpha=true, beta=false",
                "legacy feature flag: old-alpha -> alpha",
            ],
        )

    def test_config_toml_details_reports_missing_ok_and_parse_errors(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: config_toml_details
        # Contract: config.toml details report path, missing file, parse success, and parse errors.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            details: list[str] = []

            doctor_updates._push_config_toml_details(details, codex_home)
            self.assertEqual(details, [f"config.toml: {codex_home / 'config.toml'}", "config.toml: missing"])

            (codex_home / "config.toml").write_text('model = "gpt-5"\n', encoding="utf-8")
            details = []
            doctor_updates._push_config_toml_details(details, codex_home)
            self.assertEqual(details, [f"config.toml: {codex_home / 'config.toml'}", "config.toml parse: ok"])

            (codex_home / "config.toml").write_text("model = \n", encoding="utf-8")
            details = []
            doctor_updates._push_config_toml_details(details, codex_home)
            self.assertEqual(details[0], f"config.toml: {codex_home / 'config.toml'}")
            self.assertTrue(details[1].startswith("config.toml parse: "))

    def test_terminal_env_names_match_rust_sorted_union(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: terminal_env_names
        # Contract: terminal env names are the sorted, de-duplicated union of terminal env groups.
        names = doctor_updates._terminal_env_names()

        self.assertEqual(names, tuple(sorted(names)))
        self.assertEqual(len(names), len(set(names)))
        for name in (
            "TERM",
            "TERM_PROGRAM",
            "TERM_PROGRAM_VERSION",
            "COLUMNS",
            "LINES",
            "TERMINFO",
            "TERMINFO_DIRS",
            "LC_ALL",
            "LC_CTYPE",
            "LANG",
            "SSH_CONNECTION",
            "VSCODE_IPC_HOOK_CLI",
            "WT_SESSION",
            "TMUX",
        ):
            self.assertIn(name, names)

    def test_collect_env_snapshot_trims_values_and_tracks_presence(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: collect_env_snapshot
        # Contract: present env vars are tracked even when trimmed values are empty.
        values, present = doctor_updates._collect_env_snapshot(
            ("EMPTY", "LANG", "TERM", "UNSET"),
            {"TERM": " xterm-256color ", "LANG": "  ", "EMPTY": ""},
        )

        self.assertEqual(values, {"TERM": "xterm-256color"})
        self.assertEqual(present, {"EMPTY", "LANG", "TERM"})

    def test_push_terminal_env_values_reports_present_without_value(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: push_terminal_env_values
        # Contract: env values render as name/value, present-only vars render as "present", absent vars are omitted.
        details: list[str] = []

        doctor_updates._push_terminal_env_values(
            details,
            {"COLUMNS": "120"},
            {"COLUMNS", "LINES", "NO_COLOR"},
            ("COLUMNS", "LINES", "COLORTERM"),
        )

        self.assertEqual(details, ["COLUMNS: 120", "LINES: present"])

    def test_push_presence_env_values_reports_only_present_names(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: push_presence_env_values
        # Contract: presence-only env rows are emitted in requested order for present names only.
        details: list[str] = []

        doctor_updates._push_presence_env_values(
            details,
            {"WT_SESSION", "SSH_CONNECTION", "TERM"},
            ("SSH_TTY", "SSH_CONNECTION", "WT_SESSION"),
        )

        self.assertEqual(details, ["SSH_CONNECTION: present", "WT_SESSION: present"])

    def test_startup_warning_counts_group_known_sources(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: startup_warning_counts_group_known_sources
        # Contract: startup warnings are counted by known source categories.
        details: list[str] = []

        doctor_updates._push_startup_warning_counts(
            details,
            (
                "Skipped loading 2 skill(s) due to invalid SKILL.md files.",
                "[features].codex_hooks is deprecated. Use [features].hooks instead.",
                "plugin example failed to load",
                "MCP server example failed to start",
            ),
        )

        self.assertEqual(
            details,
            [
                "startup warnings: 4",
                "startup warning skills: 1",
                "startup warning hooks: 1",
                "startup warning plugins: 1",
                "startup warning MCP: 1",
                "startup warning deprecated: 1",
            ],
        )

    def test_config_overrides_from_interactive_preserves_global_options(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: config_overrides_from_interactive_preserves_global_options
        # Contract: doctor config overrides preserve interactive global CLI options and arg0 paths.
        interactive = parse_args(
            [
                "--oss",
                "--local-provider",
                "ollama",
                "--model",
                "llama3.2",
                "--cd",
                "/tmp",
                "--sandbox",
                "danger-full-access",
                "--ask-for-approval",
                "never",
                "--add-dir",
                "/var/tmp",
            ]
        )
        arg0_paths = {
            "codex_self_exe": Path("/bin/codex"),
            "codex_linux_sandbox_exe": Path("/bin/codex-linux-sandbox"),
            "main_execve_wrapper_exe": Path("/bin/codex-execve-wrapper"),
        }

        overrides = doctor_updates.doctor_config_overrides_from_interactive(interactive, arg0_paths)

        self.assertEqual(overrides.model, "llama3.2")
        self.assertEqual(overrides.model_provider, "ollama")
        self.assertEqual(overrides.cwd, Path("/tmp"))
        self.assertIs(overrides.approval_policy, AskForApproval.NEVER)
        self.assertIs(overrides.sandbox_mode, SandboxMode.DANGER_FULL_ACCESS)
        self.assertIs(overrides.show_raw_agent_reasoning, True)
        self.assertEqual(overrides.additional_writable_roots, (Path("/var/tmp"),))
        self.assertEqual(overrides.codex_self_exe, arg0_paths["codex_self_exe"])
        self.assertEqual(overrides.codex_linux_sandbox_exe, arg0_paths["codex_linux_sandbox_exe"])
        self.assertEqual(overrides.main_execve_wrapper_exe, arg0_paths["main_execve_wrapper_exe"])

    def test_load_config_web_search_appends_live_override(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: load_config
        # Contract: doctor load_config appends web_search="live" when interactive web_search is set.
        interactive = parse_args(["--search"])
        self.assertEqual(
            doctor_updates.doctor_cli_overrides_for_load_config(("model=\"gpt-5\"",), interactive),
            ("model=\"gpt-5\"", "web_search=live"),
        )

        without_search = parse_args([])
        self.assertEqual(
            doctor_updates.doctor_cli_overrides_for_load_config(("model=\"gpt-5\"",), without_search),
            ("model=\"gpt-5\"",),
        )

    def test_doctor_state_check_reports_paths_rollouts_and_missing_db_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            log_dir = codex_home / "log"
            log_dir.mkdir()
            sessions = codex_home / "sessions" / "2026"
            sessions.mkdir(parents=True)
            (sessions / "rollout-a.jsonl").write_text("abc", encoding="utf-8")
            (sessions / "notes.txt").write_text("ignored", encoding="utf-8")

            check = doctor_state_check(codex_home=codex_home, log_dir=log_dir, sqlite_home=codex_home)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "state paths and databases are inspectable")
        self.assertIn(f"CODEX_HOME: {codex_home} (dir)", check.details)
        self.assertIn(f"log dir: {log_dir} (dir)", check.details)
        self.assertIn(f"state DB: {codex_home / 'state_5.sqlite'} (missing)", check.details)
        self.assertIn("state DB integrity: skipped (missing)", check.details)
        self.assertIn("active rollout files: 1 files, 3 total bytes, 3 average bytes", check.details)

    def test_path_readiness_reports_dir_file_and_missing(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: path_readiness
        # Contract: path readiness reports directory, file, other, and missing paths with Rust detail text.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "state"
            directory.mkdir()
            file_path = root / "state_5.sqlite"
            file_path.write_text("", encoding="utf-8")
            other_path = root / "state.pipe"
            if hasattr(os, "mkfifo"):
                os.mkfifo(other_path)
            missing = root / "missing.sqlite"
            details: list[str] = []

            doctor_updates._push_path_readiness(details, "CODEX_HOME", directory)
            doctor_updates._push_path_readiness(details, "state DB", file_path)
            if other_path.exists():
                doctor_updates._push_path_readiness(details, "event pipe", other_path)
            doctor_updates._push_path_readiness(details, "log DB", missing)

            expected = [
                f"CODEX_HOME: {directory} (dir)",
                f"state DB: {file_path} (file)",
            ]
            if other_path.exists():
                expected.append(f"event pipe: {other_path} (other)")
            expected.append(f"log DB: {missing} (missing)")

        self.assertEqual(details, expected)

    def test_standalone_release_cache_details_counts_entries(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: standalone_release_cache_details
        # Contract: standalone release cache details count readable entries and skip unreadable/missing dirs.
        with tempfile.TemporaryDirectory() as tmp:
            releases = Path(tmp) / "standalone"
            releases.mkdir()
            (releases / "0.1.0").mkdir()
            (releases / "0.2.0").mkdir()
            (releases / "manifest.json").write_text("{}", encoding="utf-8")
            details: list[str] = []

            doctor_updates._push_standalone_release_cache_details(details, releases)
            doctor_updates._push_standalone_release_cache_details(details, releases / "missing")

        self.assertEqual(details, [f"standalone release cache: 3 entries in {releases}"])

    def test_push_path_detail_reports_path_or_none(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: push_path_detail
        # Contract: optional path details print the path when present and `none` when absent.
        path = Path("codex")
        details: list[str] = []

        doctor_updates._push_optional_path_detail(details, "current executable", path)
        doctor_updates._push_optional_path_detail(details, "execve wrapper helper", None)

        self.assertEqual(
            details,
            [
                f"current executable: {path}",
                "execve wrapper helper: none",
            ],
        )

    def test_push_env_path_detail_reports_path_or_not_set(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: push_env_path_detail
        # Contract: env path details print the env path when set and `not set` when absent.
        details: list[str] = []

        doctor_updates._push_env_path_detail(
            details,
            "managed package root",
            "CODEX_MANAGED_ROOT",
            env={"CODEX_MANAGED_ROOT": "codex-package"},
        )
        doctor_updates._push_env_path_detail(
            details,
            "managed package root",
            "CODEX_MANAGED_ROOT",
            env={},
        )

        self.assertEqual(
            details,
            [
                "managed package root: codex-package",
                "managed package root: not set",
            ],
        )

    def test_env_var_present_rejects_empty_values(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: env_var_present
        # Contract: environment variables are present only when set to a non-empty value.
        env = {"OPENAI_API_KEY": "", "CODEX_API_KEY": "sk-test", "CODEX_ACCESS_TOKEN": "   "}

        self.assertFalse(doctor_updates._env_var_present(env, "OPENAI_API_KEY"))
        self.assertTrue(doctor_updates._env_var_present(env, "CODEX_API_KEY"))
        self.assertTrue(doctor_updates._env_var_present(env, "CODEX_ACCESS_TOKEN"))
        self.assertFalse(doctor_updates._env_var_present(env, "MISSING_API_KEY"))

    def test_is_rollout_file_matches_rust_name_and_extension_predicate(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: is_rollout_file
        # Contract: rollout files require a .jsonl extension and a rollout- filename prefix.
        self.assertTrue(doctor_updates._is_rollout_file(Path("rollout-2026-06-16.jsonl")))
        self.assertFalse(doctor_updates._is_rollout_file(Path("rollout-2026-06-16.json")))
        self.assertFalse(doctor_updates._is_rollout_file(Path("session-2026-06-16.jsonl")))

    def test_collect_rollout_stats_counts_nested_rollout_files(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: collect_rollout_stats_counts_nested_rollout_files
        # Contract: rollout stats recurse nested directories and count only rollout-*.jsonl files.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sessions"
            nested = root / "2026" / "05" / "13"
            nested.mkdir(parents=True)
            (nested / "rollout-2026-05-13T00-00-00-test.jsonl").write_text("12345", encoding="utf-8")
            (nested / "not-a-rollout.jsonl").write_text("ignored", encoding="utf-8")

            stats = doctor_updates._collect_rollout_stats(root)

        self.assertEqual(stats, (1, 5, None))
        details: list[str] = []
        doctor_updates._push_rollout_stats_detail(details, "active rollout files", stats)
        self.assertEqual(details, ["active rollout files: 1 files, 5 total bytes, 5 average bytes"])

    def test_collect_rollout_stats_missing_root_is_empty_success(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: collect_rollout_stats_inner
        # Contract: a missing rollout root is treated as an empty successful scan, not a scan error.
        with tempfile.TemporaryDirectory() as tmp:
            missing_root = Path(tmp) / "missing-sessions"

            stats = doctor_updates._collect_rollout_stats(missing_root)

        self.assertEqual(stats, (0, 0, None))

    def test_collect_rollout_stats_preserves_partial_counts_on_scan_error(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: collect_rollout_stats_inner
        # Contract: scan errors stop traversal after preserving counts accumulated so far.
        class FakeEntry:
            def __init__(self, name: str, size: int = 0, *, error: str | None = None) -> None:
                self.name = name
                self.suffix = Path(name).suffix
                self._size = size
                self._error = error

            def is_dir(self) -> bool:
                if self._error is not None:
                    raise OSError(self._error)
                return False

            def is_file(self) -> bool:
                return True

            def stat(self) -> object:
                return types.SimpleNamespace(st_size=self._size)

        class FakeRoot:
            def iterdir(self) -> list[FakeEntry]:
                return [
                    FakeEntry("rollout-first.jsonl", 5),
                    FakeEntry("rollout-bad.jsonl", error="metadata boom"),
                    FakeEntry("rollout-later.jsonl", 7),
                ]

        stats = doctor_updates._collect_rollout_stats(FakeRoot())  # type: ignore[arg-type]

        self.assertEqual(stats, (1, 5, "metadata boom"))

    def test_collect_rollout_stats_saturates_total_bytes(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: collect_rollout_stats_inner
        # Contract: rollout byte totals saturate at u64::MAX.
        class FakeEntry:
            def __init__(self, name: str, size: int) -> None:
                self.name = name
                self.suffix = Path(name).suffix
                self._size = size

            def is_dir(self) -> bool:
                return False

            def is_file(self) -> bool:
                return True

            def stat(self) -> object:
                return types.SimpleNamespace(st_size=self._size)

        class FakeRoot:
            def iterdir(self) -> list[FakeEntry]:
                return [
                    FakeEntry("rollout-first.jsonl", doctor_updates.U64_MAX - 1),
                    FakeEntry("rollout-second.jsonl", 10),
                ]

        stats = doctor_updates._collect_rollout_stats(FakeRoot())  # type: ignore[arg-type]

        self.assertEqual(stats, (2, doctor_updates.U64_MAX, None))
        details: list[str] = []
        doctor_updates._push_rollout_stats_detail(details, "active rollout files", stats)
        self.assertEqual(
            details,
            [f"active rollout files: 2 files, {doctor_updates.U64_MAX} total bytes, {doctor_updates.U64_MAX // 2} average bytes"],
        )

    def test_push_rollout_stats_detail_reports_error_and_zero_average(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: push_rollout_stats_detail
        # Contract: scan errors are reported directly; zero files yield a zero average.
        details: list[str] = []

        doctor_updates._push_rollout_stats_detail(details, "active rollout files", (0, 0, None))
        doctor_updates._push_rollout_stats_detail(details, "archived rollout files", (0, 0, "permission denied"))

        self.assertEqual(
            details,
            [
                "active rollout files: 0 files, 0 total bytes, 0 average bytes",
                "archived rollout files: scan failed (permission denied)",
            ],
        )

    def test_rollout_stats_details_reports_active_and_archived_roots(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: rollout_stats_details
        # Contract: rollout stats report active sessions and archived sessions separately.
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            active = codex_home / "sessions"
            archived = codex_home / "archived_sessions"
            active.mkdir()
            archived.mkdir()
            (active / "rollout-active.jsonl").write_text("abc", encoding="utf-8")
            (archived / "rollout-archived.jsonl").write_text("12345", encoding="utf-8")
            details: list[str] = []

            doctor_updates._push_rollout_stats_details(details, codex_home)

        self.assertEqual(
            details,
            [
                "active rollout files: 1 files, 3 total bytes, 3 average bytes",
                "archived rollout files: 1 files, 5 total bytes, 5 average bytes",
            ],
        )

    def test_sqlite_integrity_detail_reports_missing_and_ok(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: sqlite_integrity_detail
        # Contract: missing DBs are skipped; valid SQLite DBs report ok without integrity failures.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.sqlite"
            db_path = root / "state.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
                connection.commit()
            finally:
                connection.close()

            details: list[str] = []
            failures: list[str] = []
            doctor_updates._push_sqlite_integrity_detail(details, failures, "state DB", missing)
            doctor_updates._push_sqlite_integrity_detail(details, failures, "log DB", db_path)

        self.assertEqual(details, ["state DB integrity: skipped (missing)", "log DB integrity: ok"])
        self.assertEqual(failures, [])

    def test_sqlite_integrity_detail_reports_non_ok_rows(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: sqlite_integrity_detail
        # Contract: non-ok SQLite integrity rows are joined with `; ` and recorded as failures.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.sqlite"
            db_path.write_text("placeholder", encoding="utf-8")
            original_connect = doctor_updates.sqlite3.connect

            class FakeConnection:
                def execute(self, _query: str) -> list[tuple[str]]:
                    return [("row one",), ("row two",)]

                def close(self) -> None:
                    pass

            try:
                doctor_updates.sqlite3.connect = lambda _path: FakeConnection()  # type: ignore[assignment]
                details: list[str] = []
                failures: list[str] = []
                doctor_updates._push_sqlite_integrity_detail(details, failures, "state DB", db_path)
            finally:
                doctor_updates.sqlite3.connect = original_connect

        self.assertEqual(details, ["state DB integrity: row one; row two"])
        self.assertEqual(failures, ["state DB integrity: row one; row two"])

    def test_sqlite_integrity_detail_reports_check_errors(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: sqlite_integrity_detail
        # Contract: SQLite integrity check errors are recorded as details and failures.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.sqlite"
            db_path.write_text("placeholder", encoding="utf-8")
            original_connect = doctor_updates.sqlite3.connect
            try:
                doctor_updates.sqlite3.connect = lambda _path: (_ for _ in ()).throw(sqlite3.OperationalError("db locked"))  # type: ignore[assignment]
                details: list[str] = []
                failures: list[str] = []
                doctor_updates._push_sqlite_integrity_detail(details, failures, "state DB", db_path)
            finally:
                doctor_updates.sqlite3.connect = original_connect

        self.assertEqual(details, ["state DB integrity: db locked"])
        self.assertEqual(failures, ["state DB integrity: db locked"])

    def test_http_probe_treats_http_status_as_reachable(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: http_probe_treats_http_status_as_reachable
        # Contract: HTTP error statuses still return a probe status instead of transport failure.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            host, port = listener.getsockname()

            def respond_once() -> None:
                conn, _addr = listener.accept()
                with conn:
                    conn.recv(1024)
                    conn.sendall(
                        b"HTTP/1.1 405 Method Not Allowed\r\n"
                        b"Content-Length: 0\r\n"
                        b"Connection: close\r\n\r\n"
                    )

            server = threading.Thread(target=respond_once)
            server.start()
            status = doctor_updates._default_http_status_probe(f"http://{host}:{port}/mcp", "HEAD")
            server.join(timeout=5)

        self.assertEqual(status, 405)
        self.assertFalse(server.is_alive())

    def test_mcp_http_probe_falls_back_to_get_when_head_times_out(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: mcp_http_probe_falls_back_to_get_when_head_times_out
        # Contract: MCP HTTP probing falls back to GET when the HEAD probe fails.
        for get_status in (200, 405, 500):
            with self.subTest(get_status=get_status):
                calls: list[tuple[str, str]] = []

                def probe(url: str, method: str) -> int:
                    calls.append((url, method))
                    if method == "HEAD":
                        raise TimeoutError("request timed out")
                    return get_status

                status = doctor_updates._mcp_http_probe("http://127.0.0.1:9876/mcp", probe)

                self.assertEqual(status, get_status)
                self.assertEqual(
                    calls,
                    [
                        ("http://127.0.0.1:9876/mcp", "HEAD"),
                        ("http://127.0.0.1:9876/mcp", "GET"),
                    ],
                )

    def test_mcp_http_probe_head_success_skips_get(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: mcp_http_probe_url_with_timeout
        # Contract: successful HEAD probes return immediately and do not issue the GET fallback.
        calls: list[tuple[str, str]] = []

        def probe(url: str, method: str) -> int:
            calls.append((url, method))
            if method == "GET":
                raise AssertionError("GET fallback should not run after HEAD succeeds")
            return 405

        status = doctor_updates._mcp_http_probe("http://127.0.0.1:9876/mcp", probe)

        self.assertEqual(status, 405)
        self.assertEqual(calls, [("http://127.0.0.1:9876/mcp", "HEAD")])

    def test_mcp_http_probe_reports_head_and_get_failures(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: mcp_http_probe_url_with_timeout
        # Contract: MCP HTTP probe reports both HEAD and GET errors when both attempts fail.
        cases = (
            (TimeoutError(), ConnectionRefusedError("refused"), "HEAD request timed out; GET connect failed"),
            (ValueError("bad url"), RuntimeError("tls handshake failed"), "HEAD request could not be built; GET tls handshake failed"),
        )
        for head_error, get_error, expected_message in cases:
            with self.subTest(expected_message=expected_message):
                calls: list[tuple[str, str]] = []

                def probe(url: str, method: str) -> int:
                    calls.append((url, method))
                    if method == "HEAD":
                        raise head_error
                    raise get_error

                with self.assertRaisesRegex(RuntimeError, re.escape(expected_message)):
                    doctor_updates._mcp_http_probe("http://127.0.0.1:9876/mcp", probe)

                self.assertEqual(
                    calls,
                    [
                        ("http://127.0.0.1:9876/mcp", "HEAD"),
                        ("http://127.0.0.1:9876/mcp", "GET"),
                    ],
                )

    def test_doctor_state_check_fails_for_invalid_sqlite_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            (codex_home / "state_5.sqlite").write_text("not sqlite", encoding="utf-8")

            check = doctor_state_check(codex_home=codex_home)

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "state database integrity check failed")
        self.assertTrue(any(detail.startswith("state DB integrity: ") for detail in check.details))
        self.assertEqual(
            check.remediation,
            "Back up CODEX_HOME, then remove or repair the affected SQLite database.",
        )

    def test_doctor_system_check_reports_os_language_and_locale_env(self) -> None:
        check = doctor_system_check(
            inputs=SystemCheckInputs(
                os="macOS 15.0",
                os_type="macos",
                os_version="15.0",
                os_language="en-US",
                locale_env={"LANG": "en_US.UTF-8"},
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "OS language en-US")
        self.assertEqual(
            list(check.details),
            [
                "os: macOS 15.0",
                "os type: macos",
                "os version: 15.0",
                "os language: en-US",
                "LANG: en_US.UTF-8",
            ],
        )

    def test_doctor_system_check_reports_locale_env_in_rust_order(self) -> None:
        # Rust parity: codex-cli/src/doctor/system.rs LOCALE_ENV_VARS iteration order.
        check = doctor_system_check(
            inputs=SystemCheckInputs(
                os="Linux",
                os_type="linux",
                os_version="6.8",
                os_language="en-US",
                locale_env={
                    "LANG": "en_US.UTF-8",
                    "LC_CTYPE": "C.UTF-8",
                    "LC_ALL": "C",
                },
            )
        )

        positions = [
            check.details.index("LC_ALL: C"),
            check.details.index("LC_CTYPE: C.UTF-8"),
            check.details.index("LANG: en_US.UTF-8"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_doctor_system_check_handles_missing_os_language(self) -> None:
        check = doctor_system_check(
            inputs=SystemCheckInputs(
                os="Linux",
                os_type="linux",
                os_version="unknown",
                os_language=None,
                locale_env={},
            )
        )

        self.assertEqual(check.summary, "OS language unavailable")
        self.assertIn("os language: unavailable", check.details)

    def test_doctor_runtime_check_reports_process_provenance(self) -> None:
        check = doctor_runtime_check(
            current_version="1.2.3",
            current_exe="/usr/local/bin/codex",
            env={"CODEX_BUILD_COMMIT": "abc123"},
            codex_home=None,
        )

        self.assertEqual(check.status, "ok")
        self.assertTrue(check.summary.startswith("running local build on "))
        self.assertIn("version: 1.2.3", check.details)
        self.assertIn("install method: other", check.details)
        self.assertIn("commit: abc123", check.details)
        self.assertIn(f"current executable: {Path('/usr/local/bin/codex')}", check.details)

    def test_doctor_terminal_check_reports_metadata_when_ok(self) -> None:
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "xterm-256color"},
                present_env={"TERM"},
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal metadata was detected")
        self.assertIn("terminal: unknown", check.details)
        self.assertIn("TERM: xterm-256color", check.details)
        self.assertIn("terminal size: 120x40", check.details)
        self.assertIn("color output: enabled", check.details)

    def test_should_enable_color_respects_terminal_inputs(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: should_enable_color_respects_terminal_inputs
        # Contract: color output requires no --no-color/NO_COLOR, non-dumb TERM, TTY stdout, and color support.
        def summary(
            *,
            no_color_flag: bool = False,
            no_color_env: bool = False,
            term: str = "xterm-256color",
            stdout_is_terminal: bool = True,
            stream_supports_color: bool = True,
        ) -> str:
            env = {"TERM": term}
            present_env = {"TERM"}
            if no_color_env:
                present_env.add("NO_COLOR")
            return doctor_updates._color_output_summary(
                TerminalCheckInputs(
                    term=term,
                    stdout_is_terminal=stdout_is_terminal,
                    stream_supports_color=stream_supports_color,
                    no_color_flag=no_color_flag,
                ),
                env,
                present_env,
            )

        self.assertEqual(summary(), "enabled")
        self.assertEqual(summary(no_color_flag=True), "disabled (--no-color)")
        self.assertEqual(summary(no_color_env=True), "disabled (NO_COLOR)")
        self.assertEqual(summary(term="dumb"), "disabled (TERM=dumb)")
        self.assertEqual(summary(stdout_is_terminal=False), "disabled (stdout is not a terminal)")

    def test_color_output_summary_reports_disabled_reasons(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: color_output_summary_reports_disabled_reasons
        # Contract: color output summary reports the first disabled reason in Rust priority order.
        def summary(
            *,
            no_color_flag: bool = False,
            no_color_env: bool = False,
            term: str = "xterm-256color",
            stdout_is_terminal: bool = True,
            stream_supports_color: bool = True,
        ) -> str:
            env = {"TERM": term}
            present_env = {"TERM"}
            if no_color_env:
                present_env.add("NO_COLOR")
            return doctor_updates._color_output_summary(
                TerminalCheckInputs(
                    term=term,
                    stdout_is_terminal=stdout_is_terminal,
                    stream_supports_color=stream_supports_color,
                    no_color_flag=no_color_flag,
                ),
                env,
                present_env,
            )

        self.assertEqual(summary(no_color_flag=True), "disabled (--no-color)")
        self.assertEqual(summary(no_color_env=True), "disabled (NO_COLOR)")
        self.assertEqual(summary(term="dumb"), "disabled (TERM=dumb)")
        self.assertEqual(summary(stdout_is_terminal=False), "disabled (stdout is not a terminal)")
        self.assertEqual(
            summary(stream_supports_color=False),
            "disabled (terminal color support not detected)",
        )

    def test_human_output_options_maps_command_flags(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: human_output_options
        # Contract: doctor human output options derive details/all/ascii/color from command and terminal inputs.
        self.assertEqual(
            doctor_updates._human_output_options_from_flags(
                summary=False,
                all=True,
                ascii=True,
                no_color=False,
                no_color_env=False,
                term="xterm-256color",
                stdout_is_terminal=True,
                stream_supports_color=True,
            ),
            {
                "show_details": True,
                "show_all": True,
                "ascii": True,
                "color_enabled": True,
            },
        )
        self.assertEqual(
            doctor_updates._human_output_options_from_flags(
                summary=True,
                all=False,
                ascii=False,
                no_color=True,
                no_color_env=False,
                term="xterm-256color",
                stdout_is_terminal=True,
                stream_supports_color=True,
            ),
            {
                "show_details": False,
                "show_all": False,
                "ascii": False,
                "color_enabled": False,
            },
        )

    def test_human_output_options_disables_color_for_rust_terminal_guards(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: human_output_options / should_enable_color
        # Contract: NO_COLOR, TERM=dumb, non-tty stdout, and missing color support disable human color output.
        base = {
            "summary": False,
            "all": False,
            "ascii": False,
            "no_color": False,
            "no_color_env": False,
            "term": "xterm-256color",
            "stdout_is_terminal": True,
            "stream_supports_color": True,
        }
        variants = (
            {"no_color_env": True},
            {"term": "dumb"},
            {"stdout_is_terminal": False},
            {"stream_supports_color": False},
        )

        for variant in variants:
            with self.subTest(variant=variant):
                options = doctor_updates._human_output_options_from_flags(**{**base, **variant})
                self.assertFalse(options["color_enabled"])
                self.assertTrue(options["show_details"])
                self.assertFalse(options["show_all"])
                self.assertFalse(options["ascii"])

    def test_doctor_terminal_check_includes_tmux_details_without_changing_status(self) -> None:
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="screen-256color",
                multiplexer="tmux",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "screen-256color"},
                present_env={"TERM"},
                tmux_details=(
                    "tmux client termtype: xterm-256color",
                    "tmux extended-keys: on",
                ),
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal metadata was detected")
        self.assertIn("multiplexer: tmux", check.details)
        self.assertIn("tmux client termtype: xterm-256color", check.details)
        self.assertIn("tmux extended-keys: on", check.details)

    def test_terminal_check_keeps_tmux_probe_failures_non_fatal(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_keeps_tmux_probe_failures_non_fatal
        # Contract: tmux probe failures or missing tmux details do not make terminal diagnostics non-ok.
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="screen-256color",
                multiplexer="tmux",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "screen-256color"},
                present_env={"TERM"},
                tmux_details=(),
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "terminal metadata was detected")

    def test_non_empty_trimmed_matches_rust_helper(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: non_empty_trimmed
        # Contract: trimmed empty strings return None; non-empty strings return trimmed text.
        self.assertIsNone(doctor_updates._non_empty_trimmed(""))
        self.assertIsNone(doctor_updates._non_empty_trimmed(" \r\n\t "))
        self.assertEqual(doctor_updates._non_empty_trimmed("  screen-256color\n"), "screen-256color")

    def test_tmux_probe_helpers_match_rust_commands_and_trim_output(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust items: tmux_display_message, tmux_option_value
        # Contract: tmux probes call Rust argv shapes, trim non-empty stdout, and return None on failures.
        seen: list[tuple[str, tuple[str, ...]]] = []

        def runner(program: str, args: tuple[str, ...]) -> str:
            seen.append((program, args))
            if args[0] == "display-message":
                return " xterm-256color\n"
            if args[0] == "show-options":
                return " on\n"
            raise AssertionError(args)

        self.assertEqual(doctor_updates._tmux_display_message("#{client_termtype}", runner), "xterm-256color")
        self.assertEqual(doctor_updates._tmux_option_value("extended-keys", runner), "on")
        self.assertEqual(
            seen,
            [
                ("tmux", ("display-message", "-p", "#{client_termtype}")),
                ("tmux", ("show-options", "-gqv", "extended-keys")),
            ],
        )

        def failing_runner(_program: str, _args: tuple[str, ...]) -> str:
            raise RuntimeError("tmux failed")

        self.assertIsNone(doctor_updates._tmux_display_message("#{client_termname}", failing_runner))
        self.assertIsNone(doctor_updates._tmux_option_value("xterm-keys", failing_runner))

    def test_tmux_diagnostic_details_matches_rust_order_and_fallbacks(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: tmux_diagnostic_details
        # Contract: display details come first when available; every tmux option emits a row.
        def runner(_program: str, args: tuple[str, ...]) -> str:
            if args == ("display-message", "-p", "#{client_termtype}"):
                return " xterm-256color\n"
            if args == ("display-message", "-p", "#{client_termname}"):
                return "\n"
            if args == ("show-options", "-gqv", "extended-keys"):
                return " on\n"
            return ""

        self.assertEqual(
            doctor_updates._tmux_diagnostic_details(command_runner=runner),
            (
                "tmux client termtype: xterm-256color",
                "tmux extended-keys: on",
                "tmux xterm-keys: unavailable",
                "tmux allow-passthrough: unavailable",
                "tmux set-clipboard: unavailable",
                "tmux focus-events: unavailable",
            ),
        )

    def test_doctor_terminal_check_includes_windows_console_details(self) -> None:
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "xterm-256color"},
                present_env={"TERM"},
                windows_console_details=(
                    "stdout console mode: 0x00000004 (VT processing: true)",
                ),
            )
        )

        self.assertEqual(check.status, "ok")
        self.assertIn("stdout console mode: 0x00000004 (VT processing: true)", check.details)

    def test_terminal_check_includes_windows_console_details(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_includes_windows_console_details
        # Contract: collected Windows console diagnostics are appended to terminal check details.
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "xterm-256color"},
                present_env={"TERM"},
                windows_console_details=(
                    "stdout console mode: 0x00000004 (VT processing: true)",
                ),
            )
        )

        self.assertIn("stdout console mode: 0x00000004 (VT processing: true)", check.details)

    def test_doctor_terminal_check_fails_for_dumb_terminal(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_warns_for_dumb_terminal
        # Contract: TERM=dumb fails terminal diagnostics and suggests using a real TERM value.
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="dumb",
                term="dumb",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "dumb"},
                present_env={"TERM"},
            )
        )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "TERM=dumb - colors and cursor control are disabled")
        self.assertIn("color output: disabled (TERM=dumb)", check.details)
        self.assertEqual(check.remediation, "set TERM to a real value, for example xterm-256color")

    def test_doctor_terminal_check_warns_for_narrow_terminal_and_locale(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_warns_for_narrow_terminal
        # Contract: terminal width below 80 warns and suggests resizing the window.
        narrow = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(79, 24),
                env={"TERM": "xterm-256color"},
                present_env={"TERM"},
            )
        )
        locale_warning = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "xterm-256color", "LANG": "C"},
                present_env={"TERM", "LANG"},
            )
        )

        self.assertEqual(narrow.status, "warn")
        self.assertEqual(narrow.summary, "width 79 cols - output may wrap (recommended >=80)")
        self.assertEqual(narrow.remediation, "resize the window to at least 80 columns")
        self.assertEqual(locale_warning.status, "warn")
        self.assertEqual(locale_warning.summary, "locale is not UTF-8 - unicode glyphs may render incorrectly")
        self.assertIn("effective locale: C", locale_warning.details)
        self.assertEqual(locale_warning.remediation, "export LANG=en_US.UTF-8 or another UTF-8 locale")

    def test_terminal_check_warns_for_declared_narrow_terminal(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_warns_for_declared_narrow_terminal
        # Contract: COLUMNS below 80 warns, is reported in details, and marks the COLUMNS field.
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "xterm-256color", "COLUMNS": "60"},
                present_env={"TERM", "COLUMNS"},
            )
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "COLUMNS=60 - output may wrap (recommended >=80)")
        self.assertIn("COLUMNS: 60", check.details)
        self.assertEqual(check.issues[0]["fields"], ["COLUMNS"])

    def test_terminal_size_issues_match_rust_measured_fields(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: terminal_size_issues
        # Contract: terminal size and COLUMNS/LINES warnings preserve Rust measured text and fields.
        inputs = TerminalCheckInputs(
            terminal="unknown",
            term="xterm-256color",
            stdin_is_terminal=True,
            stdout_is_terminal=True,
            stderr_is_terminal=True,
            stream_supports_color=True,
            terminal_size=(79, 23),
            env={"TERM": "xterm-256color", "COLUMNS": "60", "LINES": "10"},
            present_env={"TERM", "COLUMNS", "LINES"},
        )

        issues = doctor_updates._terminal_size_issues(
            inputs,
            {"TERM": "xterm-256color", "COLUMNS": "60", "LINES": "10"},
        )

        self.assertEqual(
            [(issue["summary"], issue["measured"], issue["fields"]) for issue in issues],
            [
                ("width 79 cols - output may wrap (recommended >=80)", "79 x 23", ["terminal size"]),
                ("height 23 rows - content may scroll off (recommended >=24)", "79 x 23", ["terminal size"]),
                ("COLUMNS=60 - output may wrap (recommended >=80)", "60 columns", ["COLUMNS"]),
                ("LINES=10 - content may scroll off (recommended >=24)", "10 rows", ["LINES"]),
            ],
        )

    def test_terminal_check_warns_for_non_utf8_locale(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_warns_for_non_utf8_locale
        # Contract: non-UTF8 locale warns, reports the effective locale, and suggests a UTF-8 LANG.
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "xterm-256color", "LANG": "C"},
                present_env={"TERM", "LANG"},
            )
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "locale is not UTF-8 - unicode glyphs may render incorrectly")
        self.assertIn("effective locale: C", check.details)
        self.assertEqual(check.issues[0]["remedy"], "export LANG=en_US.UTF-8 or another UTF-8 locale")
        self.assertEqual(check.issues[0]["fields"], ["effective locale"])

    def test_terminal_check_warns_for_unreadable_terminfo_path(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_warns_for_unreadable_terminfo_path
        # Contract: missing TERMINFO fails, reports a missing path detail, and suggests checking TERMINFO.
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-terminfo"
            check = doctor_terminal_check(
                inputs=TerminalCheckInputs(
                    terminal="unknown",
                    term="xterm-256color",
                    stdin_is_terminal=True,
                    stdout_is_terminal=True,
                    stderr_is_terminal=True,
                    stream_supports_color=True,
                    terminal_size=(120, 40),
                    env={"TERM": "xterm-256color", "TERMINFO": str(missing)},
                    present_env={"TERM", "TERMINFO"},
                )
            )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "TERMINFO unreadable - terminal capabilities are unknown")
        self.assertTrue(
            any(detail.startswith("TERMINFO: ") and detail.endswith(" (missing)") for detail in check.details)
        )
        self.assertEqual(check.issues[0]["remedy"], "check that $TERMINFO points to a readable directory")
        self.assertEqual(check.issues[0]["fields"], ["TERMINFO"])

    def test_push_terminfo_details_matches_rust_presence_and_split_paths(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: push_terminfo_details
        # Contract: TERMINFO has no present-only row; TERMINFO_DIRS does, and path lists skip empty entries.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "terminfo"
            existing.mkdir()
            missing = root / "missing"
            raw_dirs = doctor_updates.os.pathsep.join(("", str(existing), "", str(missing)))

            details: list[str] = []
            warning = doctor_updates._push_terminfo_details(details, {}, {"TERMINFO", "TERMINFO_DIRS"})
            self.assertFalse(warning)
            self.assertEqual(details, ["TERMINFO_DIRS: present"])

            details = []
            warning = doctor_updates._push_terminfo_details(
                details,
                {"TERMINFO_DIRS": raw_dirs},
                {"TERMINFO_DIRS"},
            )

        self.assertTrue(warning)
        self.assertEqual(
            details,
            [
                f"TERMINFO_DIRS entry: {existing} (dir)",
                f"TERMINFO_DIRS entry: {missing} (missing)",
            ],
        )

    def test_terminal_path_readiness_reports_file_dir_and_missing(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: terminal_path_readiness
        # Contract: terminal path readiness returns Rust status text and warning flag.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "terminfo"
            directory.mkdir()
            file_path = root / "xterm-256color"
            file_path.write_text("entry", encoding="utf-8")
            missing = root / "missing"

            self.assertEqual(doctor_updates._terminal_path_readiness(directory), ("dir", False))
            self.assertEqual(doctor_updates._terminal_path_readiness(file_path), ("file", False))
            self.assertEqual(doctor_updates._terminal_path_readiness(missing), ("missing", True))

    def test_read_probe_file_opens_and_reads_one_byte(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: read_probe_file_rejects_unreadable_file
        # Rust item: read_probe_file
        # Contract: read probe succeeds after opening a readable file and propagates open/read errors.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty-cert.pem"
            empty.write_bytes(b"")
            missing = root / "missing-cert.pem"

            self.assertIsNone(doctor_updates._read_probe_file(empty))
            with self.assertRaises(OSError):
                doctor_updates._read_probe_file(missing)

    def test_effective_locale_uses_rust_env_var_order(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: effective_locale
        # Contract: effective locale uses LC_ALL, then LC_CTYPE, then LANG.
        self.assertEqual(
            doctor_updates._effective_locale(
                {
                    "LANG": "en_US.UTF-8",
                    "LC_CTYPE": "C.UTF-8",
                    "LC_ALL": "C",
                }
            ),
            "C",
        )
        self.assertEqual(
            doctor_updates._effective_locale({"LC_CTYPE": "C.UTF-8", "LANG": "en_US.UTF-8"}),
            "C.UTF-8",
        )
        self.assertEqual(doctor_updates._effective_locale({"LANG": "en_US.UTF-8"}), "en_US.UTF-8")
        self.assertIsNone(doctor_updates._effective_locale({}))

    def test_is_non_utf8_locale_matches_rust_substring_detection(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: is_non_utf8_locale
        # Contract: locale text is ASCII-lowercased and accepts either utf-8 or utf8.
        self.assertFalse(doctor_updates._is_non_utf8_locale("en_US.UTF-8"))
        self.assertFalse(doctor_updates._is_non_utf8_locale("C.UTF8"))
        self.assertFalse(doctor_updates._is_non_utf8_locale("UTF-8"))
        self.assertTrue(doctor_updates._is_non_utf8_locale("C"))
        self.assertTrue(doctor_updates._is_non_utf8_locale("en_US.ISO-8859-1"))

    def test_terminal_check_reports_remote_indicators_as_present_only(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: terminal_check_reports_remote_indicators_as_present_only
        # Contract: remote indicator environment variables are reported as present without leaking values.
        check = doctor_terminal_check(
            inputs=TerminalCheckInputs(
                terminal="unknown",
                term="xterm-256color",
                stdin_is_terminal=True,
                stdout_is_terminal=True,
                stderr_is_terminal=True,
                stream_supports_color=True,
                terminal_size=(120, 40),
                env={"TERM": "xterm-256color", "SSH_CONNECTION": "10.0.0.1 1 10.0.0.2 22"},
                present_env={"TERM", "SSH_CONNECTION"},
            )
        )

        self.assertIn("SSH_CONNECTION: present", check.details)
        self.assertFalse(any("10.0.0.1" in detail for detail in check.details))

    def test_doctor_terminal_check_fails_for_missing_terminfo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-terminfo-directory"
            check = doctor_terminal_check(
                inputs=TerminalCheckInputs(
                    terminal="unknown",
                    term="xterm-256color",
                    stdin_is_terminal=True,
                    stdout_is_terminal=True,
                    stderr_is_terminal=True,
                    stream_supports_color=True,
                    terminal_size=(120, 40),
                    env={"TERM": "xterm-256color", "TERMINFO": str(missing)},
                    present_env={"TERM", "TERMINFO"},
                )
            )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "TERMINFO unreadable - terminal capabilities are unknown")
        self.assertIn(f"TERMINFO: {missing} (missing)", check.details)
        self.assertEqual(check.remediation, "check that $TERMINFO points to a readable directory")

    def test_doctor_runtime_check_names_managed_install_methods(self) -> None:
        check = doctor_runtime_check(
            current_version="1.2.3",
            current_exe="/tmp/codex",
            env={"CODEX_MANAGED_BY_NPM": "1"},
            codex_home=None,
        )

        self.assertIn("running npm on ", check.summary)
        self.assertIn("install method: npm", check.details)

    def test_doctor_search_check_verifies_system_rg_version(self) -> None:
        seen: list[tuple[str, tuple[str, ...]]] = []

        def runner(program: str, args: tuple[str, ...]) -> str:
            seen.append((program, args))
            return "ripgrep 14.1.0\nfeatures\n"

        check = doctor_search_check(rg_command="rg", provider="system", command_runner=runner)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "search is OK (system)")
        self.assertIn("search command: rg", check.details)
        self.assertIn("search provider: system", check.details)
        self.assertIn("search command readiness: ripgrep 14.1.0", check.details)
        self.assertEqual(seen, [("rg", ("--version",))])

    def test_doctor_search_check_uses_unknown_version_for_empty_system_rg_output(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor/runtime.rs
        # Rust item: search_check
        # Contract: successful system rg with no stdout line reports "rg version unknown".
        def runner(program: str, args: tuple[str, ...]) -> str:
            self.assertEqual((program, args), ("rg", ("--version",)))
            return "\n\n"

        check = doctor_search_check(rg_command="rg", provider="system", command_runner=runner)

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "search is OK (system)")
        self.assertIn("search command readiness: rg version unknown", check.details)

    def test_doctor_search_check_warns_when_system_rg_cannot_run(self) -> None:
        def runner(_program: str, _args: tuple[str, ...]) -> str:
            raise RuntimeError("not found")

        check = doctor_search_check(rg_command="rg", provider="system", command_runner=runner)

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "search command could not be verified")
        self.assertIn("search command readiness: not found", check.details)
        self.assertEqual(check.remediation, "Install ripgrep or repair the bundled Codex package.")

    def test_doctor_search_check_verifies_bundled_rg_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = Path(tmp) / "rg.exe"
            command.write_text("", encoding="utf-8")

            check = doctor_search_check(rg_command=command, provider="bundled")

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "search is OK (bundled)")
        self.assertIn(f"search command: {command}", check.details)
        self.assertIn("search command readiness: file exists", check.details)

    def test_doctor_search_check_warns_when_bundled_path_is_not_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = Path(tmp) / "rg.exe"
            command.mkdir()

            check = doctor_search_check(rg_command=command, provider="bundled")

        self.assertEqual(check.status, "warn")
        self.assertIn("search command readiness: path is not a file", check.details)

    def test_cached_version_details_for_missing_file(self) -> None:
        path = Path("missing-version.json")

        self.assertEqual(
            cached_version_details(path),
            ["version cache: missing-version.json", "version cache: missing"],
        )

    def test_cached_version_details_for_valid_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version.json"
            path.write_text(
                json.dumps(
                    {
                        "latest_version": "1.2.3",
                        "last_checked_at": "2026-05-30T12:00:00Z",
                        "dismissed_version": "1.2.0",
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                cached_version_details(path),
                [
                    f"version cache: {path}",
                    "cached latest version: 1.2.3",
                    "last checked at: 2026-05-30T12:00:00Z",
                    "dismissed version: 1.2.0",
                ],
            )

    def test_cached_version_details_for_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version.json"
            path.write_text("{", encoding="utf-8")

            details = cached_version_details(path)

        self.assertEqual(details[0], f"version cache: {path}")
        self.assertTrue(details[1].startswith("version cache parse: "))

    def test_cached_version_details_reports_invalid_utf8_as_read_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version.json"
            path.write_bytes(b"\xff")

            details = cached_version_details(path)

        self.assertEqual(details[0], f"version cache: {path}")
        self.assertTrue(details[1].startswith("version cache read: "))

    def test_push_cached_version_details_appends_to_existing_list(self) -> None:
        details = ["existing"]

        push_cached_version_details(details, Path("missing-version.json"))

        self.assertEqual(
            details,
            ["existing", "version cache: missing-version.json", "version cache: missing"],
        )

    def test_version_info_validates_shape(self) -> None:
        with self.assertRaisesRegex(TypeError, "latest_version must be a string"):
            VersionInfo.from_mapping({"latest_version": 123})

    def test_latest_version_details_reports_newer_version(self) -> None:
        self.assertEqual(
            latest_version_details("1.2.4", "1.2.3"),
            ["latest version: 1.2.4", "latest version status: newer version is available"],
        )

    def test_latest_version_details_reports_not_older_for_equal_older_or_unknown(self) -> None:
        self.assertEqual(
            latest_version_details("1.2.3", "1.2.3"),
            ["latest version: 1.2.3", "latest version status: current version is not older"],
        )
        self.assertEqual(
            latest_version_details("1.2.2", "1.2.3"),
            ["latest version: 1.2.2", "latest version status: current version is not older"],
        )
        self.assertEqual(
            latest_version_details("1.2.4-beta.1", "1.2.3"),
            ["latest version: 1.2.4-beta.1", "latest version status: current version is not older"],
        )

    def test_push_latest_version_details_appends_to_existing_list(self) -> None:
        details = ["existing"]

        push_latest_version_details(details, "2.0.0", "1.0.0")

        self.assertEqual(
            details,
            ["existing", "latest version: 2.0.0", "latest version status: newer version is available"],
        )

    def test_latest_version_probe_error_details(self) -> None:
        self.assertEqual(
            latest_version_probe_error_details("network timeout"),
            ["latest version probe: network timeout"],
        )

    def test_push_latest_version_probe_error_details_appends_to_existing_list(self) -> None:
        details = ["existing"]

        push_latest_version_probe_error_details(details, "offline")

        self.assertEqual(details, ["existing", "latest version probe: offline"])

    def test_build_doctor_update_check_combines_local_details_and_latest_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version.json"
            path.write_text(json.dumps({"latest_version": "1.0.0"}), encoding="utf-8")

            check = build_doctor_update_check(
                check_for_update_on_startup=True,
                update_action=None,
                version_file=path,
                current_version="1.0.0",
                latest_version="1.0.1",
            )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "update configuration is locally consistent")
        self.assertEqual(
            list(check.details),
            [
                "check for update on startup: true",
                "update action: manual or unknown",
                f"version cache: {path}",
                "cached latest version: 1.0.0",
                "latest version: 1.0.1",
                "latest version status: newer version is available",
            ],
        )

    def test_build_doctor_update_check_warns_on_latest_probe_error(self) -> None:
        check = build_doctor_update_check(
            check_for_update_on_startup=False,
            update_action=None,
            version_file=Path("missing-version.json"),
            current_version="1.0.0",
            latest_error="offline",
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(
            list(check.details),
            [
                "check for update on startup: false",
                "update action: manual or unknown",
                "version cache: missing-version.json",
                "version cache: missing",
                "latest version probe: offline",
            ],
        )

    def test_build_doctor_update_check_fetches_latest_version_by_default(self) -> None:
        seen: list[UpdateAction | None] = []

        def fake_fetch(update_action: UpdateAction | None) -> str:
            seen.append(update_action)
            return "2.0.0"

        original_fetch = doctor_updates.fetch_latest_version
        doctor_updates.fetch_latest_version = fake_fetch
        try:
            check = build_doctor_update_check(
                check_for_update_on_startup=True,
                update_action=UpdateAction.BREW_UPGRADE,
                version_file=Path("missing-version.json"),
                current_version="1.0.0",
                env={},
            )
        finally:
            doctor_updates.fetch_latest_version = original_fetch

        self.assertEqual(seen, [UpdateAction.BREW_UPGRADE])
        self.assertIn("latest version: 2.0.0", check.details)

    def test_build_doctor_update_check_adds_matching_npm_target(self) -> None:
        package_root = Path("npm-root") / "@openai" / "codex"
        check = build_doctor_update_check(
            check_for_update_on_startup=True,
            update_action=UpdateAction.NPM_GLOBAL_LATEST,
            version_file=Path("missing-version.json"),
            current_version="1.0.0",
            npm_root_check=NpmRootCheck.match(package_root),
            latest_version="1.0.0",
        )

        self.assertEqual(check.status, "ok")
        self.assertIn(f"npm update target: {package_root}", check.details)

    def test_build_doctor_update_check_runs_npm_root_check_when_npm_managed(self) -> None:
        calls: list[tuple[str, tuple[str, ...]]] = []

        def command_runner(command: str, args: tuple[str, ...]) -> str:
            calls.append((command, args))
            return str(Path("npm-root"))

        check = build_doctor_update_check(
            check_for_update_on_startup=True,
            update_action=UpdateAction.NPM_GLOBAL_LATEST,
            version_file=Path("missing-version.json"),
            current_version="1.0.0",
            current_exe="codex",
            env={"CODEX_MANAGED_BY_NPM": "1", "CODEX_MANAGED_PACKAGE_ROOT": str(Path("running-pkg"))},
            command_runner=command_runner,
            latest_version="1.0.0",
        )

        self.assertEqual(calls, [("npm", ("root", "-g"))])
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "update would target a different npm install")

    def test_build_doctor_update_check_fails_on_npm_mismatch_with_remediation(self) -> None:
        running_root = Path("running-pkg")
        npm_package_root = Path("npm-root") / "@openai" / "codex"
        check = build_doctor_update_check(
            check_for_update_on_startup=True,
            update_action=UpdateAction.NPM_GLOBAL_LATEST,
            version_file=Path("missing-version.json"),
            current_version="1.0.0",
            npm_root_check=NpmRootCheck.mismatch(running_root, npm_package_root),
            latest_error="offline",
        )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "update would target a different npm install")
        self.assertIn(f"running package root: {running_root}", check.details)
        self.assertIn(f"npm package root: {npm_package_root}", check.details)
        self.assertIn("latest version probe: offline", check.details)
        self.assertEqual(
            check.remediation,
            f"Fix PATH or npm prefix so the running package root ({running_root}) matches the npm global package root ({npm_package_root}).",
        )

    def test_build_doctor_update_check_warns_on_missing_npm_package_root(self) -> None:
        check = build_doctor_update_check(
            check_for_update_on_startup=True,
            update_action=UpdateAction.NPM_GLOBAL_LATEST,
            version_file=Path("missing-version.json"),
            current_version="1.0.0",
            npm_root_check=NpmRootCheck.missing_package_root(),
            latest_version="1.0.0",
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "npm update target could not be proven")
        self.assertEqual(check.remediation, "Reinstall or update Codex so the JS shim provides CODEX_MANAGED_PACKAGE_ROOT.")

    def test_build_doctor_update_check_warns_on_npm_unavailable(self) -> None:
        check = build_doctor_update_check(
            check_for_update_on_startup=True,
            update_action=UpdateAction.NPM_GLOBAL_LATEST,
            version_file=Path("missing-version.json"),
            current_version="1.0.0",
            npm_root_check=NpmRootCheck.npm_unavailable("npm missing"),
            latest_version="1.0.0",
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "npm update target could not be inspected")
        self.assertIn("npm root -g failed: npm missing", check.details)

    def test_doctor_updates_check_derives_update_action_from_install_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            version_file = Path(tmp) / "version.json"
            check = doctor_updates_check(
                check_for_update_on_startup=True,
                codex_home=tmp,
                current_version="1.0.0",
                current_exe="codex",
                env={"CODEX_MANAGED_BY_BUN": "1"},
                latest_version="1.0.0",
            )

        self.assertEqual(check.status, "ok")
        self.assertIn(f"version cache: {version_file}", check.details)
        self.assertIn("update action: bun install -g @openai/codex", check.details)

    def test_doctor_updates_check_from_config_reads_update_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            disabled = doctor_updates_check_from_config(
                {"check_for_update_on_startup": False},
                codex_home=tmp,
                current_version="1.0.0",
                env={},
                latest_version="1.0.0",
            )
            defaulted = doctor_updates_check_from_config(
                {"check_for_update_on_startup": "nope"},
                codex_home=tmp,
                current_version="1.0.0",
                env={},
                latest_version="1.0.0",
            )

        self.assertIn("check for update on startup: false", disabled.details)
        self.assertIn("check for update on startup: true", defaulted.details)

    def test_doctor_managed_by_npm_ignores_inherited_cargo_binary_env(self) -> None:
        env = {"CODEX_MANAGED_BY_NPM": "1"}

        self.assertTrue(doctor_managed_by_npm("/usr/local/bin/codex", env=env))
        self.assertFalse(doctor_managed_by_npm("/repo/target/debug/codex", env=env))
        self.assertTrue(inherited_managed_env_for_cargo_binary("/repo/target/release/codex", env=env))

    def test_detect_update_action_uses_managed_env_before_path_detection(self) -> None:
        self.assertEqual(
            detect_update_action("/tmp/codex", env={"CODEX_MANAGED_BY_NPM": "1"}, codex_home=None),
            UpdateAction.NPM_GLOBAL_LATEST,
        )
        self.assertEqual(
            detect_update_action("/tmp/codex", env={"CODEX_MANAGED_BY_BUN": "1"}, codex_home=None),
            UpdateAction.BUN_GLOBAL_LATEST,
        )
        self.assertIsNone(
            detect_update_action("/repo/target/debug/codex", env={"CODEX_MANAGED_BY_NPM": "1"}, codex_home=None)
        )

    def test_detect_update_action_detects_standalone_release_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            release_dir = codex_home / "packages" / "standalone" / "releases" / "1.2.3-test"
            release_dir.mkdir(parents=True)
            exe = release_dir / "codex.exe"
            exe.write_text("", encoding="utf-8")

            action = detect_update_action(exe, env={}, codex_home=codex_home)

        expected = UpdateAction.STANDALONE_WINDOWS if __import__("os").name == "nt" else UpdateAction.STANDALONE_UNIX
        self.assertEqual(action, expected)

    def test_detect_update_action_detects_standalone_package_layout_and_brew_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            package_dir = codex_home / "packages" / "standalone" / "releases" / "1.2.3-test"
            bin_dir = package_dir / "bin"
            bin_dir.mkdir(parents=True)
            (package_dir / "codex-package.json").write_text("{}", encoding="utf-8")
            exe = bin_dir / "codex.exe"
            exe.write_text("", encoding="utf-8")

            action = detect_update_action(exe, env={}, codex_home=codex_home)

        expected = UpdateAction.STANDALONE_WINDOWS if __import__("os").name == "nt" else UpdateAction.STANDALONE_UNIX
        self.assertEqual(action, expected)
        self.assertEqual(
            detect_update_action("/opt/homebrew/bin/codex", env={}, codex_home=None, is_macos=True),
            UpdateAction.BREW_UPGRADE,
        )
        self.assertIsNone(detect_update_action("/opt/homebrew/bin/codex", env={}, codex_home=None, is_macos=False))

    def test_describe_install_context_matches_method_and_package_layout_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp)
            bin_dir = package_dir / "bin"
            resources_dir = package_dir / "codex-resources"
            path_dir = package_dir / "codex-path"
            bin_dir.mkdir()
            resources_dir.mkdir()
            path_dir.mkdir()
            (package_dir / "codex-package.json").write_text("{}", encoding="utf-8")
            exe = bin_dir / "codex.exe"
            exe.write_text("", encoding="utf-8")

            description = describe_install_context(exe, env={"CODEX_MANAGED_BY_NPM": "1"}, codex_home=None)

        self.assertEqual(
            description,
            f"npm (package {package_dir.resolve()}, bin {bin_dir.resolve()}, resources {resources_dir.resolve()}, path {path_dir.resolve()})",
        )

    def test_describe_install_context_matches_standalone_release_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp)
            release_dir = codex_home / "packages" / "standalone" / "releases" / "1.2.3-test"
            resources_dir = release_dir / "codex-resources"
            resources_dir.mkdir(parents=True)
            exe = release_dir / "codex.exe"
            exe.write_text("", encoding="utf-8")

            description = describe_install_context(exe, env={}, codex_home=codex_home)

        platform = "windows" if __import__("os").name == "nt" else "unix"
        self.assertEqual(
            description,
            f"standalone ({platform}, release {release_dir.resolve()}, resources {resources_dir.resolve()})",
        )

    def test_display_optional_path_matches_rust_none_text(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: display_optional_path
        # Contract: optional paths display as their path text or the literal "none".
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "codex-resources"

            self.assertEqual(doctor_updates._display_optional_path(path), str(path))
            self.assertEqual(doctor_updates._display_optional_path(None), "none")

    def test_describe_method_with_package_layout_matches_rust_optional_layout(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: describe_method_with_package_layout
        # Contract: absent package layouts display only the method; absent resource/path dirs display as "none".
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "pkg"
            bin_dir = package_dir / "bin"

            self.assertEqual(doctor_updates._describe_method_with_package_layout("npm", None), "npm")
            self.assertEqual(
                doctor_updates._describe_method_with_package_layout(
                    "npm",
                    (package_dir, bin_dir, None, None),
                ),
                f"npm (package {package_dir}, bin {bin_dir}, resources none, path none)",
            )

    def test_doctor_installation_check_reports_core_installation_details(self) -> None:
        check = doctor_installation_check(
            current_exe="/repo/target/debug/codex",
            env={"CODEX_MANAGED_BY_NPM": "1", "CODEX_MANAGED_PACKAGE_ROOT": "pkg-root"},
            codex_home=None,
            path_entries=[],
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "installation looks consistent")
        self.assertIn("install context: other", check.details)
        self.assertIn("ignored inherited package-manager launch env for cargo-built binary", check.details)
        self.assertIn("managed by npm: false", check.details)
        self.assertIn("managed by bun: false", check.details)
        self.assertIn("managed package root: pkg-root", check.details)

    def test_doctor_installation_check_reports_unset_managed_package_root(self) -> None:
        check = doctor_installation_check(
            current_exe="codex",
            env={},
            codex_home=None,
            path_entries=[],
        )

        self.assertIn("managed package root: not set", check.details)

    def test_doctor_installation_check_treats_bun_marker_presence_as_managed(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: installation_check
        # Contract: CODEX_MANAGED_BY_BUN presence, even with an empty value, reports Bun-managed launch.
        check = doctor_installation_check(
            current_exe="codex",
            env={"CODEX_MANAGED_BY_BUN": ""},
            codex_home=None,
            path_entries=[],
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "installation looks consistent")
        self.assertIn("managed by bun: true", check.details)

    def test_codex_path_entries_runs_platform_lookup_and_filters_output(self) -> None:
        seen: list[tuple[str, tuple[str, ...]]] = []

        def runner(program: str, args: tuple[str, ...]) -> str:
            seen.append((program, args))
            return "\n  /first/codex  \n\n/second/codex\n"

        self.assertEqual(codex_path_entries(command_runner=runner), ["/first/codex", "/second/codex"])
        expected = ("where", ("codex",)) if __import__("os").name == "nt" else ("which", ("-a", "codex"))
        self.assertEqual(seen, [expected])

    def test_codex_path_entries_suppresses_lookup_errors(self) -> None:
        def runner(_program: str, _args: tuple[str, ...]) -> str:
            raise RuntimeError("missing")

        self.assertEqual(codex_path_entries(command_runner=runner), [])

    def test_doctor_installation_check_reports_path_entries_like_rust(self) -> None:
        check = doctor_installation_check(
            current_exe="codex",
            env={},
            codex_home=None,
            path_entries=["/first/codex", "/second/codex"],
        )

        self.assertIn("PATH codex entries: 2", check.details)
        self.assertIn("PATH codex #1: /first/codex", check.details)
        self.assertIn("PATH codex #2: /second/codex", check.details)

    def test_doctor_installation_check_handles_npm_root_match(self) -> None:
        package_root = Path("npm-root") / "@openai" / "codex"

        check = doctor_installation_check(
            current_exe="codex",
            env={"CODEX_MANAGED_BY_NPM": "1"},
            codex_home=None,
            path_entries=[],
            npm_root_check=NpmRootCheck.match(package_root),
        )

        self.assertEqual(check.status, "ok")
        self.assertEqual(check.summary, "installation looks consistent")
        self.assertIn(f"npm update target: {package_root}", check.details)

    def test_doctor_installation_check_fails_on_npm_root_mismatch(self) -> None:
        running_root = Path("running-pkg")
        npm_package_root = Path("npm-root") / "@openai" / "codex"

        check = doctor_installation_check(
            current_exe="codex",
            env={"CODEX_MANAGED_BY_NPM": "1"},
            codex_home=None,
            path_entries=[],
            npm_root_check=NpmRootCheck.mismatch(running_root, npm_package_root),
        )

        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "npm install -g @openai/codex would update a different install")
        self.assertIn(f"running package root: {running_root}", check.details)
        self.assertIn(f"npm package root: {npm_package_root}", check.details)
        self.assertEqual(
            check.remediation,
            f"Fix PATH or npm prefix so the running package root ({running_root}) matches the npm global package root ({npm_package_root}).",
        )

    def test_doctor_installation_check_runs_npm_root_check_when_npm_managed(self) -> None:
        calls: list[tuple[str, tuple[str, ...]]] = []

        def command_runner(command: str, args: tuple[str, ...]) -> str:
            calls.append((command, args))
            return str(Path("npm-root"))

        check = doctor_installation_check(
            current_exe="codex",
            env={"CODEX_MANAGED_BY_NPM": "1", "CODEX_MANAGED_PACKAGE_ROOT": str(Path("running-pkg"))},
            codex_home=None,
            path_entries=[],
            command_runner=command_runner,
        )

        self.assertEqual(calls, [("npm", ("root", "-g"))])
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.summary, "npm install -g @openai/codex would update a different install")

    def test_doctor_installation_check_warns_on_missing_or_unavailable_npm_root(self) -> None:
        missing = doctor_installation_check(
            current_exe="codex",
            env={"CODEX_MANAGED_BY_NPM": "1"},
            codex_home=None,
            path_entries=[],
            npm_root_check=NpmRootCheck.missing_package_root(),
        )
        unavailable = doctor_installation_check(
            current_exe="codex",
            env={"CODEX_MANAGED_BY_NPM": "1"},
            codex_home=None,
            path_entries=[],
            npm_root_check=NpmRootCheck.npm_unavailable("npm missing"),
        )

        self.assertEqual(missing.status, "warn")
        self.assertEqual(missing.summary, "npm-managed launch is missing package-root provenance")
        self.assertEqual(missing.remediation, "Reinstall or update Codex so the JS shim provides CODEX_MANAGED_PACKAGE_ROOT.")
        self.assertEqual(unavailable.status, "warn")
        self.assertEqual(unavailable.summary, "npm-managed launch could not inspect npm global root")
        self.assertIn("npm root -g failed: npm missing", unavailable.details)

    def test_doctor_installation_check_hides_single_path_entry_without_details(self) -> None:
        hidden = doctor_installation_check(current_exe="codex", env={}, codex_home=None, path_entries=["/only/codex"])
        shown = doctor_installation_check(
            current_exe="codex",
            env={},
            codex_home=None,
            path_entries=["/only/codex"],
            show_details=True,
        )

        self.assertNotIn("PATH codex #1: /only/codex", hidden.details)
        self.assertIn("PATH codex #1: /only/codex", shown.details)

    def test_npm_global_root_check_compares_managed_package_root(self) -> None:
        package_root = Path("npm-root") / "@openai" / "codex"
        env = {"CODEX_MANAGED_PACKAGE_ROOT": str(package_root)}

        check = npm_global_root_check(env=env, command_runner=lambda _program, _args: "npm-root\n")

        self.assertEqual(check, NpmRootCheck.match(package_root))

    def test_compare_npm_package_roots_detects_match(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: compare_npm_package_roots_detects_match
        # Contract: running package root under npm global root is reported as a match.
        running = Path("/prefix/lib/node_modules/@openai/codex")
        npm_root = Path("/prefix/lib/node_modules")

        self.assertEqual(
            compare_npm_package_roots(running, npm_root),
            NpmRootCheck.match(npm_root / "@openai" / "codex"),
        )

    def test_compare_npm_package_roots_detects_mismatch(self) -> None:
        # Source: rust_test_migrated
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust test: compare_npm_package_roots_detects_mismatch
        # Contract: running package root outside npm global root is reported as a mismatch.
        running = Path("/old/lib/node_modules/@openai/codex")
        npm_root = Path("/new/lib/node_modules")

        self.assertEqual(
            compare_npm_package_roots(running, npm_root),
            NpmRootCheck.mismatch(running, npm_root / "@openai" / "codex"),
        )

    def test_normalize_path_for_compare_matches_rust_canonical_fallback(self) -> None:
        # Source: rust_contract
        # Rust crate: codex-cli
        # Rust module: src/doctor.rs
        # Rust item: normalize_path_for_compare
        # Contract: existing paths canonicalize; missing paths keep input text with backslashes normalized.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "pkg"
            existing.mkdir()
            missing = root / "missing\\nested"

            self.assertEqual(
                doctor_updates.normalize_path_for_compare(existing),
                str(existing.resolve()).replace("\\", "/").lower()
                if doctor_updates.os.name == "nt"
                else str(existing.resolve()).replace("\\", "/"),
            )
            self.assertEqual(
                doctor_updates.normalize_path_for_compare(missing),
                str(missing).replace("\\", "/").lower()
                if doctor_updates.os.name == "nt"
                else str(missing).replace("\\", "/"),
            )

    def test_npm_global_root_check_reports_missing_root_empty_output_and_mismatch(self) -> None:
        self.assertEqual(npm_global_root_check(env={}), NpmRootCheck.missing_package_root())
        self.assertEqual(
            npm_global_root_check(
                env={"CODEX_MANAGED_PACKAGE_ROOT": "/running/pkg"},
                command_runner=lambda _program, _args: "\n",
            ),
            NpmRootCheck.npm_unavailable("empty output from npm root -g"),
        )
        self.assertEqual(
            compare_npm_package_roots("running-pkg", "npm-root"),
            NpmRootCheck.mismatch("running-pkg", Path("npm-root") / "@openai" / "codex"),
        )

    def test_run_command_reports_status_like_rust_without_stderr(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exited with status exit status 7"):
            run_command("python", ("-c", "import sys; sys.exit(7)"))

    def test_fetch_latest_github_release_version_extracts_rust_tag(self) -> None:
        seen: list[str] = []

        def getter(url: str) -> object:
            seen.append(url)
            return {"tag_name": "rust-v1.2.3"}

        self.assertEqual(fetch_latest_github_release_version(json_getter=getter), "1.2.3")
        self.assertEqual(seen, [GITHUB_LATEST_RELEASE_URL])

    def test_fetch_latest_github_release_version_rejects_unexpected_tag(self) -> None:
        with self.assertRaisesRegex(ValueError, "failed to parse latest tag v1.2.3"):
            fetch_latest_github_release_version(json_getter=lambda _url: {"tag_name": "v1.2.3"})

    def test_update_action_label_matches_rust_install_contexts(self) -> None:
        # Rust parity: codex-cli/src/doctor/updates.rs update_action_labels_install_contexts.
        self.assertEqual(update_action_label(UpdateAction.NPM_GLOBAL_LATEST), "npm install -g @openai/codex")
        self.assertEqual(update_action_label(UpdateAction.BUN_GLOBAL_LATEST), "bun install -g @openai/codex")
        self.assertEqual(update_action_label(UpdateAction.BREW_UPGRADE), "brew upgrade --cask codex")
        self.assertEqual(update_action_label(UpdateAction.STANDALONE_UNIX), "standalone installer")
        self.assertEqual(update_action_label(UpdateAction.STANDALONE_WINDOWS), "standalone installer")
        self.assertEqual(update_action_label(None), "manual or unknown")

    def test_http_get_json_uses_rust_curl_command_shape(self) -> None:
        calls: list[tuple[str, tuple[str, ...]]] = []

        def command_runner(command: str, args: tuple[str, ...]) -> str:
            calls.append((command, args))
            return '{"ok": true}'

        self.assertEqual(http_get_json("https://example.test/data.json", command_runner=command_runner), {"ok": True})
        self.assertEqual(calls, [("curl", ("-fsSL", "--max-time", "5", "https://example.test/data.json"))])

    def test_fetch_homebrew_cask_version_reads_version_field(self) -> None:
        seen: list[str] = []

        def getter(url: str) -> object:
            seen.append(url)
            return {"version": "1.2.3"}

        self.assertEqual(fetch_homebrew_cask_version(json_getter=getter), "1.2.3")
        self.assertEqual(seen, [HOMEBREW_CASK_API_URL])

    def test_fetch_latest_version_uses_homebrew_for_brew_action(self) -> None:
        seen: list[str] = []

        def getter(url: str) -> object:
            seen.append(url)
            return {"version": "2.0.0"}

        self.assertEqual(
            fetch_latest_version(UpdateAction.BREW_UPGRADE, json_getter=getter),
            "2.0.0",
        )
        self.assertEqual(seen, [HOMEBREW_CASK_API_URL])

    def test_fetch_latest_version_uses_github_for_other_actions(self) -> None:
        for action in (
            None,
            UpdateAction.NPM_GLOBAL_LATEST,
            UpdateAction.BUN_GLOBAL_LATEST,
            UpdateAction.STANDALONE_UNIX,
            UpdateAction.STANDALONE_WINDOWS,
        ):
            with self.subTest(action=action):
                seen: list[str] = []

                def getter(url: str) -> object:
                    seen.append(url)
                    return {"tag_name": "rust-v3.0.0"}

                self.assertEqual(fetch_latest_version(action, json_getter=getter), "3.0.0")
                self.assertEqual(seen, [GITHUB_LATEST_RELEASE_URL])


if __name__ == "__main__":
    unittest.main()


def test_doctor_output_detail_limits_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs LIST_LIMIT/PATH_LIMIT.
    assert doctor_updates._doctor_detail_list_limit() == 7
    assert doctor_updates._doctor_detail_path_limit() == 48


def test_doctor_output_detail_format_bytes_thresholds_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs format_bytes threshold branches.
    assert doctor_updates._doctor_detail_format_bytes(999) == "999 B"
    assert doctor_updates._doctor_detail_format_bytes(1024) == "1.00 KB"
    assert doctor_updates._doctor_detail_format_bytes(1024 * 1024) == "1.00 MB"
    assert doctor_updates._doctor_detail_format_bytes(1024 * 1024 * 1024) == "1.00 GB"


def test_doctor_output_detail_format_count_grouping_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs format_count comma grouping.
    assert doctor_updates._doctor_detail_format_count(0) == "0"
    assert doctor_updates._doctor_detail_format_count(999) == "999"
    assert doctor_updates._doctor_detail_format_count(1000) == "1,000"
    assert doctor_updates._doctor_detail_format_count(1234567) == "1,234,567"


def test_doctor_output_detail_format_bytes_precision_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs format_bytes uses two decimals.
    assert doctor_updates._doctor_detail_format_bytes(1536) == "1.50 KB"
    assert doctor_updates._doctor_detail_format_bytes(1572864) == "1.50 MB"
    assert doctor_updates._doctor_detail_format_bytes(1610612736) == "1.50 GB"


def test_doctor_output_detail_rollout_summary_rejects_non_numeric_parts() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs rollout_summary parse::<u64>().ok()? failures.
    assert doctor_updates._doctor_detail_rollout_summary(
        "many files, 2702146365 total bytes, 1783594 average bytes"
    ) is None
    assert doctor_updates._doctor_detail_rollout_summary(
        "1515 files, huge total bytes, 1783594 average bytes"
    ) is None
    assert doctor_updates._doctor_detail_rollout_summary(
        "1515 files, 2702146365 total bytes, average average bytes"
    ) is None


def test_doctor_output_detail_rollout_summary_zero_values_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs rollout_summary accepts zero u64 fields.
    assert doctor_updates._doctor_detail_rollout_summary(
        "0 files, 0 total bytes, 0 average bytes"
    ) == "0 files \u00b7 0 B (avg 0 B)"


def test_doctor_output_detail_humanize_timestamp_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs humanize_timestamp.
    assert doctor_updates._doctor_detail_humanize_timestamp("2026-06-16T01:23:45Z") == "2026-06-16 01:23 UTC"
    assert doctor_updates._doctor_detail_humanize_timestamp("2026-06-16T01:23Z") == "2026-06-16 01:23 UTC"
    assert doctor_updates._doctor_detail_humanize_timestamp("2026-06-16T01:23:45") is None
    assert doctor_updates._doctor_detail_humanize_timestamp("shortZ") is None


def test_doctor_output_detail_looks_like_path_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs looks_like_path.
    assert doctor_updates._doctor_detail_looks_like_path("/tmp/codex")
    assert doctor_updates._doctor_detail_looks_like_path("~/codex")
    assert doctor_updates._doctor_detail_looks_like_path("./codex")
    assert doctor_updates._doctor_detail_looks_like_path("../codex")
    assert not doctor_updates._doctor_detail_looks_like_path("codex/path")
    assert not doctor_updates._doctor_detail_looks_like_path("~codex")


def test_doctor_output_detail_middle_truncate_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs middle_truncate.
    assert doctor_updates._doctor_detail_middle_truncate("abcdef", 6) == "abcdef"
    assert doctor_updates._doctor_detail_middle_truncate("abcdefghij", 7) == "abc\u2026hij"
    assert doctor_updates._doctor_detail_middle_truncate("abcdefghij", 8) == "abcd\u2026hij"


def test_doctor_output_detail_home_shortened_path_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs home_shortened_path.
    assert doctor_updates._doctor_detail_home_shortened_path("/home/alice", "/home/alice") == "~"
    assert doctor_updates._doctor_detail_home_shortened_path("/home/alice/project", "/home/alice") == "~/project"
    assert doctor_updates._doctor_detail_home_shortened_path("/home/alice-else/project", "/home/alice") == "/home/alice-else/project"
    assert doctor_updates._doctor_detail_home_shortened_path("/home/alice/project", "") == "/home/alice/project"


def test_doctor_output_detail_shorten_path_prefix_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs shorten_path_prefix.
    assert doctor_updates._doctor_detail_shorten_path_prefix("/home/alice/project", "/home/alice") == "~/project"
    assert doctor_updates._doctor_detail_shorten_path_prefix("/home/alice/project (missing)", "/home/alice") == "~/project (missing)"
    assert doctor_updates._doctor_detail_shorten_path_prefix("/" + "a" * 60, "/home/alice") == "/" + "a" * 23 + "\u2026" + "a" * 23


def test_doctor_output_detail_humanize_value_dispatch_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs humanize_value dispatch order.
    assert doctor_updates._doctor_detail_humanize_value("/home/alice/project", "/home/alice") == "~/project"
    assert doctor_updates._doctor_detail_humanize_value("2026-06-16T01:23:45Z", "/home/alice") == "2026-06-16 01:23 UTC"
    assert doctor_updates._doctor_detail_humanize_value("plain detail", "/home/alice") == "plain detail"


def test_doctor_output_detail_display_label_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs display_label.
    assert doctor_updates._doctor_detail_display_label("codex-linux-sandbox helper") == "linux helper"
    assert doctor_updates._doctor_detail_display_label("optional reachability failed") == "optional reachability"
    assert doctor_updates._doctor_detail_display_label("check for update on startup") == "startup update check"
    assert doctor_updates._doctor_detail_display_label("custom label") == "custom label"


def test_doctor_output_detail_yes_no_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs yes_no.
    assert doctor_updates._doctor_detail_yes_no("true") == "yes"
    assert doctor_updates._doctor_detail_yes_no("false") == "no"
    assert doctor_updates._doctor_detail_yes_no("TRUE") == "no"
    assert doctor_updates._doctor_detail_yes_no("") == "no"


def test_doctor_output_detail_list_items_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs list_items.
    assert doctor_updates._doctor_detail_list_items("none") == []
    assert doctor_updates._doctor_detail_list_items(" false ") == []
    assert doctor_updates._doctor_detail_list_items("alpha, beta,, gamma ") == ["alpha", "beta", "gamma"]
    assert doctor_updates._doctor_detail_list_items("single") == ["single"]


def test_doctor_output_detail_override_names_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs override_names.
    assert doctor_updates._doctor_detail_override_names(["alpha=true", "beta=false", "gamma"]) == ["alpha", "beta", "gamma"]
    assert doctor_updates._doctor_detail_override_names(["name=value=with=equals"]) == ["name"]


def test_doctor_output_detail_rollout_files_and_bytes_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs rollout_files_and_bytes.
    assert doctor_updates._doctor_detail_rollout_files_and_bytes(
        "1515 files, 2702146365 total bytes, 1783594 average bytes"
    ) == (1515, 2702146365)
    assert doctor_updates._doctor_detail_rollout_files_and_bytes(
        "0 files, 0 total bytes, 0 average bytes"
    ) == (0, 0)
    assert doctor_updates._doctor_detail_rollout_files_and_bytes("not rollout stats") is None
    assert doctor_updates._doctor_detail_rollout_files_and_bytes(
        "many files, 2702146365 total bytes, 1783594 average bytes"
    ) is None


def test_doctor_output_detail_parse_detail_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs parsed_details split_once(": ").
    assert doctor_updates._doctor_detail_parse_detail("label: value: extra") == ("label", "value: extra")
    assert doctor_updates._doctor_detail_parse_detail("label:value") == ("", "label:value")
    assert doctor_updates._doctor_detail_parse_detail("freeform note") == ("", "freeform note")


def test_doctor_output_detail_is_falsy_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs is_falsy.
    for value in ("", " false ", "none", "not set", "unknown", "missing", "absent", "no", "-"):
        assert doctor_updates._doctor_detail_is_falsy(value)
    assert not doctor_updates._doctor_detail_is_falsy("true")
    assert not doctor_updates._doctor_detail_is_falsy("present")


def test_doctor_output_detail_numbered_values_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs numbered_values.
    parsed = [
        ("PATH git #2", "/second/git"),
        ("other", "ignored"),
        ("PATH git #10", "/tenth/git"),
        ("PATH codex #1", "/codex"),
    ]
    assert doctor_updates._doctor_detail_numbered_values(parsed, "PATH git #") == ["/second/git", "/tenth/git"]
    assert doctor_updates._doctor_detail_numbered_values(parsed, "missing #") == []


def test_doctor_output_detail_value_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs value.
    parsed = [
        ("model", "gpt-5"),
        ("model provider", "openai"),
        ("model", "later"),
        ("model provider extra", "ignored"),
    ]
    assert doctor_updates._doctor_detail_value(parsed, "model") == "gpt-5"
    assert doctor_updates._doctor_detail_value(parsed, "model provider") == "openai"
    assert doctor_updates._doctor_detail_value(parsed, "model provider extra") == "ignored"
    assert doctor_updates._doctor_detail_value(parsed, "provider") is None


def test_doctor_output_detail_push_list_row_value_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs push_list_row.
    items = [f"item-{index}" for index in range(1, 10)]
    assert doctor_updates._doctor_detail_push_list_row_value(items, show_all=False) == (
        "item-1, item-2, item-3, item-4, item-5, item-6, item-7, \u2026 (full list with --all)"
    )
    assert doctor_updates._doctor_detail_push_list_row_value(items, show_all=True) == (
        "item-1, item-2, item-3, item-4, item-5, item-6, item-7, item-8, item-9"
    )
    assert doctor_updates._doctor_detail_push_list_row_value(["a", "b"], show_all=False) == "a, b"


def test_doctor_output_detail_database_row_value_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs push_database_row.
    assert doctor_updates._doctor_detail_database_row_value("/tmp/state.db") == "/tmp/state.db"
    assert doctor_updates._doctor_detail_database_row_value("/tmp/state.db", "ok") == "/tmp/state.db \u00b7 integrity ok"


def test_doctor_output_detail_feature_flags_summary_value_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs push_feature_flags summary row.
    assert doctor_updates._doctor_detail_feature_flags_summary_value(
        "3", "alpha=true, beta=false", show_all=False
    ) == "3 enabled \u00b7 2 overridden (full list with --all)"
    assert doctor_updates._doctor_detail_feature_flags_summary_value(
        "3", "alpha=true, beta=false", show_all=True
    ) == "3 enabled \u00b7 2 overridden"
    assert doctor_updates._doctor_detail_feature_flags_summary_value(
        "not-a-number", "none", show_all=False
    ) == "0 enabled \u00b7 0 overridden"


def test_doctor_output_detail_managed_by_value_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs install_details managed-by row.
    assert doctor_updates._doctor_detail_managed_by_value("true", "false", "/pkg/root") == (
        "npm: yes \u00b7 bun: no \u00b7 package root /pkg/root"
    )
    assert doctor_updates._doctor_detail_managed_by_value("false", "true", "not set") == (
        "npm: no \u00b7 bun: yes \u00b7 package root \u2014"
    )


def test_doctor_output_detail_model_row_value_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs config_details model row.
    assert doctor_updates._doctor_detail_model_row_value("gpt-5") == "gpt-5"
    assert doctor_updates._doctor_detail_model_row_value("gpt-5", "openai") == "gpt-5 \u00b7 openai"


def test_doctor_output_detail_issue_remedies_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs issue_remedies.
    assert doctor_updates._doctor_detail_issue_remedies([
        "first remedy",
        None,
        "second remedy",
        "first remedy",
        "third remedy",
    ]) == ["first remedy", "second remedy", "third remedy"]


def test_doctor_output_detail_issue_expected_for_label_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs issue_expected_for_label.
    issues = [
        {"fields": ["other"], "expected": "ignored"},
        {"fields": ["codex-linux-sandbox helper"], "expected": "present"},
        {"fields": ["linux helper"], "expected": "later"},
    ]
    assert doctor_updates._doctor_detail_issue_expected_for_label(issues, "linux helper") == "present"
    assert doctor_updates._doctor_detail_issue_expected_for_label(issues, "other") == "ignored"
    assert doctor_updates._doctor_detail_issue_expected_for_label(issues, "missing") is None


def test_doctor_output_detail_attach_issue_expected_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs attach_issue_metadata.
    issues = [{"fields": ["codex-linux-sandbox helper"], "expected": "present"}]
    assert doctor_updates._doctor_detail_attach_issue_expected("linux helper", None, issues) == "present"
    assert doctor_updates._doctor_detail_attach_issue_expected("linux helper", "already set", issues) == "already set"
    assert doctor_updates._doctor_detail_attach_issue_expected("missing", None, issues) is None


def test_doctor_output_detail_generic_detail_kind_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs generic_details.
    assert doctor_updates._doctor_detail_generic_kind_and_label("", "freeform note") == (
        "bullet",
        None,
        "freeform note",
    )
    assert doctor_updates._doctor_detail_generic_kind_and_label(
        "optional reachability failed",
        "remote unreachable",
    ) == ("row", "optional reachability", "remote unreachable")
    assert doctor_updates._doctor_detail_generic_kind_and_label("custom", "value") == ("row", "custom", "value")


def test_doctor_output_detail_remaining_details_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs push_remaining.
    parsed = [
        ("selected git", "/usr/bin/git"),
        ("PATH git #1", "/usr/bin/git"),
        ("note", "ignored inherited package-manager launch env for cargo-built binary"),
        ("optional reachability failed", "remote unreachable"),
        ("", "freeform note"),
    ]
    assert doctor_updates._doctor_detail_remaining_details(
        parsed,
        ["selected git"],
        ["PATH git #"],
    ) == [
        ("row", "optional reachability", "remote unreachable"),
        ("bullet", None, "freeform note"),
    ]


def test_doctor_output_detail_path_entry_values_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs install_details/git_details PATH entries.
    entries = ["/one", "/two", "/three", "/four"]
    assert doctor_updates._doctor_detail_path_entry_values(entries, show_all=False) == [
        ("PATH entries (4)", "/one"),
        ("continuation", "/two"),
        ("continuation", "/three"),
        ("continuation", "\u2026 (full list with --all)"),
    ]
    assert doctor_updates._doctor_detail_path_entry_values(entries, show_all=True) == [
        ("PATH entries (4)", "/one"),
        ("continuation", "/two"),
        ("continuation", "/three"),
        ("continuation", "/four"),
    ]
    assert doctor_updates._doctor_detail_path_entry_values([], show_all=False) == []


def test_doctor_output_detail_system_rows_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs system_details.
    parsed = [
        ("os version", "ignored consumed"),
        ("LANG", "en_US.UTF-8"),
        ("os", "Linux"),
        ("custom label", "custom value"),
        ("os language", "en-US"),
    ]
    assert doctor_updates._doctor_detail_system_rows(parsed) == [
        ("row", "os", "Linux"),
        ("row", "OS language", "en-US"),
        ("row", "LANG", "en_US.UTF-8"),
        ("row", "custom label", "custom value"),
    ]


def test_doctor_output_detail_runtime_rows_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs runtime_details.
    parsed = [
        ("platform", "ignored consumed"),
        ("current executable", "/usr/bin/codex"),
        ("version", "1.2.3"),
        ("extra", "value"),
        ("install method", "standalone"),
        ("commit", "abc123"),
    ]
    assert doctor_updates._doctor_detail_runtime_rows(parsed) == [
        ("row", "version", "1.2.3"),
        ("row", "install method", "standalone"),
        ("row", "commit", "abc123"),
        ("row", "executable", "/usr/bin/codex"),
        ("row", "extra", "value"),
    ]


def test_doctor_output_detail_title_rows_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs title_details.
    parsed = [
        ("terminal title project value", "codex-python"),
        ("terminal title source", "config"),
        ("extra", "value"),
        ("terminal title items", "model,project"),
        ("terminal title activity", "model"),
        ("terminal title project source", "project config"),
    ]
    assert doctor_updates._doctor_detail_title_rows(parsed) == [
        ("row", "title source", "config"),
        ("row", "title items", "model,project"),
        ("row", "activity item", "model"),
        ("row", "project source", "project config"),
        ("row", "project value", "codex-python"),
        ("row", "extra", "value"),
    ]


def test_doctor_output_detail_state_rows_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs state_details.
    parsed = [
        ("archived rollout files", "bad stats"),
        ("state DB integrity", "ok"),
        ("CODEX_HOME", "/home/alice/.codex"),
        ("state DB", "/home/alice/.codex/state.db"),
        ("active rollout files", "2 files, 2048 total bytes, 1024 average bytes"),
        ("extra", "value"),
    ]
    assert doctor_updates._doctor_detail_state_rows(parsed) == [
        ("row", "CODEX_HOME", "/home/alice/.codex"),
        ("row", "state DB", "/home/alice/.codex/state.db \u00b7 integrity ok"),
        ("row", "active rollouts", "2 files \u00b7 2.00 KB (avg 1.00 KB)"),
        ("row", "archived rollouts", "bad stats"),
        ("row", "extra", "value"),
    ]


def test_doctor_output_detail_git_rows_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs git_details.
    parsed = [
        ("PATH git #1", "/usr/bin/git"),
        ("git build options", "ignored consumed"),
        ("git branch", "main"),
        ("selected git", "/usr/bin/git"),
        ("git version", "git version 2.50.0"),
        ("extra", "value"),
        ("repo detected", "true"),
        ("PATH git #2", "/opt/bin/git"),
    ]
    assert doctor_updates._doctor_detail_git_rows(parsed, show_all=False) == [
        ("row", "selected git", "/usr/bin/git"),
        ("row", "version", "git version 2.50.0"),
        ("row", "repo detected", "true"),
        ("row", "branch", "main"),
        ("row", "PATH entries (2)", "/usr/bin/git"),
        ("continuation", None, "/opt/bin/git"),
        ("row", "extra", "value"),
    ]


def test_doctor_output_detail_install_rows_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs install_details.
    parsed = [
        ("current executable", "/usr/bin/codex"),
        ("PATH codex #1", "/one/codex"),
        ("install context", "npm"),
        ("managed package root", "not set"),
        ("managed by npm", "true"),
        ("note", "ignored inherited package-manager launch env for cargo-built binary"),
        ("extra", "value"),
        ("PATH codex #2", "/two/codex"),
    ]
    assert doctor_updates._doctor_detail_install_rows(parsed, show_all=False) == [
        ("row", "context", "npm"),
        ("bullet", None, "ignored inherited package-manager launch env for cargo-built binary"),
        ("row", "managed by", "npm: yes \u00b7 bun: no \u00b7 package root \u2014"),
        ("row", "PATH entries (2)", "/one/codex"),
        ("continuation", None, "/two/codex"),
        ("row", "extra", "value"),
    ]


def test_doctor_output_detail_config_rows_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs config_details.
    parsed = [
        ("model provider", "openai"),
        ("cwd", "/workspace"),
        ("model", "gpt-5"),
        ("feature flag overrides", "alpha=true, beta=false"),
        ("feature flags enabled", "2"),
        ("legacy feature flag", "old_flag"),
        ("config.toml parse", "ok"),
        ("extra", "value"),
    ]
    assert doctor_updates._doctor_detail_config_rows(parsed, show_all=False) == [
        ("row", "model", "gpt-5 \u00b7 openai"),
        ("row", "cwd", "/workspace"),
        ("row", "config.toml parse", "ok"),
        ("row", "feature flags", "2 enabled \u00b7 2 overridden (full list with --all)"),
        ("row", "legacy alias", "old_flag"),
        ("row", "extra", "value"),
    ]


def test_doctor_output_detail_rows_for_category_matches_rust_dispatch() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs detail_lines category dispatch.
    assert doctor_updates._doctor_detail_rows_for_category("system", [("os", "Linux")]) == [
        ("row", "os", "Linux")
    ]
    assert doctor_updates._doctor_detail_rows_for_category("runtime", [("version", "1.2.3")]) == [
        ("row", "version", "1.2.3")
    ]
    assert doctor_updates._doctor_detail_rows_for_category("unknown", [("optional reachability failed", "bad")]) == [
        ("row", "optional reachability", "bad")
    ]


def test_doctor_output_detail_value_from_details_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs detail_value.
    details = [
        "model: gpt-5",
        "freeform note",
        "model: later",
        "OPENAI_API_KEY: secret-token",
    ]
    assert doctor_updates._doctor_detail_value_from_details(details, "model") == "gpt-5"
    assert doctor_updates._doctor_detail_value_from_details(details, "OPENAI_API_KEY") == "<redacted>"
    assert doctor_updates._doctor_detail_value_from_details(details, "missing") is None


def test_doctor_output_detail_humanize_detail_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs humanize_detail.
    assert doctor_updates._doctor_detail_humanize_detail("row", "cwd", "/home/alice/project", "/home/alice") == (
        "row",
        "cwd",
        "~/project",
    )
    assert doctor_updates._doctor_detail_humanize_detail("continuation", None, "2026-06-16T01:23:45Z") == (
        "continuation",
        None,
        "2026-06-16 01:23 UTC",
    )
    assert doctor_updates._doctor_detail_humanize_detail("remedy", None, "/home/alice/project", "/home/alice") == (
        "remedy",
        None,
        "/home/alice/project",
    )


def test_doctor_output_detail_lines_for_check_matches_rust_pipeline() -> None:
    # Rust parity: codex-cli/src/doctor/output/detail.rs detail_lines pipeline.
    issues = [
        {"fields": ["cwd"], "expected": "inside project", "remedy": "cd into the project"},
        {"fields": ["cwd"], "expected": "ignored later", "remedy": "cd into the project"},
    ]
    assert doctor_updates._doctor_detail_lines_for_check(
        "config",
        ["cwd: /home/alice/project", "model: gpt-5"],
        issues,
        home="/home/alice",
    ) == [
        ("row", "model", "gpt-5", None),
        ("row", "cwd", "~/project", "inside project"),
        ("row", "feature flags", "0 enabled \u00b7 0 overridden", None),
        ("remedy", None, "cd into the project", None),
    ]


def test_doctor_output_groups_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs GROUPS.
    assert doctor_updates._doctor_output_groups() == [
        ("Environment", ("system", "runtime", "install", "search", "git", "terminal", "title", "state", "threads")),
        ("Configuration", ("config", "auth", "mcp", "sandbox")),
        ("Updates", ("updates",)),
        ("Connectivity", ("network", "websocket", "reachability")),
        ("Background Server", ("app-server",)),
    ]


def test_doctor_output_display_status_matches_rust_idle_app_server() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs display_status.
    assert doctor_updates._doctor_output_display_status("app-server", "ok", ["status: not running"]) == "idle"
    assert doctor_updates._doctor_output_display_status("app-server", "ok", ["status: running"]) == "ok"
    assert doctor_updates._doctor_output_display_status("system", "ok", ["status: not running"]) == "ok"
    assert doctor_updates._doctor_output_display_status("git", "warn", []) == "warning"
    assert doctor_updates._doctor_output_display_status("git", "fail", []) == "fail"


def test_doctor_output_overall_status_label_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs overall_status_label.
    assert doctor_updates._doctor_output_overall_status_label("ok") == "ok"
    assert doctor_updates._doctor_output_overall_status_label("warning") == "degraded"
    assert doctor_updates._doctor_output_overall_status_label("warn") == "degraded"
    assert doctor_updates._doctor_output_overall_status_label("fail") == "failed"


def test_doctor_output_issue_summary_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs issue_summary.
    assert doctor_updates._doctor_output_issue_summary("summary", []) == "summary"
    assert doctor_updates._doctor_output_issue_summary("summary", ["first cause"]) == "first cause"
    assert doctor_updates._doctor_output_issue_summary(
        "summary",
        ["first cause", "second cause", "third cause"],
    ) == "3 issues - first cause; second cause"


def test_doctor_output_row_description_matches_rust_priority() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs row_description.
    assert doctor_updates._doctor_output_row_description(
        "warning",
        "summary",
        ["issue cause"],
        "remedy",
    ) == "issue cause"
    assert doctor_updates._doctor_output_row_description(
        "fail",
        "summary",
        [],
        "remedy",
    ) == "summary \u2014 remedy"
    assert doctor_updates._doctor_output_row_description(
        "warn",
        "summary",
        [],
        "remedy",
        ascii_output=True,
    ) == "summary - remedy"
    assert doctor_updates._doctor_output_row_description("ok", "summary", [], "ignored") == "summary"


def test_doctor_output_update_note_summary_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs update_note.
    assert doctor_updates._doctor_output_update_note_summary(
        [
            "latest version status: newer version is available",
            "latest version: 0.130.0",
            "dismissed version: 0.128.0",
        ],
        "0.0.0",
    ) == "0.130.0 available (current 0.0.0, dismissed 0.128.0)"
    assert doctor_updates._doctor_output_update_note_summary(
        [
            "latest version status: newer version is available",
            "cached latest version: 0.129.0",
            "dismissed version: none",
        ],
        "0.0.0",
    ) == "0.129.0 available (current 0.0.0)"
    assert doctor_updates._doctor_output_update_note_summary(
        ["latest version status: current version is latest"],
        "0.0.0",
    ) is None


def test_doctor_output_rollout_note_summary_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs rollout_note.
    assert doctor_updates._doctor_output_rollout_note_summary([
        "active rollout files: 999 files, 1073741823 total bytes, 1074816 average bytes"
    ]) is None
    assert doctor_updates._doctor_output_rollout_note_summary([
        "active rollout files: 1000 files, 2048 total bytes, 2 average bytes"
    ]) == "1,000 active files \u00b7 2.00 KB on disk"
    assert doctor_updates._doctor_output_rollout_note_summary([
        "active rollout files: 1 files, 1073741824 total bytes, 1073741824 average bytes"
    ]) == "1 active files \u00b7 1.00 GB on disk"
    assert doctor_updates._doctor_output_rollout_note_summary(["active rollout files: invalid"]) is None


def test_doctor_output_sandbox_note_summary_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs sandbox_note.
    assert doctor_updates._doctor_output_sandbox_note_summary([
        "filesystem sandbox: restricted",
        "network sandbox: restricted",
    ]) is None
    assert doctor_updates._doctor_output_sandbox_note_summary([
        "filesystem sandbox: danger-full-access",
        "network sandbox: restricted",
    ]) == "filesystem danger-full-access \u00b7 network restricted"
    assert doctor_updates._doctor_output_sandbox_note_summary([
        "filesystem sandbox: restricted",
    ]) is None


def test_doctor_output_auth_reachability_note_summary_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs auth_reachability_note.
    assert doctor_updates._doctor_output_auth_reachability_note_summary(
        ["auth mode: ChatGPT"],
        ["reachability mode: API key auth"],
    ) == "mixed auth signals: ChatGPT login plus API key env var; HTTP reachability uses API-key mode"
    assert doctor_updates._doctor_output_auth_reachability_note_summary(
        ["auth mode: api key"],
        ["reachability mode: API key auth"],
    ) is None
    assert doctor_updates._doctor_output_auth_reachability_note_summary(
        ["auth mode: ChatGPT"],
        ["reachability mode: ChatGPT auth"],
    ) is None


def test_doctor_output_notes_order_matches_rust_collection_order() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs notes_for_report ordering.
    assert doctor_updates._doctor_output_notes_order([
        "mcp",
        "websocket",
        "updates",
        "state",
        "sandbox",
        "reachability",
    ]) == [
        "updates",
        "rollouts",
        "sandbox",
        "non-ok:mcp",
        "non-ok:websocket",
        "non-ok:updates",
        "non-ok:state",
        "non-ok:sandbox",
        "non-ok:reachability",
        "auth",
    ]


def test_doctor_output_footer_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs write_footer.
    assert doctor_updates._doctor_output_footer_lines(show_details=True) == [
        "--summary compact output --all expand truncated lists",
        "--json redacted report",
    ]
    assert doctor_updates._doctor_output_footer_lines(show_details=False) == [
        "Run codex doctor without --summary for detailed diagnostics.",
        "--all expand truncated lists --json redacted report",
    ]


def test_doctor_output_header_suffix_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs header_suffix.
    assert doctor_updates._doctor_output_header_suffix("0.0.0") == "v0.0.0"
    assert doctor_updates._doctor_output_header_suffix("0.0.0", ["platform: darwin-arm64"]) == "v0.0.0 \u00b7 darwin-arm64"
    assert doctor_updates._doctor_output_header_suffix("0.0.0", ["version: 1.2.3"]) == "v0.0.0"


def test_doctor_output_summary_line_text_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs summary_line.
    assert doctor_updates._doctor_output_summary_line_text(
        ok=12,
        idle=0,
        notes=2,
        warning=1,
        fail=1,
        overall_status="fail",
        ascii_output=False,
    ) == "12 ok \u00b7 2 notes \u00b7 1 warn \u00b7 1 fail failed"
    assert doctor_updates._doctor_output_summary_line_text(
        ok=5,
        idle=1,
        notes=5,
        warning=1,
        fail=0,
        overall_status="warning",
        ascii_output=True,
    ) == "5 ok | 1 idle | 5 notes | 1 warn | 0 fail degraded"
    assert doctor_updates._doctor_output_summary_line_text(
        ok=1,
        idle=0,
        notes=0,
        warning=0,
        fail=0,
        overall_status="ok",
    ) == "1 ok \u00b7 0 warn \u00b7 0 fail ok"


def test_doctor_output_checks_for_group_matches_rust_order() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs checks_for_group.
    checks = [
        ("git", "git.env"),
        ("system", "system.env"),
        ("git", "git.second"),
        ("updates", "updates.status"),
    ]

    assert doctor_updates._doctor_output_checks_for_group(checks, ("system", "git")) == [
        ("system", "system.env"),
        ("git", "git.env"),
        ("git", "git.second"),
    ]
    assert doctor_updates._doctor_output_checks_for_group(checks, ("missing",)) == []


def test_doctor_output_actionable_note_summary_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs actionable_note_summary.
    assert doctor_updates._doctor_output_actionable_note_summary(
        "Sandbox is restricted",
        issue_summary="Sandbox policy blocks writes",
        remediation="change sandbox mode",
    ) == "Sandbox policy blocks writes"
    assert doctor_updates._doctor_output_actionable_note_summary(
        "Update available",
        remediation="run codex update",
    ) == "Update available - run codex update"
    assert doctor_updates._doctor_output_actionable_note_summary("All checks passed") == "All checks passed"


def test_doctor_output_non_ok_notes_matches_rust_filtering() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs non_ok_notes.
    checks = [
        {"status": "ok", "summary": "Python installed"},
        {"status": "warning", "summary": "Update available", "remediation": "run codex update"},
        {"status": "idle", "summary": "App server idle"},
        {"status": "fail", "summary": "Auth unreachable", "issue_summary": "Auth endpoint failed"},
    ]

    assert doctor_updates._doctor_output_non_ok_notes(checks) == [
        ("warning", "Update available - run codex update"),
        ("fail", "Auth endpoint failed"),
    ]



def test_doctor_output_ascii_status_marker_slot_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs status_marker_slot with ascii output.
    assert doctor_updates._doctor_output_ascii_status_marker_slot("ok") == "[ok] "
    assert doctor_updates._doctor_output_ascii_status_marker_slot("warning") == "[!!] "
    assert doctor_updates._doctor_output_ascii_status_marker_slot("fail") == "[XX] "


def test_doctor_output_ascii_detail_marker_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs detail_marker with ascii output.
    assert doctor_updates._doctor_output_ascii_detail_marker(True) == ">"
    assert doctor_updates._doctor_output_ascii_detail_marker(False) == " "


def test_doctor_output_style_update_note_summary_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_update_note_summary with !color_enabled.
    assert doctor_updates._doctor_output_style_update_note_summary_no_color(
        "v1.2.3 available (run codex update)"
    ) == "v1.2.3 available (run codex update)"
    assert doctor_updates._doctor_output_style_update_note_summary_no_color(
        "update check failed"
    ) == "update check failed"


def test_doctor_output_count_label_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs count_label with color-disabled styling.
    assert doctor_updates._doctor_output_count_label_no_color(12, "ok", "ok") == "12 ok"
    assert doctor_updates._doctor_output_count_label_no_color(1, "warn", "warning") == "1 warn"
    assert doctor_updates._doctor_output_count_label_no_color(0, "fail", "fail") == "0 fail"


def test_doctor_output_styled_overall_status_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs styled_overall_status with !color_enabled.
    assert doctor_updates._doctor_output_styled_overall_status_no_color("ok", "ok") == "ok"
    assert doctor_updates._doctor_output_styled_overall_status_no_color("degraded", "warning") == "degraded"
    assert doctor_updates._doctor_output_styled_overall_status_no_color("failed", "fail") == "failed"


def test_doctor_output_style_note_summary_update_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_note_summary update path with !color_enabled.
    assert doctor_updates._doctor_output_style_update_note_summary_from_note_no_color(
        "update", "v1.2.3 available (run codex update)"
    ) == "v1.2.3 available (run codex update)"


def test_doctor_output_highlight_actions_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs highlight_actions with !color_enabled.
    assert doctor_updates._doctor_output_highlight_actions_no_color(
        "run `codex update` with --all, then retry"
    ) == "run `codex update` with --all, then retry"
    assert doctor_updates._doctor_output_highlight_actions_no_color("plain text") == "plain text"


def test_doctor_output_highlight_flags_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs highlight_flags with color-disabled styling.
    assert doctor_updates._doctor_output_highlight_flags_no_color(
        "use --all, --summary. and --config: value"
    ) == "use --all, --summary. and --config: value"
    assert doctor_updates._doctor_output_highlight_flags_no_color(
        "wrapped (--all)\tthen --verbose;"
    ) == "wrapped (--all)\tthen --verbose;"


def test_doctor_output_is_safe_presence_value_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs is_safe_presence_value.
    for value in ["true", " FALSE ", "Yes", "no", "present", "ABSENT", "missing", " not set "]:
        assert doctor_updates._doctor_output_is_safe_presence_value(value) is True
    for value in ["", "set", "not-set", "token present", "https://example.com"]:
        assert doctor_updates._doctor_output_is_safe_presence_value(value) is False


def test_doctor_output_redact_url_token_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_url_token/redact_url_path.
    assert doctor_updates._doctor_output_redact_url_token("plain-token") == "plain-token"
    assert doctor_updates._doctor_output_redact_url_token(
        "https://user:pass@example.com/a/b/c,"
    ) == "https://example.com/a/<redacted>,"
    assert doctor_updates._doctor_output_redact_url_token(
        "https://example.com/a?token=secret"
    ) == "https://example.com/a"
    assert doctor_updates._doctor_output_redact_url_token(
        "https://example.com)"
    ) == "https://example.com)"


def test_doctor_output_redact_urls_matches_rust_split_inclusive() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_urls.
    assert doctor_updates._doctor_output_redact_urls(
        "first https://user:pass@example.com/a/b\tsecond https://example.com/x/y."
    ) == "first https://example.com/a/<redacted>\tsecond https://example.com/x/<redacted>."
    assert doctor_updates._doctor_output_redact_urls("no urls here\n") == "no urls here\n"


def test_doctor_output_redact_detail_env_var_branch_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail env var branch.
    assert doctor_updates._doctor_output_redact_detail_env_var_branch(
        "Env var source: https://user:pass@example.com/a/b"
    ) == "Env var source: https://example.com/a/<redacted>"
    assert doctor_updates._doctor_output_redact_detail_env_var_branch(
        "env var present: OPENAI_API_KEY"
    ) == "env var present: OPENAI_API_KEY"


def test_doctor_output_redact_detail_safe_presence_branch_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail safe presence branch.
    assert doctor_updates._doctor_output_redact_detail_safe_presence_branch(
        "Auth token present: PRESENT"
    ) == "Auth token present: PRESENT"
    assert doctor_updates._doctor_output_redact_detail_safe_presence_branch(
        "Setting: not set"
    ) == "Setting: not set"



def test_doctor_output_redact_detail_secret_key_branch_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail secret key branch.
    assert doctor_updates._doctor_output_redact_detail_secret_key_branch(
        "OPENAI_API_KEY: sk-secret"
    ) == "OPENAI_API_KEY: <redacted>"
    assert doctor_updates._doctor_output_redact_detail_secret_key_branch(
        "authorization header: Bearer abc:def"
    ) == "authorization header: <redacted>"
    assert doctor_updates._doctor_output_redact_detail_secret_key_branch(
        "nested token value"
    ) == "nested token value: <redacted>"


def test_doctor_output_redact_detail_fallback_branch_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail fallback branch.
    assert doctor_updates._doctor_output_redact_detail_fallback_branch(
        "Config URL: https://user:pass@example.com/a/b."
    ) == "Config URL: https://example.com/a/<redacted>."
    assert doctor_updates._doctor_output_redact_detail_fallback_branch(
        "Plain diagnostic detail"
    ) == "Plain diagnostic detail"


def test_doctor_output_status_counts_from_display_statuses_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs StatusCounts::from_report.
    assert doctor_updates._doctor_output_status_counts_from_display_statuses(
        ["ok", "idle", "warning", "fail", "update", "note", "ok"], notes=3
    ) == {"ok": 2, "idle": 1, "notes": 3, "warning": 1, "fail": 1}
    assert doctor_updates._doctor_output_status_counts_from_display_statuses([], notes=0) == {
        "ok": 0,
        "idle": 0,
        "notes": 0,
        "warning": 0,
        "fail": 0,
    }


def test_doctor_output_bold_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs bold with !color_enabled.
    assert doctor_updates._doctor_output_bold_no_color("doctor status") == "doctor status"
    assert doctor_updates._doctor_output_bold_no_color("") == ""


def test_doctor_output_dim_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs dim with !color_enabled.
    assert doctor_updates._doctor_output_dim_no_color("compact output") == "compact output"
    assert doctor_updates._doctor_output_dim_no_color("") == ""


def test_doctor_output_detail_value_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs detail_value with !color_enabled.
    assert doctor_updates._doctor_output_detail_value_no_color("plain detail") == "plain detail"
    assert doctor_updates._doctor_output_detail_value_no_color("run `codex doctor` now") == "run `codex doctor` now"


def test_doctor_output_color256_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs color256 with !color_enabled.
    assert doctor_updates._doctor_output_color256_no_color("warning", 214) == "warning"
    assert doctor_updates._doctor_output_color256_no_color("", 117) == ""
    assert doctor_updates._doctor_output_color256_no_color("same text", 10) == "same text"


def test_doctor_output_green_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs green with !color_enabled.
    assert doctor_updates._doctor_output_green_no_color("ok") == "ok"
    assert doctor_updates._doctor_output_green_no_color("ready") == "ready"


def test_doctor_output_amber_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs amber with !color_enabled.
    assert doctor_updates._doctor_output_amber_no_color("update") == "update"
    assert doctor_updates._doctor_output_amber_no_color("available") == "available"


def test_doctor_output_orange_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs orange with !color_enabled.
    assert doctor_updates._doctor_output_orange_no_color("warning") == "warning"
    assert doctor_updates._doctor_output_orange_no_color("note") == "note"


def test_doctor_output_red_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs red with !color_enabled.
    assert doctor_updates._doctor_output_red_no_color("fail") == "fail"
    assert doctor_updates._doctor_output_red_no_color("failed") == "failed"


def test_doctor_output_cyan_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs cyan with !color_enabled.
    assert doctor_updates._doctor_output_cyan_no_color("--all") == "--all"
    assert doctor_updates._doctor_output_cyan_no_color("https://example.com") == "https://example.com"


def test_doctor_output_very_dim_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs very_dim with !color_enabled.
    assert doctor_updates._doctor_output_very_dim_no_color("separator") == "separator"
    assert doctor_updates._doctor_output_very_dim_no_color("muted") == "muted"


def test_doctor_output_detail_label_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs detail_label with !color_enabled.
    assert doctor_updates._doctor_output_detail_label_no_color("source") == "source"
    assert doctor_updates._doctor_output_detail_label_no_color("config") == "config"


def test_doctor_output_looks_copyable_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs looks_copyable.
    for text in [
        "http://example.com",
        "https://example.com",
        "wss://example.com/socket",
        "~/project",
        "/tmp/project",
        "./relative",
        "../parent",
    ]:
        assert doctor_updates._doctor_output_looks_copyable(text) is True
    for text in ["example.com", "project/file", "ssh://host", "", "~user/project"]:
        assert doctor_updates._doctor_output_looks_copyable(text) is False


def test_doctor_output_style_detail_token_plain_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_token for plain unstyled tokens.
    assert doctor_updates._doctor_output_style_detail_token_plain_no_color("source, ") == "source, "
    assert doctor_updates._doctor_output_style_detail_token_plain_no_color("config:\t") == "config:\t"
    assert doctor_updates._doctor_output_style_detail_token_plain_no_color("value)\n") == "value)\n"


def test_doctor_output_style_detail_plain_text_plain_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_plain_text for plain unstyled text.
    assert doctor_updates._doctor_output_style_detail_plain_text_plain_no_color(
        "source, config:\tvalue)\n"
    ) == "source, config:\tvalue)\n"
    assert doctor_updates._doctor_output_style_detail_plain_text_plain_no_color("plain detail") == "plain detail"


def test_doctor_output_style_detail_text_plain_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_text for plain/no-color text.
    assert doctor_updates._doctor_output_style_detail_text_plain_no_color(
        "run `codex doctor` from project, then retry"
    ) == "run codex doctor from project, then retry"
    assert doctor_updates._doctor_output_style_detail_text_plain_no_color("plain detail") == "plain detail"


def test_doctor_output_style_detail_bare_token_unit_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token unit branch with !color_enabled.
    for token in ["B", "KB", "MB", "GB", "TB", "files", "file"]:
        assert doctor_updates._doctor_output_style_detail_bare_token_unit_no_color(token) == token


def test_doctor_output_style_detail_bare_token_ok_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token ok branch with !color_enabled.
    assert doctor_updates._doctor_output_style_detail_bare_token_ok_no_color("ok") == "ok"


def test_doctor_output_style_detail_bare_token_copyable_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token flag/copyable branch with !color_enabled.
    for token in ["--all", "https://example.com", "wss://example.com/socket", "~/project", "./relative"]:
        assert doctor_updates._doctor_output_style_detail_bare_token_copyable_no_color(token) == token


def test_doctor_output_style_detail_bare_token_empty_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token empty branch.
    assert doctor_updates._doctor_output_style_detail_bare_token_empty("") == ""


def test_doctor_output_style_detail_bare_token_redacted_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token <redacted> branch with !color_enabled.
    assert doctor_updates._doctor_output_style_detail_bare_token_redacted_no_color("<redacted>") == "<redacted>"


def test_doctor_output_style_detail_bare_token_falsy_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token falsy/missing branch with !color_enabled.
    for token in ["false", "no", "absent", "value(missing)", "setting (missing)"]:
        assert doctor_updates._doctor_output_style_detail_bare_token_falsy_no_color(token) == token


def test_doctor_output_style_detail_bare_token_label_falsy_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token label:falsy branch with !color_enabled.
    for token in ["enabled:false", "present:no", "source:absent"]:
        assert doctor_updates._doctor_output_style_detail_bare_token_label_falsy_no_color(token) == token


def test_doctor_output_style_detail_bare_token_fallback_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token fallback branch.
    for token in ["source", "enabled:true", "project-name", "example.com", "42"]:
        assert doctor_updates._doctor_output_style_detail_bare_token_fallback_no_color(token) == token


def test_doctor_output_style_description_ok_idle_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_description Ok/Idle branch with !color_enabled.
    assert doctor_updates._doctor_output_style_description_ok_idle_no_color(
        "run `codex doctor` with --all", "ok"
    ) == "run `codex doctor` with --all"
    assert doctor_updates._doctor_output_style_description_ok_idle_no_color(
        "app server idle", "idle"
    ) == "app server idle"


def test_doctor_output_style_description_update_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_description Update branch with !color_enabled.
    assert doctor_updates._doctor_output_style_description_update_no_color(
        "run `codex update` with --all", "update"
    ) == "run `codex update` with --all"


def test_doctor_output_style_description_note_warning_fail_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_description Note/Warning/Fail branch with !color_enabled.
    for status in ["note", "warning", "fail"]:
        assert doctor_updates._doctor_output_style_description_note_warning_fail_no_color(
            "run `codex doctor` with --all", status
        ) == "run `codex doctor` with --all"


def test_doctor_output_style_note_summary_non_update_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_note_summary non-update path with !color_enabled.
    assert doctor_updates._doctor_output_style_note_summary_non_update_no_color(
        "ok", "all checks passed"
    ) == "all checks passed"
    assert doctor_updates._doctor_output_style_note_summary_non_update_no_color(
        "warning", "run `codex doctor` with --all"
    ) == "run `codex doctor` with --all"
    assert doctor_updates._doctor_output_style_note_summary_non_update_no_color(
        "fail", "auth failed"
    ) == "auth failed"


def test_doctor_output_style_detail_bare_token_no_color_matches_rust_order() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_bare_token branch order with !color_enabled.
    cases = {
        "": "",
        "<redacted>": "<redacted>",
        "false": "false",
        "source:false": "source:false",
        "ok": "ok",
        "--all": "--all",
        "https://example.com": "https://example.com",
        "files": "files",
        "plain": "plain",
    }
    for token, expected in cases.items():
        assert doctor_updates._doctor_output_style_detail_bare_token_no_color(token) == expected


def test_doctor_output_style_detail_token_no_color_matches_rust_dispatch() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_token with full no-color bare-token dispatch.
    cases = {
        "<redacted>, ": "<redacted>, ",
        "source:false;\t": "source:false;\t",
        "--all)\n": "--all)\n",
        "files. ": "files. ",
        "plain: ": "plain: ",
    }
    for token, expected in cases.items():
        assert doctor_updates._doctor_output_style_detail_token_no_color(token) == expected


def test_doctor_output_style_detail_plain_text_no_color_matches_rust_dispatch() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_plain_text with full no-color token dispatch.
    assert doctor_updates._doctor_output_style_detail_plain_text_no_color(
        "<redacted>, source:false;\t--all) files. plain"
    ) == "<redacted>, source:false;\t--all) files. plain"
    assert doctor_updates._doctor_output_style_detail_plain_text_no_color("false ok https://example.com") == "false ok https://example.com"


def test_doctor_output_style_detail_text_no_color_matches_rust_dispatch() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_text with full no-color dispatch.
    assert doctor_updates._doctor_output_style_detail_text_no_color(
        "run `codex doctor` with --all and source:false"
    ) == "run codex doctor with --all and source:false"
    assert doctor_updates._doctor_output_style_detail_text_no_color(
        "<redacted>, `https://example.com` files"
    ) == "<redacted>, https://example.com files"


def test_doctor_output_redact_detail_matches_rust_branch_order() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail branch order.
    assert doctor_updates._doctor_output_redact_detail(
        "env var token: OPENAI_API_KEY"
    ) == "env var token: OPENAI_API_KEY"
    assert doctor_updates._doctor_output_redact_detail("token present: present") == "token present: present"
    assert doctor_updates._doctor_output_redact_detail("codex_api_key: secret-value") == "codex_api_key: <redacted>"
    assert doctor_updates._doctor_output_redact_detail(
        "Config URL: https://user:pass@example.com/a/b."
    ) == "Config URL: https://example.com/a/<redacted>."


def test_doctor_output_style_detail_token_whitespace_no_color_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_detail_token whitespace-only token path.
    for token in [" ", "\t", "\r\n", " \t"]:
        assert doctor_updates._doctor_output_style_detail_token_no_color(token) == token


def test_doctor_output_style_description_no_color_matches_rust_dispatch() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs style_description branch order with !color_enabled.
    for status in ["ok", "idle", "update", "note", "warning", "fail"]:
        assert doctor_updates._doctor_output_style_description_no_color(
            "run `codex doctor` with --all", status
        ) == "run `codex doctor` with --all"


def test_doctor_output_redact_detail_sanitizes_secret_url_path_segments_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail_sanitizes_secret_url_path_segments.
    assert doctor_updates._doctor_output_redact_detail(
        "reachability failed: https://example.com/mcp/abc123xyz"
    ) == "reachability failed: https://example.com/mcp/<redacted>"


def test_doctor_output_redact_detail_sanitizes_urls_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail_sanitizes_urls.
    assert doctor_updates._doctor_output_redact_detail(
        "reachability failed: https://user:pass@example.com/mcp?x=abc#frag (connect failed)"
    ) == "reachability failed: https://example.com/mcp (connect failed)"


def test_doctor_output_redact_detail_preserves_env_var_names_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail_preserves_env_var_names.
    assert doctor_updates._doctor_output_redact_detail(
        "auth env vars present: OPENAI_API_KEY, CODEX_API_KEY"
    ) == "auth env vars present: OPENAI_API_KEY, CODEX_API_KEY"


def test_doctor_output_redact_detail_preserves_secret_presence_booleans_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs redact_detail_preserves_secret_presence_booleans.
    assert doctor_updates._doctor_output_redact_detail("stored ChatGPT tokens: true") == "stored ChatGPT tokens: true"
    assert doctor_updates._doctor_output_redact_detail("stored ChatGPT tokens: false") == "stored ChatGPT tokens: false"


def test_doctor_output_detailed_no_color_unicode_options_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs detailed_no_color_unicode_options.
    assert doctor_updates._doctor_output_detailed_no_color_unicode_options() == {
        "show_details": True,
        "show_all": False,
        "ascii": False,
        "color_enabled": False,
    }


def test_doctor_output_summary_no_color_unicode_options_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs summary_no_color_unicode_options.
    assert doctor_updates._doctor_output_summary_no_color_unicode_options() == {
        "show_details": False,
        "show_all": False,
        "ascii": False,
        "color_enabled": False,
    }


def test_doctor_output_detailed_all_no_color_unicode_options_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs detailed_all_no_color_unicode_options.
    assert doctor_updates._doctor_output_detailed_all_no_color_unicode_options() == {
        "show_details": True,
        "show_all": True,
        "ascii": False,
        "color_enabled": False,
    }


def test_doctor_output_detailed_color_unicode_options_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs detailed_color_unicode_options.
    assert doctor_updates._doctor_output_detailed_color_unicode_options() == {
        "show_details": True,
        "show_all": False,
        "ascii": False,
        "color_enabled": True,
    }


def test_doctor_output_sample_report_check_metadata_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs sample_report lightweight metadata.
    report = doctor_updates._doctor_output_sample_report_check_metadata()
    assert report["schema_version"] == 1
    assert report["generated_at"] == "0s since unix epoch"
    assert report["overall_status"] == "fail"
    assert report["codex_version"] == "0.0.0"
    assert report["checks"] == [
        ("system.environment", "system", "ok"),
        ("runtime.provenance", "runtime", "ok"),
        ("installation", "install", "ok"),
        ("runtime.search", "search", "ok"),
        ("git.environment", "git", "ok"),
        ("terminal.env", "terminal", "warning"),
        ("terminal.title", "title", "ok"),
        ("state.paths", "state", "ok"),
        ("auth.credentials", "auth", "fail"),
        ("updates.status", "updates", "ok"),
        ("network.env", "network", "ok"),
        ("network.websocket_reachability", "websocket", "ok"),
        ("app_server.status", "app-server", "ok"),
        ("network.provider_reachability", "reachability", "ok"),
    ]


def test_doctor_output_sample_report_detail_metadata_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs sample_report details/remediation.
    assert doctor_updates._doctor_output_sample_report_detail_metadata() == {
        "system.environment": {
            "details": ["os: macOS 15.0", "os language: en-US"],
            "remediation": None,
        },
        "git.environment": {
            "details": [
                "selected git: /usr/bin/git",
                "git version: git version 2.54.0",
                "repo detected: true",
            ],
            "remediation": None,
        },
        "terminal.title": {
            "details": [
                "terminal title source: default",
                "terminal title items: activity, project-name",
                "terminal title project value: codex",
            ],
            "remediation": None,
        },
        "auth.credentials": {
            "details": ["OPENAI_API_KEY: present"],
            "remediation": "Run `codex login`.",
        },
    }


def test_doctor_output_sample_report_status_counts_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs sample_report with StatusCounts::from_report.
    assert doctor_updates._doctor_output_sample_report_status_counts(notes=0) == {
        "ok": 12,
        "idle": 0,
        "notes": 0,
        "warning": 1,
        "fail": 1,
    }
    assert doctor_updates._doctor_output_sample_report_status_counts(notes=2) == {
        "ok": 12,
        "idle": 0,
        "notes": 2,
        "warning": 1,
        "fail": 1,
    }


def test_doctor_output_sample_report_non_ok_notes_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs sample_report with non_ok_notes.
    assert doctor_updates._doctor_output_sample_report_non_ok_notes() == [
        ("warning", "narrow terminal"),
        ("fail", "token expired - Run `codex login`."),
    ]


def test_doctor_output_sample_report_summary_line_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs sample_report with summary_line.
    assert doctor_updates._doctor_output_sample_report_summary_line() == "12 ok · 1 warn · 1 fail failed"
    assert doctor_updates._doctor_output_sample_report_summary_line(ascii_output=True, notes=2) == (
        "12 ok | 2 notes | 1 warn | 1 fail failed"
    )


def test_doctor_output_summary_mode_footer_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color footer.
    assert doctor_updates._doctor_output_summary_mode_footer_lines() == [
        "Run codex doctor without --summary for detailed diagnostics.",
        "--all expand truncated lists       --json redacted report",
    ]


def test_doctor_output_sample_report_summary_notes_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color Notes block.
    assert doctor_updates._doctor_output_sample_report_summary_notes_lines() == [
        "Notes",
        "   ⚠ terminal     narrow terminal",
        "   ✗ auth         token expired - Run `codex login`.",
    ]


def test_doctor_output_sample_report_summary_section_headings_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color section headings.
    assert doctor_updates._doctor_output_sample_report_summary_section_headings() == [
        "Environment",
        "Configuration",
        "Updates",
        "Connectivity",
        "Background Server",
    ]


def test_doctor_output_sample_report_summary_environment_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color Environment rows.
    assert doctor_updates._doctor_output_sample_report_summary_environment_lines() == [
        "  ✓ system       en-US",
        "  ✓ runtime      running local build on darwin-arm64",
        "  ✓ install      consistent",
        "  ✓ search       search is OK (bundled)",
        "  ✓ git          git version 2.54.0",
        "  ⚠ terminal     narrow terminal",
        "  ✓ title        default · project codex",
        "  ✓ state        state paths inspectable",
    ]

def test_doctor_output_sample_report_summary_updates_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color Updates rows.
    assert doctor_updates._doctor_output_sample_report_summary_updates_lines() == [
        "  ✓ updates      update configuration is locally consistent",
    ]

def test_doctor_output_sample_report_summary_connectivity_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color Connectivity rows.
    assert doctor_updates._doctor_output_sample_report_summary_connectivity_lines() == [
        "  ✓ network      network environment readable",
        "  ✓ websocket    Responses WebSocket handshake succeeded",
        "  ✓ reachability active provider endpoints are reachable over HTTP",
    ]

def test_doctor_output_sample_report_summary_background_server_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color Background Server rows.
    assert doctor_updates._doctor_output_sample_report_summary_background_server_lines() == [
        "  ✓ app-server   background server is not running",
    ]

def test_doctor_output_sample_report_summary_configuration_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color Configuration rows.
    assert doctor_updates._doctor_output_sample_report_summary_configuration_lines() == [
        "  ✗ auth         token expired — Run `codex login`.",
    ]

def test_doctor_output_sample_report_summary_section_blocks_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color section order and rows.
    assert doctor_updates._doctor_output_sample_report_summary_section_blocks() == [
        ("Environment", doctor_updates._doctor_output_sample_report_summary_environment_lines()),
        ("Configuration", doctor_updates._doctor_output_sample_report_summary_configuration_lines()),
        ("Updates", doctor_updates._doctor_output_sample_report_summary_updates_lines()),
        ("Connectivity", doctor_updates._doctor_output_sample_report_summary_connectivity_lines()),
        ("Background Server", doctor_updates._doctor_output_sample_report_summary_background_server_lines()),
    ]

def test_doctor_output_sample_report_summary_title_line_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color title line.
    assert doctor_updates._doctor_output_sample_report_summary_title_line() == "Codex Doctor v0.0.0"

def test_doctor_output_sample_report_summary_footer_summary_line_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color footer summary line.
    assert (
        doctor_updates._doctor_output_sample_report_summary_footer_summary_line()
        == "12 ok · 2 notes · 1 warn · 1 fail failed"
    )


def test_doctor_output_sample_report_summary_no_color_rendered_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_summary_output_without_color full snapshot.
    assert doctor_updates._doctor_output_sample_report_summary_no_color_rendered() == (
        "Codex Doctor v0.0.0\n"
        "\n"
        "Notes\n"
        "   ⚠ terminal     narrow terminal\n"
        "   ✗ auth         token expired - Run `codex login`.\n"
        "─────────────────────────────────────────────────────────────\n"
        "\n"
        "Environment\n"
        "  ✓ system       en-US\n"
        "  ✓ runtime      running local build on darwin-arm64\n"
        "  ✓ install      consistent\n"
        "  ✓ search       search is OK (bundled)\n"
        "  ✓ git          git version 2.54.0\n"
        "  ⚠ terminal     narrow terminal\n"
        "  ✓ title        default · project codex\n"
        "  ✓ state        state paths inspectable\n"
        "\n"
        "Configuration\n"
        "  ✗ auth         token expired — Run `codex login`.\n"
        "\n"
        "Updates\n"
        "  ✓ updates      update configuration is locally consistent\n"
        "\n"
        "Connectivity\n"
        "  ✓ network      network environment readable\n"
        "  ✓ websocket    Responses WebSocket handshake succeeded\n"
        "  ✓ reachability active provider endpoints are reachable over HTTP\n"
        "\n"
        "Background Server\n"
        "  ✓ app-server   background server is not running\n"
        "\n"
        "─────────────────────────────────────────────────────────────\n"
        "12 ok · 2 notes · 1 warn · 1 fail failed\n"
        "\n"
        "Run codex doctor without --summary for detailed diagnostics.\n"
        "--all expand truncated lists       --json redacted report\n"
    )

def test_doctor_output_summary_environment_threads_row_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_includes_threads_row_in_environment.
    threads_line = doctor_updates._doctor_output_summary_environment_threads_row()
    assert "threads" in threads_line
    assert "rollout files and state DB thread inventory differ" in threads_line

def test_doctor_output_state_health_summary_with_memories_db_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_includes_memories_db_in_state_health_summary.
    lines = doctor_updates._doctor_output_state_health_summary_with_memories_db_lines()
    assert "✓ state        databases healthy" in lines
    assert "memories DB              /tmp/memories.sqlite · integrity ok" in lines

def test_doctor_output_sample_report_summary_ascii_rendered_matches_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_supports_ascii_output full snapshot.
    assert doctor_updates._doctor_output_sample_report_summary_ascii_rendered() == (
        "Codex Doctor v0.0.0\n"
        "\n"
        "Notes\n"
        "   [!!] terminal     narrow terminal\n"
        "   [XX] auth         token expired - Run `codex login`.\n"
        "-------------------------------------------------------------\n"
        "\n"
        "Environment\n"
        "  [ok] system       en-US\n"
        "  [ok] runtime      running local build on darwin-arm64\n"
        "  [ok] install      consistent\n"
        "  [ok] search       search is OK (bundled)\n"
        "  [ok] git          git version 2.54.0\n"
        "  [!!] terminal     narrow terminal\n"
        "  [ok] title        default | project codex\n"
        "  [ok] state        state paths inspectable\n"
        "\n"
        "Configuration\n"
        "  [XX] auth         token expired - Run `codex login`.\n"
        "\n"
        "Updates\n"
        "  [ok] updates      update configuration is locally consistent\n"
        "\n"
        "Connectivity\n"
        "  [ok] network      network environment readable\n"
        "  [ok] websocket    Responses WebSocket handshake succeeded\n"
        "  [ok] reachability active provider endpoints are reachable over HTTP\n"
        "\n"
        "Background Server\n"
        "  [ok] app-server   background server is not running\n"
        "\n"
        "-------------------------------------------------------------\n"
        "12 ok | 2 notes | 1 warn | 1 fail failed\n"
        "\n"
        "Run codex doctor without --summary for detailed diagnostics.\n"
        "--all expand truncated lists       --json redacted report\n"
    )

def test_doctor_output_sample_report_redacted_detail_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_includes_redacted_details.
    assert "      OPENAI_API_KEY           present" in doctor_updates._doctor_output_sample_report_redacted_detail_lines()

def test_doctor_output_terminal_warning_issue_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_explains_terminal_warning_issue.
    lines = doctor_updates._doctor_output_terminal_warning_issue_lines()
    assert "⚠ terminal     width 79 cols - output may wrap (recommended >=80)" in lines
    assert "▸ terminal size            79x26 (expected >= 80 columns)" in lines
    assert "→ resize the window to at least 80 columns" in lines
    assert doctor_updates._doctor_output_terminal_warning_issue_forbidden_summary() not in lines

def test_doctor_output_promoted_notes_without_status_change_lines_match_rust() -> None:
    # Rust parity: codex-cli/src/doctor/output.rs render_human_report_promotes_notes_without_changing_statuses.
    lines = doctor_updates._doctor_output_promoted_notes_without_status_change_lines()
    assert "Notes\n   ↑ updates" in lines
    assert "0.130.0 available (current 0.0.0, dismissed 0.128.0)" in lines
    assert "⚠ rollouts" in lines
    assert "⚠ sandbox" in lines
    assert "⚠ mcp" in lines
    assert "⚠ auth         mixed auth signals: ChatGPT login plus API key env var; HTTP reachability uses API-key mode" in lines
    assert "○ app-server   not running (ephemeral mode)" in lines
    assert "5 ok · 1 idle · 5 notes · 1 warn · 0 fail degraded" in lines
