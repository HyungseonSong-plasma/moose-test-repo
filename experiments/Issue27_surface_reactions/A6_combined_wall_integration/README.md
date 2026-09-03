# Issue #27 A5+A6 — combined COMSOL-style wall integration

This experiment intentionally combines the A5 constrained-`O2` bookkeeping check and the A6 bounded six-wall Phase-A chemistry run into one scientific execution.

## Run

```bash
python qpx -i all
python qpx -e experiments/Issue27_surface_reactions/A6_combined_wall_integration/experiment.json
```

`qpx -i` is repository/harness validation. The `qpx -e` command is the single scientific run and contains the A5 preflight plus all A6 runtime cases.

## A5 preflight

Before QPX runtime the runner verifies:

- no independent `w_O2` solver variable exists;
- `O2` remains the constrained N-1 species;
- the wall set is exactly the six plasma-facing boundaries;
- `inlet` and `outlet` are excluded;
- `QPXFVElectrostaticDrift` for `O2p`, `Om`, and `Op` avoids all physical boundaries, preventing interior/wall drift double counting;
- each charged wall model is `QPXIonWallFluxMaterial` driven by solved `potential_plasma`;
- all six Phase-A reactions conserve oxygen mass algebraically.

## A6 wall model

Neutral reactions use the already accepted state-dependent sticking law:

```text
O   -> 0.5 O2   s = 0.2
O2s -> O2       s = 1.0
Os  -> 0.5 O2   s = 0.2
```

Charged reactions use the Issue #1 validated `QPXIonWallFluxMaterial`:

```text
O2p -> constrained O2   s = 1.0
Om  -> O                s = 1.0
Op  -> O                s = 1.0
```

The charged wall flux is decomposed as

```text
surface-reaction mass flux
+ one-sided electric-migration mass flux
```

where the migration part follows the accepted COMSOL-style signed outward-normal gate owned by `QPXIonWallFluxMaterial`. Each charged species and each of the six walls has separate surface and migration flux evidence.

The bulk `QPXFVElectrostaticDrift` remains excluded from the wall boundaries; the boundary material owns the migration contribution there.

## Runtime cases

```text
control
  all Issue #27 wall fluxes OFF

surface_only
  all six Phase-A surface reactions ON
  charged electric-migration wall flux OFF
  matched signed electron charge ledger ON

comsol_wall
  same surface chemistry
  charged one-sided electric-migration wall flux ON
  matched signed electron charge ledger ON
```

The electron term remains the A3e-approved matched charge-ledger control. It is not yet a production electron sheath law. `SEE=0`, volumetric chemistry is OFF, and `sigma_s` is OFF.

## Acceptance surface

Scientific review must check:

- A5 preflight PASS for every staged case;
- P2/runtime return code 0 for every case;
- N-1 composition closure and nonnegative species state;
- species/product and total-heavy-mass bookkeeping;
- side-resolved charged `surface`, `migration`, and `total` wall rates;
- migration activation consistent with the signed one-sided wall gate;
- matched electron inventory response;
- control-relative volume-charge restoration;
- Poisson/Gauss consistency.

Passing A6 closes the bounded Phase-A six-wall integration only. Full Issue #27 closure still requires Phase-B volumetric-chemistry compatibility and Phase-C finite SEE/electron-energy coupling.
