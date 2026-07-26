"""Independent command entry points for every Harness layer."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil


# Package initialization precedes `-m` execution, so remove its one bootstrap
# cache immediately; all later bytecode writes are disabled by __init__.py.
shutil.rmtree(Path(__file__).resolve().parent / "__pycache__", ignore_errors=True)

from parity_harness.contracts import (
    ContractError,
    load_contract_directory,
    load_structure_policy,
    validate_contract_scope,
    validate_contract_set,
)
from parity_harness.contracts.generator import write_candidate_catalog
from parity_harness.paths import artifact_path
from parity_harness.structure.scanner import COVERAGE_FINDING_CODES
from parity_harness.workspace import (
    WorkspaceContractError,
    load_workspace_contract,
    validate_workspace_contract,
)
from parity_harness.workflow import (
    ACCEPTANCE_MODES,
    OUTCOME_SCENARIOS,
    TRACE_SCENARIOS,
    example_contract,
    run_acceptance,
    run_audit,
    run_dynamic,
    run_maintenance,
    run_outcome,
    run_structure,
    run_structure_collection,
    validate_contracts,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Six-layer Rust/Python parity evidence Harness")
    sub = parser.add_subparsers(dest="command", required=True)

    contract = sub.add_parser("contract", help="contract schema operations")
    contract_sub = contract.add_subparsers(dest="contract_command", required=True)
    validate = contract_sub.add_parser("validate")
    validate.add_argument("paths", nargs="*", type=Path)
    generate = contract_sub.add_parser(
        "generate",
        help="derive review-only candidates directly from Cargo and Python source trees",
    )
    generate.add_argument("--scope", required=True)
    generate.add_argument("--output", type=Path)
    validate_accepted = contract_sub.add_parser(
        "validate-accepted",
        help="validate a complete accepted contract collection",
    )
    validate_accepted.add_argument(
        "--scope",
        default="all",
    )

    structure = sub.add_parser("structure", help="run ownership and coordinate checks")
    structure.add_argument(
        "--scope",
        help="check one accepted crate scope or every active scope with 'all'",
    )
    structure.add_argument(
        "--gate",
        choices=("ownership",),
        help="gate only ownership drift while reporting coverage debt separately",
    )

    workspace = sub.add_parser("workspace", help="check Cargo crate classification")
    workspace.add_argument("workspace_command", choices=("check",))

    dynamic = sub.add_parser("dynamic", help="run semantic trace comparisons")
    dynamic_sub = dynamic.add_subparsers(dest="dynamic_command", required=True)
    dynamic_run = dynamic_sub.add_parser("run")
    dynamic_run.add_argument("scenario", choices=(*TRACE_SCENARIOS, "unavailable"))

    outcome = sub.add_parser("outcome", help="run final environment outcome scenarios")
    outcome_sub = outcome.add_subparsers(dest="outcome_command", required=True)
    outcome_run = outcome_sub.add_parser("run")
    outcome_run.add_argument("scenario", choices=tuple(OUTCOME_SCENARIOS))

    accept = sub.add_parser("accept", help="independently accept serialized layer evidence")
    accept.add_argument("mode", choices=tuple(ACCEPTANCE_MODES))

    sub.add_parser("maintain", help="audit Harness ownership and stale scaffolding")
    sub.add_parser("audit", help="compose all public layer entry points")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "workspace":
            report = validate_workspace_contract(load_workspace_contract())
            print(json.dumps(report, indent=2))
            return 0 if report["verdict"] == "verified" else 1
        if args.command == "contract":
            if args.contract_command == "generate":
                catalog = write_candidate_catalog(args.scope, args.output)
                output = (
                    args.output.resolve()
                    if args.output is not None
                    else Path(__file__).resolve().parent
                    / "contracts"
                    / "generated"
                    / f"{args.scope}.candidates.json"
                )
                print(
                    json.dumps(
                        {
                            "status": "candidate",
                            "output": str(output),
                            "summary": catalog["summary"],
                        },
                        indent=2,
                    )
                )
                return 0
            if args.contract_command == "validate-accepted":
                workspace = load_workspace_contract()
                scopes = (
                    tuple(item.scope for item in workspace.active)
                    if args.scope == "all"
                    else (workspace.crate(args.scope).scope,)
                )
                counts: dict[str, int] = {}
                accepted_contracts = []
                for scope in scopes:
                    crate = workspace.crate(scope)
                    contract_root = (
                        Path(__file__).resolve().parent / "contracts" / "accepted" / scope
                    )
                    contracts = load_contract_directory(contract_root, allow_empty=True)
                    policy = load_structure_policy(
                        contract_root.parent / f"{scope}.policy.json"
                    )
                    validate_contract_scope(
                        contracts,
                        scope=scope,
                        rust_crate=crate.rust_crate,
                        rust_root=crate.rust_root,
                        python_root=crate.python_root,
                        baseline_commit=workspace.baseline_commit,
                        policy=policy,
                    )
                    accepted_contracts.extend(contracts)
                    counts[scope] = len(contracts)
                if accepted_contracts:
                    validate_contract_set(accepted_contracts)
                print(
                    json.dumps(
                        {
                            "status": "accepted",
                            "scope": args.scope,
                            "scopes": len(scopes),
                            "contracts": sum(counts.values()),
                            "contract_counts": counts,
                        },
                        indent=2,
                    )
                )
                return 0
            contracts = validate_contracts(tuple(args.paths))
            print(json.dumps({"validated": [item.contract_id for item in contracts]}, indent=2))
            return 0
        if args.command == "structure":
            if args.scope:
                workspace = load_workspace_contract()
                scopes = (
                    tuple(item.scope for item in workspace.active)
                    if args.scope == "all"
                    else (workspace.crate(args.scope).scope,)
                )
                scope_reports: dict[str, dict[str, object]] = {}
                detailed_scope_reports: dict[str, dict[str, object]] = {}
                all_findings = []
                contract_count = 0
                for scope in scopes:
                    accepted_root = Path(__file__).resolve().parent / "contracts" / "accepted"
                    contracts = load_contract_directory(
                        accepted_root / scope,
                        allow_empty=True,
                    )
                    policy = load_structure_policy(accepted_root / f"{scope}.policy.json")
                    crate = workspace.crate(scope)
                    validate_contract_scope(
                        contracts,
                        scope=scope,
                        rust_crate=crate.rust_crate,
                        rust_root=crate.rust_root,
                        python_root=crate.python_root,
                        baseline_commit=workspace.baseline_commit,
                        policy=policy,
                    )
                    result = run_structure_collection(
                        contracts,
                        policy=policy,
                        output=artifact_path("structure", f"accepted-{scope}.json"),
                    )
                    contract_count += len(contracts)
                    all_findings.extend(result.findings)
                    scope_ownership_findings = tuple(
                        item
                        for item in result.findings
                        if item.code not in COVERAGE_FINDING_CODES
                    )
                    scope_coverage_findings = tuple(
                        item
                        for item in result.findings
                        if item.code in COVERAGE_FINDING_CODES
                    )
                    scope_reports[scope] = {
                        "contracts": len(contracts),
                        "ownership_verdict": (
                            "failed" if scope_ownership_findings else "verified"
                        ),
                        "coverage_verdict": (
                            "partial" if scope_coverage_findings else "verified"
                        ),
                        "findings": dict(sorted(Counter(item.code for item in result.findings).items())),
                    }
                    finding_payloads = {
                        code: [
                            {
                                "coordinate": item.coordinate,
                                "message": item.message,
                                "evidence_type": item.evidence_type,
                                "metadata": item.metadata,
                            }
                            for item in result.findings
                            if item.code in codes
                        ]
                        for code, codes in {
                            "orphan_python_files": {"STR012", "STR019"},
                            "merge_or_duplicate_owners": {"STR002", "STR003"},
                            "scattered_owners": {"STR005", "STR006"},
                            "duplicate_symbols": {"STR021"},
                            "foreign_items": {"STR017"},
                        }.items()
                    }
                    foreign_moves: dict[tuple[str, str, str], set[str]] = {}
                    ambiguous_foreign_moves: dict[
                        tuple[str, str, str], set[str]
                    ] = {}
                    for item in result.findings:
                        if item.code != "STR017":
                            continue
                        python_owner = str(item.metadata.get("python_owner", item.coordinate))
                        symbol = str(item.metadata.get("symbol", ""))
                        rust_owners = item.metadata.get("rust_owners", ())
                        for rust_owner in rust_owners:
                            key = (
                                python_owner,
                                str(rust_owner.get("module", "")),
                                str(rust_owner.get("source", "")),
                            )
                            foreign_moves.setdefault(key, set()).add(symbol)
                            if len(rust_owners) > 1:
                                ambiguous_foreign_moves.setdefault(key, set()).add(
                                    symbol
                                )
                    migration_plan = {
                        "foreign_item_moves": [
                            {
                                "python_owner": python_owner,
                                "rust_module": rust_module,
                                "rust_source": rust_source,
                                "symbols": sorted(symbols),
                                "ambiguous_symbols": sorted(
                                    ambiguous_foreign_moves.get(
                                        (python_owner, rust_module, rust_source), set()
                                    )
                                ),
                                "requires_disambiguation": bool(
                                    ambiguous_foreign_moves.get(
                                        (python_owner, rust_module, rust_source)
                                    )
                                ),
                                "recommendation": (
                                    (
                                        "Move only the non-ambiguous symbols into this Rust-"
                                        "aligned Python owner. Do not assign ambiguous_symbols "
                                        "until Rust call-site or re-export evidence selects one "
                                        "owner."
                                    )
                                    if ambiguous_foreign_moves.get(
                                        (python_owner, rust_module, rust_source)
                                    )
                                    else (
                                        "Move these existing implementations into the single "
                                        "Python module-file or continuous package owned by the "
                                        "listed Rust module; keep only proven Rust re-exports in "
                                        "the current parent owner."
                                    )
                                ),
                            }
                            for (
                                python_owner,
                                rust_module,
                                rust_source,
                            ), symbols in sorted(foreign_moves.items())
                        ],
                        "unowned_python_files": [
                            {
                                "path": item.coordinate,
                                "python_symbols": item.metadata.get(
                                    "python_symbols", []
                                ),
                                "rust_symbol_matches": item.metadata.get(
                                    "rust_symbol_matches", []
                                ),
                                "recommendation": (
                                    "Review this production file against the Cargo module "
                                    "graph and either map it to one Rust owner, document a "
                                    "real intentional-adapter boundary, or migrate its items "
                                    "to their Rust-aligned owners."
                                ),
                            }
                            for item in result.findings
                            if item.code in {"STR012", "STR019"}
                        ],
                    }
                    detailed_scope_reports[scope] = {
                        **scope_reports[scope],
                        "uncovered_rust_modules": list(policy.uncovered_rust_modules),
                        **finding_payloads,
                        "intentional_adapters": list(policy.allowed_unowned),
                        "migration_plan": migration_plan,
                    }
                counts = Counter(item.code for item in all_findings)
                ownership_findings = tuple(
                    item for item in all_findings if item.code not in COVERAGE_FINDING_CODES
                )
                coverage_findings = tuple(
                    item for item in all_findings if item.code in COVERAGE_FINDING_CODES
                )
                ownership_verdict = "failed" if ownership_findings else "verified"
                coverage_verdict = "partial" if coverage_findings else "verified"
                combined_verdict = (
                    "failed"
                    if ownership_verdict == "failed"
                    else coverage_verdict
                )
                report = {
                            "scope": args.scope,
                            "verdict": combined_verdict,
                            "ownership_verdict": ownership_verdict,
                            "coverage_verdict": coverage_verdict,
                            "scopes": len(scopes),
                            "contracts": contract_count,
                            "finding_counts": dict(sorted(counts.items())),
                            "scope_reports": scope_reports,
                            "sample_findings": [
                                {
                                    "code": item.code,
                                    "coordinate": item.coordinate,
                                    "message": item.message,
                                }
                                for item in all_findings[:20]
                            ],
                            "artifact_root": str(artifact_path("structure")),
                }
                migration_plans = [
                    scope_report["migration_plan"]
                    for scope_report in detailed_scope_reports.values()
                ]
                foreign_move_groups = [
                    item
                    for plan in migration_plans
                    for item in plan["foreign_item_moves"]
                ]
                unowned_file_plans = [
                    item
                    for plan in migration_plans
                    for item in plan["unowned_python_files"]
                ]
                foreign_item_findings = [
                    item
                    for scope_report in detailed_scope_reports.values()
                    for item in scope_report["foreign_items"]
                ]
                machine_report = {
                    **report,
                    "scope_reports": detailed_scope_reports,
                    "migration_summary": {
                        "foreign_item_groups": len(foreign_move_groups),
                        "foreign_item_findings": len(foreign_item_findings),
                        "foreign_symbol_assignments": sum(
                            len(item["symbols"]) for item in foreign_move_groups
                        ),
                        "ambiguous_foreign_items": sum(
                            len(item["metadata"].get("rust_owners", ())) > 1
                            for item in foreign_item_findings
                        ),
                        "unowned_python_files": len(unowned_file_plans),
                        "unowned_with_rust_symbol_matches": sum(
                            bool(item["rust_symbol_matches"])
                            for item in unowned_file_plans
                        ),
                        "unowned_without_rust_symbol_matches": sum(
                            not item["rust_symbol_matches"]
                            for item in unowned_file_plans
                        ),
                    },
                    "workspace_classification": {
                        "total": len(workspace.crates),
                        "active": len(workspace.active),
                        "deferred": sum(
                            item.disposition == "deferred"
                            for item in workspace.crates
                        ),
                    },
                    "deferred_scopes": {
                        item.scope: item.reason
                        for item in workspace.crates
                        if item.disposition == "deferred"
                    },
                }
                report_path = artifact_path(
                    "structure", f"accepted-{args.scope}-summary.json"
                )
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(machine_report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                report["machine_report"] = str(report_path)
                print(json.dumps(report, indent=2))
                if args.gate == "ownership":
                    return 0 if ownership_verdict == "verified" else 1
                return 0 if combined_verdict == "verified" else 1
            result = run_structure(example_contract(), output=artifact_path("structure", "example.json"))
            print(json.dumps(result.to_dict(), indent=2))
            return 0 if result.verdict.value == "verified" else 1
        if args.command == "dynamic":
            result = run_dynamic(example_contract(), args.scenario, output=artifact_path("dynamic", f"{args.scenario}.json"))
            print(json.dumps(result.to_dict(), indent=2))
            return 0 if result.verdict.value == "verified" else 1
        if args.command == "outcome":
            result = run_outcome(example_contract(), args.scenario, output=artifact_path("outcomes", f"{args.scenario}.json"))
            print(json.dumps(result.to_dict(), indent=2))
            return 0 if result.verdict.value == "verified" else 1
        if args.command == "accept":
            report = run_acceptance(args.mode)
            print(json.dumps(report.to_dict(), indent=2))
            expected = args.mode
            return 0 if report.verdict.value == expected else 1
        if args.command == "maintain":
            result = run_maintenance(output=artifact_path("maintenance", "result.json"))
            print(json.dumps(result.to_dict(), indent=2))
            return 0 if result.verdict.value == "verified" else 1
        summary = run_audit()
        print(json.dumps(summary, indent=2))
        return 0 if summary["harness_self_test"] == "verified" else 1
    except (ContractError, WorkspaceContractError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
