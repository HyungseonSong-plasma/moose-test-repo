# Incident Metrics

This directory contains operational metrics derived from incident/root-cause reviews.

Canonical classification and KPI semantics are owned by `docs/protocols/metrics_closure.md` (`MET-20` and `MET-21`). This directory stores observations and derived measurements; it must not redefine those rules.

## Purpose

- Keep aggregate incident statistics separate from individual incident evidence in `docs/incidents/`.
- Preserve date-stamped snapshots so root-cause distribution can be compared over time.
- Track whether incidents are genuinely novel or are recurrences of already-known failure classes.
- Measure whether known rules are machine-enforced, bypassed, defective, or escaped through environment/runtime identity.
- Support trend analysis without rewriting historical observations.

## Structure

```text
docs/metrics/incidents/
├── README.md
├── learning_ledger.md
└── snapshots/
    └── YYYY-MM-DD_root_cause_breakdown.md
```

`docs/incidents/` remains the evidence owner for individual incident narratives, reproducer/root-cause material, and closure evidence. `learning_ledger.md` contains only the minimum incident-level classification needed for cross-incident measurement and links back to that evidence.

## Prospective incident record

For every newly classified incident, append one row to `learning_ledger.md` with at least:

```text
Date
Incident / issue reference
Root-cause class
Learning status (MET-20)
Existing rule / knowledge owner before incident
Machine gate before incident? yes/no
Gate invoked? yes/no/not-applicable
Detection stage (pre-P2 / P2 / P3 / post-run / user-observed)
Evidence reference
```

Do not infer or backfill a MET-20 learning status when the historical evidence cannot establish the pre-incident control state.

## Snapshot rule

Each snapshot must preserve the reported category percentages and incident descriptors as observed on that date. Any regrouping or higher-level operational interpretation must be marked as derived analysis rather than source data.

When incident-level MET-20 coverage exists, snapshots should additionally report:

```text
classification coverage
incident rate / bounded work item
known recurrence rate
pre-execution catch rate
gate-bypass rate
gate-defect rate
enforcement coverage
novel-class share
```

Always report the denominator and unresolved count. A root-cause percentage distribution alone does not establish whether total incident frequency is rising or falling.

## Historical baseline discipline

Snapshots created before prospective MET-20 classification are historical baselines. Preserve their root-cause data unchanged and label the learning-status dimension as unavailable unless incident-level evidence supports reconstruction.