# Run-32 follow-up: preflight-gated transfer diagnostic

## Observation

The latest completed Issue-236 diagnostic workflow (run 35032700769) never reached A/B/C/D physics diagnostics. It failed in the runner preflight with a Python `SyntaxError` in `run_live_ci_transfer_diag.py`. Therefore no child/parent/heavy state comparison can be inferred from that run. The later branch head fixes that syntax error, but no new gated Issue-236 experiment is started by this redesign PR.

## Hypothesis

The next experiment should change no plasma physics. Its only experimental change is to make runner syntax a host-side hard gate before pulling/building the MOOSE container. If the corrected runner passes the syntax gate and its existing in-container `--self-test`, the same A/B/C/D diagnostic can finally execute without conflating harness failure with physics failure.

## Changed variable

- Add `python3 -m py_compile experiments/Issue236_m1a_multiapp_smoke/run_live_ci_transfer_diag.py` before dependency provenance/container work.

## Fixed variables

- Electron drift/diffusion/energy/Poisson physics.
- Heavy chemistry-off configuration.
- `dt_e = 1e-10` s.
- 100 fast substeps per heavy step.
- Transfer payloads and A/B/C/D diagnostic definitions.
- Pinned MOOSE/CRANE/SQUIRREL/ZAPDOS revisions and build-base digest.

## Discriminator

1. Host `py_compile` must pass.
2. Existing in-container `--self-test` must pass.
3. Only then may the expensive build/runtime begin.
4. Runtime evidence must contain A/B/C/D diagnostics; absence of those diagnostics is classified as harness failure, not a physics result.
5. No CI trigger marker is changed in this PR; execution remains a separate gated action.
