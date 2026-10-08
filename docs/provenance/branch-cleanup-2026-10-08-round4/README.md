# Branch cleanup provenance — round 4

Date: 2026-10-08

Deletion contract:
- target only branches with explicit PR provenance;
- require merged=true for accepted historical implementation branches;
- require closed+unmerged for obsolete matrix/draft experiment branches;
- require the PR head ref to exactly equal the target branch;
- preserve every current open-PR head;
- require exact live SHA equality and delete with force-with-lease;
- retain unrelated experiments and named archives for later review.

Branches before: 36
PR-governed targets: 9
Candidates including operational branch: 10
Deleted: 10
Pre-delete skips: 0
Mutation skips: 0
Failures: 0
Branches after: 26
