# Connector-first GitHub operation routing

**Status:** PROPOSED — owner review and operating-contract reconciliation required.
**Scope:** GitHub operations for this consumer's Supervisor and scheduled Controllers.

## Problem

The consumer pins Samuel at `9b335e3fbb9c5e8e323e382daeec56fa25336822`.
Its capability registry lists PR merge, branch deletion and workflow dispatch,
but does not list branch creation, file creation/update, PR creation or comments.
The live GitHub Connector exposes those ordinary operations. A missing registry
entry is not evidence that the Connector lacks the operation.

The central main observed at `972d3151527adb944f09f123a184cf791292ff36`
has already added several of these entries. Updating the pin alone would not
solve the architectural coupling to a fixed provider inventory.

## Proposed division of authority

- The live Connector action schema and actual response establish tool availability
  and provider-local results. Discover it on each relevant invocation.
- The owner-approved task scope, current repository policy, exact target identity,
  and GitHub permissions establish whether a write may be attempted.
- Samuel continues to provide its operating, safety and specialized action
  contracts. Its fixed registry is not a universal Connector action allowlist.
- For ordinary authorized, non-destructive operations (branch/file creation,
  scoped commit/update, draft PR creation and task/checkpoint comments), prefer
  the matching live Connector action. A missing registry entry alone must not
  cause an operation to be classified unavailable.
- Retain existing specialist contracts for merge, deletion, privileged policy
  changes and workflow dispatch. Do not bypass a hard safety, permission,
  repository-policy or upstream provider denial. No force or automatic merge.
- A failed Connector call is evidence about that call, not a global capability
  verdict. Do not assume an alternate route is authorized.

## Minimum execution and readback

1. Discover the live action and validate its schema.
2. Check owner-approved scope, repository, current target identity, policy,
   and relevant permissions. Check for existing equivalent work and conflicts.
3. Invoke the specific Connector action. Capture actual result or error.
4. Read back the target independently. Compare exact head, content, PR state or
   comment identity as appropriate. Never claim success from a plan alone.
5. Persist a checkpoint with evidence and the next obligation.

For a draft PR, use an approved isolated branch, verify the source SHA, add
only scoped changes, verify the new commit, open the draft PR, then verify its
head/base/draft state. The draft is not merge approval.

## Adoption gates

This is a proposal, not a silent override of the existing pinned Samuel
contract. Reconcile central and consumer bootstrap routing language
(`BOOTSTRAP.md`, `WORKSPACE.md`, `PROTOCOL_INDEX.md`, operating-system
binding and regression guard) before treating this as durable default policy.
Do not edit the protected capability registry or change the consumer pin merely
to discover a live Connector action.

Qualify ordinary write operations via a scoped draft and readbacks. Test that
an absent registry entry with an available action does not cause a false
unavailability verdict, and that permission/policy denial, stale identity and
unverified readback still fail closed.

Do not alter controller task scope or activate this policy globally until
adoption is explicit. No automatic merge, deletion or main write is proposed.
