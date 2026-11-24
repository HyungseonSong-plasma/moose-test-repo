# Development Logs

Use this directory for durable **moose-test-repo** development records that are broader than a single failure incident. The active GitHub issue/body is the canonical current work state; do not duplicate its progress as a persistent validation queue.

Keep live specifications and unique acceptance/provenance records. A completed temporary plan or queue can be removed when the final issue disposition supersedes it and no retained consumer needs it. Check references and machine-consumed contracts before deleting, rather than using age or issue closure alone. Do not rewrite historical observations to imply current execution or new scientific acceptance.

Recommended filename:

```text
YYYY-MM-DD_<topic>.md
```

Recommended contents:

```text
Goal
Known-good baseline
Changes attempted
Observed output
Decision
Next gate
Relevant test paths
Executable/build identifier
```

Failure investigations with hypothesis/elimination history belong in `docs/incidents/`. Reusable, closed lessons belong in `docs/knowledge/`.
