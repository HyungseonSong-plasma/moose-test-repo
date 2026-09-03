# Issue #27 — Oxygen surface reactions

Status: **A1 + A1b scientifically accepted; A1c all-wall neutral and A3e charged-wall ledger ready for user-local QPX**

Canonical internal validation and scientific execution:

```bash
python qpx -i all

python qpx -e experiments/Issue27_surface_reactions/A1c_o_sticking_all_walls/experiment.json
python qpx -e experiments/Issue27_surface_reactions/A3e_charged_wall_ledger/experiment.json
```

`qpx -i` is repository/harness validation and does not consume scientific EVR. `qpx -e` is the scientific experiment gateway. Archive-copy provenance cleanup is deliberately deferred; scientific evidence remains based on staged inputs, QPX identity, logs, CSV outputs, and frozen discriminators.

## Phase-A source contract

Primary reference: COMSOL 6.4, *Model of an Argon/Oxygen Inductively Coupled Plasma Reactor*, Application ID 109191.

Surface set:

| reaction | sticking | source SEE | Phase-A SEE |
|---|---:|---:|---:|
| `O -> 0.5 O2` | 0.2 | 0 | 0 |
| `O2+ -> O2` | 1 | 0.05 | **0** |
| `O- -> O` | 1 | 0 | 0 |
| `O2(a1Delta_g) -> O2` | 1 | 0 | 0 |
| `O(1D) -> 0.5 O2` | 0.2 | 0 | 0 |
| `O+ -> O` | 1 | 0.05 | **0** |

COMSOL 6.4 Table 4 prints `O2(a1Delta_g) -> O`, while generated Model Builder reaction lists in earlier versions of the same ICP model identify `O2a1Dg -> O2`. Phase A therefore uses the oxygen-conserving working resolution

```text
QPX O2s -> constrained O2
```

unless newer primary model-file evidence proves otherwise.

## Species and N-1 contract

Accepted R3/R4 heavy species:

```text
O2 O2s O2p O Om Op Os
```

| physical species | QPX | M [kg/mol] | z |
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
w_O2 = 1 - (w_O2s + w_O2p + w_O + w_Om + w_Op + w_Os)
```

Surface bookkeeping must preserve this N-1 ownership; no seventh O2 equation is added.

## Boundary ownership

The real-qvt plasma-facing wall set is exactly:

```text
plasma_electrode
plasma_metal
plasma_right
plasma_cover
plasma_wafer
plasma_focus_ring
```

`inlet` and `outlet` remain separate and are explicitly excluded from Issue #27 wall chemistry.

Accepted R4-QF1 interior ownership remains unchanged:

- heavy/electron electrostatic drift avoids every physical plasma boundary;
- heavy electromigration correction avoids every physical plasma boundary;
- species diffusion retains natural zero external wall flux unless Issue #27 supplies an explicit FV wall BC;
- Poisson remains solved monolithically with `potential_plasma`.

## Flux sign contract — accepted A1

Experiment-level convention:

```text
J_out > 0 => species leaves the plasma volume
J_out < 0 => species is returned from the wall into the plasma
```

A1 runtime evidence froze the MOOSE mapping:

```text
physical outward-positive J_out
    -> FVNeumannBC.value = -J_out
```

This mapping is used by every later wall control.

## A1b — accepted neutral O sticking

For `O -> 0.5 O2` with `s_O = 0.2` and Motz-Wise correction OFF:

```text
J_O,out = (s_O/4) * rho * w_O * sqrt(8*R*T_g/(pi*M_O))
```

The implementation uses an outward-positive functor and

```text
FVFunctorNeumannBC.factor = -1
```

on the target wall. User-local A1b evidence confirmed state-dependent nonlinear assembly, O inventory loss, constrained-O2 return, total-mass closure, and preserved Poisson/Gauss behavior.

## A1c — all six plasma-facing walls

A1c applies the already accepted A1b O-sticking law simultaneously to all six plasma-facing wall sidesets and nowhere else.

```text
control  : same flux functor, BC factor = 0
sticking : same flux functor, BC factor = -1
```

The discriminator measures the combined six-wall surface rate and compares control-relative O loss with the implicit-Euler transfer

```text
|Delta m_O| ~= integral_wall(J_O,out dA) * dt
```

while checking constrained O2, total mass, neutral charge response, and nonnegative mass fractions.

## Charged-wall charge conservation contract

Positive-ion neutralization must **not** be implemented as a stoichiometric bulk-electron sink. An ion can neutralize by receiving charge from the wall/electrode; blindly writing `ion + plasma electron -> neutral` would double-count the electrical current.

For singly charged wall events with SEE=0, the charge-balanced electron absorption condition is

```text
Gamma_e,abs = Gamma_O2+ + Gamma_O+ - Gamma_O-
```

or in molar event rates

```text
R_e = R_O2p + R_Op - R_Om
```

For the normalized electron solver unknown

```text
n_e solver variable = n_hat = n_e_physical / n_ref
```

the electron FV boundary flux must therefore be normalized:

```text
physical electron number flux Gamma_e,out [1/m2/s]
normalized FV flux             = Gamma_e,out / n_ref [m/s]
FVNeumannBC.value              = -Gamma_e,out / n_ref
```

This normalization is part of the charged-wall acceptance contract.

## A3e — prescribed charged-wall ledger discriminator

A3e intentionally tests charge bookkeeping **before** introducing physical ion/sheath kinetics. The prescribed Phase-A rates are:

```text
R_O2p = 1.0e-4 mol/m2/s
R_Op  = 1.0e-4 mol/m2/s
R_Om  = 5.0e-5 mol/m2/s
R_e   = R_O2p + R_Op - R_Om = 1.5e-4 mol/m2/s
SEE   = 0
```

They apply to all six plasma-facing walls.

Heavy surface stoichiometry:

```text
O2p -> constrained O2
Op  -> O
Om  -> O
```

The bounded batch contains:

```text
control
  all new wall fluxes = 0

heavy_only
  O2p / Op / Om losses ON
  stoichiometric O return ON
  electron wall absorption OFF

charge_balanced
  same heavy wall fluxes
  + electron absorption satisfying R_e = R_O2p + R_Op - R_Om
```

Expected charge behavior:

```text
heavy_only:
  Delta Q_plasma ~= -F*(R_O2p + R_Op - R_Om)*A_wall*dt

charge_balanced:
  Delta Q_plasma relative to control -> approximately 0
```

Thus `heavy_only` is a positive control proving that the charged-heavy Neumann BCs create the predicted charge shift. `charge_balanced` then tests whether the matched electron Neumann BC restores the volume-charge ledger while Gauss closure remains satisfied.

This is **not** yet a production sheath/ion-wall kinetic model. Passing A3e authorizes the next step: replace prescribed charged rates with a physical boundary-flux model without changing the accepted charge-current bookkeeping.

## Current progression

```text
A0    source/species/boundary/capability audit                COMPLETE
A1    wafer prescribed O-flux sign/bookkeeping                PASS
A1b   wafer state-dependent O sticking, s_O=0.2               PASS
A1c   O sticking on all six plasma-facing walls               READY
A3e   prescribed charged-heavy + matched electron ledger      READY

next after A3e evidence:
       physical charged-particle/sheath wall-flux model
       O2s -> O2 and Os -> 0.5 O2
       bounded combined six-wall surface chemistry

later:
       finite SEE + electron-energy coupling after #26
       dielectric surface-charge state when its contract is activated
```

During the current controls, volumetric chemistry, finite SEE, electron-energy coupling, and `sigma_s` remain OFF.
