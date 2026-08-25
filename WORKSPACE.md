# Workspace Operating Boundary

## Team ownership

This repository is reserved for **sol-adapter-moose** work.

The repository may contain:

- MOOSE/QPX regression inputs used by the sol-adapter-moose team.
- Minimal failure reproducer inputs.
- Checkers and reference data.
- Development logs and troubleshooting records.
- Test executable notes or a compatible local executable under `bin/`.

The repository must not be used to perform or modify work owned by a different team/workspace.

## Development rule

When a new failure occurs:

1. Identify the last known-good baseline.
2. Record the first bad change.
3. Build the smallest reproducer possible.
4. Preserve failed diagnostic branches/results in the incident log.
5. Change one suspected mechanism at a time.
6. Close the incident only after a regression checker passes.
7. Promote the reusable lesson into `docs/knowledge/`.

## Test packaging rule

Each canonical test directory should be self-contained:

```text
<case>/
  test.json
  input.i
  check.py
  <required mesh/data/reference files>
```

A checker is part of the test definition, not optional documentation.

## Source-code rule

This repository is primarily a test and development-log workspace. Production source changes belong in the appropriate source repository. Small source deltas may be attached to an incident only when they are needed to document/reproduce a failure investigation.
