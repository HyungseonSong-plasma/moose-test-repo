# Repeated-Failure Review Gate

## Purpose

Prevent blind edit-run-edit loops on governed Physics/MOOSE work. Repeated failures must trigger an independent code review before another implementation attempt.

## Trigger

For one bounded issue/claim and one implementation branch, enter the review gate after **2 consecutive failed governed runs** unless the second failure is byte-for-byte identical to a previously understood external infrastructure outage.

A failure counts when the governed workflow reaches the branch-specific validation path and concludes failure, including harness/construction, staging, MOOSE input, build, runtime, solver, or scientific-gate failures.

## Gate protocol

1. Stop implementation changes after the second consecutive failure.
2. Preserve exact-head workflow logs and artifacts for both failures.
3. Classify each failure as one of: `HARNESS`, `STAGING`, `BUILD`, `MOOSE_INPUT`, `RUNTIME`, `SOLVER`, `SCIENTIFIC`, `INFRASTRUCTURE`.
4. Create a CodeRabbit review PR against a `coderabbit_<issue>_<topic>` review base branch cut from the last accepted/predecessor head.
5. Ask the review to inspect the entire branch diff, both failure modes, hidden assumptions, ownership/staging semantics, and missing regression/contract checks.
6. Do not start a third governed run until review findings are read and either fixed or explicitly dispositioned.
7. After review-driven changes, reset the consecutive-failure counter only after one governed run passes the construction/runtime layer that previously failed.

## Scope

This is an engineering-process gate, not a scientific acceptance gate. A CodeRabbit approval does not promote physics, timesteps, solver profiles, mesh adequacy, or production status.

## Current application

Issue #236 M1-A entered this gate after:

- run 34987695897: `HARNESS` failure before build because evidence Python dependencies were absent;
- run 34988150016: `STAGING` failure after self-test and successful Physics build because the staged child input referenced electron-impact rate tables and heavy-chemistry files that were not copied into the MultiApp case directory.

The next #236 implementation attempt must consume the CodeRabbit review before another governed run.
