# Native P1 build harness — application-scoped, adaptive, fail closed

**Status:** implementation on an isolated PR; not yet an OCI/native validation.
**Scope:** compile a reviewed exact-SHA MOOSE PhysicsApp against an existing immutable, source- and ABI-pinned vendor build image. No source or physics change, no global non-Unity rebuild, no secret handling or workflow activation.

## Why P1 required a different build command after the source change

The historical 400 W S6 P1 path executed the pinned source's replay build step with default Unity compilation (make -C physics_app -j2). The PR #491 candidate added C++ definitions in multiple physics_app/src/utils translation units. MOOSE's Unity generator concatenated them into the same utils_Unity.C, causing same-translation-unit anonymous-namespace symbol redefinitions; these are real C++ build failures, not runtime or model failures.

Attempting MOOSE_UNITY=false globally unintentionally rebuilt cached MOOSE and vendor dependencies rather than just the changed app. It eventually failed on a Squirrel PotentialAdvection.C / FEProblemBase incomplete-type error after a long compile, a vendor/dependency build failure unrelated to the new Boltzmann data. A subsequent nested Docker bash -lc script had an unescaped single quote in an awk expression, prematurely terminating the shell string and raising unbound variable $2 before C++ started. Neither warranted modifying the physics equations or reaction-rate data.

The successful P1 compilation kept MOOSE_UNITY=true, preserving the vendor cache, and passed MOOSE's app_non_unity_dirs with **only** physics_app/src/utils. CPU and memory constrained the parallel job count. The source-pinned native build and --check-input smoke completed successfully on [Repository CI #42796955120](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42796955120) and PR #494 exact-head CI.

## Harness policy

- **Profile auto (default):** start with src/utils outside app Unity if that directory exists. On an actual compiler redefinition failure associated with an application's *_Unity.C generated translation unit, infer its corresponding existing physics_app/src/<name> directory. Retry only with the additional **application** subdirectory excluded. The default retry budget is three total attempts; each is recorded, and no generic failure is retried. This handles known signature classes, not arbitrary C++ compilation failures.
- **Profile scoped:** use only explicitly supplied --non-unity-dir src/... directories, no adaptive retries. Suitable for a reviewed fixed profile.
- **Profile unity:** explicit all-app-Unity diagnostic mode. No exceptions and no adaptive retries. **No mode** can issue MOOSE_UNITY=false.
- **Guardrails:** verify a clean source checkout at the provided 40-hex SHA, reject an existing physics-opt or ignored stale physics_app/build cache (never auto-delete artifacts), require METHOD=opt and all four vendor environment variables pointing to immutable OCI paths, check that exclusions stay inside the actual app src/, and use an argument array for make (no nested shell interpolation of source paths).
- **Resources:** cap jobs at the lesser of CPU affinity, cgroup v1/v2 CPU quota, operator --max-jobs (default 4), and a conservative available-memory band. Respect /proc and cgroup v1/v2 memory limits. Unknown/low memory means one job.
- **Storage preflight:** inspect application filesystem capacity before compilation and before every safe retry. Default minimum free space is 1 GiB and minimum free inode count is 2,000; adjust explicitly with --min-free-mib and --min-free-inodes for a reviewed OCI host. Unknown inode accounting is not assumed exhausted. No cleanup of vendor or application caches occurs automatically.
- **Error classifier:** distinguish linker undefined/multiple symbols, runtime GLIBCXX/CXXABI mismatches, missing headers/generated inputs, out-of-memory, disk/inode exhaustion and shell expansion. These are **terminal**, even if an unrelated Unity filename appears in the build log; only actual application Unity redefinition has a bounded scoped retry. Symlinks escaping the app source tree are rejected in inferred retry directories.
- **Evidence:** write per-attempt restricted build logs and structured JSON with the SHA, planned make argv, scopes, CPU and storage headroom, jobs, error category and executable SHA256. Do not print restricted rate data, environment secrets or full logs into public CI artifacts. Optional --smoke-input ci/smoke.i runs physics-opt --check-input after compilation.
- **Failure policy:** vendor/ABI errors, unknown compiler errors, OOM, timeout, shell errors, smoke errors and missing executable are all terminal. A subprocess exit without a real executable is not P1 PASS.

## Usage from a trusted OCI host

The host verifies the OCI reference
ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008
and MOOSE vendor revision before launching the container. Mount the **exact reviewed candidate** at /app (rw) and the **harness** checkout at /harness (ro). Do not invoke modified PR code under a secret-bearing unreviewed workflow.

Example **inside** that reviewed OCI container, after sourcing /environment:

~~~sh
export MOOSE_DIR=/opt/physics_vendor/moose
export CRANE_DIR=/opt/physics_vendor/crane
export SQUIRREL_DIR=/opt/physics_vendor/squirrel
export ZAPDOS_DIR=/opt/physics_vendor/zapdos METHOD=opt

python3 /harness/physics_harness/execution/native_build.py \
  --source-root /app \
  --expected-sha YOUR_EXACT_40_CHARACTER_SOURCE_SHA \
  --profile auto \
  --max-jobs 4 \
  --min-free-mib 1024 \
  --min-free-inodes 2000 \
  --log-dir /app/.native_p1_attempts \
  --report /app/.native_p1_attempts/report.json \
  --smoke-input ci/smoke.i
~~~

The Issue #493 trusted experiment runner delegates P1 compilation to this harness and otherwise preserves its pinned candidate, historical source, per-case B/C sequencing and SCIENCE_HOLD.

Run source-only tests without Docker or private rates:

~~~sh
python3 -m unittest discover -s tests/unit -p test_native_build_harness.py -v
python3 experiments/Issue493_s6_boltzmann/test_run_issue493.py
~~~

The older Issue #494-only workflow job remains historical, not a reusable entrypoint. Future Native P1 execution should invoke the harness from the repository's approved governed workflow or trusted OCI runner, without creating a standalone secret workflow or modifying the workflow allowlist.

**Verification separation:** PR #496 exact-head Native P1 compiled successfully in pinned OCI with a real --check-input smoke; this does not automatically validate new preflight/classifier behavior on a real constrained host. Changes to these policies require their own exact-head CI and validation. Neither result covers S6 P2–P4 numerical or scientific outcome.
