# Evolutionary Naming Audit v0.6 — exact-SHA replay and GitHub reviewer authority

**Status:** opt-in test execution and read-only review authentication. No
automatic source Rename/Extraction or independent-semantic PASS.

## Purpose and architecture

The v0.5 source-inspection gates can falsify AST changes but cannot verify an
actual before/after test run. A reviewer’s self-reported GitHub link is also
not authenticated evidence. v0.6 closes those two evidence-collection gaps
without silently converting source or CI results into semantic proof.

### Test replay contract

`run_naming_test_replay(GitSourceProvider(root), before_commit,
after_commit, ("tests/test_contract.py",))` must be invoked **explicitly in a
trusted CI runner**, not automatically on arbitrary GPT candidate source.
The runner:

1. Checks strict 40-character source SHAs, real local Git commits and ancestry.
2. Requires each test module to be a regular tracked file at both revisions
   with the **same exact Git Blob**. All ancestor `conftest.py` and common
   pytest settings are also checked for existence/content drift. If tests or
   fixtures changed, the result is `HOLD` with no execution. This is a
   compatible-contract-test subset only, not an upgraded suite migration.
3. Adds detached Git worktrees outside the caller's source worktree; runs a
   fixed `sys.executable -m pytest -q -p no:cacheprovider --disable-warnings`
   command (no shell, no arbitrary command arguments) with a bounded timeout,
   output hashing, actual JUnit XML generation and reduced environment.
   Removes both worktrees afterward.
4. Requires both suites to pass, at least one test collected and unchanged
   passing case count. Non-zero, timeout, missing test, missing commit or
   changed test source are not accepted. Reports test-created worktree changes.
5. Emits revision, command, interpreter, suite Blob SHAs, exact JUnit XML, stdout/stderr SHA-256,
   exit status and unresolved coverage/isolation/external-consumer claims.

**Important limitations:** Git worktrees are not OS/network sandboxes. Test
code has the runner user's permissions. A matching suite can omit changed
behavior, import dependencies can change while tests remain constant, and
pass count is not a behavioral equivalence proof. `PASS_WITH_GAPS` never
becomes mutation authority. Authenticate CI source/toolchain and add contract
coverage independently. Do not run unreviewed source on a sensitive host.

### Trusted GitHub review record

`naming_review_context_sha256(blind_packet, option, candidate_sha)` constructs
a digest of the exact snapshot and chosen proposal. The reviewer must include
exactly one stand-alone line in the official GitHub review body:

```text
Naming-Audit-Context: <64-character SHA-256 digest>
```

`verify_github_naming_review(...)` reads the official GitHub REST PR twice
and the official review once over TLS, with redirection disabled. It requires
matching PR number/repo, open PR, stable exact candidate HEAD, `APPROVED`
review at the same commit, reviewer not equal PR author, explicit
`authorized_reviewers` allowlist, explicit policy for bot accounts and the
exact context digest. It does **not** accept a user-provided review JSON as
authenticated source. The code can run without a token for publicly readable
PRs or with a caller-supplied token for a private repository; tokens never
appear in the returned receipt.

`AUTHENTICATED_REVIEW_ONLY` identifies the GitHub user and the commit they
approved. It does not prove first-pass review blindness, semantic expertise,
reviewer independence from the original GPT proposer, actual test relevance
or a safe Rename. Those constraints are explicit `unresolved` fields.

## Synthetic independent controls

- Two real fixture Git commits: unchanged executable contract tests pass
  with an API forwarding to an extracted module.
- Deliberate `return 42` regression produces test FAIL and BLOCKED despite
  matching public function signatures.
- Git worktree tampering, missing/deleted/weakened tests, changed `conftest.py`
  or `pytest.ini`, timeouts, non-descendant and same-revision attempts are
  rejected or HOLD.
- Review metadata from a simulated *transport* must be current-head, approved,
  authorized non-author reviewer, exact context and correct base repo; PR
  update during API calls fails closed; fake review/redirect/invalid responses
  cannot produce a trusted account result. Simulated transports in tests are
  not real production reviewer authentication.

## v0.6 exit and remaining gate

`NamingSafetyGateReport.status` remains `HOLD/BLOCKED`, even with a separate
replay receipt or authenticated review record. None of the names/refactor
modules can mutate the Git repository. An external executor must bind actual
reviewer-authenticated semantic decisions and trusted CI run attestations to
the *same* candidate SHA, close external consumers, apply an authorized
transaction and revalidate the post-merge SHA. No such executor is installed.

### Integration with the concurrent v0.6 JUnit comparison gate

The PR also contains a pure, read-only `verification/junit_compare.py` that
checks submitted JUnit digest, testcase identities, failure/skip states and
exact naming candidate revisions. **Do not replace that canonical module**
with executable code. `pytest_revision_runner.py` is a distinct, explicitly
invoked producer of real before/after JUnit artifacts. The helper
`build_executed_replay_artifact_pair` hands those actual XML bytes and SHA-256
digests to the canonical `compare_candidate_replay` or
`evaluate_naming_safety_gates(..., replay_baseline=..., replay_candidate=...)`.
The latter still returns HOLD/BLOCKED because test relevance, authenticated
CI identity, semantics and external consumers are not established by XML.
