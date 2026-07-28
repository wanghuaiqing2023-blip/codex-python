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

    def test_protected_app_server_scopes_preserve_verified_results(self) -> None:
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
        self.assertEqual(transport["contracts"], 13)
        self.assertEqual(transport["ownership_verdict"], "verified")
        self.assertEqual(transport["coverage_verdict"], "verified")
        self.assertEqual(transport["finding_counts"], {})

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

    def test_aligned_analytics_scope_has_no_pending_migrations(self) -> None:
        status, report = self.invoke_json(
            "structure", "--scope", "analytics", "--gate", "ownership"
        )

        self.assertEqual(status, 0)
        self.assertEqual(report["contracts"], 6)
        self.assertEqual(report["ownership_verdict"], "verified")
        self.assertEqual(report["coverage_verdict"], "verified")
        self.assertEqual(report["finding_counts"], {})
        detail = json.loads(Path(report["machine_report"]).read_text(encoding="utf-8"))
        plan = detail["scope_reports"]["analytics"]["migration_plan"]
        self.assertEqual(plan, {"foreign_item_moves": [], "unowned_python_files": []})

    def test_aligned_exec_server_scope_has_no_ambiguous_foreign_symbols(self) -> None:
        status, report = self.invoke_json(
            "structure", "--scope", "exec-server", "--gate", "ownership"
        )

        self.assertEqual(status, 0)
        self.assertEqual(report["contracts"], 40)
        self.assertEqual(report["ownership_verdict"], "verified")
        self.assertEqual(report["coverage_verdict"], "verified")
        self.assertEqual(report["finding_counts"], {})
        detail = json.loads(Path(report["machine_report"]).read_text(encoding="utf-8"))
        self.assertEqual(
            detail["scope_reports"]["exec-server"]["migration_plan"],
            {"foreign_item_moves": [], "unowned_python_files": []},
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
