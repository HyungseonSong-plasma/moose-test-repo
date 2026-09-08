# Physics runtime CI contract

This directory documents the permanent runtime-consumer boundary established by #163 and the canonical Physics source/runtime ownership migration.

## Ordinary CI

Ordinary harness validation consumes a prebuilt runtime by immutable OCI digest. It does not compile the application, MOOSE, modules, Crane, Squirrel, or Zapdos.

```text
physics_harness / tests change
        ↓
immutable runtime digest
        ↓
provenance assertions
        ↓
physics-opt --check-input
        ↓
bounded real Physics solve
```

The current accepted consumer digest is still the pre-migration compatibility runtime:

```text
ghcr.io/hyungseonsong-plasma/qpx-runtime@sha256:140d7b3d1bf9b20575f624de66af3f17dc47b8f926dbbeaadfe19e1efa516691
```

Its accepted build base is also a pre-migration immutable artifact:

```text
ghcr.io/hyungseonsong-plasma/qpx-build-base@sha256:910d406eb3574a918290dc3621df1133569907d6e7af7884f68abe257a9a1999
```

These artifact names are compatibility inputs, not canonical repository naming. They remain pinned until a `physics-runtime` candidate is actually produced and validated by immutable digest.

Historical provenance carried by the accepted compatibility image remains unchanged:

```text
source owner              moose-test-repo/qpx_app
source repository SHA     c07a72d62dadb25e9ff1b7be5458ec3abef204fb
source manifest SHA256    5acc95407813971b5816395242a05111bcfa09e333e897825751e7eed4f60ecb
MOOSE                      9f388366ccf38b9c34542ec5561198249fde0ac9
Crane                      ba26970cf419dcac563a20ed7079d445bc6341c3
Squirrel                   16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1
Zapdos                     9eceffbc46048c3760bbfa9a7f1ca681ae35af1d
```

The consumer workflow verifies those immutable labels before execution.

## Source-build lane

Changes under `physics_app/**` use the source validation lane. That lane consumes the accepted immutable build base, compiles the canonical source, runs `--check-input`, and runs the bounded real smoke case.

```text
physics_app source change
        ↓
immutable build-base digest
        ↓
compile Physics only
        ↓
check-input + bounded solve
```

Implementation source, smoke input, dependency lock, and CI validation are reviewed from one repository revision.

## Runtime producer

The runtime producer consumes `physics_app/` directly from the checked-out repository revision and builds a new `ghcr.io/hyungseonsong-plasma/physics-runtime` candidate using the repository-local `ci/physics-runtime-image/` contract.

The new runtime layout is:

```text
/opt/physics/physics-opt
/opt/physics/ci/smoke.i
io.physics.* OCI provenance labels
```

The candidate must be published and validated before the consumer digest is rotated.

## Runtime rotation

A new runtime digest must not replace the accepted digest merely because a mutable tag changed. Rotation requires recorded evidence that the candidate:

1. identifies canonical Physics source owner, source manifest, and repository revision;
2. identifies the exact build-base digest and pinned dependency revisions;
3. passes `physics-opt --check-input` on the accepted smoke input;
4. passes the bounded real Physics smoke solve;
5. contains no compiler or framework source build requirement for ordinary CI;
6. does not change scientific semantics as part of infrastructure rotation.

Only after those gates pass should `.github/workflows/physics-runtime-consumer.yml` be updated to the new immutable `physics-runtime` digest.

## Source ownership boundary

Canonical Physics source ownership is `physics_app/` in this repository. Historical source archives, external compatibility patches, and direct dependency gitlinks are not part of the permanent CI contract.

Build products remain OCI/runtime artifacts and must not be committed to the canonical source tree.

## Scientific scope

The smoke checks prove executable/runtime availability and bounded execution only. They are not scientific validation or a replacement for physics/numerics V&V.
