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
end_time = 2e-5 s
sticking = 0
bulk electrostatic drift = OFF
wall migration = ON
nl_abs_tol = 3e-12
nl_rel_tol = 1e-10
```

Only this quantity changes:

```text
phi_IC(x) = s * 20000 * (1-x)
```

with `s = 0.00, 0.25, 0.50, 0.75, 1.00`.

`nl_forced_its` is deliberately **not** used. The earlier forced-iteration diagnostic already failed for both hard and smooth gates; including it here would introduce a second changed variable and invalidate the IC-only sweep.

## Execute

From this directory:

```bash
bash run_sweep.sh /path/to/working/qpx-opt
```

The runner creates case inputs from `phi_ic_sweep.template.i`, captures one solver log per amplitude, writes solver return codes, and then runs `analyze_sweep.py`.

Generated runtime outputs are ignored by Git through the local `.gitignore`:

```text
generated/
logs/
status/
```

## Required evidence

Preserve for every amplitude:

- solver return status;
- first positive-time `ion_mass_inventory`;
- `left_migration_mass_loss_rate`;
- `right_migration_mass_loss_rate`;
- closure ratio `C=(-dm/dt)/G_end`;
- `phi_min` and `phi_max`;
- solver log if conservation fails or behavior is anomalous.

The authoritative pre-registered interpretation table is:

`docs/incidents/m5_phi_ic_sweep_decision_matrix.md`

The numeric sweep result and selected classification must be appended to:

`docs/incidents/m5_wall_migration_evidence_log.md`

## Investigation discipline

Do not alter production wall physics based on one amplitude. Complete the sweep, classify the pattern using the pre-registered decision matrix, record the numerical evidence, and only then define the next diagnostic.
