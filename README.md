# moose-test-repo Test Workspace

Shared MOOSE/QPX workspace for executable regression tests, isolated input cases, development logs, and reusable troubleshooting evidence.

## Start here

Operational behavior is defined in one canonical chain:

```text
OPERATING_CORE.md
  -> PROTOCOL_INDEX.md
       -> docs/protocols/problem_solving.md
       -> docs/protocols/validation.md
       -> docs/protocols/metrics_closure.md
```

Load only the procedure selected by `PROTOCOL_INDEX.md`. Reusable incident knowledge lives in `docs/knowledge/TROUBLESHOOTING_INDEX.md`. Current work state lives in the active GitHub issue body.

## Repository layout

```text
OPERATING_CORE.md              always-active invariants
PROTOCOL_INDEX.md              deterministic procedure router
WORKSPACE.md                   repository boundary

docs/
  protocols/                   canonical conditional procedures
  incidents/                   chronological failure investigations
  knowledge/                   reusable troubleshooting knowledge
  development/                 development notes
  guides/                      deprecated compatibility entry points

scripts/                       runner/checker utilities
tests/                         canonical test inputs/checkers
bin/                           optional local/test executable location
results/                       generated outputs; not canonical
```

## Runtime evidence

Canonical QPX runtime evidence comes from the user's real local `qpx-opt`. Runners receiving an explicit executable path must resolve it before changing directories; see `CORE-06` and `CORE-14` in `OPERATING_CORE.md`.

## Canonical test shape

A persistent regression should remain self-contained, for example:

```text
<case>/
  test.json
  input.i
  check.py
  <required mesh/data/reference files>
```

Acceptance and checker requirements are defined only in `docs/protocols/validation.md`; this README intentionally does not duplicate them.