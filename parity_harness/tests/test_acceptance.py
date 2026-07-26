from __future__ import annotations

from dataclasses import replace
import unittest

from parity_harness.acceptance import AcceptanceEvaluator
from parity_harness.model import Evidence, LayerResult, Verdict
from parity_harness.workflow import (
    example_contract,
    run_acceptance,
    run_dynamic,
    run_outcome,
    run_structure,
)


class AcceptanceTests(unittest.TestCase):
    def test_complete_serialized_evidence_is_verified(self) -> None:
        self.assertEqual(run_acceptance("verified").verdict, Verdict.VERIFIED)

    def test_missing_layer_is_inconclusive(self) -> None:
        contract = example_contract()
        report = AcceptanceEvaluator().evaluate(
            contract,
            (
                run_structure(contract),
                run_dynamic(contract, "matching"),
            ),
        )
        self.assertEqual(report.verdict, Verdict.INCONCLUSIVE)
        self.assertIn("ACC003", {item.code for item in report.findings})

    def test_python_only_dynamic_evidence_cannot_claim_parity(self) -> None:
        contract = example_contract()
        dynamic = run_dynamic(contract, "matching")
        python_only = replace(
            dynamic.evidence[0],
            provenance=("python",),
        )
        dynamic = replace(dynamic, evidence=(python_only,))
        report = AcceptanceEvaluator().evaluate(
            contract,
            (
                run_structure(contract),
                dynamic,
                run_outcome(contract, "success"),
            ),
        )
        self.assertEqual(report.verdict, Verdict.FAILED)
        self.assertIn("ACC006", {item.code for item in report.findings})

    def test_correct_trace_with_wrong_result_fails(self) -> None:
        contract = example_contract()
        report = AcceptanceEvaluator().evaluate(
            contract,
            (
                run_structure(contract),
                run_dynamic(contract, "matching"),
                run_outcome(contract, "false-claim"),
            ),
        )
        self.assertEqual(report.verdict, Verdict.FAILED)
        self.assertIn("OUT001", {item.code for item in report.findings})

    def test_correct_result_with_wrong_chain_fails(self) -> None:
        contract = example_contract()
        report = AcceptanceEvaluator().evaluate(
            contract,
            (
                run_structure(contract),
                run_dynamic(contract, "missing"),
                run_outcome(contract, "success"),
            ),
        )
        self.assertEqual(report.verdict, Verdict.FAILED)
        self.assertIn("DYN001", {item.code for item in report.findings})

    def test_conflicting_evidence_ids_fail(self) -> None:
        contract = example_contract()
        structure = run_structure(contract)
        duplicate = Evidence(
            evidence_id=structure.evidence[0].evidence_id,
            evidence_type="module-ownership",
            coordinate="different",
            source="other",
            status="verified",
            detail="conflict",
        )
        extra = LayerResult("extra", contract.contract_id, Verdict.VERIFIED, (duplicate,))
        report = AcceptanceEvaluator().evaluate(
            contract,
            (
                structure,
                run_dynamic(contract, "matching"),
                run_outcome(contract, "success"),
                extra,
            ),
        )
        self.assertEqual(report.verdict, Verdict.FAILED)
        self.assertIn("ACC004", {item.code for item in report.findings})

    def test_implementation_claim_without_independent_observation_fails(self) -> None:
        contract = example_contract()
        outcome = run_outcome(contract, "success")
        self_authored = replace(
            outcome.evidence[0],
            provenance=("environment",),
            metadata={**outcome.evidence[0].metadata, "producer_role": "implementation"},
        )
        outcome = replace(outcome, evidence=(self_authored,))
        report = AcceptanceEvaluator().evaluate(
            contract,
            (
                run_structure(contract),
                run_dynamic(contract, "matching"),
                outcome,
            ),
        )
        self.assertEqual(report.verdict, Verdict.FAILED)
        self.assertIn("ACC009", {item.code for item in report.findings})

    def test_expected_failed_and_inconclusive_examples_are_preserved(self) -> None:
        self.assertEqual(run_acceptance("failed").verdict, Verdict.FAILED)
        self.assertEqual(run_acceptance("inconclusive").verdict, Verdict.INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()
