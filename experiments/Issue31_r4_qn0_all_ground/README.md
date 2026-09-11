# Issue #31 — R4-QN0 quasi-neutral all-ground Poisson control

R4-QN0 is the bounded successor to the accepted R4-Q0 construction. It changes only the initial electron reference density before electrostatic transport feedback is enabled.

## Frozen scope

```text
accepted R4-Q0 construction               PRESERVED
physical volume charge                    ON
solved potential_plasma                   ON
all electrostatic boundaries              phi = 0
quasi-neutral initialization              ON
electrostatic transport feedback          OFF
surface accumulated charge (sigma_s)      OFF
secondary emission                        OFF
volumetric reactions                      OFF
```

The electron solver variable remains normalized:

```text
n_e == n_hat
initial n_e = 1.0
n_e_physical = n_e_value*n_e
```

Only `n_e_value` changes.

## Quasi-neutral reference

The reference is derived from the frozen initial heavy-species ledger rather than from a prior Poisson result:

```text
Mn0 = 1 / sum_k(Yin_k/M_k)
rho0 = outlet_pressure*Mn0/(R*T_g_value)

n_e,QN = rho0*N_A*(Yin_O2p/0.032 - Yin_Om/0.016 + Yin_Op/0.016)
```

For the current accepted oxygen input this is approximately

```text
n_e,QN = 1.297913466685e18 m^-3
```

while the solver initial condition remains `1.0`. This preserves the R3 normalization remedy and changes only the dimensional reference carried by `n_e_physical`.

The static construction audit requires the initial charge-number closure

```text
sum(z_k*n_k) - n_e,QN = 0
```

up to floating-point arithmetic.

## What QN0 measures

QN0 retains the R4-Q0 Poisson and Gauss-law diagnostics and additionally records:

```text
n_e_avg/min/max
Q_volume = integral(rho_q dV)
average rho_q = Q_volume/domain_volume
phi_min
phi_max
phi_span
max(abs(phi))
```

No new universal acceptance threshold is hard-coded. The purpose of this run is to determine whether the extreme R4-Q0 potential scale collapses when the initial charge ledger is physically balanced, while preserving P2, nonlinear convergence, the R3 physical invariants, and C1 Gauss-law evidence.

## Run

```bash
git pull

python -m experiments.Issue31_r4_qn0_all_ground.run \
  --qpx "$PHYSICS_EXECUTABLE" \
  --results-root "$PWD/r4_results"
```

The queue is:

```text
canonical QN0 construction/audit
-> physics-opt --check-input
-> one feedback-off R4-QN0 runtime
-> R3 physical invariant checker using the QN electron reference
-> C1 Gauss-law measurement
-> QN0 charge/potential measurement
```

A complete measurement terminates as:

```text
ISSUE31_R4_QN0_STATUS: R4_QN0_EVIDENCE_READY
```

`R4_QN0_EVIDENCE_READY` is not yet the self-consistent R4 acceptance. Return the complete directory printed as `ISSUE31_R4_QN0_ROOT`. Only after the QN0 potential/charge state is interpreted should `potential_plasma` be connected to heavy/electron drift and the C2 dynamic charge-conservation ledger be activated.
