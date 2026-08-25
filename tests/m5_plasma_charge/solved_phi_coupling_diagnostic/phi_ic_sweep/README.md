# Diagnostic suite: wall migration initial-potential sweep

**Type:** diagnostic / incident isolation  
**Auto-run:** intentionally excluded from `scripts/run_all.py` because this is a parameter sweep rather than a permanent single-case regression.

## Purpose

Test whether first-step wall-migration conservation depends on the amplitude of the initial electrostatic potential even though every case solves the same final Laplace problem.

## Invariant physics/setup

```text
phi(0) = 20000 V
phi(1) = 0 V
rho = 1 kg/m^3
w_O2+ = 1e-6
mu_i = 0.01 m^2/(V s)
z_i = +1
dt = 1e-5 s
sticking = 0
bulk electrostatic drift = OFF
wall migration = ON
```

Only this quantity changes:

```text
phi_IC(x) = s * 20000 * (1-x)
```

with `s = 0.00, 0.25, 0.50, 0.75, 1.00`.

## Execute

From this directory:

```bash
./run_sweep.sh /path/to/working/qpx-opt
```

The runner creates case inputs from `phi_ic_sweep.template.i`, captures one solver log per amplitude, and then runs `analyze_sweep.py`.

## Required evidence

Preserve for every amplitude:

- solver return status;
- first positive-time `ion_mass_inventory`;
- `left_migration_mass_loss_rate`;
- `right_migration_mass_loss_rate`;
- `phi_min` and `phi_max`;
- solver log if conservation fails or behavior is anomalous.

The authoritative interpretation table is:

`docs/incidents/m5_phi_ic_sweep_decision_matrix.md`

The numeric result must be appended to:

`docs/incidents/m5_wall_migration_evidence_log.md`

## Investigation discipline

Do not alter production wall physics based on one amplitude. Complete the sweep, classify the pattern using the pre-registered decision matrix, and only then define the next diagnostic.
