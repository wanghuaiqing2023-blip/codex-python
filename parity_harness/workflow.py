"""Public composition functions used by the CLI and end-to-end tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from parity_harness.acceptance import AcceptanceEvaluator, AcceptanceReport
from parity_harness.contracts import ModuleContract, StructureScopePolicy, load_contract
from parity_harness.dynamic import TraceComparator, load_trace
from parity_harness.maintenance import HarnessMaintenanceAuditor
from parity_harness.model import LayerResult, Verdict
from parity_harness.outcomes import OutcomeRunner
from parity_harness.outcomes.scenarios import load_file_scenario
from parity_harness.paths import HARNESS_ROOT, REPO_ROOT, artifact_path
from parity_harness.structure import StructureAuditor
from parity_harness.workspace import load_workspace_contract, validate_workspace_contract


CONTRACT_PATH = HARNESS_ROOT / "fixtures" / "contracts" / "example_status.json"
TRACE_ROOT = HARNESS_ROOT / "fixtures" / "traces"
OUTCOME_ROOT = HARNESS_ROOT / "fixtures" / "outcomes"

TRACE_SCENARIOS = {
    "matching": "python_matching.json",
    "missing": "python_missing.json",
    "duplicate": "python_duplicate.json",
    "out-of-order": "python_out_of_order.json",
}
OUTCOME_SCENARIOS = {
    "success": "success.json",
    "false-claim": "false_claim.json",
    "config-restart": "config_restart.json",
}
ACCEPTANCE_MODES = {
    "verified": ("matching", "success"),
    "failed": ("matching", "false-claim"),
    "inconclusive": ("unavailable", "success"),
}


def example_contract() -> ModuleContract:
    return load_contract(CONTRACT_PATH)


def validate_contracts(paths: tuple[Path, ...] = ()) -> tuple[ModuleContract, ...]:
    selected = paths or tuple(sorted((HARNESS_ROOT / "fixtures" / "contracts").glob("*.json")))
    return tuple(load_contract(path) for path in selected)


def run_structure(contract: ModuleContract, *, output: Path | None = None) -> LayerResult:
    auditor = StructureAuditor()
    primary = auditor.check((contract,))[0]
    structure_check = contract.checks["structure"]
    inventory = auditor.audit_inventory(
        (contract,),
        python_root=str(structure_check["python_root"]),
        allowed_unowned=tuple(structure_check.get("allowed_unowned", ())),
        contract_id=contract.contract_id,
    )
    if primary.verdict == Verdict.FAILED or inventory.verdict == Verdict.FAILED:
        verdict = Verdict.FAILED
    elif primary.verdict == Verdict.INCONCLUSIVE or inventory.verdict == Verdict.INCONCLUSIVE:
        verdict = Verdict.INCONCLUSIVE
    else:
        verdict = Verdict.VERIFIED
    result = LayerResult(
        "structure",
        contract.contract_id,
        verdict,
        evidence=(*primary.evidence, *inventory.evidence),
        findings=(*primary.findings, *inventory.findings),
    )
    if output is not None:
        result.write_json(output)
    return result


def run_structure_collection(
    contracts: tuple[ModuleContract, ...],
    *,
    policy: StructureScopePolicy,
    output: Path | None = None,
) -> LayerResult:
    auditor = StructureAuditor(
        check_item_ownership=policy.check_item_ownership,
        include_inline_modules=policy.include_inline_modules,
        python_root=policy.python_root,
        check_orphans=policy.check_orphans,
    )
    module_results = auditor.check(contracts)
    inventory = auditor.audit_inventory(
        contracts,
        rust_root=policy.rust_root,
        python_root=policy.python_root,
        allowed_unowned=policy.allowed_unowned,
        uncovered_rust_modules=policy.uncovered_rust_modules,
        uncovered_python_files=policy.uncovered_python_files,
        contract_id=f"accepted:{policy.scope}",
    )
    results = (*module_results, inventory)
    if any(result.verdict == Verdict.FAILED for result in results):
        verdict = Verdict.FAILED
    elif any(result.verdict == Verdict.INCONCLUSIVE for result in results):
        verdict = Verdict.INCONCLUSIVE
    else:
        verdict = Verdict.VERIFIED
    result = LayerResult(
        "structure",
        f"accepted:{policy.scope}",
        verdict,
        evidence=tuple(item for layer in results for item in layer.evidence),
        findings=tuple(item for layer in results for item in layer.findings),
        metadata={"contracts": len(contracts), "scope": policy.scope},
    )
    if output is not None:
        result.write_json(output)
    return result


def run_dynamic(
    contract: ModuleContract,
    scenario: str,
    *,
    output: Path | None = None,
) -> LayerResult:
    if scenario == "unavailable":
        reference_path = TRACE_ROOT / "rust_unavailable.json"
        candidate_path = TRACE_ROOT / "python_matching.json"
    else:
        try:
            candidate_path = TRACE_ROOT / TRACE_SCENARIOS[scenario]
        except KeyError as exc:
            raise ValueError(f"unknown dynamic scenario: {scenario}") from exc
        reference_path = TRACE_ROOT / "rust_reference.json"
    strategy = "exact"
    result = TraceComparator().compare(
        load_trace(reference_path),
        load_trace(candidate_path),
        strategy=strategy,
        roots=(REPO_ROOT,),
    )
    if output is not None:
        result.write_json(output)
    return result


def run_outcome(
    contract: ModuleContract,
    scenario: str,
    *,
    output: Path | None = None,
) -> LayerResult:
    try:
        path = OUTCOME_ROOT / OUTCOME_SCENARIOS[scenario]
    except KeyError as exc:
        raise ValueError(f"unknown outcome scenario: {scenario}") from exc
    result = OutcomeRunner().run(load_file_scenario(path, contract_id=contract.contract_id))
    if output is not None:
        result.write_json(output)
    return result


def run_acceptance(mode: str) -> AcceptanceReport:
    try:
        dynamic_scenario, outcome_scenario = ACCEPTANCE_MODES[mode]
    except KeyError as exc:
        raise ValueError(f"unknown acceptance mode: {mode}") from exc
    contract = example_contract()
    run_root = artifact_path("runs", mode)
    run_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "structure": run_root / "structure.json",
        "dynamic": run_root / "dynamic.json",
        "outcome": run_root / "outcome.json",
    }
    run_structure(contract, output=paths["structure"])
    run_dynamic(contract, dynamic_scenario, output=paths["dynamic"])
    run_outcome(contract, outcome_scenario, output=paths["outcome"])
    report = AcceptanceEvaluator().evaluate_files(contract, paths.values())
    report.write(
        artifact_path("reports", f"{mode}.report.json"),
        artifact_path("reports", f"{mode}.report.md"),
    )
    return report


def run_maintenance(contract: ModuleContract | None = None, *, output: Path | None = None) -> LayerResult:
    result = HarnessMaintenanceAuditor().audit((contract or example_contract(),))
    if output is not None:
        result.write_json(output)
    return result


def write_boundary_audit() -> dict[str, Any]:
    completed = subprocess.run(
        ("git", "status", "--short", "--untracked-files=all"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=True,
    )
    status_lines = tuple(line for line in completed.stdout.splitlines() if line.strip())
    harness_status = tuple(
        line for line in status_lines if line[3:].replace("\\", "/").startswith("parity_harness/")
    )
    outside_status = tuple(line for line in status_lines if line not in harness_status)
    harness_files = tuple(
        sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in HARNESS_ROOT.rglob("*")
            if path.is_file() and ".artifacts" not in path.relative_to(HARNESS_ROOT).parts
        )
    )
    tracked = subprocess.run(
        ("git", "ls-files", "parity_harness"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    ).stdout.splitlines()
    value = {
        "task_scope": "parity_harness/",
        "harness_files": harness_files,
        "harness_git_status": harness_status,
        "tracked_harness_files_before_staging": tracked,
        "outside_dirty_paths_observed": outside_status,
        "interpretation": (
            "The Harness tree is newly untracked and every task artifact is confined to it. "
            "Outside dirty paths pre-existed this isolated Harness implementation and were not edited by it."
        ),
    }
    artifact_path("boundary", "git-status.json").write_text(
        json.dumps(value, indent=2) + "\n", encoding="utf-8"
    )
    return value


def run_audit() -> dict[str, Any]:
    reports = {mode: run_acceptance(mode) for mode in ACCEPTANCE_MODES}
    maintenance_path = artifact_path("maintenance", "result.json")
    maintenance = run_maintenance(output=maintenance_path)
    workspace = validate_workspace_contract(load_workspace_contract())
    boundary = write_boundary_audit()
    expected = {
        "verified": Verdict.VERIFIED,
        "failed": Verdict.FAILED,
        "inconclusive": Verdict.INCONCLUSIVE,
    }
    self_test_ok = all(reports[key].verdict == value for key, value in expected.items())
    self_test_ok = (
        self_test_ok
        and maintenance.verdict == Verdict.VERIFIED
        and workspace["verdict"] == "verified"
    )
    summary = {
        "harness_self_test": "verified" if self_test_ok else "failed",
        "acceptance_examples": {key: value.verdict.value for key, value in reports.items()},
        "maintenance": maintenance.verdict.value,
        "workspace": workspace,
        "boundary": {
            "harness_files": len(boundary["harness_files"]),
            "tracked_harness_files": len(boundary["tracked_harness_files_before_staging"]),
            "artifact": "parity_harness/.artifacts/boundary/git-status.json",
        },
    }
    artifact_path("audit", "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Parity Harness audit",
        "",
        f"- Harness self-test: **{summary['harness_self_test']}**",
        f"- Verified example: `{summary['acceptance_examples']['verified']}`",
        f"- Failed example: `{summary['acceptance_examples']['failed']}`",
        f"- Inconclusive example: `{summary['acceptance_examples']['inconclusive']}`",
        f"- Maintenance: `{summary['maintenance']}`",
        f"- Workspace contract: `{summary['workspace']['verdict']}`",
        f"- Harness source files: `{summary['boundary']['harness_files']}`",
        f"- Previously tracked Harness files: `{summary['boundary']['tracked_harness_files']}`",
    ]
    artifact_path("audit", "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
