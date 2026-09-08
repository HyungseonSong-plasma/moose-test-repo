# Physics source provenance

Canonical source owner: `moose-test-repo/physics_app`.

Imported for Issue #165 from the legacy clean-build prototype source artifact:

`sha256:4f9973c9e8e2dc07be5b485338cc0e921578e0dc754bca90c499d0071f199e03`

The two compiler-compatibility initializer-order fixes used by the clean-build prototype are incorporated directly into canonical source. They are semantics-preserving because C++ member initialization order is determined by declaration order, not initializer-list order.

Canonical imported file-manifest SHA256 (sorted `sha256sum` lines, excluding this provenance file):

`9b24097c02317e2d4cab16796328e50035c490cca7b240c582f4f2e2e84b47e0`

Dependency revisions are pinned in `dependencies.lock`.

No plasma physics, numerical algorithm, solver tolerance, or scientific state is changed by this import.
