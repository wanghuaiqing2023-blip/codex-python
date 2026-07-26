# Accepted module contracts

This tree contains reviewed architecture standards. Each contract identifies
one complete Rust module coordinate, one Python module-file or continuous
module-package, executable anchors, and Rust-derived fixture references.

Candidate catalogs are written only under `../generated/`:

```powershell
python -B -m parity_harness contract generate --scope <crate>
python -B -m parity_harness contract validate-accepted --scope <crate>
python -B -m parity_harness structure --scope <crate> --gate ownership
```

The collection gate rejects candidate states, duplicate Rust coordinates,
duplicate Python owners, overlapping files, mixed baselines, and scattered
packages. Scope policy files preserve uncovered Rust modules and Python files
as coverage debt; they must not be cleared merely to make a report green.
