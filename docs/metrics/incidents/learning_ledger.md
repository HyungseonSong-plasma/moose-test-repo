# Incident Learning Ledger

**Status:** prospective operational metric ledger  
**Prospective start:** 2026-09-01  
**Canonical semantics:** `docs/protocols/metrics_closure.md` / `MET-20`, `MET-21`

This ledger records one row per incident only after incident-level evidence is sufficient to classify both the technical root cause and the prevention-learning status. Individual incident evidence remains under `docs/incidents/` or the attributable GitHub issue.

## Records

| Date | Incident / issue | Root-cause class | Learning status | Pre-existing rule / knowledge owner | Machine gate before incident? | Gate invoked? | Detection stage | Evidence |
|---|---|---|---|---|---|---|---|---|

## Recording constraints

- Use exactly one primary `MET-20` learning status: `NOVEL`, `KNOWN_BUT_NOT_ENFORCED`, `KNOWN_AND_GATE_BYPASSED`, `GATE_DEFECT`, `ENVIRONMENT_ESCAPE`, or `UNRESOLVED`.
- Do not classify from symptom similarity alone; establish the pre-incident control state.
- `UNRESOLVED` rows remain visible but are excluded from classified-incident denominators.
- Do not reconstruct historical rows from aggregate percentages alone.
- Link to the incident/issue evidence rather than copying RCA narratives into this ledger.

## KPI notes

Aggregate snapshots derive prevention-learning KPIs from this ledger using `MET-21`. Every reported rate must include its denominator and classification coverage.