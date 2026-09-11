# Issue #27 A5+A6 — historical combined COMSOL-style wall integration

**Status:** accepted historical Phase-A provenance / characterization  
**Control-plane status:** schema-v1 fixture; non-executable under the current experiment control plane

This directory preserves the A5 constrained-`O2` bookkeeping check and A6 bounded six-wall chemistry integration used during Issue #27 development. Its `experiment.json` is retained as provenance/characterization input only. It does not authorize current scientific execution.

Current closure-grade runtime must use the current Physics architecture and an explicitly governed acceptance surface owned by the active issue.

## Historical A5 preflight contract

The A5 preflight established that:

- no independent `w_O2` solver variable exists;
- `O2` remains the constrained N-1 species;
- the wall set is exactly the six plasma-facing boundaries;
- `inlet` and `outlet` are excluded;
- bulk charged drift avoids physical boundaries where wall migration is owned;
- charged wall flux uses solved `potential_plasma`;
- the Phase-A reactions conserve oxygen mass algebraically.

## Historical A6 wall model

Neutral reactions:

```text
O   -> 0.5 O2   s = 0.2
O2s -> O2       s = 1.0
Os  -> 0.5 O2   s = 0.2
```

Charged reactions:

```text
O2p -> constrained O2   s = 1.0
Om  -> O                s = 1.0
Op  -> O                s = 1.0
```

Charged wall transport was decomposed as:

```text
surface-reaction mass flux
+ one-sided electric-migration mass flux
```

The bounded historical cases were `control`, `surface_only`, and `comsol_wall`. Their evidence covered composition, mass bookkeeping, side-resolved charged wall rates, electron-ledger response, volume-charge behavior, and Poisson/Gauss consistency.

A6 acceptance established only the bounded Phase-A six-wall integration. It did not establish finite SEE, solved electron-energy coupling, Stage-6 acceptance, or Integrated Physics Accuracy.
