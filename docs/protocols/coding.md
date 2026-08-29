# Coding and Harness Implementation Protocol

**Status:** canonical procedure  
**Scope:** repository code, harness, runner, script, checker, and test implementation  
**Purpose:** keep implementation reusable, structurally consistent, validation-aware, and accessible through stable entry points.

Load this protocol through `PROTOCOL_INDEX.md` whenever work creates, modifies, reviews, or reorganizes executable repository code, harness logic, scripts, checkers, or test orchestration.

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

User-facing QPX test and diagnostic execution should route through the unified CLI:

```text
python3 scripts/qpx.py <command> [args]
```

Do not create an issue-specific top-level script when an existing `qpx.py` command and harness module can represent the operation as a mode or subcommand.

A separate script under `scripts/` is justified only when it is a reusable repository-wide utility with a stable standalone contract, such as parser validation or temporal CSV normalization.

## CODE-03 — File placement ownership

Use repository layers consistently:

```text
scripts/qpx.py
  -> thin unified CLI / command routing

scripts/*.py
  -> reusable standalone repository utilities only

qpx_harness/*.py
  -> reusable implementation primitives, orchestration, runners, analyzers,
     execution contracts, evidence handling, and issue-scoped harness logic

tests/
  -> canonical/diagnostic test inputs, manifests, checkers, and fixtures

docs/
  -> protocols, knowledge, incidents, development evidence; not executable glue
```

Do not duplicate orchestration between `scripts/` and `qpx_harness/`.

## CODE-04 — Extend the current canonical harness before version proliferation

When an active issue already names a canonical harness/module, modify that owner first.

Do not create `vN+1`, `_new`, `_fixed`, or a parallel runner solely to avoid editing the current implementation. A new versioned layer requires a real compatibility, experimental-branch, or migration boundary that the existing owner cannot represent without mixing incompatible contracts.

When historical version layers already exist, new behavior should preferentially converge toward one current canonical path rather than adding another layer.

## CODE-05 — Separate reusable primitives from orchestration

Keep low-level reusable semantics in focused modules and orchestration in the owning harness.

Examples:

```text
MOOSE input editing        -> parser/input helper
executable resolution      -> runtime helper
identity/provenance        -> evidence helper
execution-contract logic   -> execution-contract helper
case/branch sequencing     -> owning harness
CLI dispatch               -> scripts/qpx.py
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

Integrate reusable self-tests into the existing harness and, when appropriate, the unified `scripts/qpx.py self-test` path rather than adding a separate manual test command.

## CODE-08 — Evidence must be runner-owned

If the same manual inspection, shell probe, temporary Python snippet, grep, or post-run calculation is needed to decide the work item, promote it into the owning harness or reusable utility when practical.

User instructions should prefer one stable repository command over ad-hoc here-docs or temporary scripts.

Generated evidence should preserve enough identity and provenance to interpret the result, reusing existing runtime/evidence helpers where available.

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
