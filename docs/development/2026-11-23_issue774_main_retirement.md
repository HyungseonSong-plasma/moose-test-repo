# #774/#811 — latest-main Thermal and Heavy Mass source retirement

**Base:** `main@0755571b5d011f89a7473704337e23c042273381` (post-#816).
**Current PR scope:** delete only four active Factory C/H files, preserve
their exact Git blob bytes under `docs/development/archive/issue774_retired_factories/`,
adapt the FDEG post-cut capture contract to historical source validation, and
retain the existing split Repository/Physics Code/Physics Native CI. No
old `ci.yml` or `general-ci.yml` import from #807.

The New-only source register set becomes 11 FVKernel source files and 16
PhysicsApp FVKernel Factory registrations (down from 13/18); all four-
and three-owner shared log-molar translation units remain untouched.
Historical Issue192 S5-R/Issue282/audit route references are pinned as
research history and cannot be represented as supported current binary
inputs. Distinct QPX and all other Physics source operators are unchanged.

**Original source preservation:**
- Thermal source `6887710910c95f37f5f6ed94d4344384b297b4e0`;
  header `1845a3c793eefe72b8fbe22ba33df5324da26f36`.
- Heavy source `79bf6045942369bb483ab4e7480a08a5d1040d65`;
  header `57a56a1e5e3c7297283705b7d2d1dc1acdcd9ff2`.
Every archived .txt has byte-identical Git blob SHA; fail-closed
historical byte mutation tests must reject tampering.

**Evidence inherited for investigation, not reused as exact-main CI:**
[#807](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/807)
qualified Thermal New-only P0/P05 and Public D P2;
[#812](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/812)
qualified Heavy source-only retirement. Its W1/417/941 P05 native
verification [#45223391840](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45223391840)
is old-branch evidence only; current source SHA must receive its own
Native CI and original100 Public D 417/941 evidence.

**FDEG migration contract:** The former live FDEG `capture` step assumed
Thermal.C exists on the current HEAD, conflicting with its physical removal.
Keep the 10 original FDEG profile/transition policy entries unchanged as
historical profile data. Test the exact original byte-fixed Thermal
validParams/claim witnesses in an isolated temporary source tree; never
call this a live New-only witness. The post-cut CI exports a new SHA
pinned removal/archive receipt rather than fabricating an exact-HEAD
pre-retirement FDEG graph.

**Restrictions:** Not evidence of global dynamic/external caller-zero,
historical typed input compatibility, P3/P4 physical equivalence, or
release authorization. Do not merge to main unless exact-head Repository
CI, Physics Code CI, Physics Native W1, New-only P05 N1-N8, original100
Public D Native, and surviving FLOW/ARCH guards pass. No one-off Actions
or historical artifact deletion.