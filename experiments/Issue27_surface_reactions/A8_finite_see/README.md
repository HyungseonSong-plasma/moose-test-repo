# Issue #27 A8 — historical finite ion-induced SEE fixture

**Status:** historical schema-v1 provenance / characterization; current acceptance owned by #193  
**Control-plane status:** non-executable under the current experiment control plane

This directory preserves the A8 finite-SEE declaration used during Issue #27 development. Its schema-v1 `experiment.json` is retained because current characterization tests use it to freeze the historical coefficients and construction contract. It is **not** a current scientific execution entrypoint.

Current finite-SEE particle acceptance is owned by Issue #193 and requires governed exact-head real `physics-opt` evidence. The existing construction/evidence mechanics under `experiments/Issue27_surface_reactions/controlled_wall/see.py` may be reused by that acceptance surface without reviving the retired protocol-dispatch control plane.

## Frozen SEE particle contract

```text
O2+ -> O2   gamma_SEE = 0.05
O+  -> O    gamma_SEE = 0.05
O-          gamma_SEE = 0
```

The emitted-electron particle rate is:

```text
Gamma_e,SEE = 0.05 * (Gamma_O2+,wall + Gamma_O+,wall)
Gamma_i,wall = Gamma_i,surface + Gamma_i,migration
```

With outward-positive convention, emitted electrons travel from the wall into the plasma:

```text
Gamma_e,SEE,out = -Gamma_e,SEE
```

The normalized electron-density FV source therefore uses the historically characterized positive source factor.

## Frozen 4 eV mapping

The accepted downstream energy mapping is:

```text
epsilon_SEE = 4 eV
Gamma_epsilon,SEE,in = 4 eV * Gamma_e,SEE
```

The historical A8 mechanics carried a runtime energy-flux ledger rather than a solved electron-energy unknown. Issue #26 has since completed the solved electron-energy contract; #193/#27 must consume that accepted mapping without redefining `gamma` or the 4 eV mean energy.

## Historical discriminator

The historical two-case discriminator was:

```text
see_off
  accepted heavy-wall chemistry and ion wall transport ON
  accepted thermal electron particle loss ON
  finite SEE OFF

see_on
  same physics
  + O2+/O+ finite SEE particle source
  + 4 eV SEE energy-flux ledger
```

Characterization verifies the frozen coefficients, O2+/O+ surface-plus-migration ownership, absence of O- SEE, particle-source sign mapping, zero-SEE control, and 4 eV scaling.

## Current acceptance boundary

The historical fixture and characterization are prerequisites, not #193 PASS. Current acceptance additionally requires governed production-path runtime evidence for:

- zero-SEE baseline;
- emitted-electron sign and quantitative magnitude;
- O2+ and O+ contribution exactly once;
- no O- contribution;
- electron particle inventory closure;
- wall current and charge/Gauss consistency;
- quantitative 4 eV-per-emitted-electron consistency;
- convergence and positivity;
- exact-head ordinary CI and governed runtime provenance.

Only explicit #193 PASS/CLOSED may authorize the subsequent #27 final Stage-6 integration regression.
