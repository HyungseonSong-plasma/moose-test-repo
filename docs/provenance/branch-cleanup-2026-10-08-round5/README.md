# Branch cleanup provenance — round 5

Date: 2026-10-08

Archive owner: `experiment-full-fem-contour-mesh` at `cbc4dfef6e8c4fefb6999e09860a6e23b281983f`.

Deletion contract:
- preserve active/open-PR and explicitly named archive/architecture branches;
- delete a remaining branch only when its exact tip is a Git ancestor of `experiment-full-fem-contour-mesh`;
- therefore the retained archive contains the deleted branch history;
- require fresh exact SHA and force-with-lease for deletion;
- leave branches not contained by the archive for separate semantic review.

Branches before: 27
Archive-contained candidates including operational branch: 11
Deleted: 11
Preserved: 7
Not contained by archive: 9
Mutation skips: 0
Failures: 0
Branches after: 16
