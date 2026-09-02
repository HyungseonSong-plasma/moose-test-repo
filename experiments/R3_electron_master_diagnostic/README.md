# R3 electron master diagnostic

One-shot fault-isolation batch for the real-QVT pre-Poisson electron diffusion blocker.

## Design

- Reuses `qpx_harness` for case staging, executable validation, bounded QPX execution, runtime/Jacobian diagnostics, evidence serialization, and persistent error logging.
- Runs **all required P2 checks before any scientific P3 run**.
- Runs all supported low-cost P3 discriminators even after one case fails so secondary owners are not hidden by first-failure stopping.
- Runs only selected expensive Jacobian probes after the residual matrix is classified.
- Geometry/RZ/qvt topology is **held fixed and OUT_OF_SCOPE**, not exonerated.
- Optional pinned-version probes may become `SKIPPED_UNSUPPORTED`; required P2 failure blocks scientific execution.

## Matrix

The matrix spans:

- time-only and QPX baseline controls;
- literal / generic non-AD / generic AD / QPX coefficient delivery;
- coefficient interpolation (`harmonic`, `average`);
- two-term boundary reconstruction;
- variable and diffusion skewness correction;
- gradient caching;
- `MooseVariableFVReal` vs `INSFVScalarFieldVariable`;
- named boundary exclusion / FaceArg context;
- literal QPX lookup inputs where the pinned framework accepts them;
- automatic-scaling discriminator.

Every case keeps the frozen state

```text
n_e = 1e16 m^-3 uniform
p = 1.33322 Pa
T_g = 600 K
mean_en = 5.73276 eV
D_e = 41257.29899041419 m^2/s
E = 0
Poisson OFF
```

unless the case explicitly changes one diagnostic parameter.

## Run

```bash
python -m experiments.R3_electron_master_diagnostic.run \
  --qpx "$QPX_OPT"
```

Useful bounds:

```bash
--timeout 120
--jacobian-timeout 300
--jacobian-tolerance 1e-8
```

## Evidence

A timestamped QPX-local result root contains:

```text
identity.json
case_matrix.json
jacobian_matrix.json
final_diagnosis.json
summary.json
error_events.jsonl
run_error_stats.json
error_stats.json
cases/
logs/
jacobian/
```

The persistent ledger defaults to `~/.qpx_harness/error_ledger.jsonl` and may be overridden with `--error-ledger` or `QPX_ERROR_LEDGER`.

Attribution is conservative: `USER_ERROR`, `CHATGPT_ERROR`, `CODE_ERROR`, or `UNCLASSIFIED`. Scientific owner classification and operational error attribution are separate evidence products.
