from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

from parity_harness.__main__ import main
from parity_harness.paths import artifact_path
from parity_harness.workspace import load_workspace_contract


class CliTests(unittest.TestCase):
    def invoke(self, *args: str) -> int:
        with redirect_stdout(io.StringIO()):
            return main(list(args))

    def invoke_json(self, *args: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(list(args))
        return status, json.loads(output.getvalue())

    def test_each_layer_has_an_independent_command(self) -> None:
        self.assertEqual(self.invoke("contract", "validate"), 0)
        self.assertEqual(self.invoke("structure"), 0)
        self.assertEqual(self.invoke("dynamic", "run", "matching"), 0)
        self.assertEqual(self.invoke("outcome", "run", "success"), 0)
        self.assertEqual(self.invoke("accept", "verified"), 0)
        self.assertEqual(self.invoke("maintain"), 0)

    def test_negative_layer_scenarios_return_nonzero(self) -> None:
        self.assertEqual(self.invoke("dynamic", "run", "missing"), 1)
        self.assertEqual(self.invoke("outcome", "run", "false-claim"), 1)

    def test_real_tui_structure_scope_verifies_complete_owner_index(self) -> None:
        self.assertEqual(self.invoke("structure", "--scope", "tui"), 0)

    def test_real_core_structure_scope_verifies_complete_inventory(self) -> None:
        status, report = self.invoke_json("structure", "--scope", "core")

        self.assertEqual(status, 0)
        self.assertEqual(report["ownership_verdict"], "verified")
        self.assertEqual(report["coverage_verdict"], "verified")

    def test_core_ownership_gate_preserves_verified_coverage(self) -> None:
        status, report = self.invoke_json(
            "structure", "--scope", "core", "--gate", "ownership"
        )

        self.assertEqual(status, 0)
        self.assertEqual(report["ownership_verdict"], "verified")
        self.assertEqual(report["coverage_verdict"], "verified")

    def test_protected_app_server_scopes_preserve_their_existing_results(self) -> None:
        status, app_server = self.invoke_json(
            "structure", "--scope", "app-server", "--gate", "ownership"
        )
        transport_status, transport = self.invoke_json(
            "structure",
            "--scope",
            "app-server-transport",
            "--gate",
            "ownership",
        )

        self.assertEqual(status, 0)
        self.assertEqual(app_server["contracts"], 60)
        self.assertEqual(app_server["ownership_verdict"], "verified")
        self.assertEqual(app_server["coverage_verdict"], "verified")
        self.assertEqual(transport_status, 0)
        self.assertEqual(transport["contracts"], 3)
        self.assertEqual(transport["ownership_verdict"], "verified")
        self.assertEqual(transport["coverage_verdict"], "partial")
        self.assertEqual(transport["finding_counts"], {"STR015": 10})

    def test_structure_command_persists_detailed_machine_report(self) -> None:
        status, report = self.invoke_json(
            "structure", "--scope", "guardian", "--gate", "ownership"
        )

        self.assertEqual(status, 0)
        report_path = Path(report["machine_report"])
        self.assertTrue(report_path.is_file())
        detail = json.loads(report_path.read_text(encoding="utf-8"))
        scope = detail["scope_reports"]["guardian"]
        self.assertEqual(scope["ownership_verdict"], "verified")
        self.assertEqual(scope["coverage_verdict"], "verified")
        self.assertIn("uncovered_rust_modules", scope)
        self.assertIn("orphan_python_files", scope)
        self.assertIn("merge_or_duplicate_owners", scope)
        self.assertIn("scattered_owners", scope)
        self.assertIn("foreign_items", scope)
        self.assertIn("intentional_adapters", scope)
        self.assertEqual(
            scope["migration_plan"],
            {"foreign_item_moves": [], "unowned_python_files": []},
        )
        self.assertEqual(
            detail["migration_summary"],
            {
                "foreign_item_groups": 0,
                "foreign_item_findings": 0,
                "foreign_symbol_assignments": 0,
                "ambiguous_foreign_items": 0,
                "unowned_python_files": 0,
                "unowned_with_rust_symbol_matches": 0,
                "unowned_without_rust_symbol_matches": 0,
            },
        )
        self.assertEqual(
            detail["workspace_classification"]["total"],
            len(load_workspace_contract().crates),
        )

    def test_failed_scope_machine_report_groups_rust_owned_migrations(self) -> None:
        status, report = self.invoke_json(
            "structure", "--scope", "analytics", "--gate", "ownership"
        )

        self.assertEqual(status, 1)
        detail = json.loads(Path(report["machine_report"]).read_text(encoding="utf-8"))
        plan = detail["scope_reports"]["analytics"]["migration_plan"]
        groups = {
            (item["rust_module"], item["rust_source"]): item
            for item in plan["foreign_item_moves"]
        }
        accepted_lines = groups[
            (
                "crate::accepted_lines",
                "codex/codex-rs/analytics/src/accepted_lines.rs",
            )
        ]
        self.assertEqual(accepted_lines["python_owner"], "pycodex/analytics/__init__.py")
        self.assertFalse(accepted_lines["requires_disambiguation"])
        self.assertEqual(accepted_lines["ambiguous_symbols"], [])
        self.assertIn("AcceptedLineFingerprintEventInput", accepted_lines["symbols"])
        self.assertIn("AcceptedLineFingerprintSummary", accepted_lines["symbols"])

    def test_unowned_file_plan_reports_symbol_based_rust_navigation(self) -> None:
        status, report = self.invoke_json(
            "structure", "--scope", "api", "--gate", "ownership"
        )

        self.assertEqual(status, 1)
        detail = json.loads(Path(report["machine_report"]).read_text(encoding="utf-8"))
        files = detail["scope_reports"]["api"]["migration_plan"][
            "unowned_python_files"
        ]
        methods_common = next(
            item
            for item in files
            if item["path"].endswith("methods_common_constants.py")
        )
        self.assertEqual(methods_common["python_symbols"], ["REALTIME_AUDIO_SAMPLE_RATE"])
        self.assertEqual(
            methods_common["rust_symbol_matches"],
            [
                {
                    "module": "crate::endpoint::realtime_websocket::methods_common",
                    "source": (
                        "codex/codex-rs/codex-api/src/endpoint/"
                        "realtime_websocket/methods_common.rs"
                    ),
                    "symbols": ["REALTIME_AUDIO_SAMPLE_RATE"],
                }
            ],
        )

    def test_ambiguous_foreign_symbol_is_not_assigned_automatically(self) -> None:
        status, report = self.invoke_json(
            "structure", "--scope", "git-utils", "--gate", "ownership"
        )

        self.assertEqual(status, 1)
        detail = json.loads(Path(report["machine_report"]).read_text(encoding="utf-8"))
        groups = detail["scope_reports"]["git-utils"]["migration_plan"][
            "foreign_item_moves"
        ]
        run_git_groups = [
            item for item in groups if "run_git" in item["ambiguous_symbols"]
        ]
        self.assertEqual(
            {item["rust_module"] for item in run_git_groups},
            {"crate::apply", "crate::operations"},
        )
        self.assertTrue(all(item["requires_disambiguation"] for item in run_git_groups))
        self.assertTrue(
            all("Do not assign ambiguous_symbols" in item["recommendation"] for item in run_git_groups)
        )

    def test_generic_candidate_generation_never_claims_acceptance(self) -> None:
        status, report = self.invoke_json("contract", "generate", "--scope", "core")

        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "candidate")
        self.assertGreater(report["summary"]["rust_modules"], 0)

    def test_aggregate_audit_preserves_all_three_acceptance_verdicts(self) -> None:
        self.assertEqual(self.invoke("audit"), 0)
        self.assertTrue(artifact_path("reports", "verified.report.json").is_file())
        self.assertTrue(artifact_path("reports", "failed.report.md").is_file())
        self.assertTrue(artifact_path("reports", "inconclusive.report.json").is_file())
        self.assertTrue(artifact_path("boundary", "git-status.json").is_file())


if __name__ == "__main__":
    unittest.main()
