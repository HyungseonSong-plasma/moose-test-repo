# Issue #31 — R4-QF1 closed electrostatic feedback + C2

R4-QF1 is the first bounded R4 case in which solved `potential_plasma` actually participates in charged-particle transport.

## Frozen scope

```text
R4-QN0 quasi-neutral initialization       PRESERVED
Poisson potential_plasma                  ON
all electrostatic boundaries              phi = 0

electron electrostatic drift              potential_plasma
O2+ / O- / O+ electrostatic drift          potential_plasma
heavy mass EM correction                   potential_plasma

surface accumulated charge sigma_s         OFF
volumetric reactions                       OFF
secondary emission                         OFF
timestep                                   unchanged (1e-8 s)
mobility / diffusion                       unchanged
```

## Physical inlet feed

QF1 separates the external feed composition from the already-ionized initial plasma composition.

```text
feed gas                         pure O2
feed flow                        20 sccm
feed O2 mass fraction            1.0
feed O2s/O2+/O/O-/O+/Os          0
feed molar mass                  0.032 kg/mol
```

The accepted R3/QN0 initial values are retained as initial-plasma provenance and still define the nominal quasi-neutral electron reference before feed separation. They are not reused as the QF1 inlet composition.

O2 is the constrained heavy species in the current formulation, so it has no independent scalar inlet BC. Pure-O2 feed is represented by the full total inlet mass flux together with exactly zero inlet scalar mass flux for all six solved non-O2 species:

```text
Q_sccm = 20
M_inlet = 0.032

inlet_mdot_O2s = 0
inlet_mdot_O2p = 0
inlet_mdot_O   = 0
inlet_mdot_Om  = 0
inlet_mdot_Op  = 0
inlet_mdot_Os  = 0
```

Thus the complete 20 sccm mass feed is O2 without replacing the ionized initial plasma state by neutral feed gas.

The electron solver representation remains

```text
n_e == n_hat ~ O(1)
n_e_physical = n_e_value*n_e
n_e_value = quasi-neutral heavy-charge reference
```

No return to a raw dimensional electron FV unknown is permitted.

## Closed feedback loop

QF1 closes

```text
heavy/electron state
      -> rho_q
      -> solved potential_plasma
      -> E = -grad(potential_plasma)
      -> charged-heavy + electron drift
      -> new heavy/electron state
      -> rho_q
```

The exact feedback set is four `QPXFVElectrostaticDrift` kernels (`O2p`, `Om`, `Op`, `n_e`) plus six `QPXFVHeavyMassElectromigrationCorrection` kernels for the solved heavy species. Their existing `boundaries_to_avoid` lists are preserved exactly.

## C1

The accepted Q0/QN0 Gauss-law observables remain active:

```text
Q_volume = integral(rho_q dV)
Q_gauss  = eps0 * integral(-eps_r*grad(phi).n dA)
R_G      = Q_gauss - Q_volume
```

The prior qvt relative C1 reconstruction scale is evidence, not a hard-coded universal threshold.

## C2 global dynamic charge conservation

Current chemistry is OFF, so

```text
Delta_Q + Q_boundary = 0
```

with outward boundary current positive.

C2 uses the **actual discretized initial charge**, not `Q(0)=0` by assumption. The accepted initial `w_O` state is a spatial `FunctionIC`; through `Mn_mix` and `rho` this changes the integrated heavy charge even when the nominal top-level QN ledger is algebraically neutral. QF1 therefore executes

```text
r31_charge_integral
  execute_on = 'INITIAL TIMESTEP_END'
```

and measures

```text
Delta_Q = Q_volume(t1) - Q_volume(t0)
```

from the same postprocessor at both states.

The electrostatic drift and heavy EM-correction kernels explicitly avoid every physical plasma boundary. The current electron model has no bulk-advection boundary operator and its diffusion path retains natural zero external flux in this scope. Therefore the explicit QF1 external charge-current ledger is owned by the charged-heavy inlet/outlet advective mass fluxes:

```text
I_boundary = e*N_A * sum_k z_k * (mdot_out,k - mdot_in,k) / M_k
k = O2p, Om, Op
```

Under the pure-O2 feed all charged-heavy inlet terms are exactly zero. Any C2 boundary charge current therefore comes from charged species leaving through the outlet in this QF1 scope.

The accepted time scheme is implicit Euler, so for the one-step discriminator:

```text
Q_boundary = dt * I_boundary(t_{n+1})
R_Q = Delta_Q + Q_boundary
```

The runner records both a component-relative defect and a carrier-charge-scaled defect. The first closed-feedback run is measurement-only; no universal C2 threshold is invented before evidence exists.

## Run

```bash
git pull

python -m experiments.Issue31_r4_qf1_closed_feedback.run \
  --qpx "$QPX_OPT" \
  --results-root "$PWD/r4_results"
```

Bounded queue:

```text
canonical QF1 construction/audit
-> qpx-opt --check-input
-> one monolithic implicit QF1 runtime
-> preserved physical state/inventory checker
-> C1 Gauss-law measurement
-> potential/charge state measurement
-> C2 global charge ledger using measured Q(t0), Q(t1)
```

A complete measurement terminates as

```text
ISSUE31_R4_QF1_STATUS: R4_QF1_EVIDENCE_READY
```

`R4_QF1_EVIDENCE_READY` is not automatic scientific PASS. Interpret nonlinear convergence, field magnitude, electron/heavy state bounds, C1, and C2 together. If the monolithic feedback run is unsuitable, only then use the already-declared dielectric-relaxation / multirate evidence to decide whether an inner electron-Poisson iteration or another bounded coupling architecture is needed.
