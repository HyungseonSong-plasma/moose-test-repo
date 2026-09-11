# Paul Successor Contract

**Status:** reserved successor; not active  
**Reserved version name:** Paul  
**Predecessor:** Calvin  
**Purpose:** define the conditions and comparison contract for the next materially upgraded MOOSE/Physics operating-system baseline without prematurely declaring that upgrade complete.

## 1. Successor rule

`Paul` is reserved for the first operating-system baseline that materially supersedes Calvin.

Until that promotion occurs:

```text
Current OS = Calvin
Reserved successor = Paul
Paul status = NOT ACTIVE
```

Do not use `Paul` for minor wording cleanup, documentation-only edits, or routine addition of incident evidence. Paul should represent a material operating change that can reasonably be evaluated against Calvin.

## 2. Material-upgrade criteria

At least one material operating change should exist before promotion, for example:

```text
rule-selection / phase-routing architecture materially changed
activation policy materially changed
working-set sizing policy materially changed
incident-prevention loop materially changed
canonical activation-pattern logic materially changed
new measurable control reduces a known Calvin failure mode
```

A model upgrade by itself does not automatically create Paul. Record model-version changes separately so operating-system effects are not conflated with underlying model capability changes.

## 3. Promotion gate

Before Paul becomes current, record:

```text
1. Calvin observation window and data coverage
2. the specific Calvin limitation or hypothesis being addressed
3. Paul architectural/policy delta
4. expected measurable effect
5. compatibility of pre/post metric definitions
6. known confounders: model version, repository changes, workload/complexity mix
7. activation date and working ref
```

Promotion should be explicit. Do not infer Paul activation merely because some live rule changed.

## 4. Calvin -> Paul comparison contract

Compare where measurement coverage permits:

```text
incident rate / bounded work item
known recurrence rate
pre-execution catch rate
gate-bypass rate
gate-defect rate
enforcement coverage
working-set miss rate
false activation rate
missed activation rate
active weighted rule load by phase
error rate versus weighted rule load
WCC / T-WCC / EVR / DBR / RWR / CLR / FBR
```

The primary evaluation question is not whether Paul has more rules. It is whether Paul produces better local decisions and prevention outcomes with equal or lower active context burden and without weakening closure quality.

## 5. Hypothesis template for Paul

When Paul is proposed, create an explicit hypothesis such as:

```text
Compared with Calvin, Paul will reduce <target failure/routing metric>
while keeping <closure-quality guardrail> unchanged or improved,
under comparable workload and measurement coverage.
```

The hypothesis must be specific enough to be rejected by evidence.

## 6. Activation evidence

At Paul activation, create a dated immutable version baseline under:

```text
docs/operating_system/versions/YYYY-MM-DD_paul.md
```

That baseline should contain:

```text
activation date
repository/ref
Calvin comparison window
Paul architectural delta
initial working-set heuristic
changed activation patterns
retained Calvin invariants
retired or modified Calvin assumptions
measurement plan
known confounders
```

Then update `docs/operating_system/README.md` so:

```text
Current version name = Paul
Calvin = historical baseline
```

Do not rewrite `versions/2026-09-01_calvin.md`.

## 7. Decision states

Use these states while developing the successor:

```text
RESERVED
  Paul name is reserved; no successor implementation claim yet.

CANDIDATE
  A material successor design exists and is being evaluated.

SHADOW
  Paul logic is evaluated against Calvin without becoming the current canonical OS where practical.

ACTIVE
  Paul has passed the explicit promotion gate and is the current named OS baseline.

REJECTED
  A proposed Paul design failed its hypothesis or created unacceptable regressions; Calvin remains current and the evidence is retained.
```

Current state at creation of this contract:

```text
Paul = RESERVED
Calvin = ACTIVE
```

## 8. Preservation rule

Version evolution is itself experimental evidence. Preserve failed Paul candidates and rejected hypotheses when they are materially informative; do not retain only successful changes. This allows later operating-system design to distinguish genuine improvement from repeated rediscovery.