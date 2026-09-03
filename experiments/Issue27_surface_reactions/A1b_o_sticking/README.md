# Issue #27 A1b — O sticking-law wall flux on R4-QF1

A1b is the first state-dependent surface-reaction discriminator after A1 froze
the finite-volume wall-flux sign.

Canonical execution:

```bash
python qpx -i all
python qpx -e experiments/Issue27_surface_reactions/A1b_o_sticking/experiment.json
```

## Frozen predecessor

A1b preserves the accepted R4-QF1 reactor state:

```text
real-qvt RZ mesh                    ON
heavy transport                     ON
electron transport                  ON
solved potential_plasma             ON
monolithic electrostatic feedback   ON
volumetric reactions                OFF
secondary emission                  OFF
surface charge sigma_s              OFF
wall under test                     plasma_wafer
```

The surface reaction remains:

```text
O -> 0.5 O2
```

The accepted A1 sign mapping is frozen as:

```text
experiment convention:
  J_O,out > 0  => O leaves the plasma

MOOSE FV boundary convention:
  outward O loss => FVNeumann/FVFunctorNeumann factor = -1
```

## Sticking model

Reference sticking coefficient:

```text
s_O = 0.2
```

A1b uses the COMSOL sticking-coefficient kinetic form with **Motz-Wise
correction explicitly OFF**:

\[
k_s
=
s_O\,\frac14
\sqrt{\frac{8RT_g}{\pi M_O}}
\]

with \(M_O=0.016\ {\rm kg/mol}\). Since
\(c_O=\rho w_O/M_O\), the outward O mass flux is

\[
J_{O,\mathrm{out}}
=
M_O k_s c_O
=
s_O\,\frac14
\sqrt{\frac{8RT_g}{\pi M_O}}
\,\rho w_O.
\]

The wall flux is therefore a live functor of:

```text
rho_mat
w_O
T_g
```

and is applied with `FVFunctorNeumannBC`.

COMSOL theory also supports a Motz-Wise corrected sticking rate,

\[
k_s
=
\frac{s_O}{1-s_O/2}\,
\frac14
\sqrt{\frac{8RT_g}{\pi M_O}},
\]

but the reference reactor documentation exposes `s_O=0.2` without exposing the
Motz-Wise option state. A1b therefore freezes the uncorrected form rather than
silently assuming an undocumented 11.1% correction. A corrected variant, if
needed, must be a separate discriminator.

## Bounded batch

One A1b `qpx -e` invocation runs two otherwise identical R4-QF1 cases:

```text
control:
  same state-dependent wall-flux functor
  FVFunctorNeumannBC factor = 0

sticking:
  same state-dependent wall-flux functor
  FVFunctorNeumannBC factor = -1
```

The runner integrates the positive outward mass-flux functor over
`plasma_wafer` and records

```text
wall O mass rate [kg/s]
O inventory
constrained O2 inventory
total mass
volume charge
minimum O and constrained-O2 mass fractions
```

For one implicit-Euler step, the primary diagnostic is

\[
|\Delta m_O|
\approx
\Delta t
\int_{\mathrm{wafer}}J_{O,\mathrm{out}}(t_{n+1})\,dA.
\]

Control subtraction removes ordinary inlet/outlet and R4 transport evolution.

Successful construction/runtime terminates as:

```text
ISSUE27_A1B_STATUS: A1B_R4_EVIDENCE_READY_NOT_ACCEPTED
```

This is evidence-ready, not automatic scientific PASS. Acceptance requires
review of P2/runtime, outward O loss, wall-rate closure, constrained-O2 response,
mass conservation, nonnegative mass fractions, and neutral charge response.
