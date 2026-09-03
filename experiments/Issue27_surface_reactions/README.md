# Issue #27 — Oxygen surface reactions

Status: **A0 AUDIT COMPLETE ENOUGH TO CONSTRUCT A1 / NO SCIENTIFIC QPX RUN YET**

Canonical execution interface:

```bash
python qpx -i all
python qpx -e experiments/Issue27_surface_reactions/A1_o_recombination/experiment.json
```

`qpx -i` is repository/harness validation and is not a scientific EVR. `qpx -e` is the declarative scientific experiment gateway; a user-local QPX result returned from it is attributable as scientific EVR when it exercises the scientific acceptance surface.

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

COMSOL 6.4 Table 4 prints `O2(a1Delta_g) -> O`, but the generated Model Builder reaction list in the 6.1–6.3 versions of the same ICP model explicitly names reaction 6 as `O2a1Dg -> O2`. The latter also preserves oxygen atoms, whereas the printed Table-4 form does not.

Phase-A working resolution:

```text
QPX O2s -> constrained O2
```

Treat the Table-4 `-> O` entry as a documentation inconsistency/typo unless newer primary model-file evidence proves otherwise. Do not implement `O2s -> O` from the table alone.

## A0 QPX species mapping

Current accepted R3/R4 input defines heavy transport species:

```text
O2 O2s O2p O Om Op Os
```

Mapping:

| physical species | QPX symbol | M [kg/mol] | z |
|---|---|---:|---:|
| O2 | constrained `O2` | 0.032 | 0 |
| O2(a1Delta_g) | `O2s` | 0.032 | 0 |
| O2+ | `O2p` | 0.032 | +1 |
| O | `O` | 0.016 | 0 |
| O- | `Om` | 0.016 | -1 |
| O+ | `Op` | 0.016 | +1 |
| O(1D) | `Os` | 0.016 | 0 |

`O2` is not an independent solver variable. It is the constrained remainder

```text
w_O2 = 1 - (w_O2s + w_O2p + w_O + w_Om + w_Op + w_Os).
```

This N-1 representation is part of the wall-reaction bookkeeping contract.

## A0 real-qvt wall ownership

Current accepted qvt mesh constructs these six plasma-facing wall sidesets:

```text
plasma_electrode
plasma_metal
plasma_right
plasma_cover
plasma_wafer
plasma_focus_ring
```

They are exactly the boundaries used by the no-slip wall BCs. `inlet` and `outlet` are separately generated interfaces and are **not** included in this wall set.

Phase-A production wall chemistry therefore targets the six plasma-facing wall sidesets only. Outlet ion neutralization, which COMSOL treats separately from neutral wall reactions, must not be silently conflated with the wall chemistry contract.

## A0 flux/bookkeeping convention

Use outward-from-plasma mass flux as the experiment-level positive convention:

```text
J_k,n > 0  => species k leaves the plasma volume
J_k,n < 0  => species k is returned from the wall into the plasma volume
```

For a surface event molar rate `R_s [mol event / m2 / s]`, species mass flux is

```text
J_k,n = nu_loss,k * M_k * R_s
```

with signed stoichiometric ownership assigned by the experiment. Examples:

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

For constrained O2, the implied O2 flux is the negative sum of solved-species mass fluxes. Do not create a seventh O2 solver equation merely to express a wall product.

For charged reactants, the corresponding outward conventional charge current is

```text
I_q,out = F * z_k * R_s * A
```

or the equivalent particle-flux form. With `sigma_s` OFF, charge removed from the plasma must close through the R4 volume/boundary charge ledger; it must not be stored implicitly as surface charge.

## A0 capability decision

Current QPX inputs already use finite-volume flux BCs for inlet scalar transport but contain no production wall-reaction FVBC.

MOOSE core provides `FVNeumannBC` for prescribed FV boundary flux and `FVFunctorNeumannBC` for functor/state-dependent FV boundary flux. Therefore:

1. **A1 first uses `FVNeumannBC` with a prescribed wall-event flux** to isolate sign, N-1 constrained-O2 bookkeeping, mass conservation, and inventory response.
2. A state-dependent sticking-law experiment is added only after the prescribed-flux control passes.
3. Production input-only use of `FVFunctorNeumannBC` remains **to be proven on the user-local QPX build by P2/runtime evidence**. Do not claim that no QPX C++ object is needed until that probe succeeds.

This ordering intentionally separates wall kinetics from boundary-flux semantics.

## A1 controlled-wall discriminator

A1 is a minimal one-dimensional oxygen-only bookkeeping test, not a reactor model.

Frozen reaction:

```text
O -> 0.5 O2
```

Frozen controls:

```text
rho                     = 1 kg/m3
initial w_O             = 0.1
initial constrained w_O2= 0.9
prescribed event flux   = 0.1 mol/m2/s
M_O                     = 0.016 kg/mol
dt                      = 0.1 s
wall                    = right boundary
```

Therefore the imposed outward O mass flux is

```text
J_O = 0.1 * 0.016 = 1.6e-3 kg/m2/s.
```

A1 acceptance is based on measured wall area and CSV inventories, not an assumed unit area:

```text
1. P2/check-input PASS
2. runtime returns normally
3. O inventory decreases
4. measured O loss = J_O * measured_area * dt within numerical tolerance
5. constrained-O2 mass gain = O mass loss
6. total oxygen mass is conserved
7. total oxygen-atom inventory is conserved
8. w_O >= 0 and w_O2 >= 0
```

If the sign is opposite, A1 is a useful FAIL: it means the MOOSE/QPX FVBC sign convention needs correction before any sticking law is introduced.

## Phase-A experiment progression through qpx

```text
A0  source/species/boundary/capability audit   qpx-free
A1  O -> 0.5 O2 prescribed-flux control       qpx -e
A1b O -> 0.5 O2 sticking-law control          qpx -e, after A1
A2  O- -> O                                    qpx -e
A3  O2+ -> O2 and O+ -> O, SEE=0              qpx -e
A4  O2s -> O2 and Os -> 0.5 O2                qpx -e
A5  constrained-O2 bookkeeping regression      qpx -e / qpx-free where possible
A6  bounded real-qvt wall chemistry on R4      qpx -e
```

Do not enable bulk chemistry, finite SEE, electron-energy coupling, or `sigma_s` during Phase A.
