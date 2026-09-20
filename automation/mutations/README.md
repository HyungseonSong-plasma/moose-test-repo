# Governed repository mutation manifests

Checked-in JSON files in this directory declare deterministic repository mutations executed by the central portable skill:

`HyungseonSong-plasma/chatgpt-operation@908d5b695b4640727b3c45d8044763c5fcca1d08`

Use the canonical `Governed refactor entrypoint` with task `repository_mutation`. The consumer policy is `.chatgpt-operation.json`.

Portable v1 supports:

- file create / update / delete;
- branch create.

Branch move/delete and issue/PR mutation remain outside portable v1 and continue to use the canonical repository-mutation protocol plus an explicitly safe mutator.

Rules:

- one manifest declares one resource/action/target;
- bind the exact repository;
- file update/delete requires a fresh blob SHA;
- file and branch creation require `expected.absent=true`;
- target paths/branch names must be authorized by `.chatgpt-operation.json`;
- never use a mutation manifest as a connectivity probe;
- do not place secrets or tokens in a manifest;
- mutation results are workflow artifacts, not scientific evidence.

The central skill is pinned by exact commit SHA in `.github/workflows/refactor.yml`; do not vendor a local copy.
