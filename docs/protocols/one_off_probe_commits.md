# One-off Probe Commit Protocol

**Status:** active local operating rule  
**Scope:** temporary diagnostic inputs, checkers, and GitHub Actions workflows used for bounded scientific probes.

## Atomic publication rule

A one-off probe must be published as **one Git commit** containing every file required to launch the probe, normally:

```text
probe input
+ probe checker / summarizer when needed
+ one-off workflow
+ any small probe-specific metadata
```

Do **not** create these files with sequential Contents-API commits on an open PR. Each commit emits a separate `pull_request:synchronize` event and causes the normal Repository CI to start again.

Use an atomic Git-data mutation instead:

```text
create_blob for each changed/new file
-> create_tree from the current branch tree, including all additions/updates/deletions
-> create_commit once
-> update_ref once
```

Expected event surface:

```text
one probe publication
  -> one PR synchronize
  -> one Repository CI run
  -> one intended probe workflow run
```

After the one-off probe has produced accepted evidence, remove its temporary workflow in a later cleanup commit. Persistent diagnostic inputs may remain when they are scientifically reusable.

If several probe files are already prepared, batch them into the same tree/commit rather than publishing partial setup first.
