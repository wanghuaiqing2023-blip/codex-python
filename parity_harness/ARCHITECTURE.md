# Parity Harness Architecture

The harness is an observer. It does not own slash commands, runtime state,
rendering, model context construction, or any other PyCodex product behavior.
All generated state stays under `.artifacts/`.

## Evidence flow

```text
contract
  -> structure result
  -> structural report
```

Maintenance audits the harness itself and is not another parity grader.

## Layer boundaries

1. `structure` proves coordinates, containment, and exclusive ownership. It can
   report candidates but cannot promote behavior to verified.
2. `contracts` currently defines structural ownership and coordinate evidence
   only. It does not accept free-form behavior prose as proof.
3. `dynamic` records and compares normalized traces for contract-owned events.
4. `outcomes` drives a controlled scenario and grades final environment state.
5. `acceptance` is currently a self-test prototype. It consumes files emitted
   by the example layers and does not call
   their internal checkers or trust implementation completion claims.
6. `maintenance` checks reachability, stale references, duplicate checker
   responsibility, baseline drift, and artifact placement inside this package.

The aggregate CLI composes public layer entry points. Dynamic, outcome, and
acceptance results are not current product constraints.

## Verdicts

- `verified`: the requested evidence exists and satisfies the contract.
- `failed`: available evidence contradicts the contract.
- `inconclusive`: required evidence or an executable baseline is unavailable.

`candidate`, `mapped`, and `implemented` are mapping/evidence states. None of
them is an acceptance verdict.

## Product boundary

The repository outside `parity_harness/` is read-only input. A finding against
PyCodex or Rust is reported, never repaired by this package. Fixture repositories
under `fixtures/` exercise the harness mechanics and never claim product parity.
