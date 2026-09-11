# Issue #27 A1b — historical O sticking-law discriminator

**Status:** accepted historical Phase-A provenance / characterization  
**Control-plane status:** schema-v1 fixture; non-executable under the current experiment control plane

This directory preserves the A1b discriminator that froze the state-dependent `O -> 0.5 O2` sticking-law behavior after A1 established the finite-volume wall-flux sign. Its `experiment.json` remains useful to characterization tests and provenance reconstruction, but it must not be treated as a current operator execution entrypoint.

Current execution and acceptance are owned by the schema-v2 Physics control plane and, where P3 scientific runtime is required, an explicitly governed issue-scoped runner/workflow.

## Frozen scientific contract

A1b preserves the accepted R4-QF1 reactor state and applies the wall process on `plasma_wafer` with:

```text
O -> 0.5 O2
s_O = 0.2
Motz-Wise correction = OFF
```

The outward-positive O mass flux is

```text
J_O,out = (s_O/4) * rho * w_O * sqrt(8*R*T_g/(pi*M_O))
M_O = 0.016 kg/mol
```

The live flux functor depends on:

```text
rho_mat
w_O
T_g
```

The accepted sign mapping is:

```text
physical outward-positive species loss
  -> FVFunctorNeumannBC.factor = -1
```

## Historical discriminator

The historical two-case batch used:

```text
control:
  same state-dependent wall-flux functor
  boundary factor = 0

sticking:
  same state-dependent wall-flux functor
  boundary factor = -1
```

Evidence included wall O mass rate, O inventory, constrained-O2 inventory, total mass, volume charge, and nonnegative mass fractions. For one implicit-Euler step the primary closure relation was

```text
|Delta m_O| ~= dt * integral_wall(J_O,out dA)
```

The original runner produced evidence for scientific review rather than an automatic PASS. The accepted A1b conclusion is historical evidence; no current execution authority is implied by this fixture.
