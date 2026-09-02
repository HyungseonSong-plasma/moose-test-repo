# Pytest validation namespace

`tests/` is reserved for qpx-free pytest validation.

Allowed content:

- unit tests for reusable Python capabilities;
- scientific characterization based on synthetic fixtures or persisted evidence;
- architecture/import/ownership invariants.

Forbidden from the default pytest suite:

- `qpx-opt` execution;
- framework-effective `--check-input` / P2 execution;
- P3 scientific runtime;
- EVR consumption;
- repository-local `test.json` experiment workspaces.

QPX/MOOSE runtime assets belong under `experiments/`. Exploratory scientific analysis belongs under `studies/`.
