# Incident Learning Ledger

**Status:** prospective operational metric ledger  
**Prospective start:** 2026-09-01  
**Canonical semantics:** `docs/protocols/metrics_closure.md` / `MET-20`, `MET-21`, `MET-22`

This ledger records one row per incident only after incident-level evidence is sufficient to classify both the technical root cause and the prevention-learning status. Individual incident evidence remains under `docs/incidents/` or the attributable GitHub issue.

## Records

| Date | Incident / issue | Root-cause class | Learning status | Pre-existing rule / knowledge owner | Machine gate before incident? | Gate invoked? | Detection stage | EPR required? | Enforcement decision | Prevention maturity | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Recording constraints

- Use exactly one primary `MET-20` learning status: `NOVEL`, `KNOWN_BUT_NOT_ENFORCED`, `KNOWN_AND_GATE_BYPASSED`, `GATE_DEFECT`, `ENVIRONMENT_ESCAPE`, or `UNRESOLVED`.
- Do not classify from symptom similarity alone; establish the pre-incident control state.
- `UNRESOLVED` rows remain visible but are excluded from classified-incident denominators.
- Do not reconstruct historical rows from aggregate percentages alone.
- Link to the incident/issue evidence rather than copying RCA narratives into this ledger.
- When `MET-22` triggers an Enforcement Promotion Review, record `EPR required? = yes` and one primary enforcement decision.
- Record prevention maturity as the strongest evidence-backed state: `DOCUMENTED`, `TRIGGERED`, `MACHINE_CHECKED`, `MUTATION_TESTED`, or `IMPOSSIBLE_BY_CONSTRUCTION`.
- Do not claim `MACHINE_CHECKED` or higher without executable applicable-path evidence.

## Enforcement decision values

Use the canonical `MET-22` outcomes:

```text
PROMOTE_TO_MACHINE_GATE
STRENGTHEN_TRIGGER_OR_ROUTING
REPAIR_GATE_AND_SELFTEST
HARDEN_ENVIRONMENT_IDENTITY
IMPOSSIBLE_BY_CONSTRUCTION
RETAIN_MANUAL_WITH_JUSTIFICATION
DEFER_PENDING_EVIDENCE
```

For an incident that does not trigger EPR, record the targeted remediation decision only when one is materially required; otherwise use `not-required` rather than inventing a promotion action.

## KPI notes

Aggregate snapshots derive prevention-learning KPIs from this ledger using `MET-21`. Every reported rate must include its denominator and classification coverage.

Prevention success is recorded when a known invalid state is blocked by the applicable gate before expensive execution. Such a blocked state contributes to pre-execution catch measurements and is not counted as a new incident recurrence merely because the gate observed it.