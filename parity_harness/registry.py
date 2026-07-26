"""Declared harness ownership used by the maintenance auditor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckerRegistration:
    layer: str
    module: str
    checker_id: str
    responsibility: str
    evidence_types: tuple[str, ...]


CHECKERS = (
    CheckerRegistration(
        "structure",
        "parity_harness.structure.scanner",
        "structure.owner-and-coordinate",
        "coordinates, containment, and exclusive ownership",
        ("module-ownership",),
    ),
    CheckerRegistration(
        "dynamic",
        "parity_harness.dynamic.trace",
        "dynamic.semantic-trace",
        "contract-owned semantic event and state trajectories",
        ("semantic-trace-comparison",),
    ),
    CheckerRegistration(
        "outcome",
        "parity_harness.outcomes.pipeline",
        "outcome.environment-state",
        "final filesystem, process, TUI, config, and runtime state",
        ("environment-outcome",),
    ),
    CheckerRegistration(
        "acceptance",
        "parity_harness.acceptance.evaluator",
        "acceptance.independent-evidence",
        "independent synthesis and attempted refutation of parity evidence",
        ("acceptance-report",),
    ),
    CheckerRegistration(
        "maintenance",
        "parity_harness.maintenance.audit",
        "maintenance.harness-health",
        "harness reachability, references, baseline freshness, and artifacts",
        ("harness-health",),
    ),
)
