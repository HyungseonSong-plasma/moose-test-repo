# Issue #633 — one ion-wall Factory, no C2 helper workaround

**Status:** implementation branch; Native P2 / 417 / 941 P05 acceptance and
scientific trajectory equivalence are not claimed by this source refactor.

## Canonical implementation

- `IonWallFluxMaterial` is the **only** maintained ion-wall FunctorMaterial
  class and the only ion-wall Factory implementation registered by PhysicsApp.
- The duplicate `PhysicsIonWallFluxMaterial.{C,h}` implementation is deleted,
  not wrapped, aliased, or retained as a second registration.
- `Chemistry.C` already requests `IonWallFluxMaterial`; modern maintained
  case inputs, tests, scripts, and CI file watches use the same name.
- `IonWallC2Detail` was a temporary namespace used to avoid two otherwise
  byte-equivalent implementations having duplicate Unity-translation-unit
  helper symbols. With the duplicate implementation deleted, use an ordinary
  anonymous namespace and uniquely named `ionWall*` internal helpers.
  This is Unity-safe without a parallel class or a C2-specific helper scope.

## Physics preservation

Before refactoring, the two C++ source files were compared line-for-line after
normalizing their class name and namespace qualifiers: **0 differing lines**.
The refactor changes only the class/Factory identity and private helper names.
The existing six Functor outputs, face orientation, gradients, charge sign,
temperature selection, outward migration gating, ion flux and mass conversion
remain unchanged. Analytical parity tests still cover O2p, Om, Op, the
thermal/migration gate, both temperature modes, and signed drift fields.

## Immutable historical S6 inputs

Historical 10/11-layer archives and source SHA manifests are never rewritten.
The existing `canonicalize_staged_wall_inputs` path deliberately recognizes
the historical factory strings `PhysicsIonWallFluxMaterial` and
`PhysicsIonWallTotalFluxMaterial` **as untrusted input spellings only**.
It validates exact species, density, charge, source owner and downstream consumer
before emitting **only** `type = IonWallFluxMaterial` in disposable Scratch.
The archived `source_type` receipt retains the original spelling so historical
provenance remains auditable. This is a data migration, **not** a runtime
compatibility Factory alias. Canonicalization remains fail-closed.

## Validation

1. New regression rejects old C++ header/source reintroduction and rejects
   `IonWallC2Detail`, missing single Factory registration, and old runtime
   class references in active PhysicsApp C++ sources.
2. Rewritten S6 wall canonicalization tests require archived old-name inputs
   to produce only the new type while retaining exactly verified old-input SHA.
3. Species-wall smoke, wall semantic parity, public S6 source-stage and
   legacy-Physics-owner guard tests target the sole implementation.
4. Build the exact source HEAD against the pinned MOOSE/PhysicsApp toolchain.
   Next, run full protected-rate / original-mesh S6-417/941 Native
   `--check-input` and inspect P05 Warehouse 12 FV Kernels + 12 ion FV BCs
   and D8 consumer liveness. **No Native/P3/P4 science PASS from Python tests.**

Original archived output, private Rate bytes and main branch remain unchanged.
