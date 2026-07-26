"""Accepted contracts must be coherent before structure checks consume them."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from parity_harness.contracts import (
    ContractError,
    load_contract_directory,
    load_structure_policy,
    validate_contract_scope,
    validate_contract_set,
)
from parity_harness.paths import HARNESS_ROOT
from parity_harness.model import Verdict
from parity_harness.workflow import run_structure_collection


class AcceptedContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contracts = load_contract_directory(
            HARNESS_ROOT / "contracts" / "accepted" / "tui"
        )
        self.policy = load_structure_policy(
            HARNESS_ROOT / "contracts" / "accepted" / "tui.policy.json"
        )

    def test_tui_accepted_collection_is_coherent(self) -> None:
        self.assertEqual(len(self.contracts), 294)
        self.assertTrue(
            all(contract.evidence_status.value == "mapped" for contract in self.contracts)
        )
        by_module = {contract.rust["module"]: contract for contract in self.contracts}
        self.assertEqual(
            by_module["slash_command"].python_owner,
            "pycodex/tui/slash_command.py",
        )

    def test_real_tui_scope_has_one_owner_or_documented_exception_per_file(self) -> None:
        result = run_structure_collection(self.contracts, policy=self.policy)

        self.assertEqual(result.verdict, Verdict.VERIFIED)
        self.assertFalse(result.findings)

    def test_duplicate_owner_and_implementation_are_rejected_before_structure(self) -> None:
        contract = next(
            item for item in self.contracts if item.rust["module"] == "slash_command"
        )
        duplicate = replace(contract, contract_id="codex-tui.other")
        with self.assertRaisesRegex(ContractError, "duplicate Python owner"):
            validate_contract_set((contract, duplicate))

    def test_duplicate_rust_module_is_rejected_before_structure(self) -> None:
        contract = next(
            item for item in self.contracts if item.rust["module"] == "slash_command"
        )
        python = dict(contract.python)
        python["owner"] = "pycodex/tui/version.py"
        python["implementation_files"] = ("pycodex/tui/version.py",)
        duplicate = replace(
            contract,
            contract_id="codex-tui.other",
            python=python,
        )
        with self.assertRaisesRegex(ContractError, "duplicate Rust module"):
            validate_contract_set((contract, duplicate))

    def test_candidate_cannot_enter_accepted_collection(self) -> None:
        contract = next(
            item for item in self.contracts if item.rust["module"] == "slash_command"
        )
        candidate = replace(contract, evidence_status=type(contract.evidence_status).CANDIDATE)
        with self.assertRaisesRegex(ContractError, "unresolved evidence status"):
            validate_contract_set((candidate,))

    def test_unrelated_rust_and_python_anchor_lists_are_rejected(self) -> None:
        contract = next(
            item for item in self.contracts if item.rust["module"] == "slash_command"
        )
        python = dict(contract.python)
        python["anchors"] = ("SlashCommand",)
        with self.assertRaisesRegex(ContractError, "must be the same mapped symbols"):
            validate_contract_set((replace(contract, python=python),))

    def test_contract_filed_under_an_unrelated_scope_is_rejected(self) -> None:
        contract = next(
            item for item in self.contracts if item.rust["module"] == "slash_command"
        )
        with self.assertRaisesRegex(ContractError, "does not belong to scope core"):
            validate_contract_scope(
                (contract,),
                scope="core",
                rust_crate="codex-core",
                rust_root="codex/codex-rs/core",
                python_root="pycodex/core",
                baseline_commit=contract.rust["baseline_commit"],
                policy=load_structure_policy(
                    HARNESS_ROOT / "contracts" / "accepted" / "core.policy.json"
                ),
            )


class CoreAcceptedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contracts = load_contract_directory(
            HARNESS_ROOT / "contracts" / "accepted" / "core"
        )
        cls.policy = load_structure_policy(
            HARNESS_ROOT / "contracts" / "accepted" / "core.policy.json"
        )

    def test_core_accepted_collection_covers_the_complete_rust_inventory(self) -> None:
        self.assertEqual(len(self.contracts), 254)
        self.assertTrue(
            all(contract.evidence_status.value == "mapped" for contract in self.contracts)
        )

    def test_core_scope_has_no_structure_inventory_gaps(self) -> None:
        result = run_structure_collection(self.contracts, policy=self.policy)
        counts: dict[str, int] = {}
        for finding in result.findings:
            counts[finding.code] = counts.get(finding.code, 0) + 1

        self.assertEqual(result.verdict, Verdict.VERIFIED)
        self.assertEqual(counts, {})


class AppServerAcceptedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contracts = load_contract_directory(
            HARNESS_ROOT / "contracts" / "accepted" / "app-server"
        )
        cls.policy = load_structure_policy(
            HARNESS_ROOT / "contracts" / "accepted" / "app-server.policy.json"
        )

    def test_all_app_server_modules_have_reviewed_owners(self) -> None:
        mapped_modules = {contract.rust["module"] for contract in self.contracts}
        expected_mapped = {
            "crate",
            "analytics_utils",
            "command_exec",
            "config_manager_service",
            "in_process",
            "message_processor",
            "outgoing_message",
            "request_processors",
            "transport",
            "extensions",
        }

        self.assertTrue(expected_mapped.issubset(mapped_modules))
        self.assertEqual(len(self.contracts), 60)
        self.assertEqual(self.policy.coverage_expectation, "verified")
        self.assertEqual(self.policy.uncovered_rust_modules, ())
        self.assertEqual(self.policy.uncovered_python_files, ())

    def test_app_server_inventory_has_no_undeclared_structure_gap(self) -> None:
        result = run_structure_collection(self.contracts, policy=self.policy)
        counts: dict[str, int] = {}
        for finding in result.findings:
            counts[finding.code] = counts.get(finding.code, 0) + 1

        self.assertNotIn("STR012", counts)
        self.assertNotIn("STR018", counts)
        self.assertNotIn("STR020", counts)
        self.assertEqual(counts, {})



if __name__ == "__main__":
    unittest.main()
