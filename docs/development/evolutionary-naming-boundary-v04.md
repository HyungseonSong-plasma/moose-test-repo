# Evolutionary Naming Audit v0.4 — independently observed ownership boundary

**Status:** Experimental. Read-only evidence and verification contracts; no
production Rename/Extraction, no repository mutation authorization.

## Why the v0.3 review alone is insufficient

A source-linked line can exist at exactly the claimed Git Blob while its
English interpretation is false. The model can also invent a destination
owner, move only some implementation declarations, or rename a still-valid
responsibility owner. GPT's explanation is evidence for its reasoning, **not an
independent verification** of ownership or semantics.

## v0.4 two independent checks

1. `verify_naming_boundary(case, option, git_provider, bindings)`:
   - Read only the exact source commit and its full tracked Python inventory.
   - Check *every* cited evidence anchor through `verify_naming_evidence_sources`.
   - Bind each case `RESPONSIBILITY` ID to a real **declaration line** and a
     precise path-bound Python AST symbol. Arbitrary in-file source lines don't
     satisfy symbol ownership. Unbound/reused/imaginary ownership gives HOLD or
     REJECTED. Folder/file/class/function scopes are supported for Python.
   - Evaluate actual existing/new extraction destinations from Git, not from
     user/model-provided existence booleans; detect a possible already-duplicated
     owner and symbols claimed to serve incompatible post-split owners.
   - Result: `STRUCTURE_WITNESSED`, `HOLD`, or `REJECTED`.
2. `verify_naming_candidate(..., candidate_revision, ..., placements)`:
   - Require a distinct descendant Git commit; exact tracked files only.
   - Verify all before responsibility-symbol assignments have explicit after
     placements under the proposed residual or extracted owner.
   - Check destination source exists, expected symbols and syntactic signatures
     are present, extracted old symbol is absent, and file/folder renames match
     the proposed name. Remaining source symbols should not silently rename for
     `EXTRACT_KEEP`.
   - Result: `STRUCTURAL_DELTA_VERIFIED`, `HOLD`, or `REJECTED`.

**Neither is a semantic-equivalence proof.** A Python AST method's name or
signature is not its runtime behavior. The behavior of moved code, import order,
module initializers, dynamic references, and consumers outside this exact-source
scope may differ even if both receipts are positive.

## Independent GPT semantic reviewer — contract for the following gate

The proposed execution protocol should use a second, independent reviewer and
**withhold the proposed new name during the first pass**:

- **Pass A: responsibility evidence:** supply exact-current symbols, calls and
  consumers, historical scope and negative ownership boundaries. Ask the reviewer
  what the current and residual owner truly does, which responsibilities belong
  to the extracted owner, and what remains unproven. Existing source names may
  appear as tokens, but the proposed name and recommending GPT's preference
  are not disclosed.
- **Pass B: naming/execution challenge:** reveal original name, proposed name,
  all competitors including KEEP, and the before/after structural receipts.
  Demand positive coverage, negative boundaries, source-backed counterexamples,
  consumer and behavioral-test coverage, and a reason the current name is no
  longer sufficient. No forced winner.
- **Verification receipt:** record independent reviewer identity and source,
  exact before/candidate SHA, assessment + disconfirming observations, explicit
  `UNKNOWN` items, tested runtime/contracts and authenticated verification IDs.
  An unauthenticated plain-text reviewer label or GPT confidence score cannot
  certify the result. On inability to establish independence, return HOLD.

## Real repo negative control

`physics_harness/code/diagnostics/collector.py` declares generic `Collector`
and `run_scan` even while Python/C++/MOOSE parsers are in separate providers.
Tests exercise the exact PR HEAD Git object and preserve the existing general
name under KEEP. Source declarations alone do **not** independently prove that
this name is best, but are evidence against inventing a new `libs/` layer.

## Tests and caveats

P0 includes local multiple-commit Git fixtures and a real exact-HEAD module.
Negative tests cover missing/forged/unanchored responsibility declarations,
worktree tampering, directory scope, existing/new destination collisions,
shared ownership, changed candidate signatures, dropped/misplaced symbols,
non-descendant HEAD, and inappropriate rename. CI on a shallow checkout does
**not** replay historical GitHub commits; local fixture validates exact tree
read behavior. Only the current checkout's blob is tested in the real-repo
integration test.

**Out of scope:** complete dynamic/static cross-language references,
performance/physics behavior, public API compatibility, actual automatic code
edit/merge, historical move identity resolution. These remain independent gates.
