# Incident: duplicate shared functor material provider during coupled-input composition

**Date:** 2026-08-27  
**Origin:** issue #16 real-qvt heavy + electron + Poisson integration  
**Class:** `HARNESS_OR_CONSTRUCTION_FAIL / DUPLICATE_PROVIDER_FAIL`

## Symptom

The representative qvt candidate passed static package checks and both upstream known-good controls, then failed at `qpx-opt --check-input` before coupled physics execution:

```text
No insertion for the functor material property 'T_g' for block id 53.
Another material must already declare this property on that block.
```

Observed discriminator state:

```text
KG-H: PASS
KG-E: PASS
Q0 P0/P1: PASS
Q0 P2: FAIL
Q0/QH/QE/QF coupled P3: NOT EXECUTED
```

## Root cause

The EVR2 integration builder recursively copied electron-provider dependencies from the accepted #2 electron case into the accepted #15 heavy-qvt baseline.

That composition strategy failed to distinguish:

```text
shared state already owned by heavy qvt
  T_g
  pressure / heavy thermodynamic state
  density
  shared mesh/material properties

from electron-specific additions
  n_e
  electron mean-energy input
  QPXElectronTransportLookupMaterial
  electron diffusion/drift operators
```

A second producer of `T_g` was therefore inserted on block 53 even though the heavy-qvt stack already owned that material property. MOOSE correctly rejected the duplicate producer during input construction.

## Why the preflight missed it

The assistant-authored P0 checks verified presence of required names and some structural wiring, but did not build a block-qualified provider ownership graph. Presence-only validation can detect missing names while still false-PASSing duplicate producers.

The missing invariant was:

```text
(material_or_functor_property, block) -> exactly one intended producer
```

for shared properties consumed by the integrated stack.

## Correct integration boundary

Do not transplant shared thermodynamic provider subgraphs from an accepted subsystem case into another accepted production baseline.

For this qvt coupling, the heavy-mixture stack remains the owner of shared thermodynamic state:

```text
reuse from heavy qvt:
  T_g
  pressure / heavy thermodynamic state
  density
  heavy species and mixture-transport providers
  relative_permittivity

add only electron-specific state/path:
  linear n_e
  accepted electron mean-energy input
  QPXElectronTransportLookupMaterial
  electron diffusion kernel
  electron electrostatic-drift kernel
```

`QPXElectronTransportLookupMaterial` must bind to the existing heavy-qvt `T_g` and pressure providers rather than creating new producers for them.

## Preventive validation rule

Before P2 for generated overlay/integration inputs:

1. construct a block-qualified provider ownership map;
2. resolve every referenced functor/material property on every applicable block;
3. hard-fail missing providers;
4. hard-fail multiple unintended producers;
5. carry a negative mutation that duplicates one shared provider such as `T_g` and prove P0 rejects it;
6. prefer explicit subsystem ownership/reuse over recursive provider copying.

## Governance outcome

The failure consumed the final prospective #16 EVR and raised `RWR` to 2. Per the stop-and-redesign rule, no fourth external execution is allowed under the unchanged #16 boundary. The remaining work is decomposed into a construction-only successor followed by a fresh coupled-physics successor.
