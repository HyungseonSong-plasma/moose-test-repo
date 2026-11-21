# Code4 PR-B — bounded Electrostatic Drift A/B qualification

**Tracking:** #708, depends on PR-A #703's three verified FDEG graphs. Source kernel **not modified**.

## Decision boundary

The existing raw-scalar FV face flux is
`F_n=carrier_f * u_up * z * mobility_f * [-grad(phi)_f dot n]`.
A standard `FVAdvection` has `F_n=u_up * (velocity dot n)`.
These are equivalent **only for a limited case** where all of the following hold:

- `carrier>0`, and carrier and mobility are constants, so they may be absorbed into an externally prescribed constant velocity
- `phi` has an exactly constant spatial gradient, `velocity=-z*mu*carrier*grad(phi)`
- the transported FV state is **raw u**, with identical upwind discretization and limiter state
- both kernels exclude external boundary faces, so BC flux is independently owned
- no additional producer, AD coupling, wall, time-changing coefficient or charge balance equivalence is claimed

The tested candidate is the standard MOOSE `FVAdvection`, **not** the log-molar `PhysicsFVLogMolarElectrostaticDrift`. `FVAdvection` does **not** solve the general variable-coefficient or dynamic potential problem; `FVMatAdvection` needs a separate velocity Functor source and independent proof, including face/limiter/Jacobian differences.

## Independent controls

`bounded_ab.py` creates five controlled cases (positive/negative charge, zero E, zero mobility, carrier=2), each with an unchanged incumbent and standard FV candidate. A separate algebraic face oracle asserts signed direction, upwind selection, carrier scaling and normal reversal; negative controls reject a wrong sign/omitted carrier. A standalone finite-volume implicit upwind reference predicts cell extrema and integral for a nonuniform initial raw scalar on 12 cells and three time steps.

**Native P1/P2/P3 is a separate gate.** Pass only on a source-pinned exact binary when all ten input files pass `--check-input`, all ten time integrations finish, A/B observed extrema/integral agree within predeclared bounded tolerance, and an independent conservative FV reference also agrees. Preserve the full CSV/log/input hash set, binary SHA, OCI digest, and source SHA. If P1/P2 fails, classify it as construction failure, not physics failure.

### Nonclaims

- A bounded constant-coefficient success does **not** approve `FVAdvection` for actual Stage5/S6 consumers with variable `mobility/carrier` or solved `phi`.
- No general FE/FV gradient, dynamic provider, off-diagonal AD/Jacobian, wall/sheath ownership, or HeavyMassCorrection cancellation parity has been established.
- Issue #192 historical generator lifecycle ambiguity from #696/#701 remains unresolved.
- Do not modify current Factory, Python generator, `.C/.h`, or operational test assertions.
- `SAFE_DELETE=HOLD` for all PR-B states.

## Commands

```sh
python3 -m unittest discover -s tests -p test_code4_drift_bounded_ab.py -v
python3 experiments/code4_drift_retirement/bounded_ab.py --prepare \
  --directory /tmp/code4-bounded --expected-head "$(git rev-parse HEAD)"
# After separate exact-head P1 build, P2 check input, P3 ten Native runs:
python3 experiments/code4_drift_retirement/bounded_ab.py --analyze \
  --directory /tmp/code4-bounded --expected-head "$(git rev-parse HEAD)" \
  --binary-sha256 "<verified-executable-sha256>"
```

**Governed workflow policy:** One-shot Native collection runs on an isolated, never-merge evidence branch. Do not add an unauthorized permanent `.github/workflows` file to this PR. The PR-A #703 run demonstrated that the repository workflow-surface guard rejects such files.
