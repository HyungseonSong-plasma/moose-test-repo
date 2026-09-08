# Milestone Delivery Protocol

**Status:** canonical procedure  
**Scope:** project-to-milestone-to-issue work decomposition, delivery sequencing, integration validation, and milestone closure  
**Purpose:** scale the productivity gains of issue-level work batching to capability-level delivery without sacrificing rollback locality or validation discipline.

## MD-01 — Delivery hierarchy

Use the following hierarchy for non-trivial development programs:

```text
Project / Architecture Goal
  -> Milestone
    -> Issue
      -> Work Batch
        -> Atomic Mutation / Validation Unit
```

The levels have different responsibilities:

```text
Project    = strategic objective
Milestone  = usable capability delivery boundary
Issue      = semantic implementation and rollback boundary
Work Batch = execution-efficiency boundary
Mutation   = repository safety boundary
```

Do not collapse these levels merely because one level currently contains only one child.

## MD-02 — Milestone capability statement

Every milestone must have one explicit capability statement of the form:

```text
When this milestone is complete, the system can <new usable capability>.
```

The statement is the scope-control invariant for the milestone. A proposed issue belongs in the milestone only when its closure is materially required to establish that capability or its acceptance evidence.

Milestones are not labels, buckets, or collections of loosely related issues.

## MD-03 — Milestone M0

Before implementation begins, perform milestone-level M0 planning:

1. define the capability statement;
2. record the current architecture/state relevant to that capability;
3. define the intended end-state architecture;
4. decompose the work into bounded issues;
5. build the inter-issue dependency DAG;
6. establish the initial issue execution order;
7. identify cross-issue integration risks;
8. define milestone acceptance criteria and closure evidence.

M0 planning freezes the initial delivery graph, not every future implementation detail. If new evidence invalidates the DAG, update the plan explicitly rather than forcing the original order.

## MD-04 — Issue queue and state model

A milestone owns a delivery queue of issues. The normal issue states are:

```text
READY
BLOCKED
ACTIVE
PASS
REOPEN_REQUIRED
```

Use dependency-aware FIFO execution by default:

```text
ready predecessor
-> issue work batches
-> issue validation
-> issue closure
-> next ready issue
```

A blocked or invalidated dependency is a reason to stop or reroute the queue, not a reason to continue downstream work speculatively.

## MD-05 — Issue independence

Every issue remains an independent semantic delivery and rollback boundary even when several issues belong to one milestone.

Milestone batching must not turn several issues into one atomic rewrite. A failed later issue does not invalidate an earlier closed/PASS issue unless contradictory evidence proves that the earlier acceptance contract was wrong.

Preserve issue-level:

- explicit objective and acceptance contract;
- bounded work batches;
- local validation evidence;
- rollback locality;
- closure state.

## MD-06 — Work batching inside issues

Within each issue, group causally related implementation steps into work batches large enough to reduce repeated context loading and validation overhead while preserving recoverability.

Preferred shape:

```text
Issue M0
-> batch A
-> batch B
-> ...
-> issue final guard
-> consolidated issue validation
-> issue closure
```

Do not validate after every small edit when a larger causally recoverable batch can be validated once. Do not enlarge a batch past the point where failure localization or rollback ownership becomes ambiguous.

## MD-07 — Validation hierarchy

Issue validation and milestone validation serve different purposes.

### Issue validation

Owns local semantic correctness:

- issue-specific structural/behavioral guards;
- import/interface compatibility;
- targeted self-tests;
- issue-specific runtime evidence when explicitly authorized;
- issue acceptance markers.

### Milestone validation

Owns cross-issue integration:

- dependency-direction and architecture invariants;
- cross-issue interface compatibility;
- integration guard(s);
- full regression or harness safety net appropriate to the milestone;
- capability-statement acceptance.

Do not mechanically rerun every issue-local diagnostic at milestone closure when accepted issue evidence remains current. Reuse closed/PASS issue evidence and add only the integration evidence needed for the milestone claim, plus the declared regression safety net.

## MD-08 — Milestone integration guard

After all required milestone issues are PASS, run a milestone integration phase before closure:

```text
all required issues PASS
-> milestone integration guard
-> consolidated milestone validation
-> capability acceptance
-> milestone closure
```

The integration guard must check invariants that no single issue can prove alone.

Examples:

- no forbidden cross-layer dependencies;
- all newly introduced capability surfaces compose correctly;
- compatibility facades resolve to intended owners;
- command/registry/spec surfaces remain internally consistent;
- no accepted issue left stale current-state references in another issue or canonical document.

## MD-09 — Milestone Definition of Done

A milestone may close PASS only when:

1. every required issue is CLOSED/PASS;
2. no unresolved BLOCKED issue remains inside the declared capability scope;
3. milestone integration guard passes;
4. declared architecture invariants pass;
5. the milestone regression safety net passes;
6. current architecture/operating documentation is synchronized where material;
7. deferred work is explicitly transferred to a follow-up issue, debt record, or next milestone;
8. evidence budgets and scientific/runtime constraints are respected;
9. the capability statement is demonstrably true.

Unrecorded "do later" work is not an acceptable closure state.

## MD-10 — Milestone size and splitting

Prefer milestones small enough to preserve one coherent capability and manageable dependency graph.

Guideline:

```text
3-7 issues  -> preferred
2-10 issues -> normally acceptable
>10 issues  -> require explicit split review
```

This is a heuristic, not a hard numerical gate. Causal recoverability and capability coherence are authoritative.

## MD-11 — DAG-aware batching

Issue order is not purely chronological. Model explicit dependencies and exploit independent branches where useful.

Example:

```text
        schema foundation
              |
          compiler
          /      \
     pilot A    extraction B
          \      /
           integration
```

Parallelizable branches may be developed independently, but their accepted outputs must meet again at milestone integration before the milestone closes.

## MD-12 — Current-state ownership

GitHub issue bodies own current issue state. GitHub milestones own milestone membership/status metadata when used. Canonical operating procedures own reusable semantics.

Do not copy full milestone procedure text into every issue. Issue bodies should reference this protocol and record only milestone-specific capability, dependency, acceptance, and current-state information.

Historical comments remain evidence, not current STATE.

## MD-13 — Repository mutation isolation remains authoritative

Milestone batching changes planning and validation boundaries only. It does not relax repository mutation safety.

All actual writes remain subject to `docs/protocols/repository_mutation.md`, including resource-class isolation, fresh-read-before-write, one-shot mutation envelopes, and post-write read-only verification.

## MD-14 — Scientific/runtime evidence isolation

A milestone may contain architecture, harness, scientific, and diagnostic issues, but accepted evidence scopes must not be silently mixed.

Architecture/refactor issues must not consume new scientific EVR/P3 evidence merely to prove code organization unless explicitly authorized. Scientific claims continue to use their own validation and evidence contracts.

## MD-15 — Milestone closure output

Milestone closure should summarize, without duplicating issue details:

```text
capability statement
required issues and final states
integration guard result
milestone regression result
deferred/follow-up work
scientific/runtime evidence budget impact
final classification: CLOSED / PASS | HOLD | BLOCKED
```

The milestone closure record is an integration-level decision, not a replacement for issue-level evidence.
