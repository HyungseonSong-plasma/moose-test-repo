# Issue46 Stats migration semantic drift incident — 2026-09-01

**Status:** repaired / recorded  
**Affected work:** #50 common-mapping consolidation  
**Affected file:** `qpx_harness/issue46_jacobian_localization.py`

## Incident

The intended change was limited to replacing Issue46's duplicated runtime/result-style Stats plumbing with the canonical runtime Stats builder.

During the full-file replacement, one unrelated failure class in `audit_framework_control_structure()` changed unintentionally:

```text
expected unchanged value:
MOOSE_CONSTRAINT_CONTROL_STRUCTURE_FAIL

accidental value:
MOOSE_CONSTRAINT_CONTROL_FAIL
```

This was outside the declared semantic scope of the Stats migration.

## Detection

The drift was detected during post-write read-back verification before user-local validation was requested. The Stats rewiring itself was not the source of the semantic difference; the unrelated classifier text changed while reconstructing the complete file replacement payload.

## Repository history

```text
f69446ec0be377338c0feb76587f5efed5618a81
  Use canonical runtime SimulationStats builder in Issue46
  -> introduced the unintended failure-class drift

f92cb51f8a65dd26d22f917f6ff5fd9fb6efb9b9
  Repair Issue46 structure failure class after migration
  -> restored MOOSE_CONSTRAINT_CONTROL_STRUCTURE_FAIL
```

## Impact

- no physics or numerical model change was intended;
- no runtime evidence was used to accept the accidental state;
- the drift affected a structural failure classification path;
- post-write verification caught the drift before the deferred local-validation queue was discharged;
- the incorrect classifier was repaired immediately.

## Root cause

**Full-file replacement transcription drift during a narrow caller migration.**

The existing rules already required preservation of unchanged behavior and explicit expected-unchanged scope, but the complete replacement payload was not constrained tightly enough to the intended semantic diff before the write.

## Learning / prevention

Primary existing owners:

```text
docs/protocols/coding.md CODE-10
docs/protocols/repository_mutation.md RM-01 / RM-03 / RM-06B
docs/protocols/rule_working_set.md RWS-05A
```

Learning status: `KNOWN_AND_GATE_BYPASSED`.

The immediate prevention action is not a new semantic rule. Keep migrations narrow, compare unrelated classifier/interface text against the pre-write state, and use the staged validation queue only when descendant cuts remain causally reversible. Post-write read-back remains mandatory and is what contained this incident.
