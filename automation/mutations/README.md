# Governed repository mutation manifests

Checked-in JSON files in this directory declare deterministic repository mutations executed by the central portable Samuel skill:

`HyungseonSong-plasma/chatgpt-operation@094b0c57ba78494e3ec7f4c9aa24eaf9afc98103`

Use the canonical `Governed refactor entrypoint` with task `repository_mutation` only for independently authorized native operations; do not use it as fallback for Connector-only branch/file/PR/comment creation. The consumer policy is `.chatgpt-operation.json`.

Portable v1 supports:

- file create / update / delete;
- branch create.

Operations outside portable v1 use the explicitly appropriate Samuel capability/native mutator. For example, PR merge is owned by `GITHUB_PR_MERGE` / `pull-request-merge`, not by this manifest format.

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
