# Metrics Context

**Status:** canonical metrics observation entry point  
**Scope:** operational evidence used to evaluate and improve the MOOSE/QPX operating system  
**Canonical metric semantics:** `docs/protocols/metrics_closure.md`

This directory stores observations, ledgers, snapshots, and derived analyses. It does **not** redefine the canonical metric rules.

The operating system should improve from measured evidence rather than from anecdotal impressions alone. `moose-test-init` therefore loads a compact current metrics context in addition to the rule working set.

## Directory structure

```text
docs/metrics/
├── README.md
├── issue_efficiency_monitoring.md
├── work_closure_efficiency_ledger.md
├── efficiency/
│   ├── README.md
│   └── snapshots/
│       └── YYYY-MM-DD_<topic>.md
└── incidents/
    ├── README.md
    ├── learning_ledger.md
    └── snapshots/
        └── YYYY-MM-DD_<topic>.md
```

## Ownership

```text
docs/protocols/metrics_closure.md
  -> canonical definitions and closure/learning rules

docs/metrics/issue_efficiency_monitoring.md
  -> longitudinal issue-efficiency monitoring

docs/metrics/work_closure_efficiency_ledger.md
  -> formally CLOSED work records

docs/metrics/efficiency/
  -> date-stamped efficiency retrospectives and derived batch measurements

docs/metrics/incidents/
  -> incident-learning aggregate measurements and snapshots
```

Individual incident narratives remain owned by `docs/incidents/`.

## `moose-test-init` metrics bootstrap

On every `moose-test-init`, restore a compact **METRICS CONTEXT** from canonical repository data before declaring initialization complete.

Always read:

```text
1. docs/metrics/README.md
2. docs/metrics/issue_efficiency_monitoring.md
3. docs/metrics/work_closure_efficiency_ledger.md
4. docs/metrics/efficiency/README.md
5. the latest date-stamped file under docs/metrics/efficiency/snapshots/, when present
6. docs/metrics/incidents/README.md
7. the latest date-stamped file under docs/metrics/incidents/snapshots/, when present
```

Read `docs/metrics/incidents/learning_ledger.md` at bootstrap when the current work is about incidents, recurrence, gate effectiveness, rule promotion, operating-system improvement, or when the latest incident snapshot indicates a material unresolved prevention-learning question.

Do not preload every historical snapshot. Load older snapshots only when a trend comparison or historical reconciliation requires them.

## Bootstrap interpretation

The metrics context is observation/evidence, not another rule pack.

At initialization, extract at minimum:

```text
Current efficiency baseline / latest monitored trend
Latest refactor or batch-efficiency observation when available
Latest incident/root-cause observation
Material known process bottleneck or improvement hypothesis
Metric-data limitations (exact / reconstructed / unavailable) when relevant
```

These observations should inform planning decisions such as:

```text
Issue/work-batch sizing
validation batching
preflight investment
validator/gate hardening
rule enforcement promotion
clarification reduction
reuse of accepted evidence
```

They must not override scientific or closure-quality constraints merely to improve efficiency numbers.

## Data-driven operating-system improvement

When proposing a new operating rule, gate, batching strategy, or workflow change, first ask whether current metrics support the intervention.

Preferred loop:

```text
observe metrics
-> identify dominant interaction / failure cost
-> form a bounded process hypothesis
-> apply the smallest justified operating change
-> instrument subsequent comparable work prospectively
-> compare later metrics against the baseline
-> retain, revise, or retire the change based on evidence
```

Avoid optimizing one metric in isolation. The canonical objective remains to reduce interaction/execution cost subject to preserved closure quality.

## Metric discipline

Use the canonical issue-local metrics from `docs/protocols/metrics_closure.md`:

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

Derived batch-level quantities may supplement those metrics but must not replace or be confused with issue-local accounting.

Historical values must be labeled accurately as:

```text
exact
reconstructed
unavailable
```

Do not invent missing values to make a trend table complete.
