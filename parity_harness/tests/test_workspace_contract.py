from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from parity_harness.__main__ import main
from parity_harness.paths import HARNESS_ROOT, REPO_ROOT
from parity_harness.workspace import (
    WorkspaceContractError,
    load_workspace_contract,
    validate_workspace_contract,
)


class WorkspaceContractTests(unittest.TestCase):
    def test_harness_has_no_product_porting_dependency(self) -> None:
        offenders: list[str] = []
        for path in HARNESS_ROOT.rglob("*.py"):
            if "tests" in path.relative_to(HARNESS_ROOT).parts:
                continue
            if ("pycodex" + ".porting") in path.read_text(encoding="utf-8-sig"):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_workspace_contract_matches_cargo_inventory(self) -> None:
        contract = load_workspace_contract()
        result = validate_workspace_contract(contract)

        self.assertEqual(result["crates"], len(contract.crates))
        self.assertEqual(result["active"], len(contract.active))
        self.assertEqual(
            result["deferred"],
            sum(item.disposition == "deferred" for item in contract.crates),
        )
        self.assertEqual(result["errors"], [])

    def test_missing_cargo_crate_classification_is_rejected(self) -> None:
        contract = load_workspace_contract()
        modified = replace(contract, crates=contract.crates[1:])

        result = validate_workspace_contract(modified)

        self.assertTrue(any("Cargo crate is not classified" in error for error in result["errors"]))

    def test_duplicate_cargo_crate_classification_is_rejected(self) -> None:
        contract = load_workspace_contract()
        duplicate = replace(contract.crates[0], scope=f"{contract.crates[0].scope}-duplicate")
        modified = replace(contract, crates=(*contract.crates, duplicate))

        result = validate_workspace_contract(modified)

        self.assertTrue(any("duplicate Rust crate" in error for error in result["errors"]))

    def test_deferred_crate_without_a_reviewable_reason_is_rejected(self) -> None:
        source = json.loads(
            load_workspace_contract().source_path.read_text(encoding="utf-8")
        )
        source["crates"][0]["disposition"] = "deferred"
        source["crates"][0]["reason"] = ""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspace.json"
            path.write_text(json.dumps(source), encoding="utf-8")

            with self.assertRaisesRegex(WorkspaceContractError, "requires a reason"):
                load_workspace_contract(path)

    def test_deferred_scope_cannot_hide_python_product_files(self) -> None:
        contract = load_workspace_contract()
        core = contract.crate("core")
        disguised = replace(
            core,
            disposition="deferred",
            reason="counterexample",
        )
        modified = replace(
            contract,
            crates=tuple(
                disguised if item.scope == core.scope else item
                for item in contract.crates
            ),
        )

        result = validate_workspace_contract(modified)

        self.assertTrue(
            any(
                "deferred scope core contains Python product files" in error
                for error in result["errors"]
            )
        )

    def test_workspace_check_cli_is_machine_readable(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["workspace", "check"])

        report = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(report["verdict"], "verified")
        self.assertEqual(report["crates"], len(load_workspace_contract().crates))


if __name__ == "__main__":
    unittest.main()
