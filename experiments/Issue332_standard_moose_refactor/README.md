# Issue #332 — Standard MOOSE First Gummel refactor

This directory owns the refactor contract for reducing custom `Physics*` MooseObjects around the qualified Issue #310 Gummel endpoint.

## Immutable oracle

```text
qualified branch = qualified/issue310-gummel-optimized
qualified SHA    = cdba1cba025da3c8442c0ad2993aeccab0111732
Gen34 run        = 36051947264
case             = optimized_endpoint_20ns
```

Do not mutate the oracle. New lanes start from current `main` but compare their behavior against the exact qualified source above.

## First execution wave

Two isolated branches are registered:

```text
R1 / #333
branch = issue-333-standard-charge-density
PhysicsPlasmaChargeDensityMaterial
 -> standard MOOSE functor algebra

R2 / #334
branch = issue-334-standard-convergence
PhysicsDeltaPhiMultiAppConvergence
 -> standard MOOSE convergence composition
```

R1 and R2 may not consume each other's code mutations or conclusions while their discriminator runs are active.

## Acceptance model

A standard replacement is accepted only if all relevant semantics are preserved:

1. scientific endpoint/profile parity;
2. discrete operator or stopping-rule equivalence;
3. fixed-point history parity where applicable;
4. no material runtime regression;
5. fail-fast/bounds/AD ownership is not weakened.

The nominal final-profile parity target is approximately `1e-8–1e-7` normalized. Runtime regression >5% requires explicit review.

For R2, final-state parity alone is insufficient: the primary evidence is per-electron-step fixed-point termination behavior.

## Deferred phases

After R1/R2 are classified:

- R3: `PhysicsElectronMeanEnergyMaterial` algebra/guard audit;
- R4: heavy-transport kernel standardization audits;
- R5: integrate only independently qualified reductions;
- R6: re-run the 19.941 ns Gen34 qualification horizon.

The custom acceleration/transport objects listed in `refactor_contract.json` are KEEP-by-default unless a dedicated equivalence issue demonstrates otherwise.
