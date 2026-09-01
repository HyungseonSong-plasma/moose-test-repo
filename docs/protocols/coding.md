# Coding and Harness Implementation Protocol

**Status:** canonical procedure  
**Scope:** repository code, harness, runner, entrypoint, checker, and test implementation  
**Purpose:** keep implementation reusable, structurally consistent, validation-aware, and accessible through stable entry points.

Load this protocol through `PROTOCOL_INDEX.md` whenever work creates, modifies, reviews, or reorganizes executable repository code, harness logic, CLI behavior, checkers, or test orchestration.

## CODE-01 — Reuse-first implementation

Before creating a new file, command, runner, or helper, search the existing repository for the nearest semantic owner.

Preferred order:

```text
extend existing canonical owner
-> extract a reusable helper only when responsibility is genuinely shared
-> create a new module only when no existing owner can absorb the behavior cleanly
```

A new file is not justified merely because the current change is issue-specific or convenient to isolate temporarily.

## CODE-02 — Stable user entry point

User-facing QPX test and diagnostic execution routes through the canonical executable entrypoint:

```text
python3 bin/qpx.py <command> [args]
```

Command routing/presentation is owned by `qpx_harness/cli/`; `bin/qpx.py` is a thin process launcher only. Do not create an issue-specific top-level executable when an existing `qpx` command and harness module can represent the operation as a mode or subcommand.

Developer/repository utilities that are not product/user commands belong under `tools/` when a standalone utility is genuinely justified. Do not recreate a general `scripts/` dumping ground.

## CODE-03 — File placement ownership

Use repository layers consistently:

```text
bin/qpx.py
  -> thin executable entrypoint only

qpx_harness/cli/
  -> command presentation, routing, output boundary

tools/*.py
  -> developer/repository utilities only when standalone ownership is justified

qpx_harness/
  -> reusable capability packages plus explicit scientific/compatibility policy owners

qpx_harness/execution/
  -> generic process execution, case staging, workspace coordination

qpx_harness/evidence/
  -> generic evidence/provenance/identity mechanics

qpx_harness/diagnostics/
  -> reusable diagnostic fact extraction and invariant analysis

tests/
  -> canonical/diagnostic test inputs, manifests, checkers, and fixtures

docs/
  -> protocols, knowledge, incidents, development evidence; not executable glue
```

Do not duplicate command routing between `bin/` and `qpx_harness/cli/`, or execution/evidence semantics between capability packages and compatibility facades.

## CODE-04 — Extend the current canonical harness before version proliferation

When an active issue already names a canonical harness/module, modify that owner first.

Do not create `vN+1`, `_new`, `_fixed`, or a parallel runner solely to avoid editing the current implementation. A new versioned layer requires a real compatibility, experimental-branch, or migration boundary that the existing owner cannot represent without mixing incompatible contracts.

When historical version layers already exist, new behavior should preferentially converge toward one current canonical path rather than adding another layer.

## CODE-05 — Separate reusable primitives from orchestration

Keep low-level reusable semantics in focused modules and orchestration in the owning harness.

Examples:

```text
MOOSE input editing        -> qpx_harness/moose or input helper
executable/process runtime -> qpx_harness/execution
identity/provenance        -> qpx_harness/evidence
generic solver diagnostics -> qpx_harness/diagnostics
execution-contract logic   -> execution-contract semantic owner
case/branch sequencing     -> owning orchestration capability/policy
CLI dispatch               -> qpx_harness/cli
process entrypoint         -> bin/qpx.py
```

Do not reimplement executable resolution, hashing, logging, input parsing, evidence-directory behavior, or other existing primitives inside a new runner.

## CODE-06 — Validation phases are explicit code paths

Implementation must preserve the canonical `P0 -> P1 -> P2 -> P3` order from `validation.md`.

When a harness exposes partial execution, make the phase boundary explicit, for example:

```text
--self-test       -> P0 only
--preflight       -> P0/P1/P2 only
normal runtime    -> P0/P1/P2/P3 as authorized
```

A P1/P2 command must not accidentally enter physics P3. Record phase ownership in emitted evidence when ambiguity is possible.

## CODE-07 — Self-test new harness semantics

New or changed harness/checker behavior requires a P0 self-test appropriate to the failure class.

When applicable include:

```text
positive control -> PASS
historical/targeted negative mutation -> FAIL/HOLD
construction failure is not physics failure
phase-only mode cannot leak into later phases
semantic/evidence parser rejects incomplete or contradictory evidence
```

Integrate reusable self-tests into the existing harness and, when appropriate, the unified `python3 bin/qpx.py self-test` path rather than adding a separate manual test command.

## CODE-08 — Evidence must be runner-owned

If the same manual inspection, shell probe, temporary Python snippet, grep, or post-run calculation is needed to decide the work item, promote it into the owning harness or reusable utility when practical.

User instructions should prefer one stable repository command over ad-hoc here-docs or temporary scripts.

Generated evidence should preserve enough identity and provenance to interpret the result, reusing existing execution/evidence helpers where available.

## CODE-09 — One command should produce one interpretable result surface

A user-local command should emit concise terminal result markers and write a structured summary/log path when the result needs later diagnosis.

Prefer:

```text
<TEST>_P0: PASS|FAIL|HOLD
<TEST>_P1: PASS|FAIL|HOLD
<TEST>_P2: PASS|FAIL|HOLD
<TEST>_PRECLASS: <class>
<TEST>_LOG: <path>
<TEST>_SUMMARY: <path>
```

Do not require the user to reconstruct the decision by manually combining several unrelated commands when the harness can do so deterministically.

## CODE-10 — Preserve accepted behavior while adding diagnostics

Instrumentation, provenance, logging, introspection, and validation controls must not silently change the physical model, numerical regime, or production mechanism under test.

If implementation changes both behavior and observability, separate those claims and validate them independently under CORE-16 and `validation.md`.

## CODE-11 — User-local execution boundary

Repository code may construct and statically validate QPX work, but real QPX runtime evidence remains user-local under CORE-06.

Do not label repository/static execution as physics PASS. Harness code should make the distinction between static construction, executable preflight, runtime-semantic evidence, and physics decisions machine-visible.

## CODE-12 — Implementation delivery gate

Before asking the user to run a new or changed command, verify the implementation against this checklist:

```text
existing semantic owner searched
new-file necessity justified
stable CLI path preserved
shared utilities reused
P0 self-test present for the changed failure class
P1/P2/P3 boundaries explicit
no temporary/manual procedure remains when it can be harness-owned
result markers and evidence paths are deterministic
validation protocol requirements are satisfied
```

If any material item is unresolved, do not present the command as ready for external execution.

## CODE-13 — Staged validation queue stack

When one issue requires several small, causally ordered implementation cuts, do not require a separate user-local validation round after every low-risk cut. Preserve the validation obligation for each cut in an ordered **validation queue stack**, continue implementation while the dependency chain remains interpretable and reversible, then discharge the queued validations in causal order.

Canonical shape:

```text
M1 -> enqueue V1
M2 -> enqueue V2
M3 -> enqueue V3
...
Mn -> enqueue Vn

issue-level implementation target reached
        ↓
run V1 -> V2 -> V3 -> ... -> Vn
        ↓
final required P0/P1/P2/P3 gates
```

The queue is FIFO for validation and stack-like for rollback. Older validation claims are checked first; if an older claim fails, all later dependent modifications become untrusted descendants.

Each queued validation item must preserve enough state to identify its rollback boundary:

```text
validation id
modification/cut id or commit SHA
changed semantic scope
claim that the validation establishes
validation command / expected marker or invariant
known dependent later cuts
rollback boundary
status = PENDING | PASS | FAIL | DROPPED
```

Failure handling is causal:

```text
V1 FAIL after M1,M2,M3
  -> M2 and M3 are untrusted descendants
  -> discard/rollback M2 and M3 before repairing M1
  -> do not interpret V2 or V3

V2 FAIL after M1,M2,M3 and V1 PASS
  -> M1 remains accepted
  -> discard/rollback M3 before repairing M2
  -> do not interpret V3

Vi PASS
  -> preserve Mi and all previously accepted ancestors
  -> continue with Vi+1
```

"Discard/rollback" means remove the descendant semantic changes before continuing, using the repository mutation protocol appropriate to the already-published Git state. Do not keep later code merely because it happens to compile when an earlier prerequisite validation failed.

Queue depth is bounded by **causal recoverability**, not by an arbitrary number of cuts. Continue stacking modifications until the issue-level implementation target is reached when all of the following remain true:

```text
each cut has a clear validation claim
later cuts have identifiable dependencies on earlier cuts
later cuts can be discarded without losing unrelated accepted work
no later cut masks the failure signal of an earlier validation
no destructive or irreversible boundary has been crossed
```

Run validation immediately instead of deferring it when any of these is true:

```text
a cut deletes or retires a canonical owner
an external/public interface or persisted schema changes
physics/numerical semantics change materially
later work would make the earlier failure non-localizable
rollback would require ambiguous reconstruction
repository structural/ref mutation makes descendant discard unsafe
the validation itself is a required gate before the next cut
```

Lightweight additive helpers, reversible caller rewiring, duplicated plumbing removal, and other causally isolated refactors are normal candidates for queued validation.

The queue reduces the **number of user-local validation rounds**, not the required evidence. Before issue closure or canonical retirement, every non-dropped queued validation must be discharged successfully, and the final validation gates required by `validation.md` still apply.
