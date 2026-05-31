import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pycodex.cli.doctor_updates as doctor_updates
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
)


class DoctorUpdateDetailsTests(unittest.TestCase):
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

    def test_doctor_websocket_check_reports_static_supported_provider_without_probe(self) -> None:
        check = doctor_websocket_check(
            inputs=WebsocketCheckInputs(
                model_provider_id="openai",
                provider_name="OpenAI",
                wire_api="responses",
                supports_websockets=True,
                connect_timeout_ms=30000,
                auth_mode="api_key",
                endpoint="wss://api.openai.com/v1/responses",
                env={"HTTPS_PROXY": "http://proxy.example"},
            )
        )

        self.assertEqual(check.status, "warn")
        self.assertEqual(check.summary, "Responses WebSocket probe not run; HTTPS fallback may still work")
        self.assertIn("connect timeout: 30000 ms", check.details)
        self.assertIn("auth mode: api_key", check.details)
        self.assertIn("endpoint: wss://api.openai.com/v1/responses", check.details)
        self.assertIn("proxy env vars present: HTTPS_PROXY", check.details)
        self.assertIn("handshake probe not implemented in Python port", check.details)
        self.assertEqual(
            check.remediation,
            "Check proxy, VPN, firewall, DNS, custom CA, and WebSocket policy support.",
        )

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

    def test_doctor_terminal_check_fails_for_dumb_terminal(self) -> None:
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
