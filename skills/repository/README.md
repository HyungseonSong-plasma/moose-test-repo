# Repository mutation skill

`skills/repository/mutation.py` owns deterministic repository-mutation safety mechanics.

## Responsibility

```text
declared intent
  -> exact repository/resource/action binding
  -> active/queued CI lock check
  -> fresh target read
  -> expected identity gate
  -> semantic no-op gate
  -> exact mutation
  -> read-back verification
  -> PASS | NO_MUTATION_NEEDED | HARD_STOP
```

The caller still decides **what semantic change is intended**. The skill decides whether that declared mutation can be executed mechanically and safely.

## Supported MVP resources

| Resource | Actions | Required fresh identity |
|---|---|---|
| file | create / update / delete | `absent=true` or exact blob SHA |
| branch | create | `absent=true` plus desired commit SHA |

Branch move/delete and issue/PR mutation are intentionally unsupported in the local v1 because GitHub's corresponding write APIs do not provide the server-side expected-old-state precondition required by this skill's exact-identity claim.

File content is UTF-8 text in the MVP.

## Manifest

Example file update:

```json
{
  "schema_version": 1,
  "repository": "HyungseonSong-plasma/moose-test-repo",
  "resource": "file",
  "action": "update",
  "target": {
    "path": "docs/example.md",
    "branch": "issue-123-example"
  },
  "expected": {
    "sha": "0123456789abcdef0123456789abcdef01234567"
  },
  "desired": {
    "content": "replacement content\n"
  },
  "commit_message": "Issue #123: update example"
}
```

Mutation manifests used by governed automation belong under `automation/mutations/`.

## Self-test

```bash
python3 skills/repository/mutation.py --self-test
```

The self-test uses an in-memory fake transport and performs no network mutation. It covers positive mutation, retry-safe no-op suppression, stale identity, the Actions validation gate, unsupported branch/issue actions, and read-back mismatch.

## Governed execution

The canonical refactor workflow exposes task `repository_mutation`. It executes a checked-in manifest using the workflow-scoped GitHub token and writes a structured result artifact.

The skill exempts only its own `GITHUB_RUN_ID` from the preflight Actions validation gate. Any other queued or in-progress Actions run causes `HARD_STOP`. This is a point-in-time validation gate, not a repository lease; supported v1 mutations remain safe through server-side identity/uniqueness semantics rather than assuming the gate reserves the repository.

## Boundary

For its supported v1 surface, this skill mechanizes RM-01 through RM-05, the branch-create subset of RM-11, the preflight gate portion of RM-12, and mechanical completion checks of RM-16.

It does **not** decide scientific meaning, whether a mutation should exist, HARD STOP/SOFT CONTROL interpretation beyond its mechanical contract, dependency fan-out, or incident severity.
