"""Audits the harness without changing or deleting any file."""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
from pathlib import Path
import subprocess
from typing import Iterable

from parity_harness.contracts import ModuleContract
from parity_harness.model import Evidence, Finding, LayerResult, Verdict
from parity_harness.paths import HARNESS_ROOT, REPO_ROOT
from parity_harness.registry import CHECKERS, CheckerRegistration


def _module_name(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names if alias.name.startswith("parity_harness"))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("parity_harness"):
                values.add(node.module)
    return values


def _production_modules(root: Path) -> dict[str, Path]:
    values = {}
    for path in root.rglob("*.py"):
        relative_parts = path.relative_to(root).parts
        if "tests" in relative_parts or "fixtures" in relative_parts or ".artifacts" in relative_parts:
            continue
        values[_module_name(path)] = path
    return values


def _reachable(modules: dict[str, Path], entry: str) -> set[str]:
    graph = {name: _imports(path) for name, path in modules.items()}
    seen: set[str] = set()
    pending = [entry]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for imported in graph.get(name, ()):
            candidates = [module for module in modules if module == imported or module.startswith(f"{imported}.")]
            pending.extend(candidates)
    return seen


class HarnessMaintenanceAuditor:
    CHECKER_ID = "maintenance.harness-health"

    def __init__(
        self,
        *,
        harness_root: Path = HARNESS_ROOT,
        registrations: Iterable[CheckerRegistration] = CHECKERS,
    ) -> None:
        self.harness_root = harness_root.resolve()
        self.registrations = tuple(registrations)

    def audit(self, contracts: Iterable[ModuleContract]) -> LayerResult:
        contracts = tuple(contracts)
        findings: list[Finding] = []
        self._check_registrations(findings)
        self._check_reachability(findings)
        self._check_contracts(contracts, findings)
        self._check_fixtures(contracts, findings)
        self._check_artifacts(findings)
        evidence = Evidence(
            evidence_id="parity-harness.maintenance",
            evidence_type="harness-health",
            coordinate="parity_harness",
            source=self.CHECKER_ID,
            status="verified" if not findings else "implemented",
            detail="Audited checker ownership, reachability, contracts, fixtures, baselines, and artifact placement",
            provenance=("harness",),
        )
        return LayerResult(
            "maintenance",
            "parity-harness",
            Verdict.FAILED if any(item.severity == "error" for item in findings) else Verdict.VERIFIED,
            evidence=(evidence,),
            findings=tuple(findings),
        )

    def _check_registrations(self, findings: list[Finding]) -> None:
        for attribute, code in (
            ("checker_id", "MNT001"),
            ("responsibility", "MNT002"),
        ):
            counts = Counter(getattr(item, attribute) for item in self.registrations)
            for value, count in counts.items():
                if count > 1:
                    findings.append(
                        Finding(code, f"duplicate checker {attribute}: {value}", coordinate=value, evidence_type="checker-registry")
                    )
        owners: dict[str, list[str]] = defaultdict(list)
        for item in self.registrations:
            for evidence_type in item.evidence_types:
                owners[evidence_type].append(item.layer)
        for evidence_type, layers in owners.items():
            if len(layers) > 1:
                findings.append(
                    Finding(
                        "MNT003",
                        f"evidence type is judged by multiple layers: {', '.join(layers)}",
                        coordinate=evidence_type,
                        evidence_type="layer-overlap",
                    )
                )

    def _check_reachability(self, findings: list[Finding]) -> None:
        modules = _production_modules(self.harness_root)
        reachable = _reachable(modules, "parity_harness.__main__")
        exempt = {"parity_harness", "parity_harness.__main__"}
        for name, path in modules.items():
            if name in exempt or name in reachable:
                continue
            findings.append(
                Finding(
                    "MNT004",
                    "production Harness module is unreachable from the aggregate entry point",
                    coordinate=path.relative_to(REPO_ROOT).as_posix(),
                    evidence_type="module-reachability",
                )
            )
        registered = {item.module for item in self.registrations}
        for module in sorted(registered - set(modules)):
            findings.append(
                Finding("MNT005", "checker registration points to a missing module", coordinate=module, evidence_type="checker-registry")
            )
        for module in sorted(registered - reachable):
            findings.append(
                Finding("MNT006", "registered checker is never reached by the aggregate entry point", coordinate=module, evidence_type="module-reachability")
            )

    def _check_contracts(self, contracts: tuple[ModuleContract, ...], findings: list[Finding]) -> None:
        try:
            current_baseline = subprocess.run(
                ("git", "-C", str(REPO_ROOT / "codex"), "rev-parse", "HEAD"),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            current_baseline = ""
        registered_by_layer = {item.layer: item.checker_id for item in self.registrations}
        referenced_checkers: set[str] = set()
        for contract in contracts:
            for layer in ("structure",):
                checker = str(contract.checks[layer].get("checker", ""))
                referenced_checkers.add(checker)
                if not checker or registered_by_layer.get(layer) != checker:
                    findings.append(
                        Finding(
                            "MNT012",
                            f"contract references an unknown or wrong-layer checker for {layer}: {checker!r}",
                            coordinate=contract.contract_id,
                            evidence_type="checker-reference",
                        )
                    )
            paths = (
                contract.rust["workspace"],
                contract.rust["source"],
                contract.python_owner,
                *contract.python["implementation_files"],
            )
            for relative in dict.fromkeys(paths):
                if not (REPO_ROOT / relative).exists():
                    findings.append(
                        Finding("MNT007", "contract coordinate is stale or missing", coordinate=relative, evidence_type="contract-reference")
                    )
            if current_baseline and contract.rust["baseline_commit"] != current_baseline:
                findings.append(
                    Finding(
                        "MNT008",
                        f"contract baseline differs from Rust HEAD {current_baseline}",
                        severity="warning",
                        coordinate=contract.contract_id,
                        evidence_type="baseline-freshness",
                    )
                )
        expected_contract_checkers = {
            item.checker_id
            for item in self.registrations
            if item.layer == "structure"
        }
        for checker in sorted(expected_contract_checkers - referenced_checkers):
            findings.append(
                Finding(
                    "MNT013",
                    "registered contract checker is not referenced by any contract",
                    coordinate=checker,
                    evidence_type="checker-reference",
                )
            )

    def _check_fixtures(self, contracts: tuple[ModuleContract, ...], findings: list[Finding]) -> None:
        referenced = {value for contract in contracts for value in contract.fixture_refs}
        fixture_root = self.harness_root / "fixtures"
        assets = {
            path.relative_to(REPO_ROOT).as_posix()
            for directory in (fixture_root / "traces", fixture_root / "outcomes")
            if directory.exists()
            for path in directory.rglob("*")
            if path.is_file()
        }
        for path in sorted(assets - referenced):
            findings.append(
                Finding(
                    "MNT009",
                    "fixture is not referenced by a real contract path",
                    coordinate=path,
                    evidence_type="fixture-reachability",
                )
            )
        for path in sorted(referenced):
            if not (REPO_ROOT / path).is_file():
                findings.append(
                    Finding("MNT010", "contract references a missing fixture", coordinate=path, evidence_type="fixture-reference")
                )

    def _check_artifacts(self, findings: list[Finding]) -> None:
        generated_suffixes = (".report.json", ".report.md", ".actual.json", ".trace-output.json")
        local_artifacts = (self.harness_root / ".artifacts").resolve()
        for path in self.harness_root.rglob("*"):
            if not path.is_file() or local_artifacts in path.resolve().parents:
                continue
            if path.name.endswith(generated_suffixes):
                findings.append(
                    Finding(
                        "MNT011",
                        "generated artifact exists outside parity_harness/.artifacts",
                        coordinate=path.relative_to(REPO_ROOT).as_posix(),
                        evidence_type="artifact-placement",
                    )
                )
