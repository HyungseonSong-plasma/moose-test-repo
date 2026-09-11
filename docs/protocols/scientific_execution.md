# Scientific Execution Integrity Protocol

**Status:** canonical procedure  
**Scope:** executable scientific claims whose validity depends on preserving intent across model, numerical, framework, runtime, observation, and decision layers  
**Purpose:** keep detailed scientific-execution semantics out of the always-loaded core while preserving one canonical owner.

This protocol is loaded through `PROTOCOL_INDEX.md` only when an executable scientific claim or runtime-semantic question makes it material.

## SEI-01 — Intent-preserving execution contract

A scientific computation is valid only when the actual execution preserves the scientific intent and regime required by the closure claim. Parser acceptance, executable return code, solver convergence, or output-file existence alone are never sufficient evidence of scientific validity.

Treat every material executable claim as the following chain:

```text
CLAIM
  -> MODEL
  -> NUMERICAL REGIME
  -> FRAMEWORK-EFFECTIVE CONFIGURATION
  -> RUNTIME REGIME / TRAJECTORY
  -> OBSERVATION / EVIDENCE
  -> DECISION
```

Semantics:

```text
CLAIM
  what the run is intended to establish

MODEL
  retained physics, reduced/averaged physics, validity assumptions, and domain/interface contract

NUMERICAL REGIME
  discretization, timestep/cadence, coupling, solver, and scale-resolution intent

FRAMEWORK-EFFECTIVE CONFIGURATION
  what Physics/MOOSE actually executes after defaults, overrides, adaptivity, synchronization, and ownership rules

RUNTIME REGIME / TRAJECTORY
  the regime actually traversed during execution, including material state-dependent scale changes

OBSERVATION / EVIDENCE
  whether recorded outputs observe the intended state, time, branch, quantity, and invariant

DECISION
  the scientific claim accepted, rejected, held, or re-routed from that evidence
```

## SEI-02 — Semantic object versus representation

Across every material link, distinguish the semantic object from its representation and declare identity, ownership, and provenance when those affect meaning.

Examples of representations include:

```text
names and symbols
source-code spellings
serialized floating-point values
aggregate statistics
output rows
host constants
proxy diagnostics
```

Representations are not interchangeable merely because they look related or are numerically close.

## SEI-03 — Equivalence relation must match the claim

The validation equivalence relation must be:

```text
no stronger than the producing representation guarantees
AND
no weaker than the scientific claim requires
```

Classify the intended relation when material, for example:

```text
syntax / byte exact
identifier / enum exact
discrete mathematical exact
representation-equivalent numeric
numerical tolerance
convergence / refinement equivalence
physical-model tolerance
```

Exact equality is valid only when exact identity is both guaranteed by the representation and required by the claim.

A representation-only mismatch, wrong aggregation operator, wrong state/time identity, source-vs-host convention mismatch, or proxy/direct-evidence substitution remains a validation/contract problem until evidence proves a physics defect.

Detailed comparison and checker behavior is owned by `docs/protocols/validation.md`, especially VAL-16 and related temporal/observation rules.

## SEI-04 — No silent downstream contradiction

No downstream layer may silently contradict an upstream layer.

A PASS is allowed only when the evidence required for the claim demonstrates conformance across every material link that affects the decision.

If a material link is:

```text
unobserved
internally contradictory
outside the declared regime
silently changed into an unvalidated regime
compared using an unjustified equivalence relation
```

fail closed as the appropriate `HOLD`, construction/runtime-semantic class, `VALIDATOR_SELFTEST_FAIL`, or new incident rather than allowing a physics PASS.

## SEI-05 — Future-facing failure handling

Do not attempt to enumerate every possible framework or multiphysics failure in this protocol.

Instead:

```text
define the claim/model/regime explicitly
derive or introspect effective execution controls
preserve semantic identity across representations
monitor material runtime invariants that can change the regime
require evidence that the intended contract actually ran
```

When a new failure appears, route its broken link through the existing owners before creating another rule.

## SEI-06 — Delegated owners

This protocol defines the cross-layer integrity contract but delegates specialized decisions:

```text
model/scale/coupling meaning and regime boundaries
  -> docs/protocols/problem_solving.md

semantic equivalence, numerical/framework preflight,
runtime-semantic conformance, evidence sufficiency
  -> docs/protocols/validation.md

incident novelty, recurrence, prevention maturity,
enforcement promotion
  -> docs/protocols/metrics_closure.md
```

Do not duplicate those procedures here.

## SEI-07 — Recovery constraint

Automatic recovery is permitted only when it is a predeclared, semantics-preserving derived correction.

A model/regime transition or unknown contract violation that can change scientific meaning requires explicit validation or re-routing rather than silent automatic repair.

## SEI-08 — Load/unload rule

Load this protocol when:

```text
an executable scientific PASS/FAIL/HOLD claim is being made
numerical/runtime controls can change the scientific regime
framework-effective configuration may differ from written input intent
observation timing/state/identity can change the conclusion
an incident crosses model -> numerical -> runtime -> evidence boundaries
```

Unload it when the cross-layer integrity obligations are resolved and the current phase no longer contains an executable scientific claim.

The adaptive loading policy is owned by `docs/protocols/rule_working_set.md`.

## Legacy mapping

The long-form ontology previously embedded in `OPERATING_CORE.md` / `CORE-16` is now owned here. `CORE-16` remains a concise always-active invariant that routes to this protocol when the detailed contract is material.
