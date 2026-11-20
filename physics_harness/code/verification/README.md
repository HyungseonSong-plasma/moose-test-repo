# Verification v0.1 — facts before policy

Verification is the third stage after Diagnostics and Analysis. It has no
directory-role policy, package allowlist, or automatic mutation approval.

The implementation has two explicit responsibilities:

- `consistency.py` validates scoped Graph/EvidenceReceipt source-metadata consistency.
- `post_change.py` derives follow-up verification obligations from GraphDiff.

Both functions remain available from `physics_harness.code.verification`.

- Every Diagnostics assembly emits a VerificationReceipt alongside Graph and
  EvidenceReceipt. VERIFIED attests consistency of scoped source provenance:
  SHA/Blob/line references, Scope and file status. The result explicitly
  retains unverified runtime, semantic equivalence and global consumer closure.
- Failed integrity findings are FAILED. Partial scans or unresolved dynamic
  source facts are UNVERIFIED, not green. A source-only VERIFIED result never
  approves removing code or altering production CI.
- plan_change_verification compares two exact-HEAD Graph/Receipt pairs and
  derives checks for removed references, changed interfaces, new dependency
  candidates, Scope gaps and required test replay. It is not a policy migration.
- Explicit runtime/semantic evidence from separately executed verification is
  required to close those obligations in a later version.

Deprecated repository-specific directory-role Guards are retired separately
only after consumers and Workflow registrations are audited. Historical static
adversarial cases remain as risk examples, not hard-coded role rules.

## First retired Guard (issue #743)

The historical static `physics_directory_role_guard.py` and its
`physics_directory_roles_v1.json` role allowlist are retired. The generalized
Verifier works on Graph source Evidence and actual before/after changes.
Its dependency/call candidates produce verification obligations rather than
blocking unfamiliar directories. Other repository checks remain independent
and are not implicitly declared replaced by Verification v0.1.
