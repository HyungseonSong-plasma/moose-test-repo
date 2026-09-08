# Issue #27 — Oxygen surface reactions

Status: **A1 + A1b + A1c + A2 + A3 + A3e scientifically accepted; A4 excited-neutral quenching ready for user-local QPX**

Canonical internal validation and scientific execution:

```bash
python qpx -i all

python qpx -e experiments/Issue27_surface_reactions/A4_excited_neutral_quenching/experiment.json
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
J_out < 0 => species is returned from the wall into the plasma volume
```

A1 runtime evidence froze the MOOSE mapping:

```text
physical outward-positive J_out
    -> FVNeumannBC.value = -J_out
```

For state-dependent neutral sticking controls this becomes an outward-positive flux functor with

```text
FVFunctorNeumannBC.factor = -1
```

when the surface process is active.

## A1b — accepted neutral O sticking

For `O -> 0.5 O2` with `s_O = 0.2` and Motz-Wise correction OFF:

```text
J_O,out = (s_O/4) * rho * w_O * sqrt(8*R*T_g/(pi*M_O))
```

The implementation uses an outward-positive functor and `FVFunctorNeumannBC.factor = -1` on the target wall. User-local A1b evidence confirmed state-dependent nonlinear assembly, O inventory loss, constrained-O2 return, total-mass closure, and preserved Poisson/Gauss behavior.

## A1c — accepted all-six-wall O sticking

A1c applies the accepted A1b O-sticking law simultaneously to all six plasma-facing wall sidesets and nowhere else.

```text
control  : same flux functor, BC factor = 0
sticking : same flux functor, BC factor = -1
```

User-local evidence extended the accepted state-dependent wall law from `plasma_wafer` to the complete six-wall plasma-facing set while keeping `inlet` and `outlet` excluded.

The discriminator measures the combined six-wall surface rate and compares control-relative O loss with the implicit-Euler transfer

```text
|Delta m_O| ~= integral_wall(J_O,out dA) * dt
```

while checking constrained O2, total mass, neutral charge response, and nonnegative mass fractions.

## A2 — accepted O- -> O charged-heavy control

A2 isolates the COMSOL Phase-A negative-ion wall reaction

```text
O- -> O
```

on all six plasma-facing walls with a prescribed event flux, SEE OFF, and electron wall compensation OFF.

For outward-positive event flux `R_Om [mol/m2/s]`:

```text
J_Om,out = +M_O * R_Om
J_O,out  = -M_O * R_Om
Delta Q_plasma = +F * R_Om * A_wall * dt
```

User-local A2 evidence is accepted as scientific PASS. The measured `Om` loss and `O` return matched the prescribed transfer to about `7e-9` relative defect, total heavy mass change was zero, and the measured plasma-volume charge shift was positive with about `1.1e-4` relative defect from the predicted charge change.

A2 does not create a plasma electron and does not enforce algebraic quasi-neutrality at the wall.

## A3 — accepted O2+ -> O2 and O+ -> O positive-ion controls

A3 isolates the two positive-ion neutralization reactions with `SEE = 0` and no electron-wall compensation:

```text
O2+ -> constrained O2
O+  -> O
```

The bounded discriminator uses:

```text
control
  all A3 wall fluxes = 0

o2p_only
  O2p outward loss ON
  constrained O2 return through N-1 bookkeeping

op_only
  Op outward loss ON
  equal-mass O return ON
```

For either singly positive ion,

```text
Delta Q_plasma = -F * R_i * A_wall * dt
```

User-local A3 evidence is accepted as scientific PASS. Both positive-ion controls produced the predicted negative plasma-volume charge shift with about `1.1e-4` relative charge defect, while the species/product mass bookkeeping closed to approximately `1e-9` relative scale and electron inventory remained unchanged.

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

the electron FV boundary flux is normalized as

```text
physical electron number flux Gamma_e,out [1/m2/s]
normalized FV flux             = Gamma_e,out / n_ref [m/s]
FVNeumannBC.value              = -Gamma_e,out / n_ref
```

## A3e — accepted charged-wall global ledger

A3e composes the individually accepted A2/A3 prescribed rates:

```text
R_O2p = 1.0e-4 mol/m2/s
R_Op  = 1.0e-4 mol/m2/s
R_Om  = 5.0e-5 mol/m2/s
R_e   = R_O2p + R_Op - R_Om = 1.5e-4 mol/m2/s
SEE   = 0
```

The bounded batch contains:

```text
control
  all new charged wall fluxes = 0

heavy_only
  O2p / Op / Om losses ON
  stoichiometric neutral return ON
  electron wall absorption OFF

charge_balanced
  same heavy wall fluxes
  + matched electron absorption
```

Expected charge behavior is

```text
heavy_only:
  Delta Q_plasma ~= -F*(R_O2p + R_Op - R_Om)*A_wall*dt

charge_balanced:
  Delta Q_plasma relative to control -> approximately 0
```

User-local A3e evidence is accepted as scientific PASS. The heavy-only charge shift matched prediction to about `1.1e-4` relative defect. Matched electron absorption reduced the residual charge to about `2.5e-10` of the original heavy-only imbalance; the electron inventory defect was also about `2.5e-10`, and the balanced Gauss defect was effectively numerical zero.

This accepts the Phase-A charged-particle boundary-current bookkeeping with SEE disabled. It is still not a production sheath/ion-wall kinetic law.

## A4 — excited-neutral state-dependent wall quenching

A4 consumes the neutral sticking mechanism already accepted in A1b/A1c and applies the source coefficients directly:

```text
O2s -> constrained O2        sticking = 1.0
Os  -> 0.5 constrained O2   sticking = 0.2
Motz-Wise                    OFF
```

For each neutral species `k`,

```text
J_k,out = (s_k/4) * rho * w_k * sqrt(8*R*T_g/(pi*M_k))
```

on all six plasma-facing walls. `inlet` and `outlet` remain excluded.

The bounded batch is:

```text
control
  both A4 BC factors = 0

o2s_quench
  O2s state-dependent wall loss ON
  Os wall loss OFF

os_quench
  Os state-dependent wall loss ON
  O2s wall loss OFF
```

No explicit O2 boundary equation is added. Because O2 is the constrained N-1 species, loss of solved `O2s` or `Os` must appear as equal-mass constrained-O2 return. A4 acceptance checks each species loss against its integrated state-dependent wall rate, constrained-O2 return, total heavy-mass closure, neutral charge invariance, Gauss consistency, and nonnegative mass fractions.

## Current progression

```text
A0    source/species/boundary/capability audit                COMPLETE
A1    wafer prescribed O-flux sign/bookkeeping                PASS
A1b   wafer state-dependent O sticking, s_O=0.2               PASS
A1c   O sticking on all six plasma-facing walls               PASS
A2    O- -> O prescribed six-wall charge-shift control        PASS
A3    O2+/O+ prescribed positive-ion controls, SEE=0          PASS
A3e   charged-heavy + matched electron global ledger          PASS
A4    O2s/Os state-dependent neutral quenching                READY

next:
       run A4 user-local scientific evidence
       then bounded combined six-wall Phase-A surface chemistry
       then replace prescribed charged rates with physical sheath/ion wall kinetics

later:
       finite SEE + electron-energy coupling after #26
       dielectric surface-charge state when its contract is activated
```

During the current controls, volumetric chemistry, finite SEE, electron-energy coupling, and `sigma_s` remain OFF.
