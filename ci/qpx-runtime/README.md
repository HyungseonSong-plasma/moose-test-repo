# QPX runtime CI contract

This directory documents the permanent runtime-consumer boundary established by #163 and the canonical QPX source/runtime ownership completed by #165.

## Ordinary CI

Ordinary harness validation consumes a prebuilt QPX runtime by immutable OCI digest. It does not compile QPX, MOOSE, modules, Crane, Squirrel, or Zapdos.

```text
qpx_harness / tests change
        ↓
ghcr.io/hyungseonsong-plasma/qpx-runtime@<digest>
        ↓
provenance assertions
        ↓
qpx-opt --check-input
        ↓
bounded real QPX solve
```

Current accepted runtime:

```text
ghcr.io/hyungseonsong-plasma/qpx-runtime@sha256:140d7b3d1bf9b20575f624de66af3f17dc47b8f926dbbeaadfe19e1efa516691
```

Its accepted build base is:

```text
ghcr.io/hyungseonsong-plasma/qpx-build-base@sha256:910d406eb3574a918290dc3621df1133569907d6e7af7884f68abe257a9a1999
```

Canonical source and pinned dependency provenance:

```text
QPX source owner
         moose-test-repo/qpx_app
QPX source repository SHA
         c07a72d62dadb25e9ff1b7be5458ec3abef204fb
QPX source manifest SHA256
         5acc95407813971b5816395242a05111bcfa09e333e897825751e7eed4f60ecb
MOOSE    9f388366ccf38b9c34542ec5561198249fde0ac9
Crane    ba26970cf419dcac563a20ed7079d445bc6341c3
Squirrel 16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1
Zapdos   9eceffbc46048c3760bbfa9a7f1ca681ae35af1d
```

The consumer workflow verifies the runtime OCI labels against these expected values before execution.

## Source-build lane

Changes under `qpx_app/**` use the source validation lane. That lane consumes the accepted immutable `qpx-build-base`, compiles the canonical source, runs `--check-input`, and runs the bounded real smoke case. The build-base already owns the expensive framework/dependency compilation surface.

```text
qpx_app source change
        ↓
qpx-build-base@digest
        ↓
compile QPX only
        ↓
check-input + bounded solve
```

Implementation source, smoke input, dependency lock, and CI validation are therefore reviewed from one repository revision rather than reconstructed from external archive chunks.

## Runtime producer

The permanent runtime producer also consumes `qpx_app/` directly from the checked-out repository revision. It no longer reconstructs QPX from base64 source chunks and does not require external compatibility patches.

The accepted runtime rotation was produced by GitHub Actions run `34110792475` from repository revision `c07a72d62dadb25e9ff1b7be5458ec3abef204fb`.

Recorded producer acceptance:

```text
CANONICAL_QPX_SOURCE_OWNER=moose-test-repo/qpx_app
IMPLEMENTATION_AND_TEST_REVISION_SHARED=true
QPX_RUNTIME_IMAGE_PUBLISHED_BY_DIGEST=PASS
QPX_RUNTIME_PROVENANCE_INCLUDES_REPOSITORY_SHA=PASS
QPX_CHECK_INPUT_SMOKE=PASS
BOUNDED_REAL_QPX_RUN=PASS
EXTERNAL_COMPAT_PATCH_TRANSPORT_REQUIRED=false
SCIENTIFIC_SEMANTICS_CHANGED=false
```

## Runtime rotation

A new runtime digest must not replace the accepted digest merely because a mutable tag changed. Rotation requires recorded evidence that the candidate:

1. identifies its canonical QPX source owner, source manifest, and repository revision;
2. identifies the exact build-base digest and pinned dependency revisions;
3. passes `qpx-opt --check-input` on the accepted smoke input;
4. passes the bounded real QPX smoke solve;
5. contains no compiler or framework source build requirement for ordinary CI;
6. does not change scientific semantics as part of infrastructure rotation.

Only after those gates pass should `.github/workflows/qpx-runtime-consumer.yml` be updated to the new immutable digest.

## Source ownership boundary

Canonical QPX source ownership is `qpx_app/` in this repository. The temporary prototype transport used by #162/#163 — source archive chunks, external compatibility patches, and direct dependency gitlinks — is not part of the permanent CI contract and must not be used by ordinary CI or the permanent runtime producer.

Build products remain OCI/runtime artifacts and must not be committed to the canonical source tree.

## Scientific scope

The smoke checks prove executable/runtime availability and bounded execution only. They are not scientific validation or a replacement for physics/numerics V&V.
