# Code1 PR-A — frozen FDEG baseline and historical profile lifecycle

**Target:** FVElectronResponseBandedCorrection.C/.h
**Baseline source commit:** d0010827910581a1ca3bf4b405846a9960416c39
**Status:** PRE_RETIREMENT / HOLD. No C++ implementation is deleted.

PR-A keeps immutable reviewed Functional and Transition profiles at
ci/baselines/fdeg_historical_profiles_code1.json, together with original
C/H blob identities, historical Issue #337/#351 run identifiers, and the
critical rule that historical parity had this kernel in **both** lanes.

ci/baselines/fdeg_profile_lifecycle.json records the current candidate
status separately. ci/guards/fdeg_profile_lifecycle.py checks its exact
archived blob ID, source/header bytes, active registry correspondence,
and negative cases; a future RETIRED state requires separate explicit
owner approval and Native receipt. The guard never grants retirement.

ci/guards/fdeg_retirement_snapshot.py generates Structural v0.3,
Functional v0.2, and Transition v0.1 reports from the same exact PR HEAD,
and a SHA-256 / graph-id manifest. A PR-A-only Repository CI step uploads
these four JSON files with 90-day artifact retention. Preserve an external
durable copy and record its run/artifact ID before a deletion PR.

**Unresolved:** generated poisson_sub.i activation, effective anchor/beta/
matrix/phi providers, external consumers, ON/OFF residual and Jacobian
effects, numerical tolerances, and legacy current-binary compatibility.
FDEG P0 cannot promote any of these to verified. Transition remains
CONDITIONAL_PLAN / NOT_EXECUTED; SAFE_DELETE=HOLD.

**PR-B (not part of this change):** approve current scope; preserve
historical pinned replay; perform bounded ON/OFF characterization;
remove target source/header and active profiles; guard against Factory
reintroduction; clean-build a new binary; verify current input P2 and
physical P3; require explicit owner acceptance before merge.
