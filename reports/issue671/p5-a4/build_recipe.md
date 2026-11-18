# P5-A4 — PhysicsApp source-bound P1 / OCI reproducibility

**Issue:** #671 · **Status:** `PASS_SOURCE_RECIPE_ONLY` / actual P1 build `NOT_RUN`.

## Exact source and immutable build environment

- Draft PR #665 observed HEAD `395eeac274125ffa632b4d75a4531996dee24fe0`, Git tree `0d14b997f24a1458f085bd0d1d766d2d34ecb22d`.
- Base `ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`, platform `linux/amd64`, CI host `ubuntu-24.04`.
- Pinned dependencies: MOOSE `9f388366ccf38b9c34542ec5561198249fde0ac9`, CRANE `ba26970cf419dcac563a20ed7079d445bc6341c3`, SQUIRREL `16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1`, ZAPDOS `9eceffbc46048c3760bbfa9a7f1ca681ae35af1d`.
- Outer OCI digest is immutable. Base Dockerfile uses upstream `idaholab/moose-dev:2026.06.16` as its original build input.
- Build inside image: `source /environment`; `MOOSE_DIR=/opt/physics_vendor/moose`, `CRANE_DIR=/opt/physics_vendor/crane`, `SQUIRREL_DIR=/opt/physics_vendor/squirrel`, `ZAPDOS_DIR=/opt/physics_vendor/zapdos`; `METHOD=opt`; `make -C physics_app -j2 app_non_unity_dirs='%/utils'`.
- Source blobs: `physics_app/dependencies.lock=0aae0ffb5699fcd5c17e8ebe9ea4f2effde9ff47`, `physics_app/Makefile=07cc31f9274d598a3363cd3c7a8d5d589707294f`, `run_native_binding_smoke.sh=1258279bbcd4df06381a7e398a750c0834dd0931`, `.github/workflows/ci.yml=c8cbd38369108229af7cf2395893a4539f05e024`.

## P5-0 build steps — future run, not performed in P5-A4

Run in a new, clean detached checkout at the exact HEAD. **Do not run against this receipt branch** because it contains only evidence commits. This compact recipe follows the canonical `run_native_binding_smoke.sh` P1 build; the independent full shell recipe `p5_a4_build_recipe.sh` also checks every vendor SHA and OCI image label, records toolchain versions, and creates a JSON P1 identity receipt.

~~~bash
set -euo pipefail
HEAD_PIN=395eeac274125ffa632b4d75a4531996dee24fe0
TREE_PIN=0d14b997f24a1458f085bd0d1d766d2d34ecb22d
OCI=ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008

test "$(git rev-parse HEAD)" = "$HEAD_PIN"
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE_PIN"
test -z "$(git status --porcelain --untracked-files=no)"
test ! -e physics_app/physics-opt  # Never reuse a stale P1 executable.
grep -Fxq "PHYSICS_BUILD_BASE=$OCI" physics_app/dependencies.lock

docker pull --platform linux/amd64 "$OCI"
docker image inspect "$OCI" > /tmp/p5-a4-oci-inspect.json
docker run --rm --platform linux/amd64 --network none \
  --entrypoint /bin/bash --user 0:0 -w /workspace \
  -v "$PWD:/workspace" -e "EXPECTED_HEAD=$HEAD_PIN" "$OCI" -lc '
    set -euo pipefail
    source /environment
    git config --global --add safe.directory /workspace
    test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"
    export MOOSE_DIR=/opt/physics_vendor/moose
    export CRANE_DIR=/opt/physics_vendor/crane
    export SQUIRREL_DIR=/opt/physics_vendor/squirrel
    export ZAPDOS_DIR=/opt/physics_vendor/zapdos
    export METHOD=opt
    make -C physics_app -j2 app_non_unity_dirs="%/utils"
    test -x physics_app/physics-opt
  '
sha256sum physics_app/physics-opt  # Must capture output in an exclusive artifact.
~~~

The complete P5-A4 local replay script SHA256 is `3cd720c01d26ecb483e0245df6b0a15462f6f92ed9c6517783ed472978e5226d`. It has passed `bash -n`, embedded receipt Python compilation, non-checkout rejection and wrong-HEAD rejection. **No Docker build has been attempted by this slot.**

## P5-0 acceptance must produce new evidence

Actual executable SHA256, native build log SHA256, compiler executables/versions, Docker image inspect SHA256 and vendor source readback must be recorded **from the same P1 job**. A cached binary or previously built `physics-runtime` image is not a valid substitute for the source-bound P5-0 build.

The 417 and 941 Native P2 jobs must share this one binary SHA but have independent Scratch/input/log/Artifact paths. No `--check-input`, P05 runtime, timestep, P3 or P4 is executed in this source-only slot.

**Blocking dependency:** P4-X (#670) has not delivered a final source cutover. Once it changes PR #665 HEAD, the `HEAD_PIN` and `TREE_PIN` above become stale and must be deliberately refreshed with a newly source-bound P1 build. Do not silently reuse this exact-head receipt as current P5 proof.

**References:** `.github/workflows/ci.yml`, `run_native_binding_smoke.sh`, `physics_app/dependencies.lock`, `ci/physics-build-base/Dockerfile`, `.github/workflows/physics-build-base.yml`; P3-X source-only CI #44257739203; Issue #671.

**Gates:** `P5_A4_RECIPE=PASS`; `P5_0_BINARY=NOT_RUN`; `P4_X=HOLD`; `NATIVE_P2/P3/P4=NOT_RUN`; `SCIENCE_HOLD`.
