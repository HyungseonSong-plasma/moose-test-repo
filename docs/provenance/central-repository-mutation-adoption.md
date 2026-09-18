# Central repository-mutation v1 adoption

Issue: #270

Qualified central source:

`HyungseonSong-plasma/chatgpt-operation@661ca7fe3b214e9ca8ac802d517fa1e40f65ecca`

Qualification contract:

- exact central source blobs and test suite are qualified in `moose-test-repo` CI;
- the central composite action is invoked directly from the exact central SHA above;
- the consumer policy authorizes only this provenance path on the Issue #270 branch;
- Repository CI validate, runtime-smoke, and central code qualification complete before the write-scoped action job;
- the central skill performs an exact-SHA file update through the GitHub Contents API;
- post-write read-back must match this desired content;
- a repeated qualification recognizes the achieved post-state before stale-identity rejection, converges to `NO_MUTATION_NEEDED`, and performs no second semantic write.

This document is maintained by the central repository-mutation skill and retained as migration provenance.
