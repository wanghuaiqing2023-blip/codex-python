# Crate Structure Status

This filename is retained as a compatibility entry point for existing module
documentation. The authoritative crate inventory and ownership status are
executable data, not this Markdown page.

## Authority

- Workspace inventory and fixed baseline:
  `parity_harness/contracts/workspace.json`
- Reviewed module ownership:
  `parity_harness/contracts/accepted/<scope>/`
- Generated evidence:
  `parity_harness/.artifacts/`

## Check A Crate

```powershell
python -B -m parity_harness contract validate-accepted --scope <crate>
python -B -m parity_harness structure --scope <crate> --gate ownership
```

Generate a candidate only when ownership needs to change:

```powershell
python -B -m parity_harness contract generate --scope <crate>
```

The candidate is not authoritative and must never overwrite accepted
contracts automatically.

## Check The Workspace

```powershell
python -B -m parity_harness workspace check
python -B -m parity_harness contract validate-accepted --scope all
python -B -m parity_harness structure --scope all --gate ownership
python -B -m parity_harness audit
```

Interpret results separately:

- `ownership_verdict: verified` means existing Python production files have a
  valid, unique Rust owner.
- `coverage_verdict: verified` means all in-scope Rust modules have accepted
  Python counterparts.
- `coverage_verdict: partial` is valid debt and must not be made green by
  inventing owners.
- `deferred` is allowed only when the workspace contract records a reason.

See [PORTING_STATUS.md](PORTING_STATUS.md) for the project-wide snapshot and
[PORTING_PROJECT_PRINCIPLES.md](PORTING_PROJECT_PRINCIPLES.md) for acceptance
rules.
