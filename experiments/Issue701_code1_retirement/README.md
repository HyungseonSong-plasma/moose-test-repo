# Code1 R2 — isolated Native ON/OFF characterization (not deletion)

This Draft PR adds an intentionally small 1D four-cell Poisson input with
the existing registered \`FVElectronResponseBandedCorrection\` ON and OFF.
The only text difference is the kernel block. The synthetic response W is
4x4 row-sum-zero with half-bandwidth 1; material \`beta=160\` is an artificial
non-dimensional excitation for sensitivity, **not** qualified Gen34 physics.

The PR-specific step runs inside the immutable PhysicsApp build-base OCI
after the standard \`plasma_native_regression\` P1 build, using that job's
exact source-built \`physics-opt\` binary. It captures --check-input and
full-run logs for both arms. It is **nonblocking exploratory evidence**:
a parser error, failure to converge, identical fields, or successful runs
must not be promoted to functional equivalence, caller-zero or SAFE_DELETE.

Required follow-up before retiring C/H:
- Inspect step logs and the \`code1_native_onoff_receipt.json\` artifact;
  record exact binary, OCI, input SHA, return codes and outputs.
- Add a reliable residual/Jacobian or field observable if both arms run.
  Treat a trivial zero delta as an insufficiently sensitive discriminator.
- Preserve Issue #337/#351 historic input and independent pinned source.
- Require new-source clean build, present S6-417/941 generated inputs P2,
  and current supported P3 after an isolated deletion candidate is created.
- Keep Functional/Transition historical profile lifecycle and strict HOLD
  until explicit domain approval. Do not merge this Draft PR as a retirement.

Related: #701, #691, PR #706, harness bug comment #7012219505.
