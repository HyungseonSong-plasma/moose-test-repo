# Branch cleanup provenance — round 3

Date: 2026-10-08

Deletion contract:
- target only explicit closed-issue branch families plus obsolete cleanup-operation branches;
- refresh every owning issue state from GitHub and require `closed`;
- preserve all current open-PR heads;
- preserve `issue-306-sequence08-baseline` and `qualified/issue310-gummel-optimized` as historical numerical archives;
- require exact live SHA equality immediately before mutation;
- perform deletion with exact-SHA `--force-with-lease`;
- leave unrelated experiment/matrix/prototype branches for a later review.

Branches before: 90
Candidates: 55
Deleted: 55
Preserved by archive/open-PR gate: 3
Mutation skips: 0
Failures: 0
Branches after: 35
Qualified candidates still present: 0
