# Efficiency Metrics

This directory stores date-stamped efficiency retrospectives and derived batch-level measurements.

Canonical efficiency definitions remain owned by `docs/protocols/metrics_closure.md`. The canonical aggregate monitoring record remains `docs/metrics/issue_efficiency_monitoring.md`, and formally CLOSED work records remain in `docs/metrics/work_closure_efficiency_ledger.md`.

This directory is an observation/reporting surface. It must not redefine `WCC`, `T-WCC`, `RVR`, `EVR`, `DBR`, `RWR`, `CLR`, `FBR`, complexity classes, or closure-quality rules.

## Purpose

- Preserve date-stamped retrospectives without rewriting historical observations.
- Compare execution/batching strategies while respecting issue-local accounting.
- Keep derived batch measurements separate from canonical issue-local metrics.
- Record evidence quality explicitly when historical values are reconstructed.
- Identify whether interaction cost is moving from implementation defects toward validator, control-plane, or environment defects.
- Generate testable process hypotheses for future comparable work.

## Structure

```text
docs/metrics/efficiency/
├── README.md
└── snapshots/
    └── YYYY-MM-DD_<topic>.md
```

## Evidence classes

Every retrospective value must be treated as one of:

```text
exact
  Prospectively recorded or directly stated in durable issue/validation evidence.

reconstructed
  Recoverable from explicit issue closure evidence and/or retained interaction history, but not prospectively instrumented at work start.

unavailable
  The retained evidence is insufficient for a defensible value. Do not estimate merely to complete a table.
```

Mark reconstructed values in the report. Do not silently promote reconstructed values into exact ledger observations.

## Canonical-vs-derived rule

Canonical metrics are issue-local:

```text
WCC
T-WCC
RVR
EVR
DBR
RWR
CLR
FBR
```

A single consolidated user-local validation return may be attributable to multiple sibling Issues and therefore count in each Issue's local EVR when it directly validates each Issue. Do not divide one canonical EVR fractionally across Issues.

Batch-level quantities such as:

```text
unique user interaction rounds / Issues closed
Issues closed / unique user interaction round
owners validated / consolidated validation return
validation returns / batch
```

are derived process measurements only. They may be useful for batching analysis but must never replace or be mixed into issue-local WCC/EVR accounting.

## EVR interpretation

`MET-05 EVR` counts user-local QPX/diagnostic execution result returns attributable to the work item. A marker such as:

```text
ISSUEXX_REFACTOR_EVRS: 0
```

may prove that no scientific runtime/P3 evidence was consumed, but it does **not** imply canonical `EVR=0` when the user executed and returned final guards or self-tests. Retrospectives must distinguish:

```text
scientific runtime/P3 consumption
canonical external validation rounds (EVR)
```

## Snapshot discipline

Each snapshot should record:

- scope and comparison class;
- source/evidence boundaries;
- canonical issue-local values where defensible;
- derived batch measurements separately;
- unresolved metric gaps;
- process interpretation;
- one or more prospective hypotheses that can be tested by later comparable work.

Do not infer causal improvement from a small sample. Preserve denominator, complexity/work-type differences, and closure-quality evidence when comparing trends.
