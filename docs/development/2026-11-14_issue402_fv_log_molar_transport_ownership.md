# Issue #402 — FV log-molar transport owner retirement (2026-11-14)

**Scope:** exact-source ownership/name migration only. No change to ion drift,
diffusion, transient residual, wall-flux, Chemistry reaction/source, or energy
physics; no claim of S6 physical parity. **SCIENCE_HOLD** remains.

## Old and new owners

- Removed source/header: `PhysicsFVLogMolarElectronTransport.C/.h`.
- New canonical source/header: `PhysicsFVLogMolarTransport.C/.h`.
- Keep the same conservative FV log-molar backward-Euler, interior-face
diffusion, and signed electrostatic upwind drift implementation and parameter
contracts. Rename only `PhysicsFVLogMolarElectronTimeDerivative` to
`PhysicsFVLogMolarTimeDerivative`, and
`PhysicsFVLogMolarElectronDiffusion` to `PhysicsFVLogMolarDiffusion`.
- `PhysicsFVLogMolarElectrostaticDrift` was already species-neutral and keeps
its registered name, including FE-potential element-gradient and bounded
reconstruction behavior.
- Retire uncalled `PhysicsFVLogMolarElectronReactionSource` and its
`-number_source/N_A` residual. It accepts number-density rates and is
**not** an appropriate owner for the current Chemistry `S_<id>_molar`
source functors. The distinct, actively used `PhysicsFVElectronReactionSource`
class is **not** part of this retirement.

## Caller and evidence census

Live, maintained references in Issue #3 FV dielectric fixtures/generators,
`fem_fvm_plasma_discriminator` generators, the Issue #395 elastic-overlay
build guard, Issue #402 scratch D input (not its SHA-pinned source base), electron molar P0 contract,
retired-owner tests, and the ion-FVM hybrid workflow path filters are updated
to the canonical names. The workflow's build/run logic is unchanged.
The SHA256-pinned `native/s6_c0_physics_base_no_d1.i` is **byte-identical**
to the accepted one-time source
(`e49e7b63566f16e9eaede7e97ec232338b04a8cdfc019527d73bdb519521abfd`).
The `public_option_s6_p2.py` canonicalizer requires exactly three FV time
and three FV diffusion type fields in the scratch first layer, rewriting
only these disposable copies before Native P2/P3; unexpected references,
wrong counts and out-of-base owners fail before any write.
Historical `docs/provenance/issue256-t1-t2-canonical-promotion.md` retains
its immutable original path/blob audit; archived scientific sources remain
untouched. Old C++ class names are intentionally *not* registered as aliases.

## Validation boundary

P0 ownership/term-token self-tests and exact source-copy comparisons are
required on the migration branch; negative controls reject reintroduction of
the retired number-source class. The changed test/checker references must
be verified in CI. **Native P1 compile**, **Native P2 `--check-input`**, and
representative **P3 runtime parity** are separate required evidence gates
before any production/scientific acceptance. Creating a Draft PR or passing
Python P0 is not proof of Native compile, P2, P3, or P4 parity.

No historical S6 B/C input, archived experiment evidence, central Samuel
OS, or `main` is edited by this migration branch. No ion-energy equation is
created by this refactor. Ion DSL source wiring is a separate Issue #402 task.
