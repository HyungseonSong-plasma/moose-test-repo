# Issue #27 — Oxygen surface reactions

Status: **A0 AUDIT COMPLETE / A1 R4-QF1 DIFFERENTIAL CONTROL READY FOR USER-LOCAL QPX**

Canonical execution interface:

```bash
python qpx -i all
python qpx -e experiments/Issue27_surface_reactions/A1_o_recombination/experiment.json
```

`qpx -i` is repository/harness validation and is not a scientific EVR. `qpx -e`
is the declarative scientific experiment gateway; a user-local QPX result returned
from it is attributable as scientific evidence when it exercises the scientific
acceptance surface.

## A0 source parity

Primary reference: COMSOL 6.4, *Model of an Argon/Oxygen Inductively Coupled Plasma Reactor*, Application ID 109191.

Official model documentation:

- https://doc.comsol.com/6.4/doc/com.comsol.help.models.plasma.icp_argon_oxygen/icp_argon_oxygen.html
- https://www.comsol.com/model/model-of-an-argonoxygen-inductively-coupled-plasma-reactor-109191

Oxygen surface set used as the Phase-A source contract:

| ID | Surface reaction | sticking | SEE in source | Phase-A SEE |
|---|---|---:|---:|---:|
| S3 | `O -> 0.5 O2` | 0.2 | 0 | 0 |
| S4 | `O2+ -> O2` | 1 | 0.05 | **0** |
| S5 | `O- -> O` | 1 | 0 | 0 |
| S6 | `O2(a1Delta_g) -> O2` | 1 | 0 | 0 |
| S7 | `O(1D) -> 0.5 O2` | 0.2 | 0 | 0 |
| S8 | `O+ -> O` | 1 | 0.05 | **0** |

### S6 documentation discrepancy

COMSOL 6.4 Table 4 prints `O2(a1Delta_g) -> O`, but the generated Model Builder
reaction list in the 6.1–6.3 versions of the same ICP model explicitly names
reaction 6 as `O2a1Dg -> O2`. The latter also preserves oxygen atoms, whereas the
printed Table-4 form does not.

Phase-A working resolution:

```text
QPX O2s -> constrained O2
```

Treat the Table-4 `-> O` entry as a documentation inconsistency/typo unless newer
primary model-file evidence proves otherwise. Do not implement `O2s -> O` from
the table alone.

## A0 QPX species mapping

Current accepted R3/R4 input defines heavy transport species:

```text
O2 O2s O2p O Om Op Os
```

| physical species | QPX symbol | M [kg/mol] | z |
|---|---|---:|---:|
| O2 | constrained `O2` | 0.032 | 0 |
| O2(a1Delta_g) | `O2s` | 0.032 | 0 |
| O2+ | `O2p` | 0.032 | +1 |
| O | `O` | 0.016 | 0 |
| O- | `Om` | 0.016 | -1 |
| O+ | `Op` | 0.016 | +1 |
| O(1D) | `Os` | 0.016 | 0 |

`O2` is not an independent solver variable:

```text
w_O2 = 1 - (w_O2s + w_O2p + w_O + w_Om + w_Op + w_Os).
```

The N-1 representation is part of the wall-reaction bookkeeping contract.

## A0 real-qvt wall ownership

The accepted qvt mesh constructs exactly these six plasma-facing wall sidesets:

```text
plasma_electrode
plasma_metal
plasma_right
plasma_cover
plasma_wafer
plasma_focus_ring
```

They are exactly the boundaries used by the no-slip flow wall BCs. `inlet` and
`outlet` are separate interfaces and are not included in this wall set.

In accepted R4-QF1:

- heavy and electron electrostatic drift explicitly avoid all physical plasma boundaries;
- heavy electromigration correction explicitly avoids all physical plasma boundaries;
- species diffusion has natural zero external wall flux unless a dedicated FV wall BC owns it;
- no production surface-reaction species wall BC exists yet.

Issue #27 therefore takes explicit ownership of species wall fluxes without
changing the accepted interior transport ownership.

## A0 flux/bookkeeping convention

Experiment-level sign convention:

```text
J_k,n > 0  => species k leaves the plasma volume
J_k,n < 0  => species k is returned from the wall into the plasma volume
```

For surface event molar rate `R_s [mol event / m2 / s]`:

```text
J_k,n = nu_loss,k * M_k * R_s
```

Examples:

```text
O -> 0.5 O2
  J_O  = +0.016 R_s
  implied J_O2 = -0.016 R_s

O- -> O
  J_Om = +0.016 R_s
  J_O  = -0.016 R_s

O2+ -> O2
  J_O2p = +0.032 R_s
  implied J_O2 = -0.032 R_s

O+ -> O
  J_Op = +0.016 R_s
  J_O  = -0.016 R_s
```

For constrained O2, the implied O2 flux is the negative sum of solved-species
mass fluxes. Do not create a seventh O2 solver equation.

For charged reactants, outward conventional charge current is

```text
I_q,out = F * z_k * R_s * A
```

or the equivalent particle-flux form. With `sigma_s` OFF, charge removed from
the plasma must close through the R4 volume/boundary charge ledger; it must not
be stored implicitly as surface charge.

## A0 capability decision

MOOSE core provides `FVNeumannBC` for prescribed FV boundary flux and
`FVFunctorNeumannBC` for functor/state-dependent FV boundary flux.

Phase-A ordering:

1. A1 uses `FVNeumannBC` with a prescribed neutral-O wall-event flux.
2. A1b adds the O sticking law only after A1 freezes the FVBC sign mapping.
3. Input-only `FVFunctorNeumannBC` support remains to be proven on the user-local
   QPX build before claiming that no QPX C++ wall object is needed.

## A1 — accepted R4-QF1 + wafer prescribed-flux differential

The original standalone one-dimensional A1 input is retired. Its first user-local
run produced zero nonlinear residual because the minimal input contained no
`FVFluxKernel`, causing the MOOSE FV face loop to return before boundary flux
assembly. That result is an experiment-construction defect, not evidence against
the QPX conservative time kernel or production wall transport.

A1 now starts from the accepted **R4-QF1 closed-feedback real-qvt construction**:

```text
real-qvt RZ mesh                         PRESERVED
heavy transport                          ON
electron transport                       ON
solved potential_plasma                  ON
monolithic electrostatic feedback        ON
pure-O2 20 sccm feed                     PRESERVED
volumetric reactions                     OFF
secondary emission                       OFF
surface accumulated charge sigma_s       OFF
```

The only A1 intervention is a neutral-O `FVNeumannBC` on:

```text
plasma_wafer
```

Frozen reaction:

```text
O -> 0.5 O2
```

Frozen event-flux magnitude:

```text
R_s = 0.1 mol/m2/s
|J_O| = 0.1 * 0.016 = 1.6e-3 kg/m2/s
```

The MOOSE `FVNeumannBC.value` sign is **not assumed** to equal the
experiment-level outward-positive convention. A1 resolves that mapping
empirically.

### Three-case bounded batch

A single `qpx -e` A1 invocation runs:

```text
control : FVNeumannBC value = 0
plus    : FVNeumannBC value = +1.6e-3 kg/m2/s
minus   : FVNeumannBC value = -1.6e-3 kg/m2/s
```

All three cases use the same R4-QF1 predecessor, mesh, timestep, flow,
Poisson solve, electron state, heavy state, and output instrumentation.

Because R4 has physical inlet/outlet evolution, A1 does **not** attribute raw
inventory change directly to the wall. It subtracts the zero-wall-flux control:

```text
delta m_O(plus)  = m_O_plus(t1)  - m_O_control(t1)
delta m_O(minus) = m_O_minus(t1) - m_O_control(t1)
```

The expected single-case transfer magnitude is

```text
|delta m_O| = |J_O| * A_wafer * dt
```

using the measured `plasma_wafer` area and the actual R4 final time.

A1 also measures:

```text
delta m_O2 + delta m_O
delta total mass
plus/minus antisymmetry
delta volume charge relative to control
w_O_min
w_O2_min
```

For neutral `O -> 0.5 O2`, the surface intervention should not create a first-order
charge response relative to the control. This is only a neutral-wall check; no
charged-wall correctness is inferred from A1.

### A1 evidence status

The runner intentionally terminates successful construction/runtime as:

```text
ISSUE27_A1_STATUS: A1_R4_EVIDENCE_READY_NOT_ACCEPTED
```

This is not automatic scientific PASS. Scientific adjudication must inspect:

1. all three P2 checks;
2. all three runtime returns;
3. nonzero and opposite-sign `plus/minus` O responses;
4. which FVNeumann sign produces outward O loss;
5. `|delta m_O|` versus `|J_O| A dt`;
6. constrained-O2 mass response;
7. total-mass response relative to control;
8. neutral charge response relative to control;
9. nonnegative `w_O` and constrained `w_O2`.

Only after this evidence freezes the sign/bookkeeping contract may A1b introduce
the physical sticking coefficient `s_O = 0.2`.

## Phase-A progression

```text
A0   source/species/boundary/capability audit                COMPLETE
A1   R4-QF1 + wafer O prescribed-flux differential           READY
A1b  O -> 0.5 O2 state-dependent sticking-law test           after A1
A2   O- -> O controlled wall test                            after A1
A3   O2+ -> O2 and O+ -> O neutralization, SEE=0             after charged-flux contract
A3e  electron wall absorption + combined charge-ledger test  required before charged-wall acceptance
A4   O2s -> O2 and Os -> 0.5 O2                              after neutral controls
A5   constrained-O2 bookkeeping regression
A6   bounded six-wall real-qvt chemistry integration         after individual controls
Phase C finite SEE + electron-energy coupling                 after #26
```

Do not enable bulk chemistry, finite SEE, electron-energy coupling, or `sigma_s`
during Phase A.
