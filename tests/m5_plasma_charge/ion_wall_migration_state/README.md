# Ion wall migration state diagnostics

Purpose: isolate when solved-potential-dependent ion wall migration participates in the FV transient residual.

Cases:

```text
migration_only_zero_phi_ic/
  migration only, phi starts at zero

migration_only_exact_phi_ic/
  migration only, phi starts from exact linear Laplace solution

full_exact_phi_ic/
  surface + migration wall closure, exact initial phi
```

The shared checker compares the first-step ion inventory change against the integrated FV wall-flux contributions.

Run one case:

```bash
python3 scripts/run_test.py \
  tests/m5_plasma_charge/ion_wall_migration_state/migration_only_zero_phi_ic
```

Run all repository tests:

```bash
python3 scripts/run_all.py
```
