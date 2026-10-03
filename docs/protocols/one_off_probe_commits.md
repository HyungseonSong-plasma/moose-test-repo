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

Do **not** create these files with sequential Contents-API commits on an open PR. Each commit emits a separate event and can duplicate CI work.

Use an atomic Git-data mutation instead:

```text
create_blob for each changed/new file
-> create_tree from the current branch tree, including all additions/updates/deletions
-> create_commit once
-> update_ref once
```

## Probe-only trigger isolation

Probe-only changes use these repository paths:

```text
.github/workflows/probe-*.yml
.github/workflows/probe-*.yaml
experiments/**/probes/**
```

Repository CI does not listen to `pull_request:synchronize`. Instead, production updates on the active issue branch are detected by the branch `push` trigger. That push trigger ignores the probe-only paths above.

Therefore a commit containing only probe paths has the expected event surface:

```text
one atomic probe publication
  -> one PR synchronize event
  -> zero Repository CI runs
  -> one intended probe workflow run
```

A commit that mixes any production path with probe paths is **not** probe-only and Repository CI must run.

One-off probe workflows should use the `probe-` filename prefix. Probe-specific inputs/checkers should live under an experiment-local `probes/` directory. This path contract is what makes Repository CI suppression deterministic.

After the one-off probe has produced accepted evidence, remove its temporary workflow in a later cleanup commit. Persistent diagnostics may remain only when they are scientifically reusable; reusable non-one-off diagnostics may be promoted out of `probes/` deliberately.

If several probe files are already prepared, batch them into the same tree/commit rather than publishing partial setup first.
