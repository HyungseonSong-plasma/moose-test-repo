# Repeated-Failure Review Gate

## Purpose

Prevent blind edit-run-edit loops on governed Physics/MOOSE work while avoiding excessive review latency. Repeated failures trigger one independent review checkpoint; routine follow-up fixes should not repeatedly re-enter CodeRabbit review.

## Trigger

For one bounded issue/claim and one implementation branch, enter the review gate after **2 consecutive failed governed runs** unless the second failure is byte-for-byte identical to a previously understood external infrastructure outage.

A failure counts when the governed workflow reaches the branch-specific validation path and concludes failure, including harness/construction, staging, MOOSE input, build, runtime, solver, or scientific-gate failures.

## Gate protocol

1. Stop implementation changes after the second consecutive failure.
2. Preserve exact-head workflow logs and artifacts for both failures.
3. Classify each failure as one of: `HARNESS`, `STAGING`, `BUILD`, `MOOSE_INPUT`, `RUNTIME`, `SOLVER`, `SCIENTIFIC`, `INFRASTRUCTURE`.
4. Create one CodeRabbit review PR against a `coderabbit_<issue>_<topic>` review base branch cut from the last accepted/predecessor head.
5. Ask that review to inspect the entire branch diff, both failure modes, hidden assumptions, ownership/staging semantics, and missing regression/contract checks.
6. Do not start the next governed run until the review findings are read and each finding is either fixed or explicitly dispositioned.
7. After review-driven changes, reset the consecutive-failure counter only after one governed run passes the validation category that previously failed. For `INFRASTRUCTURE`, reset it only after the outage is resolved and the affected validation path passes.

## Review economy

CodeRabbit is an escalation tool, not a per-commit gate.

- One review is sufficient for one repeated-failure cluster.
- Do **not** require an incremental CodeRabbit review merely because the reviewed findings were fixed.
- After a completed review, apply the bounded fixes and run the next governed discriminator directly.
- Re-enter CodeRabbit only if the next governed run fails again in the same bounded task and either:
  - the failure is in a new validation category;
  - the fix requires a materially different architecture or ownership/staging contract; or
  - the failure cause remains ambiguous after local log/artifact analysis.
- Minor documentation, evidence-format, or narrowly mechanical fixes do not by themselves trigger another Rabbit review.
- Scientific acceptance still requires the registered physics evidence; Rabbit review never substitutes for it.

## Scope

This is an engineering-process gate, not a scientific acceptance gate. A CodeRabbit approval does not promote physics, timesteps, solver profiles, mesh adequacy, or production status.

## Current application

Issue #236 M1-A entered this gate after:

- run 34987695897: `HARNESS` failure before build because evidence Python dependencies were absent;
- run 34988150016: `STAGING` failure after self-test and successful Physics build because the staged child input referenced electron-impact rate tables and heavy-chemistry files that were not copied into the MultiApp case directory.

PR #237 completed the one review required for this failure cluster. Its findings may now be fixed without another incremental Rabbit review; the next allowed action is the third governed M1-A run after those fixes are applied.
