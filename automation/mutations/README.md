# Governed repository mutation manifests

Checked-in JSON files in this directory declare deterministic repository mutations executed by:

```bash
python3 skills/repository/mutation.py --manifest <manifest>
```

Use the canonical `Governed refactor entrypoint` with task `repository_mutation`.

Rules:

- one manifest declares one resource/action/target;
- bind the exact repository;
- use fresh blob identity immediately before file update/delete manifests;
- file and branch creation require `expected.absent=true`;
- branch move/delete and issue/PR mutation are not accepted by the v1 schema;
- never use a mutation manifest as a connectivity probe;
- do not place secrets or tokens in a manifest;
- mutation results are workflow artifacts, not scientific evidence.

The schema is closed-world and validated by `skills/repository/mutation.py`.
