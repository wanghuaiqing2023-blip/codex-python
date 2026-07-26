from __future__ import annotations

import json
import unittest

from parity_harness.contracts import ContractError, load_contract
from parity_harness.paths import ArtifactWorkspace
from parity_harness.workflow import CONTRACT_PATH, example_contract


class ContractTests(unittest.TestCase):
    def test_complete_example_contract_loads(self) -> None:
        contract = example_contract()
        self.assertEqual(contract.contract_id, "harness-fixture.status")
        self.assertEqual(contract.rust_coordinate, "parity-harness-fixture::status")
        self.assertTrue(contract.rust["anchors"])
        self.assertNotIn("behavior", contract.__dataclass_fields__)
        self.assertEqual(set(contract.checks), {"structure"})

    def test_deprecated_behavior_prose_is_rejected(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        value["behavior"] = {"expected_outcomes": ["looks correct"]}
        with ArtifactWorkspace("contract-") as workspace:
            path = workspace / "invalid.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "prose is not executable evidence"):
                load_contract(path)

    def test_non_structure_checks_are_rejected_for_current_milestone(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        value["checks"]["dynamic"] = {"checker": "dynamic.semantic-trace"}
        with ArtifactWorkspace("contract-") as workspace:
            path = workspace / "invalid.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "only structure checks"):
                load_contract(path)

    def test_missing_rust_anchor_is_rejected(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        value["rust"].pop("anchors")
        with ArtifactWorkspace("contract-") as workspace:
            path = workspace / "invalid.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "rust is missing required fields: anchors"):
                load_contract(path)

    def test_empty_rust_anchor_is_rejected(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        value["rust"]["anchors"] = []
        with ArtifactWorkspace("contract-") as workspace:
            path = workspace / "invalid.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "rust.anchors must not be empty"):
                load_contract(path)

    def test_invalid_baseline_and_escaping_path_are_rejected(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        value["rust"]["baseline_commit"] = "short"
        with ArtifactWorkspace("contract-") as workspace:
            path = workspace / "invalid.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "40-character"):
                load_contract(path)

        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        value["python"]["owner"] = "../outside.py"
        with ArtifactWorkspace("contract-") as workspace:
            path = workspace / "invalid.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "repository-relative"):
                load_contract(path)


if __name__ == "__main__":
    unittest.main()
