"""Independent acceptance over serialized layer evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from parity_harness.contracts import ModuleContract
from parity_harness.model import Evidence, Finding, LayerResult, MappingStatus, Verdict


EVIDENCE_LAYERS = ("structure", "dynamic", "outcome")


@dataclass(frozen=True)
class AcceptanceReport:
    contract_id: str
    verdict: Verdict
    layer_verdicts: dict[str, str]
    evidence: tuple[Evidence, ...]
    findings: tuple[Finding, ...]
    rust_coordinate: str
    python_owner: str
    rust_baseline: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["verdict"] = self.verdict.value
        return value

    def to_markdown(self) -> str:
        lines = [
            f"# Acceptance report: `{self.contract_id}`",
            "",
            f"- Verdict: **{self.verdict.value}**",
            f"- Rust: `{self.rust_coordinate}`",
            f"- Python owner: `{self.python_owner}`",
            f"- Rust baseline: `{self.rust_baseline}`",
            "",
            "## Layer verdicts",
            "",
        ]
        for layer in EVIDENCE_LAYERS:
            lines.append(f"- `{layer}`: `{self.layer_verdicts.get(layer, 'missing')}`")
        lines.extend(["", "## Findings", ""])
        if not self.findings:
            lines.append("No acceptance findings.")
        else:
            for finding in self.findings:
                location = f" (`{finding.coordinate}`)" if finding.coordinate else ""
                lines.append(f"- **{finding.code}**{location}: {finding.message}")
        lines.extend(["", "## Evidence", ""])
        for item in self.evidence:
            lines.append(
                f"- `{item.evidence_id}` [{item.evidence_type}] "
                f"status=`{item.status}`, source=`{item.source}`, "
                f"coordinate=`{item.coordinate}`"
            )
        lines.append("")
        return "\n".join(lines)

    def write(self, json_path: Path, markdown_path: Path) -> None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(self.to_markdown(), encoding="utf-8")


class AcceptanceEvaluator:
    CHECKER_ID = "acceptance.independent-evidence"

    def evaluate_files(
        self,
        contract: ModuleContract,
        result_paths: Iterable[Path],
    ) -> AcceptanceReport:
        return self.evaluate(contract, tuple(LayerResult.read_json(path) for path in result_paths))

    def evaluate(
        self,
        contract: ModuleContract,
        results: Iterable[LayerResult],
    ) -> AcceptanceReport:
        results = tuple(results)
        findings: list[Finding] = []
        by_layer: dict[str, LayerResult] = {}
        for result in results:
            if result.contract_id != contract.contract_id:
                findings.append(
                    Finding(
                        "ACC001",
                        "evidence belongs to another contract",
                        coordinate=result.contract_id,
                        evidence_type="evidence-coordinate",
                    )
                )
                continue
            if result.layer in by_layer:
                findings.append(
                    Finding(
                        "ACC002",
                        f"multiple results supplied for layer {result.layer}",
                        coordinate=result.layer,
                        evidence_type="evidence-conflict",
                    )
                )
            by_layer[result.layer] = result

        required = EVIDENCE_LAYERS
        missing = [layer for layer in required if layer not in by_layer]
        for layer in missing:
            findings.append(
                Finding(
                    "ACC003",
                    f"required layer evidence is missing: {layer}",
                    severity="warning",
                    coordinate=layer,
                    evidence_type="missing-evidence",
                )
            )

        all_evidence = tuple(item for result in results for item in result.evidence)
        evidence_ids: dict[str, Evidence] = {}
        for item in all_evidence:
            prior = evidence_ids.get(item.evidence_id)
            if prior is not None and prior != item:
                findings.append(
                    Finding(
                        "ACC004",
                        f"conflicting evidence records share ID {item.evidence_id}",
                        coordinate=item.evidence_id,
                        evidence_type="evidence-conflict",
                    )
                )
            evidence_ids[item.evidence_id] = item
            if (
                item.metadata.get("producer_role") == "implementation"
                and "independent" not in item.provenance
            ):
                findings.append(
                    Finding(
                        "ACC009",
                        "implementation-authored completion evidence lacks independent observation",
                        coordinate=item.evidence_id,
                        evidence_type="self-evaluation-bias",
                    )
                )

        structure = by_layer.get("structure")
        dynamic = by_layer.get("dynamic")
        outcome = by_layer.get("outcome")
        if structure and structure.verdict == Verdict.VERIFIED:
            if not any("cross" in item.provenance for item in structure.evidence):
                findings.append(
                    Finding("ACC005", "structure verdict lacks cross-language evidence", evidence_type="provenance")
                )
        if dynamic and dynamic.verdict == Verdict.VERIFIED:
            if not any({"rust", "python", "cross"}.issubset(set(item.provenance)) for item in dynamic.evidence):
                findings.append(
                    Finding(
                        "ACC006",
                        "Python-only dynamic evidence cannot prove Rust parity",
                        evidence_type="provenance",
                    )
                )
        if outcome and outcome.verdict == Verdict.VERIFIED:
            if not any("environment" in item.provenance for item in outcome.evidence):
                findings.append(
                    Finding("ACC007", "outcome verdict lacks environment evidence", evidence_type="provenance")
                )

        if contract.evidence_status in {MappingStatus.CANDIDATE, MappingStatus.MAPPED}:
            findings.append(
                Finding(
                    "ACC008",
                    f"contract status {contract.evidence_status.value} is not implementation evidence",
                    severity="warning",
                    coordinate=contract.rust_coordinate,
                    evidence_type="contract-status",
                )
            )
        for result in results:
            findings.extend(result.findings)

        hard_failure = any(result.verdict == Verdict.FAILED for result in by_layer.values())
        hard_failure = hard_failure or any(item.severity == "error" for item in findings)
        incomplete = bool(missing) or any(result.verdict == Verdict.INCONCLUSIVE for result in by_layer.values())
        incomplete = incomplete or contract.evidence_status in {MappingStatus.CANDIDATE, MappingStatus.MAPPED}
        if hard_failure:
            verdict = Verdict.FAILED
        elif incomplete:
            verdict = Verdict.INCONCLUSIVE
        elif all(by_layer[layer].verdict == Verdict.VERIFIED for layer in required):
            verdict = Verdict.VERIFIED
        else:
            verdict = Verdict.INCONCLUSIVE

        return AcceptanceReport(
            contract_id=contract.contract_id,
            verdict=verdict,
            layer_verdicts={key: value.verdict.value for key, value in by_layer.items()},
            evidence=all_evidence,
            findings=tuple(findings),
            rust_coordinate=contract.rust_coordinate,
            python_owner=contract.python_owner,
            rust_baseline=str(contract.rust["baseline_commit"]),
        )
