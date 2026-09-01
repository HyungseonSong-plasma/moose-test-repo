# Incident Learning Ledger

**Status:** prospective operational metric ledger  
**Prospective start:** 2026-09-01  
**Canonical semantics:** `docs/protocols/metrics_closure.md` / `MET-20`, `MET-21`, `MET-22`  
**Working-set semantics:** `docs/protocols/rule_working_set.md`

This ledger records one row per incident only after incident-level evidence is sufficient to classify both the technical root cause and the prevention-learning status. Individual incident evidence remains under `docs/incidents/` or the attributable GitHub issue.

## Records

| Date | Incident / issue | Root-cause class | Learning status | Pre-existing rule / knowledge owner | Applicable phase pack | Rule/pack active at incident? | Machine gate before incident? | Gate invoked? | Detection stage | EPR required? | Enforcement decision | Prevention maturity | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-01 | #50 sync wrong mutator — sixth repository wrong-action recurrence | Repository mutation call-routing failure: issue-only intent routed to file mutator | KNOWN_AND_GATE_BYPASSED | `docs/protocols/repository_mutation.md` RM-06D/RM-06F/RM-06G/RM-06H | MUTATE | yes | no | no | repository write / connector rejected with 409 | yes | STRENGTHEN_TRIGGER_OR_ROUTING | TRIGGERED | `docs/incidents/repository_mutation_staging_wrong_action_2026-08-28.md` — Sixth occurrence |
| 2026-09-01 | Incident-learning activation miss after the #50 wrong-action recurrence | Working-set trigger/routing failure: existing incident-recording owners were not autonomously loaded until user prompt | KNOWN_AND_GATE_BYPASSED | `docs/protocols/rule_working_set.md` RWS-05/RWS-09; `docs/protocols/metrics_closure.md` MET-20/MET-22; `docs/metrics/incidents/README.md` | TEMPORARY INCIDENT-LEARNING / CLOSE | no | no | not-applicable | user-observed | no | STRENGTHEN_TRIGGER_OR_ROUTING | TRIGGERED | `docs/incidents/repository_mutation_staging_wrong_action_2026-08-28.md`; `docs/protocols/rule_working_set.md` RWS-05A |
| 2026-09-01 | #50 Issue46 Stats caller migration semantic drift | Full-file replacement transcription drift changed an unrelated structural failure class during narrow caller rewiring | KNOWN_AND_GATE_BYPASSED | `docs/protocols/coding.md` CODE-10; `docs/protocols/repository_mutation.md` RM-01/RM-03/RM-06B | IMPLEMENT / MUTATE | yes | no | no | post-write read-back verification | no | not-required | DOCUMENTED | `docs/incidents/issue46_stats_migration_semantic_drift_2026-09-01.md` |
| 2026-09-01 | #53 Efficiency extraction transcription drift | Full-file replacement transcription drift removed an unrelated closing parenthesis during narrow structural extraction | KNOWN_AND_GATE_BYPASSED | `docs/protocols/coding.md` CODE-10; `docs/protocols/repository_mutation.md` RM-01/RM-03/RM-06B | IMPLEMENT / MUTATE | yes | no | no | post-write commit-diff verification | yes | PROMOTE_TO_MACHINE_GATE | DOCUMENTED | `docs/incidents/issue53_efficiency_extraction_transcription_drift_2026-09-01.md` |
| 2026-09-01 | #53 decomposition inventory stage-blind false FAIL | Validator semantic defect: baseline-only topology invariant rejected valid D1 facade re-export state | GATE_DEFECT | `tests/Issue53_stats_builder_decomposition/inventory.py`; `docs/protocols/coding.md` CODE-13 validation obligations | VALIDATE | yes | yes | yes | user-local validation / terminal exited under `set -e` | no | REPAIR_GATE_AND_SELFTEST | DOCUMENTED | `docs/incidents/issue53_inventory_stage_blind_false_fail_2026-09-01.md` |

## Recording constraints

- Use exactly one primary `MET-20` learning status: `NOVEL`, `KNOWN_BUT_NOT_ENFORCED`, `KNOWN_AND_GATE_BYPASSED`, `GATE_DEFECT`, `ENVIRONMENT_ESCAPE`, or `UNRESOLVED`.
- Do not classify from symptom similarity alone; establish the pre-incident control state.
- Record the phase pack that should have owned the failure when evidence supports it: `PLAN`, `RESEARCH`, `IMPLEMENT`, `VALIDATE`, `CLOSE`, or an auxiliary/temporary pack reference.
- Record `Rule/pack active at incident?` as `yes`, `no`, or `unknown`. A known relevant owner with `no` is evidence for a working-set/routing miss and should be analyzed before adding another semantic rule.
- Distinguish `rule not active` from `machine gate not present`: a semantic rule may exist in inventory without an executable gate.
- `UNRESOLVED` rows remain visible but are excluded from classified-incident denominators.
- Do not reconstruct historical rows from aggregate percentages alone.
- Link to the incident/issue evidence rather than copying RCA narratives into this ledger.
- When `MET-22` triggers an Enforcement Promotion Review, record `EPR required? = yes` and one primary enforcement decision.
- Record prevention maturity as the strongest evidence-backed state: `DOCUMENTED`, `TRIGGERED`, `MACHINE_CHECKED`, `MUTATION_TESTED`, or `IMPOSSIBLE_BY_CONSTRUCTION`.
- Do not claim `MACHINE_CHECKED` or higher without executable applicable-path evidence.

## Working-set miss interpretation

Use the active-pack evidence to distinguish:

```text
relevant owner did not exist
  -> possible NOVEL / RULE_ABSENT

relevant owner existed but was not active
  -> working-set selection or phase-routing failure

owner was active but applicability trigger was missed
  -> trigger/routing failure

mandatory gate existed but was not invoked
  -> KNOWN_AND_GATE_BYPASSED

mandatory gate invoked but produced the wrong decision
  -> GATE_DEFECT
```

Do not create a new MET-20 status solely for working-set misses. Preserve the primary learning status and use these fields to identify the remediation surface.

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
