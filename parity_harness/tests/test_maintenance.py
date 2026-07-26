from __future__ import annotations

from dataclasses import replace
import unittest

from parity_harness.maintenance import HarnessMaintenanceAuditor
from parity_harness.model import Verdict
from parity_harness.paths import ArtifactWorkspace
from parity_harness.registry import CHECKERS
from parity_harness.workflow import example_contract, run_maintenance


class MaintenanceTests(unittest.TestCase):
    def test_current_harness_is_reachable_and_non_overlapping(self) -> None:
        result = run_maintenance()
        self.assertEqual(result.verdict, Verdict.VERIFIED)

    def test_duplicate_checker_responsibility_is_detected(self) -> None:
        duplicate = replace(CHECKERS[1], checker_id=CHECKERS[0].checker_id)
        result = HarnessMaintenanceAuditor(registrations=(CHECKERS[0], duplicate)).audit((example_contract(),))
        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertIn("MNT001", {item.code for item in result.findings})

    def test_unknown_contract_checker_is_detected(self) -> None:
        contract = example_contract()
        checks = {key: dict(value) for key, value in contract.checks.items()}
        checks["structure"]["checker"] = "structure.duplicate-shortcut"
        result = HarnessMaintenanceAuditor().audit((replace(contract, checks=checks),))
        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertIn("MNT012", {item.code for item in result.findings})

    def test_stale_contract_path_and_baseline_are_detected(self) -> None:
        contract = example_contract()
        python = dict(contract.python)
        python["owner"] = "parity_harness/fixtures/example_repo/python/demo/missing.py"
        rust = dict(contract.rust)
        rust["baseline_commit"] = "0" * 40
        result = HarnessMaintenanceAuditor().audit((replace(contract, python=python, rust=rust),))
        codes = {item.code for item in result.findings}
        self.assertIn("MNT007", codes)
        self.assertIn("MNT008", codes)

    def test_unreachable_module_fixture_and_misplaced_artifact_are_detected(self) -> None:
        with ArtifactWorkspace("maintenance-") as root:
            (root / "__main__.py").write_text("pass\n", encoding="utf-8")
            (root / "unused.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "fixtures" / "traces").mkdir(parents=True)
            (root / "fixtures" / "traces" / "orphan.json").write_text("{}\n", encoding="utf-8")
            (root / "bad.report.json").write_text("{}\n", encoding="utf-8")
            result = HarnessMaintenanceAuditor(harness_root=root, registrations=()).audit((example_contract(),))
            codes = {item.code for item in result.findings}
            self.assertIn("MNT004", codes)
            self.assertIn("MNT009", codes)
            self.assertIn("MNT011", codes)


if __name__ == "__main__":
    unittest.main()
