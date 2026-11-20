# CI Retention Audit v0.2 — live checks vs historical evidence

Issue: #752. PR implementation is intentionally restricted to CI ownership,
execution frequency and dedicated audit controls; Physics source and P3/P4
scientific authorization are unchanged.

## Execution ownership

| Scope | Previous behavior | Current behavior |
|---|---|---|
| Repository Integration Contract | Required, single core validate | Unchanged |
| Physics Code Validation | Full pytest and source guards | Remains automatic |
| Wave1-E merged CI and ZIP receipt | Every code PR | Manual `Physics Legacy Audit` |
| Issue402 S6 417/941 historical reference receipt | Every code PR | Manual `Physics Legacy Audit` |
| Issue402 legacy-symbol inventory | Every code PR | Manual `Physics Legacy Audit` |
| Issue402 JSON-rate / ideal-gas / CORE four / reaction-material P0 | Four extra CI jobs repeating many tests | Manual exact-source reproduction; live invariants consolidated into Physics Code Validation |
| Group A and ARCH replay release/authorization controls | Automatic | Remain automatic until separately approved impact/authority review |
| Physics Native P1/P2 and Boltzmann C++ | Automatic for native-relevant PR | Unchanged |

Invoke `Physics Legacy Audit` via GitHub Actions, select exactly one
`audit` choice and specify the branch/ref to audit. The moved job uses the
chosen ref's exact `github.sha` and retains its original commands, source
checks, historical mutation tests, artifact policy, and evidence output.
This workflow has **no** push/PR triggers and cannot issue a scientific PASS.

The automatic `physics_code_validate` still runs `python -m pytest -q`
for all `tests/` except the five FDEG suites executed separately. The
old Issue402 P0 jobs each repeated test paths covered by this collection.
Their non-pytest source invariants are represented by the
`Verify current-source P0 invariants formerly duplicated in Issue jobs`
step, which checks Stage5 reaction ownership, JSON-rate negative controls,
energy projection and initial-composition legacy absence. Existing electron
impact and energy implementation guards remain separate active steps.

## Guarantees

- No deliberate test source deletion or modification.
- Historical ledger data and immutable receipt identities remain historical.
- The current source checker cannot be bypassed by an absent historical
  artifact. Historical receipt checks are still available on demand.
- Job and step ownership is checked by `repository_ci_scope.py`, including
  negative tests for accidental automatic audit execution, missing selector
  and deletion of a retained active Physics invariant.
- `workflow_surface_guard.py` requires the new audit workflow to be manual.
- No P3/P4 run or science acceptance is authorized.

## Gradual migration to code-derived contracts (proposal)

`repository_ci_scope_v1.json` is a transitional **static inventory**, not
a permanent architectural authority. It duplicates job and step names, and
must change whenever CI structure changes.

A follow-up should introduce providers attached to the verification code:

```python
@dataclass(frozen=True)
class ContractProvider:
    capability: str
    source_selectors: tuple[str, ...]
    required_evidence: tuple[str, ...]
    verifier: Callable[..., Verification]
    scope: str
    version: int
```

The Harness can discover these providers, compute changed source/consumers,
derive per-HEAD applicability, execute verifiers and emit a small signed-or-
hashed receipt with `PASS / FAIL / HOLD / N/A`. The receipt must distinguish
a dynamic *coverage discovery* result from a verified semantic compatibility
claim. Discovery gaps, ambiguous ownership and missing evidence fail closed
as `HOLD`.

To prevent unchecked self-declaration, a **minimal fixed safety kernel**
remains independent of providers: exact HEAD, authorized workflow/event
surface, stable source provenance, P3/P4 operator authorization, and the
rule that no known necessary verifier may be skipped. Providers must be
validated with negative controls (deleted implementation, missing provider,
modified dependency graph, wrong SHA, hidden triggering path, and false
positive on scientific equivalence).

Do not remove the static inventory until these negative tests and actual
static-vs-discovered parity have succeeded on exact candidate HEADs. Historical
metadata then becomes immutable evidence, not an always-run CI contract.
