# QPX runtime CI contract

This directory documents the permanent runtime-consumer boundary established by #163.

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
ghcr.io/hyungseonsong-plasma/qpx-runtime@sha256:3b815121ace89a5431e037aa37b96d9b1fd198185ae63e5fa9d4818b4b79acad
```

Its accepted build base is:

```text
ghcr.io/hyungseonsong-plasma/qpx-build-base@sha256:910d406eb3574a918290dc3621df1133569907d6e7af7884f68abe257a9a1999
```

Pinned dependency provenance:

```text
MOOSE    9f388366ccf38b9c34542ec5561198249fde0ac9
Crane    ba26970cf419dcac563a20ed7079d445bc6341c3
Squirrel 16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1
Zapdos   9eceffbc46048c3760bbfa9a7f1ca681ae35af1d
QPX source snapshot SHA256
         4f9973c9e8e2dc07be5b485338cc0e921578e0dc754bca90c499d0071f199e03
```

The consumer workflow verifies the runtime's OCI labels against these expected values before execution.

## Runtime rotation

A new runtime digest must not replace the accepted digest merely because a mutable tag changed. Rotation requires recorded evidence that the candidate:

1. identifies its canonical QPX source revision/provenance;
2. identifies the exact build-base digest and pinned dependency revisions;
3. passes `qpx-opt --check-input` on the accepted smoke input;
4. passes the bounded real QPX smoke solve;
5. contains no compiler or framework source build requirement for ordinary CI;
6. does not change scientific semantics as part of infrastructure rotation.

Only after those gates pass should `.github/workflows/qpx-runtime-consumer.yml` be updated to the new immutable digest.

## Source ownership boundary

The temporary source archive chunks, external compatibility patches, direct dependency gitlinks, and clean-build prototype workflow used to prove #162/#163 are **not** part of this permanent runtime-consumer contract.

Canonical QPX source ownership and the permanent runtime producer are tracked separately in #165. Until that migration is complete, this repository consumes the already accepted immutable runtime without promoting the prototype source transport into `development`.

## Scientific scope

The smoke checks prove executable/runtime availability and bounded execution only. They are not scientific validation or a replacement for physics/numerics V&V.
