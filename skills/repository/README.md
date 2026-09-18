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
| branch | create / move / delete | `absent=true` or exact head SHA |
| issue | update / close / reopen | exact `updated_at` |

Branch `move` is fast-forward only; `force=true` is not exposed.

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

The self-test uses an in-memory fake transport and performs no network mutation. It covers positive mutation, no-op suppression, stale identity, CI lock, invalid resource/action binding, non-fast-forward rejection, and read-back mismatch.

## Governed execution

The canonical refactor workflow exposes task `repository_mutation`. It executes a checked-in manifest using the workflow-scoped GitHub token and writes a structured result artifact.

The skill exempts only its own `GITHUB_RUN_ID` from the mutation lock. Any other queued or in-progress Actions run causes `HARD_STOP`.

## Boundary

This skill mechanizes RM-01 through RM-05, RM-11, the lock portion of RM-12, and the mechanical completion checks of RM-16.

It does **not** decide scientific meaning, whether a mutation should exist, HARD STOP/SOFT CONTROL interpretation beyond its mechanical contract, dependency fan-out, or incident severity.
