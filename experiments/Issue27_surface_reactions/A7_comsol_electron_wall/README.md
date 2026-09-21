# Issue #27 A7 — historical COMSOL-style electron thermal wall discriminator

**Status:** accepted historical Phase-A provenance / characterization  
**Control-plane status:** schema-v1 fixture; non-executable under the current experiment control plane

A7 replaced the A6 matched electron charge-ledger control with COMSOL-style random thermal electron particle loss while preserving accepted A6 heavy-wall chemistry and charged-heavy surface plus one-sided migration transport.

The historical `experiment.json` remains a characterization/provenance fixture. Current Stage-6 scientific acceptance must not be routed through the retired schema-v1 protocol-dispatch path.

## Frozen particle contract

For the normalized electron unknown

```text
n_hat = n_e_physical / n_ref
```

with electron reflection coefficient `r_e = 0`:

```text
Gamma_e,out / n_ref = 0.5 * n_hat * v_e,th
v_e,th = sqrt(16 * e * mean_energy_eV / (3 * pi * m_e))
```

The accepted MOOSE sign mapping is:

```text
physical outward-positive flux
  -> FVFunctorNeumannBC.factor = -1
```

A7 froze:

```text
electron reflection      = 0
electron wall migration  = OFF
secondary emission       = 0
```

Historical cases were `control`, `electron_thermal_only`, and `combined_thermal`. Acceptance evidence checked electron inventory loss, nonnegative density, independently predicted volume-charge change, Gauss consistency, and N-1 heavy-species composition closure.

A7 did not force heavy-wall and electron-wall currents to cancel; the self-consistent charge response was part of the evidence.

## Current downstream interpretation

At the time A7 was constructed, its predecessor model did not yet carry the solved electron-energy state. Issue #26 subsequently completed and accepted the electron-energy wall mapping. Therefore current Stage-6 work must consume the accepted #26 energy contract rather than treating this historical A7 fixture as the present energy-coupling authority.

A7 by itself does not establish finite SEE particle acceptance, Stage-6 acceptance, or Integrated Physics Accuracy.
