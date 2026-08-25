# sol-adapter-moose Test Workspace

This repository is the dedicated **sol-adapter-moose** workspace for executable regression tests, isolated MOOSE/QPX input cases, development logs, and reusable troubleshooting records.

## Boundary

This repository belongs to the **sol-adapter-moose team only**. Work for other teams or repositories must not be mixed into this workspace.

## Primary uses

- Store self-contained test inputs and checkers.
- Reproduce numerical/solver failures with minimal cases.
- Run tests against a local or repository-provided `qpx-opt` executable.
- Preserve development and incident history.
- Promote closed incidents into reusable troubleshooting knowledge.

## Repository layout

```text
bin/                         optional local/test executable location
docs/
  development/               development notes
  incidents/                 chronological failure investigations
  knowledge/                 reusable troubleshooting knowledge
scripts/                     test runner utilities
tests/
  <area>/<case>/
    test.json                test metadata
    input.i                  executable input
    check.py                 acceptance checker
    <runtime dependencies>   mesh/data/reference files
results/                     generated outputs; not committed
```

## Executable resolution

The runners resolve the executable in this order:

1. `QPX_EXECUTABLE` environment variable
2. `bin/qpx-opt`
3. `qpx-opt` from `PATH`

Example:

```bash
export QPX_EXECUTABLE=/path/to/qpx-opt
python3 scripts/run_test.py tests/m5_plasma_charge/ion_wall_migration_state
```

or, if `bin/qpx-opt` exists:

```bash
python3 scripts/run_test.py tests/m5_plasma_charge/ion_wall_migration_state
```

## Test rule

A regression is not considered closed until its checker passes the intended physical/numerical gates, such as conservation, positivity, directionality, stoichiometry, units, and reference agreement.

Generated CSV/log/output files belong under `results/` and should not replace the canonical input/checker pair in `tests/`.
