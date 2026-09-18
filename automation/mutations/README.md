# Governed repository mutation manifests

Checked-in JSON files in this directory declare deterministic repository mutations executed by:

```bash
python3 skills/repository/mutation.py --manifest <manifest>
```

Use the canonical `Governed refactor entrypoint` with task `repository_mutation`.

Rules:

- one manifest declares one resource/action/target;
- bind the exact repository;
- use fresh blob/head/`updated_at` identity immediately before committing the manifest;
- file and branch creation require `expected.absent=true`;
- never use a mutation manifest as a connectivity probe;
- do not place secrets or tokens in a manifest;
- mutation results are workflow artifacts, not scientific evidence.

The schema is closed-world and validated by `skills/repository/mutation.py`.
