# Issue #31 — R4-QF2 local charge relaxation

R4-QF2 is the final bounded discriminator before closing R4 and moving to surface-reaction work.

It starts from the accepted R4-QF1 state:

```text
uniform ionized heavy initial plasma
20 sccm pure O2 inlet
physical n_e reference consistent with QPX charge convention
solved potential_plasma
all-ground electrostatic boundary
closed electron + charged-heavy electrostatic feedback
surface accumulated charge sigma_s OFF
volumetric reactions OFF
secondary emission OFF
dt = 1e-8 s
```

## Controlled perturbation

QF2 changes only the electron initial field. The normalized solver unknown is initialized as

```text
n_hat(y) = 1 + 1e-4 * (y - y_bar) / y_scale
```

with the canonical real-qvt RZ geometry constants

```text
y_bar   = 0.1789375023987653 m
y_scale = 0.15883232862245206 m
```

`y_bar` is the RZ-volume-weighted FV cell-centroid mean of the plasma subdomain. Therefore the intended discrete perturbation has zero volume mean while creating non-zero local charge separation. The expected normalized electron range is approximately

```text
0.9999 <= n_hat <= 1.00008753
```

The runtime never assumes perfect cancellation. It directly measures the initial integrated charge and local charge-density extrema.

## Observables

QF2 records both `INITIAL` and `TIMESTEP_END` for:

```text
n_e_min
n_e_max
n_e_avg
r31_charge_integral
r31_qf2_charge_density_min
r31_qf2_charge_density_max
```

It also preserves the QF1 Poisson state, Gauss-law C1 observables, and C2 global charge ledger.

The local relaxation metric is

```text
A_q(t) = max(abs(rho_q_min), abs(rho_q_max))
R_relax = A_q(t1) / A_q(t0)
```

## Predeclared acceptance gates

```text
initial local charge amplitude       >= 1e-8 C/m3
initial global charge / carrier      <= 1e-6
local charge relaxation ratio        <= 0.5
C1 Gauss relative defect             <= 1e-3
C2 carrier-scaled defect             <= 1e-10
R3 physical invariants               PASS
```

Potential is recorded as evidence but is not assigned an arbitrary lower bound. A very small final potential is compatible with successful rapid charge relaxation in the monolithic implicit solve.

If all gates pass, the runner emits

```text
R4_QF2_PASS_READY_TO_CLOSE_R4
```

which is the predeclared condition for closing Issue #31 and moving the next development problem to surface reaction / surface accumulated charge physics.

## Run

```bash
git pull

git rev-parse HEAD

python -m experiments.Issue31_r4_qf2_local_charge_relaxation.run \
  --qpx "$QPX_OPT" \
  --results-root "$PWD/r4_results"
```

Upload the resulting `issue31_r4_qf2_local_charge_relaxation_<timestamp>` bundle for final scientific interpretation before the issue-state mutation is performed.
