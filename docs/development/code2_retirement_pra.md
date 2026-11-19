# code2 PR-A — T2 compatibility decision and exact-head evidence

Target: `PhysicsFVElectronEnergyJouleHeating.C/.h`. **PRE_RETIREMENT / SAFE_DELETE=HOLD.** No physics source or Factory changes in this PR.

## Static T1 census (baseline d0010827910581a1ca3bf4b405846a9960416c39)
- Tracked `.i` 153 files: only `physics_app/ci/electron_energy_joule_smoke.i` declares this class (3 instances).
- Workflow YAML 39 files: no direct old type or Joule smoke invocation. Hybrid workflow merely path-filters `prepare_cases.py`; actual staged hybrid keeps FEM electron energy.
- Physics C++ source 56 and headers 64: exact class name occurs only in its own C/H.
- `prepare_cases.py::fvm()` emits `state_form=molar_eV`, invalid under the C++ `MooseEnum("normalized physical_eV")`. Do not silently remap state units.
- Issue351 `control.py` consumes historical qualified Gen34 files but explicitly runs them with current-branch `physics-opt`: historical source preservation **does not** establish current-binary replay compatibility after Factory removal.

## T2 disposition
| Consumer | Proposed treatment | Unresolved gate |
| --- | --- | --- |
| Joule smoke 3 FV objects | Retain as source-level physics test baseline; later replace or explicitly retire test | native drift/diffusion/sign/AD characterization |
| FVM discriminator generator | HOLD: invalid declared mode, generated output unobserved | decide unsupported-generator sunset vs reviewed repair |
| Issue351 qualified Gen34 | Preserve historical source/artifacts; **do not assume replay with new binary works** | explicit legacy current-binary compatibility retirement or qualified rerun alternative |
| Hybrid staged workflow | No direct evidence for FV Joule Kernel | confirm staged final input and dynamic paths |
| Other dynamic/external inputs | HOLD UNKNOWN | declared support scope and independent caller coverage |

Path A (no supported active FV consumer) is **conditional**, not approved. Path B requires an independently validated electric-work replacement. Both keep shared `PhysicsElectronFluxModel` and historical artifacts protected.

## PR-A evidence
`ci/guards/code2_retirement_snapshot.sh` runs Structural v0.3 → Functional v0.2 → Transition v0.1 using the **exact clean PR HEAD**, checks graph joins and required HOLD, writes `structural.json`, `functional.json`, `transition.json`, and `summary.json` with sha256 identities. Repository CI uploads the snapshot only for `issue-code2-retirement-pra` PR. Structural rc=2 (`INCOMPLETE`) is preserved, not promoted to PASS.

**PR-B deletion gates:** explicit owner compatibility policy, effective current/generated/external scope, active profile retirement lifecycle and historical snapshot, P0/P1/P2/P3/rollback review as applicable, post-change source-absence and residual/AD checks. **No C++ deletion or Native claims here.**
