# Physics runtime CI contract

This directory documents the permanent runtime-consumer boundary for Issue #182 and the public Physics CI migration.

## Target artifact chain

```text
physics-build-base@sha256:<digest>
        ↓
compile current physics_app only
        ↓
physics-runtime@sha256:<digest>
        ↓
ordinary public CI / fork-safe runtime validation
```

The dependency revisions are frozen in `physics_app/dependencies.lock`. The build-base producer compiles the pinned MOOSE/modules + Crane + Squirrel + Zapdos surface once. The runtime producer then compiles only the current `physics_app` source and packages the dependency-driven runtime closure.

## Private preparation state

Before repository visibility changes, both artifact-producing workflows are intentionally `workflow_dispatch` only. No private CI execution is required for repository preparation.

The canonical image names are:

```text
ghcr.io/hyungseonsong-plasma/physics-build-base
ghcr.io/hyungseonsong-plasma/physics-runtime
```

`physics_app/dependencies.lock` uses a `PENDING_PUBLICATION` digest marker until the first accepted public `physics-build-base` digest exists. That marker must be replaced by the real immutable digest before automatic source/runtime validation is restored.

## Ordinary CI

Ordinary harness validation must consume a prebuilt public runtime by immutable OCI digest. It must not compile the application, MOOSE, modules, Crane, Squirrel, or Zapdos.

```text
physics_harness / tests change
        ↓
public physics-runtime@digest
        ↓
Physics provenance assertions
        ↓
physics-opt --check-input
        ↓
bounded real Physics solve
```

The public runtime consumer deliberately performs no GHCR login. A successful cold pull therefore proves that ordinary/fork-style CI does not require private package credentials.

## Source-build lane

Source-build validation is paused while no accepted `physics-build-base` digest exists. After the first public build-base publication, controlled source-build validation can be restored against that immutable digest using `/opt/physics_vendor/*` only.

## Runtime producer

The runtime producer consumes `physics_app/` directly from the checked-out repository revision and builds a new `ghcr.io/hyungseonsong-plasma/physics-runtime` candidate using the repository-local `ci/physics-runtime-image/` contract.

The runtime layout is:

```text
/opt/physics/physics-opt
/opt/physics/ci/smoke.i
/opt/physics_vendor/...   # build-time provenance/runtime data only as required
io.physics.* OCI provenance labels
```

The candidate must be published and validated by immutable digest before automatic ordinary CI is enabled.

## Runtime rotation

A new runtime digest must not replace an accepted digest merely because a mutable tag changed. Rotation requires recorded evidence that the candidate:

1. identifies canonical Physics source owner, source manifest, and repository revision;
2. identifies the exact `physics-build-base` digest and pinned dependency revisions;
3. passes `physics-opt --check-input` on the accepted smoke input;
4. passes the bounded real Physics smoke solve;
5. is publicly pullable without private package credentials;
6. contains no compiler or framework source build requirement for ordinary CI;
7. does not change scientific semantics as part of infrastructure rotation.

Only after those gates pass should `.github/workflows/physics-runtime-consumer.yml` be pinned to the accepted `physics-runtime` digest and ordinary push/pull-request triggers be restored.

## Source ownership boundary

Canonical Physics source ownership is `physics_app/` in this repository. Build products remain OCI/runtime artifacts and must not be committed to the canonical source tree.

## Scientific scope

The packaging/runtime smoke checks prove executable/runtime availability and bounded execution only. They are not scientific validation or a replacement for physics/numerics V&V.
