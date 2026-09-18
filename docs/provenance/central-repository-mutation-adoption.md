# Central repository-mutation v1 adoption

Issue: #270

Qualified central source:

`HyungseonSong-plasma/chatgpt-operation@2719adaca20bcb5833752e4ad8e69a2d136e56b6`

Qualification contract:

- exact central source blobs and test suite are qualified in `moose-test-repo` CI;
- the private composite action is invoked directly from the exact central SHA above;
- the consumer policy authorizes only this provenance path on the Issue #270 branch;
- Repository CI validate, runtime-smoke, and central code qualification complete before the write-scoped action job;
- the central skill performs a real file-create mutation through the GitHub Contents API;
- post-write read-back must match this desired content;
- a repeated qualification converges to `NO_MUTATION_NEEDED` and performs no second semantic write.

This document is created by the central repository-mutation skill itself and retained as migration provenance.
