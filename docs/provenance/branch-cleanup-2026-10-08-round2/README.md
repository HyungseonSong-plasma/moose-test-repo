# Branch cleanup provenance — round 2

Date: 2026-10-08

Deletion contract:
- preserve `main`;
- preserve the pre-Maxwell transport archive and active architecture branches;
- preserve every current open-PR head;
- delete only branches whose recorded tip is an ancestor of the current `main`;
- require exact live SHA equality immediately before mutation;
- perform deletion with `--force-with-lease=<ref>:<expected_sha>`;
- leave squash/non-ancestor or unique-history branches for later manual review.

Main SHA: `386a0aec1223b54ac02bf39e0a39d2eef5d221ab`

Branches before: 103
Explicit/open-PR preserved: 5
Ancestry-qualified candidates: 14
Deleted: 14
Mutation skips: 0
Failures: 0
Branches after: 89
Qualified candidates still present: 0
