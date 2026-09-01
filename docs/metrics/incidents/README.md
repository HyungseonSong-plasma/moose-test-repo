# Incident Metrics

This directory contains operational metrics derived from incident/root-cause reviews.

Canonical incident-learning and enforcement semantics are owned by `docs/protocols/metrics_closure.md` (`MET-20`, `MET-21`, `MET-22`). Rule loading/unloading semantics are owned by `docs/protocols/rule_working_set.md`. This directory stores observations and derived measurements; it does not redefine those rules.

## Purpose

- Keep aggregate incident statistics separate from individual incident evidence in `docs/incidents/`.
- Preserve date-stamped snapshots so root-cause distribution can be compared over time.
- Track whether incidents are genuinely novel or are recurrences of already-known failure classes.
- Distinguish missing rules from dormant-but-not-loaded rules, missed triggers, gate bypasses, gate defects, and environment escapes.
- Measure whether known rules are progressing from documentation toward effective prevention.
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
Applicable phase pack
Rule/pack active at incident? yes/no/unknown
Machine gate before incident? yes/no
Gate invoked? yes/no/not-applicable
Detection stage (pre-P2 / P2 / P3 / post-run / user-observed)
EPR required? yes/no
Enforcement decision when applicable
Prevention maturity
Evidence reference
```

Do not infer or backfill a MET-20 learning status or historical working-set state when the evidence cannot establish the pre-incident control state.

## Working-set interpretation

The rule inventory may contain a correct dormant owner even when that owner was not active at the time of failure. Treat this as a routing/working-set problem before proposing another rule.

```text
owner absent
  -> candidate RULE_ABSENT / NOVEL

owner existed but pack inactive
  -> working-set selection failure

pack active but trigger missed
  -> trigger/routing failure

gate required but not invoked
  -> gate bypass

gate invoked but wrong decision
  -> gate defect
```

Use `docs/rules/INVENTORY.md` to locate dormant owners and `docs/protocols/rule_working_set.md` to determine whether they should have been active.

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
working-set miss count/rate when evidence coverage is sufficient
```

Always report the denominator, classification coverage, and unresolved/unknown working-set count. A root-cause percentage distribution alone does not establish whether total incident frequency is rising or falling.

## Historical baseline discipline

Snapshots created before prospective MET-20 and working-set classification are historical baselines. Preserve their root-cause data unchanged and label learning-status or working-set dimensions as unavailable unless incident-level evidence supports reconstruction.
