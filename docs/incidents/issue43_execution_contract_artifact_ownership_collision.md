# Incident: Issue43 execution-contract artifact ownership collision

**Incident ID:** `INC-ISSUE43-ARTIFACT-OWNERSHIP-001`  
**Date:** 2026-08-29  
**Status:** FIXED / USER-LOCAL SELF-TEST PENDING  
**Associated work:** Issue #43 `QVT multiphysics space-time scale and coupling architecture audit`  
**Failure class:** `HARNESS_OR_CONSTRUCTION_FAIL`; no E300 physics execution occurred

## Symptom

The CORE-16-aware fast-plasma batch reproduced the historical known-good control through P3:

```text
ISSUE43_FAST_CASE_END: Issue43_KGE_qvt_prepoisson P3 rc=0
```

but failed before the E300 QPX case could start:

```text
FileExistsError: [Errno 17] File exists:
.../measurements/Issue43_FAST2_electron_300K
```

The traceback ended in the legacy runtime runner at:

```python
result_root = out_root / case_id
result_root.mkdir(parents=True)
```

## Root cause

The ontology integration introduced a second writer for the same filesystem resource.

Before invoking the legacy case runner, the v3 execution-contract layer wrote P1 contract artifacts into:

```text
measurements/<case_id>/
```

The existing v1 runtime runner already owns that exact path as the per-case runtime-result directory and intentionally creates it as a new directory.

The resulting ownership graph was invalid:

```text
(measurements/<case_id>) -> ontology artifact writer
(measurements/<case_id>) -> legacy runtime result writer
```

This is structurally analogous to the earlier duplicate shared-functor/provider incident: presence is not enough; a mutable resource needs an unambiguous owner.

## Scientific interpretation

- KGE P3 `rc=0` remains valid environment/control evidence for that completed case.
- E300 did not reach P2/P3 under this traceback.
- No electron-300K, Poisson, feedback, timestep-stiffness, Jacobian, scaling, or plasma-physics conclusion is justified from this failure.
- The failure is entirely in harness artifact composition.

## Fix

The v4 integration now isolates ontology artifacts under:

```text
measurements/execution_contracts/<case_id>/
```

while retaining:

```text
measurements/<case_id>/
```

as the sole legacy runtime-runner-owned namespace.

The v4 self-test now includes an ownership regression that:

1. writes a synthetic execution-contract artifact;
2. requires `measurements/execution_contracts/<case_id>` to be created;
3. requires `measurements/<case_id>` to remain absent;
4. verifies the returned contract path remains inside the isolated namespace.

## Ontology mapping

This incident does **not** require a new top-level ontology axis. It maps to CORE-16 semantic identity/ownership:

```text
semantic resource = per-case measurement artifact namespace
owner              = runtime runner or ontology writer
representation     = filesystem path
required invariant = one intended owner per mutable path namespace
```

Reusable abstraction:

```text
(resource identity, scope) -> intended owner
```

The same principle applies to:

- material/functor providers by block;
- output/checker artifact paths;
- cache/work directories;
- generated input fragments;
- MultiApp transfer targets;
- repository mutation targets.

A composition layer must add a new namespace or explicitly delegate ownership; it must not pre-create a resource owned by the downstream executor merely because both layers need related artifacts.

## Promotion condition

After the user-local `fast-relaxation --self-test` passes with the ownership regression, this incident is eligible for promotion into reusable troubleshooting knowledge. A subsequent QPX run is separate physics evidence and is not required to prove the filesystem ownership self-test itself.
